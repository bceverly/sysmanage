// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

// A host's hardware (Phase 23.1 S4): its drives, arrays, pools and memory
// with their state and why, the sensors (healthy ones folded away -- a
// laptop reports 30 of them), which sources the agent could read, and the
// recent events.

import React, { useCallback, useEffect, useState } from 'react';
import {
    Alert,
    Box,
    Button,
    Card,
    CardContent,
    Chip,
    CircularProgress,
    Stack,
    Table,
    TableBody,
    TableCell,
    TableRow,
    Tooltip,
    Typography,
} from '@mui/material';
import MemoryIcon from '@mui/icons-material/Memory';
import { useTranslation } from 'react-i18next';
import { getHostHardware } from '../../Services/hardwareHealth';
import type { HardwareComponent, HostHardware } from '../../Services/hardwareHealth';
import HardwareEventsList from './HardwareEventsList';
import { HostSmartmontools } from './SmartmontoolsRecommendation';
import TemperatureLimitControl from './TemperatureLimitControl';
import {
    kindLabel,
    metricsText,
    reasonsText,
    sourceStatusLabel,
    statusColor,
    statusHelp,
    statusLabel,
} from './hardwareHealthLabels';

const ComponentRows: React.FC<{ rows: HardwareComponent[] }> = ({ rows }) => {
    const { t } = useTranslation();
    return (
        <Table size="small">
            <TableBody>
                {rows.map(c => (
                    <TableRow key={`${c.kind}/${c.id}`}>
                        <TableCell sx={{ whiteSpace: 'nowrap' }}>{kindLabel(t, c.kind)}</TableCell>
                        <TableCell>
                            <Typography variant="body2">{c.name}</Typography>
                            <Typography variant="caption" color="text.secondary">
                                {metricsText(t, c.metrics)}
                            </Typography>
                        </TableCell>
                        <TableCell>
                            <Chip size="small" color={statusColor(c.state)} label={statusLabel(t, c.state)} />
                        </TableCell>
                        <TableCell>{reasonsText(t, c.reasons)}</TableCell>
                    </TableRow>
                ))}
            </TableBody>
        </Table>
    );
};

const Sources: React.FC<{ hardware: HostHardware }> = ({ hardware }) => {
    const { t } = useTranslation();
    if (hardware.sources.length === 0) {
        return null;
    }
    return (
        <Stack direction="row" spacing={1} sx={{ mt: 2, flexWrap: 'wrap', rowGap: 1 }} alignItems="center">
            <Typography variant="caption" color="text.secondary">
                {t('hardwareHealth.card.sources', 'Sources:')}
            </Typography>
            {hardware.sources.map(s => (
                <Tooltip key={s.name} title={s.detail ?? ''}>
                    <Chip
                        size="small"
                        variant="outlined"
                        color={s.status === 'failed' ? 'warning' : 'default'}
                        label={`${s.name}: ${sourceStatusLabel(t, s)}`}
                    />
                </Tooltip>
            ))}
        </Stack>
    );
};

const Body: React.FC<{ hostId: string; hardware: HostHardware; onChanged: () => void }> = ({
    hostId,
    hardware,
    onChanged,
}) => {
    const { t } = useTranslation();
    const [showSensors, setShowSensors] = useState(false);
    const isQuietSensor = (c: HardwareComponent) => c.kind === 'sensor' && c.state === 'ok';
    const main = hardware.components.filter(c => !isQuietSensor(c));
    const quiet = hardware.components.filter(isQuietSensor);
    if (hardware.status === 'unmeasured') {
        return <Alert severity="info">{statusHelp(t, 'unmeasured')}</Alert>;
    }
    return (
        <>
            <HostSmartmontools
                hostId={hostId}
                recommended={Boolean(hardware.smartmontools?.recommended)}
                install={hardware.smartmontools?.install ?? null}
                onChanged={onChanged}
            />
            {main.length > 0 && <ComponentRows rows={main} />}
            {quiet.length > 0 && (
                <Box sx={{ mt: 1 }}>
                    <Button size="small" onClick={() => setShowSensors(v => !v)}>
                        {showSensors
                            ? t('hardwareHealth.card.hideSensors', 'Hide healthy sensors')
                            : t('hardwareHealth.card.showSensors', 'Show {{n}} healthy sensors', { n: quiet.length })}
                    </Button>
                    {showSensors && <ComponentRows rows={quiet} />}
                </Box>
            )}
            <Sources hardware={hardware} />
            {hardware.components.some(c => c.kind === 'sensor') && (
                <TemperatureLimitControl
                    hostId={hostId}
                    limit={hardware.temperature_limit_c ?? null}
                    onChanged={onChanged}
                />
            )}
            <Typography variant="subtitle2" sx={{ mt: 2, mb: 1 }}>
                {t('hardwareHealth.card.recentEvents', 'Recent events')}
            </Typography>
            <HardwareEventsList
                events={hardware.events.slice(0, 10)}
                total={hardware.events.filter(e => !e.resolved_at).length}
                hostId={hostId}
                onChanged={onChanged}
            />
        </>
    );
};

const HostHardwareCard: React.FC<{ hostId: string }> = ({ hostId }) => {
    const { t } = useTranslation();
    const [hardware, setHardware] = useState<HostHardware | null>(null);
    const [error, setError] = useState(false);

    const load = useCallback(async () => {
        try {
            setHardware(await getHostHardware(hostId));
            setError(false);
        } catch {
            setError(true);
        }
    }, [hostId]);

    useEffect(() => {
        void load();
    }, [load]);

    return (
        <Card sx={{ mt: 2 }}>
            <CardContent>
                <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 2 }}>
                    <MemoryIcon />
                    <Typography variant="h6">{t('hardwareHealth.card.title', 'Hardware health')}</Typography>
                    {hardware && (
                        <Tooltip title={statusHelp(t, hardware.status)}>
                            <Chip size="small" color={statusColor(hardware.status)} label={statusLabel(t, hardware.status)} />
                        </Tooltip>
                    )}
                    {hardware?.reported_at && (
                        <Typography variant="caption" color="text.secondary">
                            {t('hardwareHealth.card.reportedAt', 'Reported {{when}}', {
                                when: new Date(`${hardware.reported_at}Z`).toLocaleString(),
                            })}
                        </Typography>
                    )}
                </Stack>
                {error && <Alert severity="error">{t('hardwareHealth.card.loadError', 'Could not load the hardware health.')}</Alert>}
                {!error && !hardware && <CircularProgress size={24} />}
                {hardware && <Body hostId={hostId} hardware={hardware} onChanged={() => void load()} />}
            </CardContent>
        </Card>
    );
};

export default HostHardwareCard;
