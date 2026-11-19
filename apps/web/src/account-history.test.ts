import assert from "node:assert/strict";
import { afterEach, mock, test } from "node:test";
import { fetchAccountHistory } from "./account-history.ts";

afterEach(() => mock.restoreAll());

test("expanded history keeps the scope and requests the maximum supported limit", async () => {
  const signal = new AbortController().signal;
  const fetch = mock.method(globalThis, "fetch", async () =>
    Response.json({ observations: [], truncated: false }),
  );
  await fetchAccountHistory("item", "account", signal, 200);
  assert.deepEqual(fetch.mock.calls[0].arguments, [
    "/api/accounts/history?item=item&account=account&limit=200",
    { signal },
  ]);
});

test("account history requests only the selected connection and account", async () => {
  const signal = new AbortController().signal;
  const history = {
    observations: [
      { observed_at: "2026-11-19T00:00:00Z", balance: null, currency: "BRL" },
      { observed_at: "2026-11-18T00:00:00Z", balance: "0", currency: "BRL" },
    ],
    truncated: true,
  };
  const fetch = mock.method(globalThis, "fetch", async () =>
    Response.json(history),
  );
  assert.deepEqual(
    await fetchAccountHistory("item-1", "account-1", signal),
    history,
  );
  assert.deepEqual(fetch.mock.calls[0].arguments, [
    "/api/accounts/history?item=item-1&account=account-1",
    { signal },
  ]);
});

test("missing account history is distinct from a failed request", async () => {
  const signal = new AbortController().signal;
  const fetch = mock.method(
    globalThis,
    "fetch",
    async () => new Response(null, { status: 404 }),
  );
  assert.equal(await fetchAccountHistory("item", "account", signal), null);
  fetch.mock.mockImplementation(
    async () => new Response("private details", { status: 503 }),
  );
  await assert.rejects(fetchAccountHistory("item", "account", signal), {
    message: "Account history request failed",
  });
});
