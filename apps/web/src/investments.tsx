import { summarizeInvestmentBalances } from "./balance-summary";
import { BalanceSummary } from "./balance-summary-view";
import {
  formatDate,
  formatReportedValue,
  investmentTypeLabel,
  messages,
  type Locale,
} from "./locale";
import { SnapshotView, type Snapshot } from "./snapshot";

type Position = {
  id: string;
  ticker: string | null;
  name: string | null;
  indexer_percentage: string | null;
  indexer: string | null;
  type: string | null;
  currency: string | null;
  net_balance: string | null;
  gross_amount: string | null;
  quantity: string | null;
  unit_price: string | null;
  reference_date: string | null;
  maturity_date: string | null;
  observed_at: string;
};
type InvestmentSnapshot = Snapshot & { positions: Position[] };

export function InvestmentsView({
  locale,
  nested = false,
}: {
  locale: Locale;
  nested?: boolean;
}) {
  const copy = messages[locale];
  const number = new Intl.NumberFormat(locale);
  const observed = new Intl.DateTimeFormat(locale, {
    dateStyle: "medium",
    timeStyle: "short",
    timeZone: "UTC",
  });

  function value(amount: string | null) {
    return formatReportedValue(amount, locale);
  }

  function date(day: string | null) {
    return day ? (
      <time dateTime={day}>{formatDate(day, locale)}</time>
    ) : (
      copy.unavailable
    );
  }

  return (
    <SnapshotView<InvestmentSnapshot>
      locale={locale}
      path="/api/investments"
      title={nested ? copy.reportedPositions : copy.investments}
      nested={nested}
      loadingText={copy.loadingInvestments}
      errorText={copy.investmentsError}
      emptyText={copy.noInvestments}
    >
      {({ positions, truncated }) => (
        <div className="panel">
          {positions.length === 0 ? (
            <p>{copy.noInvestments}</p>
          ) : (
            <>
              <p id="investment-help">{copy.investmentHelp}</p>
              {!truncated && (
                <BalanceSummary
                  summary={summarizeInvestmentBalances(positions)}
                  title={copy.reportedInvestmentTotals}
                  missingText={copy.incompleteInvestmentTotals}
                  locale={locale}
                  observed={observed}
                />
              )}
              <details>
                <summary>
                  {copy.investmentPositions} ({number.format(positions.length)})
                </summary>
                <div
                  className="table-wrap"
                  role="region"
                  aria-label={copy.investments}
                  tabIndex={0}
                >
                  <table
                    className="investment-table"
                    aria-describedby="investment-help"
                  >
                    <thead>
                      <tr>
                        <th scope="col">{copy.position}</th>
                        <th scope="col">{copy.investmentType}</th>
                        <th scope="col">{copy.remuneration}</th>
                        <th scope="col">{copy.netBalance}</th>
                        <th scope="col">{copy.grossAmount}</th>
                        <th scope="col">{copy.currency}</th>
                        <th scope="col">{copy.quantity}</th>
                        <th scope="col">{copy.unitPrice}</th>
                        <th scope="col">{copy.referenceDate}</th>
                        <th scope="col">{copy.maturityDate}</th>
                        <th scope="col">{copy.observedAt}</th>
                      </tr>
                    </thead>
                    <tbody>
                      {positions.map((row, index) => (
                        <tr key={row.id}>
                          <th scope="row">
                            {row.name ??
                              row.ticker ??
                              `${copy.position} ${number.format(index + 1)}`}
                          </th>
                          <td>{investmentTypeLabel(row.type, locale)}</td>
                          <td>
                            {row.indexer_percentage && row.indexer
                              ? `${number.format(Number(row.indexer_percentage))}% ${row.indexer}`
                              : copy.unavailable}
                          </td>
                          <td className="numeric">{value(row.net_balance)}</td>
                          <td className="numeric">{value(row.gross_amount)}</td>
                          <td>{row.currency ?? copy.unavailable}</td>
                          <td className="numeric">{value(row.quantity)}</td>
                          <td className="numeric">{value(row.unit_price)}</td>
                          <td>{date(row.reference_date)}</td>
                          <td>{date(row.maturity_date)}</td>
                          <td>
                            <time dateTime={row.observed_at}>
                              {observed.format(new Date(row.observed_at))}
                            </time>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </details>
            </>
          )}
          {truncated && <p>{copy.investmentLimit}</p>}
        </div>
      )}
    </SnapshotView>
  );
}
