import { AccountHistoryView } from "./account-history-view";
import { summarizeBankBalances } from "./balance-summary";
import { BalanceSummary } from "./balance-summary-view";
import { formatReportedValue, messages, type Locale } from "./locale";
import { SnapshotView, type Snapshot } from "./snapshot";

type Account = {
  id: string;
  type: string | null;
  balance: string | null;
  currency: string | null;
  observed_at: string;
};
type AccountSnapshot = Snapshot & { accounts: Account[] };

export function AccountsView({ locale }: { locale: Locale }) {
  const copy = messages[locale];
  const number = new Intl.NumberFormat(locale);
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
              <BalanceSummary
                summary={summarizeBankBalances(snapshot.accounts)}
                title={copy.reportedBankTotals}
                missingText={copy.incompleteBankTotals}
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
                          {formatReportedValue(
                            row.balance,
                            locale,
                            row.currency,
                          )}
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
