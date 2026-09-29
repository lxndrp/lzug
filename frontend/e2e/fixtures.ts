import { execFileSync } from 'node:child_process';
import { mkdtempSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import process from 'node:process';
import { expect, test as base } from '@playwright/test';

export const test = base.extend<{ resetE2e: void }>({
  launchOptions: [
    async ({ browserName, launchOptions }, use) => {
      if (process.platform !== 'darwin' || browserName !== 'firefox') {
        await use(launchOptions);
        return;
      }

      const firefoxHome = mkdtempSync(join(tmpdir(), 'lzug-playwright-firefox-'));
      try {
        await use({
          ...launchOptions,
          env: {
            ...process.env,
            ...launchOptions.env,
            CFFIXED_USER_HOME: firefoxHome,
          },
        });
      } finally {
        execFileSync('/bin/chmod', ['-R', '-P', '-N', firefoxHome], { timeout: 10_000 });
        rmSync(firefoxHome, { recursive: true });
      }
    },
    { scope: 'worker' },
  ],
  resetE2e: [
    async ({ page }, use) => {
      const reset = await page.request.post('/__e2e/reset');
      expect(reset.status(), await reset.text()).toBe(200);
      await use();
    },
    { auto: true },
  ],
});

export { expect };
