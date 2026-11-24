import { useEffect, useState, type FormEvent } from "react";
import { categoryPath, categoryTree, type CategoryNode } from "./categories";
import { formatMoney, messages, type Locale } from "./locale";
import { Dialog, Menu, Help } from "./ui";

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
  savings_box: string;
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
  const [boxes, setBoxes] = useState<{ item: string; name: string }[]>([]);
  const [formItem, setFormItem] = useState("");
  const [recurring, setRecurring] = useState(true);
  // "item|name" of the box that paid the entry, or "".
  const [box, setBox] = useState("");
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
        const result = (await response.json()) as {
          entries: Entry[];
          boxes: { item: string; name: string }[];
        };
        setEntries(result.entries);
        setBoxes(result.boxes);
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
    // A one-off entry is a single date: its month and day.
    const date = value("date");
    const body = {
      item: box ? box.split("|")[0] : value("item"),
      description: value("description"),
      amount: value("amount").replace(",", "."),
      category: value("category") || null,
      day: Number(recurring ? value("day") : date.slice(8)),
      start: recurring ? value("start") : date.slice(0, 7),
      end: recurring ? value("end") || null : date.slice(0, 7),
      cnpj: value("cnpj").replace(/\D/g, ""),
      savings_box: box ? box.slice(box.indexOf("|") + 1) : "",
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

  const oneOff = (entry: Entry) => entry.end === entry.start;
  const day = (entry: Entry) =>
    `${entry.start}-${String(entry.day).padStart(2, "0")}`;
  const period = (entry: Entry) =>
    oneOff(entry)
      ? day(entry)
      : `${entry.start} → ${entry.end ?? copy.noEndMonth} · ${copy.manualDay} ${entry.day}`;

  return (
    <section className="panel" aria-labelledby="manual-expenses">
      <h2 id="manual-expenses">{copy.manualExpenses}</h2>
      <Help label={copy.howItWorks}>{copy.manualExpensesHelp}</Help>
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
                        {entry.savings_box &&
                          ` · ${copy.paidFromSavingsBox}: ${entry.savings_box}`}
                      </small>
                    </div>
                  </td>
                  <td>{formatMoney(entry.amount, entry.currency, locale)}</td>
                  <td>{period(entry)}</td>
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
                            setRecurring(!oneOff(entry));
                            setBox(
                              entry.savings_box
                                ? `${entry.item}|${entry.savings_box}`
                                : "",
                            );
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
          setRecurring(false);
          setBox("");
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
            {copy.paidFromSavingsBox}
            <select
              value={box}
              onChange={(event) => {
                setBox(event.target.value);
                if (event.target.value)
                  setFormItem(event.target.value.split("|")[0]);
              }}
              disabled={busy}
            >
              <option value="">{copy.notFromSavingsBox}</option>
              {boxes.map((row) => (
                <option
                  key={`${row.item}|${row.name}`}
                  value={`${row.item}|${row.name}`}
                >
                  {row.name}
                  {new Set(boxes.map((other) => other.item)).size > 1 &&
                    ` · ${labels.get(row.item) ?? copy.connection}`}
                </option>
              ))}
            </select>
          </label>
          {!box && (
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
          )}
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
          <label className="checkbox">
            <input
              type="checkbox"
              checked={recurring}
              onChange={(event) => setRecurring(event.target.checked)}
              disabled={busy}
            />
            {copy.manualRecurring}
          </label>
          {recurring ? (
            <>
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
                {copy.manualStart}
                <input
                  name="start"
                  type="month"
                  required
                  defaultValue={editing?.start}
                  disabled={busy}
                />
              </label>
              <label>
                {copy.manualEnd}
                <input
                  name="end"
                  type="month"
                  defaultValue={
                    editing && !oneOff(editing) ? (editing.end ?? "") : ""
                  }
                  disabled={busy}
                />
              </label>
            </>
          ) : (
            <label>
              {copy.manualDate}
              <input
                name="date"
                type="date"
                required
                defaultValue={editing && day(editing)}
                disabled={busy}
              />
            </label>
          )}
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
