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
