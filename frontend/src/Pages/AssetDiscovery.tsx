// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

// Unenrolled asset discovery (Phase 21.6 S3): what is on the network that
// SysManage does not manage.  The one rule this page must not break: the
// list is shown WITH its blind spots.  Passive listening cannot see a silent
// device, some agents cannot listen for ARP, and an agent that stops
// reporting sees nothing -- a list without those reads as "all of them".

import React, { useCallback, useEffect, useState } from 'react';
import {
    Alert,
    Box,
    Button,
    Card,
    CardContent,
    Chip,
    CircularProgress,
    FormControl,
    InputLabel,
    MenuItem,
    Select,
    Stack,
    Tab,
    Tabs,
    TextField,
    Typography,
} from '@mui/material';
import { useTranslation } from 'react-i18next';
import {
    assetDiscoveryService,
    type DeviceStatus,
    type DiscoveredDevice,
    type DiscoverySummary,
    type Exclusion,
    type ExclusionCategory,
    type SweepRun,
} from '../Services/assetDiscoveryService';
import { hasPermission, SecurityRoles } from '../Services/permissions';
import BlindSpots from '../Components/AssetDiscovery/BlindSpots';
import DeviceTable from '../Components/AssetDiscovery/DeviceTable';
import ExcludeDialog from '../Components/AssetDiscovery/ExcludeDialog';
import ExclusionList from '../Components/AssetDiscovery/ExclusionList';
import DiscoveryPolicyCard from '../Components/AssetDiscovery/DiscoveryPolicyCard';
import SweepPanel from '../Components/AssetDiscovery/SweepPanel';
import { categoryForType, deviceTypeLabel } from '../Components/AssetDiscovery/discoveryLabels';

type View = Exclude<DeviceStatus, 'all'> | 'sweeps';
const TABS: View[] = ['unmanaged', 'managed', 'excluded', 'sweeps'];

const observedNetworks = (summary: DiscoverySummary): string[] =>
    Array.from(new Set(summary.observers.flatMap(o => o.networks.map(n => n.network))))
        .sort((a, b) => a.localeCompare(b, undefined, { numeric: true }));

const Counts: React.FC<{ summary: DiscoverySummary }> = ({ summary }) => {
    const { t } = useTranslation();
    return (
        <Card variant="outlined" sx={{ mb: 2 }}>
            <CardContent>
                <Stack direction="row" spacing={1} sx={{ flexWrap: 'wrap', rowGap: 1 }}>
                    <Chip color="warning" label={t('assetDiscovery.counts.unmanaged', '{{count}} unmanaged', { count: summary.counts.unmanaged })} />
                    <Chip variant="outlined" label={t('assetDiscovery.counts.managed', '{{count}} managed', { count: summary.counts.managed })} />
                    <Chip variant="outlined" label={t('assetDiscovery.counts.excluded', '{{count}} known and fine', { count: summary.counts.excluded })} />
                </Stack>
                {Object.keys(summary.types ?? {}).length > 0 && (
                    <Stack direction="row" spacing={1} sx={{ mt: 1, flexWrap: 'wrap', rowGap: 1 }}>
                        {Object.entries(summary.types ?? {})
                            .sort((a, b) => b[1] - a[1])
                            .map(([kind, count]) => (
                                <Chip key={kind} size="small" variant="outlined"
                                    label={`${deviceTypeLabel(t, kind)}: ${count}`} />
                            ))}
                    </Stack>
                )}
                {summary.networks.length > 0 && (
                    <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>
                        {summary.networks
                            .map(n => t('assetDiscovery.counts.onNetwork', '{{count}} on {{network}}', { count: n.unmanaged, network: n.network }))
                            .join(' - ')}
                    </Typography>
                )}
            </CardContent>
        </Card>
    );
};

const Filters: React.FC<{
    summary: DiscoverySummary;
    network: string;
    search: string;
    onNetwork: (value: string) => void;
    onSearch: (value: string) => void;
}> = ({ summary, network, search, onNetwork, onSearch }) => {
    const { t } = useTranslation();
    return (
        <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2} sx={{ mb: 2 }}>
            <FormControl size="small" sx={{ minWidth: 220 }}>
                <InputLabel id="discovery-network">{t('assetDiscovery.filters.network', 'Network')}</InputLabel>
                <Select labelId="discovery-network" value={network}
                    label={t('assetDiscovery.filters.network', 'Network')}
                    onChange={e => onNetwork(String(e.target.value))}>
                    <MenuItem value="">{t('assetDiscovery.filters.allNetworks', 'All networks')}</MenuItem>
                    {summary.networks.map(n => <MenuItem key={n.network} value={n.network}>{n.network}</MenuItem>)}
                </Select>
            </FormControl>
            <TextField size="small" sx={{ minWidth: 260 }}
                label={t('assetDiscovery.filters.search', 'Search MAC or IP address')}
                value={search} onChange={e => onSearch(e.target.value)} />
        </Stack>
    );
};

const AssetDiscovery: React.FC = () => {
    const { t } = useTranslation();
    const [tab, setTab] = useState(0);
    const [summary, setSummary] = useState<DiscoverySummary | null>(null);
    const [devices, setDevices] = useState<DiscoveredDevice[]>([]);
    const [total, setTotal] = useState(0);
    const [exclusions, setExclusions] = useState<Exclusion[]>([]);
    const [sweeps, setSweeps] = useState<SweepRun[]>([]);
    const [showRevoked, setShowRevoked] = useState(false);
    const [network, setNetwork] = useState('');
    const [search, setSearch] = useState('');
    const [selected, setSelected] = useState<Set<string>>(new Set());
    const [excluding, setExcluding] = useState(false);
    const [canManage, setCanManage] = useState(false);
    const [error, setError] = useState(false);
    const [notice, setNotice] = useState<string | null>(null);
    const status = TABS[tab];

    useEffect(() => {
        hasPermission(SecurityRoles.MANAGE_NETWORK_DISCOVERY).then(setCanManage).catch(() => setCanManage(false));
    }, []);

    const load = useCallback(async () => {
        setError(false);
        try {
            const [nextSummary, page] = await Promise.all([
                assetDiscoveryService.getSummary(),
                status === 'excluded' || status === 'sweeps'
                    ? Promise.resolve({ total: 0, devices: [] as DiscoveredDevice[] })
                    : assetDiscoveryService.listDevices({ status, network: network || undefined, search: search || undefined }),
            ]);
            setSummary(nextSummary);
            setDevices(page.devices);
            setTotal(page.total);
            if (status === 'excluded') {
                setExclusions(await assetDiscoveryService.listExclusions(showRevoked));
            }
            if (status === 'sweeps') {
                setSweeps(await assetDiscoveryService.listSweeps());
            }
        } catch {
            setError(true);
        }
    }, [status, network, search, showRevoked]);

    useEffect(() => { void load(); }, [load]);
    useEffect(() => { setSelected(new Set()); }, [status, network, search]);

    const toggle = (id: string) => setSelected(prev => {
        const next = new Set(prev);
        if (next.has(id)) next.delete(id); else next.add(id);
        return next;
    });
    const toggleAll = (ids: string[]) =>
        setSelected(prev => (ids.every(id => prev.has(id)) ? new Set() : new Set(ids)));

    const exclude = async (category: ExclusionCategory, reason: string) => {
        const result = await assetDiscoveryService.exclude(Array.from(selected), category, reason);
        setExcluding(false);
        setSelected(new Set());
        setNotice(t('assetDiscovery.exclude.done', '{{count}} devices marked as known.', { count: result.excluded }));
        await load();
    };

    const revoke = async (id: string, reason: string) => {
        await assetDiscoveryService.revoke(id, reason);
        await load();
    };

    const savePolicy = async (enabled: boolean, interval: number, sweepEnabled: boolean, retentionDays: number) => {
        await assetDiscoveryService.setPolicy(enabled, interval, sweepEnabled, retentionDays);
        await load();
    };

    const addAddress = async (address: string, category: ExclusionCategory, reason: string) => {
        await assetDiscoveryService.excludeAddress(address, category, reason);
        await load();
    };

    // The category the selection's guessed type suggests -- only when they agree.
    const suggested = (() => {
        const kinds = new Set(devices.filter(d => selected.has(d.id)).map(d => categoryForType(d.device_type)));
        return kinds.size === 1 ? Array.from(kinds)[0] : null;
    })();

    const sweep = async (cidr: string, rate: number) => {
        await assetDiscoveryService.requestSweep(cidr, rate);
        await load();
    };

    if (error && !summary) {
        return <Alert severity="error" sx={{ m: 2 }}>{t('assetDiscovery.loadError', 'Discovered devices could not be loaded.')}</Alert>;
    }
    if (!summary) return <CircularProgress sx={{ m: 2 }} />;

    return (
        <Box sx={{ p: 2 }}>
            <Typography variant="h5">{t('assetDiscovery.title', 'Network Discovery')}</Typography>
            <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
                {t('assetDiscovery.subtitle', 'Devices your agents see on their networks that SysManage does not manage.')}
            </Typography>
            <DiscoveryPolicyCard key={summary.policy.updated_at ?? 'never'} policy={summary.policy}
                canManage={canManage} onSave={savePolicy} />
            <BlindSpots summary={summary} />
            <Counts summary={summary} />
            {notice && <Alert severity="success" sx={{ mb: 2 }} onClose={() => setNotice(null)}>{notice}</Alert>}
            <Tabs value={tab} onChange={(_e, value) => setTab(value)} sx={{ mb: 2 }}>
                <Tab label={t('assetDiscovery.tabs.unmanaged', 'Unmanaged')} />
                <Tab label={t('assetDiscovery.tabs.managed', 'Managed')} />
                <Tab label={t('assetDiscovery.tabs.excluded', 'Known and fine')} />
                <Tab label={t('assetDiscovery.tabs.sweeps', 'Sweeps')} />
            </Tabs>
            {status === 'sweeps' && (
                <SweepPanel runs={sweeps} networks={observedNetworks(summary)}
                    allowed={summary.policy.enabled && summary.policy.sweep_enabled}
                    canManage={canManage} onSweep={sweep} />
            )}
            {status === 'excluded' && (
                <ExclusionList exclusions={exclusions} showRevoked={showRevoked} canManage={canManage}
                    onShowRevoked={setShowRevoked} onRevoke={revoke} onAddAddress={addAddress} />
            )}
            {(status === 'unmanaged' || status === 'managed') && (
                <>
                    <Filters summary={summary} network={network} search={search} onNetwork={setNetwork} onSearch={setSearch} />
                    {status === 'unmanaged' && canManage && (
                        <Button variant="outlined" sx={{ mb: 1 }} disabled={selected.size === 0} onClick={() => setExcluding(true)}>
                            {t('assetDiscovery.exclude.action', 'Mark {{count}} as known and fine', { count: selected.size })}
                        </Button>
                    )}
                    <DeviceTable devices={devices} selectable={status === 'unmanaged' && canManage}
                        selected={selected} onToggle={toggle} onToggleAll={toggleAll} />
                    {total > devices.length && (
                        <Typography variant="caption" color="text.secondary">
                            {t('assetDiscovery.table.more', 'Showing {{shown}} of {{total}}. Narrow the list with the filters above.', { shown: devices.length, total })}
                        </Typography>
                    )}
                </>
            )}
            {excluding && (
                <ExcludeDialog open={excluding} count={selected.size} suggested={suggested}
                    onClose={() => setExcluding(false)} onConfirm={exclude} />
            )}
        </Box>
    );
};

export default AssetDiscovery;
