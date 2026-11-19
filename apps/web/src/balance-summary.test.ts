import assert from "node:assert/strict";
import { test } from "node:test";
import {
  summarizeBankBalances,
  summarizeInvestmentBalances,
} from "./balance-summary.ts";

test("bank totals preserve decimals and currencies while excluding cards and missing values", () => {
  const early = "2026-11-17T00:00:00.000000Z";
  const late = "2026-11-18T10:00:00.000000Z";
  const bank = (
    currency: string | null,
    balance: string | null,
    observed_at = late,
  ) => ({
    type: "BANK",
    currency,
    balance,
    observed_at,
  });
  assert.deepEqual(
    summarizeBankBalances([
      bank("BRL", "9007199254740993.01"),
      bank("BRL", "-0.000000000001", early),
      bank("USD", "-0.1"),
      bank("USD", null, early),
      bank(null, "5"),
      {
        type: "CREDIT",
        currency: "BRL",
        balance: "-50",
        observed_at: "2026-11-16T00:00:00.000000Z",
      },
    ]),
    {
      unavailable: 2,
      totals: [
        {
          currency: "BRL",
          balance: "9007199254740993.009999999999",
          oldest: early,
          newest: late,
        },
        {
          currency: "USD",
          balance: "-0.100000000000",
          oldest: late,
          newest: late,
        },
      ],
    },
  );
});

test("investment totals use net balances and flag positions with only a gross amount", () => {
  const observed_at = "2026-11-18T10:00:00.000000Z";
  const position = { currency: "BRL", gross_amount: "900", observed_at };
  const { totals, unavailable } = summarizeInvestmentBalances([
    { ...position, net_balance: "115.20" },
    { ...position, net_balance: null },
    { ...position, currency: "USD", net_balance: "10" },
  ]);
  assert.equal(unavailable, 1);
  assert.deepEqual(
    totals.map(({ currency, balance }) => [currency, balance]),
    [
      ["BRL", "115.200000000000"],
      ["USD", "10.000000000000"],
    ],
  );
});
