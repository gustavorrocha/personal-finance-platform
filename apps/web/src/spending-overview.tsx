import { useState, type ReactNode } from "react";
import { formatDate, formatMoney, messages, type Locale } from "./locale";
import { Help } from "./ui";
import {
  categoryComparison,
  categoryMonths,
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
  end = month,
  locale,
  onSelect,
  disabled,
}: Props & {
  /** Last month on the axis; the selected month is highlighted inside it. */
  end?: string;
  onSelect: (month: string) => void;
  disabled: boolean;
}) {
  const copy = messages[locale];
  return (
    <>
      <Help label={copy.howItWorks}>{copy.monthlyComparisonHelp}</Help>
      <Legend locale={locale} />
      {currencies(rows).map((currency) => {
        const months = monthlyTotals(rows, currency, end, 13);
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

export function CategoryComparison({
  rows,
  month,
  locale,
  onSelect,
  disabled,
}: Props & {
  onSelect: (category: string, subcategory?: string) => void;
  disabled: boolean;
}) {
  const copy = messages[locale];
  // Categories whose subcategories are shown ("currency|category").
  const [open, setOpen] = useState<string[]>([]);
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
            {entries.map((group) => {
              const id = `${currency}|${group.category}`;
              const expanded = open.includes(id);
              return (
                <div className="category-block" key={group.category}>
                  {[
                    { ...group, parent: group.category, child: false },
                    ...(expanded ? group.subcategories : []).map((row) => ({
                      ...row,
                      parent: group.category,
                      child: true,
                    })),
                  ].map((row) => (
                    <div
                      className={row.child ? "compare child" : "compare"}
                      key={`${row.child}-${row.category}`}
                      title={`${copy.previousMonth}: ${money(row.previous)}`}
                    >
                      <span className="category-name">
                        {!row.child && group.subcategories.length > 0 && (
                          <button
                            type="button"
                            className="icon-button toggle"
                            aria-expanded={expanded}
                            aria-label={`${copy.subcategories}: ${row.category || copy.uncategorized}`}
                            onClick={() =>
                              setOpen((current) =>
                                expanded
                                  ? current.filter((value) => value !== id)
                                  : [...current, id],
                              )
                            }
                          >
                            {expanded ? "▾" : "▸"}
                          </button>
                        )}
                        <button
                          type="button"
                          className="link-button"
                          disabled={disabled}
                          aria-label={`${copy.showExpensesOf} ${
                            row.child
                              ? `${row.parent || copy.uncategorized} › ${row.category || copy.noSubcategory}`
                              : row.category || copy.uncategorized
                          }`}
                          onClick={() =>
                            row.child
                              ? onSelect(row.parent, row.category)
                              : onSelect(row.category)
                          }
                        >
                          {row.category ||
                            (row.child
                              ? copy.noSubcategory
                              : copy.uncategorized)}
                        </button>
                      </span>
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
  end = month,
  locale,
  onSelect,
  disabled,
}: InvestmentProps & {
  end?: string;
  onSelect: (month: string) => void;
  disabled: boolean;
}) {
  const copy = messages[locale];
  return (
    <>
      <Help label={copy.howItWorks}>{copy.investmentComparisonHelp}</Help>
      {investmentCurrencies(rows).map((currency) => {
        const months = monthlyInvestments(rows, currency, end);
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

/** Invested money of one investment class ("" key: unclassified) at a month's end. */
export type InvestedPoint = {
  month: string;
  currency: string;
  key: string;
  name: string;
  total: string;
};
export type InvestedGap = { name: string; currency: string; amount: string };

// Categorical slots in fixed order; a seventh component folds into "Other".
const SERIES = 6;

/** Invested money at the end of each month, stacked by investment class. Stored daily
 * balances where they exist; earlier months walk back through reported movements. */
export function InvestedEvolution({
  rows,
  gaps,
  locale,
}: {
  rows: InvestedPoint[];
  gaps: InvestedGap[];
  locale: Locale;
}) {
  const copy = messages[locale];
  const [share, setShare] = useState(false);
  const label = (row: { key: string; name: string }) =>
    row.key ? row.name : copy.unclassifiedInvestment;
  const percent = new Intl.NumberFormat(locale, {
    style: "percent",
    maximumFractionDigits: 1,
  });
  return (
    <>
      <Help label={copy.howItWorks}>{copy.investedEvolutionHelp}</Help>
      <div className="returns-mode" role="group" aria-label={copy.chartMode}>
        <button
          type="button"
          aria-pressed={!share}
          onClick={() => setShare(false)}
        >
          {copy.amountsMode}
        </button>
        <button
          type="button"
          aria-pressed={share}
          onClick={() => setShare(true)}
        >
          {copy.allocationMode}
        </button>
      </div>
      {gaps.length > 0 && (
        <div className="notice" role="note">
          <p>
            <strong>{copy.investedGapsTitle}</strong> {copy.investedGapsHelp}
          </p>
          <ul>
            {gaps.map((gap) => (
              <li key={`${gap.name}-${gap.currency}`}>
                {gap.name}: {formatMoney(gap.amount, gap.currency, locale)}
              </li>
            ))}
          </ul>
        </div>
      )}
      {[...new Set(rows.map((row) => row.currency))].sort().map((currency) => {
        const own = rows.filter((row) => row.currency === currency);
        const months = [...new Set(own.map((row) => row.month))].sort();
        const keyOf = (row: InvestedPoint) => row.key;
        // Fixed order (classes by name, unclassified last) so a color always means the
        // same class, whatever the amounts.
        const order = new Map(own.map((row) => [row.key, label(row)]));
        const ranked = [...order.keys()].sort(
          (a, b) =>
            Number(!a) - Number(!b) ||
            (order.get(a) ?? "").localeCompare(order.get(b) ?? ""),
        );
        const slot = new Map(
          ranked.map((key, index) => [key, Math.min(index, SERIES - 1)]),
        );
        const names = new Map<number, string>();
        for (const row of own) {
          const index = slot.get(keyOf(row)) ?? 0;
          names.set(
            index,
            index === SERIES - 1 && ranked.length > SERIES
              ? copy.otherComponents
              : label(row),
          );
        }
        const series = [...names.entries()].sort(([a], [b]) => a - b);
        const totals = months.map((month) => {
          const values = new Array<number>(series.length).fill(0);
          for (const row of own.filter((entry) => entry.month === month))
            values[slot.get(keyOf(row)) ?? 0] += Number(row.total);
          return {
            month,
            values,
            total: values.reduce((sum, value) => sum + value, 0),
          };
        });
        const max = Math.max(1, ...totals.map((entry) => entry.total));
        const money = (value: number) =>
          formatMoney(String(value), currency, locale);
        return (
          <div className="chart" key={currency}>
            <h3>{currency}</h3>
            <ul className="legend">
              {series.map(([index, name]) => (
                <li key={index}>
                  <i
                    className={`swatch series-${index + 1}`}
                    aria-hidden="true"
                  />
                  {name}
                </li>
              ))}
            </ul>
            <div className="month-chart" role="list">
              {totals.map((entry) => (
                <div
                  className="month-column"
                  role="listitem"
                  key={entry.month}
                  aria-label={`${monthLabel(entry.month, locale, true)}: ${money(entry.total)}`}
                >
                  <span className="month-tooltip" aria-hidden="true">
                    <b>{monthLabel(entry.month, locale, true)}</b>
                    {series.map(([index, name]) =>
                      entry.values[index] ? (
                        <span key={index}>
                          {name}: {money(entry.values[index])} (
                          {percent.format(entry.values[index] / entry.total)})
                        </span>
                      ) : null,
                    )}
                    <b>
                      {copy.total}: {money(entry.total)}
                    </b>
                  </span>
                  <span className="month-plot" aria-hidden="true">
                    <span
                      className="month-stack"
                      style={{
                        height: share
                          ? entry.total > 0
                            ? "100%"
                            : 0
                          : `${(entry.total / max) * 100}%`,
                      }}
                    >
                      {[...series].reverse().map(([index]) => (
                        <span
                          key={index}
                          className={`swatch series-${index + 1}`}
                          style={{ flexGrow: entry.values[index] }}
                        />
                      ))}
                    </span>
                  </span>
                  <span className="month-label" aria-hidden="true">
                    {monthLabel(entry.month, locale)}
                  </span>
                </div>
              ))}
            </div>
            <details>
              <summary>{copy.showTable}</summary>
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th scope="col">{copy.month}</th>
                      {series.map(([index, name]) => (
                        <th scope="col" className="numeric" key={index}>
                          {name}
                        </th>
                      ))}
                      <th scope="col" className="numeric">
                        {copy.total}
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {totals.map((entry) => (
                      <tr key={entry.month}>
                        <th scope="row">
                          {monthLabel(entry.month, locale, true)}
                        </th>
                        {series.map(([index]) => (
                          <td className="numeric" key={index}>
                            {money(entry.values[index])}
                          </td>
                        ))}
                        <td className="numeric">{money(entry.total)}</td>
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

/** Categories down, months across; each cell shaded by its share of the largest one. */
export function CategoryMonthsTable({
  rows,
  month,
  end,
  locale,
  disabled,
  onSelect,
}: Props & {
  end: string;
  disabled: boolean;
  onSelect: (month: string, category: string, subcategory?: string) => void;
}) {
  const copy = messages[locale];
  const [open, setOpen] = useState<string[]>([]);
  const short = new Intl.NumberFormat(locale, { maximumFractionDigits: 0 });
  return currencies(rows).map((currency) => {
    const { months, categories } = categoryMonths(rows, currency, end);
    if (!categories.length) return null;
    const totals = months.map((_, index) =>
      categories.reduce((sum, row) => sum + row.values[index], 0),
    );
    const active = totals.filter((value) => value > 0).length;
    const max = Math.max(1, ...categories.flatMap((row) => row.values));
    const money = (value: number) =>
      formatMoney(String(value), currency, locale);
    return (
      <div className="chart" key={currency}>
        <h3>{currency}</h3>
        <div className="table-wrap">
          <table className="heatmap">
            <thead>
              <tr>
                <th scope="col">{copy.category}</th>
                {months.map((slot) => (
                  <th
                    scope="col"
                    key={slot}
                    className={slot === month ? "selected" : undefined}
                  >
                    {monthLabel(slot, locale)}
                  </th>
                ))}
                <th scope="col">{copy.monthlyAverage}</th>
              </tr>
            </thead>
            <tbody>
              {categories.flatMap((group) => {
                const id = `${currency}|${group.category}`;
                const expanded = open.includes(id);
                return [
                  { ...group, child: false },
                  ...(expanded ? group.subcategories : []).map((row) => ({
                    ...row,
                    subcategories: [],
                    child: true,
                  })),
                ].map((row) => {
                  const name =
                    row.category ||
                    (row.child ? copy.noSubcategory : copy.uncategorized);
                  return (
                    <tr
                      key={`${group.category}|${row.child}|${row.category}`}
                      className={row.child ? "child" : undefined}
                    >
                      <th scope="row">
                        {!row.child && group.subcategories.length > 0 && (
                          <button
                            type="button"
                            className="icon-button toggle"
                            aria-expanded={expanded}
                            aria-label={`${copy.subcategories}: ${name}`}
                            onClick={() =>
                              setOpen((current) =>
                                expanded
                                  ? current.filter((value) => value !== id)
                                  : [...current, id],
                              )
                            }
                          >
                            {expanded ? "▾" : "▸"}
                          </button>
                        )}
                        {name}
                      </th>
                      {row.values.map((value, index) => {
                        const share = value / max;
                        return (
                          <td
                            key={months[index]}
                            className={
                              months[index] === month ? "selected" : undefined
                            }
                          >
                            {value > 0 ? (
                              <button
                                type="button"
                                className={share > 0.55 ? "cell dark" : "cell"}
                                style={{
                                  background: `color-mix(in srgb, #2a78b5 ${Math.round(8 + share * 92)}%, transparent)`,
                                }}
                                title={`${name} · ${monthLabel(months[index], locale, true)}: ${money(value)}`}
                                aria-label={`${copy.showExpensesOf} ${name}, ${monthLabel(months[index], locale, true)}: ${money(value)}`}
                                disabled={disabled}
                                onClick={() =>
                                  row.child
                                    ? onSelect(
                                        months[index],
                                        group.category,
                                        row.category,
                                      )
                                    : onSelect(months[index], row.category)
                                }
                              >
                                {short.format(value)}
                              </button>
                            ) : (
                              <span className="cell empty">—</span>
                            )}
                          </td>
                        );
                      })}
                      <td className="average">
                        {short.format(row.total / Math.max(1, active))}
                      </td>
                    </tr>
                  );
                });
              })}
            </tbody>
            <tfoot>
              <tr>
                <th scope="row">{copy.total}</th>
                {totals.map((value, index) => (
                  <td
                    key={months[index]}
                    className={months[index] === month ? "selected" : undefined}
                  >
                    {value > 0 ? short.format(value) : "—"}
                  </td>
                ))}
                <td className="average">
                  {short.format(
                    totals.reduce((sum, value) => sum + value, 0) /
                      Math.max(1, active),
                  )}
                </td>
              </tr>
            </tfoot>
          </table>
        </div>
      </div>
    );
  });
}

// Named series before the rest folds into "Other".
const CATEGORY_SERIES = 7;

/** Monthly spending stacked by category; picking one splits it into subcategories. */
export function CategoryChart({
  rows,
  month,
  end,
  locale,
  disabled,
  onSelect,
}: Props & {
  end: string;
  disabled: boolean;
  onSelect: (month: string) => void;
}) {
  const copy = messages[locale];
  const [focus, setFocus] = useState<string>();
  const percent = new Intl.NumberFormat(locale, {
    style: "percent",
    maximumFractionDigits: 0,
  });
  return currencies(rows).map((currency) => {
    const { months, categories } = categoryMonths(rows, currency, end);
    if (!categories.length) return null;
    const focused = categories.find((row) => row.category === focus);
    const pieces = focused
      ? focused.subcategories.length
        ? focused.subcategories
        : [focused]
      : categories;
    const named = pieces.length > CATEGORY_SERIES + 1;
    const shown = named ? pieces.slice(0, CATEGORY_SERIES) : pieces;
    const rest = named ? pieces.slice(CATEGORY_SERIES) : [];
    const series = [
      ...shown.map((row, index) => ({
        name:
          row.category || (focused ? copy.noSubcategory : copy.uncategorized),
        key: row.category,
        swatch: `series-${index + 1}`,
        values: row.values,
      })),
      ...(rest.length
        ? [
            {
              name: copy.otherComponents,
              key: undefined,
              swatch: "other",
              values: months.map((_, index) =>
                rest.reduce((sum, row) => sum + row.values[index], 0),
              ),
            },
          ]
        : []),
    ];
    const totals = months.map((_, index) =>
      series.reduce((sum, entry) => sum + entry.values[index], 0),
    );
    const max = Math.max(1, ...totals);
    const money = (value: number) =>
      formatMoney(String(value), currency, locale);
    return (
      <div className="chart" key={currency}>
        {currencies(rows).length > 1 && <h3>{currency}</h3>}
        {focused && (
          <p>
            <button
              type="button"
              className="link-button"
              onClick={() => setFocus(undefined)}
            >
              ← {copy.allCategories}
            </button>{" "}
            <strong>{focused.category || copy.uncategorized}</strong>
          </p>
        )}
        <ul className="legend">
          {series.map((entry) => (
            <li key={entry.swatch}>
              <i className={`swatch ${entry.swatch}`} aria-hidden="true" />
              {!focused && entry.key !== undefined ? (
                <button
                  type="button"
                  className="link-button"
                  aria-label={`${copy.subcategories}: ${entry.name}`}
                  onClick={() => setFocus(entry.key)}
                >
                  {entry.name}
                </button>
              ) : (
                entry.name
              )}
            </li>
          ))}
        </ul>
        <div className="month-chart">
          {months.map((slot, index) => (
            <button
              type="button"
              key={slot}
              className="month-column"
              aria-pressed={slot === month}
              aria-label={`${monthLabel(slot, locale, true)}: ${money(totals[index])}`}
              disabled={disabled}
              onClick={() => onSelect(slot)}
            >
              <span className="month-tooltip" aria-hidden="true">
                <b>{monthLabel(slot, locale, true)}</b>
                {[...series]
                  .filter((entry) => entry.values[index] > 0)
                  .sort((a, b) => b.values[index] - a.values[index])
                  .map((entry) => (
                    <span key={entry.swatch} className="tooltip-row">
                      <i
                        className={`swatch ${entry.swatch}`}
                        aria-hidden="true"
                      />
                      {entry.name}: {money(entry.values[index])} (
                      {percent.format(entry.values[index] / totals[index])})
                    </span>
                  ))}
                <b>
                  {copy.total}: {money(totals[index])}
                </b>
              </span>
              <span className="month-plot" aria-hidden="true">
                <span
                  className="month-stack"
                  style={{ height: `${(totals[index] / max) * 100}%` }}
                >
                  {[...series].reverse().map((entry) => (
                    <span
                      key={entry.swatch}
                      className={`swatch ${entry.swatch}`}
                      style={{ flexGrow: entry.values[index] }}
                    />
                  ))}
                </span>
              </span>
              <span className="month-label" aria-hidden="true">
                {monthLabel(slot, locale)}
              </span>
            </button>
          ))}
        </div>
      </div>
    );
  });
}
