/**
 * Splits `cash` among investment classes without selling anything, so the portfolio ends
 * as close as possible to the target shares (least squares): the classes furthest below
 * their target get money first, until their gaps level out. Amounts come back in cents
 * and always add up to the cash.
 */
export function splitContribution(
  held: number[],
  targets: number[],
  cash: number,
): number[] {
  const total = held.reduce((sum, value) => sum + value, 0) + cash;
  const gaps = held.map(
    (value, index) => (targets[index] / 100) * total - value,
  );
  const sorted = [...gaps].sort((a, b) => b - a);
  // The water level: the largest k whose k-th gap stays above it.
  let level = Infinity;
  let sum = 0;
  sorted.forEach((gap, index) => {
    sum += gap;
    const candidate = (sum - cash) / (index + 1);
    if (gap > candidate) level = candidate;
  });
  const raw = gaps.map((gap) => (cash > 0 ? Math.max(0, gap - level) : 0));
  const cents = raw.map((value) => Math.floor(value * 100));
  let rest = Math.round(cash * 100) - cents.reduce((a, b) => a + b, 0);
  const byRemainder = raw
    .map((value, index) => ({ index, part: value * 100 - cents[index] }))
    .filter(({ index }) => raw[index] > 0)
    .sort((a, b) => b.part - a.part);
  for (let i = 0; rest > 0 && byRemainder.length > 0; i++, rest--)
    cents[byRemainder[i % byRemainder.length].index]++;
  return cents.map((value) => value / 100);
}
