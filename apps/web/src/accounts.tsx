import { useState } from "react";
import { AccountHistoryView } from "./account-history-view";
import { summarizeBankBalances } from "./balance-summary";
import { BalanceSummary } from "./balance-summary-view";
import {
  formatMoney,
  formatReportedValue,
  messages,
  type Locale,
} from "./locale";
import { SnapshotView, type Snapshot } from "./snapshot";
import { Help } from "./ui";

type Account = {
  id: string;
  type: string | null;
  balance: string | null;
  currency: string | null;
  observed_at: string;
  name: string | null;
  number_suffix: string | null;
  brand: string | null;
  level: string | null;
  credit_limit: string | null;
  available_credit: string | null;
  minimum_payment: string | null;
  due_date: string | null;
  close_date: string | null;
  disabled: boolean;
};
type AccountSnapshot = Snapshot & { accounts: Account[] };

async function setDisabled(item: string, account: string, disabled: boolean) {
  const response = await fetch(`/api/accounts/${account}/disabled`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ item, disabled }),
    signal: AbortSignal.timeout(5000),
  });
  if (!response.ok) throw new Error();
}

export function AccountsView({ locale }: { locale: Locale }) {
  const copy = messages[locale];
  const number = new Intl.NumberFormat(locale);
  // Changes made on this page, shown before the next reload.
  const [toggled, setToggled] = useState(new Map<string, boolean>());
  const [busy, setBusy] = useState<string>();
  const [failed, setFailed] = useState(false);
  const observed = new Intl.DateTimeFormat(locale, {
    dateStyle: "medium",
    timeStyle: "short",
    timeZone: "UTC",
  });
  const day = new Intl.DateTimeFormat(locale, {
    day: "2-digit",
    month: "short",
    timeZone: "UTC",
  });
  const date = (value: string) => day.format(new Date(`${value}T00:00:00Z`));

  function typeLabel(row: Account) {
    return row.type === "BANK"
      ? copy.bankAccount
      : row.type === "CREDIT"
        ? copy.creditCard
        : copy.account;
  }

  function accountLabel(row: Account, index: number) {
    const name = row.name ?? `${typeLabel(row)} ${number.format(index + 1)}`;
    return row.number_suffix
      ? `${name} · ${copy.accountEnding.replace("{digits}", row.number_suffix)}`
      : name;
  }

  const isDisabled = (row: Account) => toggled.get(row.id) ?? row.disabled;

  async function toggle(item: string, row: Account) {
    const disabled = !isDisabled(row);
    setBusy(row.id);
    setFailed(false);
    try {
      await setDisabled(item, row.id, disabled);
      setToggled((current) => new Map(current).set(row.id, disabled));
    } catch {
      setFailed(true);
    } finally {
      setBusy(undefined);
    }
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
            <Help label={copy.howItWorks}>
              {copy.balanceHelp} {copy.disabledAccountsHelp}
            </Help>
            {!snapshot.truncated && (
              <BalanceSummary
                summary={summarizeBankBalances(
                  snapshot.accounts.filter((row) => !isDisabled(row)),
                )}
                title={copy.reportedBankTotals}
                missingText={copy.incompleteBankTotals}
                locale={locale}
                observed={observed}
              />
            )}
            {failed && <p role="alert">{copy.accountToggleError}</p>}
            {snapshot.accounts.length === 0 ? (
              <p>{copy.noAccounts}</p>
            ) : (
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th scope="col">{copy.account}</th>
                      <th scope="col">{copy.balanceOrBill}</th>
                      <th scope="col">{copy.creditLimit}</th>
                      <th scope="col">{copy.observedAt}</th>
                      <th scope="col">{copy.accountActive}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {snapshot.accounts.map((row, index) => {
                      const money = (value: string) =>
                        formatMoney(value, row.currency ?? "BRL", locale);
                      const disabled = isDisabled(row);
                      const label = accountLabel(row, index);
                      const terms = [
                        row.due_date &&
                          copy.creditDue.replace("{date}", date(row.due_date)),
                        row.close_date &&
                          copy.creditCloses.replace(
                            "{date}",
                            date(row.close_date),
                          ),
                        row.minimum_payment &&
                          copy.creditMinimum.replace(
                            "{amount}",
                            money(row.minimum_payment),
                          ),
                      ].filter(Boolean);
                      return (
                        <tr
                          key={row.id}
                          className={disabled ? "disabled" : undefined}
                        >
                          <th scope="row">
                            {label}
                            <div>
                              <small>
                                {[
                                  typeLabel(row),
                                  [row.brand, row.level]
                                    .filter(Boolean)
                                    .join(" "),
                                  disabled && copy.accountDisabled,
                                ]
                                  .filter(Boolean)
                                  .join(" · ")}
                              </small>
                            </div>
                          </th>
                          <td>
                            {formatReportedValue(
                              row.balance,
                              locale,
                              row.currency,
                            )}
                            {terms.length > 0 && (
                              <div>
                                <small>{terms.join(" · ")}</small>
                              </div>
                            )}
                          </td>
                          <td>
                            {row.credit_limit ? (
                              <>
                                {money(row.credit_limit)}
                                {row.available_credit && (
                                  <div>
                                    <small>
                                      {copy.creditAvailable.replace(
                                        "{amount}",
                                        money(row.available_credit),
                                      )}
                                    </small>
                                  </div>
                                )}
                              </>
                            ) : (
                              "—"
                            )}
                          </td>
                          <td>
                            <time dateTime={row.observed_at}>
                              {observed.format(new Date(row.observed_at))}
                            </time>
                          </td>
                          <td>
                            <input
                              type="checkbox"
                              checked={!disabled}
                              disabled={
                                busy !== undefined || !snapshot.selected
                              }
                              aria-label={copy.accountToggle.replace(
                                "{name}",
                                label,
                              )}
                              onChange={() =>
                                void toggle(snapshot.selected!.id, row)
                              }
                            />
                          </td>
                        </tr>
                      );
                    })}
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
