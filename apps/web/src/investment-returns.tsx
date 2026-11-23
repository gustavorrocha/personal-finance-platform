import { useState } from "react";
import { formatDate, formatMoney, messages, type Locale } from "./locale";

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
  }[];
  cdi: PeriodReturns;
  uncovered: { name: string; value: string }[];
  series: { day: string; portfolio: string; cdi: string }[];
};

const PERIOD_LABELS = {
  month: "periodMonth",
  "3m": "period3m",
  "6m": "period6m",
  "12m": "period12m",
  ytd: "periodYtd",
} as const;

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
  const ofCdi = (value: string | null, period: Period) => {
    const cdi = Number(data.cdi[period]);
    if (value === null || !(cdi > 0)) return null;
    return copy.returnsOfCdi.replace(
      "{percent}",
      new Intl.NumberFormat(locale, {
        style: "percent",
        maximumFractionDigits: 0,
      }).format(Number(value) / cdi),
    );
  };
  const label = (row: InvestmentReturnsData["rows"][number]) =>
    row.kind === "portfolio"
      ? copy.returnsPortfolio
      : row.kind === "class" && !row.key
        ? copy.unclassifiedInvestment
        : row.name;
  return (
    <>
      <p>
        {copy.investmentReturnsHelp.replace(
          "{date}",
          formatDate(data.end, locale),
        )}
      </p>
      <ReturnsChart series={data.series} locale={locale} percent={percent} />
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
                  const relative =
                    row.kind === "position"
                      ? null
                      : ofCdi(row.returns[period], period);
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
const HEIGHT = 220;
const PAD = { top: 12, right: 112, bottom: 24, left: 8 };

function ReturnsChart({
  series,
  locale,
  percent,
}: {
  series: InvestmentReturnsData["series"];
  locale: Locale;
  percent: (value: string | null) => string;
}) {
  const copy = messages[locale];
  const [hover, setHover] = useState<number>();
  if (series.length < 2) return null;
  const values = series.flatMap((point) => [
    Number(point.portfolio),
    Number(point.cdi),
  ]);
  const low = Math.min(0, ...values);
  const high = Math.max(0, ...values);
  const span = high - low || 1;
  const x = (index: number) =>
    PAD.left + (index / (series.length - 1)) * (WIDTH - PAD.left - PAD.right);
  const y = (value: number) =>
    PAD.top + ((high - value) / span) * (HEIGHT - PAD.top - PAD.bottom);
  const path = (pick: (point: (typeof series)[number]) => string) =>
    series
      .map((point, index) => `${x(index)},${y(Number(pick(point)))}`)
      .join(" ");
  const last = series[series.length - 1];
  const point = hover === undefined ? undefined : series[hover];
  const months = series.filter(
    (entry, index) =>
      index === series.length - 1 ||
      entry.day.slice(0, 7) !== series[index + 1].day.slice(0, 7),
  );
  // Keep the two end labels apart when the lines finish close together.
  let portfolioY = y(Number(last.portfolio));
  let cdiY = y(Number(last.cdi));
  if (Math.abs(portfolioY - cdiY) < 14) {
    const middle = (portfolioY + cdiY) / 2;
    const up = portfolioY <= cdiY ? -7 : 7;
    portfolioY = middle + up;
    cdiY = middle - up;
  }
  return (
    <div className="chart returns-chart">
      <h3>{copy.returnsChart}</h3>
      <ul className="legend">
        <li>
          <i className="swatch series-1" aria-hidden="true" />
          {copy.returnsPortfolio}
        </li>
        <li>
          <i className="swatch benchmark" aria-hidden="true" />
          {copy.returnsCdi}
        </li>
      </ul>
      <div className="returns-plot">
        <svg
          viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
          role="img"
          aria-label={`${copy.returnsChart}: ${copy.returnsPortfolio} ${percent(last.portfolio)}, ${copy.returnsCdi} ${percent(last.cdi)}`}
          onPointerMove={(event) => {
            const box = event.currentTarget.getBoundingClientRect();
            const ratio =
              ((event.clientX - box.left) / box.width) * WIDTH - PAD.left;
            const index = Math.round(
              (ratio / (WIDTH - PAD.left - PAD.right)) * (series.length - 1),
            );
            setHover(Math.max(0, Math.min(series.length - 1, index)));
          }}
          onPointerLeave={() => setHover(undefined)}
        >
          <line
            className="returns-zero"
            x1={PAD.left}
            x2={WIDTH - PAD.right}
            y1={y(0)}
            y2={y(0)}
          />
          <polyline className="returns-cdi" points={path((p) => p.cdi)} />
          <polyline
            className="returns-portfolio"
            points={path((p) => p.portfolio)}
          />
          <text
            className="returns-label"
            x={WIDTH - PAD.right + 8}
            y={portfolioY}
          >
            {copy.returnsPortfolio} {percent(last.portfolio)}
          </text>
          <text className="returns-label" x={WIDTH - PAD.right + 8} y={cdiY}>
            {copy.returnsCdi} {percent(last.cdi)}
          </text>
          <text className="returns-axis" x={PAD.left} y={HEIGHT - 6}>
            {formatDate(series[0].day, locale)}
          </text>
          <text
            className="returns-axis"
            x={WIDTH - PAD.right}
            y={HEIGHT - 6}
            textAnchor="end"
          >
            {formatDate(last.day, locale)}
          </text>
          {point && hover !== undefined && (
            <g>
              <line
                className="returns-cursor"
                x1={x(hover)}
                x2={x(hover)}
                y1={PAD.top}
                y2={HEIGHT - PAD.bottom}
              />
              <circle
                className="returns-portfolio-dot"
                cx={x(hover)}
                cy={y(Number(point.portfolio))}
                r={4}
              />
              <circle
                className="returns-cdi-dot"
                cx={x(hover)}
                cy={y(Number(point.cdi))}
                r={4}
              />
            </g>
          )}
        </svg>
        {point && hover !== undefined && (
          <span
            className="returns-tooltip"
            style={{ left: `${(x(hover) / WIDTH) * 100}%` }}
            aria-hidden="true"
          >
            <b>{formatDate(point.day, locale)}</b>
            <span>
              {copy.returnsPortfolio}: {percent(point.portfolio)}
            </span>
            <span>
              {copy.returnsCdi}: {percent(point.cdi)}
            </span>
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
                <th scope="col" className="numeric">
                  {copy.returnsPortfolio}
                </th>
                <th scope="col" className="numeric">
                  {copy.returnsCdi}
                </th>
              </tr>
            </thead>
            <tbody>
              {months.map((entry) => (
                <tr key={entry.day}>
                  <th scope="row">{formatDate(entry.day, locale)}</th>
                  <td className="numeric">{percent(entry.portfolio)}</td>
                  <td className="numeric">{percent(entry.cdi)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
    </div>
  );
}
