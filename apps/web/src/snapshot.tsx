import { useEffect, useState, type ReactNode } from "react";
import { connectionLabel, visibleConnections } from "./connections";
import { messages, type Locale } from "./locale";

type Connection = { id: string; is_demo: boolean; institution?: string | null };
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
  nested = false,
  children,
}: {
  locale: Locale;
  path: "/api/accounts" | "/api/investments";
  title: string;
  loadingText: string;
  errorText: string;
  emptyText: string;
  /** Part of another page: a section with a second-level heading. */
  nested?: boolean;
  children: (snapshot: T) => ReactNode;
}) {
  const [item, setItem] = useState("");
  const [snapshot, setSnapshot] = useState<T>();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [retry, setRetry] = useState(0);
  const copy = messages[locale];
  const Root = nested ? "section" : "main";
  const Heading = nested ? "h2" : "h1";
  const connections = visibleConnections(snapshot?.connections ?? []);
  const selected = connections.some(({ id }) => id === snapshot?.selected?.id)
    ? snapshot?.selected
    : null;

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
    <Root className="frame" aria-busy={loading}>
      <div className="intro">
        <Heading>{title}</Heading>
        <label>
          {copy.connection}
          <select
            value={selected?.id ?? ""}
            disabled={loading || !connections.length}
            onChange={(event) => {
              setLoading(true);
              setItem(event.target.value);
            }}
          >
            <option value="">{copy.selectConnection}</option>
            {connections.map((connection) => (
              <option value={connection.id} key={connection.id}>
                {connectionLabel(
                  snapshot?.connections ?? [],
                  connection,
                  copy.connection,
                  copy.syntheticDemo,
                )}
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
        (snapshot && selected ? (
          children(snapshot)
        ) : (
          <p className="empty">
            {connections.length ? copy.selectConnection : emptyText}
          </p>
        ))}
    </Root>
  );
}
