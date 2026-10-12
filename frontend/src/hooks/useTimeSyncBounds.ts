// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

// Clock offset bounds (Phase 23.3 S4): the server-wide pair, the tenant /
// site / tag overrides, and the names the editor shows for each scope.

import { useCallback, useEffect, useState } from 'react';
import axiosInstance from '../Services/api';
import { errorCode } from '../Services/machines';
import { doListFederationSites } from '../Services/federation';
import { hasPermission, SecurityRoles } from '../Services/permissions';
import {
    clearOverride,
    getBounds,
    setOverride,
    setServerBounds,
} from '../Services/timeSync';
import type { BoundsConfig, OverrideScope } from '../Services/timeSync';

export interface Named {
    id: string;
    name: string;
}

export interface TimeSyncBounds {
    config: BoundsConfig | null;
    tags: Named[];
    sites: Named[];
    canEdit: boolean;
    /** A refusal code from the last save, or null. */
    error: string | null;
    loadFailed: boolean;
    saveServer: (warningMs: number, criticalMs: number) => Promise<boolean>;
    saveOverride: (scope: OverrideScope, ref: string, warningMs: number, criticalMs: number) => Promise<boolean>;
    removeOverride: (scope: OverrideScope, ref: string) => Promise<void>;
}

const loadSites = async (): Promise<Named[]> => {
    try {
        const response = await doListFederationSites();
        return response.licensed ? (response.sites ?? []).map(s => ({ id: s.id, name: s.name })) : [];
    } catch {
        return []; // no federation here: no site level to offer
    }
};

export const useTimeSyncBounds = (): TimeSyncBounds => {
    const [config, setConfig] = useState<BoundsConfig | null>(null);
    const [tags, setTags] = useState<Named[]>([]);
    const [sites, setSites] = useState<Named[]>([]);
    const [canEdit, setCanEdit] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [loadFailed, setLoadFailed] = useState(false);

    const load = useCallback(async () => {
        try {
            setConfig(await getBounds());
        } catch {
            setLoadFailed(true);
        }
    }, []);

    useEffect(() => {
        void load();
        void hasPermission(SecurityRoles.MANAGE_TIME_SYNC).then(setCanEdit).catch(() => setCanEdit(false));
        void axiosInstance.get('/api/v1/tags')
            .then(r => setTags((r.data ?? []).map((tag: Named) => ({ id: tag.id, name: tag.name }))))
            .catch(() => setTags([]));
        void loadSites().then(setSites);
    }, [load]);

    const attempt = async (save: () => Promise<unknown>): Promise<boolean> => {
        try {
            setError(null);
            await save();
            await load();
            return true;
        } catch (e) {
            setError(errorCode(e) ?? 'unknown');
            return false;
        }
    };

    return {
        config,
        tags,
        sites,
        canEdit,
        error,
        loadFailed,
        saveServer: (w, c) => attempt(() => setServerBounds(w, c)),
        saveOverride: (scope, ref, w, c) => attempt(() => setOverride(scope, ref, w, c)),
        removeOverride: async (scope, ref) => {
            await attempt(() => clearOverride(scope, ref));
        },
    };
};
