import { useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import { AccountsView } from "./accounts";
import { visibleConnections } from "./connections";
import { InvestmentsView } from "./investments";
import type { HistoryRow, InvestmentRow } from "./spending-history";
import {
  CategoryComparison,
  InvestmentComparison,
  InvestedTotal,
  InvestmentOverview,
  type InvestedRow,
  MonthlyComparison,
  MonthOverview,
} from "./spending-overview";
import {
  TransactionDetailCell,
  type TransactionDetails,
} from "./transaction-details";
import {
  deviceLocale,
  formatDate,
  formatMoney,
  LANGUAGE_KEY,
  messages,
  monthChoices,
  readLanguagePreference,
  type LanguagePreference,
} from "./locale";
import "./style.css";

type Connection = { id: string; is_demo: boolean; latest_month: string };
type Total = {
  currency: string;
  bucket: string | null;
  total: string;
  entries: string | number;
};
type Expense = TransactionDetails & {
  id: string;
  item: string;
  date: string;
  currency: string;
  amount: string;
  merchant: string;
  category: string;
  status?: "POSTED" | "PENDING";
};
type Review = Omit<Expense, "category"> & {
  operation?: string;
  decision: "" | "include" | "exclude";
};
type Spending = {
  connections: Connection[];
  selected: Connection | null;
  month: string | null;
  totals: Total[];
  history?: HistoryRow[];
  investments?: InvestmentRow[];
  invested?: InvestedRow[];
  expenses: Expense[];
  has_more_expenses?: boolean;
  reviews: Review[];
  categories: string[];
};

const years = Array.from(
  { length: 2148 - 1970 + 1 },
  (_, index) => 2148 - index,
);

function currentView(): "accounts" | "investments" | "spending" {
  const view = window.location.hash.slice(1);
  return view === "accounts" || view === "investments" ? view : "spending";
}

function App() {
  const [view, setView] = useState(currentView);
  const [preference, setPreference] = useState(readLanguagePreference);
  const locale =
    preference === "device" ? deviceLocale(navigator.languages) : preference;
  const [item, setItem] = useState("all");
  const [month, setMonth] = useState("");
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState("");
  const [searchInput, setSearchInput] = useState("");
  const [data, setData] = useState<Spending>();
  const [revision, setRevision] = useState(0);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<
    "loadError" | "saveError" | "reviewError"
  >();
  const [notice, setNotice] = useState<"saved" | "reviewSaved">();
  const [suggesting, setSuggesting] = useState(false);
  const [attempted, setAttempted] = useState<string[]>([]);
  const [suggestions, setSuggestions] = useState<Record<string, string>>({});
  const [suggestionStatus, setSuggestionStatus] = useState<
    "suggestionsReady" | "noSuggestions" | "suggestionsUnavailable"
  >();
  const copy = messages[locale];
  const number = new Intl.NumberFormat(locale);
  const [activeYear, activeMonth] = (month || data?.month || "").split("-");

  useEffect(() => {
    const switchView = () => setView(currentView());
    window.addEventListener("hashchange", switchView);
    return () => window.removeEventListener("hashchange", switchView);
  }, []);

  useEffect(() => {
    document.documentElement.lang = locale;
    document.title = `${view === "spending" ? copy.title : copy[view]} | ${copy.brand}`;
  }, [locale, copy, view]);

  function changeLanguage(value: LanguagePreference) {
    setPreference(value);
    try {
      if (value === "device") localStorage.removeItem(LANGUAGE_KEY);
      else localStorage.setItem(LANGUAGE_KEY, value);
    } catch {
      // The current session can still switch languages.
    }
  }

  useEffect(() => {
    if (view !== "spending") return;
    const request = new AbortController();
    const query = new URLSearchParams();
    if (item) query.set("item", item);
    if (month) query.set("month", month);
    if (search) query.set("search", search);
    if (page > 1) query.set("page", String(page));
    setLoading(true);
    setError(undefined);
    void fetch(`/api/spending?${query}`, { signal: request.signal })
      .then(async (response) => {
        if (!response.ok) throw new Error();
        const spending = (await response.json()) as Spending;
        if (!request.signal.aborted) setData(spending);
      })
      .catch(() => {
        if (!request.signal.aborted) setError("loadError");
      })
      .finally(() => {
        if (!request.signal.aborted) setLoading(false);
      });
    return () => request.abort();
  }, [item, month, search, page, revision, view]);

  useEffect(() => {
    setAttempted([]);
    setSuggestions({});
    setSuggestionStatus(undefined);
  }, [item, month]);

  const eligible = (data?.expenses ?? []).filter(
    (row) =>
      row.status !== "PENDING" &&
      row.category === "Uncategorized" &&
      row.merchant &&
      !attempted.includes(row.id),
  );
  const candidates = eligible
    .filter((row) => row.item === eligible[0]?.item)
    .slice(0, 4);
  const hasProposals = data?.expenses.some(
    (row) => row.category === "Uncategorized" && suggestions[row.id],
  );

  async function requestSuggestions() {
    if (!data?.selected || !candidates.length) return;
    const transactions = candidates.map((row) => row.id);
    const source = candidates[0].item;
    setSuggesting(true);
    setSuggestionStatus(undefined);
    try {
      const response = await fetch("/api/spending/suggestions", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ item: source, transactions }),
        signal: AbortSignal.timeout(65000),
      });
      if (!response.ok) throw new Error();
      const result = (await response.json()) as {
        suggestions: { id: string; category: string }[];
      };
      setSuggestions((current) => ({
        ...current,
        ...Object.fromEntries(
          result.suggestions.map(({ id, category }) => [id, category]),
        ),
      }));
      setAttempted((current) => [...current, ...transactions]);
      setSuggestionStatus(
        result.suggestions.length ? "suggestionsReady" : "noSuggestions",
      );
    } catch {
      setSuggestionStatus("suggestionsUnavailable");
    } finally {
      setSuggesting(false);
    }
  }

  async function save(
    path: "rules" | "reviews",
    entry: Pick<Expense, "id" | "item">,
    change:
      { category: string } | { decision: "include" | "exclude" | "reset" },
  ) {
    if (!data?.selected) return;
    setSaving(true);
    setError(undefined);
    setNotice(undefined);
    try {
      const response = await fetch(`/api/spending/${path}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          item: entry.item,
          transaction: entry.id,
          ...change,
        }),
        signal: AbortSignal.timeout(5000),
      });
      if (!response.ok) throw new Error();
      setNotice(path === "rules" ? "saved" : "reviewSaved");
      setRevision((value) => value + 1);
    } catch {
      setError(path === "rules" ? "saveError" : "reviewError");
    } finally {
      setSaving(false);
    }
  }

  const history = data?.history ?? [];
  const investments = data?.investments ?? [];
  const invested = data?.invested ?? [];
  const combined = data?.selected?.id === "all";
  const hasImportedConnections = data?.connections.some(
    (connection) => !connection.is_demo,
  );
  const connections = visibleConnections(data?.connections ?? []);
  const connectionLabels = new Map(
    data?.connections.map((connection, index) => [
      connection.id,
      `${copy.connection} ${number.format(index + 1)}`,
    ]),
  );
  const uncategorized =
    data?.totals
      .filter((row) => row.bucket === "Uncategorized")
      .reduce((sum, row) => sum + Number(row.entries), 0) ?? 0;

  return (
    <>
      <header className="topbar">
        <div className="frame masthead">
          <span className="brand">{copy.brand}</span>
          <div className="header-controls">
            <span className="private">{copy.workspace}</span>
            <label className="language">
              {copy.language}
              <select
                value={preference}
                onChange={(event) =>
                  changeLanguage(event.target.value as LanguagePreference)
                }
              >
                <option value="device">{copy.deviceLanguage}</option>
                <option value="en-US" lang="en">
                  English
                </option>
                <option value="pt-BR" lang="pt-BR">
                  Português (Brasil)
                </option>
              </select>
            </label>
          </div>
        </div>
      </header>
      <nav className="frame dashboard-nav" aria-label={copy.dashboardViews}>
        <a
          href="#spending"
          aria-current={view === "spending" ? "page" : undefined}
        >
          {copy.spendingView}
        </a>
        <a
          href="#accounts"
          aria-current={view === "accounts" ? "page" : undefined}
        >
          {copy.accounts}
        </a>
        <a
          href="#investments"
          aria-current={view === "investments" ? "page" : undefined}
        >
          {copy.investments}
        </a>
      </nav>
      {view === "accounts" && <AccountsView locale={locale} />}
      {view === "investments" && <InvestmentsView locale={locale} />}
      <main className="frame" hidden={view !== "spending"} aria-busy={loading}>
        <div className="intro">
          <h1>{copy.title}</h1>
          <div className="filters">
            <label>
              {copy.connection}
              <select
                value={
                  item === "all" && !hasImportedConnections
                    ? (data?.selected?.id ?? "")
                    : item
                }
                onChange={(event) => {
                  setItem(event.target.value);
                  setLoading(true);
                  setMonth(month || data?.month || "");
                  setPage(1);
                  setNotice(undefined);
                }}
                disabled={saving || suggesting || !data?.connections.length}
              >
                {hasImportedConnections && (
                  <option value="all">{copy.allConnections}</option>
                )}
                {!data?.connections.length && (
                  <option value="">{copy.selectConnection}</option>
                )}
                {connections.map((connection) => (
                  <option key={connection.id} value={connection.id}>
                    {connection.is_demo
                      ? copy.syntheticDemo
                      : connectionLabels.get(connection.id)}
                  </option>
                ))}
              </select>
            </label>
            <label>
              {copy.month}
              <select
                value={activeMonth || ""}
                disabled={
                  saving ||
                  suggesting ||
                  loading ||
                  !data?.selected ||
                  !activeYear
                }
                onChange={(event) => {
                  setPage(1);
                  setMonth(`${activeYear}-${event.target.value}`);
                }}
              >
                {!activeMonth && <option value="">—</option>}
                {monthChoices(locale).map(({ value, label }) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </select>
            </label>
            <label>
              {copy.year}
              <select
                value={activeYear}
                disabled={
                  saving ||
                  suggesting ||
                  loading ||
                  !data?.selected ||
                  !activeMonth
                }
                onChange={(event) => {
                  setPage(1);
                  setMonth(`${event.target.value}-${activeMonth}`);
                }}
              >
                {!activeYear && <option value="">—</option>}
                {years.map((year) => (
                  <option key={year}>{year}</option>
                ))}
              </select>
            </label>
          </div>
        </div>
        {notice && <p role="status">{copy[notice]}</p>}
        {error && (
          <p role="alert">
            {copy[error]}{" "}
            <button type="button" onClick={() => setRevision((n) => n + 1)}>
              {copy.reload}
            </button>
          </p>
        )}
        {loading && <p role="status">{copy.loading}</p>}
        {!loading && !error && !data?.selected && (
          <p className="empty">
            {data?.connections.length
              ? copy.selectForSpending
              : copy.noExpenses}
          </p>
        )}
        {!loading &&
          !error &&
          data?.selected &&
          !history.some((row) => row.month === data.month) && (
            <p className="empty">{copy.noSpending}</p>
          )}
        {!loading &&
          !error &&
          data?.selected &&
          (history.length > 0 ||
            investments.length > 0 ||
            invested.length > 0) && (
            <>
              <MonthOverview
                rows={history}
                month={data.month ?? ""}
                locale={locale}
              >
                <InvestmentOverview
                  rows={investments}
                  month={data.month ?? ""}
                  locale={locale}
                />
                <InvestedTotal rows={invested} locale={locale} />
              </MonthOverview>
              <section className="panel" aria-labelledby="monthly-comparison">
                <h2 id="monthly-comparison">{copy.monthlyComparison}</h2>
                <MonthlyComparison
                  rows={history}
                  month={data.month ?? ""}
                  locale={locale}
                  disabled={saving || suggesting}
                  onSelect={(value) => {
                    setPage(1);
                    setMonth(value);
                  }}
                />
              </section>
              {investments.length > 0 && (
                <section
                  className="panel"
                  aria-labelledby="investment-comparison"
                >
                  <h2 id="investment-comparison">
                    {copy.investmentComparison}
                  </h2>
                  <InvestmentComparison
                    rows={investments}
                    month={data.month ?? ""}
                    locale={locale}
                    disabled={saving || suggesting}
                    onSelect={(value) => {
                      setPage(1);
                      setMonth(value);
                    }}
                  />
                </section>
              )}
              <section className="panel" aria-labelledby="categories">
                <h2 id="categories">{copy.categoryComparison}</h2>
                {uncategorized > 0 && (
                  <p>
                    {number.format(uncategorized)} {copy.awaitingCategory}
                  </p>
                )}
                <CategoryComparison
                  rows={history}
                  month={data.month ?? ""}
                  locale={locale}
                />
              </section>
            </>
          )}
        {!loading && !error && data?.selected && (
          <section className="panel" aria-labelledby="reviews">
            <h2 id="reviews">{copy.reviewTitle}</h2>
            {data.reviews.length === 0 ? (
              <p>{copy.noReviews}</p>
            ) : (
              <>
                <p>{copy.reviewHelp}</p>
                <div className="table-wrap">
                  <table>
                    <thead>
                      <tr>
                        <th scope="col">{copy.date}</th>
                        <th scope="col">{copy.transactionDetails}</th>
                        <th scope="col">{copy.amount}</th>
                        <th scope="col">{copy.reviewStatus}</th>
                        <th scope="col">{copy.reviewAction}</th>
                      </tr>
                    </thead>
                    <tbody>
                      {data.reviews.map((entry) => (
                        <tr key={entry.id}>
                          <td>
                            <time dateTime={entry.date}>
                              {formatDate(entry.date, locale)}
                            </time>
                          </td>
                          <TransactionDetailCell
                            entry={entry}
                            locale={locale}
                            connection={
                              combined
                                ? connectionLabels.get(entry.item)
                                : undefined
                            }
                          />
                          <td>
                            {formatMoney(entry.amount, entry.currency, locale)}
                          </td>
                          <td>
                            {entry.decision === "include"
                              ? copy.reviewIncluded
                              : entry.decision === "exclude"
                                ? copy.reviewExcluded
                                : copy.reviewPending}
                          </td>
                          <td>
                            <div
                              className="review-actions"
                              role="group"
                              aria-label={
                                entry.description ||
                                entry.merchant ||
                                entry.operation ||
                                copy.unavailable
                              }
                            >
                              {entry.decision !== "include" && (
                                <button
                                  disabled={saving}
                                  type="button"
                                  onClick={() =>
                                    void save("reviews", entry, {
                                      decision: "include",
                                    })
                                  }
                                >
                                  {copy.includeExpense}
                                </button>
                              )}
                              {entry.decision !== "exclude" && (
                                <button
                                  disabled={saving}
                                  type="button"
                                  onClick={() =>
                                    void save("reviews", entry, {
                                      decision: "exclude",
                                    })
                                  }
                                >
                                  {copy.excludeExpense}
                                </button>
                              )}
                              {entry.decision && (
                                <button
                                  disabled={saving}
                                  type="button"
                                  onClick={() =>
                                    void save("reviews", entry, {
                                      decision: "reset",
                                    })
                                  }
                                >
                                  {copy.resetReview}
                                </button>
                              )}
                            </div>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                {data.reviews.length === 100 && <p>{copy.reviewLimit}</p>}
              </>
            )}
          </section>
        )}
        {!loading && !error && data?.selected && (
          <>
            <section className="panel" aria-labelledby="expenses">
              <h2 id="expenses">{copy.recentExpenses}</h2>
              <p>{copy.matchingExpenses}</p>
              <form
                className="filters"
                role="search"
                onSubmit={(event) => {
                  event.preventDefault();
                  setPage(1);
                  setSearch(searchInput.trim());
                }}
              >
                <input
                  type="search"
                  aria-label={copy.searchExpenses}
                  placeholder={copy.searchExpenses}
                  maxLength={120}
                  value={searchInput}
                  onChange={(event) => setSearchInput(event.target.value)}
                />
                <button type="submit">{copy.searchExpenses}</button>
              </form>
              {(candidates.length > 0 || suggesting) && (
                <button
                  type="button"
                  disabled={saving || suggesting}
                  onClick={() => void requestSuggestions()}
                >
                  {suggesting ? copy.suggesting : copy.suggestCategories}
                </button>
              )}
              {suggestionStatus &&
                (suggestionStatus !== "suggestionsReady" || hasProposals) && (
                  <p role="status">{copy[suggestionStatus]}</p>
                )}
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th scope="col">{copy.date}</th>
                      <th scope="col">{copy.transactionDetails}</th>
                      <th scope="col">{copy.amount}</th>
                      <th scope="col">{copy.category}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.expenses.map((entry) => (
                      <tr key={entry.id}>
                        <td>
                          <time dateTime={entry.date}>
                            {formatDate(entry.date, locale)}
                          </time>
                        </td>
                        <TransactionDetailCell
                          entry={entry}
                          locale={locale}
                          connection={
                            combined
                              ? connectionLabels.get(entry.item)
                              : undefined
                          }
                        />
                        <td>
                          {formatMoney(entry.amount, entry.currency, locale)}
                          <div>
                            <small>
                              {entry.status === "PENDING"
                                ? copy.pendingStatus
                                : copy.postedStatus}
                            </small>
                          </div>
                        </td>
                        <td>
                          <select
                            aria-label={copy.categoryFor(
                              entry.merchant || copy.expense,
                              formatDate(entry.date, locale),
                            )}
                            disabled={
                              saving ||
                              suggesting ||
                              loading ||
                              entry.status === "PENDING"
                            }
                            value={entry.category}
                            onChange={(event) =>
                              void save("rules", entry, {
                                category: event.target.value,
                              })
                            }
                          >
                            {!data.categories.includes(entry.category) && (
                              <option value={entry.category} disabled>
                                {entry.category}
                              </option>
                            )}
                            {data.categories.map((category) => (
                              <option key={category} value={category}>
                                {category}
                              </option>
                            ))}
                          </select>
                          {entry.bank_category &&
                            entry.bank_category !== entry.category && (
                              <div>
                                <small>
                                  {copy.bankCategory} · {entry.bank_category}
                                </small>
                              </div>
                            )}
                          {entry.category === "Uncategorized" &&
                            suggestions[entry.id] && (
                              <div className="suggestion">
                                <p>
                                  {copy.suggested} · {suggestions[entry.id]}
                                </p>
                                <div className="review-actions">
                                  <button
                                    type="button"
                                    disabled={saving}
                                    onClick={() =>
                                      void save("rules", entry, {
                                        category: suggestions[entry.id],
                                      })
                                    }
                                  >
                                    {copy.applySuggestion}
                                  </button>
                                  <button
                                    type="button"
                                    disabled={saving}
                                    onClick={() =>
                                      setSuggestions((current) => ({
                                        ...current,
                                        [entry.id]: "",
                                      }))
                                    }
                                  >
                                    {copy.dismissSuggestion}
                                  </button>
                                </div>
                              </div>
                            )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {data.expenses.length === 0 && <p>{copy.noMatchingExpenses}</p>}
              {(page > 1 || data.has_more_expenses) && (
                <div className="review-actions">
                  <button
                    type="button"
                    disabled={page === 1 || saving || suggesting}
                    onClick={() => setPage((value) => value - 1)}
                  >
                    {copy.previousPage}
                  </button>
                  <span>{number.format(page)}</span>
                  <button
                    type="button"
                    disabled={
                      !data.has_more_expenses ||
                      page >= 1000 ||
                      saving ||
                      suggesting
                    }
                    onClick={() => setPage((value) => value + 1)}
                  >
                    {copy.nextPage}
                  </button>
                </div>
              )}
            </section>
          </>
        )}
      </main>
    </>
  );
}

createRoot(document.getElementById("root")!).render(<App />);
