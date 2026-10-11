// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import type { TFunction } from 'i18next';
import type { GridRenderCellParams } from '@mui/x-data-grid';
import {
  assetTagMatches,
  buildAssetTagColumn,
  findHostsByAssetTag,
  hostAssetTag,
  isUntagged,
  UNTAGGED_PLACEHOLDER,
} from '../../Components/hostAssetTag';
import { buildHostColumns } from '../../Components/hostsColumns';
import type { SysManageHost } from '../../Services/hosts';

const t = ((_key: string, fallback?: string) => fallback ?? _key) as unknown as TFunction;

const host = (id: string, fqdn: string, asset_tag: string | null): SysManageHost =>
  ({ id, fqdn, asset_tag, machine_id: asset_tag ? `m-${asset_tag}` : null } as SysManageHost);

describe('hostAssetTag helpers', () => {
  it('reads the tag and treats blank or missing as untagged', () => {
    expect(hostAssetTag(host('1', 'a', 'GDR-000042'))).toBe('GDR-000042');
    expect(hostAssetTag(host('1', 'a', '   '))).toBeNull();
    expect(hostAssetTag({} as SysManageHost)).toBeNull();
    expect(isUntagged(host('1', 'a', null))).toBe(true);
    expect(isUntagged(host('1', 'a', 'X1'))).toBe(false);
  });

  it('matches case-insensitively and never matches untagged or an empty query', () => {
    expect(assetTagMatches(host('1', 'a', 'GDR-000042'), 'gdr-0000')).toBe(true);
    expect(assetTagMatches(host('1', 'a', 'GDR-000042'), 'zzz')).toBe(false);
    expect(assetTagMatches(host('1', 'a', null), 'gdr')).toBe(false);
    expect(assetTagMatches(host('1', 'a', 'GDR-000042'), '  ')).toBe(false);
  });

  it('finds hosts by tag, exact matches first, then by name, within the limit', () => {
    const hosts = [
      host('1', 'zeta', 'GDR-0000420'),
      host('2', 'beta', 'GDR-000042'),
      host('3', 'alpha', 'GDR-000042'),
      host('4', 'none', null),
    ];
    expect(findHostsByAssetTag(hosts, 'gdr-000042').map(h => h.id)).toEqual(['3', '2', '1']);
    expect(findHostsByAssetTag(hosts, 'gdr', 1)).toHaveLength(1);
  });
});

describe('Asset Tag column', () => {
  const column = buildAssetTagColumn(t);
  const renderCell = (value: string | null) =>
    render(<>{column.renderCell?.({ value } as GridRenderCellParams)}</>);

  it('is sortable and reads the tag from the row', () => {
    expect(column.field).toBe('asset_tag');
    expect(column.headerName).toBe('Asset Tag');
    expect(column.sortable).not.toBe(false);
    const getter = column.valueGetter as unknown as (_v: unknown, _row: SysManageHost) => unknown;
    expect(getter(undefined, host('1', 'a', 'GDR-000042'))).toBe('GDR-000042');
    expect(getter(undefined, host('1', 'a', null))).toBeNull();
  });

  it('renders the tag', () => {
    renderCell('GDR-000042');
    expect(screen.getByText('GDR-000042')).toBeInTheDocument();
  });

  it('renders a placeholder for an untagged host', () => {
    renderCell(null);
    expect(screen.getByText(UNTAGGED_PLACEHOLDER)).toHaveAttribute('title', 'Untagged');
  });

  it('is part of the Hosts grid columns', () => {
    const columns = buildHostColumns({
      t,
      navigate: () => {},
      canViewHostDetails: false,
      tableData: [],
      hasHealthData: false,
    });
    expect(columns.map(c => c.field)).toContain('asset_tag');
  });
});
