const scale = 10n ** 12n;

type ReferenceDates = {
  oldest: string | null;
  newest: string | null;
  missing: boolean;
};

function summarizeBalances(
  balances: {
    currency: string | null;
    balance: string | null;
    observed_at: string;
    reference_date?: string | null;
  }[],
) {
  const totals = new Map<
    string,
    {
      units: bigint;
      oldest: string;
      newest: string;
      referenceDates?: ReferenceDates;
    }
  >();
  let unavailable = 0;
  for (const { currency, balance, observed_at, reference_date } of balances) {
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
    if (reference_date !== undefined) {
      const dates = total.referenceDates ?? {
        oldest: null,
        newest: null,
        missing: false,
      };
      if (reference_date === null) dates.missing = true;
      else {
        if (!dates.oldest || reference_date < dates.oldest)
          dates.oldest = reference_date;
        if (!dates.newest || reference_date > dates.newest)
          dates.newest = reference_date;
      }
      total.referenceDates = dates;
    }
    totals.set(currency, total);
  }
  return {
    unavailable,
    totals: Array.from(
      totals,
      ([currency, { units, oldest, newest, referenceDates }]) => {
        const absolute = units < 0n ? -units : units;
        const fraction = (absolute % scale).toString().padStart(12, "0");
        return {
          currency,
          oldest,
          newest,
          ...(referenceDates ? { referenceDates } : {}),
          balance: `${units < 0n ? "-" : ""}${absolute / scale}.${fraction}`,
        };
      },
    ).sort((a, b) => a.currency.localeCompare(b.currency)),
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
    reference_date: string | null;
  })[],
) {
  return summarizeBalances(
    positions.map(({ net_balance, currency, observed_at, reference_date }) => ({
      balance: net_balance,
      currency,
      observed_at,
      reference_date,
    })),
  );
}
