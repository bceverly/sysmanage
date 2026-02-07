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
}

/** Tab insertion position in host detail page. */
export type TabInsertPosition = 'after-info' | 'after-security' | 'before-diagnostics';

/** Tab added by a plugin to the host detail page. */
export interface PluginHostDetailTab {
    id: string;
    icon: ReactElement;
    labelKey: string;
    component: ComponentType<{ hostId: string }>;
    moduleRequired?: string;
    position: TabInsertPosition;
}

/** Tab added by a plugin to the settings page. */
export interface PluginSettingsTab {
    id: string;
    labelKey: string;
    component: ComponentType;
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
