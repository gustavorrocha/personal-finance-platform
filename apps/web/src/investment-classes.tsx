import { useEffect, useState, type FormEvent } from "react";
import { formatMoney, messages, type Locale } from "./locale";
import { Help } from "./ui";

type InvestmentClass = { id: string; name: string };
type Position = {
  position: string;
  type: string | null;
  name: string | null;
  symbol: string | null;
  currency: string;
  balance: string;
  class_id: string;
  automatic_id: string;
};

async function send(
  method: "POST" | "PUT" | "DELETE",
  path: string,
  body?: object,
) {
  const response = await fetch(`/api/investments/${path}`, {
    method,
    headers: { "Content-Type": "application/json" },
    body: body && JSON.stringify(body),
    signal: AbortSignal.timeout(5000),
  });
  if (!response.ok) throw new Error();
}

/** Editable investment classes and the class of each held position. */
export function InvestmentClasses({ locale }: { locale: Locale }) {
  const copy = messages[locale];
  const [data, setData] = useState<{
    classes: InvestmentClass[];
    positions: Position[];
  }>();
  const [revision, setRevision] = useState(0);
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState<"categorySaveError" | "categorySaved">();

  useEffect(() => {
    const request = new AbortController();
    void fetch("/api/investments/classes", { signal: request.signal })
      .then(async (response) => {
        if (!response.ok) throw new Error();
        setData(await response.json());
      })
      .catch(() => undefined);
    return () => request.abort();
  }, [revision]);

  async function change(action: () => Promise<void>) {
    setBusy(true);
    setStatus(undefined);
    try {
      await action();
      setStatus("categorySaved");
      setRevision((value) => value + 1);
    } catch {
      setStatus("categorySaveError");
    } finally {
      setBusy(false);
    }
  }

  function save(event: FormEvent<HTMLFormElement>, id?: string) {
    event.preventDefault();
    const target = event.currentTarget;
    const name = String(new FormData(target).get("name") ?? "").trim();
    if (!name) return;
    void change(async () => {
      await (id
        ? send("PUT", `classes/${id}`, { name })
        : send("POST", "classes", { name }));
      if (!id) target.reset();
    });
  }

  if (!data) return null;
  const names = new Map(data.classes.map((entry) => [entry.id, entry.name]));

  return (
    <section className="panel" aria-labelledby="investment-classes">
      <h2 id="investment-classes">{copy.investmentClasses}</h2>
      <Help label={copy.howItWorks}>{copy.investmentClassesHelp}</Help>
      {status && <p role="status">{copy[status]}</p>}
      {data.classes.map((entry) => (
        <form
          className="category-row"
          key={`${entry.id}-${entry.name}`}
          onSubmit={(event) => save(event, entry.id)}
        >
          <input
            name="name"
            aria-label={copy.categoryName}
            defaultValue={entry.name}
            maxLength={60}
            required
            disabled={busy}
          />
          <button type="submit" disabled={busy}>
            {copy.saveCategory}
          </button>
          <button
            type="button"
            disabled={busy}
            onClick={() => {
              if (
                window.confirm(
                  copy.deleteInvestmentClassConfirm.replace(
                    "{name}",
                    entry.name,
                  ),
                )
              )
                void change(() => send("DELETE", `classes/${entry.id}`));
            }}
          >
            {copy.deleteInvestmentClass}
          </button>
        </form>
      ))}
      <form className="category-row add" onSubmit={(event) => save(event)}>
        <input
          name="name"
          aria-label={copy.newInvestmentClass}
          placeholder={copy.newInvestmentClass}
          maxLength={60}
          required
          disabled={busy}
        />
        <button type="submit" disabled={busy}>
          {copy.addCategory}
        </button>
      </form>
      <h3>{copy.investmentPositions}</h3>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th scope="col">{copy.transactionDetails}</th>
              <th scope="col" className="numeric">
                {copy.amount}
              </th>
              <th scope="col">{copy.investmentClass}</th>
            </tr>
          </thead>
          <tbody>
            {data.positions.map((row) => (
              <tr key={row.position}>
                <td>
                  <div>{row.name || row.symbol || row.type}</div>
                  {row.symbol && row.symbol !== row.name && (
                    <small>{row.symbol}</small>
                  )}
                </td>
                <td className="numeric">
                  {formatMoney(row.balance, row.currency, locale)}
                </td>
                <td>
                  <select
                    aria-label={copy.investmentClass}
                    value={
                      row.class_id && names.has(row.class_id)
                        ? row.class_id
                        : ""
                    }
                    disabled={busy}
                    onChange={(event) =>
                      void change(() =>
                        send("POST", "assignments", {
                          position: row.position,
                          class_id: event.target.value || null,
                        }),
                      )
                    }
                  >
                    <option value="">
                      {copy.automaticClass.replace(
                        "{name}",
                        names.get(row.automatic_id) ??
                          copy.unclassifiedInvestment,
                      )}
                    </option>
                    {data.classes.map((entry) => (
                      <option key={entry.id} value={entry.id}>
                        {entry.name}
                      </option>
                    ))}
                  </select>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
