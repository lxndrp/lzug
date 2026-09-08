import { expect, test } from './fixtures';
import { athenCommittee } from './quality-support';

test.describe('shell navigation', () => {
  test.describe.configure({ timeout: 60_000 });

  test('navigates through the application views', async ({ page }) => {
    await page.goto('/');
    await expect(page.getByRole('heading', { name: 'Übersicht' })).toBeVisible({
      timeout: 30_000,
    });
    await expect(page.locator('.app-progress')).toHaveCount(0);
    await expect(page.getByLabel('Aktueller Prüfungskontext')).toBeVisible();

    for (const [view, path] of [
      ['Prüflinge', '/candidates'],
      ['Terminorganisationen', '/scheduling-overview'],
      ['Prüfungspläne', '/confirmed-plans'],
      ['Prüfungsausschüsse', '/committee'],
      ['Prüfungsorte', '/locations'],
    ] as const) {
      await page.getByRole('link', { name: view, exact: true }).click();
      await expect(page).toHaveURL(path);
      await expect(page.getByRole('heading', { name: view })).toBeVisible();
    }

    await expect(page.getByRole('link', { name: 'Terminplanung', exact: true })).toHaveCount(0);
    await expect(
      page.getByRole('link', { name: 'Terminorganisation fortsetzen', exact: true }),
    ).toHaveCount(0);
  });

  test('keeps the active exam context visible in contextual views', async ({ page }) => {
    for (const path of [
      '/candidates',
      '/scheduling-overview',
      '/confirmed-plans',
      '/scheduling-overview/1',
    ]) {
      await page.goto(path);
      const context = page.getByLabel('Aktueller Prüfungskontext');
      await expect(context).toBeVisible();
      await expect(context).toContainText('Winter 2026');
      await expect(context).toContainText('Winter 2026/27');
      await expect(context).toContainText(athenCommittee.name);
    }
  });

  test('keeps the mobile sidebar state, semantics, and focus synchronized', async ({ page }) => {
    await page.setViewportSize({ width: 320, height: 844 });
    await page.goto('/dashboard');

    const sidebarToggle = page.locator('.app-sidebar-toggle');
    const sidebar = page.locator('#appSidebar');
    const accessibleSidebar = page.getByRole('complementary', {
      name: 'Prüfungsverwaltung',
    });
    await expect(sidebarToggle).toBeVisible();
    await expect(sidebarToggle).toHaveAttribute('aria-label', 'Navigation öffnen');
    await expect(sidebarToggle).toHaveAttribute('aria-expanded', 'false');
    await expect(sidebar).toHaveAttribute('inert', '');
    await expect(sidebar).toHaveAttribute('aria-hidden', 'true');
    await expect(accessibleSidebar).toHaveCount(0);
    const iconWidth = await sidebarToggle
      .locator('svg')
      .evaluate((element) => element.getBoundingClientRect().width);
    expect(iconWidth).toBeGreaterThan(0);

    await sidebarToggle.click();

    await expect(sidebar).toHaveClass(/show/);
    await expect(sidebar).not.toHaveAttribute('inert');
    await expect(sidebar).not.toHaveAttribute('aria-hidden');
    await expect(accessibleSidebar).toBeVisible();
    await expect(sidebarToggle).toHaveAttribute('aria-label', 'Navigation schließen');
    await expect(sidebarToggle).toHaveAttribute('aria-expanded', 'true');
    const sidebarClose = page.locator('.app-sidebar-close');
    await expect(sidebarClose).toBeVisible();
    await expect(sidebarClose).toBeFocused();

    await page.keyboard.press('Escape');

    await expect(sidebar).toHaveClass(/hide/);
    await expect(sidebar).toHaveAttribute('inert', '');
    await expect(sidebar).toHaveAttribute('aria-hidden', 'true');
    await expect(accessibleSidebar).toHaveCount(0);
    await expect(sidebarToggle).toHaveAttribute('aria-label', 'Navigation öffnen');
    await expect(sidebarToggle).toHaveAttribute('aria-expanded', 'false');
    await expect(sidebarToggle).toBeFocused();

    await sidebarToggle.click();
    await page.locator('.app-sidebar-backdrop').click({ position: { x: 300, y: 400 } });

    await expect(sidebar).toHaveAttribute('inert', '');
    await expect(sidebar).toHaveAttribute('aria-hidden', 'true');
    await expect(sidebarToggle).toBeFocused();

    await sidebarToggle.click();
    await expect(sidebarClose).toBeFocused();
    await sidebarClose.click();

    await expect(sidebar).toHaveClass(/hide/);
    await expect(sidebar).toHaveAttribute('inert', '');
    await expect(sidebar).toHaveAttribute('aria-hidden', 'true');
    await expect(sidebarToggle).toHaveAttribute('aria-label', 'Navigation öffnen');
    await expect(sidebarToggle).toHaveAttribute('aria-expanded', 'false');
    await expect(sidebarToggle).toBeFocused();
  });

  test('keeps application views within the mobile viewport', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });

    for (const path of [
      '/dashboard',
      '/scheduling-overview',
      '/confirmed-plans',
      '/candidates',
      '/committee',
      '/scheduling-overview/1',
      '/locations',
      '/notifications',
    ]) {
      await page.goto(path);
      const dimensions = await page.evaluate(() => ({
        clientWidth: document.documentElement.clientWidth,
        scrollWidth: document.documentElement.scrollWidth,
      }));
      expect(dimensions.scrollWidth).toBe(dimensions.clientWidth);
    }
  });

  test('keeps development-only prototype content out of production navigation', async ({
    page,
  }) => {
    await page.goto('/dashboard');
    await expect(page.getByText('Taiga-Prototyp')).toHaveCount(0);
    await expect(page.getByText('Entwicklung', { exact: true })).toHaveCount(0);
  });
});
