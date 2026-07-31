import type { Page } from '@playwright/test';

import { expect, test } from './fixtures';

test.describe('E2E test data isolation', () => {
  test('permits a test-local mutation', async ({ page }) => {
    await page.goto('/scheduling-overview/1');
    await advanceToRoundMetadata(page);
    await page.locator('#roundName').fill('Nur für diesen Test');
    await page.getByRole('button', { name: 'Prüfungsrunde speichern' }).click();
    await expect(page.getByText('Prüfungsrunde gespeichert')).toBeVisible();
  });

  test('starts from the seeded round after any other test', async ({ page }) => {
    await page.goto('/scheduling-overview/1');
    await advanceToRoundMetadata(page);
    await expect(page.locator('#roundName')).toHaveValue('Winter 2026/27');
  });

  async function advanceToRoundMetadata(page: Page): Promise<void> {
    await page.getByRole('button', { name: 'Verfügbarkeitsanfrage' }).click();
    await expect(page.locator('#roundName')).toBeVisible();
  }
});
