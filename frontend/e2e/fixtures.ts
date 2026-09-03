import { expect, test as base } from '@playwright/test';

export const test = base.extend<{ resetE2e: void }>({
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
