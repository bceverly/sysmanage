import { test, expect, Page } from '@playwright/test';

/**
 * i18n layout-overflow guard.
 *
 * Translated UI labels run 30-50% longer than English (German, French, and
 * Russian are the usual worst cases).  When a button, toolbar, or column header
 * can't wrap, the extra width pushes the whole page wider than the viewport and
 * content runs off the right edge — exactly the symptom we hit on the docs site.
 *
 * This spec renders a sample of authenticated pages at several viewport widths in
 * the longest-growth locales and asserts the DOCUMENT never overflows
 * horizontally (``scrollWidth <= clientWidth``).  We check the document, not
 * individual scroll containers, so an intentionally horizontally-scrollable
 * MUI DataGrid (its own scroll area) doesn't false-positive — only something that
 * widens the page itself fails.
 *
 * The MuiButton theme override in ``App.tsx`` (whiteSpace: normal / overflowWrap)
 * is what keeps buttons wrapping instead of overflowing; this test is the gate
 * that catches a regression of it, or a new fixed-width element that can't cope
 * with a long translation.
 *
 * Runs under the default (authenticated) project so it exercises the real
 * toolbar/grid-bearing pages, not just login.  Seeding ``i18nextLng`` only sets
 * the language; it doesn't disturb the auth storage state.
 */

// Longest-growth locales — German (compounds), French (verbose), Russian
// (Cyrillic + long words).  Keep the set small: this is widths x locales x pages,
// so it grows fast against the CI budget.
const LOCALES = ['de', 'fr', 'ru'] as const;

// Tablet through wide-desktop.  This is the band where a non-wrapping toolbar
// overflows before the responsive breakpoints stack it.
const WIDTHS = [768, 1024, 1440] as const;

// A sample of authenticated, toolbar/grid-bearing routes.
const ROUTES = ['/', '/hosts', '/updates', '/settings'] as const;

async function seedLocale(page: Page, lang: string): Promise<void> {
  await page.addInitScript(
    ([key, value]) => {
      window.localStorage.setItem(key, value);
    },
    ['i18nextLng', lang],
  );
}

/**
 * Assert the document doesn't overflow horizontally, and if it does, report the
 * widest offending elements so the failure is actionable (which button/header
 * blew out the layout) rather than just a number.
 */
async function expectNoHorizontalOverflow(page: Page, label: string): Promise<void> {
  const result = await page.evaluate(() => {
    const de = document.documentElement;
    const vw = de.clientWidth;
    const offenders: string[] = [];
    // Only inspect interactive/label-bearing elements — those are what grow with
    // translation; a scrollable grid body is intentionally wide and excluded by
    // the document-level (not element-level) pass/fail.
    const sel =
      'button, .MuiButton-root, [role="toolbar"], .MuiToolbar-root, ' +
      '.MuiTab-root, .MuiChip-root, .MuiDataGrid-columnHeaderTitle, label';
    document.querySelectorAll(sel).forEach((el) => {
      const r = el.getBoundingClientRect();
      if (r.width > 0 && r.right > vw + 1) {
        const text = (el.textContent || (el as HTMLElement).className || '').trim();
        offenders.push(`${Math.round(r.right - vw)}px past: "${text.slice(0, 40)}"`);
      }
    });
    return { scrollW: de.scrollWidth, clientW: vw, offenders: offenders.slice(0, 12) };
  });

  // +2px tolerance for sub-pixel rounding / scrollbar gutter.
  expect(
    result.scrollW,
    `${label}: page is ${result.scrollW - result.clientW}px wider than the viewport ` +
      `(${result.clientW}px). Offenders:\n  ${result.offenders.join('\n  ') || '(none flagged)'}`,
  ).toBeLessThanOrEqual(result.clientW + 2);
}

for (const locale of LOCALES) {
  test.describe(`i18n overflow — ${locale}`, () => {
    for (const route of ROUTES) {
      for (const width of WIDTHS) {
        test(`${route} at ${width}px has no horizontal overflow (${locale})`, async ({
          page,
        }) => {
          await seedLocale(page, locale);
          await page.setViewportSize({ width, height: 900 });
          await page.goto(route);
          await page.waitForLoadState('domcontentloaded');
          // Let i18n hydrate + the layout settle (toolbars/grids mount async).
          await page.waitForTimeout(750);
          await expectNoHorizontalOverflow(page, `${route} @ ${width}px / ${locale}`);
        });
      }
    }
  });
}
