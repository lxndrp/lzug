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
    await page.route('**/api/auth/login', (route) =>
      route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({
          authenticated: true,
          account_id: 2,
          expires_at: '2026-01-01T20:00:00+00:00',
        }),
      }),
    );

    await page.goto('/login');
    await page.getByLabel('E-Mail-Adresse').fill('member@example.invalid');
    await page.getByLabel('Kennwort').fill('correct horse battery staple');
    await page.getByLabel('TOTP-Code oder Recovery-Code').fill('123456');
    await page.getByRole('button', { name: 'Anmelden' }).click();

    await expect(page).toHaveURL('/dashboard');
    expect(page.url()).not.toContain('correct');
    expect(page.url()).not.toContain('123456');
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
