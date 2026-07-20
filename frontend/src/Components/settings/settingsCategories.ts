// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

// Two-pane Settings: the (~20) tabs are grouped into a categorized left rail
// instead of one long horizontal strip.  Unmapped tab ids fall into "System".
export const SETTINGS_CATEGORY_ORDER = [
  'general', 'security', 'patching', 'integrations', 'reporting', 'secrets', 'airgap', 'system',
] as const;

export const SETTINGS_CAT_LABEL = new Map<string, { key: string; def: string }>([
  ['general', { key: 'settings.cat.general', def: 'General' }],
  ['security', { key: 'settings.cat.security', def: 'Security & Access' }],
  ['patching', { key: 'settings.cat.patching', def: 'Patching' }],
  ['integrations', { key: 'settings.cat.integrations', def: 'Integrations & Logging' }],
  ['reporting', { key: 'settings.cat.reporting', def: 'Reporting' }],
  ['secrets', { key: 'settings.cat.secrets', def: 'Secrets' }],
  ['airgap', { key: 'settings.cat.airgap', def: 'Air-Gap & Mirroring' }],
  ['system', { key: 'settings.cat.system', def: 'System' }],
]);

export const SETTINGS_TAB_CATEGORY = new Map<string, string>([
  ['configuration', 'general'], ['tags', 'general'], ['host-defaults', 'general'], ['available-packages', 'general'],
  ['authentication', 'security'], ['antivirus', 'security'], ['firewall-roles', 'security'],
  ['compliance-profiles', 'security'], ['cve-refresh', 'security'], ['cve-database', 'security'], ['fips-compliance', 'security'],
  ['update-profiles', 'patching'], ['distributions', 'patching'],
  ['integrations', 'integrations'], ['logging', 'integrations'], ['ubuntu-pro', 'integrations'], ['alerting', 'integrations'],
  ['report-branding', 'reporting'], ['report-templates', 'reporting'],
  ['dynamic-secrets', 'secrets'],
  ['airgap-bundles', 'airgap'], ['repository-mirroring', 'airgap'],
  ['server-role', 'system'], ['queues', 'system'], ['license', 'system'],
]);

export interface SettingsTabDef {
  id: string;
  labelKey: string;
  labelDefault: string;
  moduleRequired?: string;
  requiresLicense?: boolean;
}

// Tab definitions — each entry declares its hash id, label key, and the
// module that must be licensed for the tab to be visible.  ``moduleRequired``
// is undefined for OSS-appropriate tabs.  The order here is the visible
// order in the UI.  License filtering is applied by the caller.
export const SETTINGS_TAB_DEFS: SettingsTabDef[] = [
  // Fixed leading order (Bryan): Configuration, Server Role, Host
  // Defaults — the most-used settings, with Configuration as the default
  // landing tab for the settings gear.
  {
    id: 'configuration',
    labelKey: 'configuration.title',
    labelDefault: 'Configuration',
  },
  // Server Role (air-gap topology) — ungated: every deployment,
  // including standalone Community, can pick its role.  Replaces
  // the old sysmanage.yaml ``role:`` key.  The page hosts BOTH the
  // air-gap and federation role cards, so the menu item is "Server
  // Role" — distinct from ``serverRole.heading`` (the air-gap card's
  // own "Air-Gap Role" title).
  {
    id: 'server-role',
    labelKey: 'serverRole.menuTitle',
    labelDefault: 'Server Role',
  },
  { id: 'logging', labelKey: 'logging.title', labelDefault: 'Logging' },
  { id: 'host-defaults', labelKey: 'hostDefaults.title', labelDefault: 'Host Defaults' },
  { id: 'tags', labelKey: 'tags.title', labelDefault: 'Tags' },
  { id: 'queues', labelKey: 'queues.title', labelDefault: 'Queues' },
  {
    id: 'integrations',
    labelKey: 'integrations.title',
    labelDefault: 'Integrations',
    moduleRequired: 'observability_engine',
  },
  { id: 'ubuntu-pro', labelKey: 'ubuntuPro.title', labelDefault: 'Ubuntu Pro' },
  {
    id: 'antivirus',
    labelKey: 'antivirus.title',
    labelDefault: 'Antivirus',
    moduleRequired: 'av_management_engine',
  },
  {
    id: 'available-packages',
    labelKey: 'availablePackages.title',
    labelDefault: 'Available Packages',
  },
  {
    id: 'firewall-roles',
    labelKey: 'firewallRoles.title',
    labelDefault: 'Firewall Roles',
    moduleRequired: 'firewall_orchestration_engine',
  },
  { id: 'distributions', labelKey: 'distributions.title', labelDefault: 'Distributions' },
  // Dynamic Secrets: visibility deferred until its Pro+ fold-in
  // lands.  Stays visible (and OSS-functional) until then.
  //
  // Access Groups + Registration Keys (Phase 12.4): contributed at
  // runtime via the federation controller plugin bundle (see
  // ``sysmanage-professional-plus/frontend/plugin-src/entries/federation-controller-entry.ts``).
  // Picked up by the ``pluginSettingsTabs`` loop further down with
  // ``moduleRequired: 'federation_controller_engine'`` gating.
  {
    id: 'update-profiles',
    labelKey: 'upgradeProfiles.tabLabel',
    labelDefault: 'Update Profiles',
    // Phase 10.6: scheduled upgrade profiles moved to the Pro+
    // ``automation_engine`` (cron + per-host dispatch live there).
    // The OSS server returns 402 from every /api/v1/upgrade-profiles
    // route without it, so the tab simply hides.
    moduleRequired: 'automation_engine',
  },
  {
    id: 'compliance-profiles',
    labelKey: 'packageProfiles.tabLabel',
    labelDefault: 'Compliance Profiles',
    // Phase 11.5: package compliance profiles moved to the Pro+
    // ``compliance_engine`` (evaluator + remediation-plan builder
    // live there).  The OSS server returns 402 from every
    // /api/v1/package-profiles route without it, so the tab simply
    // hides for unlicensed deployments.
    moduleRequired: 'compliance_engine',
  },
  {
    id: 'report-branding',
    labelKey: 'reportBranding.tabLabel',
    labelDefault: 'Report Branding',
    moduleRequired: 'reporting_engine',
  },
  {
    id: 'report-templates',
    labelKey: 'reportTemplates.tabLabel',
    labelDefault: 'Report Templates',
    moduleRequired: 'reporting_engine',
  },
  {
    id: 'airgap-bundles',
    labelKey: 'airgapBundles.tabLabel',
    labelDefault: 'Air-Gap Bundles',
    // Air-gap is an ENTERPRISE feature (features.py: AIRGAP_* live in the
    // Enterprise tier, paired with the airgap_collector_engine). Gate on
    // that engine so the tab hides on Community AND Professional — a bare
    // ``requiresLicense`` leaked it onto Professional, which has no air-gap.
    moduleRequired: 'airgap_collector_engine',
  },
  {
    id: 'repository-mirroring',
    labelKey: 'mirror.tabLabel',
    labelDefault: 'Repository Mirroring',
    // Phase 10.4: gated on the Pro+ engine that owns the plan
    // builders.  Without it loaded every /api/mirror-repositories
    // route returns 402, so the tab simply hides.
    moduleRequired: 'repository_mirroring_engine',
  },
  {
    id: 'authentication',
    labelKey: 'idp.tabLabel',
    labelDefault: 'Authentication',
    // Phase 10.5: external IdP integration (LDAP/AD + OIDC).
    // Routes 402 without ``external_idp_engine`` loaded.
    moduleRequired: 'external_idp_engine',
  },
];
