import { defineConfig, devices } from '@playwright/test';
import { createHash } from 'node:crypto';

const runId = (process.env.LZUG_E2E_RUN_ID ?? 'direct-playwright-run').replaceAll(
  /[^a-zA-Z0-9_-]/g,
  '-',
);
const portFor = (name: string, base: number): number => {
  const hash = createHash('sha256').update(`${runId}:${name}`).digest('hex');
  return base + (Number.parseInt(hash.slice(0, 8), 16) % 10_000);
};
const backendPort = portFor('backend', 20_000);
const frontendPort = portFor('frontend', 40_000);
const backendUrl = `http://127.0.0.1:${backendPort}`;
const frontendUrl = `http://127.0.0.1:${frontendPort}`;

export default defineConfig({
  testDir: './e2e',
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: 1,
  reporter: process.env.CI ? [['html'], ['list']] : [['list']],
  use: {
    baseURL: frontendUrl,
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
    ...devices['Desktop Chrome'],
  },
  webServer: [
    {
      command: `.venv/bin/python -m backend.e2e_server --host 127.0.0.1 --port ${backendPort} --db var/e2e/lzug-e2e-${runId}.sqlite3`,
      cwd: '..',
      url: `${backendUrl}/api/health`,
      reuseExistingServer: false,
      timeout: 120_000,
    },
    {
      command: `node e2e/start-frontend.mjs ${frontendPort} ${backendPort}`,
      cwd: '.',
      url: frontendUrl,
      reuseExistingServer: false,
      timeout: 120_000,
    },
  ],
});
