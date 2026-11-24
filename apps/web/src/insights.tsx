import { useState } from "react";
import type { InvestmentReturnsData } from "./investment-returns";
import { formatMoney, messages, type Locale } from "./locale";
import {
  currencies,
  monthlyInvestments,
  monthlyTotals,
  cumulative,
  usualPace,
  type DailyRow,
  type HistoryRow,
  type InvestmentRow,
} from "./spending-history";

export type { DailyRow };

const WIDTH = 640;
const HEIGHT = 220;
const PAD = { top: 12, right: 12, bottom: 24, left: 64 };

function monthLabel(month: string, locale: Locale, long = false) {
  return new Intl.DateTimeFormat(locale, {
    month: long ? "long" : "short",
    year: long ? "numeric" : "2-digit",
    timeZone: "UTC",
  }).format(new Date(`${month}-01T00:00:00Z`));
}

/** Round step so an axis gets about four gridlines. */
function niceTicks(max: number) {
  const raw = max / 4 || 1;
  const power = 10 ** Math.floor(Math.log10(raw));
  const step = [1, 2, 2.5, 5, 10].map((n) => n * power).find((n) => n >= raw)!;
  return Array.from(
    { length: Math.floor(max / step) + 1 },
    (_, index) => index * step,
  );
}

/** Spending accumulated day by day in the month against the usual pace. */
export function MonthPace({
  rows,
  month,
  today,
  locale,
}: {
  rows: DailyRow[];
  month: string;
  /** ISO date; the current month's line stops on it. */
  today: string;
  locale: Locale;
}) {
  const copy = messages[locale];
  const [hover, setHover] = useState<number>();
  const percent = new Intl.NumberFormat(locale, {
    style: "percent",
    signDisplay: "exceptZero",
    maximumFractionDigits: 0,
  });
  const shown = [...new Set(rows.map((row) => row.currency))].sort();
  if (!shown.length) return <p>{copy.noSpending}</p>;
  return (
    <>
      {shown.map((currency) => {
        const current = cumulative(rows, currency, month);
        const { months, average } = usualPace(rows, currency, month);
        const last =
          today.slice(0, 7) === month
            ? Number(today.slice(8))
            : today.slice(0, 7) < month
              ? 0
              : current.length;
        const reached = current.slice(0, last);
        const money = (value: number) =>
          formatMoney(String(value), currency, locale);
        const max = Math.max(1, ...reached, ...average);
        const ticks = niceTicks(max);
        const top = ticks.at(-1)!;
        const x = (day: number) =>
          PAD.left +
          (day / Math.max(1, current.length - 1)) *
            (WIDTH - PAD.left - PAD.right);
        const y = (value: number) =>
          HEIGHT - PAD.bottom - (value / top) * (HEIGHT - PAD.top - PAD.bottom);
        const path = (values: number[]) =>
          values
            .map((value, day) => `${day ? "L" : "M"}${x(day)},${y(value)}`)
            .join("");
        const now = reached.at(-1) ?? 0;
        const usual = average[Math.max(0, last - 1)] ?? 0;
        const ratio = usual > 0 ? now / usual - 1 : null;
        const day = hover ?? Math.max(0, last - 1);
        return (
          <div className="chart" key={currency}>
            {shown.length > 1 && <h3>{currency}</h3>}
            {last > 0 && months > 0 && (
              <p className="headline">
                {copy.paceHeadline
                  .replace("{day}", String(last))
                  .replace("{spent}", money(now))
                  .replace("{usual}", money(usual))}{" "}
                {ratio !== null && (
                  <strong className={ratio > 0 ? "over" : "under"}>
                    {percent.format(ratio)}
                  </strong>
                )}
              </p>
            )}
            <ul className="legend">
              <li>
                <i className="swatch line-current" aria-hidden="true" />
                {monthLabel(month, locale, true)}
              </li>
              <li>
                <i className="swatch line-usual" aria-hidden="true" />
                {copy.paceUsual.replace("{months}", String(months))}
              </li>
            </ul>
            <div className="plot">
              <svg
                viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
                role="img"
                aria-label={copy.paceChart}
                onMouseLeave={() => setHover(undefined)}
                onMouseMove={(event) => {
                  const box = event.currentTarget.getBoundingClientRect();
                  const position =
                    ((event.clientX - box.left) / box.width) * WIDTH;
                  const index = Math.round(
                    ((position - PAD.left) / (WIDTH - PAD.left - PAD.right)) *
                      (current.length - 1),
                  );
                  setHover(Math.max(0, Math.min(current.length - 1, index)));
                }}
              >
                {ticks.map((tick) => (
                  <g key={tick} className="grid">
                    <line
                      x1={PAD.left}
                      x2={WIDTH - PAD.right}
                      y1={y(tick)}
                      y2={y(tick)}
                    />
                    <text x={PAD.left - 6} y={y(tick)} dy="0.32em">
                      {new Intl.NumberFormat(locale, {
                        notation: "compact",
                      }).format(tick)}
                    </text>
                  </g>
                ))}
                {[1, 8, 15, 22, current.length].map((value) => (
                  <text
                    key={value}
                    className="axis"
                    x={x(value - 1)}
                    y={HEIGHT - 6}
                  >
                    {value}
                  </text>
                ))}
                {months > 0 && (
                  <path className="line usual" d={path(average)} />
                )}
                {reached.length > 0 && (
                  <path className="line current" d={path(reached)} />
                )}
                {hover !== undefined && (
                  <line
                    className="crosshair"
                    x1={x(hover)}
                    x2={x(hover)}
                    y1={PAD.top}
                    y2={HEIGHT - PAD.bottom}
                  />
                )}
                {day < reached.length && (
                  <circle
                    className="dot current"
                    cx={x(day)}
                    cy={y(reached[day])}
                    r={4}
                  />
                )}
              </svg>
              {hover !== undefined && (
                <div
                  className="plot-tooltip"
                  style={{
                    left: `${(x(hover) / WIDTH) * 100}%`,
                    transform:
                      hover > current.length / 2
                        ? "translateX(-100%)"
                        : undefined,
                  }}
                >
                  <b>
                    {copy.manualDay} {hover + 1}
                  </b>
                  {hover < reached.length && (
                    <span>
                      {monthLabel(month, locale)}: {money(reached[hover])}
                    </span>
                  )}
                  {months > 0 && (
                    <span>
                      {copy.paceUsualShort}: {money(average[hover])}
                    </span>
                  )}
                </div>
              )}
            </div>
          </div>
        );
      })}
    </>
  );
}

/** Per month: what was spent and what was invested net of withdrawals. */
export function CashFlow({
  history,
  investments,
  month,
  end,
  locale,
  disabled,
  onSelect,
}: {
  history: HistoryRow[];
  investments: InvestmentRow[];
  month: string;
  end: string;
  locale: Locale;
  disabled: boolean;
  onSelect: (month: string) => void;
}) {
  const copy = messages[locale];
  const shown = [
    ...new Set([
      ...currencies(history),
      ...investments.map((row) => row.currency),
    ]),
  ].sort();
  return (
    <>
      <ul className="legend">
        <li>
          <i className="swatch spent" aria-hidden="true" />
          {copy.cashFlowSpent}
        </li>
        <li>
          <i className="swatch invested" aria-hidden="true" />
          {copy.netInvested}
        </li>
      </ul>
      {shown.map((currency) => {
        const spent = monthlyTotals(history, currency, end);
        const invested = monthlyInvestments(investments, currency, end);
        const rows = spent.map((entry, index) => ({
          month: entry.month,
          spent: entry.total,
          invested: invested[index].net,
        }));
        const high = Math.max(
          1,
          ...rows.flatMap((row) => [row.spent, row.invested]),
        );
        const low = Math.min(0, ...rows.map((row) => row.invested));
        const span = high - low;
        const money = (value: number) =>
          formatMoney(String(value), currency, locale);
        const bar = (value: number) => ({
          height: `${(Math.abs(value) / span) * 100}%`,
          bottom: `${((Math.min(0, value) - low) / span) * 100}%`,
        });
        return (
          <div className="chart" key={currency}>
            {shown.length > 1 && <h3>{currency}</h3>}
            <div className="month-chart">
              {rows.map((row) => (
                <button
                  type="button"
                  key={row.month}
                  className="month-column"
                  aria-pressed={row.month === month}
                  aria-label={`${monthLabel(row.month, locale, true)}: ${copy.cashFlowSpent} ${money(row.spent)}, ${copy.netInvested} ${money(row.invested)}`}
                  disabled={disabled}
                  onClick={() => onSelect(row.month)}
                >
                  <span className="month-tooltip" aria-hidden="true">
                    <b>{monthLabel(row.month, locale, true)}</b>
                    <span>
                      {copy.cashFlowSpent}: {money(row.spent)}
                    </span>
                    <span>
                      {copy.netInvested}: {money(row.invested)}
                    </span>
                    <b>
                      {copy.cashFlowTotal}: {money(row.spent + row.invested)}
                    </b>
                  </span>
                  <span className="pair-plot" aria-hidden="true">
                    <span
                      className="zero"
                      style={{ bottom: `${(-low / span) * 100}%` }}
                    />
                    <i className="swatch spent" style={bar(row.spent)} />
                    <i
                      className={
                        row.invested < 0
                          ? "swatch invested negative"
                          : "swatch invested"
                      }
                      style={bar(row.invested)}
                    />
                  </span>
                  <span className="month-label" aria-hidden="true">
                    {monthLabel(row.month, locale)}
                  </span>
                </button>
              ))}
            </div>
          </div>
        );
      })}
    </>
  );
}

/** Summary tile: the portfolio's 12-month return against the CDI over the same days. */
export function ReturnsTile({
  data,
  locale,
}: {
  data: InvestmentReturnsData;
  locale: Locale;
}) {
  const copy = messages[locale];
  const row = data.rows.find((entry) => entry.kind === "portfolio");
  const value = row?.returns["12m"];
  const cdi = row?.cdi["12m"];
  if (!row || value == null) return null;
  const percent = (number: number, digits = 2) =>
    new Intl.NumberFormat(locale, {
      style: "percent",
      minimumFractionDigits: digits,
      maximumFractionDigits: digits,
    }).format(number);
  return (
    <div>
      <span>{copy.returnsTile}</span>
      <strong>{percent(Number(value))}</strong>
      {cdi != null && Number(cdi) > 0 && (
        <small>
          {copy.returnsCdi} {percent(Number(cdi))} ·{" "}
          {copy.returnsOfCdi.replace(
            "{percent}",
            percent(Number(value) / Number(cdi), 0),
          )}
        </small>
      )}
      <a href="#investments">{copy.seeInvestments}</a>
    </div>
  );
}
