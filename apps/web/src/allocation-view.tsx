import { useEffect, useState } from "react";
import { splitContribution } from "./allocation";
import { formatMoney, messages, type Locale } from "./locale";
import { Help } from "./ui";

type Allocation = {
  classes: { id: string; name: string; target: string }[];
  held: { currency: string; class_id: string; total: string }[];
  cash: { currency: string; total: string }[];
};

const savedTargets = (data: Allocation) =>
  Object.fromEntries(
    data.classes.map((row) => [row.id, String(Number(row.target))]),
  );

/** Target share per investment class and how to split new cash to approach it. */
export function AllocationPlanner({ locale }: { locale: Locale }) {
  const copy = messages[locale];
  const [data, setData] = useState<Allocation>();
  const [targets, setTargets] = useState<Record<string, string>>({});
  const [currency, setCurrency] = useState("BRL");
  const [cash, setCash] = useState<string>();
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState<
    "allocationSaved" | "allocationSaveError"
  >();
  const [revision, setRevision] = useState(0);

  useEffect(() => {
    const request = new AbortController();
    void fetch("/api/investments/allocation", { signal: request.signal })
      .then(async (response) => {
        if (!response.ok) throw new Error();
        const next: Allocation = await response.json();
        setData(next);
        setTargets(savedTargets(next));
      })
      .catch(() => undefined);
    return () => request.abort();
  }, [revision]);

  if (!data || data.classes.length === 0) return null;
  const currencies = [
    ...new Set([...data.held, ...data.cash].map((row) => row.currency)),
  ].sort();
  const bank = Math.max(
    0,
    Number(data.cash.find((row) => row.currency === currency)?.total ?? 0),
  );
  const amount = Math.max(0, Number(cash ?? bank) || 0);
  const money = (value: number) => formatMoney(String(value), currency, locale);
  const held = (id: string) =>
    data.held
      .filter((row) => row.currency === currency && row.class_id === id)
      .reduce((total, row) => total + Number(row.total), 0);
  // Positions without an active class keep their money but have no target.
  const rows = [
    ...data.classes.map((row) => ({ ...row, held: held(row.id) })),
    ...(held("") !== 0
      ? [{ id: "", name: copy.unclassifiedInvestment, held: held("") }]
      : []),
  ];
  const percent = (id: string) => Number(targets[id] || 0);
  const sum = rows.reduce((total, row) => total + percent(row.id), 0);
  const valid = Math.abs(sum - 100) < 0.00005;
  const dirty = data.classes.some(
    (row) => Number(row.target) !== percent(row.id),
  );
  const split = valid
    ? splitContribution(
        rows.map((row) => row.held),
        rows.map((row) => percent(row.id)),
        amount,
      )
    : rows.map(() => 0);
  const now = rows.reduce((total, row) => total + row.held, 0);
  const after = now + amount;
  const shareNow = rows.map((row) => (now > 0 ? row.held / now : 0));
  const shareAfter = rows.map((row, index) =>
    after > 0 ? (row.held + split[index]) / after : 0,
  );
  // Share of the portfolio sitting in the wrong class: half the total deviation.
  const off = (shares: number[]) =>
    rows.reduce(
      (total, row, index) =>
        total + Math.abs(shares[index] - percent(row.id) / 100),
      0,
    ) / 2;
  const receiving = split.filter((value) => value > 0).length;
  const pct = new Intl.NumberFormat(locale, {
    style: "percent",
    maximumFractionDigits: 1,
  });
  const points = new Intl.NumberFormat(locale, { maximumFractionDigits: 2 });
  const fill = (fraction: number) =>
    `${Math.min(100, Math.max(0, fraction * 100))}%`;

  async function save() {
    setBusy(true);
    setStatus(undefined);
    try {
      const response = await fetch("/api/investments/targets", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          targets: Object.fromEntries(
            data!.classes
              .filter((row) => percent(row.id) > 0)
              .map((row) => [row.id, percent(row.id)]),
          ),
        }),
        signal: AbortSignal.timeout(5000),
      });
      if (!response.ok) throw new Error();
      setStatus("allocationSaved");
      setRevision((value) => value + 1);
    } catch {
      setStatus("allocationSaveError");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="panel allocation" aria-labelledby="allocation-planner">
      <h2 id="allocation-planner">{copy.allocationTitle}</h2>
      <Help label={copy.howItWorks}>{copy.allocationHelp}</Help>

      <div className="allocation-inputs">
        {currencies.length > 1 && (
          <label>
            {copy.currency}
            <select
              value={currency}
              onChange={(event) => setCurrency(event.target.value)}
            >
              {currencies.map((value) => (
                <option key={value}>{value}</option>
              ))}
            </select>
          </label>
        )}
        <label>
          {copy.allocationCash}
          <input
            type="number"
            min={0}
            step={0.01}
            inputMode="decimal"
            value={cash ?? bank.toFixed(2)}
            onChange={(event) => setCash(event.target.value)}
          />
        </label>
        <p className="allocation-bank">
          {copy.allocationBank.replace("{amount}", money(bank))}
          {cash !== undefined && Number(cash) !== bank && (
            <button
              type="button"
              className="link"
              onClick={() => setCash(undefined)}
            >
              {copy.allocationUseBank}
            </button>
          )}
        </p>
      </div>

      {valid && (
        <div className="allocation-plan" aria-live="polite">
          <strong>
            {amount === 0
              ? copy.allocationNothing
              : (receiving === 1 ? copy.allocationPlanOne : copy.allocationPlan)
                  .replace("{amount}", money(amount))
                  .replace("{count}", String(receiving))}
          </strong>
          {now > 0 && (
            <span>
              {copy.allocationOff
                .replace("{before}", pct.format(off(shareNow)))
                .replace("{after}", pct.format(off(shareAfter)))}
            </span>
          )}
        </div>
      )}

      <ul className="legend allocation-legend" aria-hidden="true">
        <li>
          <i className="swatch previous" />
          {copy.allocationHeld}
        </li>
        <li>
          <i className="swatch invested" />
          {copy.allocationAfter}
        </li>
        <li>
          <i className="allocation-tick" />
          {copy.allocationTarget}
        </li>
      </ul>

      <ul className="allocation-rows">
        {rows.map((row, index) => {
          const target = percent(row.id);
          return (
            <li key={row.id || "unclassified"} className="allocation-row">
              <div className="allocation-name">
                <strong>{row.name}</strong>
                <small>
                  {money(row.held)} ·{" "}
                  {copy.allocationShares
                    .replace("{now}", pct.format(shareNow[index]))
                    .replace(
                      "{after}",
                      valid ? pct.format(shareAfter[index]) : "–",
                    )}
                </small>
              </div>
              <div
                className="allocation-bars"
                role="img"
                aria-label={`${copy.allocationHeld} ${pct.format(shareNow[index])}, ${copy.allocationAfter} ${valid ? pct.format(shareAfter[index]) : "–"}, ${copy.allocationTarget} ${pct.format(target / 100)}`}
              >
                <span>
                  <b style={{ width: fill(shareNow[index]) }} />
                </span>
                <span className="after">
                  <b style={{ width: fill(valid ? shareAfter[index] : 0) }} />
                </span>
                {row.id && target > 0 && (
                  <i
                    className="allocation-tick"
                    style={{ left: fill(target / 100) }}
                  />
                )}
              </div>
              <label className="allocation-target">
                <span className="visually-hidden">
                  {copy.allocationTarget} · {row.name}
                </span>
                {row.id ? (
                  <span className="allocation-percent">
                    <input
                      type="number"
                      min={0}
                      max={100}
                      step={0.1}
                      inputMode="decimal"
                      value={targets[row.id] ?? "0"}
                      disabled={busy}
                      onChange={(event) =>
                        setTargets({ ...targets, [row.id]: event.target.value })
                      }
                    />
                    %
                  </span>
                ) : (
                  <small>{copy.allocationNoTarget}</small>
                )}
              </label>
              <div
                className={
                  split[index] > 0
                    ? "allocation-invest receives"
                    : "allocation-invest"
                }
              >
                {split[index] > 0 ? `+ ${money(split[index])}` : "–"}
              </div>
            </li>
          );
        })}
      </ul>

      <div className="allocation-footer">
        <span
          className={valid ? "allocation-sum ok" : "allocation-sum"}
          role="status"
        >
          {valid
            ? copy.allocationComplete
            : sum === 0
              ? copy.allocationNoTargets
              : (sum < 100
                  ? copy.allocationRemaining
                  : copy.allocationExcess
                ).replace("{points}", points.format(Math.abs(100 - sum)))}
        </span>
        {status && !dirty && <span role="status">{copy[status]}</span>}
        {dirty && (
          <span className="allocation-dirty">{copy.allocationUnsaved}</span>
        )}
        <span className="allocation-actions">
          {dirty && (
            <button
              type="button"
              disabled={busy}
              onClick={() => setTargets(savedTargets(data))}
            >
              {copy.allocationDiscard}
            </button>
          )}
          <button
            type="button"
            className="primary"
            disabled={busy || !dirty || !(valid || sum === 0)}
            onClick={() => void save()}
          >
            {copy.allocationSave}
          </button>
        </span>
      </div>
    </section>
  );
}
