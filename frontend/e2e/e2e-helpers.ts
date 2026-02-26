import { Page } from '@playwright/test';

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

  // Wait for client-side router to settle — the SPA may redirect to
  // /login after the initial DOM load if the auth token is missing/expired.
  try {
    await page.waitForLoadState('networkidle', { timeout: 20000 });
  } catch {
    // networkidle may timeout on slow CI, continue
  }

  // Give the client-side auth redirect an extra moment to kick in.
  // Without this, page.url() can still show the target path while
  // the React router redirect is pending.
  if (!page.url().includes('/login')) {
    await page.waitForTimeout(500);
  }

  if (!page.url().includes('/login')) {
    return true; // Auth worked
  }

  // Auth state wasn't picked up — re-authenticate inline
  const username = process.env.TEST_USERNAME || 'e2e-test@sysmanage.org';
  const password = process.env.TEST_PASSWORD || 'E2ETestPassword123!';

  try {
    await page.waitForLoadState('domcontentloaded');
    await page.fill('#userid', username);
    await page.fill('#password', password);
    await page.click('button[type="submit"]');

    // Wait for login to complete (redirect away from /login)
    await page.waitForURL(url => !url.toString().includes('/login'), { timeout: 30000 });
  } catch {
    return false; // Login failed
  }

  // Now navigate to the actual target
  await page.goto(targetPath);
  try {
    await page.waitForLoadState('networkidle', { timeout: 20000 });
  } catch {
    // networkidle may timeout, continue
  }

  return !page.url().includes('/login');
}
