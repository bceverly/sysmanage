/**
 * React context that provides plugin state to components.
 *
 * Wraps the PluginManager singleton in a React context so that
 * components re-render when plugins are registered.
 */

// Declare Vite's import.meta.env types
declare global {
    interface ImportMeta {
        env: {
            VITE_BACKEND_PORT?: string;
            [key: string]: string | undefined;
        };
    }
}

import React, { createContext, useContext, useState, useEffect, useCallback, useMemo } from 'react';
import { pluginManager } from './PluginManager';
import type {
    PluginNavItem,
    PluginRoute,
    PluginHostDetailTab,
    PluginSettingsTab,
} from './types';

interface PluginContextValue {
    navItems: PluginNavItem[];
    routes: PluginRoute[];
    hostDetailTabs: PluginHostDetailTab[];
    settingsTabs: PluginSettingsTab[];
    pluginsLoaded: boolean;
}

const PluginContext = createContext<PluginContextValue>({
    navItems: [],
    routes: [],
    hostDetailTabs: [],
    settingsTabs: [],
    pluginsLoaded: false,
});

export const usePlugins = (): PluginContextValue => useContext(PluginContext);

interface PluginProviderProps {
    children: React.ReactNode;
}

export const PluginProvider: React.FC<PluginProviderProps> = ({ children }) => {
    const [revision, setRevision] = useState(0);
    const [pluginsLoaded, setPluginsLoaded] = useState(false);

    // Subscribe to plugin manager changes
    useEffect(() => {
        const unsubscribe = pluginManager.subscribe(() => {
            setRevision(r => r + 1);
        });
        return unsubscribe;
    }, []);

    // Load plugin bundles from backend
    const loadPlugins = useCallback(async () => {
        try {
            const token = localStorage.getItem('bearer_token');
            if (!token) {
                setPluginsLoaded(true);
                return;
            }

            const currentHost = globalThis.location.hostname;
            const backendPort = import.meta.env.VITE_BACKEND_PORT || 8080;
            const baseURL = `http://${currentHost}:${backendPort}`;

            const response = await fetch(`${baseURL}/api/plugins/bundles`, {
                headers: { 'Authorization': `Bearer ${token}` },
            });

            if (!response.ok) {
                setPluginsLoaded(true);
                return;
            }

            const data = await response.json();
            const bundles: string[] = data.bundles || [];

            for (const bundleUrl of bundles) {
                try {
                    const scriptResponse = await fetch(`${baseURL}${bundleUrl}`, {
                        headers: { 'Authorization': `Bearer ${token}` },
                    });
                    if (scriptResponse.ok) {
                        const scriptText = await scriptResponse.text();
                        // Execute the IIFE script which will call registerPlugin
                        const scriptEl = document.createElement('script');
                        scriptEl.textContent = scriptText;
                        document.head.appendChild(scriptEl);
                        scriptEl.remove();
                    }
                } catch (err) {
                    console.warn('Failed to load plugin bundle:', bundleUrl, err);
                }
            }
        } catch (err) {
            console.warn('Failed to discover plugins:', err);
        } finally {
            setPluginsLoaded(true);
        }
    }, []);

    useEffect(() => {
        loadPlugins();
    }, [loadPlugins]);

    // Rebuild context value when plugins change (revision triggers re-computation)
    const value: PluginContextValue = useMemo(
        () => ({
            navItems: pluginManager.getNavItems(),
            routes: pluginManager.getRoutes(),
            hostDetailTabs: pluginManager.getHostDetailTabs(),
            settingsTabs: pluginManager.getSettingsTabs(),
            pluginsLoaded,
        }),
        // eslint-disable-next-line react-hooks/exhaustive-deps -- revision is intentionally used to trigger re-computation when plugins change
        [revision, pluginsLoaded]
    );

    return (
        <PluginContext.Provider value={value}>
            {children}
        </PluginContext.Provider>
    );
};
