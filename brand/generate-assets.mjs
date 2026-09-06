#!/usr/bin/env node

import {
  existsSync,
  mkdirSync,
  mkdtempSync,
  readFileSync,
  readdirSync,
  rmSync,
  writeFileSync,
} from "node:fs";
import { dirname, extname, resolve } from "node:path";
import { tmpdir } from "node:os";
import { fileURLToPath } from "node:url";
import { createRequire } from "node:module";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const require = createRequire(import.meta.url);
const { Resvg } = require(
  resolve(root, "frontend/node_modules/@resvg/resvg-js"),
);
const contract = JSON.parse(
  readFileSync(resolve(root, "brand/asset-contract.json"), "utf8"),
);
const derivatives = new Set(contract.derivatives);

function fail(message) {
  throw new Error(`Brand asset contract: ${message}`);
}

function validateContract() {
  if (contract.schema !== 3) fail("unsupported asset schema");

  const expectedSources = new Set();
  for (const source of contract.sources ?? []) {
    if (!source.id || !source.path || !source.viewBox) {
      fail("every source needs id, path, and viewBox");
    }
    const sourcePath = resolve(root, source.path);
    if (!sourcePath.startsWith(resolve(root, "brand/source/"))) {
      fail(`${source.path} is outside brand/source`);
    }
    if (!existsSync(sourcePath) || extname(sourcePath) !== ".svg") {
      fail(`${source.path} is not an SVG source`);
    }
    const svg = readFileSync(sourcePath, "utf8");
    const rootElement = svg.match(/<svg\b[^>]*>/i)?.[0];
    if (!rootElement?.includes(`viewBox="${source.viewBox}"`)) {
      fail(`${source.path} does not use viewBox ${source.viewBox}`);
    }
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

  const actualDerivatives = new Set(
    readdirSync(resolve(root, "brand/derived")),
  );
  if (
    derivatives.size !== actualDerivatives.size ||
    [...derivatives].some((name) => !actualDerivatives.has(name))
  ) {
    fail("brand/derived contains assets outside the current consumer contract");
  }
  for (const name of derivatives) {
    if (!existsSync(resolve(root, "brand/derived", name)))
      fail(`missing derivative ${name}`);
  }

  const packageJson = JSON.parse(
    readFileSync(resolve(root, "frontend/package.json"), "utf8"),
  );
  const lock = JSON.parse(
    readFileSync(resolve(root, "frontend/package-lock.json"), "utf8"),
  );
  for (const [name, version] of [
    ["@fontsource-variable/inter", "5.3.0"],
    ["lucide", "1.39.0"],
  ]) {
    if (packageJson.dependencies?.[name] !== version)
      fail(`${name} dependency is not exact`);
    if (lock.packages?.[`node_modules/${name}`]?.version !== version) {
      fail(`${name} lock version differs`);
    }
  }
  if (
    !existsSync(resolve(root, "brand/licenses/Inter-OFL.txt")) ||
    !readFileSync(
      resolve(root, "brand/licenses/Inter-OFL.txt"),
      "utf8",
    ).includes("SIL OPEN FONT LICENSE")
  ) {
    fail("Inter OFL license text is missing");
  }
  for (const token of [
    "--lzug-color-brand-ink",
    "--lzug-color-status-success",
    "--lzug-color-data-1",
    "--lzug-font-family",
    "--lzug-touch-target-min",
    "--lzug-motion-normal",
  ]) {
    if (
      !readFileSync(resolve(root, "brand/tokens.css"), "utf8").includes(token)
    ) {
      fail(`missing canonical token ${token}`);
    }
  }
  if (
    !readFileSync(
      resolve(root, "frontend/src/taiga-adapter.css"),
      "utf8",
    ).includes("--tui-background-accent-1")
  ) {
    fail("Taiga adapter is incomplete");
  }
}

function dataUrl(value) {
  return `data:image/svg+xml;base64,${Buffer.from(value).toString("base64")}`;
}

function logoVariant(name) {
  const variant = contract.variants[name];
  const source = readFileSync(
    resolve(root, "brand/source/logo-mark.svg"),
    "utf8",
  );
  return source
    .replace("--brand-ink: #2d235c", `--brand-ink: ${variant.ink}`)
    .replace("--brand-accent: #f3b33d", `--brand-accent: ${variant.accent}`);
}

function keyVisualVariant(name) {
  const variant = contract.variants[name];
  const source = readFileSync(
    resolve(root, "brand/source/key-visual.svg"),
    "utf8",
  );
  if (name === "light") return source;
  return source
    .replaceAll("#2d235c", variant.ink)
    .replaceAll("#f3b33d", variant.accent)
    .replaceAll("#f8f7fc", "#f5f2ff")
    .replaceAll("#110d25", "#151225");
}

function wordmarkSvg(name) {
  const variant = contract.variants[name];
  const mark = dataUrl(logoVariant(name));
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 720 256" role="img" aria-labelledby="title description">
  <title id="title">lzug Wort- und Bildmarke</title>
  <desc id="description">Die lzug Bildmarke neben der Wortmarke lzug.</desc>
  <image href="${mark}" x="24" y="30" width="196" height="196" />
  <text x="250" y="161" fill="${variant.wordmark}" font-family="Inter, Arial, sans-serif" font-size="114" font-weight="700" letter-spacing="0">lzug</text>
</svg>
`;
}

function rasterize(svg, output, width) {
  const renderer = new Resvg(svg, {
    fitTo: { mode: "width", value: width },
    font: { loadSystemFonts: true },
  });
  writeFileSync(output, renderer.render().asPng());
}

function ico(pngPaths, output) {
  const images = pngPaths.map((path) => readFileSync(path));
  const sizes = [16, 32, 48];
  const header = Buffer.alloc(6);
  header.writeUInt16LE(0, 0);
  header.writeUInt16LE(1, 2);
  header.writeUInt16LE(images.length, 4);
  let offset = 6 + images.length * 16;
  const entries = images.map((image, index) => {
    const entry = Buffer.alloc(16);
    entry.writeUInt8(sizes[index], 0);
    entry.writeUInt8(sizes[index], 1);
    entry.writeUInt16LE(1, 4);
    entry.writeUInt16LE(32, 6);
    entry.writeUInt32LE(image.length, 8);
    entry.writeUInt32LE(offset, 12);
    offset += image.length;
    return entry;
  });
  writeFileSync(output, Buffer.concat([header, ...entries, ...images]));
}

function files(directory) {
  return readdirSync(directory).sort();
}

function writeDerivative(output, name, content) {
  if (derivatives.has(name)) writeFileSync(resolve(output, name), content);
}

function generate(output) {
  mkdirSync(output, { recursive: true });
  for (const name of files(output))
    rmSync(resolve(output, name), { force: true });
  writeDerivative(output, "favicon.svg", logoVariant("light"));
  writeDerivative(output, "logo-mark-dark.svg", logoVariant("dark"));
  writeDerivative(output, "logo-horizontal-light.svg", wordmarkSvg("light"));
  writeDerivative(output, "logo-horizontal-dark.svg", wordmarkSvg("dark"));
  writeDerivative(output, "key-visual-light.svg", keyVisualVariant("light"));
  writeDerivative(output, "key-visual-dark.svg", keyVisualVariant("dark"));
  if (derivatives.has("favicon.ico")) {
    const faviconDirectory = mkdtempSync(resolve(tmpdir(), "lzug-favicon-"));
    try {
      const pngs = [16, 32, 48].map((size) => {
        const path = resolve(faviconDirectory, `favicon-${size}.png`);
        rasterize(logoVariant("light"), path, size);
        return path;
      });
      ico(pngs, resolve(output, "favicon.ico"));
    } finally {
      rmSync(faviconDirectory, { recursive: true, force: true });
    }
  }
}

const output = resolve(
  root,
  process.argv.includes("--output")
    ? process.argv[process.argv.indexOf("--output") + 1]
    : "brand/derived",
);
const check = process.argv.includes("--check");
const temporary = check
  ? mkdtempSync(resolve(tmpdir(), "lzug-brand-assets-"))
  : null;
const destination = temporary ?? output;

try {
  validateContract();
  generate(destination);
  if (check) {
    if (
      !existsSync(output) ||
      JSON.stringify(files(destination)) !== JSON.stringify(files(output))
    ) {
      throw new Error(
        "derived asset inventory differs; run task brand:generate",
      );
    }
    for (const name of files(destination)) {
      if (
        !readFileSync(resolve(destination, name)).equals(
          readFileSync(resolve(output, name)),
        )
      ) {
        throw new Error(`derived asset drift: brand/derived/${name}`);
      }
    }
    console.log(
      `Brand derivatives are reproducible: ${files(destination).length} files`,
    );
  } else {
    console.log(
      `Generated ${files(destination).length} brand derivatives in ${destination}`,
    );
  }
} finally {
  if (temporary) rmSync(temporary, { recursive: true, force: true });
}
