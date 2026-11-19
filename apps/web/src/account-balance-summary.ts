const scale = 10n ** 12n;

export function summarizeBankBalances(
  accounts: {
    type: string | null;
    currency: string | null;
    balance: string | null;
  }[],
) {
  const totals = new Map<string, bigint>();
  let unavailable = 0;
  for (const { type, currency, balance } of accounts) {
    if (type !== "BANK") continue;
    const decimal = balance?.match(/^(-?)(\d+)(?:\.(\d{1,12}))?$/);
    if (!decimal || !currency) {
      unavailable++;
      continue;
    }
    const [, sign, whole, fraction = ""] = decimal;
    const units = BigInt(whole) * scale + BigInt(fraction.padEnd(12, "0"));
    totals.set(
      currency,
      (totals.get(currency) ?? 0n) + (sign ? -units : units),
    );
  }
  return {
    unavailable,
    totals: Array.from(totals, ([currency, units]) => {
      const absolute = units < 0n ? -units : units;
      const fraction = (absolute % scale).toString().padStart(12, "0");
      return {
        currency,
        balance: `${units < 0n ? "-" : ""}${absolute / scale}.${fraction}`,
      };
    }).sort((a, b) => a.currency.localeCompare(b.currency)),
  };
}
