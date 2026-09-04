#!/usr/bin/env node

import { existsSync, readFileSync, readdirSync } from "node:fs";
import { dirname, extname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { spawnSync } from "node:child_process";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const contract = JSON.parse(
  readFileSync(resolve(root, "brand/asset-contract.json"), "utf8"),
);

function fail(message) {
  throw new Error(`Brand asset contract: ${message}`);
}

if (contract.schema !== 3) fail("unsupported asset schema");

const expectedSources = new Set();
for (const source of contract.sources ?? []) {
  if (!source.id || !source.path || !source.viewBox)
    fail("every source needs id, path, and viewBox");
  const sourcePath = resolve(root, source.path);
  if (!sourcePath.startsWith(resolve(root, "brand/source/")))
    fail(`${source.path} is outside brand/source`);
  if (!existsSync(sourcePath) || extname(sourcePath) !== ".svg")
    fail(`${source.path} is not an SVG source`);
  const svg = readFileSync(sourcePath, "utf8");
  const rootElement = svg.match(/<svg\b[^>]*>/i)?.[0];
  if (!rootElement?.includes(`viewBox="${source.viewBox}"`))
    fail(`${source.path} does not use viewBox ${source.viewBox}`);
  if (
    !/<title\b[^>]*>[^<]+<\/title>/i.test(svg) ||
    !/<desc\b[^>]*>[^<]+<\/desc>/i.test(svg)
  ) {
    fail(`${source.path} needs accessible title and description`);
  }
  if (
    /<(?:script|foreignObject)\b/i.test(svg) ||
    /(?:href|src)\s*=\s*["'](?:https?:|\/\/)/i.test(svg)
  ) {
    fail(`${source.path} contains active or external content`);
  }
  expectedSources.add(source.path.replace("brand/source/", ""));
}
const actualSources = new Set(readdirSync(resolve(root, "brand/source")));
if (
  expectedSources.size !== actualSources.size ||
  [...expectedSources].some((source) => !actualSources.has(source))
) {
  fail("brand/source contains assets outside the canonical contract");
}
if (
  existsSync(resolve(root, "brand/proposals")) &&
  readdirSync(resolve(root, "brand/proposals")).length > 0
) {
  fail("brand/proposals must not contain superseded logo sources");
}
const expectedDerivatives = new Set(contract.derivatives ?? []);
const derivativeDirectory = resolve(root, "brand/derived");
const actualDerivatives = new Set(readdirSync(derivativeDirectory));
if (
  expectedDerivatives.size !== actualDerivatives.size ||
  [...expectedDerivatives].some((name) => !actualDerivatives.has(name))
) {
  fail("brand/derived contains assets outside the current consumer contract");
}
for (const name of expectedDerivatives) {
  if (!existsSync(resolve(derivativeDirectory, name)))
    fail(`missing derivative ${name}`);
}

const packageJson = JSON.parse(
  readFileSync(resolve(root, "frontend/package.json"), "utf8"),
);
const lock = JSON.parse(
  readFileSync(resolve(root, "frontend/package-lock.json"), "utf8"),
);
if (packageJson.dependencies?.["@fontsource-variable/inter"] !== "5.3.0")
  fail("Inter dependency is not exact");
if (
  lock.packages?.["node_modules/@fontsource-variable/inter"]?.version !==
  "5.3.0"
)
  fail("Inter lock version differs");
if (
  !existsSync(resolve(root, "brand/licenses/Inter-OFL.txt")) ||
  !readFileSync(resolve(root, "brand/licenses/Inter-OFL.txt"), "utf8").includes(
    "SIL OPEN FONT LICENSE",
  )
) {
  fail("Inter OFL license text is missing");
}
if (packageJson.dependencies?.lucide !== "0.468.0")
  fail("Lucide dependency is not exact");
if (lock.packages?.["node_modules/lucide"]?.version !== "0.468.0")
  fail("Lucide lock version differs");

for (const token of [
  "--lzug-color-brand-ink",
  "--lzug-color-status-success",
  "--lzug-color-data-1",
  "--lzug-font-family",
  "--lzug-touch-target-min",
  "--lzug-motion-normal",
]) {
  if (!readFileSync(resolve(root, "brand/tokens.css"), "utf8").includes(token))
    fail(`missing canonical token ${token}`);
}
if (
  !readFileSync(resolve(root, "frontend/src/taiga-adapter.css"), "utf8").includes(
    "--tui-background-accent-1",
  )
) {
  fail("Taiga adapter is incomplete");
}

const generation = spawnSync(
  process.execPath,
  [resolve(root, "scripts/generate_brand_assets.mjs"), "--check"],
  {
    cwd: root,
    encoding: "utf8",
  },
);
if (generation.status !== 0)
  fail(generation.stderr || generation.stdout || "derivative check failed");

console.log(
  `Brand asset contract valid: ${contract.sources.length} sources, ${expectedDerivatives.size} derivatives`,
);
