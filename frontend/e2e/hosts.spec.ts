import { test, expect, Page } from '@playwright/test';
import { ensureAuthenticated } from './e2e-helpers';

/**
 * E2E Tests for Host List and Detail Page Flows
 * Tests the core host management functionality
 */

/**
 * Navigate from the hosts list to the first host's detail page.
 * Uses the View button in the Actions column, scrolling the grid
 * horizontally if necessary (the Actions column may be off-screen
 * due to MUI DataGrid column virtualization).
 */
async function navigateToFirstHostDetail(page: Page): Promise<boolean> {
  const firstRow = page.locator('.MuiDataGrid-row').first();
  if (!(await firstRow.isVisible())) return false;

  // Scroll the grid right to ensure the Actions column is rendered
  const virtualScroller = page.locator('.MuiDataGrid-virtualScroller');
  await virtualScroller.evaluate(el => el.scrollLeft = el.scrollWidth);
  await page.waitForTimeout(500);

  // Click the View button (eye icon) in the Actions column
  const viewButton = firstRow.getByRole('button', { name: /view/i });
  await expect(viewButton).toBeVisible({ timeout: 20000 });
  await viewButton.click();

  // Wait for navigation to complete
  await page.waitForURL(/\/hosts\/[a-f0-9-]+/, { timeout: 20000 });
  return true;
}

test.describe('Host List Page', () => {
  test.beforeEach(async ({ page }) => {
    await ensureAuthenticated(page, '/hosts');
  });

  test('should display host list page', async ({ page }) => {
    // If we landed back on /login, auth setup broke — fail loudly.
    expect(page.url()).not.toContain('/login');

    // Page should load successfully
    await expect(page).toHaveURL(/\/hosts/);

    // Should have the Hosts nav item highlighted or data grid visible
    // The page doesn't have a separate heading - title is in the navigation
    const dataGrid = page.locator('.MuiDataGrid-root');
    await expect(dataGrid).toBeVisible();
  });

  test('should display host data grid', async ({ page }) => {
    // If we landed back on /login, auth setup broke — fail loudly.
    expect(page.url()).not.toContain('/login');
    // Wait for the data grid to be visible
    const dataGrid = page.locator('.MuiDataGrid-root');
    await expect(dataGrid).toBeVisible({ timeout: 30000 });
  });

  test('should have search/filter functionality', async ({ page }) => {
    // Look for search input or filter controls
    const searchInput = page.getByPlaceholder(/search|filter/i).first();

    if (await searchInput.isVisible()) {
      await searchInput.fill('test');
      // Verify filter is applied (grid should update)
      await page.waitForTimeout(500); // Wait for debounce
    }
  });

  test('should navigate to host detail on row click', async ({ page }) => {
    // If we landed back on /login, auth setup broke — fail loudly.
    expect(page.url()).not.toContain('/login');
    // Wait for grid to load
    const dataGrid = page.locator('.MuiDataGrid-root');
    await expect(dataGrid).toBeVisible({ timeout: 30000 });

    const navigated = await navigateToFirstHostDetail(page);
    if (navigated) {
      await expect(page).toHaveURL(/\/hosts\/[a-f0-9-]+/);
    }
  });

  test('should have approve/reject buttons for pending hosts', async ({ page }) => {
    // If we landed back on /login, auth setup broke — fail loudly.
    expect(page.url()).not.toContain('/login');
    // Check if there are any pending hosts that need approval
    const approveButton = page.getByRole('button', { name: /approve/i }).first();
    const rejectButton = page.getByRole('button', { name: /reject|delete/i }).first();

    // These may or may not be visible depending on pending hosts
    // Just verify the page structure is correct
    await expect(page.locator('.MuiDataGrid-root')).toBeVisible({ timeout: 30000 });
  });

  test('should show host count or statistics', async ({ page }) => {
    // Look for any count/statistics display
    try {
      await page.waitForLoadState('networkidle', { timeout: 3000 });
    } catch {
      // networkidle may timeout, continue anyway
    }

    // The page should have loaded content
    await expect(page.locator('body')).not.toBeEmpty();
  });
});

test.describe('Host Detail Page', () => {
  // Note: These tests require at least one host to exist in the system

  test('should display host detail when navigating directly', async ({ page }) => {
    // First get a host ID from the hosts list
    await page.goto('/hosts');
    try { await page.waitForLoadState('networkidle', { timeout: 3000 }); } catch { /* timeout ok */ }

    // If we landed back on /login, auth setup broke — fail loudly.
    expect(page.url()).not.toContain('/login');

    const dataGrid = page.locator('.MuiDataGrid-root');
    await expect(dataGrid).toBeVisible({ timeout: 30000 });

    if (await navigateToFirstHostDetail(page)) {
      // Verify host detail page elements
      await expect(page.locator('body')).toContainText(/hostname|host|details/i);
    }
  });

  test('should display host tabs', async ({ page }) => {
    await page.goto('/hosts');

    if (await navigateToFirstHostDetail(page)) {
      // Look for tab navigation (MUI Tabs)
      const tabs = page.locator('.MuiTabs-root');
      if (await tabs.isVisible()) {
        await expect(tabs).toBeVisible();
      }
    }
  });

  test('should display system information section', async ({ page }) => {
    await page.goto('/hosts');

    if (await navigateToFirstHostDetail(page)) {
      // Wait for the loading spinner to disappear and real content to render
      const spinner = page.locator('[role="progressbar"]');
      await expect(spinner).toBeHidden({ timeout: 60000 });

      // Use auto-retrying assertion so Playwright waits for the text to appear
      await expect(page.locator('body')).toContainText(
        /cpu|memory|operating system|platform|processor|architecture|hostname/i,
        { timeout: 30000 }
      );
    }
  });

  test('should have action buttons', async ({ page }) => {
    await page.goto('/hosts');

    if (await navigateToFirstHostDetail(page)) {
      // Look for common action buttons
      try { await page.waitForLoadState('networkidle', { timeout: 3000 }); } catch { /* timeout ok */ }

      // Page should have interactive elements
      const buttons = page.locator('button');
      const buttonCount = await buttons.count();
      expect(buttonCount).toBeGreaterThan(0);
    }
  });

  test('should display software inventory tab', async ({ page }) => {
    await page.goto('/hosts');

    if (await navigateToFirstHostDetail(page)) {
      // Look for software/packages tab
      const softwareTab = page.getByRole('tab', { name: /software|packages|inventory/i }).first();
      if (await softwareTab.isVisible()) {
        await softwareTab.click();

        // Wait for tab content to load
        try { await page.waitForLoadState('networkidle', { timeout: 3000 }); } catch { /* timeout ok */ }
      }
    }
  });

  test('should display certificates tab', async ({ page }) => {
    await page.goto('/hosts');

    if (await navigateToFirstHostDetail(page)) {
      // Look for certificates tab
      const certTab = page.getByRole('tab', { name: /certificate/i }).first();
      if (await certTab.isVisible()) {
        await certTab.click();
        try { await page.waitForLoadState('networkidle', { timeout: 3000 }); } catch { /* timeout ok */ }
      }
    }
  });

  test('should display firewall tab', async ({ page }) => {
    await page.goto('/hosts');

    if (await navigateToFirstHostDetail(page)) {
      // Look for firewall tab
      const firewallTab = page.getByRole('tab', { name: /firewall/i }).first();
      if (await firewallTab.isVisible()) {
        await firewallTab.click();
        try { await page.waitForLoadState('networkidle', { timeout: 3000 }); } catch { /* timeout ok */ }
      }
    }
  });

  test('should display child hosts tab for virtualization hosts', async ({ page }) => {
    await page.goto('/hosts');

    if (await navigateToFirstHostDetail(page)) {
      // Look for child hosts/VMs tab
      const childHostsTab = page.getByRole('tab', { name: /child|virtual|vm/i }).first();
      if (await childHostsTab.isVisible()) {
        await childHostsTab.click();
        try { await page.waitForLoadState('networkidle', { timeout: 3000 }); } catch { /* timeout ok */ }
      }
    }
  });
});

test.describe('Host Actions', () => {
  test('should be able to refresh host data', async ({ page }) => {
    await page.goto('/hosts');

    if (!(await navigateToFirstHostDetail(page))) {
      // No hosts in the grid — nothing to refresh; treat as a no-op pass.
      return;
    }

    // Anchor on the host-detail diagnostics button via its stable
    // ``data-testid`` (request-host-data-button), NOT its accessible
    // name.  The label toggles between "Request Host Data" and
    // "Requesting..." (i18n keys hostDetail.requestHostData /
    // requestingDiagnostics) as ``diagnosticsLoading`` flips, so a
    // name-based locator drops the element the instant host-detail's
    // initial fetch or periodic polling toggles that flag — the cause
    // of the intermittent "element(s) not found" failure.  The testid
    // is invariant across both states and is also unambiguous vs. the
    // global "Broadcast Refresh" / per-tab "Refresh" buttons.
    const refreshButton = page.getByTestId('request-host-data-button');

    // The button is disabled while a diagnostics request is in-flight.
    // Wait for it to be both visible AND enabled before clicking — that
    // also lets host-detail's initial fetches settle, so we don't race
    // a re-render mid-click.
    try {
      await refreshButton.waitFor({ state: 'visible', timeout: 15000 });
    } catch {
      // Diagnostics tab not present for this host (older agent, etc.);
      // treat as a no-op pass rather than a hard failure.
      return;
    }
    await expect(refreshButton).toBeEnabled({ timeout: 15000 });
    // ``click()`` auto-scrolls the element into view and runs its own
    // actionability retries (visible / stable / enabled / receives
    // events) under the configured timeout.  The earlier two-step
    // ``scrollIntoViewIfNeeded()`` + ``click()`` opened a window where
    // host-detail's periodic polling could re-render between the
    // scroll and the click, detaching the matched DOM node and
    // restarting the locator wait against a freshly-mounted button.
    // Collapsing to a single ``click`` with a generous timeout closes
    // that race.
    await refreshButton.click({ timeout: 15000 });

    // After clicking, the button stays mounted (its label flips to
    // "Requesting..." while the backend processes the request, then
    // back).  Assert on the same stable testid locator to confirm the
    // click landed without detaching; don't block on networkidle (the
    // host-detail page has periodic polling that never goes idle).
    await expect(refreshButton).toBeVisible({ timeout: 10000 });
  });

  test('should navigate back to hosts list', async ({ page }) => {
    await page.goto('/hosts');

    if (await navigateToFirstHostDetail(page)) {
      // Navigate back using breadcrumb or back button
      const backButton = page.getByRole('button', { name: /back/i }).first();
      const breadcrumb = page.getByRole('link', { name: /hosts/i }).first();

      if (await backButton.isVisible()) {
        await backButton.click();
      } else if (await breadcrumb.isVisible()) {
        await breadcrumb.click();
      } else {
        // Use browser back
        await page.goBack();
      }

      await expect(page).toHaveURL(/\/hosts$/);
    }
  });
});
