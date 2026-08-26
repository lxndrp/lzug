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
  { name: 'Benachrichtigungen', path: '/notifications' },
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

const demoNoticeViewports = [
  { name: 'desktop', width: 1440, height: 1000 },
  { name: 'tablet', width: 768, height: 1024 },
  { name: 'mobile', width: 390, height: 844 },
] as const;

async function showDemoRuntimeNotice(page: Page): Promise<void> {
  await page.locator('app-runtime-notice').evaluate((host) => {
    host.innerHTML = `
      <aside class="demo-notice" aria-label="Hinweis zur flüchtigen Demo" tabindex="-1">
        <strong>Flüchtige Demo</strong>
        <span>Keine realen personenbezogenen Daten eingeben.</span>
        <span>Nächster Reset: 25.08.26, 03:00 · Version 0.2.0-SNAPSHOT</span>
      </aside>
    `;
    const notice = host.querySelector<HTMLElement>('.demo-notice');
    if (!notice) {
      throw new Error('Demo runtime notice fixture was not created');
    }
    Object.assign(notice.style, {
      display: 'flex',
      flexWrap: 'wrap',
      justifyContent: 'center',
      gap: '0.35rem 1.25rem',
      padding: '0.65rem 1rem',
      borderBottom: '1px solid #d9a548',
      background: '#fff3dc',
      fontSize: '0.9rem',
      lineHeight: '1.35',
      textAlign: 'center',
    });
  });
}

async function useDraftRound(page: Page): Promise<void> {
  const response = await page.request.patch('/api/exam-rounds/1', {
    data: { status: 'draft' },
    headers: await csrfHeaders(page),
  });
  expect(response.status()).toBe(200);
}

async function csrfHeaders(page: Page): Promise<Record<string, string>> {
  const csrfCookie = (await page.context().cookies()).find((cookie) => cookie.name === 'lzug_csrf');
  expect(csrfCookie?.value).toBeTruthy();
  return { 'X-CSRF-Token': csrfCookie?.value ?? '' };
}

test.describe('lzug browser workflows', () => {
  test.describe.configure({ timeout: 60_000 });

  test('resumes coordination, plans, confirms, and opens the persisted exam plan', async ({
    page,
  }) => {
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

  test('tracks start, completion, failure, and follow-up in the exam-day view', async ({
    page,
  }) => {
    const plan = confirmedPlan(1, 'Prüfungsausschuss Status', 'Prüfling', 'Status', 'regular');
    const day = plan.days[0];
    const firstSlot = day.slots[0];
    day.slots.push(
      {
        ...structuredClone(firstSlot),
        id: 2,
        sequence_number: 2,
        starts_at: '2026-11-16T09:30:00',
        ends_at: '2026-11-16T10:30:00',
        candidate: { ...firstSlot.candidate, id: 2, first_name: 'Prüfling', last_name: 'Ausfall' },
      },
      {
        ...structuredClone(firstSlot),
        id: 3,
        sequence_number: 3,
        starts_at: '2026-11-16T10:30:00',
        ends_at: '2026-11-16T11:30:00',
        candidate: {
          ...firstSlot.candidate,
          id: 3,
          first_name: 'Prüfling',
          last_name: 'Nachbereitung',
        },
      },
    );
    const updateSummary = () => {
      day.status_summary = { open: 0, running: 0, completed: 0, cancelled: 0, needs_follow_up: 0 };
      for (const slot of day.slots) day.status_summary[slot.execution_status] += 1;
    };

    await page.route('**/api/confirmed-plan-days/1', (route) =>
      route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({
          plan: {
            id: plan.id,
            name: plan.name,
            committee: plan.committee,
            exam_half_year: plan.exam_half_year,
          },
          day,
          _links: {},
        }),
      }),
    );
    await page.route('**/api/confirmed-plan-days/1/slots/*/start', async (route) => {
      const slotId = Number(
        route
          .request()
          .url()
          .match(/slots\/(\d+)\/start/)?.[1],
      );
      const slot = day.slots.find((item) => item.id === slotId)!;
      slot.execution_status = 'running';
      slot.actual_started_at = '2026-11-16T08:31:00+01:00';
      slot.status_changed_at = slot.actual_started_at;
      updateSummary();
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({
          plan: {
            id: plan.id,
            name: plan.name,
            committee: plan.committee,
            exam_half_year: plan.exam_half_year,
          },
          day,
          _links: {},
        }),
      });
    });
    await page.route('**/api/confirmed-plan-days/1/slots/*/status', async (route) => {
      const slotId = Number(
        route
          .request()
          .url()
          .match(/slots\/(\d+)\/status/)?.[1],
      );
      const slot = day.slots.find((item) => item.id === slotId)!;
      const body = route.request().postDataJSON() as { status: string; reason?: string };
      slot.execution_status = body.status;
      slot.status_reason = body.reason ?? slot.status_reason;
      slot.status_changed_at = '2026-11-16T12:00:00+01:00';
      if (body.status === 'completed') slot.actual_completed_at = slot.status_changed_at;
      updateSummary();
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({
          plan: {
            id: plan.id,
            name: plan.name,
            committee: plan.committee,
            exam_half_year: plan.exam_half_year,
          },
          day,
          _links: {},
        }),
      });
    });

    await page.goto('/confirmed-plans/1/days/1');
    await expect(page.getByText('Zusammenfassung der Durchführung')).toBeVisible();

    const rows = page.locator('.app-exam-day-slots tbody tr');
    await rows.nth(0).getByRole('button', { name: 'Prüfung starten' }).click();
    await expect(rows.nth(0).getByRole('button', { name: 'Gestartet' })).toBeVisible();

    await rows.nth(0).getByLabel('Durchführungsstatus', { exact: true }).selectOption('completed');
    await rows.nth(0).getByRole('button', { name: 'Status speichern' }).click();
    await expect(
      rows.nth(0).locator('span[tuibadge]').filter({ hasText: 'Abgeschlossen' }),
    ).toBeVisible();

    await rows.nth(1).getByLabel('Durchführungsstatus', { exact: true }).selectOption('cancelled');
    await rows
      .nth(1)
      .getByLabel('Begründung für den Durchführungsstatus')
      .fill('Prüfling erkrankt');
    await rows.nth(1).getByRole('button', { name: 'Status speichern' }).click();
    await expect(
      rows.nth(1).locator('span[tuibadge]').filter({ hasText: 'Ausgefallen' }),
    ).toBeVisible();

    await rows.nth(2).getByRole('button', { name: 'Prüfung starten' }).click();
    await rows
      .nth(2)
      .getByLabel('Durchführungsstatus', { exact: true })
      .selectOption('needs_follow_up');
    await rows
      .nth(2)
      .getByLabel('Begründung für den Durchführungsstatus')
      .fill('Dokumentation nachreichen');
    await rows.nth(2).getByRole('button', { name: 'Status speichern' }).click();
    await expect(
      rows.nth(2).locator('span[tuibadge]').filter({ hasText: 'Nachzubereiten' }),
    ).toBeVisible();
    await rows.nth(2).getByLabel('Durchführungsstatus', { exact: true }).selectOption('completed');
    await rows.nth(2).getByRole('button', { name: 'Status speichern' }).click();
    await expect(
      rows.nth(2).locator('span[tuibadge]').filter({ hasText: 'Abgeschlossen' }),
    ).toBeVisible();
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

  test('keeps demo roles visible and role-safe on desktop and mobile', async ({ page }) => {
    let role: 'chair' | 'examiner' = 'chair';
    await page.route('**/api/session', async (route) => {
      if (route.request().method() === 'POST') {
        await route.fulfill({ status: 204 });
        return;
      }
      const isChair = role === 'chair';
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({
          authenticated: true,
          account_id: isChair ? 1 : 2,
          person_id: isChair ? 1 : 3,
          committee_member_id: isChair ? 1 : 3,
          is_operator: false,
          demo_role: role,
          display_name: isChair ? 'Testperson Alpha' : 'Testperson Gamma',
          capabilities: isChair
            ? [
                'attendance:coordinate',
                'attendance:write-own',
                'availability:coordinate',
                'availability:write-own',
                'candidate-days:generate',
                'exam-status:write',
                'planning-proposal:confirm',
                'planning-proposal:generate',
                'planning-settings:write',
                'round:write',
              ]
            : ['attendance:write-own', 'availability:write-own'],
        }),
      });
    });

    for (const currentRole of ['chair', 'examiner'] as const) {
      role = currentRole;
      for (const viewport of viewports) {
        await test.step(`${currentRole} · ${viewport.name}`, async () => {
          await page.setViewportSize(viewport);
          await page.goto('/dashboard');
          await expect(page.getByLabel('Aktive Demo-Identität')).toContainText(
            currentRole === 'chair' ? 'Testperson Alpha' : 'Testperson Gamma',
          );
          await expect(
            page.getByText(currentRole === 'chair' ? 'Vorsitz' : 'Prüfperson'),
          ).toBeVisible();
          await expect(page.getByRole('button', { name: 'Rolle wechseln' })).toBeVisible();
          if (viewport.name === 'mobile') {
            await page.getByRole('button', { name: 'Navigation öffnen' }).click();
            await expect(
              page.getByRole('complementary', { name: 'Prüfungsverwaltung' }),
            ).toBeVisible();
          }
          await expect(page.getByRole('link', { name: 'Prüflinge', exact: true })).toHaveCount(0);
          await expect(
            page.getByRole('link', { name: 'Prüfungsausschüsse', exact: true }),
          ).toHaveCount(0);
          await expect(
            page.getByRole('link', { name: 'Terminorganisationen', exact: true }),
          ).toBeVisible();
          await expect(
            page.getByRole('link', { name: 'Prüfungspläne', exact: true }),
          ).toBeVisible();

          await page.goto('/candidates');
          await expect(
            page.getByText('Dieser Demo-Bereich ist für Ihre Rolle nicht freigegeben.'),
          ).toBeVisible();
          await expect(page.locator('app-candidates')).toHaveCount(0);
        });
      }
    }

    role = 'examiner';
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto('/dashboard');
    const switchButton = page.getByRole('button', { name: 'Rolle wechseln' });
    await switchButton.focus();
    await expect(switchButton).toBeFocused();
    await page.keyboard.press('Enter');
    await expect(page.getByRole('heading', { name: 'Anmelden' })).toBeVisible();
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

  test('keeps the demo notice clear of the sidebar and sticky header', async ({ page }) => {
    for (const viewport of demoNoticeViewports) {
      await test.step(viewport.name, async () => {
        await page.setViewportSize(viewport);
        await page.goto('/dashboard');
        await expect(page.getByRole('heading', { name: 'Übersicht' })).toBeVisible();
        await showDemoRuntimeNotice(page);

        const notice = page.getByRole('complementary', { name: 'Hinweis zur flüchtigen Demo' });
        const sidebar = page.locator('#appSidebar');
        const sidebarIsOpen = await sidebar.evaluate((element) => !element.hasAttribute('inert'));
        if (!sidebarIsOpen) {
          await page.getByRole('button', { name: 'Navigation öffnen' }).click();
        }

        await expect(notice).toBeVisible();
        await expect(notice).toContainText('Flüchtige Demo');
        await expect(notice).toContainText('Keine realen personenbezogenen Daten eingeben.');
        await expect(notice).toContainText('Nächster Reset:');

        const openLayout = await page.evaluate(() => {
          const noticeRect = document.querySelector('.demo-notice')?.getBoundingClientRect();
          const sidebarRect = document.querySelector('#appSidebar')?.getBoundingClientRect();
          const headerRect = document.querySelector('.app-header')?.getBoundingClientRect();
          if (!noticeRect || !sidebarRect || !headerRect) {
            throw new Error('Expected demo shell elements are missing');
          }
          return {
            documentWidth: document.documentElement.scrollWidth,
            viewportWidth: document.documentElement.clientWidth,
            notice: { left: noticeRect.left, right: noticeRect.right, bottom: noticeRect.bottom },
            sidebarTop: sidebarRect.top,
            headerTop: headerRect.top,
          };
        });
        expect(openLayout.documentWidth).toBe(openLayout.viewportWidth);
        expect(openLayout.notice.left).toBeGreaterThanOrEqual(0);
        expect(openLayout.notice.right).toBeLessThanOrEqual(openLayout.viewportWidth);
        expect(openLayout.sidebarTop).toBeGreaterThanOrEqual(openLayout.notice.bottom - 1);
        expect(openLayout.headerTop).toBeGreaterThanOrEqual(openLayout.notice.bottom - 1);

        await notice.focus();
        await expect(notice).toBeFocused();
        await expect(notice).toBeInViewport();

        if (viewport.width < 768) {
          await page.locator('.app-sidebar-close').click();
        } else {
          await page.getByRole('button', { name: 'Navigation schließen' }).click();
        }
        await expect(sidebar).toHaveAttribute('inert', '');
        await expect(notice).toBeVisible();
        const closedLayout = await notice.evaluate((element) => {
          const rect = element.getBoundingClientRect();
          return {
            left: rect.left,
            right: rect.right,
            viewportWidth: document.documentElement.clientWidth,
            documentWidth: document.documentElement.scrollWidth,
          };
        });
        expect(closedLayout.documentWidth).toBe(closedLayout.viewportWidth);
        expect(closedLayout.left).toBeGreaterThanOrEqual(0);
        expect(closedLayout.right).toBeLessThanOrEqual(closedLayout.viewportWidth);
      });
    }
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

    const newHalfYear = page.locator('article').filter({ hasText: 'Sommer 2027' });
    await expect(newHalfYear).toBeVisible();
    await newHalfYear.getByRole('button', { name: 'Öffnen' }).click();
    await expect(page.getByRole('heading', { name: 'Sommer 2027' })).toBeVisible();
    await page.locator('#roundCommittee').selectOption('1');
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
    expect(settingsResponse.status()).toBe(200);
    const generationResponse = await generationResponsePromise;
    expect(generationResponse.status()).toBe(200);

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
    await expect(location.locator('option:checked')).toHaveText(
      'Prüfungszentrum Alpha (Test) · Testraum A-01',
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
      name: 'E2E Testperson löschen?',
    });
    await expect(confirmationDialog).toBeVisible();
    await confirmationDialog.getByRole('button', { name: 'E2E Testperson löschen' }).click();
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
          const refreshButton = page.getByRole('button', { name: 'Aktualisieren' });
          await expect(refreshButton).toBeEnabled();
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
  test('keeps exam-day attendance controls keyboard-accessible @a11y', async ({ page }) => {
    const plan = confirmedPlan(1, 'Prüfungsausschuss Accessibility', 'Prüfling', 'A11y', 'regular');
    await page.route('**/api/confirmed-plan-days/1', (route) =>
      route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({
          plan: {
            id: plan.id,
            name: plan.name,
            committee: plan.committee,
            exam_half_year: plan.exam_half_year,
          },
          day: plan.days[0],
          _links: {},
        }),
      }),
    );
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto('/confirmed-plans/1/days/1');
    await expect(page.getByRole('heading', { name: 'Prüfungstag' })).toBeVisible();
    await page.getByLabel('Status Prüfling').focus();
    await expect(page.getByLabel('Status Prüfling')).toBeFocused();
    await page.keyboard.press('Tab');
    await expect(page.getByLabel('Ankunftszeit Prüfling')).toBeFocused();
    expect((await new AxeBuilder({ page }).include('app-exam-day').analyze()).violations).toEqual(
      [],
    );
  });

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
            actual_started_at: null,
            execution_status: 'open',
            status_changed_at: '2026-11-16T08:00:00+01:00',
            actual_completed_at: null,
            status_reason: null,
            candidate_attendance: { status: 'open', arrived_at: null },
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
            attendance: { status: 'open', arrived_at: null },
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
            attendance: { status: 'open', arrived_at: null },
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
            day_part: 'full_day',
            fallback_status: null,
            attendance: { status: 'open', arrived_at: null },
            member: {
              id: id * 10 + 2,
              first_name: 'Testperson',
              last_name: 'Langname-Schulseite',
              representing_side: 'school',
            },
          },
          {
            id: id * 10 + 3,
            assignment_role: 'examiner',
            day_part: 'full_day',
            fallback_status: null,
            attendance: { status: 'open', arrived_at: null },
            member: {
              id: id * 10 + 3,
              first_name: 'Testperson',
              last_name: 'Langname-Arbeitnehmerseite',
              representing_side: 'employee',
            },
          },
        ],
        status_summary: {
          open: 1,
          running: 0,
          completed: 0,
          cancelled: 0,
          needs_follow_up: 0,
        },
      },
    ],
  };
}

async function expectReadableContrast(
  locator: import('@playwright/test').Locator,
  pseudo = '',
  foregroundProperty = 'color',
): Promise<void> {
  await expect(async () => {
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
    expect(result.ratio, `${result.foreground} on ${result.background}`).toBeGreaterThanOrEqual(
      4.5,
    );
  }).toPass({ timeout: 5_000 });
}
