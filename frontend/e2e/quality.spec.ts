import AxeBuilder from '@axe-core/playwright';
import type { Page } from '@playwright/test';
import { expect, test } from './fixtures';

const productiveViews = [
  { name: 'Übersicht', path: '/dashboard' },
  { name: 'Terminorganisationen', path: '/scheduling-overview' },
  { name: 'Prüfungspläne', path: '/confirmed-plans' },
  { name: 'Prüflinge', path: '/candidates' },
  { name: 'Prüfungsausschüsse', path: '/committee' },
  { name: 'Terminorganisation', path: '/scheduling-overview/1' },
  { name: 'Prüfungsorte', path: '/locations' },
] as const;

function overviewItem(
  id: number,
  name: string,
  status: string,
  statusGroup: 'draft' | 'coordination' | 'planning' | 'confirmed',
  canContinue: boolean,
) {
  return {
    id,
    name,
    status,
    status_group: statusGroup,
    committee_name: 'Prüfungsausschuss Teststadt 1',
    exam_half_year: { id: 1, season: 'winter', year: 2026, status: 'active' },
    calendar_week_from: '2026-W47',
    calendar_week_to: '2026-W49',
    can_continue: canContinue,
    _links: {},
  };
}

const colorSchemes = ['light', 'dark'] as const;
const viewports = [
  { name: 'desktop', width: 1440, height: 1000 },
  { name: 'mobile', width: 390, height: 844 },
] as const;

async function useDraftRound(page: Page): Promise<void> {
  const response = await page.request.patch('/api/exam-rounds/1', {
    data: { status: 'draft' },
  });
  expect(response.status(), await response.text()).toBe(200);
}

test.describe('lzug browser workflows', () => {
  test.describe.configure({ timeout: 60_000 });

  test('resumes coordination, plans, confirms, and opens the persisted exam plan', async ({
    page,
  }) => {
    await page.goto('/scheduling-overview/1');

    await expect(
      page.getByRole('navigation', { name: 'Schritte der Terminorganisation' }),
    ).toBeVisible();
    await expect(page.getByText('In Abstimmung', { exact: true })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Rückmeldungen' })).toHaveAttribute(
      'aria-current',
      'step',
    );
    await expect(page.getByRole('button', { name: 'Zeitraum' })).toBeDisabled();
    await expect(page.getByLabel('Verfügbarkeiten nach Mitglied und Prüfungstag')).toBeVisible();

    await page.getByRole('button', { name: 'Planungsvorschlag erzeugen' }).click();
    await expect(page.getByText('Planung', { exact: true }).first()).toBeVisible();
    await expect(page.getByText('Zusammenfassung vor der Bestätigung')).toBeVisible();
    await expect(page.getByRole('button', { name: 'Plan bestätigen' })).toBeEnabled();

    await page.getByRole('button', { name: 'Plan bestätigen' }).click();
    await page.getByRole('button', { name: 'Plan verbindlich bestätigen' }).click();
    await expect(page).toHaveURL('/confirmed-plans/1');
    await expect(page.getByRole('heading', { name: 'Prüfungspläne' })).toBeVisible();
    await expect(page.locator('.app-confirmed-plan').getByText('Winter 2026/27')).toBeVisible();

    await page.goto('/scheduling-overview/1');
    await expect(page).toHaveURL('/confirmed-plans/1');
    await expect(page.getByRole('heading', { name: 'Prüfungspläne' })).toBeVisible();
  });

  test('groups terminorganisationen and continues an eligible round', async ({ page }) => {
    await page.route('**/api/scheduling-overview', (route) =>
      route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({
          items: [
            overviewItem(1, 'Offene Runde', 'draft', 'draft', true),
            overviewItem(2, 'Rückmeldungen', 'availability_requested', 'coordination', true),
            overviewItem(3, 'Vorschlag', 'plan_proposed', 'planning', true),
            overviewItem(4, 'Bestätigte Runde', 'plan_confirmed', 'confirmed', false),
          ],
          _links: {},
        }),
      }),
    );
    await page.goto('/scheduling-overview');

    await expect(page.getByRole('heading', { name: 'Terminorganisationen' })).toBeVisible();
    await expect(page.getByText('Entwurf', { exact: true }).first()).toBeVisible();
    await expect(page.getByText('In Abstimmung', { exact: true })).toBeVisible();
    await expect(page.getByText('Planung', { exact: true }).first()).toBeVisible();
    await expect(page.getByText('Bestätigt', { exact: true }).first()).toBeVisible();
    await page.getByRole('button', { name: 'Neue Terminorganisation' }).click();
    await expect(page).toHaveURL('/scheduling-overview/1');
    await expect(
      page.getByRole('navigation', { name: 'Schritte der Terminorganisation' }),
    ).toBeVisible();
    await page.goBack();
    await expect(page).toHaveURL('/scheduling-overview');
    await expect(page.getByRole('heading', { name: 'Terminorganisationen' })).toBeVisible();
  });

  test('moves a prepared draft into coordination', async ({ page }) => {
    const draftResponse = await page.request.patch('/api/exam-rounds/1', {
      data: { status: 'draft' },
    });
    expect(draftResponse.status(), await draftResponse.text()).toBe(200);

    await page.goto('/scheduling-overview/1');
    await expect(page.getByText('Entwurf', { exact: true })).toBeVisible();
    await page.getByRole('button', { name: 'Weiter' }).click();
    await page.getByRole('button', { name: 'Weiter' }).click();

    const requestResponsePromise = page.waitForResponse(
      (response) =>
        response.url().endsWith('/api/exam-rounds/1/request-availabilities') &&
        response.request().method() === 'POST',
    );
    await page.getByRole('button', { name: 'Verfügbarkeiten anfragen' }).click();
    const requestResponse = await requestResponsePromise;
    expect(requestResponse.status(), await requestResponse.text()).toBe(200);
    await expect(page.getByText('In Abstimmung', { exact: true })).toBeVisible();
    await expect(page.getByLabel('Verfügbarkeiten nach Mitglied und Prüfungstag')).toBeVisible();
  });

  test('shows confirmed plans correctly on desktop and mobile', async ({ page }) => {
    await page.route('**/api/confirmed-plans', (route) =>
      route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({
          items: [
            confirmedPlan(1, 'Prüfungsausschuss Plan Alpha', 'Prüfling', 'Plan-Alpha', 'mep'),
            confirmedPlan(2, 'Prüfungsausschuss Plan Beta', 'Prüfling', 'Plan-Beta', 'regular'),
          ],
          _links: {},
        }),
      }),
    );

    for (const viewport of viewports) {
      await test.step(viewport.name, async () => {
        await page.setViewportSize(viewport);
        await page.goto('/confirmed-plans');
        await expect(page.getByRole('heading', { name: 'Prüfungspläne' })).toBeVisible();
        await expect(page.getByText('08:30–09:30', { exact: true })).toBeVisible();
        await expect(page.getByText('MEP-Prüfung')).toBeVisible();
        await expect(page.getByText('Ersatzprüfer/in')).toBeVisible();
        await expect(page.getByText('Arbeitgeber', { exact: true })).toBeVisible();
        await expect(page.getByText('Arbeitnehmer', { exact: true })).toBeVisible();
        await expect(page.getByText('Schule', { exact: true })).toBeVisible();
        await expect(page.getByText('employee', { exact: true })).toHaveCount(0);

        for (const selector of ['.app-confirmed-day-header', '.app-confirmed-crew']) {
          const dimensions = await page.locator(selector).evaluate((element) => {
            const rectangle = element.getBoundingClientRect();
            return {
              clientWidth: element.clientWidth,
              right: rectangle.right,
              scrollWidth: element.scrollWidth,
              viewportWidth: document.documentElement.clientWidth,
            };
          });
          expect(dimensions.right).toBeLessThanOrEqual(dimensions.viewportWidth);
          expect(dimensions.scrollWidth).toBeLessThanOrEqual(dimensions.clientWidth);
        }

        const pageDimensions = await page.evaluate(() => ({
          clientWidth: document.documentElement.clientWidth,
          scrollWidth: document.documentElement.scrollWidth,
        }));
        expect(pageDimensions.scrollWidth).toBe(pageDimensions.clientWidth);

        const slotTable = page.getByLabel('Prüfungsslots');
        const tableDimensions = await slotTable.evaluate((element) => ({
          clientWidth: element.clientWidth,
          scrollWidth: element.scrollWidth,
        }));
        if (viewport.name === 'mobile') {
          expect(tableDimensions.scrollWidth).toBeGreaterThan(tableDimensions.clientWidth);
        } else {
          expect(tableDimensions.scrollWidth).toBe(tableDimensions.clientWidth);
        }

        const accessibility = await new AxeBuilder({ page })
          .include('app-confirmed-plans')
          .analyze();
        expect(accessibility.violations, `${viewport.name} confirmed plans`).toEqual([]);
      });
    }

    const northTab = page.getByRole('tab', { name: 'Prüfungsausschuss Plan Alpha' });
    await northTab.focus();
    await page.keyboard.press('ArrowRight');
    await expect(page.getByRole('tab', { name: 'Prüfungsausschuss Plan Beta' })).toHaveAttribute(
      'aria-selected',
      'true',
    );
    await expect(page.getByText('Prüfling Plan-Beta')).toBeVisible();
  });

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
      await expect(context).toContainText('Prüfungsausschuss Teststadt 1');
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
      .locator('.header-toggler-icon')
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

  test('updates exam round metadata and keeps it after reload', async ({ page }) => {
    await page.goto('/scheduling-overview/1');
    await advanceToRoundMetadata(page);

    await expect(page.locator('#roundName')).toHaveValue('Winter 2026/27', { timeout: 30_000 });
    await page.locator('#roundName').fill('Sommer 2027');
    await page.locator('#availabilityDeadline').fill('15.04.2027, 18:00');
    await page.locator('#availabilityReminder').fill('08.04.2027, 09:00');

    const updateResponsePromise = page.waitForResponse(
      (response) =>
        response.url().endsWith('/api/exam-rounds/1') && response.request().method() === 'PATCH',
    );
    await page.getByRole('button', { name: 'Prüfungsrunde speichern' }).click();

    const updateResponse = await updateResponsePromise;
    expect(updateResponse.status(), await updateResponse.text()).toBe(200);
    await expect(page.getByText('Prüfungsrunde gespeichert')).toBeVisible();

    await page.reload();
    await advanceToRoundMetadata(page);
    await expect(page.locator('#roundName')).toHaveValue('Sommer 2027');
    await expect(page.locator('#availabilityDeadline')).toHaveValue('15.04.2027, 18:00');
    await expect(page.locator('#availabilityReminder')).toHaveValue('08.04.2027, 09:00');

    await page.getByRole('button', { name: 'Abbrechen und zur Übersicht' }).click();
    await expect(page).toHaveURL('/scheduling-overview');
    await page.getByRole('button', { name: 'Rückmeldungen ansehen' }).click();
    await expect(page).toHaveURL('/scheduling-overview/1');
    await expect(page.getByLabel('Verfügbarkeiten nach Mitglied und Prüfungstag')).toBeVisible();

    const persistedRoundResponse = await page.request.get('/api/exam-rounds/1');
    expect(persistedRoundResponse.status(), await persistedRoundResponse.text()).toBe(200);
    const persistedRound = (await persistedRoundResponse.json()) as Record<string, unknown>;
    expect(persistedRound['name']).toBe('Sommer 2027');
    expect(persistedRound['availability_deadline']).toBe('2027-04-15 18:00:00');
    expect(persistedRound['availability_reminder_at']).toBe('2027-04-08 09:00:00');
  });

  async function advanceToRoundMetadata(page: Page): Promise<void> {
    await page.getByRole('button', { name: 'Verfügbarkeitsanfrage' }).click();
    await expect(page.getByRole('button', { name: 'Verfügbarkeitsanfrage' })).toHaveAttribute(
      'aria-current',
      'step',
    );
  }

  test('creates a half-year and its committee-specific exam round', async ({ page }) => {
    await page.goto('/exam-half-years');
    await expect(page.getByRole('heading', { name: 'Prüfungshalbjahre' })).toBeVisible({
      timeout: 30_000,
    });

    const createHalfYearButton = page
      .locator('.app-panel-header')
      .getByRole('button', { name: 'Prüfungshalbjahr anlegen' });
    await createHalfYearButton.click();
    await page.locator('#examHalfYearSeason').selectOption('summer');
    await page.locator('#examHalfYearYear').fill('2027');
    const halfYearResponse = page.waitForResponse(
      (response) =>
        response.url().endsWith('/api/exam-half-years') && response.request().method() === 'POST',
    );
    await page
      .getByRole('button', { name: 'Prüfungshalbjahr anlegen', exact: true })
      .last()
      .click();
    expect((await halfYearResponse).status()).toBe(201);

    await page.locator('#roundCommittee').selectOption('1');
    await expect(page.locator('#roundCreatedByMember option[value="1"]')).toHaveCount(1);
    await page.locator('#roundCreatedByMember').selectOption('1');
    const roundResponse = page.waitForResponse(
      (response) =>
        response.url().endsWith('/api/exam-rounds') && response.request().method() === 'POST',
    );
    await page.getByRole('button', { name: 'Ausschuss hinzufügen' }).click();
    expect((await roundResponse).status()).toBe(201);
    await expect(page).toHaveURL('/dashboard');
    await expect(page.getByLabel('Aktueller Prüfungskontext')).toContainText('Sommer 2027');
  });

  test('generates possible exam days while excluding state holidays', async ({ page }) => {
    await useDraftRound(page);
    await page.goto('/scheduling-overview/1');

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

    await page.getByRole('button', { name: 'Weiter' }).click();
    await expect(page.getByText('4 Tage angelegt')).toBeVisible();
    await expect(page.getByText('1 Feiertage ausgeschlossen')).toBeVisible();
    await expect(page.getByText('04.06.2026 · Fronleichnam')).toBeVisible();
  });

  test('shows a contextual candidate toolbar with aligned filters', async ({ page }) => {
    await useDraftRound(page);
    await page.goto('/scheduling-overview/1');

    const state = page.locator('#holidaySubdivisionCode');
    const location = page.locator('#defaultLocation');
    const updater = page.locator('#updatedByMember');
    await expect(location.locator('option:checked')).toHaveText(
      'Prüfungszentrum Alpha (Test) · Testraum A-01',
    );
    await expect(updater.locator('option:checked')).toHaveText('Testperson Alpha');
    await expect(
      state.locator('xpath=ancestor::tui-textfield').locator('button[tuiButtonX]'),
    ).toHaveCount(0);
    await expect(
      location.locator('xpath=ancestor::tui-textfield').locator('button[tuiButtonX]'),
    ).toHaveCount(1);
    await expect(
      updater.locator('xpath=ancestor::tui-textfield').locator('button[tuiButtonX]'),
    ).toHaveCount(0);

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
    await expect(page.locator('tbody > tr').filter({ hasText: 'Beta, Prüfling' })).toBeVisible();
    await expect(page.locator('tbody > tr').filter({ hasText: 'Alpha, Prüfling' })).toHaveCount(0);

    await search.fill('Zeta');
    await expect(page.locator('tbody > tr').filter({ hasText: 'Zeta, Prüfling' })).toBeVisible();
    await expect(page.locator('tbody > tr').filter({ hasText: 'Beta, Prüfling' })).toHaveCount(0);

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

    await page.locator('#candidateFirstName').fill('E2E');
    await page.locator('#candidateLastName').fill('Testperson');
    await page.locator('#candidateExamNumber').fill('E2E-2026-001');
    await page.getByRole('button', { name: 'Prüfling anlegen' }).click();

    const row = page.locator('tr').filter({ hasText: 'E2E-2026-001' });
    await expect(row).toBeVisible();
    const deleteButton = row.getByRole('button', { name: 'Löschen' });
    await expect(deleteButton).toHaveAttribute('data-appearance', 'secondary-destructive');
    await expect(row.getByRole('button', { name: 'Bearbeiten' })).toHaveAttribute(
      'data-appearance',
      'secondary',
    );
    await deleteButton.click();
    const confirmationDialog = page.getByRole('dialog', { name: 'Prüfling löschen?' });
    await expect(confirmationDialog).toBeVisible();
    await confirmationDialog.getByRole('button', { name: 'Prüfling löschen' }).click();
    await expect(row).toHaveCount(0);
  });

  test('shows a readable message when the API becomes unavailable', async ({ page }) => {
    await page.goto('/');
    await page.route('**/api/round-summary*', (route) => route.fulfill({ status: 500 }));

    await page.getByRole('button', { name: 'Aktualisieren' }).click();
    await expect(page.getByText('Synchronisierung nicht möglich')).toBeVisible();
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
    ]) {
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
    await expect
      .poll(() => scrollRegion.evaluate((element) => getComputedStyle(element, '::before').content))
      .toContain('Tabelle seitlich scrollen');
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

  test('keeps contextual create editors associated, cancellable and accessible', async ({
    page,
  }) => {
    test.setTimeout(120_000);
    const editors = [
      {
        path: '/candidates',
        action: 'Neuen Prüfling anlegen',
        editor: '#candidate-create-editor',
        input: '#candidateFirstName',
      },
      {
        path: '/committee',
        action: 'Neuen Ausschuss anlegen',
        editor: '#committee-create-editor',
        input: '#committeeName',
      },
      {
        path: '/committee',
        action: 'Prüfer hinzufügen',
        editor: '#member-create-editor',
        input: '#memberFirstName',
      },
      {
        path: '/locations',
        action: 'Neuen Prüfungsort anlegen',
        editor: '#location-create-editor',
        input: '#locationName',
      },
    ] as const;

    for (const viewport of viewports) {
      await page.setViewportSize(viewport);

      for (const item of editors) {
        await test.step(`${viewport.name}: ${item.action}`, async () => {
          await page.goto(item.path);
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

  test('keeps development-only prototype content out of production navigation', async ({
    page,
  }) => {
    await page.goto('/dashboard');
    await expect(page.getByText('Taiga-Prototyp')).toHaveCount(0);
    await expect(page.getByText('Entwicklung', { exact: true })).toHaveCount(0);
  });
});

test.describe('lzug theme and accessibility matrix', () => {
  test('keeps the closed mobile navigation out of the accessibility tree @a11y', async ({
    page,
  }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto('/dashboard');

    const sidebar = page.locator('#appSidebar');
    const sidebarToggle = page.getByRole('button', { name: 'Navigation öffnen' });
    await expect(sidebar).toHaveAttribute('inert', '');
    await expect(sidebar).toHaveAttribute('aria-hidden', 'true');
    await expect(page.getByRole('complementary', { name: 'Prüfungsverwaltung' })).toHaveCount(0);
    expect((await new AxeBuilder({ page }).include('#appSidebar').analyze()).violations).toEqual(
      [],
    );

    await sidebarToggle.click();

    await expect(page.getByRole('complementary', { name: 'Prüfungsverwaltung' })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Navigation schließen' }).first()).toBeFocused();
    expect((await new AxeBuilder({ page }).include('#appSidebar').analyze()).violations).toEqual(
      [],
    );
  });

  for (const scheme of colorSchemes) {
    for (const viewport of viewports) {
      test(`${scheme} ${viewport.name} renders every productive view with readable colors @a11y`, async ({
        page,
      }) => {
        test.setTimeout(120_000);
        await page.emulateMedia({ colorScheme: scheme });
        await page.setViewportSize(viewport);

        for (const view of productiveViews) {
          await test.step(view.name, async () => {
            await page.goto(view.path);
            await expect(page.locator('h1')).toBeVisible();
            await expect(page.locator('.app-progress')).toHaveCount(0);
            if (scheme === 'dark') {
              await expect(page.locator('body')).toHaveAttribute('tuiTheme', 'dark');
            } else {
              await expect(page.locator('body')).not.toHaveAttribute('tuiTheme', 'dark');
            }

            await expectReadableContrast(page.locator('h1'));
            await expectReadableContrast(page.locator('.app-panel').first());

            const firstControl = page.locator('input:visible, select:visible').first();
            if (await firstControl.count()) {
              await expectReadableContrast(firstControl);
            }

            const firstCell = page.locator('tbody td:visible').first();
            if (await firstCell.count()) {
              await expectReadableContrast(firstCell);
            }

            if (viewport.name === 'mobile') {
              const menuIcon = page.locator('.app-sidebar-toggle .app-menu-icon');
              await expect(menuIcon).toBeVisible();
              await expectReadableContrast(menuIcon, '::before', 'background-color');

              const scrollRegion = page.locator('.app-table-scroll').first();
              if (await scrollRegion.count()) {
                await expect
                  .poll(() =>
                    scrollRegion.evaluate(
                      (element) => getComputedStyle(element, '::before').content,
                    ),
                  )
                  .toContain('Tabelle seitlich scrollen');
              }
            }

            const results = await new AxeBuilder({ page }).analyze();
            expect(results.violations, `${scheme} ${viewport.name} ${view.name}`).toEqual([]);
          });
        }
      });
    }
  }
});

function confirmedPlan(
  id: number,
  committeeName: string,
  firstName: string,
  lastName: string,
  slotType: 'regular' | 'mep',
) {
  return {
    id,
    name: `Winter ${committeeName}`,
    committee: { id, name: committeeName },
    exam_half_year: { id: 1, season: 'winter', year: 2026, status: 'active' },
    days: [
      {
        id,
        date: '2026-11-16',
        location: {
          id: 1,
          name: 'Prüfungszentrum Langname (Test)',
          room: 'Testraum Langname A-12',
          city: 'Teststadt-West',
        },
        slots: [
          {
            id,
            starts_at: '2026-11-16T08:30:00',
            ends_at: '2026-11-16T09:30:00',
            sequence_number: 1,
            slot_type: slotType,
            candidate: {
              id,
              first_name: firstName,
              last_name: lastName,
              ihk_exam_number: `TEST-PLAN-${id}`,
            },
          },
        ],
        assignments: [
          {
            id: id * 10,
            assignment_role: 'examiner',
            day_part: 'full_day',
            fallback_status: null,
            member: {
              id: id * 10,
              first_name: 'Testperson',
              last_name: 'Langname-Arbeitgeberseite',
              representing_side: 'employer',
            },
          },
          {
            id: id * 10 + 1,
            assignment_role: 'fallback',
            day_part: 'morning',
            fallback_status: 'confirmed',
            member: {
              id: id * 10 + 1,
              first_name: 'Testperson',
              last_name: 'Langname-Arbeitnehmerseite',
              representing_side: 'employee',
            },
          },
          {
            id: id * 10 + 2,
            assignment_role: 'examiner',
            day_part: 'afternoon',
            fallback_status: null,
            member: {
              id: id * 10 + 2,
              first_name: 'Testperson',
              last_name: 'Langname-Schulseite',
              representing_side: 'school',
            },
          },
        ],
      },
    ],
  };
}

async function expectReadableContrast(
  locator: import('@playwright/test').Locator,
  pseudo = '',
  foregroundProperty = 'color',
): Promise<void> {
  const result = await locator.evaluate(
    (element, options) => {
      const parse = (value: string): [number, number, number, number] => {
        const values = value.match(/[\d.]+/g)?.map(Number) ?? [];
        return [values[0] ?? 0, values[1] ?? 0, values[2] ?? 0, values[3] ?? 1];
      };
      const luminance = ([red, green, blue]: [number, number, number, number]): number => {
        const channels = [red, green, blue].map((channel) => {
          const value = channel / 255;
          return value <= 0.04045 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4;
        });
        return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2];
      };
      const composite = (
        foreground: [number, number, number, number],
        background: [number, number, number, number],
      ): [number, number, number, number] => {
        const alpha = foreground[3] + background[3] * (1 - foreground[3]);
        return [
          (foreground[0] * foreground[3] + background[0] * background[3] * (1 - foreground[3])) /
            alpha,
          (foreground[1] * foreground[3] + background[1] * background[3] * (1 - foreground[3])) /
            alpha,
          (foreground[2] * foreground[3] + background[2] * background[3] * (1 - foreground[3])) /
            alpha,
          alpha,
        ];
      };

      const foreground = parse(
        getComputedStyle(element, options.pseudo).getPropertyValue(options.foregroundProperty),
      );
      let backgroundElement: Element | null = options.pseudo ? element.parentElement : element;
      const backgroundLayers: [number, number, number, number][] = [];
      let background: [number, number, number, number] = [255, 255, 255, 1];
      while (backgroundElement) {
        const candidate = parse(getComputedStyle(backgroundElement).backgroundColor);
        if (candidate[3] > 0) {
          backgroundLayers.push(candidate);
        }
        backgroundElement = backgroundElement.parentElement;
      }
      for (const layer of backgroundLayers.reverse()) {
        background = composite(layer, background);
      }
      const visibleForeground = composite(foreground, background);

      const lighter = Math.max(luminance(visibleForeground), luminance(background));
      const darker = Math.min(luminance(visibleForeground), luminance(background));
      return {
        foreground: getComputedStyle(element, options.pseudo).getPropertyValue(
          options.foregroundProperty,
        ),
        background: `rgb(${background[0]} ${background[1]} ${background[2]})`,
        ratio: (lighter + 0.05) / (darker + 0.05),
      };
    },
    { pseudo, foregroundProperty },
  );

  expect(result.foreground).not.toBe(result.background);
  expect(result.ratio, `${result.foreground} on ${result.background}`).toBeGreaterThanOrEqual(4.5);
}
