import AxeBuilder from '@axe-core/playwright';
import { expect, test } from '@playwright/test';

test.describe('lzug browser workflows', () => {
  test('generates and confirms a planning proposal', async ({ page }) => {
    await page.goto('/');

    await expect(page.getByRole('heading', { name: 'Winter 2026/27' })).toBeVisible();

    await page.getByRole('button', { name: 'Planung erzeugen' }).click();
    await expect(page.getByText('Validierungsreport')).toBeVisible();
    await expect(page.getByText('16 geplante Prüfungstermine')).toBeVisible();

    await page.getByRole('button', { name: 'Plan bestätigen' }).click();
    await page.getByRole('button', { name: 'Plan verbindlich bestätigen' }).click();
    await expect(page.locator('c-badge').filter({ hasText: 'Plan bestätigt' })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Plan bestätigen' })).toBeDisabled();
  });

  test('navigates through the application views', async ({ page }) => {
    await page.goto('/');

    for (const [view, path] of [
      ['Prüflinge', '/candidates'],
      ['Ausschuss', '/committee'],
      ['Terminplanung', '/planning'],
      ['Prüfungsorte', '/locations'],
    ] as const) {
      await page.getByRole('link', { name: view, exact: true }).click();
      await expect(page).toHaveURL(path);
      await expect(page.getByRole('heading', { name: view })).toBeVisible();
    }
  });

  test('opens and closes the sidebar on a narrow viewport', async ({ page }) => {
    await page.setViewportSize({ width: 320, height: 844 });
    await page.goto('/dashboard');

    const sidebarToggle = page.locator('.app-sidebar-toggle');
    const sidebar = page.getByRole('complementary', { name: 'Prüfungsverwaltung' });
    await expect(sidebarToggle).toBeVisible();
    await expect(sidebarToggle).toHaveAttribute('aria-label', 'Navigation öffnen');
    await expect(sidebarToggle).toHaveAttribute('aria-expanded', 'false');
    const iconWidth = await sidebarToggle
      .locator('.header-toggler-icon')
      .evaluate((element) => element.getBoundingClientRect().width);
    expect(iconWidth).toBeGreaterThan(0);

    await sidebarToggle.click();

    await expect(sidebar).toHaveClass(/show/);
    await expect(sidebarToggle).toHaveAttribute('aria-label', 'Navigation schließen');
    await expect(sidebarToggle).toHaveAttribute('aria-expanded', 'true');
    const sidebarClose = page.locator('.app-sidebar-close');
    await expect(sidebarClose).toBeVisible();
    await sidebarClose.click();

    await expect(sidebar).toHaveClass(/hide/);
    await expect(sidebarToggle).toHaveAttribute('aria-label', 'Navigation öffnen');
    await expect(sidebarToggle).toHaveAttribute('aria-expanded', 'false');
  });

  test('updates exam round metadata and keeps it after reload', async ({ page }) => {
    await page.goto('/planning');

    await expect(page.locator('#roundName')).toHaveValue('Winter 2026/27');
    await page.locator('#roundName').fill('Sommer 2027');
    await page.locator('#availabilityDeadline').fill('2027-04-15T18:00');
    await page.locator('#availabilityReminder').fill('2027-04-08T09:00');

    const updateResponsePromise = page.waitForResponse(
      (response) =>
        response.url().endsWith('/api/exam-rounds/1') && response.request().method() === 'PATCH',
    );
    await page.getByRole('button', { name: 'Prüfungsrunde speichern' }).click();

    const updateResponse = await updateResponsePromise;
    expect(updateResponse.status(), await updateResponse.text()).toBe(200);
    await expect(page.getByText('Prüfungsrunde gespeichert')).toBeVisible();

    await page.reload();
    await expect(page.locator('#roundName')).toHaveValue('Sommer 2027');
    await expect(page.locator('#availabilityDeadline')).toHaveValue('2027-04-15T18:00');
    await expect(page.locator('#availabilityReminder')).toHaveValue('2027-04-08T09:00');
  });

  test('generates possible exam days while excluding state holidays', async ({ page }) => {
    await page.goto('/planning');

    const weekFrom = page.locator('#weekFrom');
    const weekTo = page.locator('#weekTo');
    await expect(weekFrom).toHaveValue('2026-W47');
    await expect(weekTo).toHaveValue('2026-W49');
    await weekFrom.fill('2026-W23');
    await weekFrom.press('Tab');
    await weekTo.fill('2026-W23');
    await weekTo.press('Tab');
    await page.getByText('Gesetzliche Feiertage ausschließen', { exact: true }).click();
    await expect(page.locator('#excludePublicHolidays')).toBeChecked();
    await page.locator('#holidaySubdivisionCode').selectOption({ label: 'Nordrhein-Westfalen' });

    const settingsResponsePromise = page.waitForResponse(
      (response) =>
        response.url().endsWith('/api/planning-settings') && response.request().method() === 'POST',
    );
    const generationResponsePromise = page.waitForResponse(
      (response) =>
        response.url().endsWith('/api/candidate-exam-days/generate') &&
        response.request().method() === 'POST',
    );
    await page.getByRole('button', { name: 'Mögliche Tage berechnen' }).click();

    const settingsResponse = await settingsResponsePromise;
    expect(settingsResponse.status(), await settingsResponse.text()).toBe(200);
    const generationResponse = await generationResponsePromise;
    expect(generationResponse.status(), await generationResponse.text()).toBe(200);

    await expect(page.getByText('4 Tage angelegt')).toBeVisible();
    await expect(page.getByText('1 Feiertage ausgeschlossen')).toBeVisible();
    await expect(page.getByText('04.06.2026 · Fronleichnam')).toBeVisible();
  });

  test('keeps required candidate fields enforced', async ({ page }) => {
    await page.goto('/');
    await page.getByRole('link', { name: 'Prüflinge', exact: true }).click();
    await page.getByText('Neuen Prüfling anlegen', { exact: true }).click();

    const firstName = page.locator('#candidateFirstName');
    const lastName = page.locator('#candidateLastName');
    const examNumber = page.locator('#candidateExamNumber');
    await expect(firstName).toBeVisible();
    await expect(firstName).toHaveAttribute('required', '');
    await expect(lastName).toHaveAttribute('required', '');
    await expect(examNumber).toHaveAttribute('required', '');
  });

  test('creates and deletes a candidate through the browser', async ({ page }) => {
    await page.goto('/');
    await page.getByRole('link', { name: 'Prüflinge', exact: true }).click();
    await page.getByText('Neuen Prüfling anlegen', { exact: true }).click();

    await page.locator('#candidateFirstName').fill('E2E');
    await page.locator('#candidateLastName').fill('Testperson');
    await page.locator('#candidateExamNumber').fill('E2E-2026-001');
    await page.getByRole('button', { name: 'Prüfling anlegen' }).click();

    const row = page.locator('tr').filter({ hasText: 'E2E-2026-001' });
    await expect(row).toBeVisible();
    await row.getByRole('button', { name: 'Löschen' }).click();
    await page.getByRole('button', { name: 'Prüfling löschen' }).click();
    await expect(row).toHaveCount(0);
  });

  test('shows a readable message when the API becomes unavailable', async ({ page }) => {
    await page.goto('/');
    await page.route('**/api/round-summary*', (route) => route.fulfill({ status: 500 }));

    await page.getByRole('button', { name: 'Aktualisieren' }).click();
    await expect(page.getByText('Backend nicht erreichbar')).toBeVisible();
  });

  test('renders an empty candidate list without breaking the view', async ({ page }) => {
    await page.route('**/api/candidates', (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ items: [], _links: {} }),
      }),
    );
    await page.goto('/');
    await page.getByRole('link', { name: 'Prüflinge', exact: true }).click();

    await expect(page.getByText('Keine passenden Prüflinge vorhanden.')).toBeVisible();
  });

  test('keeps application views within the mobile viewport', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });

    for (const path of ['/dashboard', '/candidates', '/committee', '/planning', '/locations']) {
      await page.goto(path);
      const dimensions = await page.evaluate(() => ({
        clientWidth: document.documentElement.clientWidth,
        scrollWidth: document.documentElement.scrollWidth,
      }));
      expect(dimensions.scrollWidth).toBe(dimensions.clientWidth);
    }
  });

  test('keeps table actions scrollable instead of covering mobile data', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto('/locations');

    const scrollRegion = page.locator('.app-table-scroll');
    const locationHeader = page.getByRole('columnheader', { name: 'Ort' });
    const actionHeader = page.getByRole('columnheader', { name: 'Aktion' });
    await expect(locationHeader).toBeInViewport();
    await expect(actionHeader).not.toBeInViewport();
    await expect
      .poll(() => scrollRegion.evaluate((element) => element.scrollWidth > element.clientWidth))
      .toBe(true);
  });

  test('opens the candidate form with the keyboard', async ({ page }) => {
    await page.goto('/candidates');

    const trigger = page.getByText('Neuen Prüfling anlegen', { exact: true });
    await trigger.focus();
    await page.keyboard.press('Enter');

    await expect(page.locator('#candidateFirstName')).toBeVisible();
    await expect(trigger).toBeFocused();
  });
});

test.describe('lzug accessibility', () => {
  test('has no detectable accessibility violations on the dashboard @a11y', async ({ page }) => {
    await page.goto('/');
    const results = await new AxeBuilder({ page }).analyze();
    expect(results.violations).toEqual([]);
  });

  test('has no detectable accessibility violations on planning @a11y', async ({ page }) => {
    await page.goto('/');
    await page.getByRole('link', { name: 'Terminplanung', exact: true }).click();
    const results = await new AxeBuilder({ page }).analyze();
    expect(results.violations).toEqual([]);
  });

  for (const view of [
    { name: 'Prüflinge', path: '/candidates' },
    { name: 'Ausschuss', path: '/committee' },
    { name: 'Prüfungsorte', path: '/locations' },
  ]) {
    test(`has no detectable accessibility violations on ${view.name} @a11y`, async ({ page }) => {
      await page.goto(view.path);
      const results = await new AxeBuilder({ page }).analyze();
      expect(results.violations).toEqual([]);
    });
  }
});
