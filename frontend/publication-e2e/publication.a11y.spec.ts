import AxeBuilder from '@axe-core/playwright';
import { expect, test } from '@playwright/test';

const candidates = [
  {
    name: 'desktop-light',
    colorScheme: 'light',
    themeVariant: 'relearn-light',
    viewport: { width: 1440, height: 1000 },
  },
  {
    name: 'desktop-dark',
    colorScheme: 'dark',
    themeVariant: 'relearn-dark',
    viewport: { width: 1440, height: 1000 },
  },
  {
    name: 'mobile-light',
    colorScheme: 'light',
    themeVariant: 'relearn-light',
    viewport: { width: 390, height: 844 },
  },
  {
    name: 'mobile-dark',
    colorScheme: 'dark',
    themeVariant: 'relearn-dark',
    viewport: { width: 390, height: 844 },
  },
] as const;

test.describe('public site accessibility contract', () => {
  test.describe.configure({ timeout: 60_000 });

  for (const candidate of candidates) {
    test(`${candidate.name} has no blocking axe findings @a11y`, async ({ browser }, testInfo) => {
      const context = await browser.newContext({
        viewport: candidate.viewport,
        colorScheme: candidate.colorScheme,
      });
      const page = await context.newPage();
      await page.addInitScript((themeVariant) => {
        window.localStorage.setItem(
          'https://lzug.repertoire.papaspyrou.name/variant',
          themeVariant,
        );
      }, candidate.themeVariant);
      await page.goto('/', { waitUntil: 'networkidle' });

      const accessibility = await new AxeBuilder({ page }).analyze();
      const blocking = accessibility.violations.filter(
        ({ impact }) => impact === 'critical' || impact === 'serious',
      );
      await testInfo.attach('axe-results', {
        body: JSON.stringify(accessibility, null, 2),
        contentType: 'application/json',
      });
      expect(blocking, `${candidate.name} blocking axe violations`).toEqual([]);
      await context.close();
    });
  }
});
