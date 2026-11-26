import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { createHash } from "node:crypto";
import {
  copyFileSync,
  mkdirSync,
  mkdtempSync,
  rmdirSync,
  rmSync,
  writeFileSync,
} from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { test } from "node:test";

test("the offline catalog check rejects stale, missing, and invalid translations", () => {
  const root = mkdtempSync(join(tmpdir(), "finance-translation-test-"));
  const data = join(root, "src");
  mkdirSync(data);
  try {
    const source = "Open report for {merchant}";
    const hash = createHash("sha256").update(source).digest("hex");
    copyFileSync(
      new URL("../translate.mjs", import.meta.url),
      join(root, "translate.mjs"),
    );
    writeFileSync(
      join(data, "messages.en-US.json"),
      JSON.stringify({ report: source }),
    );

    function check(
      sourceHashes: Record<string, string>,
      messages: Record<string, string>,
    ) {
      writeFileSync(
        join(data, "messages.pt-BR.json"),
        JSON.stringify({ source: sourceHashes, messages }),
      );
      return spawnSync(
        process.execPath,
        [join(root, "translate.mjs"), "--check"],
        {
          encoding: "utf8",
        },
      );
    }

    const valid = { report: "Abrir relatório de {merchant}" };
    assert.equal(check({ report: hash }, valid).status, 0);
    const stale = check({ report: "previous-source" }, valid);
    assert.equal(stale.status, 1);
    assert.match(stale.stderr, /report/);
    const missing = check({}, {});
    assert.equal(missing.status, 1);
    assert.match(missing.stderr, /report/);
    const invalid = check({ report: hash }, { report: "Abrir relatório" });
    assert.equal(invalid.status, 1);
    assert.match(invalid.stderr, /report/);
    const removed = check(
      { report: hash, old: hash },
      { ...valid, old: "Antigo" },
    );
    assert.equal(removed.status, 1);
    assert.match(removed.stderr, /old/);
  } finally {
    rmSync(join(data, "messages.en-US.json"), { force: true });
    rmSync(join(data, "messages.pt-BR.json"), { force: true });
    rmSync(join(root, "translate.mjs"), { force: true });
    rmdirSync(data);
    rmdirSync(root);
  }
});

test("translations keep their accents", async () => {
  const { messages } = (
    await import("./messages.pt-BR.json", { with: { type: "json" } })
  ).default;
  // A letter next to "?" means accents were lost to a non-UTF-8 write.
  const broken = Object.entries(messages as Record<string, string>).filter(
    ([, text]) => /\p{L}\?|\?\p{L}/u.test(text),
  );
  assert.deepEqual(broken, []);
});
