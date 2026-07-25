import { expect, test as base } from '@playwright/test';

export const test = base.extend({});

test.beforeEach(async ({ request }) => {
  const response = await request.post('/__e2e/reset');
  expect(response.ok(), await response.text()).toBe(true);
});

export { expect };
