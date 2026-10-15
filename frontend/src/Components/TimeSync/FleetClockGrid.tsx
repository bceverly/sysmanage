// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

// The fleet's clocks, worst first (Phase 23.3 S4).  The server sorts; the grid
// keeps that order until the operator sorts by a column.

import React, { useMemo } from 'react';
import { Chip, Link, Stack, Tooltip, Typography } from '@mui/material';
import { DataGrid, GridColDef } from '@mui/x-data-grid';
import { Link as RouterLink } from 'react-router';
import { useTranslation } from 'react-i18next';
import type { TFunction } from 'i18next';
import type { FleetClock } from '../../Services/timeSync';
import { policyChip } from './HostClockPolicy';
import {
    formatOffset,
    offsetDirection,
    policyFindingText,
    serviceName,
    sourceLabel,
    statusColor,
    statusHelp,
    statusLabel,
} from './timeSyncLabels';

const serviceText = (t: TFunction, row: FleetClock): string => {
    const name = serviceName(t, row.time_service);
    if (row.service_ok === false) {
        return t('timeSync.grid.serviceProblem', '{{service}} (not running or not synchronized)', { service: name });
    }
    return name;
};

const columns = (t: TFunction): GridColDef<FleetClock>[] => [
    {
        field: 'fqdn',
        headerName: t('timeSync.grid.host', 'Host'),
        flex: 1.4,
        minWidth: 180,
        renderCell: ({ row }) => (
            <Link component={RouterLink} to={`/hosts/${row.host_id}`}>{row.fqdn}</Link>
        ),
    },
    {
        field: 'status',
        headerName: t('timeSync.grid.status', 'Status'),
        width: 190,
        renderCell: ({ row }) => (
            <Tooltip title={statusHelp(t, row.status)}>
                <Chip size="small" color={statusColor(row.status)} label={statusLabel(t, row.status)} />
            </Tooltip>
        ),
    },
    {
        field: 'offset',
        headerName: t('timeSync.grid.offset', 'Offset'),
        width: 210,
        valueGetter: (_value, row) => row.measured?.offset_ms ?? null,
        sortComparator: (a, b) => Math.abs(a ?? 0) - Math.abs(b ?? 0),
        renderCell: ({ row }) => (
            <Stack direction="column" justifyContent="center" sx={{ height: '100%' }}>
                <Typography variant="body2">{formatOffset(t, row.measured?.offset_ms)}</Typography>
                <Typography variant="caption" color="text.secondary">
                    {offsetDirection(t, row.measured?.offset_ms)}
                </Typography>
            </Stack>
        ),
    },
    {
        field: 'rtt',
        headerName: t('timeSync.grid.roundTrip', 'Round trip'),
        width: 120,
        valueGetter: (_value, row) => row.measured?.rtt_ms ?? null,
        valueFormatter: (value: number | null) => formatOffset(t, value).replace('+', ''),
    },
    {
        field: 'time_service',
        headerName: t('timeSync.grid.service', 'Time service'),
        flex: 1,
        minWidth: 170,
        valueGetter: (_value, row) => serviceText(t, row),
    },
    {
        field: 'time_source',
        headerName: t('timeSync.grid.source', 'Time source'),
        flex: 1,
        minWidth: 150,
    },
    {
        field: 'bounds',
        headerName: t('timeSync.grid.bounds', 'Bounds'),
        width: 220,
        sortable: false,
        // Pure punctuation around translated parts: nothing here to translate.
        valueGetter: (_value, row) =>
            `${formatOffset(t, row.bounds.warning_ms).replace('+', '')} / `
            + `${formatOffset(t, row.bounds.critical_ms).replace('+', '')} `
            + `(${sourceLabel(t, row.bounds.source)})`,
    },
    {
        field: 'policy_compliant',
        headerName: t('timeSync.policy.column', 'NTP policy'),
        width: 170,
        renderCell: ({ row }) => (
            <Tooltip title={row.policy_findings.map(code => policyFindingText(t, code)).join('; ')}>
                <span>{policyChip(t, row.policy_compliant, row.policy_findings.length)}</span>
            </Tooltip>
        ),
    },
    {
        field: 'site_name',
        headerName: t('timeSync.grid.site', 'Site'),
        width: 140,
    },
    {
        field: 'tags',
        headerName: t('timeSync.grid.tags', 'Tags'),
        flex: 1,
        minWidth: 150,
        sortable: false,
        valueGetter: (_value, row) => row.tags.map(tag => tag.name).join(', '),
    },
];

const FleetClockGrid: React.FC<{ rows: FleetClock[] }> = ({ rows }) => {
    const { t } = useTranslation();
    const anyPolicy = rows.some(r => r.policy_compliant !== null);
    const cols = useMemo(
        () => columns(t).filter(c => anyPolicy || c.field !== 'policy_compliant'),
        [t, anyPolicy],
    );
    return (
        // A flex-column parent with no fixed height lets the grid grow with
        // its rows (the replacement for the deprecated autoHeight prop).
        <div style={{ width: '100%', display: 'flex', flexDirection: 'column' }}>
            <DataGrid
                rows={rows}
                columns={cols}
                getRowId={(row) => row.host_id}
                initialState={{ pagination: { paginationModel: { pageSize: 50 } } }}
                pageSizeOptions={[25, 50, 100]}
                rowHeight={56}
                disableRowSelectionOnClick
            />
        </div>
    );
};

export default FleetClockGrid;
