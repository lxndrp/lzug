#!/usr/bin/env node

import { createReadStream } from "node:fs";
import { mkdir, stat } from "node:fs/promises";
import { createServer } from "node:http";
import { extname, join, normalize, resolve } from "node:path";
import { chromium } from "../frontend/node_modules/@playwright/test/index.mjs";
import AxeBuilder from "../frontend/node_modules/@axe-core/playwright/dist/index.mjs";

const root = resolve(process.argv[2] ?? "build/publication-spike");
const evidence = resolve(process.argv[3] ?? "build/publication-spike-evidence");
const mimeTypes = new Map([
  [".css", "text/css"],
  [".html", "text/html; charset=utf-8"],
  [".js", "text/javascript"],
  [".json", "application/json"],
  [".svg", "image/svg+xml"],
  [".woff2", "font/woff2"],
]);

function resolveRequest(url) {
  const pathname = new URL(url, "http://127.0.0.1").pathname;
  const relative = pathname.replace(/^\/lzug\/?/, "");
  const candidate = resolve(root, normalize(relative || "index.html"));
  if (candidate !== root && !candidate.startsWith(`${root}/`)) {
    throw new Error(`Unsafe request path: ${pathname}`);
  }
  return candidate;
}

const server = createServer(async (request, response) => {
  try {
    let path = resolveRequest(request.url ?? "/");
    const metadata = await stat(path);
    if (metadata.isDirectory()) path = join(path, "index.html");
    response.writeHead(200, { "content-type": mimeTypes.get(extname(path)) ?? "application/octet-stream" });
    createReadStream(path).pipe(response);
  } catch {
    response.writeHead(404).end("Not found");
  }
});

await new Promise((resolveListen) => server.listen(0, "127.0.0.1", resolveListen));
const address = server.address();
if (!address || typeof address === "string") throw new Error("Static server did not bind");
const baseUrl = `http://127.0.0.1:${address.port}/lzug/`;
await mkdir(evidence, { recursive: true });

const browser = await chromium.launch({ chromiumSandbox: true });
const results = [];
try {
  for (const candidate of [
    { name: "desktop", viewport: { width: 1440, height: 1000 } },
    { name: "mobile", viewport: { width: 390, height: 844 } },
  ]) {
    const context = await browser.newContext({ viewport: candidate.viewport });
    const page = await context.newPage();
    const consoleErrors = [];
    page.on("console", (message) => {
      if (message.type() === "error") consoleErrors.push(message.text());
    });
    const response = await page.goto(baseUrl, { waitUntil: "networkidle" });
    if (!response?.ok()) throw new Error(`${candidate.name}: homepage returned ${response?.status()}`);

    const structure = await page.evaluate(() => ({
      h1: document.querySelectorAll("h1").length,
      main: document.querySelectorAll("main").length,
      nav: document.querySelectorAll("nav").length,
      search: document.querySelectorAll('input[type="search"]').length,
      overflow: document.documentElement.scrollWidth - window.innerWidth,
    }));
    if (structure.h1 !== 1 || structure.main !== 1 || structure.nav < 1 || structure.search < 1) {
      throw new Error(`${candidate.name}: invalid landmarks ${JSON.stringify(structure)}`);
    }
    if (structure.overflow > 0) throw new Error(`${candidate.name}: horizontal overflow ${structure.overflow}px`);

    const accessibility = await new AxeBuilder({ page }).analyze();
    const blocking = accessibility.violations.filter(({ impact }) => impact === "critical" || impact === "serious");
    if (blocking.length) {
      const details = blocking.flatMap(({ id, nodes }) =>
        nodes.map(({ html, failureSummary }) => ({ id, html, failureSummary })),
      );
      throw new Error(`${candidate.name}: blocking axe violations ${JSON.stringify(details)}`);
    }
    if (consoleErrors.length) throw new Error(`${candidate.name}: console errors ${consoleErrors.join(" | ")}`);
    await page.screenshot({ path: join(evidence, `${candidate.name}.png`), fullPage: true });
    results.push({ ...candidate, ...structure, axeViolations: accessibility.violations.length });
    await context.close();
  }

  const handbookContext = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  const handbook = await handbookContext.newPage();
  const handbookResponse = await handbook.goto(`${baseUrl}handbuch/`, { waitUntil: "networkidle" });
  if (!handbookResponse?.ok()) throw new Error(`handbook returned ${handbookResponse?.status()}`);
  if (!(await handbook.locator('input[type="search"]').count())) throw new Error("handbook search is missing");
  await handbookContext.close();
} finally {
  await browser.close();
  await new Promise((resolveClose, rejectClose) => server.close((error) => error ? rejectClose(error) : resolveClose()));
}

console.log(JSON.stringify({ baseUrl, results }, null, 2));
