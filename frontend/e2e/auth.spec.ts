import AxeBuilder from '@axe-core/playwright';

import { expect, test } from './fixtures';

test.describe('local password and TOTP authentication', () => {
  test.beforeEach(async ({ page }) => {
    await page.context().clearCookies();
    await page.route('**/api/session', (route) =>
      route.fulfill({
        status: 401,
        contentType: 'application/json',
        body: JSON.stringify({ error: 'Authentication required.' }),
      }),
    );
  });

  test('logs in with password and a second factor without putting secrets in the URL', async ({
    page,
  }) => {
    let authenticated = false;
    await page.unroute('**/api/session');
    await page.route('**/api/session', (route) =>
      authenticated
        ? route.fulfill({
            contentType: 'application/json',
            body: JSON.stringify({
              authenticated: true,
              account_id: 2,
              person_id: 4,
              committee_member_id: 7,
              is_operator: false,
            }),
          })
        : route.fulfill({
            status: 401,
            contentType: 'application/json',
            body: JSON.stringify({ error: 'Authentication required.' }),
          }),
    );
    await page.route('**/api/auth/login', (route) => {
      authenticated = true;
      return route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({
          authenticated: true,
          account_id: 2,
          expires_at: '2026-01-01T20:00:00+00:00',
        }),
      });
    });

    await page.goto('/login');
    await page.getByLabel('E-Mail-Adresse').fill('member@example.invalid');
    await page.getByLabel('Kennwort').fill('correct horse battery staple');
    await page.getByLabel('TOTP-Code oder Recovery-Code').fill('123456');
    await page.getByRole('button', { name: 'Anmelden' }).click();

    await expect(page).toHaveURL('/dashboard');
    expect(page.url()).not.toContain('correct');
    expect(page.url()).not.toContain('123456');
  });

  test('revokes a login when session validation fails after credentials are accepted', async ({
    page,
  }) => {
    let loginAccepted = false;
    let logoutRequests = 0;
    await page.unroute('**/api/session');
    await page.route('**/api/session', (route) =>
      loginAccepted
        ? route.fulfill({
            status: 503,
            contentType: 'application/json',
            body: JSON.stringify({ error: { message: 'Session validation failed.' } }),
          })
        : route.fulfill({
            status: 401,
            contentType: 'application/json',
            body: JSON.stringify({ error: 'Authentication required.' }),
          }),
    );
    await page.route('**/api/auth/login', (route) => {
      loginAccepted = true;
      return route.fulfill({
        contentType: 'application/json',
        headers: { 'Set-Cookie': 'session=issued; HttpOnly; Path=/' },
        body: JSON.stringify({
          authenticated: true,
          account_id: 2,
          expires_at: '2026-01-01T20:00:00+00:00',
        }),
      });
    });
    await page.route('**/api/session/logout', (route) => {
      logoutRequests += 1;
      loginAccepted = false;
      return route.fulfill({
        status: 204,
        headers: { 'Set-Cookie': 'session=; Max-Age=0; HttpOnly; Path=/' },
      });
    });

    await page.goto('/login');
    await page.getByLabel('E-Mail-Adresse').fill('member@example.invalid');
    await page.getByLabel('Kennwort').fill('correct horse battery staple');
    await page.getByLabel('TOTP-Code oder Recovery-Code').fill('123456');
    await page.getByRole('button', { name: 'Anmelden' }).click();

    await expect(page.getByRole('alert')).toHaveText('Session validation failed.');
    expect(logoutRequests).toBe(1);
    await expect(page).toHaveURL('/login');
    expect(await page.context().cookies()).toEqual([]);
  });

  test('@a11y redirects protected deep links before rendering the application shell', async ({
    page,
  }) => {
    await page.goto('/candidates');

    await expect(page).toHaveURL('/login');
    await expect(page.getByRole('heading', { name: 'Anmelden' })).toBeVisible();
    await expect(page.locator('.app-shell')).toHaveCount(0);

    const accessibility = await new AxeBuilder({ page }).include('main').analyze();
    expect(accessibility.violations).toEqual([]);
  });

  test('@a11y activates an invitation and shows recovery codes exactly once', async ({ page }) => {
    await page.route('**/api/auth/invitation/prepare', (route) =>
      route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({
          email: 'member@example.invalid',
          expires_at: '2026-01-02T12:00:00+00:00',
          totp_secret: 'JBSWY3DPEHPK3PXP',
        }),
      }),
    );
    await page.route('**/api/auth/invitation/activate', (route) =>
      route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({
          activated: true,
          account: { id: 2, email: 'member@example.invalid', is_operator: false },
          recovery_codes: ['ABCD2345EF', 'GHJK6789MN'],
        }),
      }),
    );

    await page.goto('/activate');
    await expect(page.getByRole('heading', { name: 'Einladung aktivieren' })).toBeVisible();
    await page.getByLabel('Einladungstoken').fill('one-time-invitation-token');
    await page.getByRole('button', { name: 'Einrichtung beginnen' }).click();
    await expect(page.getByText('JBSWY3DPEHPK3PXP')).toBeVisible();
    await page.getByLabel('Neues Kennwort').fill('correct horse battery staple');
    await page.getByLabel('Kennwort wiederholen').fill('correct horse battery staple');
    await page.getByLabel('TOTP-Code zur Bestätigung').fill('123456');
    await page.getByRole('button', { name: 'Aktivierung abschließen' }).click();
    await expect(
      page.getByRole('heading', { name: 'Recovery-Codes sicher verwahren' }),
    ).toBeVisible();
    await expect(page.getByText('ABCD2345EF')).toBeVisible();
    await expect(page).toHaveURL(/\/activate$/);

    const accessibility = await new AxeBuilder({ page }).include('.auth-card').analyze();
    expect(accessibility.violations).toEqual([]);
  });
});
