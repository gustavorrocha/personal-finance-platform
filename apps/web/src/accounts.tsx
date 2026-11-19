import { AccountHistoryView } from "./account-history-view";
import { summarizeBankBalances } from "./account-balance-summary";
import {
  formatMoney,
  formatReportedValue,
  messages,
  type Locale,
} from "./locale";
import { SnapshotView, type Snapshot } from "./snapshot";

type Account = {
  id: string;
  type: string | null;
  balance: string | null;
  currency: string | null;
  observed_at: string;
};
type AccountSnapshot = Snapshot & { accounts: Account[] };

function BankBalanceSummary({
  accounts,
  locale,
  observed,
}: {
  accounts: Account[];
  locale: Locale;
  observed: Intl.DateTimeFormat;
}) {
  const { totals, unavailable } = summarizeBankBalances(accounts);
  if (totals.length === 0 && unavailable === 0) return null;
  const copy = messages[locale];
  return (
    <section aria-labelledby="bank-balances">
      <h3 id="bank-balances">{copy.reportedBankTotals}</h3>
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
      {unavailable > 0 && <p>{copy.incompleteBankTotals}</p>}
    </section>
  );
}

export function AccountsView({ locale }: { locale: Locale }) {
  const copy = messages[locale];
  const number = new Intl.NumberFormat(locale);
  const balance = new Intl.NumberFormat(locale, { maximumFractionDigits: 12 });
  const observed = new Intl.DateTimeFormat(locale, {
    dateStyle: "medium",
    timeStyle: "short",
    timeZone: "UTC",
  });

  function accountLabel(row: Account, index: number) {
    const type =
      row.type === "BANK"
        ? copy.bankAccount
        : row.type === "CREDIT"
          ? copy.creditCard
          : copy.account;
    return `${type} ${number.format(index + 1)}`;
  }

  return (
    <SnapshotView<AccountSnapshot>
      locale={locale}
      path="/api/accounts"
      title={copy.accounts}
      loadingText={copy.loadingAccounts}
      errorText={copy.accountsError}
      emptyText={copy.noAccounts}
    >
      {(snapshot) => (
        <>
          <section className="panel" aria-labelledby="balances">
            <h2 id="balances">{copy.reportedBalances}</h2>
            <p>{copy.balanceHelp}</p>
            {!snapshot.truncated && (
              <BankBalanceSummary
                accounts={snapshot.accounts}
                locale={locale}
                observed={observed}
              />
            )}
            {snapshot.accounts.length === 0 ? (
              <p>{copy.noAccounts}</p>
            ) : (
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th scope="col">{copy.account}</th>
                      <th scope="col">{copy.balance}</th>
                      <th scope="col">{copy.currency}</th>
                      <th scope="col">{copy.observedAt}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {snapshot.accounts.map((row, index) => (
                      <tr key={row.id}>
                        <th scope="row">{accountLabel(row, index)}</th>
                        <td>
                          {row.balance === null
                            ? copy.unavailable
                            : row.currency
                              ? formatMoney(row.balance, row.currency, locale)
                              : balance.format(Number(row.balance))}
                        </td>
                        <td>{row.currency || copy.unavailable}</td>
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
            )}
            {snapshot.truncated && <p>{copy.accountLimit}</p>}
          </section>
          {snapshot.selected && snapshot.accounts.length > 0 && (
            <AccountHistoryView
              key={snapshot.selected.id}
              item={snapshot.selected.id}
              locale={locale}
              choices={snapshot.accounts.map((row, index) => ({
                id: row.id,
                label: accountLabel(row, index),
              }))}
            />
          )}
        </>
      )}
    </SnapshotView>
  );
}
