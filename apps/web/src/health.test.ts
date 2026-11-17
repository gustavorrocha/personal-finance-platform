import assert from "node:assert/strict";
import { afterEach, mock, test } from "node:test";
import { checkHealth } from "./health.ts";

afterEach(() => mock.restoreAll());

test("health requires a successful response with the Phase 0 contract", async () => {
  mock.method(globalThis, "fetch", async () =>
    Response.json({ status: "ok", phase: 0 }),
  );
  assert.equal(await checkHealth(), "Ambiente disponível");
});

test("a failed or unexpected response never reports a healthy stack", async () => {
  for (const response of [
    Response.json({ status: "ok" }),
    Response.json({ status: "ok", phase: 0 }, { status: 503 }),
  ]) {
    mock.method(globalThis, "fetch", async () => response);
    assert.match(await checkHealth(), /indisponível/);
    mock.restoreAll();
  }
});

test("network errors do not disclose their content", async () => {
  mock.method(globalThis, "fetch", async () => {
    throw new Error("synthetic-secret");
  });
  const result = await checkHealth();
  assert.match(result, /indisponível/);
  assert.ok(!result.includes("synthetic-secret"));
});
