const scale = 10n ** 12n;

function summarizeBalances(
  balances: {
    currency: string | null;
    balance: string | null;
    observed_at: string;
  }[],
) {
  const totals = new Map<
    string,
    { units: bigint; oldest: string; newest: string }
  >();
  let unavailable = 0;
  for (const { currency, balance, observed_at } of balances) {
    const decimal = balance?.match(/^(-?)(\d+)(?:\.(\d{1,12}))?$/);
    if (!decimal || !currency) {
      unavailable++;
      continue;
    }
    const [, sign, whole, fraction = ""] = decimal;
    const units = BigInt(whole) * scale + BigInt(fraction.padEnd(12, "0"));
    const total = totals.get(currency) ?? {
      units: 0n,
      oldest: observed_at,
      newest: observed_at,
    };
    total.units += sign ? -units : units;
    if (observed_at < total.oldest) total.oldest = observed_at;
    if (observed_at > total.newest) total.newest = observed_at;
    totals.set(currency, total);
  }
  return {
    unavailable,
    totals: Array.from(totals, ([currency, { units, oldest, newest }]) => {
      const absolute = units < 0n ? -units : units;
      const fraction = (absolute % scale).toString().padStart(12, "0");
      return {
        currency,
        oldest,
        newest,
        balance: `${units < 0n ? "-" : ""}${absolute / scale}.${fraction}`,
      };
    }).sort((a, b) => a.currency.localeCompare(b.currency)),
  };
}

type ReportedBalance = Parameters<typeof summarizeBalances>[0][number];
export type BalanceTotals = ReturnType<typeof summarizeBalances>;

export function summarizeBankBalances(
  accounts: (ReportedBalance & { type: string | null })[],
) {
  return summarizeBalances(
    accounts.filter((account) => account.type === "BANK"),
  );
}

export function summarizeInvestmentBalances(
  positions: (Omit<ReportedBalance, "balance"> & {
    net_balance: string | null;
  })[],
) {
  return summarizeBalances(
    positions.map(({ net_balance, currency, observed_at }) => ({
      balance: net_balance,
      currency,
      observed_at,
    })),
  );
}
