import AxeBuilder from '@axe-core/playwright';
import { expect, test } from './fixtures';
import { expectFinalStyleState } from './style-stability';
import {
  athenCourtLocation,
  planchangeCandidate,
  viewports,
  useDraftRound,
} from './quality-support';

test.describe('master data workflows', () => {
  test.describe.configure({ timeout: 60_000 });

  test('shows a contextual candidate toolbar with aligned filters', async ({ page }) => {
    await useDraftRound(page);
    await page.goto('/scheduling-overview/1');

    const state = page.locator('#holidaySubdivisionCode');
    const location = page.locator('#defaultLocation');
    await expect(location.locator('option:checked')).toHaveText(
      `${athenCourtLocation.name} · ${athenCourtLocation.room}`,
    );
    await expect(
      state.locator('xpath=ancestor::tui-textfield').locator('button[tuiButtonX]'),
    ).toHaveCount(0);
    await expect(
      location.locator('xpath=ancestor::tui-textfield').locator('button[tuiButtonX]'),
    ).toHaveCount(1);

    const excludePublicHolidays = page.locator('#excludePublicHolidays');
    await excludePublicHolidays.check();
    await expect(excludePublicHolidays).toBeChecked();
    await expect(state).toBeEnabled();
    await state.selectOption({ label: 'Nordrhein-Westfalen' });
    await expect(state.locator('option:checked')).toHaveText('Nordrhein-Westfalen');

    await page.goto('/candidates');
    const search = page.locator('#candidateSearch');
    const filter = page.locator('#candidateFilter');
    await expect(page.getByRole('searchbox', { name: 'Suche' })).toBeVisible();
    await expect(page.getByRole('combobox', { name: 'Fachrichtung' })).toBeVisible();
    await expect(page.getByRole('toolbar', { name: 'Prüflingsliste verwalten' })).toContainText(
      'Neuen Prüfling anlegen',
    );
    await expect(search).toHaveAttribute('tuiInput', '');
    await expect(filter.locator('option:checked')).toHaveText('Alle Fachrichtungen');

    const searchBox = await search.locator('xpath=ancestor::tui-textfield').boundingBox();
    const filterBox = await filter.locator('xpath=ancestor::tui-textfield').boundingBox();
    expect(searchBox).not.toBeNull();
    expect(filterBox).not.toBeNull();
    expect(Math.abs(searchBox!.y - filterBox!.y)).toBeLessThan(1);
    expect(Math.abs(searchBox!.height - filterBox!.height)).toBeLessThan(1);
    await search.focus();
    await page.keyboard.press('Tab');
    await expect(filter).toBeFocused();

    await filter.selectOption({ label: 'Systemintegration' });
    await expect(filter.locator('option:checked')).toHaveText('Systemintegration');
    await expect(page.locator('tbody > tr').filter({ hasText: 'von Athen, Helena' })).toBeVisible();
    await expect(page.locator('tbody > tr').filter({ hasText: 'von Athen, Hermia' })).toHaveCount(
      0,
    );

    await search.fill('Philostrate');
    await expect(
      page.locator('tbody > tr').filter({ hasText: 'vom Hof, Philostrate' }),
    ).toBeVisible();
    await expect(page.locator('tbody > tr').filter({ hasText: 'von Athen, Helena' })).toHaveCount(
      0,
    );

    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto('/candidates');
    const mobileSearchBox = await search.locator('xpath=ancestor::tui-textfield').boundingBox();
    const mobileFilterBox = await filter.locator('xpath=ancestor::tui-textfield').boundingBox();
    expect(mobileSearchBox).not.toBeNull();
    expect(mobileFilterBox).not.toBeNull();
    expect(Math.abs(mobileSearchBox!.x - mobileFilterBox!.x)).toBeLessThan(1);
    expect(Math.abs(mobileSearchBox!.width - mobileFilterBox!.width)).toBeLessThan(1);

    await page.goto('/exam-half-years');
    const season = page.locator('#examHalfYearSeason');
    await expect(season.locator('option:checked')).toHaveText('Sommer');
    await expect(
      season.locator('xpath=ancestor::tui-textfield').locator('button[tuiButtonX]'),
    ).toHaveCount(0);
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

    await page.locator('#candidateFirstName').fill(planchangeCandidate.first_name);
    await page.locator('#candidateLastName').fill(planchangeCandidate.last_name);
    await page.locator('#candidateExamNumber').fill('E2E-2026-001');
    await page.getByRole('button', { name: 'Prüfling anlegen', exact: true }).click();

    const row = page.locator('tr').filter({ hasText: 'E2E-2026-001' });
    await expect(row).toBeVisible();
    const deleteButton = row.getByRole('button', { name: 'Löschen' });
    await expect(deleteButton).toHaveAttribute('data-appearance', 'secondary-destructive');
    await expect(row.getByRole('button', { name: 'Bearbeiten' })).toHaveAttribute(
      'data-appearance',
      'secondary',
    );
    await deleteButton.click();
    const confirmationDialog = page.getByRole('dialog', {
      name: `${planchangeCandidate.first_name} ${planchangeCandidate.last_name} löschen?`,
    });
    await expect(confirmationDialog).toBeVisible();
    await confirmationDialog
      .getByRole('button', {
        name: `${planchangeCandidate.first_name} ${planchangeCandidate.last_name} löschen`,
      })
      .click();
    await expect(row).toHaveCount(0);
  });

  test('shows a readable message when the API becomes unavailable', async ({ page }) => {
    await page.goto('/');
    await page.route('**/api/round-summary*', (route) => route.fulfill({ status: 500 }));

    await page.getByRole('button', { name: 'Aktualisieren' }).click();
    const alert = page.getByRole('alert');
    await expect(alert.getByText('Synchronisierung nicht möglich')).toBeVisible();
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

    await expect(page.getByText('Noch keine Prüflinge vorhanden.')).toBeVisible();
    await expect(page.getByRole('button', { name: 'Ersten Prüfling anlegen' })).toBeVisible();
  });

  test('keeps venue card information and actions within the mobile viewport', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto('/locations');

    const card = page.getByRole('article', { name: athenCourtLocation.name });
    await expect(card).toBeVisible();
    await expect(card.getByText(athenCourtLocation.city, { exact: false })).toBeVisible();
    await expect(card.locator(':scope > .app-row-actions')).toBeVisible();

    const layout = await card.evaluate((element) => ({
      cardFits: element.scrollWidth <= element.clientWidth,
      actionsFit: Array.from(element.querySelectorAll('button')).every((button) => {
        const bounds = button.getBoundingClientRect();
        return bounds.left >= 0 && bounds.right <= document.documentElement.clientWidth;
      }),
    }));
    expect(layout.cardFits).toBe(true);
    expect(layout.actionsFit).toBe(true);
  });

  test('searches and filters venues before opening an accessible detail view', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    const providerRequests: string[] = [];
    page.on('request', (request) => {
      if (/tile|nominatim|googleapis|maps/.test(request.url()))
        providerRequests.push(request.url());
    });

    await page.goto('/locations');
    const venueCard = page.getByRole('article', { name: athenCourtLocation.name });
    await expect(venueCard).toBeVisible();
    const search = page.getByRole('searchbox', { name: 'Suche' });
    await search.fill(athenCourtLocation.name);
    await expect(
      page.getByRole('status').filter({ hasText: /von .* sichtbaren Orten/ }),
    ).toContainText('1 von');
    await page.getByRole('combobox', { name: 'Scope' }).selectOption('global');
    await expect(venueCard).toBeVisible();

    await page.getByRole('button', { name: 'Details ansehen' }).click();
    await expect(page).toHaveURL(/\/locations\/\d+$/);
    await expect(page.getByRole('heading', { name: 'Ort und Anreise' })).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Räume' })).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Zulässige Kontakte' })).toBeVisible();
    expect(providerRequests).toEqual([]);
  });

  test('keeps the browser map boundary closed when the provider is off', async ({ page }) => {
    const providerRequests: string[] = [];
    page.on('request', (request) => {
      if (/openstreetmap|google\.com\/maps|nominatim/.test(request.url())) {
        providerRequests.push(request.url());
      }
    });

    const response = await page.goto('/locations');
    expect(response).not.toBeNull();
    if (process.env.LZUG_E2E_PRODUCTION_BUILD === 'true') {
      expect(response?.headers()['content-security-policy']).toContain("frame-src 'none'");
      expect(response?.headers()['referrer-policy']).toBe('no-referrer');
    }
    await page.getByRole('button', { name: 'Details ansehen' }).first().click();

    await expect(page.locator('iframe.locations-map-frame')).toHaveCount(0);
    expect(providerRequests).toEqual([]);
  });

  test('opens the candidate form with the keyboard', async ({ page }) => {
    await page.goto('/candidates');

    const trigger = page.locator('button[aria-controls="candidate-create-editor"]');
    await expect(trigger).toHaveAccessibleName('Neuen Prüfling anlegen');
    await trigger.focus();
    await page.keyboard.press('Enter');

    await expect(page.locator('#candidateFirstName')).toBeVisible();
    await expect(trigger).toBeFocused();
  });

  test('does not offer productive committee creation', async ({ page }) => {
    await page.goto('/committee');

    await expect(page.getByRole('button', { name: 'Neuen Ausschuss anlegen' })).toHaveCount(0);
    await expect(page.locator('#committee-create-editor')).toHaveCount(0);
  });

  test('keeps contextual create editors associated, cancellable and accessible', async ({
    page,
  }) => {
    test.setTimeout(300_000);
    const editors = [
      {
        path: '/locations',
        action: 'Prüfungsort anlegen',
        editor: '#location-create-editor',
        input: '#locationName',
      },
      {
        path: '/candidates',
        action: 'Neuen Prüfling anlegen',
        editor: '#candidate-create-editor',
        input: '#candidateFirstName',
      },
      {
        path: '/committee',
        action: 'Prüfer hinzufügen',
        editor: '#member-create-editor',
        input: '#memberFirstName',
      },
    ] as const;

    for (const viewport of viewports) {
      await page.setViewportSize(viewport);

      for (const item of editors) {
        await test.step(`${viewport.name}: ${item.action}`, async () => {
          await page.goto(item.path);
          const refreshButton = page.getByRole('button', { name: 'Aktualisieren' });
          await expect(refreshButton).toBeEnabled({ timeout: 30_000 });
          await expect(refreshButton).toHaveCSS('opacity', '1');
          const trigger = page.locator(
            `${item.editor === '#candidate-create-editor' ? '.app-list-toolbar ' : ''}button[aria-controls="${item.editor.slice(1)}"]`,
          );
          const editor = page.locator(item.editor);

          await expect(trigger).toHaveAccessibleName(item.action);
          expect(
            await trigger.evaluate(
              (element) =>
                !!element.closest('.app-panel-header') || !!element.closest('.app-list-toolbar'),
            ),
          ).toBe(true);
          await expect(trigger).toHaveAttribute('aria-expanded', 'false');
          await expect(editor).toBeHidden();

          await trigger.click();
          await expect(trigger).toHaveAttribute('aria-expanded', 'true');
          await expect(editor).toBeVisible();
          await page.locator(item.input).fill('Nicht speichern');

          const dimensions = await page.evaluate(() => ({
            clientWidth: document.documentElement.clientWidth,
            scrollWidth: document.documentElement.scrollWidth,
          }));
          expect(dimensions.scrollWidth).toBe(dimensions.clientWidth);

          await expectFinalStyleState(page);
          const results = await new AxeBuilder({ page }).analyze();
          expect(results.violations, `${viewport.name} ${item.action}`).toEqual([]);

          await editor.getByRole('button', { name: 'Abbrechen', exact: true }).click();
          await expect(editor).toBeHidden();
          await expect(trigger).toHaveAttribute('aria-expanded', 'false');
          await expect(page.locator(item.input)).toHaveValue('');
          await expect(trigger).toBeFocused();
        });
      }
    }
  });
});
