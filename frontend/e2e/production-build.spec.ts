import { expect, test } from './fixtures';
import { demoRoles, demoCapabilities } from './quality-support';

const colorSchemes = ['light', 'dark'] as const;
const viewports = [
  { name: 'desktop', width: 1440, height: 1000 },
  { name: 'mobile', width: 390, height: 844 },
] as const;

test.describe('optimized frontend artifact', () => {
  test.skip(
    process.env.LZUG_E2E_PRODUCTION_BUILD !== 'true',
    'The optimized artifact requires the production Playwright server.',
  );

  test('renders global styles under the backend CSP', async ({ page }) => {
    const cspErrors: string[] = [];
    page.on('console', (message) => {
      if (
        message.type() === 'error' &&
        /content security policy|inline script/i.test(message.text())
      ) {
        cspErrors.push(message.text());
      }
    });

    for (const viewport of viewports) {
      await test.step(viewport.name, async () => {
        await page.setViewportSize(viewport);

        for (const colorScheme of colorSchemes) {
          await test.step(colorScheme, async () => {
            await page.emulateMedia({ colorScheme });
            const response = await page.request.get('/api/health');
            expect(response.status()).toBe(200);
            await page.goto('/login', { waitUntil: 'domcontentloaded' });
            await expect(page.getByRole('main')).toBeVisible();
            await expect(page.getByRole('heading', { name: 'Übersicht' })).toBeVisible();

            const csp = response.headers()['content-security-policy'] ?? '';
            expect(csp).toContain("script-src 'self';");
            expect(csp).not.toMatch(/script-src[^;]*unsafe-inline/);

            const stylesheetLinks = await page
              .locator('link[rel="stylesheet"]')
              .evaluateAll((links) =>
                links.map((link) => ({
                  media: link.getAttribute('media'),
                  onload: link.getAttribute('onload'),
                })),
              );
            expect(stylesheetLinks.length).toBeGreaterThan(0);
            expect(stylesheetLinks).toEqual(
              expect.arrayContaining([expect.objectContaining({ media: null, onload: null })]),
            );

            const globalStyles = await page.evaluate(() => ({
              bodyBackground: getComputedStyle(document.body).backgroundColor,
              bodyFont: getComputedStyle(document.body).fontFamily,
              canvasColor: getComputedStyle(document.documentElement).getPropertyValue(
                '--app-color-canvas',
              ),
            }));
            expect(globalStyles.bodyBackground).not.toBe('rgba(0, 0, 0, 0)');
            expect(globalStyles.bodyFont).toContain('Inter');
            expect(globalStyles.canvasColor.trim()).not.toBe('');
          });
        }
      });
    }

    expect(cspErrors).toEqual([]);
  });

  test('keeps demo runtime disabled in product builds', async ({ page }) => {
    let scenarioRequests = 0;
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
    await page.route('**/api/demo/scenarios', async (route) => {
      scenarioRequests += 1;
      await route.continue();
    });

    await page.goto('/demo-scenarios');

    await expect(page.getByRole('alert')).toContainText(
      'Der Demo-Arbeitsstand konnte nicht geladen werden.',
    );
    expect(scenarioRequests).toBe(0);
  });
});
