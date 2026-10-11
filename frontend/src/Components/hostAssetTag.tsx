// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

// Asset tags in the Hosts grid and in search (Phase 23.2).  The tag belongs to
// the MACHINE, so every OS on a multi-boot machine carries the same one; these
// helpers only read ``host.asset_tag`` as the server reports it.

import React from 'react';
import { GridColDef } from '@mui/x-data-grid';
import { TFunction } from 'i18next';
import { SysManageHost } from '../Services/hosts';

/** Shown in the grid for a host whose machine has no tag. */
export const UNTAGGED_PLACEHOLDER = '-';

/** The host's asset tag, or null when its machine is untagged. */
export const hostAssetTag = (host: Pick<SysManageHost, 'asset_tag'>): string | null => {
    const tag = host.asset_tag?.trim();
    return tag || null;
};

export const isUntagged = (host: Pick<SysManageHost, 'asset_tag'>): boolean =>
    hostAssetTag(host) === null;

/** Case-insensitive substring match on the asset tag; untagged never matches. */
export const assetTagMatches = (host: Pick<SysManageHost, 'asset_tag'>, query: string): boolean => {
    const tag = hostAssetTag(host);
    const q = query.trim().toLowerCase();
    return tag !== null && q !== '' && tag.toLowerCase().includes(q);
};

/** Hosts whose asset tag matches ``query``, exact tags first, then by name. */
export const findHostsByAssetTag = (
    hosts: SysManageHost[],
    query: string,
    limit = 10,
): SysManageHost[] => {
    const q = query.trim().toLowerCase();
    const exact = (h: SysManageHost) => (hostAssetTag(h)?.toLowerCase() === q ? 0 : 1);
    return hosts
        .filter(h => assetTagMatches(h, q))
        .sort((a, b) => exact(a) - exact(b) || (a.fqdn || '').localeCompare(b.fqdn || ''))
        .slice(0, limit);
};

/** The Hosts grid's "Asset Tag" column. */
export const buildAssetTagColumn = (t: TFunction): GridColDef => ({
    field: 'asset_tag',
    headerName: t('assetTags.grid.column', 'Asset Tag'),
    width: 140,
    valueGetter: (_value, row: SysManageHost) => hostAssetTag(row),
    renderCell: (params) => {
        const tag = params.value as string | null;
        if (tag === null) {
            return (
                <span
                    style={{ color: '#666' }}
                    title={t('assetTags.grid.untagged', 'Untagged')}
                >
                    {UNTAGGED_PLACEHOLDER}
                </span>
            );
        }
        return <span style={{ fontFamily: 'monospace' }}>{tag}</span>;
    },
});
