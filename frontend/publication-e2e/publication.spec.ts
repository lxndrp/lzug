import { expect, test, type Page } from '@playwright/test';

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

async function readDemoOrigin(page: Page): Promise<string> {
  const configuredValue = await page.locator('[data-demo-start]').getAttribute('data-demo-url');
  expect(configuredValue, 'homepage configures a demo URL').toBeTruthy();

  let configuredUrl: URL;
  try {
    configuredUrl = new URL(configuredValue ?? '');
  } catch {
    throw new Error('homepage configures an invalid demo URL');
  }
  expect(configuredUrl.protocol).toBe('https:');
  expect(configuredUrl.username).toBe('');
  expect(configuredUrl.password).toBe('');
  expect(configuredUrl.pathname).toBe('/');
  expect(configuredUrl.search).toBe('');
  expect(configuredUrl.hash).toBe('');
  expect(configuredValue).toBe(configuredUrl.origin);
  return configuredUrl.origin;
}

test.describe('public site browser contract', () => {
  test.describe.configure({ timeout: 60_000 });

  test('renders desktop and mobile themes without browser errors', async ({
    browser,
  }, testInfo) => {
    const results = [];
    for (const candidate of candidates) {
      await test.step(candidate.name, async () => {
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
        const consoleErrors: string[] = [];
        const failedResponses: string[] = [];
        page.on('console', (message) => {
          if (message.type() === 'error') {
            const { url, lineNumber, columnNumber } = message.location();
            consoleErrors.push(
              `${message.text()} (${url || 'unknown URL'}:${lineNumber}:${columnNumber})`,
            );
          }
        });
        page.on('response', (response) => {
          if (response.status() >= 400) {
            failedResponses.push(`${response.status()} ${response.url()}`);
          }
        });

        const response = await page.goto('/', { waitUntil: 'networkidle' });
        expect(response?.ok(), 'homepage response').toBe(true);
        const structure = await page.evaluate(() => ({
          h1: document.querySelectorAll('h1').length,
          main: document.querySelectorAll('main').length,
          nav: document.querySelectorAll('nav').length,
          search: document.querySelectorAll('input[type="search"]').length,
          demoStart: document.querySelectorAll('[data-demo-start]').length,
          themeVariant: document.documentElement.dataset.rThemeVariant,
          overflow: document.documentElement.scrollWidth - window.innerWidth,
        }));
        expect(structure.h1).toBe(1);
        expect(structure.main).toBe(1);
        expect(structure.nav).toBeGreaterThanOrEqual(1);
        expect(structure.search).toBeGreaterThanOrEqual(1);
        expect(structure.demoStart).toBe(1);
        expect(structure.overflow).toBeLessThanOrEqual(0);
        expect(structure.themeVariant).toBe(candidate.themeVariant);

        const palette = await page.evaluate(() => {
          const resolveColor = (property: string) => {
            const probe = document.createElement('span');
            probe.style.color = `var(${property})`;
            document.body.append(probe);
            const color = getComputedStyle(probe).color;
            probe.remove();
            return color;
          };

          return {
            primary: resolveColor('--PRIMARY-color'),
            brandInk: resolveColor('--lzug-color-brand-ink'),
            mainBackground: resolveColor('--MAIN-BG-color'),
            canvas: resolveColor('--lzug-color-neutral-canvas'),
            menuBackground: resolveColor('--MENU-SECTIONS-BG-color'),
            surface: resolveColor('--lzug-color-neutral-surface'),
            menuText: resolveColor('--MENU-SECTIONS-LINK-color'),
            text: resolveColor('--lzug-color-text'),
          };
        });
        expect(palette.primary).toBe(palette.brandInk);
        expect(palette.mainBackground).toBe(palette.canvas);
        expect(palette.menuBackground).toBe(palette.surface);
        expect(palette.menuText).toBe(palette.text);
        expect(palette.primary).not.toBe('rgb(125, 201, 3)');

        await page.evaluate(() => document.fonts.ready);
        const typography = await page.evaluate(() => {
          const fontFamily = (selector: string) => {
            const element = document.querySelector(selector);
            if (!(element instanceof HTMLElement)) {
              throw new Error(`missing typography contract element: ${selector}`);
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
            body: fontFamily('.publication-lead'),
            heading: fontFamily('.publication-hero h1'),
            navigation: fontFamily('#R-sidebar a'),
            button: fontFamily('.publication-button'),
            formControl: fontFamily('#R-search-by'),
            code: codeFont,
            pre: preFont,
          };
        });
        expect(typography.interLoaded).toBe(true);
        for (const role of ['body', 'heading', 'navigation', 'button', 'formControl'] as const) {
          expect(typography[role]).toContain('Inter Variable');
        }
        expect(typography.code.toLowerCase()).toContain('monospace');
        expect(typography.pre.toLowerCase()).toContain('monospace');
        expect(consoleErrors).toEqual([]);
        expect(failedResponses).toEqual([]);

        const screenshot = testInfo.outputPath(`${candidate.name}.png`);
        await page.screenshot({ path: screenshot, fullPage: true });
        await testInfo.attach(candidate.name, { path: screenshot, contentType: 'image/png' });
        results.push({ ...candidate, ...structure });
        await context.close();
      });
    }
    await testInfo.attach('browser-results', {
      body: JSON.stringify(results, null, 2),
      contentType: 'application/json',
    });
  });

  test('renders the projected handbook with search', async ({ page }) => {
    const response = await page.goto('/handbuch/', { waitUntil: 'networkidle' });
    expect(response?.ok(), 'handbook response').toBe(true);
    await expect(page.locator('input[type="search"]')).toHaveCount(1);
  });

  test('attaches portal content evidence for the shared visual grammar', async ({
    page,
  }, testInfo) => {
    await page.goto('/handbuch/', { waitUntil: 'networkidle' });
    await expect(page.locator('main')).toBeVisible();
    await page.evaluate(() => document.fonts.ready);

    const evidence = await page.screenshot({ fullPage: true });
    await testInfo.attach('portal-content-desktop-light', {
      body: evidence,
      contentType: 'image/png',
    });
  });

  test('keeps the shared focus and reflow grammar at 200 percent', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto('/', { waitUntil: 'networkidle' });
    const primary = page.getByRole('button', { name: 'Demo starten' });
    await primary.focus();
    await expect(primary).toBeFocused();
    await expect
      .poll(() => primary.evaluate((element) => getComputedStyle(element).outlineWidth))
      .toBe('3px');

    await page.evaluate(() => document.documentElement.style.setProperty('font-size', '200%'));
    await expect
      .poll(() =>
        page.evaluate(
          () => document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1,
        ),
      )
      .toBe(true);
  });

  test('warms up the configured demo origin before navigation', async ({ page }) => {
    await page.goto('/', { waitUntil: 'networkidle' });
    const warmupDemoOrigin = await readDemoOrigin(page);
    let readinessRequests = 0;
    await page.route(`${warmupDemoOrigin}/**`, (route) => route.abort('blockedbyclient'));
    await page.route(`${warmupDemoOrigin}/api/ready`, async (route) => {
      readinessRequests += 1;
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          status: 'ready',
          _links: { self: { href: '/api/ready' } },
        }),
      });
    });
    await page.route(`${warmupDemoOrigin}/`, (route) =>
      route.fulfill({ status: 200, body: 'Demo' }),
    );

    await page.getByRole('button', { name: 'Demo starten' }).click({ noWaitAfter: true });
    await page.waitForURL(`${warmupDemoOrigin}/`);
    expect(readinessRequests).toBe(1);
  });

  test('offers an accessible retry after a failed warm-up', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto('/', { waitUntil: 'networkidle' });
    const failureDemoOrigin = await readDemoOrigin(page);
    let failedReadinessRequests = 0;
    await page.route(`${failureDemoOrigin}/**`, (route) => route.abort('blockedbyclient'));
    await page.route(`${failureDemoOrigin}/api/ready`, (route) => {
      failedReadinessRequests += 1;
      return route.fulfill({
        status: 503,
        contentType: 'application/json',
        body: JSON.stringify({ status: 'unavailable' }),
      });
    });
    await page.locator('[data-demo-start]').evaluate((element: HTMLElement) => {
      element.dataset.demoMaximumAttempts = '1';
      element.dataset.demoTotalTimeoutMs = '1000';
    });

    await page.getByRole('button', { name: 'Demo starten' }).click({ noWaitAfter: true });
    await expect(page.getByText('Demo konnte nicht gestartet werden')).toBeVisible();
    const retry = page.getByRole('button', { name: 'Erneut versuchen' });
    await expect(retry).toBeEnabled();
    await retry.focus();
    await expect(retry).toBeFocused();
    const retryResponse = page.waitForResponse(
      (response) => response.url() === `${failureDemoOrigin}/api/ready`,
    );
    await retry.click({ noWaitAfter: true });
    await retryResponse;
    await expect(page.getByText('Demo konnte nicht gestartet werden')).toBeVisible();
    expect(failedReadinessRequests).toBe(2);
  });
});
