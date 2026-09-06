import AxeBuilder from '@axe-core/playwright';
import type { Page } from '@playwright/test';

import { expect, test } from './fixtures';
import { expectFinalStyleState } from './style-stability';

const routes = [
  '/dashboard',
  '/exam-half-years',
  '/committee',
  '/candidates',
  '/locations',
  '/locations/1',
  '/scheduling-overview',
  '/scheduling-overview/1',
  '/confirmed-plans',
  '/confirmed-plans/1',
  '/confirmed-plans/1/edit',
  '/confirmed-plans/1/days/1',
  '/notifications',
  '/absence-reports',
  '/demo-scenarios',
  '/about',
  '/planning',
] as const;

const accessibilityRoutes = [
  '/dashboard',
  '/candidates',
  '/confirmed-plans',
  '/confirmed-plans/1/days/1',
  '/notifications',
  '/demo-scenarios',
] as const;

async function expectStableLayout(page: Page): Promise<void> {
  await expect(page.locator('main')).toBeVisible();
  await expect(page.locator('.app-progress')).toHaveCount(0, { timeout: 30_000 });
  await expect(page.locator('h1')).toBeVisible();
  await expect
    .poll(() =>
      page.evaluate(
        () => document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1,
      ),
    )
    .toBe(true);
}

test.describe('@ui-review cross-browser UI review', () => {
  test.describe.configure({ mode: 'serial', timeout: 180_000 });

  test('renders the complete authenticated route inventory without layout or script failures', async ({
    page,
  }) => {
    const pageErrors: string[] = [];
    page.on('pageerror', (error) => pageErrors.push(error.message));

    for (const path of routes) {
      await test.step(path, async () => {
        await page.setViewportSize({ width: 1440, height: 1000 });
        await page.goto(path);
        await expectStableLayout(page);
      });
    }

    expect(pageErrors).toEqual([]);
  });

  test('keeps representative routes accessible in every supported browser engine', async ({
    page,
  }) => {
    for (const path of accessibilityRoutes) {
      await test.step(path, async () => {
        await page.goto(path);
        await expectStableLayout(page);
        await expectFinalStyleState(page);
        const result = await new AxeBuilder({ page }).include('main').analyze();
        expect(result.violations, path).toEqual([]);
      });
    }
  });

  test('renders login, activation, and recovery without authenticated shell leakage', async ({
    page,
  }, testInfo) => {
    await page.context().clearCookies();
    await page.route('**/api/session', (route) =>
      route.fulfill({
        status: 401,
        contentType: 'application/json',
        body: JSON.stringify({ error: 'Authentication required.' }),
      }),
    );

    for (const path of ['/login', '/activate', '/recover']) {
      await test.step(path, async () => {
        await page.goto(path);
        await expectStableLayout(page);
        await expect(page.locator('.app-shell')).toHaveCount(0);
        await expectFinalStyleState(page);
        const result = await new AxeBuilder({ page }).include('main').analyze();
        expect(result.violations, path).toEqual([]);
      });
    }

    await page.goto('/login');
    await expectStableLayout(page);
    await testInfo.attach('application-login', {
      body: await page.screenshot({ fullPage: true }),
      contentType: 'image/png',
    });
  });

  test('attaches representative application evidence for the shared visual grammar', async ({
    page,
  }, testInfo) => {
    await page.goto('/dashboard');
    await expectStableLayout(page);
    const grammar = await page.evaluate(() => {
      const panel = document.querySelector('.app-panel');
      if (!panel) throw new Error('missing representative application panel');
      const resolve = (property: string, cssProperty: string) => {
        const probe = document.createElement('span');
        probe.style.setProperty(cssProperty, `var(${property})`);
        document.body.append(probe);
        const value = getComputedStyle(probe).getPropertyValue(cssProperty);
        probe.remove();
        return value;
      };
      const panelStyle = getComputedStyle(panel);
      return {
        panelRadius: panelStyle.borderRadius,
        roleRadius: resolve('--lzug-role-card-radius', 'border-radius'),
        panelSurface: panelStyle.backgroundColor,
        roleSurface: resolve('--lzug-role-card-surface', 'background-color'),
      };
    });
    expect(grammar.panelRadius).toBe(grammar.roleRadius);
    expect(grammar.panelSurface).toBe(grammar.roleSurface);
    await testInfo.attach('application-dashboard', {
      body: await page.screenshot({ fullPage: true }),
      contentType: 'image/png',
    });
  });

  test('supports mobile, touch, keyboard, reduced motion, and 200-percent reflow', async ({
    page,
  }) => {
    await page.emulateMedia({ reducedMotion: 'reduce' });
    await page.setViewportSize({ width: 320, height: 844 });
    await page.goto('/dashboard');
    await expectStableLayout(page);

    const navigationToggle = page.getByRole('button', { name: 'Navigation öffnen' });
    const toggleBox = await navigationToggle.boundingBox();
    expect(toggleBox?.width).toBeGreaterThanOrEqual(44);
    expect(toggleBox?.height).toBeGreaterThanOrEqual(44);
    await navigationToggle.focus();
    await page.keyboard.press('Enter');
    await expect(page.getByRole('complementary', { name: 'Prüfungsverwaltung' })).toBeVisible();
    await expect(page.locator('.app-sidebar-close')).toBeFocused();
    await page.keyboard.press('Escape');
    await expect(navigationToggle).toBeFocused();
    await expect
      .poll(() =>
        page
          .locator('.app-sidebar')
          .evaluate((element) => getComputedStyle(element).transitionDuration),
      )
      .toBe('0s');

    await page.setViewportSize({ width: 768, height: 1024 });
    await page.goto('/candidates');
    await expectStableLayout(page);
    await expect(page.getByRole('toolbar', { name: 'Prüflingsliste verwalten' })).toBeVisible();

    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto('/dashboard');
    await page.evaluate(() => document.documentElement.style.setProperty('font-size', '200%'));
    await expectStableLayout(page);
    const contextRows = await page.locator('.app-active-context dl > div').evaluateAll((items) =>
      items.map((item) => {
        const rectangle = item.getBoundingClientRect();
        return { top: rectangle.top, bottom: rectangle.bottom };
      }),
    );
    expect(
      contextRows.every((row, index) => index === 0 || row.top >= contextRows[index - 1].bottom),
    ).toBe(true);
  });

  test('announces and focuses candidate validation with field-level recovery links', async ({
    page,
  }) => {
    await page.goto('/candidates');
    await page.getByText('Neuen Prüfling anlegen', { exact: true }).click();
    await page.getByRole('button', { name: 'Prüfling anlegen', exact: true }).click();

    const summary = page.getByRole('alert').filter({ hasText: 'Prüfling noch nicht angelegt' });
    await expect(summary).toBeVisible();
    await expect
      .poll(() =>
        page.evaluate(() => {
          const active = document.activeElement;
          return (
            active?.classList.contains('app-form-error-summary') ||
            active?.id === 'candidateFirstName'
          );
        }),
      )
      .toBe(true);
    await expect(summary.getByRole('link')).toHaveCount(3);
    await expect(page.locator('#candidateFirstName')).toHaveAttribute(
      'aria-describedby',
      'candidateFirstNameError',
    );
    await summary.getByRole('link', { name: 'Vorname eingeben.' }).click();
    await expect(page.locator('#candidateFirstName')).toBeFocused();
  });

  test('keeps dialog, table, error, and demo-tour semantics operable', async ({ page }) => {
    await page.goto('/candidates');
    const table = page.getByRole('table');
    await expect(table).toBeVisible();
    await expectFinalStyleState(page);
    expect((await new AxeBuilder({ page }).include('table').analyze()).violations).toEqual([]);

    const deleteButton = page.getByRole('button', { name: /löschen$/i }).first();
    await deleteButton.click();
    const confirmation = page.getByRole('dialog');
    await expect(confirmation).toBeVisible();
    await expectFinalStyleState(page);
    expect(
      (await new AxeBuilder({ page }).include('[role="dialog"]').analyze()).violations,
    ).toEqual([]);
    await page.keyboard.press('Escape');
    await expect(confirmation).toHaveCount(0);

    await page.goto('/dashboard');
    await page.route('**/api/round-summary*', (route) => route.fulfill({ status: 500 }));
    await page.getByRole('button', { name: 'Aktualisieren' }).click();
    const error = page.getByRole('alert').filter({ hasText: 'Synchronisierung nicht möglich' });
    await expect(error).toBeVisible();
    await expect(error).toContainText(/versuchen Sie es erneut/i);

    await page.unroute('**/api/round-summary*');
    await page.route('**/api/session', (route) =>
      route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({
          authenticated: true,
          account_id: 1,
          person_id: 1,
          committee_member_id: 1,
          is_operator: false,
          demo_role: 'chair',
          display_name: 'Theseus von Athen',
          capabilities: ['absence:coordinate', 'confirmed-plan:revise'],
          demo_matrix_version: 'demo-paths-v8',
          demo_workspace_expires_at: '2027-01-01T00:00:00Z',
        }),
      }),
    );
    await page.goto('/demo-scenarios');
    await page.getByRole('button', { name: 'Demo-Tour starten' }).first().click();
    const tour = page.getByRole('dialog', { name: 'Synthetische Demo' });
    await expect(tour).toBeVisible();
    await expect(tour).toBeFocused();
    await expectFinalStyleState(page);
    expect(
      (await new AxeBuilder({ page }).include('.demo-tour-dialog').analyze()).violations,
    ).toEqual([]);
  });

  test('keeps final color-contrast violations visible to axe', async ({ page }) => {
    await page.setContent(
      '<main><p id="contrast-probe" style="color: #fff; background: #8984a4">Kontrastprüfung</p></main>',
    );
    await expectFinalStyleState(page);

    const result = await new AxeBuilder({ page }).include('#contrast-probe').analyze();
    expect(result.violations.map((violation) => violation.id)).toContain('color-contrast');
  });
});
