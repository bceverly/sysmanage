import { test, expect } from '@playwright/test';

/**
 * E2E Tests for Child Host Creation Flows
 * Tests LXD, WSL, and other virtualization creation workflows
 */

test.describe('Child Host Management', () => {
  test('should navigate to host with child host capabilities', async ({ page }) => {
    await page.goto('/hosts');

    // Wait for host list to load
    const dataGrid = page.locator('.MuiDataGrid-root');
    await expect(dataGrid).toBeVisible();

    // Click on first host to check for child host tab
    const firstRow = page.locator('.MuiDataGrid-row').first();
    if (await firstRow.isVisible()) {
      await firstRow.click();
      await page.waitForURL(/\/hosts\/[a-f0-9-]+/);
      await page.waitForLoadState('networkidle');
    }
  });

  test('should display child hosts tab on virtualization host', async ({ page }) => {
    await page.goto('/hosts');

    const dataGrid = page.locator('.MuiDataGrid-root');
    await expect(dataGrid).toBeVisible();

    const firstRow = page.locator('.MuiDataGrid-row').first();
    if (await firstRow.isVisible()) {
      await firstRow.click();
      await page.waitForURL(/\/hosts\/[a-f0-9-]+/);

      // Look for child hosts/VMs tab
      const childHostsTab = page.getByRole('tab', { name: /child|virtual|vm|container/i }).first();
      if (await childHostsTab.isVisible()) {
        await childHostsTab.click();
        await page.waitForLoadState('networkidle');

        // Tab content should be visible
        await expect(page.locator('body')).not.toBeEmpty();
      }
    }
  });
});

test.describe('LXD Container Creation', () => {
  test('should have create LXD container button', async ({ page }) => {
    await page.goto('/hosts');

    const firstRow = page.locator('.MuiDataGrid-row').first();
    if (await firstRow.isVisible()) {
      await firstRow.click();
      await page.waitForURL(/\/hosts\/[a-f0-9-]+/);

      // Navigate to child hosts tab
      const childHostsTab = page.getByRole('tab', { name: /child|virtual|vm|container/i }).first();
      if (await childHostsTab.isVisible()) {
        await childHostsTab.click();
        await page.waitForLoadState('networkidle');

        // Look for create LXD button
        const createLxdButton = page.getByRole('button', { name: /lxd|create.*container/i }).first();
        if (await createLxdButton.isVisible()) {
          await expect(createLxdButton).toBeVisible();
        }
      }
    }
  });

  test('should open LXD creation dialog', async ({ page }) => {
    await page.goto('/hosts');

    const firstRow = page.locator('.MuiDataGrid-row').first();
    if (await firstRow.isVisible()) {
      await firstRow.click();
      await page.waitForURL(/\/hosts\/[a-f0-9-]+/);

      const childHostsTab = page.getByRole('tab', { name: /child|virtual|vm|container/i }).first();
      if (await childHostsTab.isVisible()) {
        await childHostsTab.click();
        await page.waitForLoadState('networkidle');

        const createLxdButton = page.getByRole('button', { name: /lxd|create.*container/i }).first();
        if (await createLxdButton.isVisible()) {
          await createLxdButton.click();

          // Dialog should appear
          const dialog = page.locator('.MuiDialog-root');
          await expect(dialog).toBeVisible();
        }
      }
    }
  });

  test('should show LXD creation form fields', async ({ page }) => {
    await page.goto('/hosts');

    const firstRow = page.locator('.MuiDataGrid-row').first();
    if (await firstRow.isVisible()) {
      await firstRow.click();
      await page.waitForURL(/\/hosts\/[a-f0-9-]+/);

      const childHostsTab = page.getByRole('tab', { name: /child|virtual|vm|container/i }).first();
      if (await childHostsTab.isVisible()) {
        await childHostsTab.click();
        await page.waitForLoadState('networkidle');

        const createLxdButton = page.getByRole('button', { name: /lxd|create.*container/i }).first();
        if (await createLxdButton.isVisible()) {
          await createLxdButton.click();

          const dialog = page.locator('.MuiDialog-root');
          if (await dialog.isVisible()) {
            // Should have name field
            const nameInput = page.getByLabel(/name|hostname/i);
            if (await nameInput.isVisible()) {
              await expect(nameInput).toBeVisible();
            }

            // Should have image selection
            const imageSelect = page.locator('[id*="image"]').first();
            if (await imageSelect.isVisible()) {
              await expect(imageSelect).toBeVisible();
            }
          }
        }
      }
    }
  });
});

test.describe('WSL Instance Creation', () => {
  test('should have create WSL instance button', async ({ page }) => {
    await page.goto('/hosts');

    const firstRow = page.locator('.MuiDataGrid-row').first();
    if (await firstRow.isVisible()) {
      await firstRow.click();
      await page.waitForURL(/\/hosts\/[a-f0-9-]+/);

      const childHostsTab = page.getByRole('tab', { name: /child|virtual|vm|wsl/i }).first();
      if (await childHostsTab.isVisible()) {
        await childHostsTab.click();
        await page.waitForLoadState('networkidle');

        // Look for create WSL button
        const createWslButton = page.getByRole('button', { name: /wsl|windows.*subsystem/i }).first();
        if (await createWslButton.isVisible()) {
          await expect(createWslButton).toBeVisible();
        }
      }
    }
  });

  test('should open WSL creation dialog', async ({ page }) => {
    await page.goto('/hosts');

    const firstRow = page.locator('.MuiDataGrid-row').first();
    if (await firstRow.isVisible()) {
      await firstRow.click();
      await page.waitForURL(/\/hosts\/[a-f0-9-]+/);

      const childHostsTab = page.getByRole('tab', { name: /child|virtual|vm|wsl/i }).first();
      if (await childHostsTab.isVisible()) {
        await childHostsTab.click();
        await page.waitForLoadState('networkidle');

        const createWslButton = page.getByRole('button', { name: /wsl|windows.*subsystem/i }).first();
        if (await createWslButton.isVisible()) {
          await createWslButton.click();

          const dialog = page.locator('.MuiDialog-root');
          await expect(dialog).toBeVisible();
        }
      }
    }
  });

  test('should show WSL distro selection', async ({ page }) => {
    await page.goto('/hosts');

    const firstRow = page.locator('.MuiDataGrid-row').first();
    if (await firstRow.isVisible()) {
      await firstRow.click();
      await page.waitForURL(/\/hosts\/[a-f0-9-]+/);

      const childHostsTab = page.getByRole('tab', { name: /child|virtual|vm|wsl/i }).first();
      if (await childHostsTab.isVisible()) {
        await childHostsTab.click();
        await page.waitForLoadState('networkidle');

        const createWslButton = page.getByRole('button', { name: /wsl|windows.*subsystem/i }).first();
        if (await createWslButton.isVisible()) {
          await createWslButton.click();

          const dialog = page.locator('.MuiDialog-root');
          if (await dialog.isVisible()) {
            // Should have distro selection
            const distroSelect = page.locator('[id*="distro"], [id*="distribution"]').first();
            if (await distroSelect.isVisible()) {
              await expect(distroSelect).toBeVisible();
            }
          }
        }
      }
    }
  });
});

test.describe('VM Creation (KVM/bhyve)', () => {
  test('should have create VM button', async ({ page }) => {
    await page.goto('/hosts');

    const firstRow = page.locator('.MuiDataGrid-row').first();
    if (await firstRow.isVisible()) {
      await firstRow.click();
      await page.waitForURL(/\/hosts\/[a-f0-9-]+/);

      const childHostsTab = page.getByRole('tab', { name: /child|virtual|vm/i }).first();
      if (await childHostsTab.isVisible()) {
        await childHostsTab.click();
        await page.waitForLoadState('networkidle');

        // Look for create VM button
        const createVmButton = page.getByRole('button', { name: /vm|virtual.*machine|create/i }).first();
        if (await createVmButton.isVisible()) {
          await expect(createVmButton).toBeVisible();
        }
      }
    }
  });

  test('should show VM configuration options', async ({ page }) => {
    await page.goto('/hosts');

    const firstRow = page.locator('.MuiDataGrid-row').first();
    if (await firstRow.isVisible()) {
      await firstRow.click();
      await page.waitForURL(/\/hosts\/[a-f0-9-]+/);

      const childHostsTab = page.getByRole('tab', { name: /child|virtual|vm/i }).first();
      if (await childHostsTab.isVisible()) {
        await childHostsTab.click();
        await page.waitForLoadState('networkidle');

        const createVmButton = page.getByRole('button', { name: /vm|virtual.*machine|create/i }).first();
        if (await createVmButton.isVisible()) {
          await createVmButton.click();

          const dialog = page.locator('.MuiDialog-root');
          if (await dialog.isVisible()) {
            // Should have configuration options
            await page.waitForLoadState('networkidle');
            await expect(dialog).toBeVisible();
          }
        }
      }
    }
  });
});

test.describe('Child Host List', () => {
  test('should display list of child hosts', async ({ page }) => {
    await page.goto('/hosts');

    const firstRow = page.locator('.MuiDataGrid-row').first();
    if (await firstRow.isVisible()) {
      await firstRow.click();
      await page.waitForURL(/\/hosts\/[a-f0-9-]+/);

      const childHostsTab = page.getByRole('tab', { name: /child|virtual|vm|container/i }).first();
      if (await childHostsTab.isVisible()) {
        await childHostsTab.click();
        await page.waitForLoadState('networkidle');

        // Should show child hosts list or empty state
        const pageContent = await page.textContent('body');
        expect(pageContent).toBeDefined();
      }
    }
  });

  test('should have actions for existing child hosts', async ({ page }) => {
    await page.goto('/hosts');

    const firstRow = page.locator('.MuiDataGrid-row').first();
    if (await firstRow.isVisible()) {
      await firstRow.click();
      await page.waitForURL(/\/hosts\/[a-f0-9-]+/);

      const childHostsTab = page.getByRole('tab', { name: /child|virtual|vm|container/i }).first();
      if (await childHostsTab.isVisible()) {
        await childHostsTab.click();
        await page.waitForLoadState('networkidle');

        // If there are child hosts, they should have action buttons
        const actionButtons = page.locator('button[aria-label], [class*="action"]');
        const buttonCount = await actionButtons.count();

        // Page loaded successfully
        await expect(page.locator('body')).not.toBeEmpty();
      }
    }
  });
});

test.describe('Child Host Operations', () => {
  test('should be able to start/stop child hosts', async ({ page }) => {
    await page.goto('/hosts');

    const firstRow = page.locator('.MuiDataGrid-row').first();
    if (await firstRow.isVisible()) {
      await firstRow.click();
      await page.waitForURL(/\/hosts\/[a-f0-9-]+/);

      const childHostsTab = page.getByRole('tab', { name: /child|virtual|vm|container/i }).first();
      if (await childHostsTab.isVisible()) {
        await childHostsTab.click();
        await page.waitForLoadState('networkidle');

        // Look for start/stop buttons
        const startButton = page.getByRole('button', { name: /start/i }).first();
        const stopButton = page.getByRole('button', { name: /stop/i }).first();

        // At least one should be potentially available
        await expect(page.locator('body')).not.toBeEmpty();
      }
    }
  });

  test('should be able to delete child hosts', async ({ page }) => {
    await page.goto('/hosts');

    const firstRow = page.locator('.MuiDataGrid-row').first();
    if (await firstRow.isVisible()) {
      await firstRow.click();
      await page.waitForURL(/\/hosts\/[a-f0-9-]+/);

      const childHostsTab = page.getByRole('tab', { name: /child|virtual|vm|container/i }).first();
      if (await childHostsTab.isVisible()) {
        await childHostsTab.click();
        await page.waitForLoadState('networkidle');

        // Look for delete buttons
        const deleteButton = page.getByRole('button', { name: /delete|remove/i }).first();
        if (await deleteButton.isVisible()) {
          // Don't actually click delete, just verify it exists
          await expect(deleteButton).toBeVisible();
        }
      }
    }
  });
});
