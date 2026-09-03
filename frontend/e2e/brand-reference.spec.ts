import { mkdirSync, readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import type { Page } from '@playwright/test';

import { expect, test } from './fixtures';

const enabled = process.env['LZUG_BRAND_REFERENCES'] === 'true';
const root = resolve(dirname(fileURLToPath(import.meta.url)), '../..');
const output = resolve(root, 'brand/review/final');
const desktop = { width: 1440, height: 1000 };
const mobile = { width: 390, height: 844 };

test.skip(!enabled, 'Brand references are generated only by task brand:references.');
test.describe.configure({ mode: 'serial', timeout: 120_000 });

async function prepare(
  page: Page,
  path: string,
  options: {
    scheme?: 'light' | 'dark';
    viewport?: { width: number; height: number };
    waitForStable?: boolean;
  } = {},
): Promise<void> {
  await page.emulateMedia({
    colorScheme: options.scheme ?? 'light',
    reducedMotion: 'reduce',
  });
  await page.setViewportSize(options.viewport ?? desktop);
  await page.goto(path);
  await expect(page.locator('main')).toBeVisible();
  if (options.waitForStable !== false) {
    await page.waitForLoadState('networkidle');
    await expect(page.locator('.app-progress')).toHaveCount(0, { timeout: 30_000 });
  }
  await page.evaluate(() => document.fonts.ready);
  await page.addStyleTag({
    content: `
      *, *::before, *::after {
        animation-duration: 0s !important;
        caret-color: transparent !important;
        transition-duration: 0s !important;
      }
    `,
  });
  await page.evaluate(
    () =>
      new Promise<void>((resolveFrame) =>
        requestAnimationFrame(() => requestAnimationFrame(() => resolveFrame())),
      ),
  );
}

async function capture(page: Page, name: string, fullPage = true): Promise<void> {
  mkdirSync(output, { recursive: true });
  await page.evaluate(async () => {
    await document.fonts.ready;
    if (document.activeElement instanceof HTMLElement) document.activeElement.blur();
    await new Promise<void>((resolveFrame) =>
      requestAnimationFrame(() => requestAnimationFrame(() => resolveFrame())),
    );
  });
  await page.waitForTimeout(500);
  if (fullPage) await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({
    path: resolve(output, `${name}.png`),
    fullPage,
    animations: 'disabled',
    caret: 'hide',
  });
}

test('captures product shell, authentication, data, forms, and detail views', async ({ page }) => {
  await prepare(page, '/dashboard');
  await expect(page.getByRole('heading', { name: 'Übersicht' })).toBeVisible();
  await capture(page, 'product-dashboard-light-desktop');

  await prepare(page, '/dashboard', { scheme: 'dark' });
  await capture(page, 'product-dashboard-dark-desktop');

  await prepare(page, '/candidates', { scheme: 'dark' });
  await expect(page.locator('tbody tr').first()).toBeVisible();
  await capture(page, 'product-table-dark-desktop');

  await prepare(page, '/candidates');
  await page.getByText('Neuen Prüfling anlegen', { exact: true }).click();
  await page.getByRole('button', { name: 'Prüfling anlegen', exact: true }).click();
  await expect(page.getByText('Prüfling noch nicht angelegt')).toBeVisible();
  await page
    .locator('#candidate-create-editor')
    .evaluate((editor) => editor.scrollIntoView({ block: 'start', behavior: 'instant' }));
  await capture(page, 'product-form-validation-light-desktop', false);

  await prepare(page, '/locations');
  await expect(page.getByRole('heading', { name: 'Prüfungsorte' })).toBeVisible();
  await capture(page, 'product-detail-cards-light-desktop');

  await page.context().clearCookies();
  await page.route('**/api/session', (route) =>
    route.fulfill({
      status: 401,
      contentType: 'application/json',
      body: JSON.stringify({ error: 'Authentication required.' }),
    }),
  );
  await prepare(page, '/login');
  await expect(page.getByRole('heading', { name: 'Anmelden' })).toBeVisible();
  await capture(page, 'product-login-light-desktop');
});

test('captures empty, loading, success, warning, error, and conflict states', async ({ page }) => {
  await page.route('**/api/candidates', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ items: [], _links: {} }),
    }),
  );
  await prepare(page, '/candidates');
  await expect(page.getByText('Noch keine Prüflinge vorhanden.')).toBeVisible();
  await capture(page, 'state-empty-light-desktop');
  await page.unroute('**/api/candidates');

  let releaseSummary = (): void => undefined;
  const summaryGate = new Promise<void>((resolveGate) => {
    releaseSummary = resolveGate;
  });
  await page.route('**/api/round-summary*', async (route) => {
    await summaryGate;
    await route.continue();
  });
  await prepare(page, '/dashboard', { scheme: 'dark', waitForStable: false });
  await expect(page.locator('.app-progress')).toBeVisible();
  await capture(page, 'state-loading-dark-desktop', false);
  releaseSummary();
  await expect(page.locator('.app-progress')).toHaveCount(0);
  await page.unroute('**/api/round-summary*');

  await prepare(page, '/candidates');
  await page.getByText('Neuen Prüfling anlegen', { exact: true }).click();
  await page.locator('#candidateFirstName').fill('Δήμητρα');
  await page.locator('#candidateLastName').fill('Παπαδοπούλου');
  await page.locator('#candidateExamNumber').fill('REF-2026-568');
  await page.getByRole('button', { name: 'Prüfling anlegen', exact: true }).click();
  await expect(page.getByText('Prüfling angelegt')).toBeVisible();
  await capture(page, 'state-success-light-desktop');
  await page.getByRole('button', { name: 'Meldung schließen' }).click();

  await prepare(page, '/dashboard', { scheme: 'dark' });
  await expect(page.getByText(/offen/).first()).toBeVisible();
  await capture(page, 'state-warning-dark-desktop');

  await page.route('**/api/round-summary*', (route) => route.fulfill({ status: 500 }));
  await page.getByRole('button', { name: 'Aktualisieren' }).click();
  await expect(page.getByRole('alert').getByText('Synchronisierung nicht möglich')).toBeVisible();
  await capture(page, 'state-error-dark-desktop');
  await page.unroute('**/api/round-summary*');

  let proposalGenerated = false;
  await page.route('**/api/exam-rounds/1', async (route) => {
    if (route.request().method() !== 'GET') return route.continue();
    const response = await route.fetch();
    const round = await response.json();
    await route.fulfill({
      response,
      json: proposalGenerated ? { ...round, status: 'plan_proposed' } : round,
    });
  });
  await page.route('**/api/planning-proposals', async (route) => {
    proposalGenerated = true;
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        status: 'plan_proposed',
        counts: { planned_slots: 0 },
        validation: {
          passed: false,
          messages: ['Zwei Ausschüsse beanspruchen dieselbe Person zur selben Zeit.'],
        },
      }),
    });
  });
  await prepare(page, '/scheduling-overview/1', { scheme: 'dark' });
  await page.getByRole('button', { name: 'Planungsvorschlag erzeugen' }).click();
  await expect(
    page.getByText('Ausschussübergreifende Konflikte verhindern die Bestätigung'),
  ).toBeVisible();
  await capture(page, 'state-conflict-dark-desktop');
});

test('captures mobile navigation, 200-percent text reflow, and the complete asset contract', async ({
  page,
}) => {
  await prepare(page, '/dashboard', { scheme: 'dark', viewport: mobile });
  await expect(page.locator('.app-nav-context')).toHaveCount(1);
  await page.getByRole('button', { name: 'Navigation öffnen' }).click();
  await expect(page.getByRole('complementary', { name: 'Prüfungsverwaltung' })).toBeVisible();
  await capture(page, 'product-mobile-navigation-dark', false);

  await prepare(page, '/dashboard', { viewport: mobile });
  await page.evaluate(() => document.documentElement.style.setProperty('font-size', '200%'));
  await expect
    .poll(() => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth))
    .toBe(true);
  await capture(page, 'product-reflow-200-percent-light', false);

  const asset = (name: string): string => {
    const bytes = readFileSync(resolve(root, `brand/derived/${name}`));
    const mime = name.endsWith('.svg') ? 'image/svg+xml' : 'image/png';
    return `data:${mime};base64,${bytes.toString('base64')}`;
  };
  const variants = ['light', 'dark', 'black', 'white'];
  const samples = variants
    .map(
      (variant) => `<figure class="${variant}">
        <div class="backdrop"><img src="${asset(`logo-mark-${variant}.svg`)}" alt="${variant} Bildmarke"></div>
        <img class="lockup" src="${asset(`logo-horizontal-${variant}.svg`)}" alt="${variant} Wort-/Bildmarke">
        <figcaption>${variant}</figcaption>
      </figure>`,
    )
    .join('');
  const sizes = [16, 32, 48]
    .map(
      (size) =>
        `<figure><img src="${asset(`favicon-${size}.png`)}" width="${size}" height="${size}" alt="${size} Pixel"><figcaption>${size}px</figcaption></figure>`,
    )
    .join('');
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.setContent(`<!doctype html><html lang="de"><head><style>
    * { box-sizing: border-box; } body { margin: 0; padding: 48px; color: #1e1a2e; background: #f7f7fb; font: 18px Inter, sans-serif; }
    h1, h2 { margin: 0 0 24px; } h2 { margin-top: 40px; } .grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 24px; }
    figure { margin: 0; } .backdrop { display: grid; min-height: 260px; place-items: center; border: 1px solid #d9d6e6; background: repeating-conic-gradient(#fff 0 25%, #e8e7ee 0 50%) 50% / 24px 24px; }
    .backdrop img { width: 180px; height: 180px; } .lockup { width: 320px; max-width: 100%; margin-top: 12px; }
    .dark .backdrop, .white .backdrop { background: #151225; } figcaption { margin-top: 8px; font-weight: 700; text-transform: capitalize; }
    .sizes { display: flex; min-height: 96px; align-items: end; gap: 36px; padding: 24px; border: 1px solid #d9d6e6; background: #fff; }
    .sizes figure { display: grid; min-width: 64px; justify-items: center; gap: 8px; }
  </style></head><body><h1>lzug Assetvertrag</h1><div class="grid">${samples}</div><h2>Kleine Rasterableitungen</h2><div class="sizes">${sizes}</div></body></html>`);
  await capture(page, 'assets-theme-monochrome-small-sizes', true);
});
