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
    response.writeHead(200, {
      "content-type":
        mimeTypes.get(extname(path)) ?? "application/octet-stream",
    });
    createReadStream(path).pipe(response);
  } catch {
    response.writeHead(404).end("Not found");
  }
});

await new Promise((resolveListen) =>
  server.listen(0, "127.0.0.1", resolveListen),
);
const address = server.address();
if (!address || typeof address === "string")
  throw new Error("Static server did not bind");
const baseUrl = `http://127.0.0.1:${address.port}/lzug/`;
await mkdir(evidence, { recursive: true });

const browserChannel = process.env.PLAYWRIGHT_BROWSER_CHANNEL;
if (browserChannel !== undefined && browserChannel !== "chrome") {
  throw new Error(`Unsupported Playwright browser channel: ${browserChannel}`);
}
const browser = await chromium.launch({
  chromiumSandbox: true,
  ...(browserChannel === "chrome" ? { channel: browserChannel } : {}),
});
const results = [];
try {
  for (const candidate of [
    {
      name: "desktop-light",
      colorScheme: "light",
      themeVariant: "relearn-light",
      viewport: { width: 1440, height: 1000 },
    },
    {
      name: "desktop-dark",
      colorScheme: "dark",
      themeVariant: "relearn-dark",
      viewport: { width: 1440, height: 1000 },
    },
    {
      name: "mobile-light",
      colorScheme: "light",
      themeVariant: "relearn-light",
      viewport: { width: 390, height: 844 },
    },
    {
      name: "mobile-dark",
      colorScheme: "dark",
      themeVariant: "relearn-dark",
      viewport: { width: 390, height: 844 },
    },
  ]) {
    const context = await browser.newContext({
      viewport: candidate.viewport,
      colorScheme: candidate.colorScheme,
    });
    const page = await context.newPage();
    await page.addInitScript((themeVariant) => {
      window.localStorage.setItem(
        "https://lxndrp.github.io/lzug/variant",
        themeVariant,
      );
    }, candidate.themeVariant);
    page.setDefaultTimeout(10_000);
    page.setDefaultNavigationTimeout(15_000);
    const consoleErrors = [];
    page.on("console", (message) => {
      if (message.type() === "error") consoleErrors.push(message.text());
    });
    const response = await page.goto(baseUrl, { waitUntil: "networkidle" });
    if (!response?.ok())
      throw new Error(
        `${candidate.name}: homepage returned ${response?.status()}`,
      );

    const structure = await page.evaluate(() => ({
      h1: document.querySelectorAll("h1").length,
      main: document.querySelectorAll("main").length,
      nav: document.querySelectorAll("nav").length,
      search: document.querySelectorAll('input[type="search"]').length,
      demoStart: document.querySelectorAll("[data-demo-start]").length,
      themeVariant: document.documentElement.dataset.rThemeVariant,
      overflow: document.documentElement.scrollWidth - window.innerWidth,
    }));
    if (
      structure.h1 !== 1 ||
      structure.main !== 1 ||
      structure.nav < 1 ||
      structure.search < 1 ||
      structure.demoStart !== 1
    ) {
      throw new Error(
        `${candidate.name}: invalid landmarks ${JSON.stringify(structure)}`,
      );
    }
    if (structure.overflow > 0)
      throw new Error(
        `${candidate.name}: horizontal overflow ${structure.overflow}px`,
      );
    if (structure.themeVariant !== candidate.themeVariant) {
      throw new Error(
        `${candidate.name}: expected ${candidate.themeVariant}, got ${structure.themeVariant}`,
      );
    }

    const accessibility = await new AxeBuilder({ page }).analyze();
    const blocking = accessibility.violations.filter(
      ({ impact }) => impact === "critical" || impact === "serious",
    );
    if (blocking.length) {
      const details = blocking.flatMap(({ id, nodes }) =>
        nodes.map(({ html, failureSummary }) => ({ id, html, failureSummary })),
      );
      throw new Error(
        `${candidate.name}: blocking axe violations ${JSON.stringify(details)}`,
      );
    }
    if (consoleErrors.length)
      throw new Error(
        `${candidate.name}: console errors ${consoleErrors.join(" | ")}`,
      );
    await page.screenshot({
      path: join(evidence, `${candidate.name}.png`),
      fullPage: true,
    });
    results.push({
      ...candidate,
      ...structure,
      axeViolations: accessibility.violations.length,
    });
    await context.close();
  }

  const handbookContext = await browser.newContext({
    viewport: { width: 1280, height: 900 },
  });
  const handbook = await handbookContext.newPage();
  handbook.setDefaultTimeout(10_000);
  handbook.setDefaultNavigationTimeout(15_000);
  const handbookResponse = await handbook.goto(`${baseUrl}handbuch/`, {
    waitUntil: "networkidle",
  });
  if (!handbookResponse?.ok())
    throw new Error(`handbook returned ${handbookResponse?.status()}`);
  if (!(await handbook.locator('input[type="search"]').count()))
    throw new Error("handbook search is missing");
  await handbookContext.close();

  const warmupContext = await browser.newContext({
    viewport: { width: 1280, height: 900 },
  });
  const warmup = await warmupContext.newPage();
  warmup.setDefaultTimeout(10_000);
  warmup.setDefaultNavigationTimeout(15_000);
  let readinessRequests = 0;
  await warmup.route(
    "https://demo.example.invalid/api/ready",
    async (route) => {
      readinessRequests += 1;
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          status: "ready",
          _links: { self: { href: "/api/ready" } },
        }),
      });
    },
  );
  await warmup.route("https://demo.example.invalid/", (route) =>
    route.fulfill({ status: 200, body: "Demo" }),
  );
  await warmup.goto(baseUrl, { waitUntil: "networkidle" });
  await warmup
    .getByRole("button", { name: "Demo starten" })
    .click({ noWaitAfter: true });
  await warmup.waitForURL("https://demo.example.invalid/");
  if (readinessRequests !== 1)
    throw new Error(
      `warm-up used ${readinessRequests} readiness requests before success`,
    );
  await warmupContext.close();

  const failureContext = await browser.newContext({
    viewport: { width: 390, height: 844 },
  });
  const failure = await failureContext.newPage();
  failure.setDefaultTimeout(10_000);
  await failure.route("https://demo.example.invalid/api/ready", (route) =>
    route.fulfill({
      status: 503,
      contentType: "application/json",
      body: JSON.stringify({ status: "unavailable" }),
    }),
  );
  await failure.goto(baseUrl, { waitUntil: "networkidle" });
  await failure.locator("[data-demo-start]").evaluate((element) => {
    element.dataset.demoMaximumAttempts = "1";
    element.dataset.demoTotalTimeoutMs = "1000";
  });
  await failure
    .getByRole("button", { name: "Demo starten" })
    .click({ noWaitAfter: true });
  await failure.getByText("Demo konnte nicht gestartet werden").waitFor();
  const retry = failure.getByRole("button", { name: "Erneut versuchen" });
  if (!(await retry.isEnabled()))
    throw new Error("failed warm-up did not expose an enabled retry");
  await retry.focus();
  if (
    !(await retry.evaluate((element) => element === document.activeElement))
  ) {
    throw new Error("failed warm-up did not restore focus to the retry action");
  }
  await failureContext.close();
} finally {
  await browser.close();
  server.closeAllConnections();
  await new Promise((resolveClose, rejectClose) =>
    server.close((error) => (error ? rejectClose(error) : resolveClose())),
  );
}

console.log(JSON.stringify({ baseUrl, results }, null, 2));
