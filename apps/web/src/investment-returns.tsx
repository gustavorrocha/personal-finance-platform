import { useState } from "react";
import { formatDate, formatMoney, messages, type Locale } from "./locale";
import { Help } from "./ui";

const PERIODS = ["month", "3m", "6m", "12m", "ytd"] as const;
type Period = (typeof PERIODS)[number];
type PeriodReturns = Record<Period, string | null>;

export type InvestmentReturnsData = {
  end: string;
  rows: {
    kind: "portfolio" | "class" | "position";
    key: string;
    name: string;
    value: string;
    returns: PeriodReturns;
    /** The CDI over the days the row was held. */
    cdi: PeriodReturns;
  }[];
  cdi: PeriodReturns;
  uncovered: { name: string; value: string }[];
  series: {
    days: string[];
    lines: {
      kind: "cdi" | "portfolio" | "class";
      key: string;
      name: string;
      /** Cumulative return, null before the line's class entered the portfolio. */
      values: (string | null)[];
      /** Lead over the CDI compounded on the same days. */
      excess: (string | null)[];
    }[];
  };
};

type Line = InvestmentReturnsData["series"]["lines"][number];

const PERIOD_LABELS = {
  month: "periodMonth",
  "3m": "period3m",
  "6m": "period6m",
  "12m": "period12m",
  ytd: "periodYtd",
} as const;

// Same palette size as the invested wealth chart; classes keep its name order.
const SERIES = 6;
// Direct labels at the line ends only while they stay readable.
const LABELLED = 4;

/** Time-weighted returns of the portfolio, classes and positions against the CDI. */
export function InvestmentReturns({
  data,
  locale,
}: {
  data: InvestmentReturnsData;
  locale: Locale;
}) {
  const copy = messages[locale];
  const percent = (value: string | null) =>
    value === null
      ? "—"
      : new Intl.NumberFormat(locale, {
          style: "percent",
          minimumFractionDigits: 2,
          maximumFractionDigits: 2,
        }).format(Number(value));
  const ofCdi = (value: string | null, cdi: string | null) => {
    if (value === null || cdi === null || !(Number(cdi) > 0)) return null;
    return copy.returnsOfCdi.replace(
      "{percent}",
      new Intl.NumberFormat(locale, {
        style: "percent",
        maximumFractionDigits: 0,
      }).format(Number(value) / Number(cdi)),
    );
  };
  const label = (row: { kind: string; key: string; name: string }) =>
    row.kind === "portfolio"
      ? copy.returnsPortfolio
      : row.kind === "cdi"
        ? copy.returnsCdi
        : row.kind === "class" && !row.key
          ? copy.unclassifiedInvestment
          : row.name;
  return (
    <>
      <Help label={copy.howItWorks}>
        {copy.investmentReturnsHelp.replace(
          "{date}",
          formatDate(data.end, locale),
        )}
      </Help>
      <ReturnsChart
        series={data.series}
        locale={locale}
        percent={percent}
        label={label}
      />
      <div className="table-wrap">
        <table className="returns-table">
          <thead>
            <tr>
              <th scope="col">{copy.investment}</th>
              <th scope="col" className="numeric">
                {copy.amount}
              </th>
              {PERIODS.map((period) => (
                <th scope="col" className="numeric" key={period}>
                  {copy[PERIOD_LABELS[period]]}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {data.rows.map((row) => (
              <tr
                key={`${row.kind}-${row.key}`}
                className={`returns-${row.kind}`}
              >
                <th scope="row">{label(row)}</th>
                <td className="numeric">
                  {formatMoney(row.value, "BRL", locale)}
                </td>
                {PERIODS.map((period) => {
                  const relative = ofCdi(row.returns[period], row.cdi[period]);
                  return (
                    <td className="numeric" key={period}>
                      {percent(row.returns[period])}
                      {relative && <small>{relative}</small>}
                    </td>
                  );
                })}
              </tr>
            ))}
            <tr className="returns-benchmark">
              <th scope="row">{copy.returnsCdi}</th>
              <td />
              {PERIODS.map((period) => (
                <td className="numeric" key={period}>
                  {percent(data.cdi[period])}
                </td>
              ))}
            </tr>
          </tbody>
        </table>
      </div>
      {data.uncovered.length > 0 && (
        <div className="notice" role="note">
          <p>{copy.returnsUncovered}</p>
          <ul>
            {data.uncovered.map((row) => (
              <li key={row.name}>
                {row.name}: {formatMoney(row.value, "BRL", locale)}
              </li>
            ))}
          </ul>
        </div>
      )}
    </>
  );
}

const WIDTH = 640;
const HEIGHT = 260;
const PAD = { top: 12, right: 8, bottom: 24, left: 56 };
const LABEL_WIDTH = 150;
const STEPS = [
  0.001, 0.0025, 0.005, 0.01, 0.02, 0.025, 0.05, 0.1, 0.2, 0.25, 0.5, 1,
];

/** Round tick values covering [low, high] with at most six intervals. */
function ticks(low: number, high: number) {
  const step = STEPS.find((size) => (high - low) / size <= 6) ?? 1;
  const values = [];
  for (
    let value = Math.floor(low / step) * step;
    value <= high + step / 2;
    value += step
  )
    values.push(Number(value.toFixed(6)));
  return values;
}

function ReturnsChart({
  series,
  locale,
  percent,
  label,
}: {
  series: InvestmentReturnsData["series"];
  locale: Locale;
  percent: (value: string | null) => string;
  label: (line: Line) => string;
}) {
  const copy = messages[locale];
  const [hover, setHover] = useState<number>();
  const [mode, setMode] = useState<"values" | "excess">("values");
  const { days } = series;
  if (days.length < 2 || series.lines.length === 0) return null;
  // Classes in the API's order (by name, unclassified last) take the fixed palette;
  // the portfolio is drawn in ink and the CDI dashed, outside the palette.
  let next = 0;
  const styled = series.lines.map((line) => ({
    line,
    className:
      line.kind === "class"
        ? `series-${Math.min(next++, SERIES - 1) + 1}`
        : `returns-${line.kind}`,
  }));
  // Against the CDI, the CDI itself is the zero line.
  const shown = styled.filter(
    ({ line }) => mode === "values" || line.kind !== "cdi",
  );
  const points = (line: Line) => line[mode];
  // Draw the CDI first and the portfolio last, on top.
  const drawn = [
    ...shown.filter(({ line }) => line.kind === "cdi"),
    ...shown.filter(({ line }) => line.kind === "class"),
    ...shown.filter(({ line }) => line.kind === "portfolio"),
  ];
  const labelled = shown.length <= LABELLED;
  const right = WIDTH - PAD.right - (labelled ? LABEL_WIDTH : 0);
  const values = shown.flatMap(({ line }) =>
    points(line)
      .filter((value): value is string => value !== null)
      .map(Number),
  );
  const grid = ticks(Math.min(0, ...values), Math.max(0, ...values));
  const low = grid[0];
  const high = grid[grid.length - 1];
  const span = high - low || 1;
  const x = (index: number) =>
    PAD.left + (index / (days.length - 1)) * (right - PAD.left);
  const y = (value: number) =>
    PAD.top + ((high - value) / span) * (HEIGHT - PAD.top - PAD.bottom);
  const last = days.length - 1;
  const axis = (value: number) =>
    new Intl.NumberFormat(locale, {
      style: "percent",
      maximumFractionDigits: 2,
    }).format(value);
  // End labels, nudged apart so they never overlap.
  const ends = shown
    .map(({ line }) => ({ line, at: y(Number(points(line)[last])) }))
    .sort((a, b) => a.at - b.at);
  for (let index = 1; index < ends.length; index += 1)
    ends[index].at = Math.max(ends[index].at, ends[index - 1].at + 14);
  const months = days
    .map((day, index) => ({ day, index }))
    .filter(
      ({ day, index }) =>
        index === last || day.slice(0, 7) !== days[index + 1].slice(0, 7),
    );
  const title = mode === "values" ? copy.returnsChart : copy.returnsVsCdiChart;
  const summary = shown
    .map(({ line }) => `${label(line)} ${percent(points(line)[last])}`)
    .join(", ");
  return (
    <div className="chart returns-chart">
      <div className="returns-heading">
        <h3>{title}</h3>
        <div
          className="returns-mode"
          role="group"
          aria-label={copy.returnsChartView}
        >
          {(["values", "excess"] as const).map((option) => (
            <button
              type="button"
              key={option}
              aria-pressed={mode === option}
              onClick={() => setMode(option)}
            >
              {option === "values" ? copy.returnsCumulative : copy.returnsVsCdi}
            </button>
          ))}
        </div>
      </div>
      {mode === "excess" && <p>{copy.returnsVsCdiHelp}</p>}
      <ul className="legend">
        {shown.map(({ line, className }) => (
          <li key={`${line.kind}-${line.key}`}>
            <i className={`swatch ${className}`} aria-hidden="true" />
            {label(line)}
          </li>
        ))}
      </ul>
      <div className="returns-plot">
        <svg
          viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
          role="img"
          aria-label={`${title}: ${summary}`}
          onPointerMove={(event) => {
            const box = event.currentTarget.getBoundingClientRect();
            const position =
              ((event.clientX - box.left) / box.width) * WIDTH - PAD.left;
            const index = Math.round(
              (position / (right - PAD.left)) * (days.length - 1),
            );
            setHover(Math.max(0, Math.min(last, index)));
          }}
          onPointerLeave={() => setHover(undefined)}
        >
          {grid.map((value) => (
            <g key={value}>
              <line
                className={value === 0 ? "returns-zero" : "returns-grid"}
                x1={PAD.left}
                x2={right}
                y1={y(value)}
                y2={y(value)}
              />
              <text
                className="returns-axis"
                x={PAD.left - 6}
                y={y(value)}
                textAnchor="end"
              >
                {value === 0 && mode === "excess"
                  ? copy.returnsCdi
                  : axis(value)}
              </text>
            </g>
          ))}
          {drawn.map(({ line, className }) => (
            <polyline
              key={`${line.kind}-${line.key}`}
              className={`returns-line ${className}`}
              points={points(line)
                .map((value, index) =>
                  value === null ? null : `${x(index)},${y(Number(value))}`,
                )
                .filter(Boolean)
                .join(" ")}
            />
          ))}
          {labelled &&
            ends.map(({ line, at }) => (
              <text
                key={`${line.kind}-${line.key}`}
                className="returns-label"
                x={right + 8}
                y={at}
              >
                {label(line)} {percent(points(line)[last])}
              </text>
            ))}
          <text className="returns-axis" x={PAD.left} y={HEIGHT - 6}>
            {formatDate(days[0], locale)}
          </text>
          <text
            className="returns-axis"
            x={right}
            y={HEIGHT - 6}
            textAnchor="end"
          >
            {formatDate(days[last], locale)}
          </text>
          {hover !== undefined && (
            <g>
              <line
                className="returns-cursor"
                x1={x(hover)}
                x2={x(hover)}
                y1={PAD.top}
                y2={HEIGHT - PAD.bottom}
              />
              {drawn.map(({ line, className }) => {
                const value = points(line)[hover];
                return value === null ? null : (
                  <circle
                    key={`${line.kind}-${line.key}`}
                    className={`returns-dot ${className}`}
                    cx={x(hover)}
                    cy={y(Number(value))}
                    r={4}
                  />
                );
              })}
            </g>
          )}
        </svg>
        {hover !== undefined && (
          <span
            className="returns-tooltip"
            style={{ left: `${(x(hover) / WIDTH) * 100}%` }}
            aria-hidden="true"
          >
            <b>{formatDate(days[hover], locale)}</b>
            {shown.map(({ line }) =>
              points(line)[hover] === null ? null : (
                <span key={`${line.kind}-${line.key}`}>
                  {label(line)}: {percent(points(line)[hover])}
                </span>
              ),
            )}
          </span>
        )}
      </div>
      <details>
        <summary>{copy.showTable}</summary>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th scope="col">{copy.month}</th>
                {shown.map(({ line }) => (
                  <th
                    scope="col"
                    className="numeric"
                    key={`${line.kind}-${line.key}`}
                  >
                    {label(line)}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {months.map(({ day, index }) => (
                <tr key={day}>
                  <th scope="row">{formatDate(day, locale)}</th>
                  {shown.map(({ line }) => (
                    <td className="numeric" key={`${line.kind}-${line.key}`}>
                      {percent(points(line)[index])}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
    </div>
  );
}
