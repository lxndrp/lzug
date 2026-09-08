import AxeBuilder from '@axe-core/playwright';
import { expect, test } from './fixtures';
import {
  overviewItem,
  viewports,
  useDraftRound,
  csrfHeaders,
  confirmedPlan,
} from './quality-support';

test.describe('planning workflows', () => {
  test.describe.configure({ timeout: 60_000 });

  test('resumes coordination, plans, confirms, and opens the persisted exam plan', async ({
    page,
  }) => {
    test.setTimeout(120_000);
    await page.goto('/scheduling-overview/1');
    await expect(page.getByText('Daten synchronisiert', { exact: true })).toBeVisible({
      timeout: 30_000,
    });

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
    await expect(page.getByText('Planung', { exact: true }).first()).toBeVisible({
      timeout: 30_000,
    });
    await expect(page.getByText('Zusammenfassung vor der Bestätigung')).toBeVisible();
    await expect(page.getByRole('button', { name: 'Plan bestätigen' })).toBeEnabled();

    await page.getByRole('button', { name: 'Plan bestätigen' }).click();
    await page.getByRole('button', { name: 'Plan verbindlich bestätigen' }).click();
    await expect(page).toHaveURL('/confirmed-plans/1');
    await expect(page.getByRole('heading', { name: 'Prüfungspläne' })).toBeVisible();
    await expect(page.locator('.app-confirmed-plan').getByText('Winter 2026/27')).toBeVisible();

    await page.getByRole('link', { name: 'Winter 2026/27: Planänderungen bearbeiten' }).click();
    await expect(page).toHaveURL('/confirmed-plans/1/edit');
    await expect(page.getByRole('heading', { name: 'Bestätigten Plan ändern' })).toBeVisible();
    await page
      .locator('.app-confirmed-editor-day')
      .first()
      .getByRole('button', { name: 'Termin 2 nach oben verschieben' })
      .click();
    await page.getByLabel('Änderungsgrund').fill('Reihenfolge nach Rücksprache korrigiert');
    await page.getByRole('button', { name: 'Änderung mit Grund speichern' }).click();
    await expect(
      page.getByText('Die Änderung wurde als neue Planrevision gespeichert.'),
    ).toBeVisible();
    await page.getByText('Entstandene Revisionen (1)').click();
    await expect(page.getByText(/^Revision \d+ → \d+$/).last()).toBeVisible();

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
      headers: await csrfHeaders(page),
    });
    expect(draftResponse.status()).toBe(200);

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
    expect(requestResponse.status()).toBe(200);
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
        await expect(page.getByText('Arbeitgeber', { exact: true }).first()).toBeVisible();
        await expect(page.getByText('Arbeitnehmer', { exact: true }).first()).toBeVisible();
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
    await northTab.click();

    const selectedPlan = confirmedPlan(
      1,
      'Prüfungsausschuss Plan Alpha',
      'Prüfling',
      'Plan-Alpha',
      'mep',
    );
    const operationalDay = structuredClone(selectedPlan.days[0]);
    await page.route('**/api/confirmed-plan-days/1', (route) =>
      route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({
          plan: {
            id: selectedPlan.id,
            name: selectedPlan.name,
            committee: selectedPlan.committee,
            exam_half_year: selectedPlan.exam_half_year,
          },
          day: operationalDay,
          _links: {},
        }),
      }),
    );
    let startAttempts = 0;
    await page.route('**/api/confirmed-plan-days/1/**', async (route) => {
      const request = route.request();
      const body = request.postDataJSON() as { status?: string; arrived_at?: string } | null;
      if (request.method() === 'PATCH') {
        const assignmentMatch = request.url().match(/assignments\/(\d+)\/attendance$/);
        if (assignmentMatch) {
          const assignment = operationalDay.assignments.find(
            (item) => item.id === Number(assignmentMatch[1]),
          );
          if (assignment && body) {
            assignment.attendance = { status: body.status!, arrived_at: body.arrived_at ?? null };
          }
        } else if (body) {
          operationalDay.slots[0].candidate_attendance = {
            status: body.status!,
            arrived_at: body.arrived_at ?? null,
          };
        }
      } else if (request.method() === 'POST') {
        startAttempts += 1;
        if (startAttempts === 1) {
          await route.fulfill({
            status: 400,
            contentType: 'application/json',
            body: JSON.stringify({
              error: 'Mindestens drei anwesende reguläre Prüfer sind erforderlich',
            }),
          });
          return;
        }
        operationalDay.slots[0].actual_started_at = '2026-11-16T08:31:00+01:00';
        operationalDay.slots[0].execution_status = 'running';
        operationalDay.slots[0].status_changed_at = '2026-11-16T08:31:00+01:00';
      }
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({
          plan: {
            id: selectedPlan.id,
            name: selectedPlan.name,
            committee: selectedPlan.committee,
            exam_half_year: selectedPlan.exam_half_year,
          },
          day: operationalDay,
          _links: {},
        }),
      });
    });
    await page.getByRole('link', { name: 'Tagesansicht öffnen' }).first().click();
    await expect(page).toHaveURL('/confirmed-plans/1/days/1');
    await expect(page.getByRole('heading', { name: 'Prüfungstag' })).toBeVisible();
    await expect(
      page.getByRole('heading', { name: 'Prüfer- und Fallback-Besetzung' }),
    ).toBeVisible();
    await expect(page.getByText('IHK-Prüfungsnummer')).toBeVisible();
    await page.getByLabel('Status Prüfling').selectOption('present');
    await page.getByLabel('Ankunftszeit Prüfling').fill('2026-11-16T08:24');
    await page.getByRole('button', { name: 'Anwesenheit speichern' }).first().click();
    await expect(page.getByText('Änderung gespeichert.')).toBeVisible();
    await page.getByRole('button', { name: 'Prüfung starten' }).click();
    await expect(page.getByRole('alert')).toContainText(
      'Mindestens drei anwesende reguläre Prüfer',
    );

    const regularRows = page
      .locator('.app-exam-day-assignments tbody tr')
      .filter({ has: page.getByText('Prüfer/in') });
    for (const row of await regularRows.all()) {
      await row.getByRole('combobox').selectOption('present');
      await row.locator('input[type="datetime-local"]').fill('2026-11-16T08:10');
      await row.getByRole('button', { name: 'Anwesenheit speichern' }).click();
    }
    await page.getByRole('button', { name: 'Prüfung starten' }).click();
    await expect(page.getByRole('button', { name: 'Gestartet' })).toBeVisible();
    const expectedStartedTime = new Intl.DateTimeFormat('de-DE', {
      timeStyle: 'short',
    }).format(new Date('2026-11-16T08:31:00+01:00'));
    await expect(
      page.locator('.app-exam-day-slots tbody tr').first().locator('td').nth(6),
    ).toContainText(expectedStartedTime);
    await page.getByRole('link', { name: 'Zurück zum Prüfungsplan' }).click();
    await expect(page).toHaveURL('/confirmed-plans/1');
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
    expect(updateResponse.status()).toBe(200);
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
    expect(persistedRoundResponse.status()).toBe(200);
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

  test('creates a half-year context and its committee-specific round atomically', async ({
    page,
  }) => {
    await page.goto('/exam-half-years');
    await expect(page.getByRole('heading', { name: 'Prüfungshalbjahre' })).toBeVisible({
      timeout: 30_000,
    });

    const createRoundButton = page
      .locator('.app-panel-header')
      .getByRole('button', { name: 'Prüfungsrunde anlegen' });
    await createRoundButton.click();
    await page.locator('#examHalfYearSeason').selectOption('summer');
    await page.locator('#examHalfYearYear').fill('2027');
    await page.locator('#newRoundCommittee').selectOption('1');
    const roundResponse = page.waitForResponse(
      (response) =>
        response.url().endsWith('/api/exam-rounds') && response.request().method() === 'POST',
    );
    await page.getByRole('button', { name: 'Prüfungsrunde anlegen', exact: true }).last().click();
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
    expect(settingsResponse.status()).toBe(200);
    const generationResponse = await generationResponsePromise;
    expect(generationResponse.status()).toBe(200);

    await page.getByRole('button', { name: 'Weiter' }).click();
    await expect(page.getByText('4 Tage angelegt')).toBeVisible();
    await expect(page.getByText('1 Feiertage ausgeschlossen')).toBeVisible();
    await expect(page.getByText('04.06.2026 · Fronleichnam')).toBeVisible();
  });
});
