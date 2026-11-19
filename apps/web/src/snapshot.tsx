import { useEffect, useState, type ReactNode } from "react";
import { messages, type Locale } from "./locale";

type Connection = { id: string; is_demo: boolean };
export type Snapshot = {
  connections: Connection[];
  selected: Connection | null;
  truncated: boolean;
};

export function SnapshotView<T extends Snapshot>({
  locale,
  path,
  title,
  loadingText,
  errorText,
  emptyText,
  children,
}: {
  locale: Locale;
  path: "/api/accounts" | "/api/investments";
  title: string;
  loadingText: string;
  errorText: string;
  emptyText: string;
  children: (snapshot: T) => ReactNode;
}) {
  const [item, setItem] = useState("");
  const [snapshot, setSnapshot] = useState<T>();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [retry, setRetry] = useState(0);
  const copy = messages[locale];
  const number = new Intl.NumberFormat(locale);

  useEffect(() => {
    const request = new AbortController();
    const query = item ? `?${new URLSearchParams({ item })}` : "";
    setError(false);
    setLoading(true);
    void fetch(`${path}${query}`, {
      signal: AbortSignal.any([request.signal, AbortSignal.timeout(8000)]),
    })
      .then(async (response) => {
        if (!response.ok) throw new Error();
        const next = (await response.json()) as T;
        if (!request.signal.aborted) setSnapshot(next);
      })
      .catch(() => {
        if (!request.signal.aborted) setError(true);
      })
      .finally(() => {
        if (!request.signal.aborted) setLoading(false);
      });
    return () => request.abort();
  }, [path, item, retry]);

  return (
    <main className="frame" aria-busy={loading}>
      <div className="intro">
        <h1>{title}</h1>
        <label>
          {copy.connection}
          <select
            value={item || snapshot?.selected?.id || ""}
            disabled={loading || !snapshot?.connections.length}
            onChange={(event) => {
              setLoading(true);
              setItem(event.target.value);
            }}
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
      {loading && <p role="status">{loadingText}</p>}
      {error && !loading && (
        <p role="alert">
          {errorText}{" "}
          <button type="button" onClick={() => setRetry((value) => value + 1)}>
            {copy.reload}
          </button>
        </p>
      )}
      {!loading &&
        !error &&
        (snapshot?.selected ? (
          children(snapshot)
        ) : (
          <p className="empty">
            {snapshot?.connections.length ? copy.selectConnection : emptyText}
          </p>
        ))}
    </main>
  );
}
