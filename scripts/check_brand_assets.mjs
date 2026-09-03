#!/usr/bin/env node

import { existsSync, readFileSync, readdirSync } from "node:fs";
import { dirname, extname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { spawnSync } from "node:child_process";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const contract = JSON.parse(
  readFileSync(resolve(root, "brand/asset-contract.json"), "utf8"),
);
const font = JSON.parse(
  readFileSync(resolve(root, "brand/font-contract.json"), "utf8"),
);
const icons = JSON.parse(
  readFileSync(resolve(root, "brand/icon-contract.json"), "utf8"),
);

function fail(message) {
  throw new Error(`Brand asset contract: ${message}`);
}

if (contract.schema !== 2) fail("unsupported asset schema");
if (contract.approval?.logo?.variant !== "B2b: Urkunde rechts oben") {
  fail("approved logo variant must be B2b: Urkunde rechts oben");
}
if (
  contract.approval?.logo?.issueComment !==
  "https://github.com/lxndrp/lzug/issues/568#issuecomment-5512076189"
) {
  fail("canonical logo approval link changed");
}
if (contract.approval?.font?.family !== "Inter")
  fail("approved font must be Inter");
if (
  contract.approval?.font?.issueComment !==
  "https://github.com/lxndrp/lzug/issues/568#issuecomment-5514030813"
) {
  fail("canonical font approval link changed");
}

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

for (const variant of ["light", "dark", "black", "white"]) {
  if (!contract.variants?.[variant]) fail(`missing ${variant} variant`);
  for (const family of ["logo-mark", "logo-horizontal"]) {
    const asset = resolve(root, `brand/derived/${family}-${variant}.svg`);
    if (!existsSync(asset)) fail(`missing ${family} ${variant} derivative`);
  }
}
for (const monochrome of ["black", "white"]) {
  for (const family of ["logo-mark", "logo-horizontal"]) {
    const svg = readFileSync(
      resolve(root, `brand/derived/${family}-${monochrome}.svg`),
      "utf8",
    );
    if (!svg.includes(contract.variants[monochrome].ink))
      fail(`${monochrome} ${family} is not truly monochrome`);
    if (
      svg.includes(contract.variants.light.accent) ||
      svg.includes(contract.variants.dark.accent)
    ) {
      fail(`${monochrome} ${family} contains a themed accent color`);
    }
  }
}

const packageJson = JSON.parse(
  readFileSync(resolve(root, "frontend/package.json"), "utf8"),
);
const lock = JSON.parse(
  readFileSync(resolve(root, "frontend/package-lock.json"), "utf8"),
);
if (packageJson.dependencies?.[font.package] !== font.packageVersion)
  fail("Inter dependency is not exact");
if (
  lock.packages?.[`node_modules/${font.package}`]?.version !==
  font.packageVersion
)
  fail("Inter lock version differs");
if (
  !existsSync(resolve(root, font.licenseFile)) ||
  !readFileSync(resolve(root, font.licenseFile), "utf8").includes(
    "SIL OPEN FONT LICENSE",
  )
) {
  fail("Inter OFL license text is missing");
}
if (packageJson.dependencies?.[icons.package] !== icons.version)
  fail("Lucide dependency is not exact");
if (lock.packages?.[`node_modules/${icons.package}`]?.version !== icons.version)
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
  !readFileSync(resolve(root, "brand/taiga-adapter.css"), "utf8").includes(
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
if (existsSync(resolve(root, "brand/review/final"))) {
  const references = spawnSync(
    process.execPath,
    [resolve(root, "scripts/check_brand_references.mjs")],
    {
      cwd: root,
      encoding: "utf8",
    },
  );
  if (references.status !== 0)
    fail(references.stderr || references.stdout || "reference check failed");
}
console.log(
  `Brand asset contract valid: ${contract.sources.length} sources, Inter ${font.packageVersion}, Lucide ${icons.version}`,
);
