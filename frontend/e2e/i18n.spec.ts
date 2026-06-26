import { test, expect, Page } from '@playwright/test';

/**
 * UI translation smoke tests.
 *
 * Verifies the i18n wiring on a sample of locales by setting
 * ``localStorage.i18nextLng`` (the key the
 * ``i18next-browser-languagedetector`` plugin reads) before
 * navigating, then asserting the page renders translated text
 * — not raw English fallbacks, and not unresolved keys like
 * ``login.title`` leaking through.
 *
 * The static i18n validators in ``make lint`` already check that
 * every code-referenced key exists in every locale.  THIS file
 * closes the loop: it confirms the keys actually wire up at
 * render time on the LOGIN page (no auth needed, smallest
 * possible surface), so a future regression where a component
 * forgets ``useTranslation`` or hard-codes English shows up
 * in CI.
 *
 * Coverage: a representative sample of the 14 supported locales
 * — not all 14, because running this spec across every locale
 * would dominate the CI test budget for marginal incremental
 * confidence.  The sample picks one Latin-script (es), one
 * Germanic (de), one Asian script (ja), and one RTL (ar) so we
 * exercise both LTR and RTL rendering.
 */

// Override the chromium project's authenticated storage state — the
// login page is the test target, so we explicitly want NO auth here.
test.use({ storageState: { cookies: [], origins: [] } });

/**
 * Expected translation of ``login.title`` for each locale we sample.
 * Hard-coded here (rather than re-reading the JSON at test time)
 * so a translation change is a deliberate edit to BOTH places — the
 * test catches drift if someone retranslates the key on one side
 * but not the other.
 *
 * Keep in sync with ``frontend/public/locales/<lang>/translation.json``
 * key ``login.title``.
 */
const LOCALE_SAMPLES: ReadonlyArray<{
  readonly code: string;
  readonly loginHeading: RegExp;
  readonly description: string;
}> = [
  { code: 'en', loginHeading: /^Login$/i, description: 'baseline English' },
  { code: 'es', loginHeading: /^Acceso$/i, description: 'Spanish (LTR Latin)' },
  { code: 'de', loginHeading: /^Anmelden$/i, description: 'German (LTR Germanic)' },
  { code: 'ja', loginHeading: /^ログイン$/, description: 'Japanese (CJK)' },
  { code: 'ar', loginHeading: /^تسجيل/, description: 'Arabic (RTL)' },
];

/**
 * Pre-seed localStorage with the target locale BEFORE the SPA boots.
 *
 * ``i18next-browser-languagedetector`` reads ``i18nextLng`` from
 * localStorage on first init; if we set it after navigation, the
 * detector has already picked a different locale.  The trick is
 * Playwright's ``addInitScript`` — it runs in the page context
 * BEFORE any other script on every navigation.
 */
async function seedLocale(page: Page, lang: string): Promise<void> {
  await page.addInitScript(
    ([key, value]) => {
      window.localStorage.setItem(key, value);
    },
    ['i18nextLng', lang],
  );
}

test.describe('i18n smoke — login page renders in each sampled locale', () => {
  for (const { code, loginHeading, description } of LOCALE_SAMPLES) {
    test(`login heading translates to ${code} (${description})`, async ({ page }) => {
      await seedLocale(page, code);
      await page.goto('/login');
      await page.waitForLoadState('domcontentloaded');

      // The login heading uses the ``login.title`` key.  We match
      // against the locale's translated regex so an unresolved key
      // ("login.title") or an English fallback ("Login") fails the
      // non-English locale tests.
      const heading = page.getByRole('heading', { name: loginHeading }).first();
      await expect(heading).toBeVisible({ timeout: 20000 });
    });
  }
});

test.describe('i18n smoke — locale persists across reload', () => {
  test('refreshing the page keeps the selected language', async ({ page }) => {
    // Pick a non-default locale so the assertion is meaningful.
    await seedLocale(page, 'de');
    await page.goto('/login');
    await page.waitForLoadState('domcontentloaded');

    await expect(
      page.getByRole('heading', { name: /^Anmelden$/i }).first(),
    ).toBeVisible({ timeout: 20000 });

    // Reload — localStorage survives, language detector must pick it
    // up again on the second init.
    await page.reload();
    await page.waitForLoadState('domcontentloaded');

    await expect(
      page.getByRole('heading', { name: /^Anmelden$/i }).first(),
    ).toBeVisible({ timeout: 20000 });
  });
});

test.describe('i18n smoke — no unresolved keys leak through', () => {
  /**
   * Catches the common regression where a component does
   * ``t('foo.bar')`` but ``foo.bar`` isn't in any translation file —
   * react-i18next renders the raw key as visible text.  These keys
   * always contain a dot, never appear in real copy, and would be
   * highly visible in any UI: assert none are on the login page in
   * any sampled locale.
   */
  for (const { code, description } of LOCALE_SAMPLES) {
    test(`no dotted key fragments visible on login in ${code} (${description})`, async ({
      page,
    }) => {
      await seedLocale(page, code);
      await page.goto('/login');
      await page.waitForLoadState('domcontentloaded');

      // Wait for the form to be ready before scraping body text — i18n
      // hydration can lag the first render by a frame.
      await page.locator('#userid').waitFor({ state: 'visible', timeout: 20000 });

      const bodyText = (await page.locator('body').innerText()).trim();

      // Pattern: lowercase + dotted segments + lowercase.  Matches
      // ``login.title``, ``common.save``, ``hostDetail.tabs.info``,
      // etc.  Does NOT match version strings (digits), URLs (slashes
      // / colons), or filenames (extensions).
      const unresolvedKey = /\b[a-z][a-zA-Z]*(\.[a-z][a-zA-Z]+){1,4}\b/;
      const match = bodyText.match(unresolvedKey);
      expect(
        match,
        `Found what looks like an unresolved i18n key on the login page (${code}): ${JSON.stringify(match?.[0])}.  Full body text:\n${bodyText.slice(0, 500)}`,
      ).toBeNull();
    });
  }
});
