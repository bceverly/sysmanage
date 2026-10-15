// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

// The fleet's hardware, worst first (Phase 23.1 S4): each host's status, the
// components that need attention and why, and how many it reports.

import React, { useMemo } from 'react';
import { Chip, Link, Stack, Tooltip, Typography } from '@mui/material';
import { DataGrid, GridColDef } from '@mui/x-data-grid';
import { Link as RouterLink } from 'react-router';
import { useTranslation } from 'react-i18next';
import type { TFunction } from 'i18next';
import type { FleetHost } from '../../Services/hardwareHealth';
import { kindLabel, reasonsText, statusColor, statusHelp, statusLabel } from './hardwareHealthLabels';

const Problems: React.FC<{ row: FleetHost }> = ({ row }) => {
    const { t } = useTranslation();
    if (row.problems.length === 0) {
        return <Typography variant="body2" color="text.secondary">-</Typography>;
    }
    return (
        <Stack direction="column" justifyContent="center" sx={{ height: '100%', py: 0.5 }}>
            {row.problems.map(p => (
                <Typography key={`${p.kind}/${p.id}`} variant="body2" noWrap>
                    <strong>{kindLabel(t, p.kind)} {p.name}</strong>: {reasonsText(t, p.reasons)}
                </Typography>
            ))}
        </Stack>
    );
};

const componentCount = (row: FleetHost): number =>
    Object.values(row.component_counts).reduce((sum, n) => sum + (n ?? 0), 0);

const columns = (t: TFunction): GridColDef<FleetHost>[] => [
    {
        field: 'fqdn',
        headerName: t('hardwareHealth.grid.host', 'Host'),
        flex: 1.2,
        minWidth: 180,
        renderCell: ({ row }) => (
            <Link component={RouterLink} to={`/hosts/${row.host_id}`}>{row.fqdn}</Link>
        ),
    },
    {
        field: 'status',
        headerName: t('hardwareHealth.grid.status', 'Status'),
        width: 170,
        renderCell: ({ row }) => (
            <Tooltip title={statusHelp(t, row.status)}>
                <Chip size="small" color={statusColor(row.status)} label={statusLabel(t, row.status)} />
            </Tooltip>
        ),
    },
    {
        field: 'problems',
        headerName: t('hardwareHealth.grid.problems', 'Needs attention'),
        flex: 2.4,
        minWidth: 280,
        sortable: false,
        renderCell: ({ row }) => <Problems row={row} />,
    },
    {
        field: 'components',
        headerName: t('hardwareHealth.grid.components', 'Components'),
        width: 120,
        valueGetter: (_value, row) => componentCount(row),
    },
    {
        field: 'platform',
        headerName: t('hardwareHealth.grid.platform', 'OS'),
        width: 120,
        valueGetter: (_value, row) => row.platform ?? '',
    },
    {
        field: 'site_name',
        headerName: t('hardwareHealth.grid.site', 'Site'),
        width: 150,
        valueGetter: (_value, row) => row.site_name ?? '',
    },
    {
        field: 'reported_at',
        headerName: t('hardwareHealth.grid.reported', 'Last report'),
        width: 190,
        valueFormatter: (value: string | null) => (value ? new Date(`${value}Z`).toLocaleString() : '-'),
    },
];

const FleetHardwareGrid: React.FC<{ rows: FleetHost[] }> = ({ rows }) => {
    const { t } = useTranslation();
    const cols = useMemo(() => columns(t), [t]);
    return (
        // A flex-column parent with no fixed height lets the grid grow with
        // its rows (the replacement for the deprecated autoHeight prop).
        <div style={{ display: 'flex', flexDirection: 'column' }}>
            <DataGrid
                rows={rows}
                columns={cols}
                getRowId={row => row.host_id}
                getRowHeight={() => 'auto'}
                disableRowSelectionOnClick
                pageSizeOptions={[25, 50, 100]}
                initialState={{ pagination: { paginationModel: { pageSize: 50 } } }}
            />
        </div>
    );
};

export default FleetHardwareGrid;
