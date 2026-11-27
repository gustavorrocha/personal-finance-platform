import { Fragment, useCallback, useEffect, useRef, useState } from "react";
import { messages, type Locale } from "./locale";

type Job = null | {
  id: string;
  requested_at: string;
  state: "queued" | "running" | "succeeded" | "failed";
  finished_at?: string;
  detail?: {
    failed?: number | boolean;
    market?: string;
    error?: string;
    captures?: number;
    edits?: number;
  };
};

type SyncStatus = {
  agent: boolean;
  request: Job;
  export: Job;
  import: Job;
  connections: { item: string; institution: string; synced_at: string }[];
};

const running = (job: Job | undefined) =>
  job?.state === "queued" || job?.state === "running";

function ago(iso: string, locale: Locale): string {
  const seconds = (Date.parse(iso) - Date.now()) / 1000;
  const format = new Intl.RelativeTimeFormat(locale, { numeric: "auto" });
  for (const [unit, size] of [
    ["day", 86400],
    ["hour", 3600],
    ["minute", 60],
  ] as const) {
    if (Math.abs(seconds) >= size)
      return format.format(Math.round(seconds / size), unit);
  }
  return format.format(0, "minute");
}

/** Header control: data updates, plus backup export and import, all run by the host agent. */
export function SyncControl({
  locale,
  onUpdated,
}: {
  locale: Locale;
  onUpdated: () => void;
}) {
  const copy = messages[locale];
  const [status, setStatus] = useState<SyncStatus>();
  const [unavailable, setUnavailable] = useState(false);
  const [file, setFile] = useState<File>();
  const state = status?.request?.state;
  const busy = running(status?.request);
  const anyBusy = busy || running(status?.export) || running(status?.import);

  const load = useCallback(async () => {
    try {
      const response = await fetch("/api/sync");
      if (!response.ok) throw new Error();
      setStatus((await response.json()) as SyncStatus);
      setUnavailable(false);
    } catch {
      setUnavailable(true);
    }
  }, []);

  useEffect(() => {
    void load();
    const timer = setInterval(() => void load(), anyBusy ? 3000 : 60000);
    return () => clearInterval(timer);
  }, [load, anyBusy]);

  // Reload the dashboard's data once an update or an import ends.
  const changing = busy || running(status?.import);
  const wasChanging = useRef(false);
  useEffect(() => {
    if (wasChanging.current && !changing) onUpdated();
    wasChanging.current = changing;
  }, [changing, onUpdated]);

  async function send(path: string, body: BodyInit, type: string) {
    try {
      const response = await fetch(path, {
        method: "POST",
        headers: { "Content-Type": type },
        body,
      });
      if (response.ok) setStatus((await response.json()) as SyncStatus);
      else await load();
    } catch {
      setUnavailable(true);
    }
  }

  if (!status) return null;
  const latest = status.connections
    .map((row) => row.synced_at)
    .sort()
    .at(-1);
  const detail = status.request?.detail;
  const problem =
    state !== "failed"
      ? detail?.market === "failed"
        ? copy.syncMarketFailed
        : undefined
      : detail?.error === "credentials"
        ? copy.syncCredentials
        : detail?.error === "busy"
          ? copy.syncBusy
          : detail?.failed
            ? copy.syncPartial
            : copy.syncFailed;
  const when = new Intl.DateTimeFormat(locale, {
    dateStyle: "short",
    timeStyle: "short",
  });
  const exported = status.export;
  const imported = status.import;
  return (
    <details className="sync-control">
      <summary>
        <span
          className={`sync-dot ${anyBusy ? "busy" : problem || !status.agent ? "warn" : "ok"}`}
          aria-hidden="true"
        />
        {busy
          ? state === "queued"
            ? copy.syncQueued
            : copy.syncRunning
          : latest
            ? copy.syncedAgo.replace("{time}", ago(latest, locale))
            : copy.neverSynced}
      </summary>
      <div className="sync-panel" role="status">
        <strong>{copy.syncTitle}</strong>
        {!status.agent && <p className="sync-warning">{copy.syncAgentOff}</p>}
        {problem && <p className="sync-warning">{problem}</p>}
        {unavailable && <p className="sync-warning">{copy.syncUnavailable}</p>}
        {status.connections.length > 0 && (
          <dl className="breakdown">
            {status.connections.map((row) => (
              <Fragment key={row.item}>
                <dt>{row.institution || copy.unavailable}</dt>
                <dd>{when.format(new Date(row.synced_at))}</dd>
              </Fragment>
            ))}
          </dl>
        )}
        <button
          type="button"
          disabled={anyBusy || !status.agent}
          onClick={() => void send("/api/sync", "{}", "application/json")}
        >
          {busy ? copy.syncRunning : copy.syncNow}
        </button>
        <small>{copy.syncHelp}</small>

        <strong className="sync-section">{copy.backupTitle}</strong>
        <small>{copy.backupHelp}</small>
        <button
          type="button"
          disabled={anyBusy || !status.agent}
          onClick={() =>
            void send("/api/backup/export", "{}", "application/json")
          }
        >
          {running(exported) ? copy.backupPreparing : copy.backupExport}
        </button>
        {exported?.state === "succeeded" && exported.finished_at && (
          <a href="/api/backup/export" download>
            {copy.backupDownload.replace(
              "{time}",
              when.format(new Date(exported.finished_at)),
            )}
          </a>
        )}
        {exported?.state === "failed" && (
          <p className="sync-warning">{copy.backupFailed}</p>
        )}
        {file ? (
          <div className="sync-confirm">
            <span>{copy.backupImportConfirm.replace("{file}", file.name)}</span>
            <small>{copy.backupImportHelp}</small>
            <div>
              <button
                type="button"
                onClick={() => {
                  void send("/api/backup/import", file, "application/zip");
                  setFile(undefined);
                }}
              >
                {copy.backupImport}
              </button>
              <button type="button" onClick={() => setFile(undefined)}>
                {copy.cancel}
              </button>
            </div>
          </div>
        ) : (
          <label className="sync-file" aria-disabled={anyBusy || !status.agent}>
            {running(imported) ? copy.backupImporting : copy.backupImport}
            <input
              type="file"
              accept=".zip,application/zip"
              disabled={anyBusy || !status.agent}
              onChange={(event) => {
                setFile(event.target.files?.[0]);
                event.target.value = "";
              }}
            />
          </label>
        )}
        {imported?.state === "succeeded" && (
          <small>
            {copy.backupImported
              .replace("{captures}", String(imported.detail?.captures ?? 0))
              .replace("{edits}", String(imported.detail?.edits ?? 0))}
          </small>
        )}
        {imported?.state === "failed" && (
          <p className="sync-warning">
            {imported.detail?.error === "invalid"
              ? copy.backupInvalid
              : copy.backupFailed}
          </p>
        )}
      </div>
    </details>
  );
}
