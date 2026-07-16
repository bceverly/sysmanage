// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

/**
 * Plugin system type definitions for SysManage.
 *
 * Plugins (like Pro+) register UI components, routes, navigation items,
 * host detail tabs, and settings tabs dynamically at runtime.
 */

import { ReactElement, ComponentType } from 'react';

/** Navigation item added by a plugin to the main navbar. */
export interface PluginNavItem {
    path: string;
    labelKey: string;
    featureFlag?: string;
}

/** Route added by a plugin to the main router. */
export interface PluginRoute {
    path: string;
    component: ComponentType;
    /**
     * Optional license-feature gate (a FeatureCode). When set, navigating to
     * this route directly by URL is only allowed if the active license grants
     * the feature; otherwise the router redirects home. Prevents reaching a
     * paid page by typing its URL even when its nav link is hidden.
     */
    featureFlag?: string;
    /** Optional license-module gate (a ModuleCode); same redirect semantics. */
    moduleRequired?: string;
}

/** Tab insertion position in host detail page. */
export type TabInsertPosition = 'after-info' | 'after-security' | 'before-diagnostics';

/** Tab added by a plugin to the host detail page. */
export interface PluginHostDetailTab {
    id: string;
    icon: ReactElement;
    labelKey: string;
    component: ComponentType<{ hostId: string }>;
    /**
     * Optional license-feature gate (a FeatureCode). When set, the tab is only
     * shown if the active license grants the feature. This is finer-grained
     * than ``moduleRequired``: an engine module can be licensed at a lower tier
     * (e.g. Professional) while a specific capability inside it is higher-tier
     * (e.g. the Enterprise ``fips_mode`` feature inside ``compliance_engine``),
     * so gate on the feature to avoid showing a tab the user can't actually use.
     * When both ``featureFlag`` and ``moduleRequired`` are set, BOTH must pass.
     */
    featureFlag?: string;
    moduleRequired?: string;
    position: TabInsertPosition;
}

/** Tab added by a plugin to the settings page. */
export interface PluginSettingsTab {
    id: string;
    labelKey: string;
    component: ComponentType;
    /**
     * Optional license-feature gate (a FeatureCode); finer-grained than
     * ``moduleRequired``. When both are set, BOTH must pass. See the note on
     * ``PluginHostDetailTab.featureFlag``.
     */
    featureFlag?: string;
    /**
     * Optional license-module gate.  When set, the tab is only
     * displayed if the active license includes this module code.
     * Mirrors the same field on ``PluginHostDetailTab`` and the
     * hardcoded ``tabDefs`` filter in ``Pages/Settings.tsx`` —
     * plugin tabs that omit ``moduleRequired`` stay always-visible
     * (the pre-Phase-10.7 behaviour).
     */
    moduleRequired?: string;
}

/**
 * A widget a plugin renders into a fixed slot in the main navbar (e.g. the
 * multi-tenancy tenant switcher).  Unlike a ``PluginNavItem`` (a link), this is
 * an arbitrary component owned by the plugin.  The component owns its own
 * visibility (e.g. renders ``null`` when not applicable).
 */
export interface PluginNavbarWidget {
    id: string;
    component: ComponentType;
    /** Optional license-feature gate (a FeatureCode); both gates must pass when set. */
    featureFlag?: string;
    /** Optional license-module gate (same semantics as the tab gates). */
    moduleRequired?: string;
}

/**
 * A banner a plugin renders at the top of the app shell (e.g. the
 * tenant-migration banner).  The component owns its own visibility.
 */
export interface PluginAppBanner {
    id: string;
    component: ComponentType;
    /** Optional license-feature gate (a FeatureCode); both gates must pass when set. */
    featureFlag?: string;
    /** Optional license-module gate (same semantics as the tab gates). */
    moduleRequired?: string;
}

/** Translation resources provided by a plugin. */
export interface PluginTranslations {
    [language: string]: Record<string, unknown>;
}

/** Full plugin registration object. */
export interface PluginRegistration {
    id: string;
    name: string;
    version: string;
    navItems?: PluginNavItem[];
    routes?: PluginRoute[];
    hostDetailTabs?: PluginHostDetailTab[];
    settingsTabs?: PluginSettingsTab[];
    navbarWidgets?: PluginNavbarWidget[];
    appBanners?: PluginAppBanner[];
    translations?: PluginTranslations;
}

/** Shape of the shared dependencies exposed on window. */
export interface SysManageShared {
    React: typeof import('react');
    ReactRouterDOM: typeof import('react-router-dom');
    ReactI18next: typeof import('react-i18next');
    MuiMaterial: Record<string, unknown>;
    MuiXDataGrid: Record<string, unknown>;
    MuiIcons: Record<string, unknown>;
    axiosInstance: unknown;
    hooks: Record<string, unknown>;
    components: Record<string, unknown>;
    services: Record<string, unknown>;
    i18n: Record<string, unknown>;
    registerPlugin: (plugin: PluginRegistration) => void;
}

declare global {
    interface Window {
        __SYSMANAGE_SHARED__?: SysManageShared;
    }
}
