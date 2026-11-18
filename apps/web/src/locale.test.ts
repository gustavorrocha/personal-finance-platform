import assert from "node:assert/strict";
import { test } from "node:test";
import {
  categoryLabel,
  deviceLocale,
  formatDate,
  formatMoney,
  monthChoices,
} from "./locale.ts";

test("device language chooses the first supported browser preference", () => {
  assert.equal(deviceLocale(["pt-BR", "en-US"]), "pt-BR");
  assert.equal(deviceLocale(["en-GB", "pt-BR"]), "en-US");
  assert.equal(deviceLocale(["es", "pt-PT"]), "pt-BR");
  assert.equal(deviceLocale(["es-419"]), "en-US");
  assert.equal(deviceLocale([]), "en-US");
});

test("Portuguese category labels leave saved identifiers available in English", () => {
  const translations = {
    Groceries: "Supermercado",
    Dining: "Alimentação fora de casa",
    Transport: "Transporte",
    Home: "Moradia",
    Shopping: "Compras",
    Health: "Saúde",
    Leisure: "Lazer",
    Uncategorized: "Sem categoria",
  };
  for (const [category, label] of Object.entries(translations)) {
    assert.equal(categoryLabel(category, "pt-BR"), label);
    assert.equal(categoryLabel(category, "en-US"), category);
  }
});

test("Brazilian formatting preserves the currency and calendar day", () => {
  assert.equal(formatMoney("257.03", "BRL", "pt-BR"), "R$\u00a0257,03");
  assert.match(formatMoney("257.03", "USD", "pt-BR"), /US\$\s257,03/);
  assert.equal(formatDate("2026-11-15", "pt-BR"), "15/11/2026");
  assert.deepEqual(monthChoices("pt-BR")[10], {
    value: "11",
    label: "novembro",
  });
  assert.deepEqual(monthChoices("en-US")[10], {
    value: "11",
    label: "November",
  });
});
