import type { BalanceTotals } from "./balance-summary";
import { formatReportedValue, messages, type Locale } from "./locale";

export function BalanceSummary({
  summary,
  title,
  missingText,
  locale,
  observed,
}: {
  summary: BalanceTotals;
  title: string;
  missingText: string;
  locale: Locale;
  observed: Intl.DateTimeFormat;
}) {
  const { totals, unavailable } = summary;
  if (totals.length === 0 && unavailable === 0) return null;
  const copy = messages[locale];
  return (
    <section aria-labelledby="balance-totals">
      <h3 id="balance-totals">{title}</h3>
      <dl>
        {totals.map(({ currency, balance, oldest, newest }) => (
          <div key={currency}>
            <dt>{currency}</dt>
            <dd>{formatReportedValue(balance, locale)}</dd>
            <dd>
              <small>
                {copy.observedAt}{" "}
                <time dateTime={oldest}>
                  {observed.format(new Date(oldest))}
                </time>
                {oldest !== newest && (
                  <>
                    {" – "}
                    <time dateTime={newest}>
                      {observed.format(new Date(newest))}
                    </time>
                  </>
                )}
              </small>
            </dd>
          </div>
        ))}
      </dl>
      {unavailable > 0 && <p>{missingText}</p>}
    </section>
  );
}
