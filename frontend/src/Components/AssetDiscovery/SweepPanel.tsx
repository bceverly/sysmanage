// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

// Active sweeps (Phase 21.6 S4): the one discovery method that puts traffic
// on a network, so it is requested explicitly, one network at a time, and
// every run -- refused and timed-out ones included -- stays in the history.

import React, { useState } from 'react';
import {
    Alert,
    Button,
    Chip,
    Dialog,
    DialogActions,
    DialogContent,
    DialogTitle,
    FormControl,
    InputLabel,
    MenuItem,
    Select,
    Table,
    TableBody,
    TableCell,
    TableHead,
    TableRow,
    Typography,
} from '@mui/material';
import { useTranslation } from 'react-i18next';
import type { TFunction } from 'i18next';
import { SWEEP_RATES, type SweepRun, type SweepStatus } from '../../Services/assetDiscoveryService';
import { formatSeen } from './discoveryLabels';

interface Props {
    runs: SweepRun[];
    networks: string[];
    allowed: boolean;
    canManage: boolean;
    onSweep: (cidr: string, rate: number) => Promise<void>;
}

const statusLabel = (t: TFunction, status: SweepStatus): string => {
    const labels: Record<SweepStatus, string> = {
        queued: t('assetDiscovery.sweep.status.queued', 'Waiting for the agent'),
        completed: t('assetDiscovery.sweep.status.completed', 'Completed'),
        refused: t('assetDiscovery.sweep.status.refused', 'Refused by the agent'),
        failed: t('assetDiscovery.sweep.status.failed', 'Failed'),
        timed_out: t('assetDiscovery.sweep.status.timedOut', 'No answer from the agent'),
    };
    return labels[status] ?? status;
};

const STATUS_COLOR: Record<SweepStatus, 'default' | 'success' | 'warning' | 'error'> = {
    queued: 'default',
    completed: 'success',
    refused: 'warning',
    failed: 'error',
    timed_out: 'error',
};

const SweepDialog: React.FC<{
    open: boolean;
    networks: string[];
    onClose: () => void;
    onSweep: (cidr: string, rate: number) => Promise<void>;
}> = ({ open, networks, onClose, onSweep }) => {
    const { t } = useTranslation();
    const [cidr, setCidr] = useState(networks[0] ?? '');
    const [rate, setRate] = useState<number>(50);
    const [error, setError] = useState<string | null>(null);
    const [busy, setBusy] = useState(false);

    const submit = async () => {
        setBusy(true);
        setError(null);
        try {
            await onSweep(cidr, rate);
            onClose();
        } catch (err: unknown) {
            const detail = (err as { response?: { data?: { detail?: { message?: string } } } })?.response?.data?.detail;
            setError(detail?.message ?? t('assetDiscovery.sweep.error', 'The sweep could not be started.'));
        } finally {
            setBusy(false);
        }
    };

    return (
        <Dialog open={open} onClose={onClose} fullWidth maxWidth="sm">
            <DialogTitle>{t('assetDiscovery.sweep.title', 'Sweep a network')}</DialogTitle>
            <DialogContent>
                <Typography variant="body2" sx={{ mb: 2 }}>
                    {t('assetDiscovery.sweep.intro', 'An agent on the network sends one small packet to every address, then reports every device that answered. This finds devices that never announce themselves, and it is recorded with your name.')}
                </Typography>
                <FormControl fullWidth size="small" sx={{ mb: 2 }}>
                    <InputLabel id="sweep-network">{t('assetDiscovery.filters.network', 'Network')}</InputLabel>
                    <Select labelId="sweep-network" value={cidr} label={t('assetDiscovery.filters.network', 'Network')}
                        onChange={e => setCidr(String(e.target.value))}>
                        {networks.map(n => <MenuItem key={n} value={n}>{n}</MenuItem>)}
                    </Select>
                </FormControl>
                <FormControl fullWidth size="small">
                    <InputLabel id="sweep-rate">{t('assetDiscovery.sweep.rate', 'Speed')}</InputLabel>
                    <Select labelId="sweep-rate" value={rate} label={t('assetDiscovery.sweep.rate', 'Speed')}
                        onChange={e => setRate(Number(e.target.value))}>
                        {SWEEP_RATES.map(r => (
                            <MenuItem key={r} value={r}>
                                {t('assetDiscovery.sweep.perSecond', '{{count}} addresses per second', { count: r })}
                            </MenuItem>
                        ))}
                    </Select>
                </FormControl>
                {error && <Alert severity="error" sx={{ mt: 2 }}>{error}</Alert>}
            </DialogContent>
            <DialogActions>
                <Button onClick={onClose}>{t('common.cancel', 'Cancel')}</Button>
                <Button variant="contained" disabled={!cidr || busy} onClick={submit}>
                    {t('assetDiscovery.sweep.start', 'Start sweep')}
                </Button>
            </DialogActions>
        </Dialog>
    );
};

const SweepPanel: React.FC<Props> = ({ runs, networks, allowed, canManage, onSweep }) => {
    const { t } = useTranslation();
    const [open, setOpen] = useState(false);
    return (
        <>
            {!allowed && (
                <Alert severity="info" sx={{ mb: 2 }}>
                    {t('assetDiscovery.sweep.disabled', 'Active sweeps are turned off. Allow them in the settings above to find devices that never announce themselves.')}
                </Alert>
            )}
            {allowed && canManage && (
                <Button variant="outlined" sx={{ mb: 2 }} disabled={networks.length === 0} onClick={() => setOpen(true)}>
                    {t('assetDiscovery.sweep.title', 'Sweep a network')}
                </Button>
            )}
            {runs.length === 0 ? (
                <Typography color="text.secondary" sx={{ py: 3 }}>
                    {t('assetDiscovery.sweep.none', 'No network has been swept yet.')}
                </Typography>
            ) : (
                <Table size="small">
                    <TableHead>
                        <TableRow>
                            <TableCell>{t('assetDiscovery.filters.network', 'Network')}</TableCell>
                            <TableCell>{t('assetDiscovery.table.status', 'Status')}</TableCell>
                            <TableCell>{t('assetDiscovery.sweep.found', 'Found')}</TableCell>
                            <TableCell>{t('assetDiscovery.sweep.agent', 'Swept by')}</TableCell>
                            <TableCell>{t('assetDiscovery.sweep.requestedBy', 'Requested by')}</TableCell>
                        </TableRow>
                    </TableHead>
                    <TableBody>
                        {runs.map(run => (
                            <TableRow key={run.id}>
                                <TableCell sx={{ fontFamily: 'monospace' }}>{run.cidr}</TableCell>
                                <TableCell>
                                    <Chip size="small" color={STATUS_COLOR[run.status]} label={statusLabel(t, run.status)} />
                                    {run.reason && (
                                        <Typography variant="caption" display="block" color="text.secondary">{run.reason}</Typography>
                                    )}
                                </TableCell>
                                <TableCell>
                                    {run.status === 'completed'
                                        ? t('assetDiscovery.sweep.foundOf', '{{found}} of {{probed}} addresses', { found: run.devices_found ?? 0, probed: run.probed ?? 0 })
                                        : '-'}
                                </TableCell>
                                <TableCell>{run.agent_fqdn ?? '-'}</TableCell>
                                <TableCell>
                                    {run.requested_by}
                                    <Typography variant="caption" display="block" color="text.secondary">{formatSeen(run.requested_at)}</Typography>
                                </TableCell>
                            </TableRow>
                        ))}
                    </TableBody>
                </Table>
            )}
            {open && <SweepDialog open={open} networks={networks} onClose={() => setOpen(false)} onSweep={onSweep} />}
        </>
    );
};

export default SweepPanel;
