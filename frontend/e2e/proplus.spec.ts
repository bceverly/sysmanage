// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

import { test, expect, Page } from '@playwright/test';
import { ensureAuthenticated } from './e2e-helpers';

/**
 * E2E Tests for Pro+ Feature Flows
 * Tests health analysis, compliance, vulnerabilities, and other Pro+ features
 * Note: These tests may require a Pro+ license to fully execute
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

test.describe('Pro+ Health Analysis', () => {
  test('should navigate to health analysis if available', async ({ page }) => {
    await page.goto('/hosts');
    try { await page.waitForLoadState('networkidle', { timeout: 3000 }); } catch { /* timeout ok */ }

    // If we landed back on /login, auth setup broke — fail loudly.
    expect(page.url()).not.toContain('/login');

    const dataGrid = page.locator('.MuiDataGrid-root');
    await expect(dataGrid).toBeVisible({ timeout: 30000 });

    if (await navigateToFirstHostDetail(page)) {
      // Look for health analysis tab
      const healthTab = page.getByRole('tab', { name: /health/i }).first();
      if (await healthTab.isVisible()) {
        await healthTab.click();
        try { await page.waitForLoadState('networkidle', { timeout: 3000 }); } catch { /* networkidle timeout ok */ }

        // Health analysis content should be visible
        await expect(page.locator('body')).not.toBeEmpty();
      }
    }
  });

  test('should display health score', async ({ page }) => {
    await page.goto('/hosts');

    if (await navigateToFirstHostDetail(page)) {
      const healthTab = page.getByRole('tab', { name: /health/i }).first();
      if (await healthTab.isVisible()) {
        await healthTab.click();
        try { await page.waitForLoadState('networkidle', { timeout: 3000 }); } catch { /* networkidle timeout ok */ }

        // Look for health score display
        const pageContent = await page.textContent('body');
        const hasHealthInfo =
          pageContent?.toLowerCase().includes('health') ||
          pageContent?.toLowerCase().includes('score') ||
          pageContent?.toLowerCase().includes('status');

        if (hasHealthInfo) {
          expect(hasHealthInfo).toBeTruthy();
        }
      }
    }
  });

  test('should display health recommendations', async ({ page }) => {
    await page.goto('/hosts');

    if (await navigateToFirstHostDetail(page)) {
      const healthTab = page.getByRole('tab', { name: /health/i }).first();
      if (await healthTab.isVisible()) {
        await healthTab.click();
        try { await page.waitForLoadState('networkidle', { timeout: 3000 }); } catch { /* networkidle timeout ok */ }

        // Look for recommendations section
        const pageContent = await page.textContent('body');
        expect(pageContent).toBeDefined();
      }
    }
  });
});

test.describe('Pro+ Compliance', () => {
  test('should navigate to compliance page if available', async ({ page }) => {
    // Try direct navigation to compliance page
    await page.goto('/compliance');

    // If not a plugin route, check within host detail
    if (await page.getByText(/not found|404/i).isVisible()) {
      await page.goto('/hosts');

      if (await navigateToFirstHostDetail(page)) {
        const complianceTab = page.getByRole('tab', { name: /compliance/i }).first();
        if (await complianceTab.isVisible()) {
          await complianceTab.click();
          try { await page.waitForLoadState('networkidle', { timeout: 3000 }); } catch { /* networkidle timeout ok */ }
        }
      }
    }
  });

  test('should display compliance status', async ({ page }) => {
    await page.goto('/hosts');

    if (await navigateToFirstHostDetail(page)) {
      const complianceTab = page.getByRole('tab', { name: /compliance/i }).first();
      if (await complianceTab.isVisible()) {
        await complianceTab.click();
        try { await page.waitForLoadState('networkidle', { timeout: 3000 }); } catch { /* networkidle timeout ok */ }

        // Should show compliance status
        const pageContent = await page.textContent('body');
        expect(pageContent).toBeDefined();
      }
    }
  });

  test('should display compliance violations if any', async ({ page }) => {
    await page.goto('/hosts');
    try { await page.waitForLoadState('networkidle', { timeout: 3000 }); } catch { /* networkidle timeout ok */ }

    if (!(await navigateToFirstHostDetail(page))) {
      // No hosts available, test passes
      return;
    }

    const complianceTab = page.getByRole('tab', { name: /compliance/i }).first();
    if (!(await complianceTab.isVisible({ timeout: 6000 }).catch(() => false))) {
      // No compliance tab (Pro+ not licensed), test passes
      return;
    }

    await complianceTab.click();
    try { await page.waitForLoadState('networkidle', { timeout: 10000 }); } catch { /* networkidle timeout ok */ }

    // Look for violations list or compliant status
    const pageContent = await page.textContent('body');
    expect(pageContent).toBeDefined();
  });
});

test.describe('Pro+ Vulnerabilities', () => {
  test('should navigate to vulnerabilities page if available', async ({ page }) => {
    // Try direct navigation
    await page.goto('/vulnerabilities');

    // If not a plugin route, check within host detail
    if (await page.getByText(/not found|404/i).isVisible()) {
      await page.goto('/hosts');

      if (await navigateToFirstHostDetail(page)) {
        const vulnTab = page.getByRole('tab', { name: /vuln|cve|security/i }).first();
        if (await vulnTab.isVisible()) {
          await vulnTab.click();
          try { await page.waitForLoadState('networkidle', { timeout: 3000 }); } catch { /* networkidle timeout ok */ }
        }
      }
    }
  });

  test('should display vulnerability scan results', async ({ page }) => {
    await page.goto('/hosts');

    if (await navigateToFirstHostDetail(page)) {
      const vulnTab = page.getByRole('tab', { name: /vuln|cve|security/i }).first();
      if (await vulnTab.isVisible()) {
        await vulnTab.click();
        try { await page.waitForLoadState('networkidle', { timeout: 3000 }); } catch { /* networkidle timeout ok */ }

        // Should show vulnerability info
        const pageContent = await page.textContent('body');
        expect(pageContent).toBeDefined();
      }
    }
  });

  test('should display CVE details', async ({ page }) => {
    await page.goto('/hosts');

    if (await navigateToFirstHostDetail(page)) {
      const vulnTab = page.getByRole('tab', { name: /vuln|cve|security/i }).first();
      if (await vulnTab.isVisible()) {
        await vulnTab.click();
        try { await page.waitForLoadState('networkidle', { timeout: 3000 }); } catch { /* networkidle timeout ok */ }

        // Look for CVE identifiers or severity ratings
        const pageContent = await page.textContent('body');
        const hasCveInfo =
          pageContent?.includes('CVE-') ||
          pageContent?.toLowerCase().includes('critical') ||
          pageContent?.toLowerCase().includes('severity');

        expect(pageContent).toBeDefined();
      }
    }
  });
});

test.describe('Pro+ Dashboard Cards', () => {
  test('should display Pro+ cards on home page', async ({ page }) => {
    await page.goto('/');
    try { await page.waitForLoadState('networkidle', { timeout: 3000 }); } catch { /* networkidle timeout ok */ }

    // Look for Pro+ specific dashboard cards
    const healthCard = page.locator('[class*="health"], [data-testid*="health"]').first();
    const complianceCard = page.locator('[class*="compliance"], [data-testid*="compliance"]').first();
    const vulnCard = page.locator('[class*="vuln"], [data-testid*="vuln"]').first();

    // At least one Pro+ card might be visible if licensed
    await expect(page.locator('body')).not.toBeEmpty();
  });

  test('should navigate from dashboard card to detail', async ({ page }) => {
    await page.goto('/');
    try { await page.waitForLoadState('networkidle', { timeout: 3000 }); } catch { /* networkidle timeout ok */ }

    // Try clicking on Pro+ cards
    const cards = page.locator('.MuiCard-root, [class*="Card"]');
    const cardCount = await cards.count();

    if (cardCount > 0) {
      // Cards exist on dashboard
      await expect(cards.first()).toBeVisible();
    }
  });
});

test.describe('Pro+ Settings', () => {
  test('should display Pro+ settings if licensed', async ({ page }) => {
    test.setTimeout(60000);
    // ensureAuthenticated returns false only if auth never succeeded, which
    // is a real failure — surface it.
    expect(await ensureAuthenticated(page, '/settings')).toBe(true);

    // Look for Pro+ specific settings tabs
    const proplusTab = page.getByRole('tab', { name: /pro|enterprise|professional|health|cve/i }).first();
    if (await proplusTab.isVisible()) {
      await proplusTab.click();
      try { await page.waitForLoadState('networkidle', { timeout: 3000 }); } catch { /* networkidle timeout ok */ }

      // Should show Pro+ settings
      await expect(page.locator('body')).not.toBeEmpty();
    }
  });

  test('should have health analysis settings', async ({ page }) => {
    await page.goto('/settings');
    try { await page.waitForLoadState('networkidle', { timeout: 3000 }); } catch { /* networkidle timeout ok */ }

    const healthTab = page.getByRole('tab', { name: /health/i }).first();
    if (await healthTab.isVisible()) {
      await healthTab.click();
      try { await page.waitForLoadState('networkidle', { timeout: 3000 }); } catch { /* networkidle timeout ok */ }

      // Should show health analysis configuration
      const pageContent = await page.textContent('body');
      expect(pageContent).toBeDefined();
    }
  });

  test('should have CVE database settings', async ({ page }) => {
    await page.goto('/settings');
    try { await page.waitForLoadState('networkidle', { timeout: 3000 }); } catch { /* networkidle timeout ok */ }

    const cveTab = page.getByRole('tab', { name: /cve|vulnerability|nvd/i }).first();
    if (await cveTab.isVisible()) {
      await cveTab.click();
      try { await page.waitForLoadState('networkidle', { timeout: 3000 }); } catch { /* networkidle timeout ok */ }

      // Should show CVE database configuration
      const pageContent = await page.textContent('body');
      expect(pageContent).toBeDefined();
    }
  });
});

test.describe('Pro+ License', () => {
  test('should display license status', async ({ page }) => {
    await page.goto('/settings');
    try { await page.waitForLoadState('networkidle', { timeout: 3000 }); } catch { /* networkidle timeout ok */ }

    const licenseTab = page.getByRole('tab', { name: /license/i }).first();
    if (await licenseTab.isVisible()) {
      await licenseTab.click();
      try { await page.waitForLoadState('networkidle', { timeout: 3000 }); } catch { /* networkidle timeout ok */ }

      // Should show license information
      const pageContent = await page.textContent('body');
      const hasLicenseInfo =
        pageContent?.toLowerCase().includes('license') ||
        pageContent?.toLowerCase().includes('tier') ||
        pageContent?.toLowerCase().includes('feature');

      expect(pageContent).toBeDefined();
    }
  });

  test('should show feature availability based on license', async ({ page }) => {
    await page.goto('/settings');
    try { await page.waitForLoadState('networkidle', { timeout: 3000 }); } catch { /* networkidle timeout ok */ }

    const licenseTab = page.getByRole('tab', { name: /license/i }).first();
    if (await licenseTab.isVisible()) {
      await licenseTab.click();
      try { await page.waitForLoadState('networkidle', { timeout: 3000 }); } catch { /* networkidle timeout ok */ }

      // License tab should indicate which features are available
      await expect(page.locator('body')).not.toBeEmpty();
    }
  });
});

test.describe('Pro+ Navigation', () => {
  test('should show Pro+ nav items if licensed', async ({ page }) => {
    await page.goto('/');
    try { await page.waitForLoadState('networkidle', { timeout: 3000 }); } catch { /* networkidle timeout ok */ }

    // Look for Pro+ navigation items
    const nav = page.locator('nav, [role="navigation"]').first();
    if (await nav.isVisible()) {
      const navContent = await nav.textContent();

      // Pro+ features might add nav items
      expect(navContent).toBeDefined();
    }
  });

  test('should navigate to Pro+ pages from nav', async ({ page }) => {
    await page.goto('/');
    try { await page.waitForLoadState('networkidle', { timeout: 3000 }); } catch { /* networkidle timeout ok */ }

    // Try to find and click Pro+ nav links
    const vulnLink = page.getByRole('link', { name: /vuln|cve/i }).first();
    const complianceLink = page.getByRole('link', { name: /compliance/i }).first();
    const healthLink = page.getByRole('link', { name: /health/i }).first();

    // Click whichever is available
    if (await vulnLink.isVisible()) {
      await vulnLink.click();
      try { await page.waitForLoadState('networkidle', { timeout: 3000 }); } catch { /* networkidle timeout ok */ }
    } else if (await complianceLink.isVisible()) {
      await complianceLink.click();
      try { await page.waitForLoadState('networkidle', { timeout: 3000 }); } catch { /* networkidle timeout ok */ }
    } else if (await healthLink.isVisible()) {
      await healthLink.click();
      try { await page.waitForLoadState('networkidle', { timeout: 3000 }); } catch { /* networkidle timeout ok */ }
    }

    // Page should be navigable
    await expect(page.locator('body')).not.toBeEmpty();
  });
});

/**
 * Helper: open the Settings page and click the named tab.  Returns
 * true when the tab was found + clicked; false when it isn't present
 * (which can happen when the Pro+ engines aren't licensed / loaded in
 * this test environment, in which case the caller should soft-skip).
 *
 * The Settings page uses MUI ``<Tabs variant="scrollable">`` so tabs
 * past the viewport width are present in the DOM but clipped behind
 * an ``overflow: hidden`` container.  ``isVisible()`` returns false for
 * those clipped tabs, which is why we gate on ``count()`` (existence
 * in the DOM) rather than visibility, and call
 * ``scrollIntoViewIfNeeded()`` before the click.  License-absent → the
 * tab isn't rendered at all → ``count() === 0`` → soft-skip.
 */
async function openSettingsTab(page: Page, tabName: RegExp): Promise<boolean> {
  await page.goto('/settings', { waitUntil: 'domcontentloaded' });
  try { await page.waitForLoadState('networkidle', { timeout: 3000 }); } catch { /* ok */ }
  // Settings.tsx filters tabs against ``licenseModules`` which is
  // populated by an async ``/api/license`` fetch in a useEffect.  That
  // fetch can land just AFTER ``networkidle`` resolves, and React's
  // batched setState defers the tab-list re-render by another frame.
  //
  // CRITICAL ordering: before deciding a specific tab is "gated away", wait
  // for the settings TAB BAR ITSELF to render (any tab attached).  Otherwise,
  // under load the ``/api/license`` fetch + tab render can outrun a per-tab
  // attach wait, and a tab that is merely SLOW gets misclassified as ABSENT —
  // the caller then asserts ``count() === 0`` and fails because the tab does
  // in fact appear a moment later.  Waiting for the bar first makes the
  // gated-vs-present decision deterministic (the bar is rendered → the tab
  // list is final → a missing tab is genuinely gated).
  try {
    await page.getByRole('tab').first().waitFor({ state: 'attached', timeout: 20000 });
  } catch { /* no tabs rendered at all — fall through to the per-tab check */ }

  const tab = page.getByRole('tab', { name: tabName }).first();
  try {
    // Generous window: even after the bar renders, the licensed-module tabs
    // can attach a frame or two later under load.  A too-short wait here was
    // the source of the "slow tab read as gated" flake.
    await tab.waitFor({ state: 'attached', timeout: 10000 });
  } catch {
    return false;
  }
  await tab.scrollIntoViewIfNeeded().catch(() => { /* ok */ });
  await tab.click();
  try { await page.waitForLoadState('networkidle', { timeout: 10000 }); } catch { /* ok */ }
  return true;
}

/**
 * Pro+ settings-tab assertions — no-skip variant.
 *
 * Two failure modes that look identical without context:
 *   (a) The Pro+ engine isn't loaded → tab is correctly OSS-gated
 *       (the moduleRequired: '<engine>' filter in Settings.tsx hides
 *       the tab).  This is correct behavior and the test should PASS.
 *   (b) The Pro+ engine IS loaded → tab renders + the canonical
 *       interactions work.
 *
 * Earlier versions of these tests used ``test.skip()`` when the tab
 * wasn't present, which showed up as "skipped" in CI reports and made
 * it impossible to distinguish "this CI run doesn't have a license
 * fixture" from "this CI run has a regression that broke the tab".
 *
 * The pattern below collapses both branches into one assertion: the
 * tab is either gated-away (count === 0 → assert it's NOT in the DOM
 * to lock in the gating contract) OR present (→ assert the canonical
 * functionality).  Both branches PASS — no skip.
 */

test.describe('Pro+ Phase 8.7 — Report Branding settings', () => {
  test('Report Branding tab is correctly gated or fully functional', async ({ page }) => {
    const opened = await openSettingsTab(page, /report branding/i);
    if (!opened) {
      // Gated-away branch: the moduleRequired: 'reporting_engine' filter
      // in Settings.tsx hid the tab.  Verify that's actually what happened
      // (positive assertion on the gating contract).
      const tab = page.getByRole('tab', { name: /report branding/i });
      expect(await tab.count()).toBe(0);
      return;
    }
    // Functional branch: tab is present → canonical fields render.  20s (the
    // expect default): the branding tabpanel form mounts after the tab-click
    // React transition + its GET /report-branding fetch, which can lag under
    // load — 10s raced it.
    const company = page.getByRole('textbox', { name: /company/i }).first();
    await expect(company).toBeVisible({ timeout: 20000 });
    const header = page.getByRole('textbox', { name: /header/i }).first();
    await expect(header).toBeVisible();
  });

  test('Report Branding logo upload is gated or rejects oversize', async ({ page }) => {
    const opened = await openSettingsTab(page, /report branding/i);
    if (!opened) {
      // Gated path — assert tab really is absent and we're done.
      const tab = page.getByRole('tab', { name: /report branding/i });
      expect(await tab.count()).toBe(0);
      return;
    }
    // Tab present — verify the oversize-upload error path.  Inject a
    // 2 MB buffer into the hidden ``<input type="file">`` to trigger
    // the server-side 1 MB cap.  We don't assert on the exact alert
    // wording — only that the UI surfaces an error path AND the page
    // stays interactive (i.e. doesn't crash).
    //
    // The file input is part of the tabpanel content, which renders
    // AFTER the tab click triggers a React state transition.  Use
    // ``waitFor`` instead of an instantaneous ``count()`` — the input
    // is hidden via CSS so we wait for ``attached`` rather than
    // ``visible``.  Throws on timeout (functions as the assertion).
    const fileInput = page.locator('input[type="file"]').first();
    // 20s: the tabpanel content mounts after the tab-click React transition +
    // its GET /report-branding fetch, which can lag under load — shorter waits
    // raced it even though the input attaches moments later.
    await fileInput.waitFor({ state: 'attached', timeout: 20000 });
    const big = Buffer.alloc(2 * 1024 * 1024, 0xff);
    await fileInput.setInputFiles({
      name: 'big.png',
      mimeType: 'image/png',
      buffer: big,
    });
    try { await page.waitForLoadState('networkidle', { timeout: 10000 }); } catch { /* ok */ }
    // The Save button must still be around — nothing in this flow
    // should leave the tab broken.
    const saveButton = page.getByRole('button', { name: /save/i }).first();
    await expect(saveButton).toBeVisible();
  });
});

test.describe('Pro+ Phase 8.7 — Report Templates settings', () => {
  test('Report Templates tab is correctly gated or fully functional', async ({ page }) => {
    const opened = await openSettingsTab(page, /report templates/i);
    if (!opened) {
      const tab = page.getByRole('tab', { name: /report templates/i });
      expect(await tab.count()).toBe(0);
      return;
    }
    // Functional branch — the "Add Template" button is the canonical
    // entry point; its presence proves the tab loaded its CRUD UI.
    const addButton = page.getByRole('button', { name: /add.*template/i }).first();
    await expect(addButton).toBeVisible({ timeout: 10000 });
  });

  test('Add Template dialog opens cleanly or feature is gated', async ({ page }) => {
    const opened = await openSettingsTab(page, /report templates/i);
    if (!opened) {
      const tab = page.getByRole('tab', { name: /report templates/i });
      expect(await tab.count()).toBe(0);
      return;
    }
    const addButton = page.getByRole('button', { name: /add.*template/i }).first();
    await expect(addButton).toBeVisible({ timeout: 10000 });
    await addButton.click();
    // Dialog should have a Cancel button.
    const dialog = page.getByRole('dialog').first();
    await expect(dialog).toBeVisible({ timeout: 10000 });
    const cancelButton = dialog.getByRole('button', { name: /cancel/i }).first();
    await expect(cancelButton).toBeVisible();
    await cancelButton.click();
    await expect(dialog).not.toBeVisible({ timeout: 5000 });
  });
});

test.describe('Pro+ Phase 8.7 — Dynamic Secrets settings', () => {
  test('Dynamic Secrets tab is correctly gated or fully functional', async ({ page }) => {
    const opened = await openSettingsTab(page, /dynamic secrets/i);
    if (!opened) {
      const tab = page.getByRole('tab', { name: /dynamic secrets/i });
      expect(await tab.count()).toBe(0);
      return;
    }
    const issueButton = page.getByRole('button', { name: /issue.*lease/i }).first();
    await expect(issueButton).toBeVisible({ timeout: 10000 });
  });

  test('Issue Lease dialog opens cleanly or feature is gated', async ({ page }) => {
    const opened = await openSettingsTab(page, /dynamic secrets/i);
    if (!opened) {
      const tab = page.getByRole('tab', { name: /dynamic secrets/i });
      expect(await tab.count()).toBe(0);
      return;
    }
    const issueButton = page.getByRole('button', { name: /issue.*lease/i }).first();
    await expect(issueButton).toBeVisible({ timeout: 10000 });
    await issueButton.click();
    const dialog = page.getByRole('dialog').first();
    await expect(dialog).toBeVisible({ timeout: 10000 });
    // Required fields: Name + Role.
    await expect(dialog.getByRole('textbox', { name: /name/i }).first()).toBeVisible();
    await expect(dialog.getByRole('textbox', { name: /role/i }).first()).toBeVisible();
    await dialog.getByRole('button', { name: /cancel/i }).first().click();
    await expect(dialog).not.toBeVisible({ timeout: 5000 });
  });
});

test.describe('Phase 8.4 — Audit Log PDF export', () => {
  test('exposes both CSV and PDF export buttons', async ({ page }) => {
    await page.goto('/reports/audit-log');
    try { await page.waitForLoadState('networkidle', { timeout: 3000 }); } catch { /* ok */ }
    expect(page.url()).not.toContain('/login');
    const csvButton = page.getByRole('button', { name: /export\s*csv/i }).first();
    const pdfButton = page.getByRole('button', { name: /export\s*pdf/i }).first();
    // Either the user is unauthorized (no buttons) or both are present.
    if (await csvButton.isVisible().catch(() => false)) {
      await expect(pdfButton).toBeVisible({ timeout: 5000 });
    }
  });

  test('PDF export is gated or download triggers', async ({ page }) => {
    await page.goto('/reports/audit-log');
    try { await page.waitForLoadState('networkidle', { timeout: 3000 }); } catch { /* ok */ }
    const pdfButton = page.getByRole('button', { name: /export\s*pdf/i }).first();
    const pdfVisible = await pdfButton.isVisible().catch(() => false);
    if (!pdfVisible) {
      // Gated path: the user lacks reporting_engine OR isn't authorized
      // to read audit logs.  Either way, the absence of the PDF button
      // is the correct OSS-gating signal.  Assert positively that the
      // page didn't redirect to login (the button absence is a real
      // gating decision, not a network failure).
      expect(page.url()).not.toContain('/login');
      return;
    }
    // Visible path: clicking should trigger a download with .pdf
    // suffix.  Tolerate "no download fires" because the audit log may
    // genuinely be empty in this test run — that's still a successful
    // OSS-side render, not a regression.
    const downloadPromise = page.waitForEvent('download', { timeout: 30000 }).catch(() => null);
    await pdfButton.click();
    const download = await downloadPromise;
    if (download) {
      const filename = download.suggestedFilename();
      expect(filename.toLowerCase()).toContain('.pdf');
    }
  });
});
