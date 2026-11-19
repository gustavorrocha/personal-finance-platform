const scale = 10n ** 12n;

export function summarizeBankBalances(
  accounts: {
    type: string | null;
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
  for (const { type, currency, balance, observed_at } of accounts) {
    if (type !== "BANK") continue;
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
