import assert from "node:assert/strict";
import { test } from "node:test";
import {
  deviceLocale,
  formatDate,
  formatReportedValue,
  formatMoney,
  messages,
  monthChoices,
} from "./locale.ts";

test("localized interface templates preserve provider and user values verbatim", () => {
  assert.equal(
    messages["pt-BR"].categoryFor("Loja {date}", "19/11/2026"),
    "Categoria de Loja {date} em 19/11/2026",
  );
});

test("device language chooses the first supported browser preference", () => {
  assert.equal(deviceLocale(["pt-BR", "en-US"]), "pt-BR");
  assert.equal(deviceLocale(["en-GB", "pt-BR"]), "en-US");
  assert.equal(deviceLocale(["es", "pt-PT"]), "pt-BR");
  assert.equal(deviceLocale(["es-419"]), "en-US");
  assert.equal(deviceLocale([]), "en-US");
});

test("reported decimals keep their precision and distinguish zero from missing", () => {
  assert.equal(
    formatReportedValue("9007199254740993.000000000001", "en-US"),
    "9,007,199,254,740,993.000000000001",
  );
  assert.equal(
    formatReportedValue("-0.000000000001", "pt-BR"),
    "-0,000000000001",
  );
  assert.equal(formatReportedValue("0", "pt-BR"), "0");
  assert.equal(formatReportedValue(null, "pt-BR"), "Indisponível");
  assert.equal(
    formatReportedValue("9007199254740993.000000000001", "en-US", "USD"),
    "$9,007,199,254,740,993.000000000001",
  );
  assert.equal(formatReportedValue("0", "pt-BR", "BRL"), "R$\u00a00,00");
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
