import { useEffect, useState } from "react";
import { fetchAccountHistory, type AccountHistory } from "./account-history";
import { formatReportedValue, messages, type Locale } from "./locale";

export function AccountHistoryView({
  item,
  choices,
  locale,
}: {
  item: string;
  choices: { id: string; label: string }[];
  locale: Locale;
}) {
  const [account, setAccount] = useState("");
  const copy = messages[locale];

  return (
    <section className="panel" aria-labelledby="account-history">
      <h2 id="account-history">{copy.accountHistory}</h2>
      <div className="filters">
        <label>
          {copy.account}
          <select
            value={account}
            onChange={(event) => setAccount(event.target.value)}
          >
            <option value="">{copy.selectHistoryAccount}</option>
            {choices.map(({ id, label }) => (
              <option key={id} value={id}>
                {label}
              </option>
            ))}
          </select>
        </label>
      </div>
      {account && (
        <HistoryTable
          key={account}
          item={item}
          account={account}
          locale={locale}
        />
      )}
    </section>
  );
}

function HistoryTable({
  item,
  account,
  locale,
}: {
  item: string;
  account: string;
  locale: Locale;
}) {
  const copy = messages[locale];
  const [result, setResult] = useState<AccountHistory | null | "error">();
  const [retry, setRetry] = useState(0);

  useEffect(() => {
    const request = new AbortController();
    const signal = AbortSignal.any([request.signal, AbortSignal.timeout(8000)]);
    void fetchAccountHistory(item, account, signal)
      .then((history) => {
        if (!request.signal.aborted) setResult(history);
      })
      .catch(() => {
        if (!request.signal.aborted) setResult("error");
      });
    return () => request.abort();
  }, [item, account, retry]);

  if (result === undefined) return <p role="status">{copy.loadingHistory}</p>;
  if (result === "error") {
    return (
      <p role="alert">
        {copy.historyError}{" "}
        <button
          type="button"
          onClick={() => {
            setResult(undefined);
            setRetry((value) => value + 1);
          }}
        >
          {copy.reload}
        </button>
      </p>
    );
  }
  if (!result?.observations.length) return <p>{copy.noHistory}</p>;

  const observed = new Intl.DateTimeFormat(locale, {
    dateStyle: "medium",
    timeStyle: "short",
    timeZone: "UTC",
  });
  return (
    <>
      <div className="table-wrap">
        <table aria-labelledby="account-history">
          <thead>
            <tr>
              <th scope="col">{copy.observedAt}</th>
              <th scope="col">{copy.currency}</th>
              <th scope="col">{copy.balance}</th>
            </tr>
          </thead>
          <tbody>
            {result.observations.map((row) => (
              <tr key={row.observed_at}>
                <td>
                  <time dateTime={row.observed_at}>
                    {observed.format(new Date(row.observed_at))}
                  </time>
                </td>
                <td>{row.currency ?? copy.unavailable}</td>
                <td>{formatReportedValue(row.balance, locale)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {result.truncated && <p>{copy.historyLimit}</p>}
    </>
  );
}
