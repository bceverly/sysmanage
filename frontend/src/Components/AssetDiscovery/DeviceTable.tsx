// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

// The discovered devices, with what each one says about itself and who saw
// it (Phase 21.6 S3).  Columns sort on click (deviceSort.ts).  A plain MUI table rather than a DataGrid: bulk
// selection is simple here, and a DataGrid does not render in jsdom tests.

import React from 'react';
import {
    Box,
    Checkbox,
    Chip,
    Stack,
    Table,
    TableBody,
    TableCell,
    TableHead,
    TableRow,
    TableSortLabel,
    Tooltip,
    Typography,
} from '@mui/material';
import { useTranslation } from 'react-i18next';
import type { DiscoveredDevice } from '../../Services/assetDiscoveryService';
import { categoryLabel, deviceTypeLabel, formatSeen } from './discoveryLabels';
import { sortDevices, type SortDirection, type SortKey } from './deviceSort';

interface Props {
    devices: DiscoveredDevice[];
    selectable: boolean;
    selected: Set<string>;
    onToggle: (id: string) => void;
    onToggleAll: (ids: string[]) => void;
}

/**
 * SSDP lines that say what the device IS, and what it only SEARCHED for.
 *
 * An M-SEARCH's ST is what the sender is looking for: a Windows laptop
 * searching for its router, Chrome searching for cast targets.  Agents from
 * 2026-10-17 send those apart (``ssdp_searches``) and mark a reply's ST as
 * "RST:".  Older agents mixed both into ``ssdp`` as bare "ST:" lines, so --
 * like the engine -- a bare ST counts as identity only when the device also
 * sent a SERVER line (replies and announcements carry one; searches do not).
 */
export const splitSsdp = (device: DiscoveredDevice): { identity: string[]; searches: string[] } => {
    const lines = device.evidence.ssdp ?? [];
    const replied = lines.some(line => line.toLowerCase().startsWith('server:'));
    const identity: string[] = [];
    const searches: string[] = [...(device.evidence.ssdp_searches ?? [])];
    for (const line of lines) {
        const bareSt = line.toLowerCase().startsWith('st:');
        if (bareSt && !replied) {
            const what = line.slice(3).trim();
            if (what && !searches.includes(what)) searches.push(what);
        } else {
            identity.push(line);
        }
    }
    return { identity, searches };
};

const Evidence: React.FC<{ device: DiscoveredDevice }> = ({ device }) => {
    const { t } = useTranslation();
    const { identity, searches } = splitSsdp(device);
    const items = [
        ...device.hostnames,
        ...(device.evidence.mdns_services ?? []),
        ...identity,
    ];
    if (items.length === 0 && searches.length === 0) {
        return <Typography variant="body2" color="text.secondary">-</Typography>;
    }
    return (
        <Stack direction="row" spacing={0.5} sx={{ flexWrap: 'wrap', rowGap: 0.5 }}>
            {items.slice(0, 4).map(item => <Chip key={item} size="small" variant="outlined" label={item} />)}
            {items.length > 4 && <Chip size="small" label={`+${items.length - 4}`} />}
            {searches.length > 0 && (
                <Tooltip title={t('assetDiscovery.table.searchesForHint',
                    'What this device looked for on the network (SSDP search). It describes what the device wants, not what it is.')}>
                    <Chip
                        size="small"
                        variant="outlined"
                        color="default"
                        sx={{ borderStyle: 'dashed' }}
                        label={t('assetDiscovery.table.searchesFor', 'Searches for: {{what}}', {
                            what: searches.length > 1 ? `${searches[0]} (+${searches.length - 1})` : searches[0],
                        })}
                        data-testid="ssdp-searches"
                    />
                </Tooltip>
            )}
        </Stack>
    );
};

// The engine's guess, labeled as one: "Maybe" for low confidence, reasons on hover.
const LooksLike: React.FC<{ device: DiscoveredDevice }> = ({ device }) => {
    const { t } = useTranslation();
    if (!device.device_type || device.device_type === 'unknown') return null;
    const low = device.classification?.confidence === 'low';
    const label = low
        ? t('assetDiscovery.table.maybe', 'Maybe: {{type}}', { type: deviceTypeLabel(t, device.device_type) })
        : deviceTypeLabel(t, device.device_type);
    return (
        <Tooltip title={[
            ...(device.classification?.reasons ?? []),
            // Other roles it advertises, e.g. a computer that shares a printer.
            ...(device.classification?.also ?? []).map(role => `also:${role}`),
        ].join(', ')}>
            <Chip size="small" variant={low ? 'outlined' : 'filled'} sx={{ mt: 0.5 }} label={label} />
        </Tooltip>
    );
};

const Identity: React.FC<{ device: DiscoveredDevice }> = ({ device }) => {
    const { t } = useTranslation();
    return (
        <Box>
            <Typography variant="body2" sx={{ fontFamily: 'monospace' }}>
                {device.mac ?? device.last_ip ?? device.identity}
            </Typography>
            {device.vendor && (
                <Typography variant="caption" color="text.secondary" display="block">{device.vendor}</Typography>
            )}
            <LooksLike device={device} />
            {device.mac_locally_administered && (
                <Tooltip title={t('assetDiscovery.table.localMacHelp', 'A locally administered address: phones and tablets change it, so this device may reappear under a new one.')}>
                    <Chip size="small" color="warning" variant="outlined" sx={{ mt: 0.5 }}
                        label={t('assetDiscovery.table.localMac', 'Address may change')} />
                </Tooltip>
            )}
            {device.identity_kind === 'ip' && (
                <Chip size="small" variant="outlined" sx={{ mt: 0.5 }}
                    label={t('assetDiscovery.table.ipOnly', 'No MAC seen')} />
            )}
        </Box>
    );
};

const StatusNote: React.FC<{ device: DiscoveredDevice }> = ({ device }) => {
    const { t } = useTranslation();
    if (device.status === 'managed') {
        return <Typography variant="body2">{device.managed_host_fqdn ?? '-'}</Typography>;
    }
    if (device.exclusion) {
        return (
            <Tooltip title={device.exclusion.reason}>
                <Chip size="small" label={categoryLabel(t, device.exclusion.category)} />
            </Tooltip>
        );
    }
    return <Chip size="small" color="warning" label={t('assetDiscovery.status.unmanaged', 'Unmanaged')} />;
};

interface SortState {
    key: SortKey;
    direction: SortDirection;
}

// A column header that sorts: first click ascending, the next flips it.
const SortHeader: React.FC<{
    column: SortKey;
    sort: SortState | null;
    onSort: (column: SortKey) => void;
    children: React.ReactNode;
}> = ({ column, sort, onSort, children }) => {
    const active = sort?.key === column;
    return (
        <TableCell sortDirection={active ? sort.direction : false}>
            <TableSortLabel active={active} direction={active ? sort.direction : 'asc'} onClick={() => onSort(column)}>
                {children}
            </TableSortLabel>
        </TableCell>
    );
};

const DeviceTable: React.FC<Props> = ({ devices, selectable, selected, onToggle, onToggleAll }) => {
    const { t } = useTranslation();
    // No sort until a header is clicked: the server's order (newest first) stands.
    const [sort, setSort] = React.useState<SortState | null>(null);
    const onSort = (column: SortKey) => setSort(previous => ({
        key: column,
        direction: previous?.key === column && previous.direction === 'asc' ? 'desc' : 'asc',
    }));
    const rows = React.useMemo(
        () => (sort ? sortDevices(devices, sort.key, sort.direction) : devices),
        [devices, sort],
    );
    if (devices.length === 0) {
        return (
            <Typography color="text.secondary" sx={{ py: 3 }}>
                {t('assetDiscovery.table.empty', 'No devices match.')}
            </Typography>
        );
    }
    const ids = devices.map(d => d.id);
    const allSelected = ids.every(id => selected.has(id));
    return (
        <Table size="small">
            <TableHead>
                <TableRow>
                    {selectable && (
                        <TableCell padding="checkbox">
                            <Checkbox checked={allSelected} onChange={() => onToggleAll(ids)}
                                slotProps={{ input: { 'aria-label': t('assetDiscovery.table.selectAll', 'Select all') } }} />
                        </TableCell>
                    )}
                    <SortHeader column="device" sort={sort} onSort={onSort}>{t('assetDiscovery.table.device', 'Device')}</SortHeader>
                    <SortHeader column="address" sort={sort} onSort={onSort}>{t('assetDiscovery.table.address', 'Address')}</SortHeader>
                    <TableCell>{t('assetDiscovery.table.evidence', 'What it says it is')}</TableCell>
                    <SortHeader column="seenBy" sort={sort} onSort={onSort}>{t('assetDiscovery.table.seenBy', 'Seen by')}</SortHeader>
                    <SortHeader column="lastSeen" sort={sort} onSort={onSort}>{t('assetDiscovery.table.lastSeen', 'Last seen')}</SortHeader>
                    <SortHeader column="status" sort={sort} onSort={onSort}>{t('assetDiscovery.table.status', 'Status')}</SortHeader>
                </TableRow>
            </TableHead>
            <TableBody>
                {rows.map(device => (
                    <TableRow key={device.id} hover selected={selected.has(device.id)}>
                        {selectable && (
                            <TableCell padding="checkbox">
                                <Checkbox checked={selected.has(device.id)} onChange={() => onToggle(device.id)}
                                    slotProps={{ input: { 'aria-label': device.identity } }} />
                            </TableCell>
                        )}
                        <TableCell><Identity device={device} /></TableCell>
                        <TableCell>
                            <Typography variant="body2">{device.last_ip ?? '-'}</Typography>
                            <Typography variant="caption" color="text.secondary">{device.networks.join(', ')}</Typography>
                        </TableCell>
                        <TableCell><Evidence device={device} /></TableCell>
                        <TableCell><Typography variant="body2">{device.observers.join(', ') || '-'}</Typography></TableCell>
                        <TableCell><Typography variant="body2">{formatSeen(device.last_seen_at)}</Typography></TableCell>
                        <TableCell><StatusNote device={device} /></TableCell>
                    </TableRow>
                ))}
            </TableBody>
        </Table>
    );
};

export default DeviceTable;
