// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

// Hardware health (Phase 23.1 S4): every host's drives, arrays, pools,
// sensors and memory as its agent judged them -- worst first -- and the open
// events: what changed, and whether someone has it in hand.

import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
    Alert,
    Box,
    Chip,
    CircularProgress,
    FormControl,
    InputLabel,
    MenuItem,
    Paper,
    Select,
    Stack,
    TextField,
    Typography,
} from '@mui/material';
import { useTranslation } from 'react-i18next';
import { getFleetHardware, getHardwareEventsPage, STATUS_ORDER } from '../Services/hardwareHealth';
import type { FleetHardware, FleetHost, HardwareEvent, HardwareStatus } from '../Services/hardwareHealth';
import FleetHardwareGrid from '../Components/HardwareHealth/FleetHardwareGrid';
import HardwareEventsList from '../Components/HardwareHealth/HardwareEventsList';
import { FleetSmartmontools } from '../Components/HardwareHealth/SmartmontoolsRecommendation';
import { statusColor, statusLabel } from '../Components/HardwareHealth/hardwareHealthLabels';
import { useVisiblePolling } from '../hooks/useVisiblePolling';

const ALL = '';

interface Filters {
    status: HardwareStatus | typeof ALL;
    site: string;
    tag: string;
    search: string;
}

const matches = (row: FleetHost, f: Filters): boolean =>
    (!f.status || row.status === f.status)
    && (!f.site || row.site_id === f.site)
    && (!f.tag || row.tags.some(tag => tag.id === f.tag))
    && (!f.search || row.fqdn.toLowerCase().includes(f.search.toLowerCase()));

/** Distinct ``{id, name}`` pairs, sorted by name. */
const distinct = (pairs: { id: string; name: string }[]) =>
    Array.from(new Map(pairs.map(p => [p.id, p])).values()).sort((a, b) => a.name.localeCompare(b.name));

const PickOne: React.FC<{
    id: string;
    label: string;
    value: string;
    options: { id: string; name: string }[];
    onChange: (value: string) => void;
}> = ({ id, label, value, options, onChange }) => {
    const { t } = useTranslation();
    return (
        <FormControl size="small" sx={{ minWidth: 200 }}>
            <InputLabel id={id}>{label}</InputLabel>
            <Select labelId={id} label={label} value={value} onChange={e => onChange(e.target.value)}>
                <MenuItem value="">{t('hardwareHealth.filter.all', 'All')}</MenuItem>
                {options.map(o => <MenuItem key={o.id} value={o.id}>{o.name}</MenuItem>)}
            </Select>
        </FormControl>
    );
};

const HardwareHealth: React.FC = () => {
    const { t } = useTranslation();
    const [data, setData] = useState<FleetHardware | null>(null);
    const [events, setEvents] = useState<HardwareEvent[]>([]);
    const [openTotal, setOpenTotal] = useState(0);
    const [error, setError] = useState(false);
    const [filters, setFilters] = useState<Filters>({ status: ALL, site: '', tag: '', search: '' });

    const load = useCallback(async () => {
        try {
            const [fleet, open] = await Promise.all([getFleetHardware(), getHardwareEventsPage()]);
            setData(fleet);
            setEvents(open.events);
            setOpenTotal(open.total);
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
            <Alert severity="error">{t('hardwareHealth.loadError', 'Could not load the fleet hardware.')}</Alert>
        ) : (
            <Box display="flex" justifyContent="center" sx={{ mt: 4 }}><CircularProgress /></Box>
        );
    }

    const statuses = STATUS_ORDER.map(s => ({ id: s, name: statusLabel(t, s) }));
    return (
        <Box>
            <Typography variant="h5" sx={{ mb: 2 }}>{t('hardwareHealth.title', 'Hardware Health')}</Typography>
            <FleetSmartmontools onChanged={() => void load()} />
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
                    label={t('hardwareHealth.filter.search', 'Host')}
                    value={filters.search}
                    onChange={e => set({ search: e.target.value })}
                />
                <PickOne
                    id="hardware-status"
                    label={t('hardwareHealth.filter.status', 'Status')}
                    value={filters.status}
                    options={statuses}
                    onChange={v => set({ status: v as Filters['status'] })}
                />
                {sites.length > 0 && (
                    <PickOne id="hardware-site" label={t('hardwareHealth.filter.site', 'Site')}
                        value={filters.site} options={sites} onChange={v => set({ site: v })} />
                )}
                {tags.length > 0 && (
                    <PickOne id="hardware-tag" label={t('hardwareHealth.filter.tag', 'Tag')}
                        value={filters.tag} options={tags} onChange={v => set({ tag: v })} />
                )}
            </Stack>
            {data.hosts.length === 0 ? (
                <Alert severity="info">{t('hardwareHealth.empty', 'There are no approved hosts yet.')}</Alert>
            ) : (
                <FleetHardwareGrid rows={rows} />
            )}
            <Paper variant="outlined" sx={{ mt: 3, p: 2 }}>
                <Typography variant="h6" sx={{ mb: 1 }}>
                    {t('hardwareHealth.events.openTitle', 'Unresolved events')}
                </Typography>
                <HardwareEventsList events={events} total={openTotal} showHost onChanged={() => void load()} />
            </Paper>
        </Box>
    );
};

export default HardwareHealth;
