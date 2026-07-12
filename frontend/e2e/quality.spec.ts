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
    await expect(page.locator('c-badge').filter({ hasText: 'Plan bestätigt' })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Plan bestätigen' })).toBeDisabled();
  });

  test('navigates through the application views', async ({ page }) => {
    await page.goto('/');

    for (const view of ['Prüflinge', 'Ausschuss', 'Terminplanung', 'Prüfungsorte']) {
      await page.getByRole('button', { name: view, exact: true }).click();
      await expect(page.getByRole('heading', { name: view })).toBeVisible();
    }
  });

  test('keeps required candidate fields enforced', async ({ page }) => {
    await page.goto('/');
    await page.getByRole('button', { name: 'Prüflinge', exact: true }).click();

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
    await page.getByRole('button', { name: 'Prüflinge', exact: true }).click();

    await page.locator('#candidateFirstName').fill('E2E');
    await page.locator('#candidateLastName').fill('Testperson');
    await page.locator('#candidateExamNumber').fill('E2E-2026-001');
    await page.getByRole('button', { name: 'Prüfling anlegen' }).click();

    const row = page.locator('tr').filter({ hasText: 'E2E-2026-001' });
    await expect(row).toBeVisible();
    await row.getByRole('button', { name: 'Löschen' }).click();
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
    await page.getByRole('button', { name: 'Prüflinge', exact: true }).click();

    await expect(page.getByText('Keine passenden Prüflinge vorhanden.')).toBeVisible();
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
    await page.getByRole('button', { name: 'Terminplanung', exact: true }).click();
    const results = await new AxeBuilder({ page }).analyze();
    expect(results.violations).toEqual([]);
  });
});
