import { useCallback, useEffect, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import { AccountsView } from "./accounts";
import { CategoriesView, categoryPath, type CategoryNode } from "./categories";
import { connectionLabel, visibleConnections } from "./connections";
import { InvestmentsView } from "./investments";
import {
  ExpenseDialog,
  type DialogExpense,
  type RuleScope,
} from "./expense-dialog";
import { CashFlow, MonthPace, ReturnsTile, type DailyRow } from "./insights";
import { ManualExpenses } from "./manual-expenses";
import { SavingsBoxSuggestions } from "./savings-suggestions";
import { Menu, Toast, Help } from "./ui";
import type { HistoryRow, InvestmentRow } from "./spending-history";
import {
  CategoryChart,
  CategoryComparison,
  CategoryMonthsTable,
  InvestmentComparison,
  InvestedEvolution,
  type InvestedGap,
  type InvestedPoint,
  InvestedTotal,
  InvestmentOverview,
  type InvestedRow,
  MonthlyComparison,
  MonthOverview,
} from "./spending-overview";
import {
  InvestmentReturns,
  type InvestmentReturnsData,
} from "./investment-returns";
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

type Connection = {
  id: string;
  is_demo: boolean;
  latest_month: string;
  institution?: string | null;
};
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
  category_rule?:
    "" | "transaction" | "merchant" | "mcc" | "provider" | "manual";
  provider_category_id?: string;
  status?: "POSTED" | "PENDING";
};
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
  invested_history?: InvestedPoint[];
  invested_gaps?: InvestedGap[];
  invested_returns?: InvestmentReturnsData;
  chart_month?: string | null;
  invested?: InvestedRow[];
  daily?: DailyRow[];
  expenses: Expense[];
  has_more_expenses?: boolean;
  reviews: Review[];
  receipts?: (Review & { category?: string })[];
  categories: CategoryNode[];
};

const years = Array.from(
  { length: 2148 - 1970 + 1 },
  (_, index) => 2148 - index,
);

const VIEWS = [
  "overview",
  "spending",
  "pending",
  "investments",
  "accounts",
  "categories",
] as const;
type View = (typeof VIEWS)[number];
// Views built from the spending API (filtered by connection and month).
const DATA_VIEWS: View[] = ["overview", "spending", "pending", "investments"];
const TITLES = {
  overview: "overviewView",
  spending: "title",
  pending: "pendingView",
  investments: "investments",
  accounts: "accounts",
  categories: "categories",
} as const;

function currentView(): View {
  const view = window.location.hash.slice(1);
  return VIEWS.find((value) => value === view) ?? "overview";
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
  const [selected, setSelected] = useState<{
    entry: DialogExpense;
    editable: boolean;
  }>();
  const [filter, setFilter] = useState<CategoryFilter>();
  // A filter picked together with another month, applied once that month loads.
  const nextFilter = useRef<CategoryFilter>(undefined);
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
    document.title = `${copy[TITLES[view]]} | ${copy.brand}`;
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
    if (!DATA_VIEWS.includes(view)) return;
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
    setFilter(nextFilter.current);
    setExpanded(nextFilter.current !== undefined);
    nextFilter.current = undefined;
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
    if (!data?.selected) return false;
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
      setSelected(undefined);
      return true;
    } catch {
      setError(path === "rules" ? "saveError" : "reviewError");
      return false;
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
    data?.connections.map((connection) => [
      connection.id,
      connectionLabel(
        data.connections,
        connection,
        copy.connection,
        copy.syntheticDemo,
      ),
    ]),
  );
  const categories = data?.categories ?? [];
  // Keep showing the last result while a new one loads, so the page does not jump.
  const ready = Boolean(data) && error !== "loadError";
  const dismissToast = useCallback(() => {
    setNotice(undefined);
    setError((current) => (current === "loadError" ? current : undefined));
  }, []);
  const showAll = expanded || Boolean(search) || Boolean(filter);
  const visibleExpenses = showAll
    ? (data?.expenses ?? [])
    : (data?.expenses ?? []).slice(0, RECENT_ROWS);
  const receipts = data?.receipts ?? [];
  const pendingReceipts = receipts.filter((row) => !row.decision);
  const decidedReceipts = receipts.filter((row) => row.decision);
  const pendingReviews = data?.reviews.filter((row) => !row.decision) ?? [];
  const decidedReviews = data?.reviews.filter((row) => row.decision) ?? [];
  const pendingCount = pendingReviews.length + pendingReceipts.length;
  const today = new Date().toLocaleDateString("en-CA");
  const uncategorized =
    data?.totals
      .filter((row) => row.bucket === "")
      .reduce((sum, row) => sum + Number(row.entries), 0) ?? 0;

  function receiptTable(rows: (Review & { category?: string })[]) {
    return (
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th scope="col">{copy.date}</th>
              <th scope="col">{copy.transactionDetails}</th>
              <th scope="col" className="numeric">
                {copy.amount}
              </th>
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
                  compact
                  onOpen={() =>
                    setSelected({
                      entry: { ...entry, amount: `-${entry.amount}` },
                      editable: entry.decision === "include",
                    })
                  }
                  connection={
                    combined ? connectionLabels.get(entry.item) : undefined
                  }
                />
                <td className="numeric">
                  {formatMoney(entry.amount, entry.currency, locale)}
                  {entry.decision === "include" && (
                    <div>
                      <small>
                        {entry.category
                          ? entry.subcategory
                            ? `${entry.category} › ${entry.subcategory}`
                            : entry.category
                          : copy.uncategorized}
                      </small>
                    </div>
                  )}
                </td>
                <td>
                  <div className="review-actions">
                    {entry.decision !== "include" && (
                      <button
                        type="button"
                        disabled={saving}
                        onClick={async () => {
                          // Counted refunds need a subcategory: ask for it right away.
                          if (
                            await save("reviews", entry, {
                              decision: "include",
                            })
                          )
                            setSelected({
                              entry: { ...entry, amount: `-${entry.amount}` },
                              editable: true,
                            });
                        }}
                      >
                        {copy.countAsRefund}
                      </button>
                    )}
                    {entry.decision !== "exclude" && (
                      <button
                        type="button"
                        disabled={saving}
                        onClick={() =>
                          void save("reviews", entry, { decision: "exclude" })
                        }
                      >
                        {copy.notRefund}
                      </button>
                    )}
                    {entry.decision && (
                      <button
                        type="button"
                        disabled={saving}
                        onClick={() =>
                          void save("reviews", entry, { decision: "reset" })
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
                  compact
                  onOpen={() => setSelected({ entry, editable: false })}
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
                        onClick={async () => {
                          // Ask for the category right away; the row leaves the backlog.
                          if (
                            await save("reviews", entry, {
                              decision: "include",
                            })
                          )
                            setSelected({ entry, editable: true });
                        }}
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
        {(
          [
            "overview",
            "spending",
            "pending",
            "investments",
            "accounts",
          ] as const
        ).map((value) => (
          <a
            key={value}
            href={`#${value}`}
            aria-current={view === value ? "page" : undefined}
          >
            {copy[TITLES[value]]}
            {value === "pending" && pendingCount > 0 && (
              <span className="count">{number.format(pendingCount)}</span>
            )}
          </a>
        ))}
        <a
          className="settings-link"
          href="#categories"
          aria-current={view === "categories" ? "page" : undefined}
        >
          <span aria-hidden="true">⚙ </span>
          {copy.categories}
        </a>
      </nav>
      {view === "categories" && <CategoriesView locale={locale} />}
      <Toast
        message={
          notice
            ? copy[notice]
            : error && error !== "loadError"
              ? copy[error]
              : undefined
        }
        tone={notice ? "info" : "error"}
        closeLabel={copy.close}
        onDone={dismissToast}
      />
      <ExpenseDialog
        key={selected?.entry.id}
        entry={selected?.entry}
        editable={selected?.editable ?? false}
        categories={categories}
        locale={locale}
        connection={
          selected && combined
            ? connectionLabels.get(selected.entry.item)
            : undefined
        }
        saving={saving}
        suggestion={selected ? suggestions[selected.entry.id] : undefined}
        onSave={(category, scope) => {
          if (selected) void save("rules", selected.entry, { category, scope });
        }}
        onDismissSuggestion={() => {
          if (!selected) return;
          setSuggestions((current) => ({
            ...current,
            [selected.entry.id]: "",
          }));
        }}
        onClose={() => setSelected(undefined)}
      />
      {view === "accounts" && <AccountsView locale={locale} />}
      <main
        className={loading && data ? "frame refreshing" : "frame"}
        hidden={!DATA_VIEWS.includes(view)}
        aria-busy={loading}
      >
        <div className="intro">
          <h1>{copy[TITLES[view]]}</h1>
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
        {error === "loadError" && (
          <p role="alert">
            {copy[error]}{" "}
            <button type="button" onClick={() => setRevision((n) => n + 1)}>
              {copy.reload}
            </button>
          </p>
        )}
        {loading && !data && <p role="status">{copy.loading}</p>}
        {ready && !data?.selected && (
          <p className="empty">
            {data?.connections.length
              ? copy.selectForSpending
              : copy.noExpenses}
          </p>
        )}
        {ready &&
          data?.selected &&
          (view === "overview" || view === "spending") &&
          !history.some((row) => row.month === data.month) && (
            <p className="empty">{copy.noSpending}</p>
          )}
        {ready && data?.selected && view === "overview" && (
          <>
            <MonthOverview
              rows={history}
              month={data.month ?? ""}
              locale={locale}
            >
              <InvestedTotal rows={invested} locale={locale} />
              {data.invested_returns && (
                <ReturnsTile data={data.invested_returns} locale={locale} />
              )}
            </MonthOverview>
            {pendingCount > 0 && (
              <section
                className="panel pending-summary"
                aria-labelledby="pending-summary"
              >
                <div>
                  <h2 id="pending-summary">{copy.pendingTitle}</h2>
                  <ul>
                    {pendingReviews.length > 0 && (
                      <li>
                        {number.format(pendingReviews.length)}{" "}
                        {copy.pendingDebits}
                      </li>
                    )}
                    {pendingReceipts.length > 0 && (
                      <li>
                        {number.format(pendingReceipts.length)}{" "}
                        {copy.pendingReceipts}
                      </li>
                    )}
                  </ul>
                </div>
                <a className="button-link" href="#pending">
                  {copy.reviewNow}
                </a>
              </section>
            )}
            <div className="chart-grid">
              <section className="panel" aria-labelledby="month-pace">
                <h2 id="month-pace">{copy.paceTitle}</h2>
                <MonthPace
                  rows={data.daily ?? []}
                  month={data.month ?? ""}
                  today={today}
                  locale={locale}
                />
              </section>
              <section className="panel" aria-labelledby="cash-flow">
                <h2 id="cash-flow">{copy.cashFlowTitle}</h2>
                <Help label={copy.howItWorks}>{copy.cashFlowHelp}</Help>
                <CashFlow
                  history={history}
                  investments={investments}
                  month={data.month ?? ""}
                  end={data.chart_month ?? data.month ?? ""}
                  locale={locale}
                  disabled={saving || suggesting}
                  onSelect={(value) => {
                    setPage(1);
                    setMonth(value);
                  }}
                />
              </section>
            </div>
          </>
        )}
        {ready && data?.selected && view === "spending" && (
          <>
            <section className="panel" aria-labelledby="monthly-comparison">
              <h2 id="monthly-comparison">{copy.monthlyComparison}</h2>
              <MonthlyComparison
                rows={history}
                month={data.month ?? ""}
                end={data.chart_month ?? data.month ?? ""}
                locale={locale}
                disabled={saving || suggesting}
                onSelect={(value) => {
                  setPage(1);
                  setMonth(value);
                }}
              />
            </section>
            <section className="panel" aria-labelledby="categories">
              <h2 id="categories">{copy.categoryComparison}</h2>
              {uncategorized > 0 && (
                <p>
                  <button
                    type="button"
                    className="link-button"
                    disabled={saving || suggesting}
                    onClick={() => {
                      setFilter({ category: "" });
                      setPage(1);
                      setExpanded(true);
                      document
                        .getElementById("expenses")
                        ?.scrollIntoView({ behavior: "smooth" });
                    }}
                  >
                    {number.format(uncategorized)} {copy.awaitingCategory}
                  </button>
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
            <section className="panel" aria-labelledby="category-chart">
              <h2 id="category-chart">{copy.categoryChart}</h2>
              <Help label={copy.howItWorks}>{copy.categoryChartHelp}</Help>
              <CategoryChart
                rows={history}
                month={data.month ?? ""}
                end={data.chart_month ?? data.month ?? ""}
                locale={locale}
                disabled={saving || suggesting}
                onSelect={(value) => {
                  setPage(1);
                  setMonth(value);
                }}
              />
            </section>
            <section className="panel" aria-labelledby="category-months">
              <h2 id="category-months">{copy.categoryMonths}</h2>
              <Help label={copy.howItWorks}>{copy.categoryMonthsHelp}</Help>
              <CategoryMonthsTable
                rows={history}
                month={data.month ?? ""}
                end={data.chart_month ?? data.month ?? ""}
                locale={locale}
                disabled={saving || suggesting}
                onSelect={(value, category, subcategory) => {
                  setPage(1);
                  if (value === data.month) {
                    setFilter({ category, subcategory });
                    setExpanded(true);
                  } else {
                    nextFilter.current = { category, subcategory };
                    setMonth(value);
                  }
                  document
                    .getElementById("expenses")
                    ?.scrollIntoView({ behavior: "smooth" });
                }}
              />
            </section>
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
                <table className="expense-table">
                  <thead>
                    <tr>
                      <th scope="col">{copy.date}</th>
                      <th scope="col">{copy.transactionDetails}</th>
                      <th scope="col">{copy.category}</th>
                      <th scope="col" className="numeric">
                        {copy.amount}
                      </th>
                      <th scope="col">
                        <span className="visually-hidden">
                          {copy.reviewAction}
                        </span>
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {visibleExpenses.map((entry) => {
                      // Pending card purchases already count: they are editable too.
                      const open = () => setSelected({ entry, editable: true });
                      return (
                        <tr key={entry.id}>
                          <td>
                            <time dateTime={entry.date}>
                              {formatDate(entry.date, locale)}
                            </time>
                          </td>
                          <TransactionDetailCell
                            entry={entry}
                            locale={locale}
                            compact
                            onOpen={open}
                            connection={
                              combined
                                ? connectionLabels.get(entry.item)
                                : undefined
                            }
                          />
                          <td>
                            <button
                              type="button"
                              className={
                                entry.category
                                  ? "category-chip"
                                  : "category-chip empty"
                              }
                              onClick={open}
                              aria-label={copy.categoryFor(
                                entry.merchant || copy.expense,
                                formatDate(entry.date, locale),
                              )}
                            >
                              {entry.category
                                ? entry.subcategory
                                  ? `${entry.category} › ${entry.subcategory}`
                                  : entry.category
                                : copy.uncategorized}
                            </button>
                            {!entry.category && suggestions[entry.id] && (
                              <div>
                                <small>
                                  {copy.suggested} ·{" "}
                                  {categoryPath(
                                    categories,
                                    suggestions[entry.id],
                                  )}
                                </small>
                              </div>
                            )}
                          </td>
                          <td className="numeric">
                            {formatMoney(entry.amount, entry.currency, locale)}
                            {entry.status === "PENDING" && (
                              <div>
                                <small>{copy.pendingStatus}</small>
                              </div>
                            )}
                          </td>
                          <td>
                            <Menu
                              label={copy.moreActions}
                              items={[
                                { label: copy.expenseDetails, onSelect: open },
                                {
                                  label: copy.changeCategory,
                                  onSelect: open,
                                },
                                {
                                  label: copy.sameMerchant,
                                  disabled: !entry.merchant,
                                  onSelect: () => {
                                    setSearchInput(entry.merchant);
                                    setSearch(entry.merchant);
                                    setFilter(undefined);
                                    setPage(1);
                                  },
                                },
                                {
                                  label: copy.sameCategory,
                                  onSelect: () => {
                                    setFilter({
                                      category: entry.category,
                                      subcategory: entry.subcategory ?? "",
                                    });
                                    setPage(1);
                                  },
                                },
                              ]}
                            />
                          </td>
                        </tr>
                      );
                    })}
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
          </>
        )}
        {view === "pending" && (
          <>
            {ready && data?.selected && (
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
                    <Help label={copy.howItWorks}>{copy.reviewHelp}</Help>
                    {reviewTable(pendingReviews)}
                  </>
                )}
                {decidedReviews.length > 0 && (
                  <details>
                    <summary>
                      {copy.decidedReviews} (
                      {number.format(decidedReviews.length)})
                    </summary>
                    {reviewTable(decidedReviews)}
                  </details>
                )}
                {data.reviews.length === 100 && <p>{copy.reviewLimit}</p>}
              </section>
            )}
            {ready && data?.selected && receipts.length > 0 && (
              <section className="panel" aria-labelledby="receipts">
                <h2 id="receipts">
                  {copy.receiptsTitle}
                  {pendingReceipts.length > 0 &&
                    ` (${number.format(pendingReceipts.length)})`}
                </h2>
                <Help label={copy.howItWorks}>{copy.receiptsHelp}</Help>
                {pendingReceipts.length > 0 && receiptTable(pendingReceipts)}
                {decidedReceipts.length > 0 && (
                  <details open={pendingReceipts.length === 0}>
                    <summary>
                      {copy.decidedReceipts} (
                      {number.format(decidedReceipts.length)})
                    </summary>
                    {receiptTable(decidedReceipts)}
                  </details>
                )}
              </section>
            )}
            {ready && data?.selected && (
              <SavingsBoxSuggestions
                locale={locale}
                revision={revision}
                categories={categories}
                onChange={() => setRevision((value) => value + 1)}
              />
            )}
            {ready && data?.selected && (
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
            )}
          </>
        )}
        {ready && data?.selected && view === "investments" && (
          <>
            <div className="summary">
              <InvestedTotal rows={invested} locale={locale} />
              {data.invested_returns && (
                <ReturnsTile data={data.invested_returns} locale={locale} />
              )}
              <InvestmentOverview
                rows={investments}
                month={data.month ?? ""}
                locale={locale}
              />
            </div>
            {(data.invested_history ?? []).length > 0 && (
              <section className="panel" aria-labelledby="invested-evolution">
                <h2 id="invested-evolution">{copy.investedEvolution}</h2>
                <InvestedEvolution
                  rows={data.invested_history ?? []}
                  gaps={data.invested_gaps ?? []}
                  locale={locale}
                />
              </section>
            )}
            {(data.invested_returns?.rows ?? []).length > 0 && (
              <section className="panel" aria-labelledby="investment-returns">
                <h2 id="investment-returns">{copy.investmentReturns}</h2>
                <InvestmentReturns
                  data={data.invested_returns!}
                  locale={locale}
                />
              </section>
            )}
            {investments.length > 0 && (
              <section
                className="panel"
                aria-labelledby="investment-comparison"
              >
                <h2 id="investment-comparison">{copy.investmentComparison}</h2>
                <InvestmentComparison
                  rows={investments}
                  month={data.month ?? ""}
                  end={data.chart_month ?? data.month ?? ""}
                  locale={locale}
                  disabled={saving || suggesting}
                  onSelect={(value) => {
                    setPage(1);
                    setMonth(value);
                  }}
                />
              </section>
            )}
          </>
        )}
      </main>
      {view === "investments" && <InvestmentsView locale={locale} nested />}
    </>
  );
}

createRoot(document.getElementById("root")!).render(<App />);
