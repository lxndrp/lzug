import { mkdirSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import type { Browser, Page } from '@playwright/test';
import { expect, test } from '@playwright/test';

const enabled = process.env['LZUG_BRAND_REFERENCES'] === 'true';
const output = resolve(dirname(fileURLToPath(import.meta.url)), '../../brand/review/final');

test.skip(!enabled, 'Brand references are generated only by task brand:references.');
test.describe.configure({ mode: 'serial', timeout: 60_000 });

async function themedPage(
  browser: Browser,
  scheme: 'light' | 'dark',
  viewport: { width: number; height: number },
): Promise<Page> {
  const context = await browser.newContext({
    colorScheme: scheme,
    reducedMotion: 'reduce',
    viewport,
  });
  const page = await context.newPage();
  await page.addInitScript((variant) => {
    window.localStorage.setItem(
      'https://lzug.repertoire.papaspyrou.name/variant',
      `relearn-${variant}`,
    );
  }, scheme);
  return page;
}

async function capture(page: Page, name: string): Promise<void> {
  mkdirSync(output, { recursive: true });
  await page.screenshot({ path: resolve(output, `${name}.png`), fullPage: true });
  await page.context().close();
}

async function expectInterContract(page: Page, controlSelector: string): Promise<void> {
  await page.evaluate(() => document.fonts.ready);
  const contract = await page.evaluate((selector) => {
    const fontFamily = (elementSelector: string) => {
      const element = document.querySelector(elementSelector);
      if (!(element instanceof HTMLElement)) {
        throw new Error(`missing typography contract element: ${elementSelector}`);
      }
      return getComputedStyle(element).fontFamily;
    };
    const code = document.createElement('code');
    const pre = document.createElement('pre');
    code.textContent = 'const lzug = true;';
    pre.textContent = 'task quality';
    document.body.append(code, pre);
    const codeFont = getComputedStyle(code).fontFamily;
    const preFont = getComputedStyle(pre).fontFamily;
    code.remove();
    pre.remove();

    return {
      interLoaded: document.fonts.check('16px "Inter Variable"', 'Prüfungsplanung'),
      body: fontFamily('main p'),
      heading: fontFamily('main h1'),
      navigation: fontFamily('#R-sidebar a'),
      button: fontFamily(selector),
      formControl: fontFamily('#R-search-by'),
      code: codeFont,
      pre: preFont,
    };
  }, controlSelector);

  expect(contract.interLoaded).toBe(true);
  for (const role of ['body', 'heading', 'navigation', 'button', 'formControl'] as const) {
    expect(contract[role]).toContain('Inter Variable');
  }
  expect(contract.code.toLowerCase()).toContain('monospace');
  expect(contract.pre.toLowerCase()).toContain('monospace');
}

test('captures the public landing page in light desktop and dark mobile', async ({ browser }) => {
  const light = await themedPage(browser, 'light', { width: 1440, height: 1000 });
  await light.goto('/', { waitUntil: 'networkidle' });
  await expect(light.locator('.publication-wordmark-light')).toBeVisible();
  await expectInterContract(light, '.publication-button');
  await capture(light, 'publication-landing-light-desktop');

  const dark = await themedPage(browser, 'dark', { width: 390, height: 844 });
  await dark.goto('/', { waitUntil: 'networkidle' });
  await expect(dark.locator('.publication-wordmark-dark')).toBeVisible();
  await expectInterContract(dark, '.publication-button');
  await capture(dark, 'publication-landing-dark-mobile');
});

test('captures the public handbook with the shared brand contract', async ({ browser }) => {
  const page = await themedPage(browser, 'light', { width: 1440, height: 1000 });
  await page.goto('/handbuch/', { waitUntil: 'networkidle' });
  await expect(page.locator('main')).toBeVisible();
  await expectInterContract(page, '#R-topbar button');
  await capture(page, 'publication-handbook-light-desktop');
});
