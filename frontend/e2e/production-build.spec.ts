import { expect, test } from './fixtures';

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
            expect(globalStyles.bodyFont).toContain('Source Sans 3');
            expect(globalStyles.canvasColor.trim()).not.toBe('');
          });
        }
      });
    }

    expect(cspErrors).toEqual([]);
  });
});
