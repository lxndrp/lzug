import { expect, test as base } from '@playwright/test';

export const test = base.extend({});

test.beforeEach(async ({ page }) => {
  await page.goto('/api/health');
  const reset = await page.evaluate(async () => {
    const response = await fetch('/__e2e/reset', { method: 'POST' });
    return { status: response.status, body: await response.text() };
  });
  expect(reset.status, reset.body).toBe(200);
});

export { expect };
