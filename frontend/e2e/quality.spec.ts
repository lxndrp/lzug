import AxeBuilder from '@axe-core/playwright';
import { expect, test } from './fixtures';

const productiveViews = [
  { name: 'Übersicht', path: '/dashboard' },
  { name: 'Terminorganisationen', path: '/scheduling-overview' },
  { name: 'Prüflinge', path: '/candidates' },
  { name: 'Ausschuss', path: '/committee' },
  { name: 'Terminplanung', path: '/planning' },
  { name: 'Prüfungsorte', path: '/locations' },
] as const;

function overviewItem(
  id: number,
  name: string,
  status: string,
  statusGroup: 'open' | 'coordination' | 'confirmed',
  canContinue: boolean,
) {
  return {
    id,
    name,
    status,
    status_group: statusGroup,
    committee_name: 'PA Fachinformatiker Hamburg 1',
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

test.describe('lzug browser workflows', () => {
  test.describe.configure({ timeout: 60_000 });

  test('generates and confirms a planning proposal', async ({ page }) => {
    await page.goto('/');

    await expect(page.getByRole('heading', { name: 'Winter 2026/27' })).toBeVisible();

    await page.getByRole('button', { name: 'Planung erzeugen' }).click();
    await expect(page.getByText('Validierungsreport')).toBeVisible();
    await expect(page.getByText('16 geplante Prüfungstermine')).toBeVisible();

    await page.getByRole('button', { name: 'Plan bestätigen' }).click();
    await page.getByRole('button', { name: 'Plan verbindlich bestätigen' }).click();
    await expect(page.getByText('Plan bestätigt', { exact: true }).first()).toBeVisible();
    await expect(page.getByRole('button', { name: 'Plan bestätigen' })).toBeDisabled();
  });

  test('guides a persisted terminorganisation through every wizard step', async ({ page }) => {
    await page.goto('/planning');

    await expect(
      page.getByRole('navigation', { name: 'Schritte der Terminorganisation' }),
    ).toBeVisible();
    await expect(page.getByRole('button', { name: 'Zeitraum' })).toHaveAttribute(
      'aria-current',
      'step',
    );
    await expect(page.locator('#weekFrom')).toHaveValue('2026-W47');

    await page.getByRole('button', { name: 'Weiter' }).click();
    await expect(page.getByText('Mögliche Prüfungstage')).toBeVisible();
    await page.getByRole('button', { name: 'Weiter' }).click();
    await expect(page.locator('#roundName')).toHaveValue('Winter 2026/27');

    await page.getByRole('button', { name: 'Weiter' }).click();
    await expect(page.getByLabel('Verfügbarkeiten nach Mitglied und Prüfungstag')).toBeVisible();
    await page.getByRole('button', { name: 'Weiter' }).click();
    await expect(page.getByText('Zusammenfassung vor der Bestätigung')).toBeVisible();
    await expect(page.getByText('Rückmeldefrist', { exact: true })).toBeVisible();

    await expect(page.getByRole('button', { name: 'Planung erzeugen' })).toBeEnabled();
    await expect(page.getByRole('button', { name: 'Plan bestätigen' })).toBeDisabled();
  });

  test('groups terminorganisationen and continues an eligible round', async ({ page }) => {
    await page.route('**/api/scheduling-overview', (route) =>
      route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({
          items: [
            overviewItem(1, 'Offene Runde', 'draft', 'open', true),
            overviewItem(2, 'Rückmeldungen', 'availability_requested', 'coordination', true),
            overviewItem(3, 'Bestätigte Runde', 'plan_confirmed', 'confirmed', false),
          ],
          _links: {},
        }),
      }),
    );
    await page.goto('/scheduling-overview');

    await expect(page.getByRole('heading', { name: 'Terminorganisationen' })).toBeVisible();
    await expect(page.getByText('Offen', { exact: true }).first()).toBeVisible();
    await expect(page.getByText('In Abstimmung', { exact: true })).toBeVisible();
    await expect(page.getByText('Bestätigt', { exact: true }).first()).toBeVisible();
    await expect(page.getByText('Plan bestätigt')).toBeVisible();
    await page.getByRole('button', { name: 'Fortsetzen' }).first().click();
    await expect(page).toHaveURL('/planning');
    await expect(
      page.getByRole('navigation', { name: 'Schritte der Terminorganisation' }),
    ).toBeVisible();
  });

  test('navigates through the application views', async ({ page }) => {
    await page.goto('/');
    await expect(page.getByRole('heading', { name: 'Winter 2026/27' })).toBeVisible({
      timeout: 30_000,
    });
    await expect(page.locator('.app-progress')).toHaveCount(0);

    for (const [view, path] of [
      ['Prüflinge', '/candidates'],
      ['Terminorganisationen', '/scheduling-overview'],
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
    await page.getByRole('button', { name: 'Weiter' }).click();
    await page.getByRole('button', { name: 'Weiter' }).click();

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
    await page.getByRole('button', { name: 'Weiter' }).click();
    await page.getByRole('button', { name: 'Weiter' }).click();
    await expect(page.locator('#roundName')).toHaveValue('Sommer 2027');
    await expect(page.locator('#availabilityDeadline')).toHaveValue('15.04.2027, 18:00');
    await expect(page.locator('#availabilityReminder')).toHaveValue('08.04.2027, 09:00');
  });

  test('creates a half-year and its committee-specific exam round', async ({ page }) => {
    await page.goto('/exam-half-years');
    await expect(page.getByRole('heading', { name: 'Prüfungshalbjahre' })).toBeVisible({
      timeout: 30_000,
    });

    await page.locator('#examHalfYearSeason').selectOption('summer');
    await page.locator('#examHalfYearYear').fill('2027');
    const halfYearResponse = page.waitForResponse(
      (response) =>
        response.url().endsWith('/api/exam-half-years') && response.request().method() === 'POST',
    );
    await page.getByRole('button', { name: 'Prüfungshalbjahr anlegen' }).click();
    expect((await halfYearResponse).status()).toBe(201);

    await page.locator('#roundHalfYear').selectOption({ label: 'Sommer 2027' });
    const roundResponse = page.waitForResponse(
      (response) =>
        response.url().endsWith('/api/exam-rounds') && response.request().method() === 'POST',
    );
    await page.getByRole('button', { name: 'Prüfungsrunde anlegen' }).click();
    expect((await roundResponse).status()).toBe(201);
    await expect(page).toHaveURL('/dashboard');
    await expect(page.getByRole('heading', { name: /Sommer 2027/ })).toBeVisible();
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
    await page.locator('#holidaySubdivisionCode').selectOption('DE-NW');

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

    await expect(page.getByText('Keine passenden Prüflinge vorhanden.')).toBeVisible();
  });

  test('keeps application views within the mobile viewport', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });

    for (const path of [
      '/dashboard',
      '/scheduling-overview',
      '/candidates',
      '/committee',
      '/planning',
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

    const trigger = page.getByText('Neuen Prüfling anlegen', { exact: true });
    await trigger.focus();
    await page.keyboard.press('Enter');

    await expect(page.locator('#candidateFirstName')).toBeVisible();
    await expect(trigger).toBeFocused();
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
