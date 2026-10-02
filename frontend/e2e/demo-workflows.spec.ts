import AxeBuilder from '@axe-core/playwright';
import { expect, test } from './fixtures';
import { resolve } from 'node:path';
import {
  demoRoles,
  demoCapabilities,
  demoWorkspaceExpiry,
  demoScenarioOverview,
  viewports,
  demoNoticeViewports,
  showDemoRuntimeNotice,
} from './quality-support';

test.describe('demo workflows', () => {
  test.describe.configure({ timeout: 60_000 });

  test('does not restore a demo role after validation and revocation both fail', async ({
    page,
  }) => {
    await page.setViewportSize({ width: 1280, height: 720 });
    let role: 'chair' | 'examiner' | 'replacement' = 'examiner';
    let roleSwitchSucceeded = false;
    let lifecycleUnavailable = false;
    let sessionRequests = 0;
    let logoutRequests = 0;

    await page.route('**/api/lifecycle', (route) =>
      lifecycleUnavailable
        ? route.fulfill({
            status: 503,
            contentType: 'application/json',
            body: JSON.stringify({
              error: {
                code: 'runtime_not_ready',
                state: 'unreachable',
                ready: false,
                message: 'Runtime is temporarily unavailable.',
              },
            }),
          })
        : route.fulfill({
            contentType: 'application/json',
            body: JSON.stringify({ state: 'ready', ready: true }),
          }),
    );
    await page.route('**/api/session', (route) => {
      sessionRequests += 1;
      if (roleSwitchSucceeded) {
        lifecycleUnavailable = true;
        return route.fulfill({
          status: 503,
          contentType: 'application/json',
          body: JSON.stringify({
            error: {
              code: 'runtime_not_ready',
              state: 'unreachable',
              ready: false,
              message: 'Session validation failed.',
            },
          }),
        });
      }
      return route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({
          authenticated: true,
          account_id: demoRoles[role].account_id,
          person_id: demoRoles[role].person_id,
          committee_member_id: demoRoles[role].committee_member_id,
          is_operator: false,
          demo_role: role,
          display_name: demoRoles[role].display_name,
          capabilities: demoCapabilities(role),
          demo_matrix_version: 'demo-paths-v8',
          demo_workspace_expires_at: demoWorkspaceExpiry(),
        }),
      });
    });
    await page.route('**/api/demo/scenarios', (route) =>
      route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify(demoScenarioOverview(role)),
      }),
    );
    await page.route('**/api/demo/session', (route) => {
      role = 'chair';
      roleSwitchSucceeded = true;
      return route.fulfill({
        status: 201,
        contentType: 'application/json',
        headers: { 'Set-Cookie': 'session=switched-role; HttpOnly; Path=/' },
        body: JSON.stringify({ authenticated: true }),
      });
    });
    await page.route('**/api/session/logout', (route) => {
      logoutRequests += 1;
      if (logoutRequests === 1) {
        return route.fulfill({
          status: 503,
          contentType: 'application/json',
          body: JSON.stringify({ error: { message: 'Revocation temporarily unavailable.' } }),
        });
      }
      roleSwitchSucceeded = false;
      return route.fulfill({
        status: 204,
        headers: { 'Set-Cookie': 'session=; Max-Age=0; HttpOnly; Path=/' },
      });
    });

    await page.goto('/demo-scenarios');
    await expect(page.getByText('Eigenen Ausfall melden')).toBeVisible();
    await page.getByRole('button', { name: 'Vorsitz', exact: true }).click();

    await expect(page.getByRole('alert')).toContainText('nicht beendet');
    expect(sessionRequests).toBe(2);
    expect(logoutRequests).toBe(1);
    expect((await page.context().cookies()).map(({ name }) => name)).toContain('session');

    await page.reload();
    const recoveryScreen = page.locator('app-lifecycle-notice');
    const recoveryAlert = recoveryScreen.getByRole('alert');
    const retryButton = recoveryScreen.getByRole('button', {
      name: 'Sitzung sicher beenden erneut versuchen',
    });
    await expect(recoveryAlert).toContainText('Geschützte Bereiche bleiben gesperrt');
    await expect(retryButton).toBeVisible();
    expect(
      await retryButton.evaluate((element) => {
        const rect = element.getBoundingClientRect();
        return rect.top >= 0 && rect.bottom <= window.innerHeight;
      }),
    ).toBe(true);
    expect(sessionRequests).toBe(2);

    lifecycleUnavailable = false;
    await recoveryScreen.getByRole('button', { name: 'Status erneut prüfen' }).click();
    await expect(page.getByRole('heading', { name: 'Anmeldung wird geprüft' })).toBeVisible();
    await expect(page.locator('.app-shell')).toHaveCount(0);
    await expect(page.getByRole('alert')).toContainText('Geschützte Bereiche bleiben gesperrt');
    expect(sessionRequests).toBe(2);

    await page.getByRole('button', { name: 'Sitzung sicher beenden erneut versuchen' }).click();
    await expect(page).toHaveURL('/login');
    expect(logoutRequests).toBe(2);
    expect((await page.context().cookies()).map(({ name }) => name)).not.toContain('session');
  });

  test('keeps isolated demo scenarios and roles safe on desktop and mobile', async ({ page }) => {
    test.setTimeout(180_000);
    let role: 'chair' | 'examiner' | 'replacement' = 'chair';
    await page.route('**/api/session', async (route) => {
      if (route.request().method() === 'POST') {
        await route.fulfill({ status: 204 });
        return;
      }
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({
          authenticated: true,
          account_id: demoRoles[role].account_id,
          person_id: demoRoles[role].person_id,
          committee_member_id: demoRoles[role].committee_member_id,
          is_operator: false,
          demo_role: role,
          display_name: demoRoles[role].display_name,
          capabilities: demoCapabilities(role),
          demo_matrix_version: 'demo-paths-v8',
          demo_workspace_expires_at: demoWorkspaceExpiry(),
        }),
      });
    });
    await page.route('**/api/demo/scenarios', (route) =>
      route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify(demoScenarioOverview(role)),
      }),
    );
    await page.route('**/api/demo/session', async (route) => {
      const payload = route.request().postDataJSON() as { role: typeof role };
      role = payload.role;
      await route.fulfill({ status: 201, body: JSON.stringify({ authenticated: true }) });
    });

    for (const currentRole of ['chair', 'examiner', 'replacement'] as const) {
      role = currentRole;
      for (const viewport of viewports) {
        await test.step(`${currentRole} · ${viewport.name}`, async () => {
          await page.setViewportSize(viewport);
          await page.goto('/demo-scenarios');
          await expect(page.getByLabel('Aktive Demo-Identität')).toContainText(
            demoRoles[currentRole].display_name,
          );
          await expect(
            page.getByRole('heading', { name: 'Zwei unabhängige Fachabläufe' }),
          ).toBeVisible();
          await expect(page.getByText('Dringlicher Ausfall und Ersatz')).toBeVisible();
          await expect(page.getByText('Bestätigte Planänderung')).toBeVisible();
          await expect(page.getByText('60 Minuten ab Start')).toBeVisible();
          await expect(
            page.getByText('Keine realen personenbezogenen Daten eingeben.'),
          ).toBeVisible();
          if (process.env['LZUG_CAPTURE_DEMO_MEDIA'] === 'true' && currentRole === 'chair') {
            await page.screenshot({
              path: resolve(
                process.cwd(),
                '..',
                'docs',
                'media',
                `demo-scenarios-${viewport.name}.png`,
              ),
              fullPage: false,
              animations: 'disabled',
              mask: [page.locator('.demo-session-facts dd').first()],
              maskColor: '#e7e9ec',
            });
          }
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
          ).toHaveCount(0);
          await expect(page.getByRole('link', { name: 'Prüfungspläne', exact: true })).toHaveCount(
            currentRole === 'replacement' ? 0 : 1,
          );
          const mainNavigation = page.getByLabel('Hauptnavigation');
          await expect(
            mainNavigation.getByRole('link', { name: 'Prüfungskontext auswählen', exact: true }),
          ).toHaveCount(0);
          await expect(
            mainNavigation.getByRole('link', { name: 'Benachrichtigungen', exact: true }),
          ).toBeVisible();
          await expect(
            mainNavigation.getByRole('link', { name: 'Ausfall und Ersatz', exact: true }),
          ).toBeVisible();

          await page.goto('/candidates');
          await expect(
            page.getByText('Dieser Demo-Bereich ist für Ihre Rolle nicht freigegeben.'),
          ).toBeVisible();
          await expect(page.locator('app-candidates')).toHaveCount(0);

          await page.goto('/exam-half-years');
          await expect(
            page.getByText('Dieser Demo-Bereich ist für Ihre Rolle nicht freigegeben.'),
          ).toBeVisible();

          await page.goto('/notifications');
          await expect(
            page.getByText('Externe Zustellung ist in der öffentlichen Demo deaktiviert.'),
          ).toBeVisible();
          await expect(
            page.getByRole('button', { name: 'Browser-Benachrichtigungen aktivieren' }),
          ).toHaveCount(0);
          await expect(
            page.getByRole('button', { name: 'Persönlichen Feed aktivieren' }),
          ).toHaveCount(0);
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
    await expect(page).toHaveURL('/demo-scenarios');
    const chairButton = page.getByRole('button', { name: 'Vorsitz', exact: true });
    await chairButton.focus();
    await expect(chairButton).toBeFocused();
    const workspaceReload = page.waitForRequest(
      (request) => request.method() === 'GET' && new URL(request.url()).pathname === '/api',
    );
    await page.keyboard.press('Enter');
    await workspaceReload;
    await expect(page.getByText('Vorsitz · ' + demoRoles.chair.display_name)).toBeVisible();
  });

  test('keeps demo scenarios and regular own-data paths screen-reader accessible @a11y', async ({
    page,
  }) => {
    await page.route('**/api/session', (route) =>
      route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({
          authenticated: true,
          account_id: demoRoles.examiner.account_id,
          person_id: demoRoles.examiner.person_id,
          committee_member_id: demoRoles.examiner.committee_member_id,
          is_operator: false,
          demo_role: 'examiner',
          display_name: demoRoles.examiner.display_name,
          capabilities: demoCapabilities('examiner'),
        }),
      }),
    );
    await page.route('**/api/demo/scenarios', (route) =>
      route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify(demoScenarioOverview('examiner')),
      }),
    );

    for (const path of ['/demo-scenarios', '/notifications', '/absence-reports']) {
      await page.goto(path);
      await expect(page.locator('main')).toBeVisible();
      const accessibility = await new AxeBuilder({ page }).include('main').analyze();
      expect(accessibility.violations).toEqual([]);
    }
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

        if (viewport.width <= 768) {
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
});
