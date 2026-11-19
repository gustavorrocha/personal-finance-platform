import { useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import { AccountsView } from "./accounts";
import {
  CategoriesView,
  categoryPath,
  categoryTree,
  type CategoryNode,
} from "./categories";
import { visibleConnections } from "./connections";
import { InvestmentsView } from "./investments";
import { ManualExpenses } from "./manual-expenses";
import type { HistoryRow, InvestmentRow } from "./spending-history";
import {
  CategoryComparison,
  InvestmentComparison,
  InvestedEvolution,
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
  subcategory?: string;
  category_id?: string;
  category_rule?: "" | "merchant" | "mcc" | "provider" | "manual";
  provider_category_id?: string;
  status?: "POSTED" | "PENDING";
};
type RuleScope = "merchant" | "mcc" | "provider";
type CategoryFilter = { category: string; subcategory?: string };
const RECENT_ROWS = 10;
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
  invested_history?: { month: string; currency: string; total: string }[];
  invested?: InvestedRow[];
  expenses: Expense[];
  has_more_expenses?: boolean;
  reviews: Review[];
  categories: CategoryNode[];
};

const years = Array.from(
  { length: 2148 - 1970 + 1 },
  (_, index) => 2148 - index,
);

function currentView(): "accounts" | "investments" | "categories" | "spending" {
  const view = window.location.hash.slice(1);
  return view === "accounts" || view === "investments" || view === "categories"
    ? view
    : "spending";
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
  const [scopes, setScopes] = useState<Record<string, RuleScope>>({});
  const [filter, setFilter] = useState<CategoryFilter>();
  const [expanded, setExpanded] = useState(false);
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
    setScopes({});
    const request = new AbortController();
    const query = new URLSearchParams();
    if (item) query.set("item", item);
    if (month) query.set("month", month);
    if (search) query.set("search", search);
    if (page > 1) query.set("page", String(page));
    if (filter) {
      query.set("category", filter.category);
      if (filter.subcategory !== undefined)
        query.set("subcategory", filter.subcategory);
    }
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
  }, [item, month, search, page, revision, view, filter]);

  useEffect(() => {
    setFilter(undefined);
    setExpanded(false);
    setAttempted([]);
    setSuggestions({});
    setSuggestionStatus(undefined);
  }, [item, month]);

  const eligible = (data?.expenses ?? []).filter(
    (row) =>
      row.status !== "PENDING" &&
      !row.category &&
      row.merchant &&
      !attempted.includes(row.id),
  );
  const candidates = eligible
    .filter((row) => row.item === eligible[0]?.item)
    .slice(0, 4);
  const hasProposals = data?.expenses.some(
    (row) => !row.category && suggestions[row.id],
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
      | { category: string | null; scope: RuleScope }
      | { decision: "include" | "exclude" | "reset" },
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
  const categories = data?.categories ?? [];
  const showAll = expanded || Boolean(search) || Boolean(filter);
  const visibleExpenses = showAll
    ? (data?.expenses ?? [])
    : (data?.expenses ?? []).slice(0, RECENT_ROWS);
  const pendingReviews = data?.reviews.filter((row) => !row.decision) ?? [];
  const decidedReviews = data?.reviews.filter((row) => row.decision) ?? [];
  const tree = categoryTree(categories);
  const uncategorized =
    data?.totals
      .filter((row) => row.bucket === "")
      .reduce((sum, row) => sum + Number(row.entries), 0) ?? 0;

  function reviewTable(rows: Review[]) {
    return (
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
            {rows.map((entry) => (
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
                    combined ? connectionLabels.get(entry.item) : undefined
                  }
                />
                <td>{formatMoney(entry.amount, entry.currency, locale)}</td>
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
    );
  }

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
        <a
          href="#categories"
          aria-current={view === "categories" ? "page" : undefined}
        >
          {copy.categories}
        </a>
      </nav>
      {view === "categories" && <CategoriesView locale={locale} />}
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
        {!loading && !error && data?.selected && (
          <section className="panel" aria-labelledby="reviews">
            <h2 id="reviews">
              {copy.reviewTitle}
              {pendingReviews.length > 0 &&
                ` (${number.format(pendingReviews.length)})`}
            </h2>
            {pendingReviews.length === 0 ? (
              <p>{copy.noReviews}</p>
            ) : (
              <>
                <p>{copy.reviewHelp}</p>
                {reviewTable(pendingReviews)}
              </>
            )}
            {decidedReviews.length > 0 && (
              <details>
                <summary>
                  {copy.decidedReviews} ({number.format(decidedReviews.length)})
                </summary>
                {reviewTable(decidedReviews)}
              </details>
            )}
            {data.reviews.length === 100 && <p>{copy.reviewLimit}</p>}
          </section>
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
              {(data.invested_history ?? []).length > 0 && (
                <section className="panel" aria-labelledby="invested-evolution">
                  <h2 id="invested-evolution">{copy.investedEvolution}</h2>
                  <InvestedEvolution
                    rows={data.invested_history ?? []}
                    locale={locale}
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
                  disabled={saving || suggesting}
                  onSelect={(category, subcategory) => {
                    setFilter({ category, subcategory });
                    setPage(1);
                    setExpanded(true);
                    document
                      .getElementById("expenses")
                      ?.scrollIntoView({ behavior: "smooth" });
                  }}
                />
              </section>
            </>
          )}
        {!loading && !error && data?.selected && (
          <>
            <section className="panel" aria-labelledby="expenses">
              <h2 id="expenses">{copy.recentExpenses}</h2>
              <p>{copy.matchingExpenses}</p>
              {filter && (
                <p className="filter-chip" role="status">
                  {copy.showingCategory}{" "}
                  <strong>
                    {filter.category || copy.uncategorized}
                    {filter.subcategory !== undefined &&
                      ` › ${filter.subcategory || copy.noSubcategory}`}
                  </strong>{" "}
                  <button
                    type="button"
                    onClick={() => {
                      setFilter(undefined);
                      setPage(1);
                    }}
                  >
                    {copy.clearFilter}
                  </button>
                </p>
              )}
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
                    {visibleExpenses.map((entry) => (
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
                            value={entry.category_id ?? ""}
                            onChange={(event) =>
                              void save("rules", entry, {
                                category: event.target.value || null,
                                scope: scopes[entry.id] ?? "merchant",
                              })
                            }
                          >
                            <option value="">{copy.automaticCategory}</option>
                            {tree.map((top) => (
                              <optgroup key={top.id} label={top.name}>
                                <option value={top.id}>
                                  {top.name} · {copy.wholeCategory}
                                </option>
                                {top.children.map((child) => (
                                  <option key={child.id} value={child.id}>
                                    {child.name}
                                  </option>
                                ))}
                              </optgroup>
                            ))}
                          </select>
                          {entry.status !== "PENDING" && (
                            <select
                              className="rule-scope"
                              aria-label={copy.ruleScope}
                              value={scopes[entry.id] ?? "merchant"}
                              disabled={saving || suggesting || loading}
                              onChange={(event) =>
                                setScopes((current) => ({
                                  ...current,
                                  [entry.id]: event.target.value as RuleScope,
                                }))
                              }
                            >
                              <option value="merchant">
                                {copy.scopeMerchant}
                              </option>
                              {entry.mcc != null && (
                                <option value="mcc">
                                  {copy.scopeMcc} {entry.mcc}
                                </option>
                              )}
                              {entry.provider_category_id && (
                                <option value="provider">
                                  {copy.scopeProvider}:{" "}
                                  {entry.bank_category ||
                                    entry.provider_category_id}
                                </option>
                              )}
                            </select>
                          )}
                          <div>
                            <small>
                              {entry.category_rule
                                ? copy[`rule_${entry.category_rule}`]
                                : copy.uncategorized}
                              {entry.bank_category &&
                                ` · ${copy.bankCategory}: ${entry.bank_category}`}
                            </small>
                          </div>
                          {!entry.category && suggestions[entry.id] && (
                            <div className="suggestion">
                              <p>
                                {copy.suggested} ·{" "}
                                {categoryPath(
                                  categories,
                                  suggestions[entry.id],
                                )}
                              </p>
                              <div className="review-actions">
                                <button
                                  type="button"
                                  disabled={saving}
                                  onClick={() =>
                                    void save("rules", entry, {
                                      category: suggestions[entry.id],
                                      scope: "merchant",
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
              {!showAll && data.expenses.length > RECENT_ROWS && (
                <button
                  type="button"
                  className="show-more"
                  onClick={() => setExpanded(true)}
                >
                  {copy.showMore}
                </button>
              )}
              {showAll && (page > 1 || data.has_more_expenses) && (
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
            <ManualExpenses
              locale={locale}
              categories={categories}
              connections={(data.connections ?? [])
                .filter((connection) => !connection.is_demo)
                .map((connection) => ({
                  id: connection.id,
                  label: connectionLabels.get(connection.id) ?? connection.id,
                }))}
              onChange={() => setRevision((value) => value + 1)}
            />
          </>
        )}
      </main>
    </>
  );
}

createRoot(document.getElementById("root")!).render(<App />);
