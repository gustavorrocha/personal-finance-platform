import { useEffect, useState, type FormEvent } from "react";
import { categoryTree, type CategoryNode } from "./categories";
import { formatDate, formatMoney, messages, type Locale } from "./locale";
import { Dialog } from "./ui";

type Suggestion = {
  kind: "observed" | "estimated";
  window: [string, string] | null;
  month: string;
  date: string;
  day: number;
  cnpj: string;
  payee: string;
  item: string;
  category_id: string;
  category: string;
  amount: number;
  low: number;
  high: number;
  box: string;
};
type Gap = {
  item: string;
  box: string;
  amount: number;
  observed: number;
  suggested: number;
  observed_since: string | null;
};
type Result = { daily_rate: number; gaps: Gap[]; suggestions: Suggestion[] };

async function post(path: string, body: object) {
  const response = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    signal: AbortSignal.timeout(5000),
  });
  if (!response.ok) throw new Error();
}

/** Monthly bills likely paid straight from a savings box, to accept or ignore one by one. */
export function SavingsBoxSuggestions({
  locale,
  revision,
  categories,
  onChange,
}: {
  locale: Locale;
  revision: number;
  categories: CategoryNode[];
  onChange: () => void;
}) {
  const copy = messages[locale];
  const [result, setResult] = useState<Result>();
  // The suggestion being accepted: every field is prefilled and editable first.
  const [editing, setEditing] = useState<Suggestion>();
  const [boxes, setBoxes] = useState<{ item: string; name: string }[]>([]);
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    const request = new AbortController();
    void fetch("/api/spending/savings-box-suggestions", {
      signal: request.signal,
    })
      .then(async (response) => {
        if (!response.ok) throw new Error();
        setResult((await response.json()) as Result);
      })
      .catch(() => {
        // The section is optional: without it the rest of the page still works.
      });
    void fetch("/api/spending/manual", { signal: request.signal })
      .then(async (response) => {
        if (response.ok)
          setBoxes(
            (
              (await response.json()) as {
                boxes: { item: string; name: string }[];
              }
            ).boxes,
          );
      })
      .catch(() => undefined);
    return () => request.abort();
  }, [revision]);

  if (!result || (!result.suggestions.length && !failed)) return null;
  const key = (row: Suggestion) => `${row.cnpj}-${row.month}`;
  const money = (value: number) => formatMoney(String(value), "BRL", locale);

  async function act(action: () => Promise<void>) {
    setBusy(true);
    setFailed(false);
    try {
      await action();
      setEditing(undefined);
      onChange();
    } catch {
      setFailed(true);
    } finally {
      setBusy(false);
    }
  }

  function accept(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!editing) return;
    const form = new FormData(event.currentTarget);
    const value = (name: string) => String(form.get(name) ?? "").trim();
    const [year, month, day] = value("date").split("-");
    void act(() =>
      post("/api/spending/manual", {
        item: editing.item,
        description: value("description"),
        amount: value("amount").replace(",", "."),
        category: value("category") || null,
        day: Number(day),
        start: `${year}-${month}`,
        end: `${year}-${month}`,
        cnpj: value("cnpj").replace(/\D/g, ""),
        savings_box: value("savings_box"),
      }),
    );
  }

  const tree = categoryTree(categories);

  return (
    <section className="panel" aria-labelledby="box-suggestions">
      <h2 id="box-suggestions">
        {copy.boxSuggestions} ({result.suggestions.length})
      </h2>
      <p>
        {copy.boxSuggestionsHelp}{" "}
        {copy.boxYield.replace(
          "{rate}",
          new Intl.NumberFormat(locale, { maximumFractionDigits: 4 }).format(
            result.daily_rate * 100,
          ),
        )}
      </p>
      <ul>
        {result.gaps.map((gap) => (
          <li key={`${gap.item}-${gap.box}`}>
            {copy.boxGap
              .replace("{box}", gap.box)
              .replace("{gap}", money(gap.amount))
              .replace("{suggested}", money(gap.suggested))
              .replace("{observed}", money(gap.observed))
              .replace(
                "{since}",
                gap.observed_since
                  ? formatDate(gap.observed_since, locale)
                  : "—",
              )}
          </li>
        ))}
      </ul>
      {failed && <p role="alert">{copy.manualError}</p>}
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th scope="col">{copy.date}</th>
              <th scope="col">{copy.transactionDetails}</th>
              <th scope="col">{copy.amount}</th>
              <th scope="col">{copy.reviewAction}</th>
            </tr>
          </thead>
          <tbody>
            {result.suggestions.map((row) => (
              <tr key={key(row)}>
                <td>
                  <time dateTime={row.date}>
                    {formatDate(row.date, locale)}
                  </time>
                </td>
                <td className="transaction-details">
                  <div>{row.payee}</div>
                  <small>
                    <span className={`badge ${row.kind}`}>
                      {row.kind === "observed"
                        ? copy.observedDrop
                        : copy.estimatedDrop}
                    </span>{" "}
                    {row.kind === "observed" && row.window
                      ? copy.dropWindow
                          .replace("{start}", formatDate(row.window[0], locale))
                          .replace("{end}", formatDate(row.window[1], locale))
                      : copy.estimatedHelp}
                  </small>
                  <small>{row.category}</small>
                  <small>
                    {copy.paidFromSavingsBox}: {row.box}
                  </small>
                </td>
                <td>
                  {money(row.amount)}
                  <div>
                    <small>
                      {copy.observedRange
                        .replace("{low}", money(row.low))
                        .replace("{high}", money(row.high))}
                    </small>
                  </div>
                </td>
                <td>
                  <div className="review-actions">
                    <button
                      type="button"
                      disabled={busy}
                      onClick={() => setEditing(row)}
                    >
                      {copy.acceptSuggestion}
                    </button>
                    <button
                      type="button"
                      disabled={busy}
                      onClick={() =>
                        void act(() =>
                          post(
                            "/api/spending/savings-box-suggestions/dismiss",
                            {
                              cnpj: row.cnpj,
                              month: row.month,
                            },
                          ),
                        )
                      }
                    >
                      {copy.ignoreSuggestion}
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <Dialog
        open={Boolean(editing)}
        title={copy.acceptSuggestionTitle}
        closeLabel={copy.close}
        onClose={() => setEditing(undefined)}
      >
        {editing && (
          <form className="dialog-form" onSubmit={accept} key={key(editing)}>
            <p>
              <span className={`badge ${editing.kind}`}>
                {editing.kind === "observed"
                  ? copy.observedDrop
                  : copy.estimatedDrop}
              </span>{" "}
              <small>
                {copy.observedRange
                  .replace("{low}", money(editing.low))
                  .replace("{high}", money(editing.high))}
              </small>
            </p>
            <label>
              {copy.manualDescription}
              <input
                name="description"
                required
                maxLength={80}
                defaultValue={editing.payee}
              />
            </label>
            <label>
              {copy.amount}
              <input
                name="amount"
                required
                inputMode="decimal"
                pattern="\d+([.,]\d{1,2})?"
                defaultValue={editing.amount.toFixed(2)}
              />
            </label>
            <label>
              {copy.date}
              <input
                name="date"
                type="date"
                required
                defaultValue={editing.date}
              />
            </label>
            <label>
              {copy.category}
              <select name="category" defaultValue={editing.category_id}>
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
              {copy.paidFromSavingsBox}
              <select name="savings_box" defaultValue={editing.box}>
                {boxes
                  .filter((box) => box.item === editing.item)
                  .map((box) => (
                    <option key={box.name} value={box.name}>
                      {box.name}
                    </option>
                  ))}
              </select>
            </label>
            <label>
              {copy.manualCnpj}
              <input
                name="cnpj"
                inputMode="numeric"
                maxLength={18}
                pattern="[\d./-]*"
                defaultValue={editing.cnpj}
              />
            </label>
            <div className="review-actions">
              <button type="submit" disabled={busy}>
                {copy.acceptSuggestion}
              </button>
              <button
                type="button"
                disabled={busy}
                onClick={() => setEditing(undefined)}
              >
                {copy.cancelEdit}
              </button>
            </div>
          </form>
        )}
      </Dialog>
    </section>
  );
}
