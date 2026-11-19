import type { ReactNode } from "react";
import { formatDate, formatMoney, messages, type Locale } from "./locale";
import {
  categoryComparison,
  change,
  currencies,
  monthlyInvestments,
  monthlyTotals,
  type HistoryRow,
  type InvestmentRow,
  type MonthTotal,
} from "./spending-history";

type Props = { rows: HistoryRow[]; month: string; locale: Locale };

function monthLabel(month: string, locale: Locale, long = false) {
  return new Intl.DateTimeFormat(locale, {
    month: long ? "long" : "short",
    year: long ? "numeric" : "2-digit",
    timeZone: "UTC",
  }).format(new Date(`${month}-01T00:00:00Z`));
}

function ChangeText({
  current,
  previous,
  locale,
}: {
  current: number;
  previous: number;
  locale: Locale;
}) {
  const ratio = change(current, previous);
  if (ratio === null) return <>—</>;
  const percent = new Intl.NumberFormat(locale, {
    style: "percent",
    signDisplay: "exceptZero",
    maximumFractionDigits: 0,
  }).format(ratio);
  return (
    <>
      <span aria-hidden="true">{ratio > 0 ? "▲ " : ratio < 0 ? "▼ " : ""}</span>
      {percent}
    </>
  );
}

export function MonthOverview({
  rows,
  month,
  locale,
  children,
}: Props & { children?: ReactNode }) {
  const copy = messages[locale];
  const number = new Intl.NumberFormat(locale);
  return (
    <div className="summary">
      {currencies(rows).map((currency) => {
        const [previous, current] = monthlyTotals(rows, currency, month, 2);
        const money = (value: number) =>
          formatMoney(String(value), currency, locale);
        return (
          <div key={currency}>
            <span>
              {copy.monthSpending} · {currency}
            </span>
            <strong>{money(current.total)}</strong>
            <small>
              <ChangeText
                current={current.total}
                previous={previous.total}
                locale={locale}
              />{" "}
              {copy.vsPreviousMonth} ({money(previous.total)})
            </small>
            <dl className="breakdown">
              <dt>
                <i className="swatch bank" aria-hidden="true" />
                {copy.bankDebits}
              </dt>
              <dd>{money(current.bank)}</dd>
              <dt>
                <i className="swatch card" aria-hidden="true" />
                {copy.cardPurchases}
              </dt>
              <dd>{money(current.card)}</dd>
              {current.pending !== 0 && (
                <>
                  <dt>
                    <i className="swatch pending" aria-hidden="true" />
                    {copy.pendingCard}
                  </dt>
                  <dd>{money(current.pending)}</dd>
                </>
              )}
            </dl>
            <small>
              {number.format(current.entries)}{" "}
              {current.entries === 1 ? copy.expenseEntry : copy.expenseEntries}
            </small>
          </div>
        );
      })}
      {children}
    </div>
  );
}

function Legend({ locale }: { locale: Locale }) {
  const copy = messages[locale];
  return (
    <ul className="legend">
      <li>
        <i className="swatch bank" aria-hidden="true" />
        {copy.bankDebits}
      </li>
      <li>
        <i className="swatch card" aria-hidden="true" />
        {copy.cardPurchases}
      </li>
      <li>
        <i className="swatch pending" aria-hidden="true" />
        {copy.pendingCard}
      </li>
    </ul>
  );
}

export function MonthlyComparison({
  rows,
  month,
  locale,
  onSelect,
  disabled,
}: Props & { onSelect: (month: string) => void; disabled: boolean }) {
  const copy = messages[locale];
  return (
    <>
      <p>{copy.monthlyComparisonHelp}</p>
      <Legend locale={locale} />
      {currencies(rows).map((currency) => {
        const months = monthlyTotals(rows, currency, month, 13);
        const shown = months.slice(1);
        const max = Math.max(1, ...shown.map((entry) => entry.total));
        const money = (value: number) =>
          formatMoney(String(value), currency, locale);
        const describe = (entry: MonthTotal) =>
          `${monthLabel(entry.month, locale, true)}: ${copy.total} ${money(entry.total)}, ` +
          `${copy.bankDebits} ${money(entry.bank)}, ${copy.cardPurchases} ${money(entry.card)}` +
          (entry.pending
            ? `, ${copy.pendingCard} ${money(entry.pending)}`
            : "");
        return (
          <div className="chart" key={currency}>
            <h3>{currency}</h3>
            <div className="month-chart">
              {shown.map((entry) => (
                <button
                  type="button"
                  key={entry.month}
                  className="month-column"
                  aria-pressed={entry.month === month}
                  aria-label={describe(entry)}
                  disabled={disabled}
                  onClick={() => onSelect(entry.month)}
                >
                  <span className="month-tooltip" aria-hidden="true">
                    <b>{monthLabel(entry.month, locale, true)}</b>
                    <span>
                      {copy.bankDebits}: {money(entry.bank)}
                    </span>
                    <span>
                      {copy.cardPurchases}: {money(entry.card)}
                    </span>
                    {entry.pending !== 0 && (
                      <span>
                        {copy.pendingCard}: {money(entry.pending)}
                      </span>
                    )}
                    <b>
                      {copy.total}: {money(entry.total)}
                    </b>
                  </span>
                  <span className="month-plot" aria-hidden="true">
                    <span
                      className="month-stack"
                      style={{
                        height: `${(Math.max(0, entry.total) / max) * 100}%`,
                      }}
                    >
                      <span
                        className="swatch pending"
                        style={{ flexGrow: Math.max(0, entry.pending) }}
                      />
                      <span
                        className="swatch card"
                        style={{
                          flexGrow: Math.max(0, entry.card - entry.pending),
                        }}
                      />
                      <span
                        className="swatch bank"
                        style={{ flexGrow: Math.max(0, entry.bank) }}
                      />
                    </span>
                  </span>
                  <span className="month-label" aria-hidden="true">
                    {monthLabel(entry.month, locale)}
                  </span>
                </button>
              ))}
            </div>
            <details>
              <summary>{copy.showTable}</summary>
              <div className="table-wrap">
                <table className="investment-table">
                  <thead>
                    <tr>
                      <th scope="col">{copy.month}</th>
                      <th scope="col" className="numeric">
                        {copy.bankDebits}
                      </th>
                      <th scope="col" className="numeric">
                        {copy.cardPurchases}
                      </th>
                      <th scope="col" className="numeric">
                        {copy.pendingCard}
                      </th>
                      <th scope="col" className="numeric">
                        {copy.total}
                      </th>
                      <th scope="col" className="numeric">
                        {copy.vsPreviousMonth}
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {shown
                      .map((entry, index) => ({
                        entry,
                        previous: months[index].total,
                      }))
                      .reverse()
                      .map(({ entry, previous }) => (
                        <tr key={entry.month}>
                          <th scope="row">
                            {monthLabel(entry.month, locale, true)}
                          </th>
                          <td className="numeric">{money(entry.bank)}</td>
                          <td className="numeric">{money(entry.card)}</td>
                          <td className="numeric">{money(entry.pending)}</td>
                          <td className="numeric">{money(entry.total)}</td>
                          <td className="numeric">
                            <ChangeText
                              current={entry.total}
                              previous={previous}
                              locale={locale}
                            />
                          </td>
                        </tr>
                      ))}
                  </tbody>
                </table>
              </div>
            </details>
          </div>
        );
      })}
    </>
  );
}

export function CategoryComparison({ rows, month, locale }: Props) {
  const copy = messages[locale];
  return (
    <>
      <ul className="legend">
        <li>
          <i className="swatch bank" aria-hidden="true" />
          {monthLabel(month, locale, true)}
        </li>
        <li>
          <i className="swatch previous" aria-hidden="true" />
          {copy.previousMonth}
        </li>
      </ul>
      {currencies(rows).map((currency) => {
        const entries = categoryComparison(rows, currency, month);
        if (!entries.length) return null;
        const max = Math.max(
          1,
          ...entries.flatMap((row) => [row.current, row.previous]),
        );
        const money = (value: number) =>
          formatMoney(String(value), currency, locale);
        const width = (value: number) => `${(Math.max(0, value) / max) * 100}%`;
        return (
          <div className="chart" key={currency}>
            <h3>{currency}</h3>
            {entries.map((row) => (
              <div
                className="compare"
                key={row.category}
                title={`${copy.previousMonth}: ${money(row.previous)}`}
              >
                <span>{row.category}</span>
                <span className="compare-bars" aria-hidden="true">
                  <i
                    className="swatch bank"
                    style={{ width: width(row.current) }}
                  />
                  <i
                    className="swatch previous"
                    style={{ width: width(row.previous) }}
                  />
                </span>
                <span>
                  {money(row.current)}
                  <small>
                    {copy.previousMonth}: {money(row.previous)}
                  </small>
                </span>
                <span>
                  <ChangeText
                    current={row.current}
                    previous={row.previous}
                    locale={locale}
                  />
                </span>
              </div>
            ))}
          </div>
        );
      })}
    </>
  );
}

type InvestmentProps = { rows: InvestmentRow[]; month: string; locale: Locale };

function investmentCurrencies(rows: InvestmentRow[]) {
  return [...new Set(rows.map((row) => row.currency))].sort();
}

export function InvestmentOverview({ rows, month, locale }: InvestmentProps) {
  const copy = messages[locale];
  return investmentCurrencies(rows).map((currency) => {
    const [previous, current] = monthlyInvestments(rows, currency, month, 2);
    const money = (value: number) =>
      formatMoney(String(value), currency, locale);
    return (
      <div key={`investments-${currency}`}>
        <span>
          {copy.netInvested} · {currency}
        </span>
        <strong>{money(current.net)}</strong>
        <small>
          {money(previous.net)} {copy.inPreviousMonth}
        </small>
        <dl className="breakdown">
          <dt>{copy.contributions}</dt>
          <dd>{money(current.contribution)}</dd>
          <dt>{copy.withdrawals}</dt>
          <dd>{money(current.withdrawal)}</dd>
          <dt>{copy.investmentIncome}</dt>
          <dd>{money(current.income)}</dd>
        </dl>
      </div>
    );
  });
}

export function InvestmentComparison({
  rows,
  month,
  locale,
  onSelect,
  disabled,
}: InvestmentProps & { onSelect: (month: string) => void; disabled: boolean }) {
  const copy = messages[locale];
  return (
    <>
      <p>{copy.investmentComparisonHelp}</p>
      {investmentCurrencies(rows).map((currency) => {
        const months = monthlyInvestments(rows, currency, month);
        const max = Math.max(1, ...months.map((entry) => Math.abs(entry.net)));
        const money = (value: number) =>
          formatMoney(String(value), currency, locale);
        const height = (value: number) =>
          `${(Math.max(0, value) / max) * 100}%`;
        return (
          <div className="chart" key={currency}>
            <h3>{currency}</h3>
            <div className="month-chart">
              {months.map((entry) => (
                <button
                  type="button"
                  key={entry.month}
                  className="month-column flow-column"
                  aria-pressed={entry.month === month}
                  aria-label={
                    `${monthLabel(entry.month, locale, true)}: ${copy.netInvested} ${money(entry.net)}, ` +
                    `${copy.contributions} ${money(entry.contribution)}, ` +
                    `${copy.withdrawals} ${money(entry.withdrawal)}, ` +
                    `${copy.investmentIncome} ${money(entry.income)}`
                  }
                  disabled={disabled}
                  onClick={() => onSelect(entry.month)}
                >
                  <span className="month-tooltip" aria-hidden="true">
                    <b>{monthLabel(entry.month, locale, true)}</b>
                    <span>
                      {copy.contributions}: {money(entry.contribution)}
                    </span>
                    <span>
                      {copy.withdrawals}: {money(entry.withdrawal)}
                    </span>
                    <span>
                      {copy.investmentIncome}: {money(entry.income)}
                    </span>
                    <b>
                      {copy.netInvested}: {money(entry.net)}
                    </b>
                  </span>
                  <span className="flow-plot" aria-hidden="true">
                    <span className="flow-half">
                      <i
                        className="swatch invested"
                        style={{ height: height(entry.net) }}
                      />
                    </span>
                    <span className="flow-half negative">
                      <i
                        className="swatch invested"
                        style={{ height: height(-entry.net) }}
                      />
                    </span>
                  </span>
                  <span className="month-label" aria-hidden="true">
                    {monthLabel(entry.month, locale)}
                  </span>
                </button>
              ))}
            </div>
            <details>
              <summary>{copy.showTable}</summary>
              <div className="table-wrap">
                <table className="investment-table">
                  <thead>
                    <tr>
                      <th scope="col">{copy.month}</th>
                      <th scope="col" className="numeric">
                        {copy.contributions}
                      </th>
                      <th scope="col" className="numeric">
                        {copy.withdrawals}
                      </th>
                      <th scope="col" className="numeric">
                        {copy.netInvested}
                      </th>
                      <th scope="col" className="numeric">
                        {copy.investmentIncome}
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {[...months].reverse().map((entry) => (
                      <tr key={entry.month}>
                        <th scope="row">
                          {monthLabel(entry.month, locale, true)}
                        </th>
                        <td className="numeric">{money(entry.contribution)}</td>
                        <td className="numeric">{money(entry.withdrawal)}</td>
                        <td className="numeric">{money(entry.net)}</td>
                        <td className="numeric">{money(entry.income)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </details>
          </div>
        );
      })}
    </>
  );
}

export type InvestedRow = {
  currency: string;
  source: "positions" | "savings_boxes";
  total: string;
  observed_on: string;
};

export function InvestedTotal({
  rows,
  locale,
}: {
  rows: InvestedRow[];
  locale: Locale;
}) {
  const copy = messages[locale];
  return [...new Set(rows.map((row) => row.currency))].map((currency) => {
    const own = rows.filter((row) => row.currency === currency);
    const amount = (source: InvestedRow["source"]) =>
      own
        .filter((row) => row.source === source)
        .reduce((sum, row) => sum + Number(row.total), 0);
    const money = (value: number) =>
      formatMoney(String(value), currency, locale);
    const latest =
      own
        .map((row) => row.observed_on)
        .sort()
        .at(-1) ?? "";
    return (
      <div key={`invested-${currency}`}>
        <span>
          {copy.totalInvested} · {currency}
        </span>
        <strong>{money(amount("positions") + amount("savings_boxes"))}</strong>
        <small>
          {copy.latestBalance} {formatDate(latest, locale)}
        </small>
        <dl className="breakdown">
          <dt>{copy.investmentPositions}</dt>
          <dd>{money(amount("positions"))}</dd>
          <dt>{copy.savingsBoxes}</dt>
          <dd>{money(amount("savings_boxes"))}</dd>
        </dl>
      </div>
    );
  });
}
