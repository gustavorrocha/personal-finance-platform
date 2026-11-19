export type HistoryRow = {
  month: string;
  currency: string;
  source: "bank" | "card";
  status: "POSTED" | "PENDING";
  category: string;
  subcategory?: string;
  total: string;
  entries: string | number;
};

export type MonthTotal = {
  month: string;
  bank: number;
  card: number;
  pending: number;
  total: number;
  entries: number;
};

export function previousMonth(month: string, offset = 1): string {
  const [year, value] = month.split("-").map(Number);
  const index = year * 12 + value - 1 - offset;
  return `${Math.floor(index / 12)}-${String((index % 12) + 1).padStart(2, "0")}`;
}

export function currencies(rows: HistoryRow[]): string[] {
  return [...new Set(rows.map((row) => row.currency))].sort();
}

/** One slot per month ending at `month`, so months without spending stay visible. */
export function monthlyTotals(
  rows: HistoryRow[],
  currency: string,
  month: string,
  length = 12,
): MonthTotal[] {
  return Array.from({ length }, (_, index) => {
    const slot = previousMonth(month, length - 1 - index);
    const total: MonthTotal = {
      month: slot,
      bank: 0,
      card: 0,
      pending: 0,
      total: 0,
      entries: 0,
    };
    for (const row of rows) {
      if (row.month !== slot || row.currency !== currency) continue;
      const amount = Number(row.total);
      total[row.source] += amount;
      if (row.status === "PENDING") total.pending += amount;
      total.total += amount;
      total.entries += Number(row.entries);
    }
    return total;
  });
}

type Comparison = { category: string; current: number; previous: number };

function byAmount(a: Comparison, b: Comparison) {
  return b.current - a.current || b.previous - a.previous;
}

/** Categories ("" when uncategorized), each with its subcategories, this month vs the previous. */
export function categoryComparison(
  rows: HistoryRow[],
  currency: string,
  month: string,
): (Comparison & { subcategories: Comparison[] })[] {
  const previous = previousMonth(month);
  const categories = new Map<
    string,
    Comparison & { children: Map<string, Comparison> }
  >();
  for (const row of rows) {
    if (row.currency !== currency) continue;
    const key =
      row.month === month
        ? "current"
        : row.month === previous
          ? "previous"
          : null;
    if (!key) continue;
    const amount = Number(row.total);
    const entry = categories.get(row.category) ?? {
      category: row.category,
      current: 0,
      previous: 0,
      children: new Map(),
    };
    entry[key] += amount;
    const name = row.subcategory ?? "";
    const child = entry.children.get(name) ?? {
      category: name,
      current: 0,
      previous: 0,
    };
    child[key] += amount;
    entry.children.set(name, child);
    categories.set(row.category, entry);
  }
  return [...categories.values()]
    .map(({ children, ...entry }) => ({
      ...entry,
      // Spending filed directly under the category has no subcategory name.
      subcategories:
        children.size === 1 && children.has("")
          ? []
          : [...children.values()].sort(byAmount),
    }))
    .sort(byAmount);
}

/** Relative change, or null when there is no prior spending to compare with. */
export function change(current: number, previous: number): number | null {
  return previous > 0 ? (current - previous) / previous : null;
}

export type InvestmentRow = {
  month: string;
  currency: string;
  kind: "contribution" | "withdrawal" | "income";
  total: string;
  entries: string | number;
};

export type MonthInvestment = {
  month: string;
  contribution: number;
  withdrawal: number;
  income: number;
  /** Money moved into investments minus money taken out; income stays separate. */
  net: number;
};

export function monthlyInvestments(
  rows: InvestmentRow[],
  currency: string,
  month: string,
  length = 12,
): MonthInvestment[] {
  return Array.from({ length }, (_, index) => {
    const slot = previousMonth(month, length - 1 - index);
    const total = {
      month: slot,
      contribution: 0,
      withdrawal: 0,
      income: 0,
      net: 0,
    };
    for (const row of rows) {
      if (row.month === slot && row.currency === currency)
        total[row.kind] += Number(row.total);
    }
    total.net = total.contribution - total.withdrawal;
    return total;
  });
}
