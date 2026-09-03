import { defineConfig } from '@playwright/test';
import { createHash } from 'node:crypto';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const frontendDirectory = dirname(fileURLToPath(import.meta.url));
const suite = process.env.LZUG_PUBLICATION_SUITE ?? 'browser';
if (!['browser', 'a11y', 'reference'].includes(suite)) {
  throw new Error(`Unsupported publication suite: ${suite}`);
}

const runId = (process.env.LZUG_E2E_RUN_ID ?? 'direct-publication-run').replaceAll(
  /[^a-zA-Z0-9_-]/g,
  '-',
);
const port =
  50_000 +
  (Number.parseInt(createHash('sha256').update(runId).digest('hex').slice(0, 8), 16) % 10_000);
const baseURL = `http://127.0.0.1:${port}`;
const publicationRoot = resolve(
  frontendDirectory,
  process.env.LZUG_PUBLICATION_ROOT ?? '../build/publication',
);
const browserChannel = process.env.PLAYWRIGHT_BROWSER_CHANNEL;
if (browserChannel !== undefined && browserChannel !== 'chrome') {
  throw new Error(`Unsupported Playwright browser channel: ${browserChannel}`);
}

export default defineConfig({
  testDir: './publication-e2e',
  testMatch:
    suite === 'a11y'
      ? 'publication.a11y.spec.ts'
      : suite === 'reference'
        ? 'brand-reference.spec.ts'
        : 'publication.spec.ts',
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: 1,
  reporter: process.env.CI
    ? [
        ['html', { outputFolder: `playwright-publication-${suite}-report`, open: 'never' }],
        ['list'],
      ]
    : [['list']],
  outputDir: `../build/publication-evidence/${suite}`,
  use: {
    baseURL,
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
    video: 'off',
    launchOptions: { chromiumSandbox: true },
    ...(browserChannel === 'chrome' ? { channel: browserChannel } : {}),
  },
  webServer: {
    command: `node e2e/serve-publication.mjs "${publicationRoot}" ${port}`,
    cwd: '.',
    url: baseURL,
    reuseExistingServer: false,
    timeout: 30_000,
  },
});
