import { useEffect, useState } from "react";
import { formatMoney, messages, type Locale } from "./locale";

type Connection = { id: string; is_demo: boolean };
type Account = {
  id: string;
  type: string | null;
  balance: string | null;
  currency: string | null;
  observed_at: string;
};
type Snapshot = {
  connections: Connection[];
  selected: Connection | null;
  accounts: Account[];
  truncated: boolean;
};

export function AccountsView({ locale }: { locale: Locale }) {
  const [item, setItem] = useState("");
  const [snapshot, setSnapshot] = useState<Snapshot>();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [retry, setRetry] = useState(0);
  const copy = messages[locale];
  const number = new Intl.NumberFormat(locale);
  const balance = new Intl.NumberFormat(locale, { maximumFractionDigits: 12 });
  const observed = new Intl.DateTimeFormat(locale, {
    dateStyle: "medium",
    timeStyle: "short",
    timeZone: "UTC",
  });

  useEffect(() => {
    const request = new AbortController();
    const query = item ? `?${new URLSearchParams({ item })}` : "";
    setError(false);
    setLoading(true);
    void fetch(`/api/accounts${query}`, {
      signal: AbortSignal.any([request.signal, AbortSignal.timeout(8000)]),
    })
      .then(async (response) => {
        if (!response.ok) throw new Error();
        const next = (await response.json()) as Snapshot;
        if (!request.signal.aborted) setSnapshot(next);
      })
      .catch(() => {
        if (!request.signal.aborted) setError(true);
      })
      .finally(() => {
        if (!request.signal.aborted) setLoading(false);
      });
    return () => request.abort();
  }, [item, retry]);

  return (
    <main className="frame" aria-busy={loading}>
      <div className="intro">
        <h1>{copy.accounts}</h1>
        <label>
          {copy.connection}
          <select
            value={item || snapshot?.selected?.id || ""}
            disabled={loading || !snapshot?.connections.length}
            onChange={(event) => setItem(event.target.value)}
          >
            <option value="">{copy.selectConnection}</option>
            {snapshot?.connections.map(({ id, is_demo }, index) => (
              <option value={id} key={id}>
                {is_demo
                  ? copy.syntheticDemo
                  : `${copy.connection} ${number.format(index + 1)}`}
              </option>
            ))}
          </select>
        </label>
      </div>
      {loading && <p role="status">{copy.loadingAccounts}</p>}
      {error && (
        <p role="alert">
          {copy.accountsError}{" "}
          <button type="button" onClick={() => setRetry((value) => value + 1)}>
            {copy.reload}
          </button>
        </p>
      )}
      {!loading && !error && !snapshot?.selected && (
        <p className="empty">
          {snapshot?.connections.length
            ? copy.selectConnection
            : copy.noAccounts}
        </p>
      )}
      {!loading && !error && snapshot?.selected && (
        <section className="panel" aria-labelledby="balances">
          <h2 id="balances">{copy.reportedBalances}</h2>
          <p>{copy.balanceHelp}</p>
          {snapshot.accounts.length === 0 ? (
            <p>{copy.noAccounts}</p>
          ) : (
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th scope="col">{copy.account}</th>
                    <th scope="col">{copy.balance}</th>
                    <th scope="col">{copy.currency}</th>
                    <th scope="col">{copy.observedAt}</th>
                  </tr>
                </thead>
                <tbody>
                  {snapshot.accounts.map((row, index) => (
                    <tr key={row.id}>
                      <th scope="row">
                        {row.type === "BANK"
                          ? copy.bankAccount
                          : row.type === "CREDIT"
                            ? copy.creditCard
                            : copy.account}{" "}
                        {number.format(index + 1)}
                      </th>
                      <td>
                        {row.balance === null
                          ? copy.unavailable
                          : row.currency
                            ? formatMoney(row.balance, row.currency, locale)
                            : balance.format(Number(row.balance))}
                      </td>
                      <td>{row.currency || copy.unavailable}</td>
                      <td>
                        <time dateTime={row.observed_at}>
                          {observed.format(new Date(row.observed_at))}
                        </time>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          {snapshot.truncated && <p>{copy.accountLimit}</p>}
        </section>
      )}
    </main>
  );
}
