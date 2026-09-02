#!/usr/bin/env node

import { createHash } from "node:crypto";
import {
  existsSync,
  mkdirSync,
  mkdtempSync,
  readFileSync,
  readdirSync,
  rmSync,
  statSync,
  writeFileSync,
} from "node:fs";
import { tmpdir } from "node:os";
import { dirname, resolve } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { createRequire } from "node:module";
import { spawnSync } from "node:child_process";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const require = createRequire(import.meta.url);
const { chromium } = require(resolve(root, "frontend/node_modules/playwright"));
const reviewDirectory = resolve(root, "brand/review");
const outputDirectory = resolve(reviewDirectory, "evidence");
const candidateManifest = JSON.parse(
  readFileSync(resolve(reviewDirectory, "font-candidates.json"), "utf8"),
);

function argumentValue(name, fallback) {
  const index = process.argv.indexOf(name);
  return index === -1 ? fallback : process.argv[index + 1];
}

function sha512(path) {
  return `sha512-${createHash("sha512").update(readFileSync(path)).digest("base64")}`;
}

function sha256(path) {
  return createHash("sha256").update(readFileSync(path)).digest("hex");
}

function extractCandidate(candidate, fontCache, temporaryDirectory) {
  const archive = resolve(fontCache, candidate.tarball);
  if (!existsSync(archive)) {
    throw new Error(
      `Missing ${candidate.tarball}; run npm pack ${candidate.package}@${candidate.version} --pack-destination ${fontCache}`,
    );
  }
  const integrity = sha512(archive);
  if (integrity !== candidate.integrity) {
    throw new Error(`${candidate.tarball} integrity mismatch: ${integrity}`);
  }

  const destination = resolve(temporaryDirectory, candidate.id);
  mkdirSync(destination, { recursive: true });
  const extraction = spawnSync("tar", ["-xzf", archive, "-C", destination], {
    encoding: "utf8",
  });
  if (extraction.status !== 0) {
    throw new Error(
      extraction.stderr || `Could not extract ${candidate.tarball}`,
    );
  }
  const packageDirectory = resolve(destination, "package");
  const metadata = JSON.parse(
    readFileSync(resolve(packageDirectory, "metadata.json"), "utf8"),
  );
  if (metadata.version !== candidate.sourceVersion) {
    throw new Error(
      `${candidate.name} upstream version mismatch: ${metadata.version} != ${candidate.sourceVersion}`,
    );
  }
  if (metadata.license.type !== candidate.license) {
    throw new Error(
      `${candidate.name} license mismatch: ${metadata.license.type} != ${candidate.license}`,
    );
  }
  const cssPath = resolve(packageDirectory, "wght.css");
  const css = readFileSync(cssPath, "utf8").replace(
    /url\(\.\/files\/([^)]+)\)/g,
    (_, filename) =>
      `url("${pathToFileURL(resolve(packageDirectory, "files", filename)).href}")`,
  );
  const family = css.match(/font-family: '([^']+)'/)?.[1];
  if (!family)
    throw new Error(`Could not read variable family from ${cssPath}`);
  for (const subset of ["latin", "greek", "greek-ext"]) {
    if (!metadata.subsets.includes(subset)) {
      throw new Error(
        `${candidate.name} does not provide the required ${subset} subset`,
      );
    }
  }
  return { candidate, css, family, metadata, packageDirectory };
}

async function renderPage(
  browser,
  { file, output, theme, viewport, beforeScreenshot },
) {
  const context = await browser.newContext({ colorScheme: theme, viewport });
  const page = await context.newPage();
  await page.goto(file, { waitUntil: "load" });
  if (beforeScreenshot) await beforeScreenshot(page);
  await page.screenshot({ path: output, fullPage: true });
  const dimensions = await page.evaluate(() => ({
    height: document.documentElement.scrollHeight,
    overflow: document.documentElement.scrollWidth - window.innerWidth,
    width: document.documentElement.scrollWidth,
  }));
  await context.close();
  if (dimensions.overflow > 0) {
    throw new Error(
      `${output} overflows its viewport by ${dimensions.overflow}px`,
    );
  }
  return dimensions;
}

async function main() {
  const fontCache = resolve(
    argumentValue("--font-cache", "/private/tmp/lzug-568-fonts"),
  );
  mkdirSync(outputDirectory, { recursive: true });
  const temporaryDirectory = mkdtempSync(
    resolve(tmpdir(), "lzug-brand-review-"),
  );
  const extractedCandidates = candidateManifest.candidates.map((candidate) =>
    extractCandidate(candidate, fontCache, temporaryDirectory),
  );
  let browser;

  try {
    browser = await chromium.launch({ ignoreDefaultArgs: ["--no-sandbox"] });
    const report = {
      schema: 1,
      renderer: await browser.version(),
      logo: [],
      fonts: [],
    };
    for (const theme of ["light", "dark"]) {
      const name = `logo-comparison-${theme}.png`;
      const file = `${pathToFileURL(resolve(reviewDirectory, "logo-comparison.html")).href}?theme=${theme}`;
      const output = resolve(outputDirectory, name);
      const dimensions = await renderPage(browser, {
        file,
        output,
        theme,
        viewport: { width: 1440, height: 1000 },
      });
      const context = await browser.newContext({
        colorScheme: theme,
        viewport: { width: 1440, height: 1000 },
      });
      const page = await context.newPage();
      await page.goto(file, { waitUntil: "load" });
      const variants = await page.locator(".panel").count();
      const samples = await page
        .locator(".size-sample img")
        .evaluateAll((images) =>
          images.map((image) => ({
            complete: image.complete,
            height: image.getBoundingClientRect().height,
            naturalWidth: image.naturalWidth,
            width: image.getBoundingClientRect().width,
          })),
        );
      await context.close();
      const expectedSizes = [16, 32, 64, 16, 32, 64, 16, 32, 64];
      if (
        variants !== 3 ||
        samples.length !== expectedSizes.length ||
        samples.some(
          (sample, index) =>
            !sample.complete ||
            sample.naturalWidth === 0 ||
            sample.width !== expectedSizes[index] ||
            sample.height !== expectedSizes[index],
        )
      ) {
        throw new Error(`${name} does not contain three valid 16/32/64px sets`);
      }
      report.logo.push({ name, theme, variants, samples, ...dimensions });
    }

    const modes = [
      {
        name: "desktop-light",
        theme: "light",
        viewport: { width: 1440, height: 1100 },
      },
      {
        name: "mobile-dark",
        theme: "dark",
        viewport: { width: 390, height: 844 },
      },
    ];
    for (const extracted of extractedCandidates) {
      for (const mode of modes) {
        const name = `font-${extracted.candidate.id}-${mode.name}.png`;
        const file = `${pathToFileURL(resolve(reviewDirectory, "font-comparison.html")).href}?theme=${mode.theme}&candidate=${encodeURIComponent(extracted.candidate.name)}`;
        const output = resolve(outputDirectory, name);
        let loadedFaces = [];
        const dimensions = await renderPage(browser, {
          file,
          output,
          theme: mode.theme,
          viewport: mode.viewport,
          beforeScreenshot: async (page) => {
            await page.addStyleTag({ content: extracted.css });
            await page.evaluate((family) => {
              document.documentElement.style.setProperty(
                "--font-review",
                `"${family}", ui-sans-serif, system-ui, sans-serif`,
              );
            }, extracted.family);
            loadedFaces = await page.evaluate(async (family) => {
              const sample =
                "Prüfungsausschuss Köln Zoë Ἀθήνα Νίκος 24.06.2027 08:30-10:15 1.234,50 EUR";
              await Promise.all([
                document.fonts.load(`400 16px "${family}"`, sample),
                document.fonts.load(`600 16px "${family}"`, sample),
                document.fonts.load(`700 16px "${family}"`, sample),
              ]);
              await document.fonts.ready;
              return [...document.fonts]
                .filter(
                  (face) => face.family === family && face.status === "loaded",
                )
                .map((face) => ({
                  status: face.status,
                  unicodeRange: face.unicodeRange,
                  weight: face.weight,
                }));
            }, extracted.family);
          },
        });
        const loadedRanges = loadedFaces.map(({ unicodeRange }) =>
          unicodeRange.toUpperCase(),
        );
        const loadedSubsets = [
          loadedRanges.some((range) => range.includes("U+0-FF")) && "latin",
          loadedRanges.some((range) => range.includes("U+370-377")) && "greek",
          loadedRanges.some((range) => range.includes("U+1F00-1FFF")) &&
            "greek-ext",
        ].filter(Boolean);
        if (loadedSubsets.length !== 3) {
          throw new Error(
            `${extracted.candidate.name} did not load all required subsets: ${loadedSubsets.join(", ")}`,
          );
        }
        const payloadFiles = readdirSync(
          resolve(extracted.packageDirectory, "files"),
        ).filter(
          (file) =>
            /-(?:latin|greek|greek-ext)-wght-normal\.woff2$/.test(file) &&
            !file.includes("latin-ext"),
        );
        const payloadBytes = payloadFiles.reduce(
          (total, file) =>
            total +
            statSync(resolve(extracted.packageDirectory, "files", file)).size,
          0,
        );
        report.fonts.push({
          axes: extracted.candidate.axes,
          candidate: extracted.candidate.name,
          family: extracted.family,
          license: extracted.candidate.license,
          licenseSha256: sha256(resolve(extracted.packageDirectory, "LICENSE")),
          mode: mode.name,
          name,
          payloadBytes,
          payloadFiles,
          sourceVersion: extracted.candidate.sourceVersion,
          upstream: extracted.metadata.source,
          subsets: loadedSubsets,
          ...dimensions,
        });
      }
    }
    writeFileSync(
      resolve(outputDirectory, "render-report.json"),
      `${JSON.stringify(report, null, 2)}\n`,
    );
  } finally {
    if (browser) await browser.close();
    rmSync(temporaryDirectory, { recursive: true, force: true });
  }
}

await main();
