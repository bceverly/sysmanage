// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

// Tab-name/URL-hash synchronisation and left-rail grouping for the Host Detail
// page.  The numeric tab index + tabDefinitions stay in the parent; this hook
// derives navigation helpers from them.

import React, { useCallback, useEffect, useMemo, useRef } from 'react';
import type { TFunction } from 'i18next';
import { SysManageHost, UbuntuProInfo } from '../../Services/hosts';
import { HOST_CATEGORY_ORDER, HOST_CAT_LABEL, HOST_TAB_CATEGORY } from './hostDetailTypes';

interface TabDef { id: string; label: string; }

interface UseHostTabNavigationArgs {
    tabDefinitions: TabDef[];
    currentTab: number;
    setCurrentTab: React.Dispatch<React.SetStateAction<number>>;
    host: SysManageHost | null;
    ubuntuProInfo: UbuntuProInfo | null;
    t: TFunction;
}

export const useHostTabNavigation = ({
    tabDefinitions,
    currentTab,
    setCurrentTab,
    host,
    ubuntuProInfo,
    t,
}: UseHostTabNavigationArgs) => {
    // Store the initial URL hash for tab resolution after tabDefinitions is ready
    const initialTabHash = useRef(globalThis.location.hash.slice(1));

    // Tab names for URL hash - derived from tabDefinitions
    const getTabNames = useCallback(() => {
        return tabDefinitions.map(td => td.id);
    }, [tabDefinitions]);

    // Group the visible tabs into the left-rail sections (empty categories drop
    // out, so a host shows only the categories it has tabs in).
    const hostTabGroups = useMemo(() => {
        const groups = new Map<string, { id: string; label: string }[]>();
        for (const td of tabDefinitions) {
            const cat = HOST_TAB_CATEGORY.get(td.id) ?? 'overview';
            const arr = groups.get(cat) ?? [];
            arr.push({ id: td.id, label: td.label });
            groups.set(cat, arr);
        }
        return HOST_CATEGORY_ORDER
            .filter(c => (groups.get(c)?.length ?? 0) > 0)
            .map(c => {
                const meta = HOST_CAT_LABEL.get(c);
                return {
                    id: c,
                    label: t(meta?.key ?? c, meta?.def ?? c),
                    tabs: groups.get(c) ?? [],
                };
            });
    }, [tabDefinitions, t]);

    // Resolve initial tab from URL hash once tabDefinitions is ready
    useEffect(() => {
        if (initialTabHash.current) {
            const hash = initialTabHash.current;
            initialTabHash.current = ''; // Only resolve once
            const idx = tabDefinitions.findIndex(td => td.id === hash);
            if (idx > 0) {
                setCurrentTab(idx);
            }
        }
    }, [tabDefinitions, setCurrentTab]);

    // Listen for hash changes (browser back/forward)
    useEffect(() => {
        const handleHashChange = () => {
            const hash = globalThis.location.hash.slice(1);
            if (!hash) return;
            const tabs = getTabNames();
            const tabIndex = tabs.indexOf(hash);
            if (tabIndex >= 0) {
                setCurrentTab(tabIndex);
            }
        };

        globalThis.addEventListener('hashchange', handleHashChange);
        return () => globalThis.removeEventListener('hashchange', handleHashChange);
    }, [getTabNames, setCurrentTab]);

    // Recalculate current tab when host or ubuntuProInfo changes (handles dynamic tabs)
    useEffect(() => {
        const hash = globalThis.location.hash.slice(1);
        if (!hash) return;
        const tabs = getTabNames();
        const tabIndex = tabs.indexOf(hash);
        if (tabIndex >= 0 && tabIndex !== currentTab) {
            setCurrentTab(tabIndex);
        }
    }, [host, ubuntuProInfo, getTabNames, currentTab, setCurrentTab]);

    const handleTabChange = (_event: React.SyntheticEvent, newValue: number) => {
        setCurrentTab(newValue);
        const tabs = getTabNames();
        // Safely access array element with bounds check
        if (newValue >= 0 && newValue < tabs.length) {
            globalThis.location.hash = tabs[newValue]; // nosemgrep: detect-object-injection
        }
    };

    return {
        hostTabGroups,
        handleTabChange,
    };
};
