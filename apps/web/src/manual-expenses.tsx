import { useEffect, useState, type FormEvent } from "react";
import { categoryPath, categoryTree, type CategoryNode } from "./categories";
import { formatMoney, messages, type Locale } from "./locale";
import { Dialog, Menu } from "./ui";

type Entry = {
  id: string;
  item: string;
  description: string;
  amount: string;
  currency: string;
  category: string | null;
  day: number;
  start: string;
  end: string | null;
  cnpj: string;
};

async function send(
  method: "POST" | "PUT" | "DELETE",
  path: string,
  body?: object,
) {
  const response = await fetch(`/api/spending/manual${path}`, {
    method,
    headers: { "Content-Type": "application/json" },
    body: body && JSON.stringify(body),
    signal: AbortSignal.timeout(5000),
  });
  if (!response.ok) throw new Error();
}

/** Expenses the provider does not report, such as rent paid from a savings box. */
export function ManualExpenses({
  locale,
  connections,
  categories,
  onChange,
}: {
  locale: Locale;
  connections: { id: string; label: string }[];
  categories: CategoryNode[];
  onChange: () => void;
}) {
  const copy = messages[locale];
  const [entries, setEntries] = useState<Entry[]>([]);
  const [editing, setEditing] = useState<Entry>();
  const [formOpen, setFormOpen] = useState(false);
  const [formItem, setFormItem] = useState("");
  const [revision, setRevision] = useState(0);
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState<"manualSaved" | "manualError">();
  const tree = categoryTree(categories);
  const labels = new Map(connections.map((row) => [row.id, row.label]));

  useEffect(() => {
    const request = new AbortController();
    void fetch("/api/spending/manual", { signal: request.signal })
      .then(async (response) => {
        if (!response.ok) throw new Error();
        setEntries(((await response.json()) as { entries: Entry[] }).entries);
      })
      .catch(() => {
        if (!request.signal.aborted) setStatus("manualError");
      });
    return () => request.abort();
  }, [revision]);

  async function change(action: () => Promise<void>) {
    setBusy(true);
    setStatus(undefined);
    try {
      await action();
      setStatus("manualSaved");
      setEditing(undefined);
      setFormOpen(false);
      setRevision((value) => value + 1);
      onChange();
    } catch {
      setStatus("manualError");
    } finally {
      setBusy(false);
    }
  }

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const value = (name: string) => String(form.get(name) ?? "").trim();
    const recurring = form.get("recurring") === "on";
    const body = {
      item: value("item"),
      description: value("description"),
      amount: value("amount").replace(",", "."),
      category: value("category") || null,
      day: Number(value("day")),
      start: value("start"),
      end: recurring ? value("end") || null : value("start"),
      cnpj: value("cnpj").replace(/\D/g, ""),
    };
    const target = event.currentTarget;
    void change(async () => {
      await (editing
        ? send("PUT", `/${editing.id}`, body)
        : send("POST", "", body));
      target.reset();
    });
  }

  function archive(entry: Entry) {
    if (
      !window.confirm(
        copy.archiveManualConfirm.replace("{name}", entry.description),
      )
    )
      return;
    void change(() => send("DELETE", `/${entry.id}`));
  }

  const period = (entry: Entry) =>
    entry.end === entry.start
      ? entry.start
      : `${entry.start} → ${entry.end ?? copy.noEndMonth}`;

  return (
    <section className="panel" aria-labelledby="manual-expenses">
      <h2 id="manual-expenses">{copy.manualExpenses}</h2>
      <p>{copy.manualExpensesHelp}</p>
      {status && <p role="status">{copy[status]}</p>}
      {entries.length > 0 && (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th scope="col">{copy.manualDescription}</th>
                <th scope="col">{copy.amount}</th>
                <th scope="col">{copy.manualPeriod}</th>
                <th scope="col">{copy.category}</th>
                <th scope="col">{copy.reviewAction}</th>
              </tr>
            </thead>
            <tbody>
              {entries.map((entry) => (
                <tr key={entry.id}>
                  <td>
                    {entry.description}
                    <div>
                      <small>
                        {labels.get(entry.item) ?? copy.connection}
                        {entry.cnpj && ` · ${copy.cnpj} ${entry.cnpj}`}
                      </small>
                    </div>
                  </td>
                  <td>{formatMoney(entry.amount, entry.currency, locale)}</td>
                  <td>
                    {period(entry)} · {copy.manualDay} {entry.day}
                  </td>
                  <td>
                    {entry.category
                      ? categoryPath(categories, entry.category)
                      : copy.uncategorized}
                  </td>
                  <td>
                    <Menu
                      label={copy.moreActions}
                      items={[
                        {
                          label: copy.editManual,
                          disabled: busy,
                          onSelect: () => {
                            setEditing(entry);
                            setFormItem("");
                            setFormOpen(true);
                          },
                        },
                        {
                          label: copy.archiveCategory,
                          disabled: busy,
                          onSelect: () => archive(entry),
                        },
                      ]}
                    />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <button
        type="button"
        disabled={!connections.length}
        onClick={() => {
          setEditing(undefined);
          setFormItem("");
          setFormOpen(true);
        }}
      >
        {copy.addManual}
      </button>
      <Dialog
        open={formOpen}
        title={editing ? copy.editManual : copy.addManual}
        closeLabel={copy.close}
        onClose={() => {
          setEditing(undefined);
          setFormOpen(false);
        }}
      >
        <form
          className="manual-form"
          key={editing?.id ?? "new"}
          onSubmit={submit}
          aria-label={editing ? copy.editManual : copy.addManual}
        >
          <label>
            {copy.manualDescription}
            <input
              name="description"
              required
              maxLength={80}
              defaultValue={editing?.description}
              disabled={busy}
            />
          </label>
          <label>
            {copy.amount}
            <input
              name="amount"
              required
              inputMode="decimal"
              pattern="\d+([.,]\d{1,2})?"
              defaultValue={editing?.amount.replace(/(\.\d\d)\d*$/, "$1")}
              disabled={busy}
            />
          </label>
          <label>
            {copy.manualDay}
            <input
              name="day"
              type="number"
              min={1}
              max={31}
              required
              defaultValue={editing?.day ?? 5}
              disabled={busy}
            />
          </label>
          <label>
            {copy.connection}
            <select
              name="item"
              required
              value={formItem || editing?.item || connections[0]?.id || ""}
              onChange={(event) => setFormItem(event.target.value)}
              disabled={busy}
            >
              {connections.map((connection) => (
                <option key={connection.id} value={connection.id}>
                  {connection.label}
                </option>
              ))}
            </select>
          </label>
          <label>
            {copy.category}
            <select
              name="category"
              defaultValue={editing?.category ?? ""}
              disabled={busy}
            >
              <option value="">{copy.uncategorized}</option>
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
          </label>
          <label>
            {copy.manualStart}
            <input
              name="start"
              type="month"
              required
              defaultValue={editing?.start}
              disabled={busy}
            />
          </label>
          <label className="checkbox">
            <input
              name="recurring"
              type="checkbox"
              defaultChecked={editing ? editing.end !== editing.start : true}
              disabled={busy}
            />
            {copy.manualRecurring}
          </label>
          <label>
            {copy.manualEnd}
            <input
              name="end"
              type="month"
              defaultValue={
                editing?.end === editing?.start ? "" : (editing?.end ?? "")
              }
              disabled={busy}
            />
          </label>
          <label>
            {copy.manualCnpj}
            <input
              name="cnpj"
              inputMode="numeric"
              maxLength={18}
              pattern="[\d./-]*"
              defaultValue={editing?.cnpj}
              disabled={busy}
            />
          </label>
          <div className="review-actions">
            <button type="submit" disabled={busy || !connections.length}>
              {editing ? copy.saveCategory : copy.addManual}
            </button>
            {editing && (
              <button
                type="button"
                disabled={busy}
                onClick={() => setEditing(undefined)}
              >
                {copy.cancelEdit}
              </button>
            )}
          </div>
        </form>
      </Dialog>
    </section>
  );
}
