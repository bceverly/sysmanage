import { test as setup, expect } from '@playwright/test';

const authFile = 'playwright/.auth/user.json';

/**
 * Authentication Setup
 * This runs before all other tests to establish an authenticated session.
 * The storage state is saved and reused by all subsequent tests.
 */
setup('authenticate', async ({ page }) => {
  // Navigate to login page
  await page.goto('/login');
  await page.waitForLoadState('domcontentloaded');

  // Wait for login form to be visible
  await expect(page.getByRole('heading', { name: /login/i })).toBeVisible();

  // Fill in credentials (using test credentials from environment or defaults)
  // These must match the credentials in scripts/e2e_test_user.py
  const username = process.env.TEST_USERNAME || 'e2e-test@sysmanage.org';
  const password = process.env.TEST_PASSWORD || 'E2ETestPassword123!';

  // Use the same selectors as the working Python Playwright tests
  // The userid field has id="userid" and password field has id="password"
  await page.fill('#userid', username);
  await page.fill('#password', password);
  await page.click('button[type="submit"]');

  // Wait for login success - verify by checking we're no longer on login page
  // Use polling approach like the Python tests for reliability
  const maxWaitSeconds = 15;
  let loginSucceeded = false;

  for (let attempt = 0; attempt < maxWaitSeconds; attempt++) {
    await page.waitForTimeout(1000);

    // Check if we're no longer on login page
    const currentUrl = page.url();
    if (!currentUrl.includes('/login')) {
      loginSucceeded = true;
      break;
    }

    // Also check if nav menu became visible (backup check)
    const navMenu = page.locator('#nav-menu');
    if (await navMenu.count() > 0) {
      const visibility = await navMenu.evaluate(el => getComputedStyle(el).visibility);
      if (visibility === 'visible') {
        loginSucceeded = true;
        break;
      }
    }
  }

  if (!loginSucceeded) {
    throw new Error(`Login failed after ${maxWaitSeconds}s. URL: ${page.url()}`);
  }

  // Save authentication state for reuse
  await page.context().storageState({ path: authFile });
});
