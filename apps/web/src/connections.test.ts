import assert from "node:assert/strict";
import { test } from "node:test";
import { visibleConnections } from "./connections.ts";

test("imported connections hide the demo without removing it from synthetic-only views", () => {
  const demo = { id: "demo", is_demo: true };
  const imported = { id: "imported", is_demo: false };
  assert.deepEqual(visibleConnections([demo, imported]), [imported]);
  assert.deepEqual(visibleConnections([demo]), [demo]);
  assert.deepEqual(visibleConnections([]), []);
});
