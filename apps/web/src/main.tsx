import { useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import "./style.css";

type Connection = { id: string; label: string; latest_month: string };
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

function money(amount: string, currency: string): string {
  return new Intl.NumberFormat("en", { style: "currency", currency }).format(
    Number(amount),
  );
}

function App() {
  const [item, setItem] = useState("");
  const [month, setMonth] = useState("");
  const [data, setData] = useState<Spending>();
  const [revision, setRevision] = useState(0);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  useEffect(() => {
    const request = new AbortController();
    const query = new URLSearchParams();
    if (item) query.set("item", item);
    if (month) query.set("month", month);
    setLoading(true);
    setError("");
    void fetch(`/api/spending?${query}`, { signal: request.signal })
      .then(async (response) => {
        if (!response.ok) throw new Error();
        const spending = (await response.json()) as Spending;
        if (!request.signal.aborted) setData(spending);
      })
      .catch(() => {
        if (!request.signal.aborted) setError("Spending could not be loaded.");
      })
      .finally(() => {
        if (!request.signal.aborted) setLoading(false);
      });
    return () => request.abort();
  }, [item, month, revision]);

  async function classify(transaction: string, category: string) {
    if (!data?.selected) return;
    setSaving(true);
    setError("");
    setNotice("");
    try {
      const response = await fetch("/api/spending/rules", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ item: data.selected.id, transaction, category }),
        signal: AbortSignal.timeout(5000),
      });
      if (!response.ok) throw new Error();
      setNotice("Category rule saved.");
      setRevision((value) => value + 1);
    } catch {
      setError("The category could not be saved.");
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
          <span className="brand">Personal Finance</span>
          <span className="private">Local workspace</span>
        </div>
      </header>
      <main className="frame" aria-busy={loading}>
        <div className="intro">
          <h1>Monthly spending</h1>
          <div className="filters">
            <label>
              Connection
              <select
                value={item || data?.selected?.id || ""}
                onChange={(event) => {
                  setItem(event.target.value);
                  setMonth("");
                  setNotice("");
                }}
                disabled={saving || !data?.connections.length}
              >
                <option value="">Select a connection</option>
                {data?.connections.map((connection) => (
                  <option key={connection.id} value={connection.id}>
                    {connection.label}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Month
              <input
                type="month"
                min="1970-01"
                max="2148-12"
                disabled={saving || !data?.selected}
                value={month || data?.month || ""}
                onChange={(event) => setMonth(event.target.value)}
              />
            </label>
          </div>
        </div>
        {notice && <p role="status">{notice}</p>}
        {error && (
          <p role="alert">
            {error}{" "}
            <button type="button" onClick={() => setRevision((n) => n + 1)}>
              Reload
            </button>
          </p>
        )}
        {loading && <p role="status">Loading expenses…</p>}
        {!loading && !error && !data?.selected && (
          <p className="empty">
            {data?.connections.length
              ? "Select a connection to view its spending."
              : "No expenses are available. Load the synthetic demo or replay a connection."}
          </p>
        )}
        {!loading && !error && data?.selected && !currencies.length && (
          <p className="empty">No posted spending for this month.</p>
        )}
        {!loading && !error && data?.selected && currencies.length > 0 && (
          <>
            <div className="summary">
              {currencies.map((row) => (
                <div key={row.currency}>
                  <span>Net spending · {row.currency}</span>
                  <strong>{money(row.total, row.currency)}</strong>
                  <small>{row.entries} posted entries</small>
                </div>
              ))}
              <div>
                <span>Uncategorized</span>
                <strong>{uncategorized}</strong>
                <small>Posted entries awaiting a category</small>
              </div>
            </div>
            <section className="panel" aria-labelledby="categories">
              <h2 id="categories">Spending by category</h2>
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
                        <span>{row.bucket}</span>
                        <meter
                          aria-hidden="true"
                          min={0}
                          max={max}
                          value={Math.abs(Number(row.total))}
                        />
                        <span>{money(row.total, currency)}</span>
                      </div>
                    ))}
                  </div>
                );
              })}
            </section>
            <section className="panel" aria-labelledby="expenses">
              <h2 id="expenses">Recent expenses</h2>
              <p>
                A category change applies to matching expenses in this
                connection.
              </p>
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th scope="col">Date</th>
                      <th scope="col">Merchant</th>
                      <th scope="col">Amount</th>
                      <th scope="col">Category</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.expenses.map((entry) => (
                      <tr key={entry.id}>
                        <td>
                          <time dateTime={entry.date}>{entry.date}</time>
                        </td>
                        <td>{entry.merchant || "Unknown merchant"}</td>
                        <td>{money(entry.amount, entry.currency)}</td>
                        <td>
                          <select
                            aria-label={`Category for ${entry.merchant || "expense"} on ${entry.date}`}
                            disabled={saving || loading}
                            value={entry.category}
                            onChange={(event) =>
                              void classify(entry.id, event.target.value)
                            }
                          >
                            {data.categories.map((category) => (
                              <option key={category}>{category}</option>
                            ))}
                          </select>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {data.expenses.length === 100 && (
                <p>Showing the most recent 100 entries.</p>
              )}
            </section>
          </>
        )}
      </main>
    </>
  );
}

createRoot(document.getElementById("root")!).render(<App />);
