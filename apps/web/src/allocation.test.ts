import assert from "node:assert/strict";
import { test } from "node:test";
import { splitContribution } from "./allocation.ts";

test("cash goes to the classes furthest below target", () => {
  // 60/40 target, 700/300 held, 100 to invest: 660/440 is the target, so all of it goes to B.
  assert.deepEqual(splitContribution([700, 300], [60, 40], 100), [0, 100]);
});

test("enough cash reaches the targets exactly", () => {
  assert.deepEqual(
    splitContribution([100, 0, 0], [50, 25, 25], 100),
    [0, 50, 50],
  );
});

test("gaps are levelled when cash cannot close them", () => {
  // Targets 1/3 each of 400: B and C are 133.33 short; 30 is split evenly between them.
  assert.deepEqual(
    splitContribution([370, 0, 0], [100 / 3, 100 / 3, 100 / 3], 30),
    [0, 15, 15],
  );
});

test("classes over target or without one never receive money", () => {
  const split = splitContribution([500, 100, 50], [0, 50, 50], 99.99);
  assert.equal(split[0], 0);
  assert.equal(Math.round(split.reduce((a, b) => a + b, 0) * 100), 9999);
  assert.ok(split[2] > split[1]);
});

test("no cash, no contribution", () => {
  assert.deepEqual(splitContribution([10, 20], [50, 50], 0), [0, 0]);
});
