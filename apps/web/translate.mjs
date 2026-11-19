import { execFileSync } from "node:child_process";
import { createHash } from "node:crypto";
import { readFileSync, writeFileSync } from "node:fs";

const args = process.argv.slice(2);
const check = args[0] === "--check";
const model = args[1];
if (
  !(check && args.length === 1) &&
  !(args[0] === "--model" && model && args.length === 2)
) {
  throw new Error("Use --check or --model <installed Ollama model>");
}

const source = JSON.parse(
  readFileSync(new URL("./src/messages.en-US.json", import.meta.url)),
);
const target = new URL("./src/messages.pt-BR.json", import.meta.url);
const previous = JSON.parse(readFileSync(target));
const placeholders = (value) =>
  (value.match(/\{\w+\}/g) ?? []).sort().join(",");
const valid = (english, translated) =>
  typeof translated === "string" &&
  translated.trim() !== "" &&
  placeholders(english) === placeholders(translated);
const result = { source: {}, messages: {} };
const pending = [];

for (const [key, value] of Object.entries(source)) {
  result.source[key] = createHash("sha256").update(value).digest("hex");
  if (
    previous.source[key] === result.source[key] &&
    valid(value, previous.messages[key])
  ) {
    result.messages[key] = previous.messages[key];
  } else {
    pending.push(key);
  }
}

if (
  check &&
  (pending.length ||
    Object.keys(previous.messages).length !== Object.keys(source).length ||
    Object.keys(previous.source).length !== Object.keys(source).length)
) {
  throw new Error(
    "Portuguese catalog is stale. Regenerate it with the local translator.",
  );
}

for (const key of pending) {
  const prompt = [
    "Translate this English interface string into Brazilian Portuguese.",
    "Keep any placeholders such as {merchant} exactly as written.",
    'Return only a JSON object with one string property named "translation".',
    JSON.stringify(source[key]),
  ].join("\n");
  const raw = execFileSync(
    "docker",
    [
      "exec",
      "-i",
      "personal-finance-ollama-1",
      "ollama",
      "run",
      "--hidethinking",
      "--format",
      "json",
      model,
    ],
    {
      input: prompt,
      encoding: "utf8",
      timeout: 120_000,
      stdio: ["pipe", "pipe", "ignore"],
    },
  );
  const { translation } = JSON.parse(raw);
  if (!valid(source[key], translation))
    throw new Error(`Invalid translation for ${key}`);
  result.messages[key] = translation;
}

if (!check) {
  result.messages = Object.fromEntries(
    Object.keys(source).map((key) => [key, result.messages[key]]),
  );
  writeFileSync(target, JSON.stringify(result, null, 2) + "\n");
}
