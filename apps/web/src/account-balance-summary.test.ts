import assert from "node:assert/strict";
import { test } from "node:test";
import { summarizeBankBalances } from "./account-balance-summary.ts";

test("bank totals preserve decimals and currencies while excluding cards and missing values", () => {
  const bank = (currency: string | null, balance: string | null) => ({
    type: "BANK",
    currency,
    balance,
  });
  assert.deepEqual(
    summarizeBankBalances([
      bank("BRL", "9007199254740993.01"),
      bank("BRL", "-0.000000000001"),
      bank("USD", "-0.1"),
      bank("USD", null),
      bank(null, "5"),
      { type: "CREDIT", currency: "BRL", balance: "-50" },
    ]),
    {
      unavailable: 2,
      totals: [
        { currency: "BRL", balance: "9007199254740993.009999999999" },
        { currency: "USD", balance: "-0.100000000000" },
      ],
    },
  );
});
