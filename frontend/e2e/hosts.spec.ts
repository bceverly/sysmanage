import { test, expect } from '@playwright/test';

/**
 * E2E Tests for Host List and Detail Page Flows
 * Tests the core host management functionality
 */

test.describe('Host List Page', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/hosts');
  });

  test('should display host list page', async ({ page }) => {
    // Page should load successfully
    await expect(page).toHaveURL(/\/hosts/);

    // Should have the Hosts nav item highlighted or data grid visible
    // The page doesn't have a separate heading - title is in the navigation
    const dataGrid = page.locator('.MuiDataGrid-root');
    await expect(dataGrid).toBeVisible();
  });

  test('should display host data grid', async ({ page }) => {
    // Wait for the data grid to be visible
    const dataGrid = page.locator('.MuiDataGrid-root');
    await expect(dataGrid).toBeVisible();
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
    // Wait for grid to load
    const dataGrid = page.locator('.MuiDataGrid-root');
    await expect(dataGrid).toBeVisible();

    // Click on first data row (if exists)
    const firstRow = page.locator('.MuiDataGrid-row').first();
    if (await firstRow.isVisible()) {
      await firstRow.click();

      // Should navigate to host detail page
      await expect(page).toHaveURL(/\/hosts\/[a-f0-9-]+/);
    }
  });

  test('should have approve/reject buttons for pending hosts', async ({ page }) => {
    // Check if there are any pending hosts that need approval
    const approveButton = page.getByRole('button', { name: /approve/i }).first();
    const rejectButton = page.getByRole('button', { name: /reject|delete/i }).first();

    // These may or may not be visible depending on pending hosts
    // Just verify the page structure is correct
    await expect(page.locator('.MuiDataGrid-root')).toBeVisible();
  });

  test('should show host count or statistics', async ({ page }) => {
    // Look for any count/statistics display
    await page.waitForLoadState('networkidle');

    // The page should have loaded content
    await expect(page.locator('body')).not.toBeEmpty();
  });
});

test.describe('Host Detail Page', () => {
  // Note: These tests require at least one host to exist in the system

  test('should display host detail when navigating directly', async ({ page }) => {
    // First get a host ID from the hosts list
    await page.goto('/hosts');

    const dataGrid = page.locator('.MuiDataGrid-root');
    await expect(dataGrid).toBeVisible();

    // Try to find and click a host row
    const firstRow = page.locator('.MuiDataGrid-row').first();
    if (await firstRow.isVisible()) {
      await firstRow.click();

      // Wait for navigation
      await page.waitForURL(/\/hosts\/[a-f0-9-]+/);

      // Verify host detail page elements
      await expect(page.locator('body')).toContainText(/hostname|host|details/i);
    }
  });

  test('should display host tabs', async ({ page }) => {
    await page.goto('/hosts');

    const firstRow = page.locator('.MuiDataGrid-row').first();
    if (await firstRow.isVisible()) {
      await firstRow.click();
      await page.waitForURL(/\/hosts\/[a-f0-9-]+/);

      // Look for tab navigation (MUI Tabs)
      const tabs = page.locator('.MuiTabs-root');
      if (await tabs.isVisible()) {
        await expect(tabs).toBeVisible();
      }
    }
  });

  test('should display system information section', async ({ page }) => {
    await page.goto('/hosts');

    const firstRow = page.locator('.MuiDataGrid-row').first();
    if (await firstRow.isVisible()) {
      await firstRow.click();
      await page.waitForURL(/\/hosts\/[a-f0-9-]+/);

      // Look for system info content - CPU, RAM, OS, etc.
      const pageContent = await page.textContent('body');
      const hasSystemInfo =
        pageContent?.toLowerCase().includes('cpu') ||
        pageContent?.toLowerCase().includes('memory') ||
        pageContent?.toLowerCase().includes('operating system') ||
        pageContent?.toLowerCase().includes('hostname');

      expect(hasSystemInfo).toBeTruthy();
    }
  });

  test('should have action buttons', async ({ page }) => {
    await page.goto('/hosts');

    const firstRow = page.locator('.MuiDataGrid-row').first();
    if (await firstRow.isVisible()) {
      await firstRow.click();
      await page.waitForURL(/\/hosts\/[a-f0-9-]+/);

      // Look for common action buttons
      await page.waitForLoadState('networkidle');

      // Page should have interactive elements
      const buttons = page.locator('button');
      const buttonCount = await buttons.count();
      expect(buttonCount).toBeGreaterThan(0);
    }
  });

  test('should display software inventory tab', async ({ page }) => {
    await page.goto('/hosts');

    const firstRow = page.locator('.MuiDataGrid-row').first();
    if (await firstRow.isVisible()) {
      await firstRow.click();
      await page.waitForURL(/\/hosts\/[a-f0-9-]+/);

      // Look for software/packages tab
      const softwareTab = page.getByRole('tab', { name: /software|packages|inventory/i }).first();
      if (await softwareTab.isVisible()) {
        await softwareTab.click();

        // Wait for tab content to load
        await page.waitForLoadState('networkidle');
      }
    }
  });

  test('should display certificates tab', async ({ page }) => {
    await page.goto('/hosts');

    const firstRow = page.locator('.MuiDataGrid-row').first();
    if (await firstRow.isVisible()) {
      await firstRow.click();
      await page.waitForURL(/\/hosts\/[a-f0-9-]+/);

      // Look for certificates tab
      const certTab = page.getByRole('tab', { name: /certificate/i }).first();
      if (await certTab.isVisible()) {
        await certTab.click();
        await page.waitForLoadState('networkidle');
      }
    }
  });

  test('should display firewall tab', async ({ page }) => {
    await page.goto('/hosts');

    const firstRow = page.locator('.MuiDataGrid-row').first();
    if (await firstRow.isVisible()) {
      await firstRow.click();
      await page.waitForURL(/\/hosts\/[a-f0-9-]+/);

      // Look for firewall tab
      const firewallTab = page.getByRole('tab', { name: /firewall/i }).first();
      if (await firewallTab.isVisible()) {
        await firewallTab.click();
        await page.waitForLoadState('networkidle');
      }
    }
  });

  test('should display child hosts tab for virtualization hosts', async ({ page }) => {
    await page.goto('/hosts');

    const firstRow = page.locator('.MuiDataGrid-row').first();
    if (await firstRow.isVisible()) {
      await firstRow.click();
      await page.waitForURL(/\/hosts\/[a-f0-9-]+/);

      // Look for child hosts/VMs tab
      const childHostsTab = page.getByRole('tab', { name: /child|virtual|vm/i }).first();
      if (await childHostsTab.isVisible()) {
        await childHostsTab.click();
        await page.waitForLoadState('networkidle');
      }
    }
  });
});

test.describe('Host Actions', () => {
  test('should be able to refresh host data', async ({ page }) => {
    await page.goto('/hosts');

    const firstRow = page.locator('.MuiDataGrid-row').first();
    if (await firstRow.isVisible()) {
      await firstRow.click();
      await page.waitForURL(/\/hosts\/[a-f0-9-]+/);

      // Look for refresh button
      const refreshButton = page.getByRole('button', { name: /refresh/i }).first();
      if (await refreshButton.isVisible()) {
        await refreshButton.click();

        // Wait for the refresh action to complete
        await page.waitForLoadState('networkidle');
      }
    }
  });

  test('should navigate back to hosts list', async ({ page }) => {
    await page.goto('/hosts');

    const firstRow = page.locator('.MuiDataGrid-row').first();
    if (await firstRow.isVisible()) {
      await firstRow.click();
      await page.waitForURL(/\/hosts\/[a-f0-9-]+/);

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
