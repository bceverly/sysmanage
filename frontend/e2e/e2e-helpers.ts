import { Page } from '@playwright/test';

/**
 * Wait for the SPA to finish any auth-related redirects.
 * The React app may initially render on the target path, then redirect to
 * /login after checking the JWT.  We poll the URL until it stabilizes
 * (stays the same for 1 second) to avoid race conditions.
 */
async function waitForUrlToStabilize(page: Page, timeoutMs = 5000): Promise<string> {
  const start = Date.now();
  let lastUrl = page.url();
  let stableStart = Date.now();

  while (Date.now() - start < timeoutMs) {
    await page.waitForTimeout(250);
    const currentUrl = page.url();
    if (currentUrl !== lastUrl) {
      lastUrl = currentUrl;
      stableStart = Date.now();
    } else if (Date.now() - stableStart >= 1000) {
      // URL has been stable for 1 second
      return currentUrl;
    }
  }
  return page.url();
}

/**
 * Perform an inline login on the current page.
 * Assumes the page is on /login.  Returns true on success.
 */
async function doLogin(page: Page): Promise<boolean> {
  const username = process.env.TEST_USERNAME || 'e2e-test@sysmanage.org';
  const password = process.env.TEST_PASSWORD || 'E2ETestPassword123!';

  try {
    // Wait for the login form to be ready
    await page.waitForLoadState('domcontentloaded');
    const userField = page.locator('#userid');
    await userField.waitFor({ state: 'visible', timeout: 10000 });

    await page.fill('#userid', username);
    await page.fill('#password', password);
    await page.click('button[type="submit"]');

    // Wait for redirect away from /login
    await page.waitForURL(url => !url.toString().includes('/login'), { timeout: 30000 });
    return true;
  } catch {
    return false;
  }
}

/**
 * Navigate to a target page with automatic re-authentication.
 *
 * On CI (especially macOS with Firefox), the Playwright storageState
 * auth occasionally doesn't take effect, causing the SPA router to
 * redirect to /login.  When that happens this helper performs an
 * inline re-login so the test can proceed without skipping.
 *
 * Returns true if navigation succeeded (page is on target),
 * false if even re-authentication failed (caller should skip).
 */
export async function ensureAuthenticated(page: Page, targetPath: string): Promise<boolean> {
  // Retry navigation in case the dev server is momentarily unavailable
  // (e.g. NS_ERROR_CONNECTION_REFUSED on Firefox).
  for (let attempt = 0; attempt < 3; attempt++) {
    try {
      await page.goto(targetPath);
      break;
    } catch (e) {
      if (attempt === 2) throw e;
      await page.waitForTimeout(2000);
    }
  }

  // Wait for the SPA to finish loading and any auth redirect to complete.
  // networkidle alone isn't enough — the SPA may fire the redirect AFTER
  // network goes idle (React checks localStorage, then navigates).
  try {
    await page.waitForLoadState('networkidle', { timeout: 20000 });
  } catch {
    // networkidle may timeout on slow CI, continue
  }

  // Wait for URL to stabilize — catches the delayed SPA redirect to /login
  let stableUrl = await waitForUrlToStabilize(page);

  if (!stableUrl.includes('/login')) {
    return true; // Auth worked
  }

  // Auth state wasn't picked up — re-authenticate inline
  if (!(await doLogin(page))) {
    return false;
  }

  // After login the SPA redirects to its default route (usually "/").
  // Wait for that post-login redirect to finish before we navigate again,
  // otherwise our goto() gets interrupted by the in-flight SPA redirect.
  await waitForUrlToStabilize(page);

  // Navigate to the actual target after re-login.
  // Wrap in retry because on slow CI the SPA redirect can still be settling.
  for (let attempt = 0; attempt < 3; attempt++) {
    try {
      await page.goto(targetPath);
      break;
    } catch (e) {
      if (attempt === 2) throw e;
      await page.waitForTimeout(1000);
    }
  }
  try {
    await page.waitForLoadState('networkidle', { timeout: 20000 });
  } catch {
    // networkidle may timeout, continue
  }

  // Wait again for any redirect after re-navigation
  stableUrl = await waitForUrlToStabilize(page);
  return !stableUrl.includes('/login');
}
