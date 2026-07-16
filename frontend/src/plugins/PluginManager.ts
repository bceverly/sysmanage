// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

/**
 * Plugin manager singleton.
 *
 * Manages plugin registration and provides access to all registered
 * plugin contributions (nav items, routes, tabs, etc.).
 */

import type {
    PluginRegistration,
    PluginNavItem,
    PluginRoute,
    PluginHostDetailTab,
    PluginSettingsTab,
    PluginNavbarWidget,
    PluginAppBanner,
} from './types';

type Listener = () => void;

class PluginManager {
    private readonly plugins: Map<string, PluginRegistration> = new Map();
    private readonly listeners: Set<Listener> = new Set();

    registerPlugin = (plugin: PluginRegistration): void => {
        if (this.plugins.has(plugin.id)) {
            // Duplicate plugin registration silently ignored
            return;
        }
        // Plugin registration logged at debug level only
        this.plugins.set(plugin.id, plugin);
        this.notify();
    };

    getPlugins(): PluginRegistration[] {
        return Array.from(this.plugins.values());
    }

    getNavItems(): PluginNavItem[] {
        const items: PluginNavItem[] = [];
        for (const plugin of Array.from(this.plugins.values())) {
            if (plugin.navItems) {
                items.push(...plugin.navItems);
            }
        }
        return items;
    }

    getRoutes(): PluginRoute[] {
        const routes: PluginRoute[] = [];
        for (const plugin of Array.from(this.plugins.values())) {
            if (plugin.routes) {
                routes.push(...plugin.routes);
            }
        }
        return routes;
    }

    getHostDetailTabs(): PluginHostDetailTab[] {
        const tabs: PluginHostDetailTab[] = [];
        for (const plugin of Array.from(this.plugins.values())) {
            if (plugin.hostDetailTabs) {
                tabs.push(...plugin.hostDetailTabs);
            }
        }
        return tabs;
    }

    getSettingsTabs(): PluginSettingsTab[] {
        const tabs: PluginSettingsTab[] = [];
        for (const plugin of Array.from(this.plugins.values())) {
            if (plugin.settingsTabs) {
                tabs.push(...plugin.settingsTabs);
            }
        }
        return tabs;
    }

    getNavbarWidgets(): PluginNavbarWidget[] {
        const widgets: PluginNavbarWidget[] = [];
        for (const plugin of Array.from(this.plugins.values())) {
            if (plugin.navbarWidgets) {
                widgets.push(...plugin.navbarWidgets);
            }
        }
        return widgets;
    }

    getAppBanners(): PluginAppBanner[] {
        const banners: PluginAppBanner[] = [];
        for (const plugin of Array.from(this.plugins.values())) {
            if (plugin.appBanners) {
                banners.push(...plugin.appBanners);
            }
        }
        return banners;
    }

    subscribe(listener: Listener): () => void {
        this.listeners.add(listener);
        return () => {
            this.listeners.delete(listener);
        };
    }

    private notify(): void {
        for (const listener of Array.from(this.listeners)) {
            listener();
        }
    }
}

export const pluginManager = new PluginManager();
