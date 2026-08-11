import { expect, test as base } from '@playwright/test';

export const test = base.extend<{ resetE2e: void }>({
  resetE2e: [
    async ({ page }, use) => {
      await page.goto('/api/health');
      const reset = await page.evaluate(async () => {
        const response = await fetch('/__e2e/reset', { method: 'POST' });
        return { status: response.status, body: await response.text() };
      });
      expect(reset.status, reset.body).toBe(200);
      await use();
    },
    { auto: true },
  ],
});

export { expect };
