#!/usr/bin/env node

import { createHash } from "node:crypto";
import { existsSync, readFileSync, readdirSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const directory = resolve(root, "brand/review/final");
const reportPath = resolve(directory, "report.json");
const expected = [
  "assets-theme-monochrome-small-sizes.png",
  "product-dashboard-dark-desktop.png",
  "product-dashboard-light-desktop.png",
  "product-detail-cards-light-desktop.png",
  "product-form-validation-light-desktop.png",
  "product-login-light-desktop.png",
  "product-mobile-navigation-dark.png",
  "product-reflow-200-percent-light.png",
  "product-table-dark-desktop.png",
  "publication-handbook-light-desktop.png",
  "publication-landing-dark-mobile.png",
  "publication-landing-light-desktop.png",
  "state-conflict-dark-desktop.png",
  "state-empty-light-desktop.png",
  "state-error-dark-desktop.png",
  "state-loading-dark-desktop.png",
  "state-success-light-desktop.png",
  "state-warning-dark-desktop.png",
].sort();

function sha256(bytes) {
  return createHash("sha256").update(bytes).digest("hex");
}

function pngSize(bytes, name) {
  if (bytes.toString("ascii", 1, 4) !== "PNG")
    throw new Error(`${name} is not a PNG`);
  return { width: bytes.readUInt32BE(16), height: bytes.readUInt32BE(20) };
}

if (!existsSync(directory))
  throw new Error(
    "final brand references are missing; run task brand:references",
  );
const actual = readdirSync(directory)
  .filter((name) => name !== "report.json")
  .sort();
if (JSON.stringify(actual) !== JSON.stringify(expected)) {
  throw new Error(
    `final reference inventory differs: expected ${expected.length}, found ${actual.length}`,
  );
}

const references = expected.map((name) => {
  const bytes = readFileSync(resolve(directory, name));
  return { name, ...pngSize(bytes, name), sha256: sha256(bytes) };
});
const report = {
  schema: 1,
  renderer: `Playwright ${JSON.parse(readFileSync(resolve(root, "frontend/node_modules/@playwright/test/package.json"), "utf8")).version}`,
  contracts: {
    assets: sha256(readFileSync(resolve(root, "brand/asset-contract.json"))),
    font: sha256(readFileSync(resolve(root, "brand/font-contract.json"))),
    icons: sha256(readFileSync(resolve(root, "brand/icon-contract.json"))),
    tokens: sha256(readFileSync(resolve(root, "brand/tokens.css"))),
  },
  checks: [
    "light and dark themes",
    "desktop and mobile viewports",
    "200-percent text reflow",
    "reduced motion",
    "transparent, themed, black, and white logo variants",
    "16, 32, and 48 pixel raster derivatives",
  ],
  references,
};

if (process.argv.includes("--write-report")) {
  writeFileSync(reportPath, `${JSON.stringify(report, null, 2)}\n`);
}
if (!existsSync(reportPath))
  throw new Error("final reference report is missing");
const recorded = JSON.parse(readFileSync(reportPath, "utf8"));
if (JSON.stringify(recorded) !== JSON.stringify(report)) {
  throw new Error("final reference report drift; run task brand:references");
}
console.log(`Final brand references valid: ${references.length} PNG files`);
