import assert from "node:assert/strict";
import { test } from "node:test";
import { connectionLabel, visibleConnections } from "./connections.ts";

test("imported connections hide the demo without removing it from synthetic-only views", () => {
  const demo = { id: "demo", is_demo: true };
  const imported = { id: "imported", is_demo: false };
  assert.deepEqual(visibleConnections([demo, imported]), [imported]);
  assert.deepEqual(visibleConnections([demo]), [demo]);
  assert.deepEqual(visibleConnections([]), []);
});

test("connections show the institution, numbered only when two share it", () => {
  const demo = { id: "demo", is_demo: true };
  const bank = { id: "a", is_demo: false, institution: "Bank A" };
  const card = { id: "b", is_demo: false, institution: "Bank B" };
  const card2 = { id: "c", is_demo: false, institution: "Bank B" };
  const unnamed = { id: "d", is_demo: false, institution: null };
  const all = [demo, bank, card, card2, unnamed];
  const label = (row: (typeof all)[number]) =>
    connectionLabel(all, row, "Connection", "Demo");
  assert.deepEqual(all.map(label), [
    "Demo",
    "Bank A",
    "Bank B 1",
    "Bank B 2",
    "Connection",
  ]);
});
