import { test, expect, Page } from '@playwright/test';

/**
 * Phase 10.7 line 1829 — triple-tier license-matrix smoke test.
 *
 * Verifies that the OSS frontend's license-gating logic actually
 * hides Pro+ surfaces from Community-tier users and surfaces the
 * right slice for Professional vs Enterprise tiers.  The static
 * unit tests in ``__tests__/Services/license.test.tsx`` cover the
 * predicate-cache plumbing in isolation; this spec closes the loop
 * end-to-end against a real page render.
 *
 * Approach: intercept ``GET /api/license`` with a tier-specific
 * fixture, navigate to a page that uses the gates, and assert on
 * which Settings tabs the user actually sees.  We don't seed real
 * signed licenses on the backend because that would require:
 *   (a) generating signed JWTs in test setup, and
 *   (b) restarting the server between cases to swap the cached
 *       license.
 * The HTTP-intercept path is faster, deterministic, and exercises
 * the exact frontend logic in production.
 */

// Module codes we gate on.  Mirror ``backend/licensing/features.py``
// ``ModuleCode`` enum values; keep in sync if either side adds a
// new module.
const MODULES = {
    // Professional tier — included in both Pro and Ent fixtures below.
    HEALTH_ENGINE: 'health_engine',
    VULN_ENGINE: 'vuln_engine',
    COMPLIANCE_ENGINE: 'compliance_engine',
    ALERTING_ENGINE: 'alerting_engine',
    REPORTING_ENGINE: 'reporting_engine',
    AUDIT_ENGINE: 'audit_engine',
    SECRETS_ENGINE: 'secrets_engine',
    CONTAINER_ENGINE: 'container_engine',
    PROPLUS_CORE: 'proplus_core',
    // Enterprise-only — included only in the Ent fixture.
    AV_MANAGEMENT_ENGINE: 'av_management_engine',
    FIREWALL_ORCHESTRATION_ENGINE: 'firewall_orchestration_engine',
    AUTOMATION_ENGINE: 'automation_engine',
    FLEET_ENGINE: 'fleet_engine',
    VIRTUALIZATION_ENGINE: 'virtualization_engine',
    OBSERVABILITY_ENGINE: 'observability_engine',
    REPOSITORY_MIRRORING_ENGINE: 'repository_mirroring_engine',
    EXTERNAL_IDP_ENGINE: 'external_idp_engine',
    AIRGAP_COLLECTOR_ENGINE: 'airgap_collector_engine',
    AIRGAP_REPOSITORY_ENGINE: 'airgap_repository_engine',
} as const;

// Fixture: the body the frontend's ``getLicenseInfo()`` receives
// from ``GET /api/license`` for each of the three tiers.  Shape
// matches ``LicenseInfoResponse`` at ``backend/api/license_management.py``.
const FIXTURES = {
    community: {
        active: false,
    },
    professional: {
        active: true,
        tier: 'professional',
        license_id: 'test-pro',
        modules: [
            MODULES.HEALTH_ENGINE,
            MODULES.VULN_ENGINE,
            MODULES.COMPLIANCE_ENGINE,
            MODULES.ALERTING_ENGINE,
            MODULES.REPORTING_ENGINE,
            MODULES.AUDIT_ENGINE,
            MODULES.SECRETS_ENGINE,
            MODULES.CONTAINER_ENGINE,
            MODULES.PROPLUS_CORE,
        ],
        features: [],
    },
    enterprise: {
        active: true,
        tier: 'enterprise',
        license_id: 'test-ent',
        modules: Object.values(MODULES),
        features: [],
    },
} as const;

/**
 * Install a Playwright route interceptor that serves ``fixture`` as
 * the response body for every ``GET /api/license`` call from the
 * current page.  Call BEFORE ``page.goto(...)`` so the first fetch
 * the frontend issues lands on the mock.
 */
async function mockLicense(page: Page, fixture: object): Promise<void> {
    await page.route('**/api/license', async route => {
        if (route.request().method() !== 'GET') {
            return route.continue();
        }
        await route.fulfill({
            status: 200,
            contentType: 'application/json',
            body: JSON.stringify(fixture),
        });
    });
}

/**
 * Helper that opens the Settings page and waits for the Tabs strip
 * to render so the visibility assertions don't race the React
 * render cycle.
 */
async function gotoSettingsAndWait(page: Page): Promise<void> {
    await page.goto('/settings');
    await page.waitForLoadState('domcontentloaded');
    // The Tags tab is always-on regardless of license — it's the
    // anchor we use to know the Settings page rendered before
    // checking the conditional ones.
    await expect(page.getByRole('tab', { name: /^Tags$/i })).toBeVisible({
        timeout: 30000,
    });
}

/**
 * Names of the Settings tabs and the license tier in which each
 * should be visible.  ``labelRegex`` matches the rendered text via
 * ``getByRole('tab', { name: ... })``.  Each tab has a
 * ``moduleRequired`` field in ``Pages/Settings.tsx``'s tabDefs
 * (lines 175-256); we use the rendered label here rather than
 * coupling to internal IDs.
 */
const SETTINGS_TABS = [
    {
        labelRegex: /^Integrations$/i,
        requiredModule: MODULES.OBSERVABILITY_ENGINE,
        availableIn: 'enterprise' as const,
    },
    {
        labelRegex: /^Antivirus$/i,
        requiredModule: MODULES.AV_MANAGEMENT_ENGINE,
        availableIn: 'enterprise' as const,
    },
    {
        labelRegex: /^Firewall Roles$/i,
        requiredModule: MODULES.FIREWALL_ORCHESTRATION_ENGINE,
        availableIn: 'enterprise' as const,
    },
    {
        labelRegex: /^Update Profiles$/i,
        requiredModule: MODULES.AUTOMATION_ENGINE,
        availableIn: 'enterprise' as const,
    },
    {
        labelRegex: /^Compliance Profiles$/i,
        requiredModule: MODULES.COMPLIANCE_ENGINE,
        availableIn: 'professional' as const,
    },
    {
        labelRegex: /^Report Branding$/i,
        requiredModule: MODULES.REPORTING_ENGINE,
        availableIn: 'professional' as const,
    },
    {
        labelRegex: /^Report Templates$/i,
        requiredModule: MODULES.REPORTING_ENGINE,
        availableIn: 'professional' as const,
    },
] as const;

type Tier = 'community' | 'professional' | 'enterprise';

/**
 * Per-tier visibility expectation for a given tab.
 *   community     -> no Pro+ modules → hidden
 *   professional  -> shown iff its requiredModule is in the Pro fixture
 *   enterprise    -> always shown (every required module is licensed)
 */
function shouldBeVisible(
    tab: typeof SETTINGS_TABS[number],
    tier: Tier,
): boolean {
    if (tier === 'community') return false;
    if (tier === 'enterprise') return true;
    // professional
    return (FIXTURES.professional.modules as readonly string[]).includes(
        tab.requiredModule,
    );
}

for (const tier of ['community', 'professional', 'enterprise'] as const) {
    test.describe(`license matrix — ${tier}`, () => {
        test.beforeEach(async ({ page }) => {
            await mockLicense(page, FIXTURES[tier]);
        });

        test(`Settings shows the correct tab set for ${tier}`, async ({
            page,
        }) => {
            await gotoSettingsAndWait(page);

            for (const tab of SETTINGS_TABS) {
                const expectedVisible = shouldBeVisible(tab, tier);
                const tabElement = page.getByRole('tab', {
                    name: tab.labelRegex,
                });
                if (expectedVisible) {
                    await expect(
                        tabElement,
                        `${tab.labelRegex} should be visible for ${tier}`,
                    ).toBeVisible({ timeout: 15000 });
                } else {
                    // Negative assertion — tab must not be in the DOM.
                    // ``toHaveCount(0)`` rather than ``not.toBeVisible``
                    // catches the case where the tab renders off-screen
                    // due to the scrollable Tabs strip.
                    await expect(
                        tabElement,
                        `${tab.labelRegex} should be hidden for ${tier}`,
                    ).toHaveCount(0);
                }
            }
        });
    });
}

test.describe('license matrix — nav items follow the license', () => {
    test('community: /secrets and /reports nav links are hidden', async ({
        page,
    }) => {
        await mockLicense(page, FIXTURES.community);
        await page.goto('/hosts');
        await page.waitForLoadState('domcontentloaded');

        // Both NavLinks gate on activeLicenseModules.includes(...).  With
        // an empty modules list (community fixture), neither should render.
        await expect(page.getByRole('link', { name: /^Secrets$/i })).toHaveCount(
            0,
        );
        await expect(page.getByRole('link', { name: /^Reports$/i })).toHaveCount(
            0,
        );
    });

    test('enterprise: /secrets and /reports nav links are visible', async ({
        page,
    }) => {
        await mockLicense(page, FIXTURES.enterprise);
        await page.goto('/hosts');
        await page.waitForLoadState('domcontentloaded');

        await expect(
            page.getByRole('link', { name: /^Secrets$/i }).first(),
        ).toBeVisible({ timeout: 20000 });
        await expect(
            page.getByRole('link', { name: /^Reports$/i }).first(),
        ).toBeVisible({ timeout: 20000 });
    });
});
