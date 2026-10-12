// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

// Time synchronization (Phase 23.3 S4): every host's clock, measured by the
// server, against its bounds -- worst first.  The server's own clock comes
// first, because every offset here is relative to it.

import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
    Alert,
    Box,
    Chip,
    CircularProgress,
    FormControl,
    InputLabel,
    MenuItem,
    Select,
    Stack,
    TextField,
    Typography,
} from '@mui/material';
import { useTranslation } from 'react-i18next';
import { getFleetClocks, STATUS_ORDER } from '../Services/timeSync';
import type { ClockStatus, FleetClock, FleetClocks } from '../Services/timeSync';
import ServerClockBanner from '../Components/TimeSync/ServerClockBanner';
import FleetClockGrid from '../Components/TimeSync/FleetClockGrid';
import FleetResyncButton from '../Components/TimeSync/FleetResyncButton';
import { statusColor, statusLabel } from '../Components/TimeSync/timeSyncLabels';
import { useVisiblePolling } from '../hooks/useVisiblePolling';

const ALL = '';

interface Filters {
    status: ClockStatus | typeof ALL;
    site: string;
    tag: string;
    search: string;
}

const matches = (row: FleetClock, f: Filters): boolean =>
    (!f.status || row.status === f.status)
    && (!f.site || row.site_id === f.site)
    && (!f.tag || row.tags.some(tag => tag.id === f.tag))
    && (!f.search || row.fqdn.toLowerCase().includes(f.search.toLowerCase()));

/** Distinct ``{id, name}`` pairs, sorted by name. */
const distinct = (pairs: { id: string; name: string }[]) =>
    Array.from(new Map(pairs.map(p => [p.id, p])).values()).sort((a, b) => a.name.localeCompare(b.name));

const TimeSync: React.FC = () => {
    const { t } = useTranslation();
    const [data, setData] = useState<FleetClocks | null>(null);
    const [error, setError] = useState(false);
    const [filters, setFilters] = useState<Filters>({ status: ALL, site: '', tag: '', search: '' });

    const load = useCallback(async () => {
        try {
            setData(await getFleetClocks());
            setError(false);
        } catch {
            setError(true);
        }
    }, []);

    useEffect(() => {
        void load();
    }, [load]);
    useVisiblePolling(load, 60000, true);

    const sites = useMemo(
        () => distinct((data?.hosts ?? [])
            .filter(h => h.site_id)
            .map(h => ({ id: h.site_id as string, name: h.site_name ?? h.site_id as string }))),
        [data],
    );
    const tags = useMemo(() => distinct((data?.hosts ?? []).flatMap(h => h.tags)), [data]);
    const rows = useMemo(() => (data?.hosts ?? []).filter(r => matches(r, filters)), [data, filters]);

    const set = (patch: Partial<Filters>) => setFilters(f => ({ ...f, ...patch }));

    if (!data) {
        return error ? (
            <Alert severity="error">{t('timeSync.loadError', 'Could not load the fleet clocks.')}</Alert>
        ) : (
            <Box display="flex" justifyContent="center" sx={{ mt: 4 }}><CircularProgress /></Box>
        );
    }

    return (
        <Box>
            <Typography variant="h5" sx={{ mb: 2 }}>{t('timeSync.title', 'Time Sync')}</Typography>
            <ServerClockBanner server={data.server} />
            <Box sx={{ mb: 2 }}>
                <FleetResyncButton data={data} onDone={() => void load()} />
            </Box>
            <Stack direction="row" spacing={1} sx={{ mb: 2, flexWrap: 'wrap', rowGap: 1 }}>
                {STATUS_ORDER.filter(s => data.counts[s]).map(s => (
                    <Chip
                        key={s}
                        color={statusColor(s)}
                        variant={filters.status === s ? 'filled' : 'outlined'}
                        label={`${statusLabel(t, s)}: ${data.counts[s]}`}
                        onClick={() => set({ status: filters.status === s ? ALL : s })}
                    />
                ))}
            </Stack>
            <Stack direction={{ xs: 'column', md: 'row' }} spacing={2} sx={{ mb: 2 }}>
                <TextField
                    size="small"
                    label={t('timeSync.filter.search', 'Host')}
                    value={filters.search}
                    onChange={e => set({ search: e.target.value })}
                />
                <FormControl size="small" sx={{ minWidth: 200 }}>
                    <InputLabel id="time-sync-status">{t('timeSync.filter.status', 'Status')}</InputLabel>
                    <Select
                        labelId="time-sync-status"
                        label={t('timeSync.filter.status', 'Status')}
                        value={filters.status}
                        onChange={e => set({ status: e.target.value as Filters['status'] })}
                    >
                        <MenuItem value={ALL}>{t('timeSync.filter.all', 'All')}</MenuItem>
                        {STATUS_ORDER.map(s => <MenuItem key={s} value={s}>{statusLabel(t, s)}</MenuItem>)}
                    </Select>
                </FormControl>
                {sites.length > 0 && (
                    <FormControl size="small" sx={{ minWidth: 200 }}>
                        <InputLabel id="time-sync-site">{t('timeSync.filter.site', 'Site')}</InputLabel>
                        <Select
                            labelId="time-sync-site"
                            label={t('timeSync.filter.site', 'Site')}
                            value={filters.site}
                            onChange={e => set({ site: e.target.value })}
                        >
                            <MenuItem value="">{t('timeSync.filter.all', 'All')}</MenuItem>
                            {sites.map(s => <MenuItem key={s.id} value={s.id}>{s.name}</MenuItem>)}
                        </Select>
                    </FormControl>
                )}
                {tags.length > 0 && (
                    <FormControl size="small" sx={{ minWidth: 200 }}>
                        <InputLabel id="time-sync-tag">{t('timeSync.filter.tag', 'Tag')}</InputLabel>
                        <Select
                            labelId="time-sync-tag"
                            label={t('timeSync.filter.tag', 'Tag')}
                            value={filters.tag}
                            onChange={e => set({ tag: e.target.value })}
                        >
                            <MenuItem value="">{t('timeSync.filter.all', 'All')}</MenuItem>
                            {tags.map(tag => <MenuItem key={tag.id} value={tag.id}>{tag.name}</MenuItem>)}
                        </Select>
                    </FormControl>
                )}
            </Stack>
            {data.hosts.length === 0 ? (
                <Alert severity="info">{t('timeSync.empty', 'There are no approved hosts yet.')}</Alert>
            ) : (
                <FleetClockGrid rows={rows} />
            )}
        </Box>
    );
};

export default TimeSync;
