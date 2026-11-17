import { mkdir, copyFile } from "node:fs/promises";
import { build } from "esbuild";

await mkdir("dist/assets", { recursive: true });
await build({
  entryPoints: ["src/main.tsx"],
  bundle: true,
  minify: true,
  outfile: "dist/assets/app.js",
  target: ["es2022"],
  define: { "process.env.NODE_ENV": '"production"' },
});
await copyFile("index.html", "dist/index.html");
