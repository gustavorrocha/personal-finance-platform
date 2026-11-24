import assert from "node:assert/strict";
import test from "node:test";
import {
  categoryComparison,
  cumulative,
  usualPace,
  monthlyInvestments,
  change,
  monthlyTotals,
  previousMonth,
  type HistoryRow,
} from "./spending-history.ts";

const row = (
  month: string,
  source: HistoryRow["source"],
  status: HistoryRow["status"],
  category: string,
  total: string,
): HistoryRow => ({
  month,
  currency: "BRL",
  source,
  status,
  category,
  total,
  entries: 1,
});

const rows = [
  row("2024-01", "bank", "POSTED", "Groceries", "20"),
  row("2024-01", "card", "POSTED", "Groceries", "5"),
  row("2023-12", "card", "POSTED", "Travel", "40"),
  row("2024-01", "card", "PENDING", "Travel", "8"),
  { ...row("2024-01", "bank", "POSTED", "Groceries", "99"), currency: "USD" },
];

test("month arithmetic crosses year boundaries", () => {
  assert.equal(previousMonth("2024-01"), "2023-12");
  assert.equal(previousMonth("2024-01", 13), "2022-12");
});

test("monthly totals combine bank and card, keep pending visible, and fill gaps", () => {
  const totals = monthlyTotals(rows, "BRL", "2024-01", 3);
  assert.deepEqual(
    totals.map((month) => month.month),
    ["2023-11", "2023-12", "2024-01"],
  );
  assert.equal(totals[0].total, 0);
  assert.deepEqual(totals[2], {
    month: "2024-01",
    bank: 20,
    card: 13,
    pending: 8,
    total: 33,
    entries: 3,
  });
});

test("categories compare the month with the previous one", () => {
  assert.deepEqual(categoryComparison(rows, "BRL", "2024-01"), [
    { category: "Groceries", current: 25, previous: 0, subcategories: [] },
    { category: "Travel", current: 8, previous: 40, subcategories: [] },
  ]);
  const nested = [
    {
      ...row("2024-01", "card", "POSTED", "Food", "10"),
      subcategory: "Delivery",
    },
    { ...row("2024-01", "card", "POSTED", "Food", "4"), subcategory: "" },
    {
      ...row("2023-12", "card", "POSTED", "Food", "6"),
      subcategory: "Delivery",
    },
  ];
  assert.deepEqual(categoryComparison(nested, "BRL", "2024-01"), [
    {
      category: "Food",
      current: 14,
      previous: 6,
      subcategories: [
        { category: "Delivery", current: 10, previous: 6 },
        { category: "", current: 4, previous: 0 },
      ],
    },
  ]);
  assert.equal(change(8, 40), -0.8);
  assert.equal(change(25, 0), null);
});

test("investment months net contributions against withdrawals", () => {
  const flows = [
    {
      month: "2024-01",
      currency: "BRL",
      kind: "contribution",
      total: "100",
      entries: 2,
    },
    {
      month: "2024-01",
      currency: "BRL",
      kind: "withdrawal",
      total: "30",
      entries: 1,
    },
    {
      month: "2024-01",
      currency: "BRL",
      kind: "income",
      total: "1.5",
      entries: 3,
    },
  ] as const;
  assert.deepEqual(monthlyInvestments([...flows], "BRL", "2024-01", 2), [
    { month: "2023-12", contribution: 0, withdrawal: 0, income: 0, net: 0 },
    {
      month: "2024-01",
      contribution: 100,
      withdrawal: 30,
      income: 1.5,
      net: 70,
    },
  ]);
});

test("the month's pace accumulates by day against the previous months' average", () => {
  const rows = [
    { day: "2026-09-02", currency: "BRL", total: "100" },
    { day: "2026-09-30", currency: "BRL", total: "50" },
    { day: "2026-10-01", currency: "BRL", total: "300" },
    { day: "2026-11-03", currency: "BRL", total: "20" },
    { day: "2026-11-03", currency: "USD", total: "9" },
  ];
  const current = cumulative(rows, "BRL", "2026-11");
  assert.equal(current.length, 30);
  assert.deepEqual(current.slice(0, 4), [0, 0, 20, 20]);
  const { months, average } = usualPace(rows, "BRL", "2026-11");
  assert.equal(months, 2);
  // Day 1: (0 + 300) / 2; day 2: (100 + 300) / 2; day 30: (150 + 300) / 2.
  assert.deepEqual([average[0], average[1], average[29]], [150, 200, 225]);
});
