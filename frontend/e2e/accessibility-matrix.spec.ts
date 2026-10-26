import AxeBuilder from '@axe-core/playwright';
import { expect, test } from './fixtures';
import {
  productiveViews,
  colorSchemes,
  viewports,
  confirmedPlan,
  expectReadableContrast,
} from './quality-support';

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

  test('keeps exception closure fields keyboard-accessible and submits validated details @a11y', async ({
    page,
  }) => {
    const plan = confirmedPlan(
      1,
      'Prüfungsausschuss Abschluss',
      'Prüfling',
      'Abschluss',
      'regular',
    );
    const day = plan.days[0];
    day.closure.permissions.close = true;
    day.closure.evaluation.exception_close_ready = true;
    await page.route('**/api/session', (route) =>
      route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({
          authenticated: true,
          account_id: 1,
          person_id: 1,
          committee_member_id: 1,
          is_operator: false,
          capabilities: ['exam-day-closure:read', 'exam-day-closure:close'],
        }),
      }),
    );
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
    let submittedBody: Record<string, unknown> | undefined;
    await page.route('**/api/confirmed-plan-days/1/closure', async (route) => {
      submittedBody = route.request().postDataJSON() as Record<string, unknown>;
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({
          ...day.closure,
          revision: 2,
          status: 'closed',
          permissions: { close: false, reopen: false, export: true },
        }),
      });
    });

    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto('/confirmed-plans/1/days/1');
    await expect(page.getByRole('heading', { name: 'Prüfungstag' })).toBeVisible();
    const closure = page.getByRole('group', { name: 'Abschlussentscheidung' });
    const closureType = closure.getByLabel('Abschlussart');
    await closureType.focus();
    await closureType.selectOption('exception');

    const reason = closure.getByLabel('Ausnahmegrund');
    const attempts = closure.getByLabel('Bisherige Klärungsversuche');
    await expect(reason).toBeVisible();
    await reason.focus();
    await expect(reason).toBeFocused();
    await page.keyboard.press('Tab');
    await expect(attempts).toBeFocused();
    expect(
      (await new AxeBuilder({ page }).include('.app-exam-day-closure-form').analyze()).violations,
    ).toEqual([]);

    await closure
      .getByRole('button', { name: 'Voraussetzungen bestätigen und abschließen' })
      .click();
    await expect(page.getByRole('alert')).toContainText(
      'Grund und bisherige Klärungsversuche sind erforderlich.',
    );
    expect(submittedBody).toBeUndefined();

    await reason.fill('  Systemausfall  ');
    await attempts.fill('  Support kontaktiert  ');
    await closure
      .getByRole('button', { name: 'Voraussetzungen bestätigen und abschließen' })
      .click();
    await expect(page.getByRole('status')).toContainText('Prüfungstag formal abgeschlossen.');
    expect(submittedBody).toEqual({
      revision: 1,
      closure_type: 'exception',
      confirmed: true,
      reason: 'Systemausfall',
      clarification_attempts: 'Support kontaktiert',
    });
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
        test.setTimeout(180_000);
        await page.emulateMedia({ colorScheme: scheme });
        await page.setViewportSize(viewport);

        for (const view of productiveViews) {
          await test.step(view.name, async () => {
            await page.goto(view.path);
            await expect(page.locator('h1')).toBeVisible();
            await expect(page.locator('.app-progress')).toHaveCount(0, { timeout: 30_000 });
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
              const menuIcon = page.locator('.app-sidebar-toggle svg');
              await expect(menuIcon).toBeVisible();
              await expectReadableContrast(menuIcon);

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
