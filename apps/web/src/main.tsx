import { useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  categoryLabel,
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
type Expense = {
  id: string;
  date: string;
  currency: string;
  amount: string;
  merchant: string;
  category: string;
};
type Spending = {
  connections: Connection[];
  selected: Connection | null;
  month: string | null;
  totals: Total[];
  expenses: Expense[];
  categories: string[];
};

const years = Array.from(
  { length: 2148 - 1970 + 1 },
  (_, index) => 2148 - index,
);

function App() {
  const [preference, setPreference] = useState(readLanguagePreference);
  const locale =
    preference === "device" ? deviceLocale(navigator.languages) : preference;
  const [item, setItem] = useState("");
  const [month, setMonth] = useState("");
  const [data, setData] = useState<Spending>();
  const [revision, setRevision] = useState(0);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<"loadError" | "saveError">();
  const [notice, setNotice] = useState(false);
  const copy = messages[locale];
  const number = new Intl.NumberFormat(locale);
  const [activeYear, activeMonth] = (month || data?.month || "").split("-");

  useEffect(() => {
    document.documentElement.lang = locale;
    document.title = `${copy.title} | ${copy.brand}`;
  }, [locale, copy]);

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
    const request = new AbortController();
    const query = new URLSearchParams();
    if (item) query.set("item", item);
    if (month) query.set("month", month);
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
  }, [item, month, revision]);

  async function classify(transaction: string, category: string) {
    if (!data?.selected) return;
    setSaving(true);
    setError(undefined);
    setNotice(false);
    try {
      const response = await fetch("/api/spending/rules", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ item: data.selected.id, transaction, category }),
        signal: AbortSignal.timeout(5000),
      });
      if (!response.ok) throw new Error();
      setNotice(true);
      setRevision((value) => value + 1);
    } catch {
      setError("saveError");
    } finally {
      setSaving(false);
    }
  }

  const currencies = data?.totals.filter((row) => row.bucket === null) ?? [];
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
      <main className="frame" aria-busy={loading}>
        <div className="intro">
          <h1>{copy.title}</h1>
          <div className="filters">
            <label>
              {copy.connection}
              <select
                value={item || data?.selected?.id || ""}
                onChange={(event) => {
                  setItem(event.target.value);
                  setMonth("");
                  setNotice(false);
                }}
                disabled={saving || !data?.connections.length}
              >
                <option value="">{copy.selectConnection}</option>
                {data?.connections.map((connection, index) => (
                  <option key={connection.id} value={connection.id}>
                    {connection.is_demo
                      ? copy.syntheticDemo
                      : `${copy.connection} ${number.format(index + 1)}`}
                  </option>
                ))}
              </select>
            </label>
            <label>
              {copy.month}
              <select
                value={activeMonth || ""}
                disabled={saving || loading || !data?.selected || !activeYear}
                onChange={(event) =>
                  setMonth(`${activeYear}-${event.target.value}`)
                }
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
                disabled={saving || loading || !data?.selected || !activeMonth}
                onChange={(event) =>
                  setMonth(`${event.target.value}-${activeMonth}`)
                }
              >
                {!activeYear && <option value="">—</option>}
                {years.map((year) => (
                  <option key={year}>{year}</option>
                ))}
              </select>
            </label>
          </div>
        </div>
        {notice && <p role="status">{copy.saved}</p>}
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
        {!loading && !error && data?.selected && !currencies.length && (
          <p className="empty">{copy.noSpending}</p>
        )}
        {!loading && !error && data?.selected && currencies.length > 0 && (
          <>
            <div className="summary">
              {currencies.map((row) => (
                <div key={row.currency}>
                  <span>
                    {copy.netSpending} · {row.currency}
                  </span>
                  <strong>
                    {formatMoney(row.total, row.currency, locale)}
                  </strong>
                  <small>
                    {number.format(Number(row.entries))}{" "}
                    {Number(row.entries) === 1
                      ? copy.postedEntry
                      : copy.postedEntries}
                  </small>
                </div>
              ))}
              <div>
                <span>{categoryLabel("Uncategorized", locale)}</span>
                <strong>{number.format(uncategorized)}</strong>
                <small>{copy.awaitingCategory}</small>
              </div>
            </div>
            <section className="panel" aria-labelledby="categories">
              <h2 id="categories">{copy.spendingByCategory}</h2>
              {currencies.map(({ currency }) => {
                const rows = data.totals
                  .filter((row) => row.currency === currency && row.bucket)
                  .sort((a, b) => Number(b.total) - Number(a.total));
                const max = Math.max(
                  1,
                  ...rows.map((row) => Math.abs(Number(row.total))),
                );
                return (
                  <div className="chart" key={currency}>
                    <h3>{currency}</h3>
                    {rows.map((row) => (
                      <div className="bar" key={row.bucket}>
                        <span>
                          {row.bucket && categoryLabel(row.bucket, locale)}
                        </span>
                        <meter
                          aria-hidden="true"
                          min={0}
                          max={max}
                          value={Math.abs(Number(row.total))}
                        />
                        <span>{formatMoney(row.total, currency, locale)}</span>
                      </div>
                    ))}
                  </div>
                );
              })}
            </section>
            <section className="panel" aria-labelledby="expenses">
              <h2 id="expenses">{copy.recentExpenses}</h2>
              <p>{copy.matchingExpenses}</p>
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th scope="col">{copy.date}</th>
                      <th scope="col">{copy.merchant}</th>
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
                        <td>{entry.merchant || copy.unknownMerchant}</td>
                        <td>
                          {formatMoney(entry.amount, entry.currency, locale)}
                        </td>
                        <td>
                          <select
                            aria-label={copy.categoryFor(
                              entry.merchant || copy.expense,
                              formatDate(entry.date, locale),
                            )}
                            disabled={saving || loading}
                            value={entry.category}
                            onChange={(event) =>
                              void classify(entry.id, event.target.value)
                            }
                          >
                            {data.categories.map((category) => (
                              <option key={category} value={category}>
                                {categoryLabel(category, locale)}
                              </option>
                            ))}
                          </select>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {data.expenses.length === 100 && <p>{copy.recentLimit}</p>}
            </section>
          </>
        )}
      </main>
    </>
  );
}

createRoot(document.getElementById("root")!).render(<App />);
