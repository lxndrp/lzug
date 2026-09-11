import AxeBuilder from '@axe-core/playwright';
import { expect, test } from './fixtures';
import { expectReadableContrast } from './quality-support';

test('keeps the maintenance shell usable and resumes only after a manual check', async ({
  page,
}) => {
  let state = 'migration_required';
  let checks = 0;
  let business = 0;
  page.on('request', (request) => {
    if (/\/api\//.test(request.url()) && !request.url().endsWith('/api/lifecycle')) business++;
  });
  await page.route('**/api/lifecycle', (route) => {
    checks++;
    return route.fulfill({ json: { state, ready: state === 'ready', reason: '/private/secret' } });
  });
  await page.goto('/dashboard');
  const heading = page.getByRole('heading', { name: 'Datenaktualisierung erforderlich' });
  await expect(heading).toBeVisible();
  await expect(heading).toBeFocused();
  await expect(page).toHaveTitle(/nicht verfügbar/);
  await expect(page.getByRole('status')).toContainText('Zuletzt geprüft');
  expect(checks).toBe(1);
  expect(business).toBe(0);
  await expect(page.getByRole('main')).not.toContainText('/private/secret');
  await page.getByText('Hinweise für Betreiber', { exact: true }).click();
  await expect(page.getByRole('main')).toContainText('lzug-admin system doctor');
  await expect(page.getByRole('main')).toContainText('lzug-admin upgrade status');
  await expect(page.getByRole('main')).toContainText('lzug-admin upgrade apply');
  state = 'ready';
  await page.getByRole('button', { name: 'Status erneut prüfen' }).click();
  await expect(page.getByRole('heading', { name: 'Übersicht', exact: true })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Übersicht', exact: true })).toBeFocused();
  expect(checks).toBe(2);
});

test('replaces an active workspace after a structured 503 without replay', async ({ page }) => {
  await page.goto('/dashboard');
  await expect(page.getByRole('heading', { name: 'Übersicht', exact: true })).toBeVisible();
  await page.route('**/api', (route) =>
    route.fulfill({
      status: 503,
      json: {
        error: { code: 'runtime_not_ready', state: 'maintenance', ready: false },
      },
    }),
  );
  await page.getByRole('button', { name: 'Aktualisieren', exact: true }).click();
  const heading = page.getByRole('heading', { name: 'Anwendung wird gewartet' });
  await expect(heading).toBeVisible();
  await expect(heading).toBeFocused();
  await expect(page.locator('.app-feedback')).toHaveCount(0);
});

test('lifecycle states preserve contrast, focus and mobile reflow @a11y', async ({ page }) => {
  test.setTimeout(180_000);
  const states = [
    'initializing',
    'maintenance',
    'migration_required',
    'migrating',
    'error',
    'stopping',
    'stopped',
  ];
  for (const colorScheme of ['light', 'dark'] as const) {
    await page.emulateMedia({ colorScheme });
    await page.setViewportSize({ width: 320, height: 800 });
    for (const state of states) {
      await page.route('**/api/lifecycle', (route) =>
        route.fulfill({ json: { state, ready: false } }),
      );
      await page.goto('/dashboard');
      const heading = page.locator('h1');
      await expect(heading).toBeFocused();
      await expectReadableContrast(heading);
      await page.getByText('Hinweise für Betreiber', { exact: true }).click();
      expect(
        await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth),
      ).toBe(true);
      expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([]);
      await page.unroute('**/api/lifecycle');
    }
  }
});
