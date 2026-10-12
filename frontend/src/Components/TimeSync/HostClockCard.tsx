// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

// The host's clock (Phase 23.3 S4): what the SERVER measured, what the
// host's own time service claims, and the measured offset over 7 days.  The
// two are kept side by side so a service that says "synchronized" on a clock
// measured seconds off stays visible.

import React, { useCallback, useEffect, useState } from 'react';
import {
    Alert,
    Box,
    Card,
    CardContent,
    Chip,
    CircularProgress,
    Grid,
    Stack,
    Tooltip,
    Typography,
} from '@mui/material';
import AccessTimeIcon from '@mui/icons-material/AccessTime';
import { LineChart } from '@mui/x-charts/LineChart';
import { ChartsReferenceLine } from '@mui/x-charts/ChartsReferenceLine';
import { useTranslation } from 'react-i18next';
import type { TFunction } from 'i18next';
import { getHostClock } from '../../Services/timeSync';
import type { HostClock, TimeService } from '../../Services/timeSync';
import {
    formatOffset,
    offsetDirection,
    serviceName,
    sourceLabel,
    statusColor,
    statusHelp,
    statusLabel,
} from './timeSyncLabels';

const Field: React.FC<{ label: string; value: React.ReactNode }> = ({ label, value }) => (
    <Grid size={{ xs: 12, sm: 6 }}>
        <Typography variant="caption" color="text.secondary">{label}</Typography>
        <Typography variant="body2">{value}</Typography>
    </Grid>
);

const yesNo = (t: TFunction, value: boolean | null): string => {
    if (value === null) {
        return t('timeSync.card.notReported', 'Not reported');
    }
    return value ? t('timeSync.card.yes', 'Yes') : t('timeSync.card.no', 'No');
};

const ClaimFields: React.FC<{ claim: TimeService }> = ({ claim }) => {
    const { t } = useTranslation();
    return (
        <>
            <Field label={t('timeSync.card.service', 'Time service')} value={serviceName(t, claim.service)} />
            <Field label={t('timeSync.card.running', 'Running')} value={yesNo(t, claim.running)} />
            <Field label={t('timeSync.card.synchronized', 'Synchronized')} value={yesNo(t, claim.synchronized)} />
            <Field label={t('timeSync.card.source', 'Time source')} value={claim.source ?? '-'} />
            <Field label={t('timeSync.card.stratum', 'Stratum')} value={claim.stratum ?? '-'} />
            <Field
                label={t('timeSync.card.reportedOffset', "The service's own offset estimate")}
                value={formatOffset(t, claim.reported_offset_ms)}
            />
        </>
    );
};

const History: React.FC<{ clock: HostClock }> = ({ clock }) => {
    const { t } = useTranslation();
    if (clock.history.length < 2) {
        return (
            <Typography variant="body2" color="text.secondary" sx={{ mt: 2 }}>
                {t('timeSync.card.noHistory', 'The offset history fills in as the host stays connected (one point every 15 minutes).')}
            </Typography>
        );
    }
    const warning = clock.bounds.warning_ms;
    return (
        <Box sx={{ mt: 2 }}>
            <Typography variant="subtitle2">{t('timeSync.card.history', 'Measured offset, last 7 days (ms)')}</Typography>
            <LineChart
                height={220}
                xAxis={[{ data: clock.history.map(p => new Date(p.at)), scaleType: 'time' }]}
                series={[{ data: clock.history.map(p => p.offset_ms), showMark: false }]}
            >
                <ChartsReferenceLine y={warning} lineStyle={{ strokeDasharray: '4 4' }} />
                <ChartsReferenceLine y={-warning} lineStyle={{ strokeDasharray: '4 4' }} />
            </LineChart>
        </Box>
    );
};

const Measurement: React.FC<{ clock: HostClock }> = ({ clock }) => {
    const { t } = useTranslation();
    const measured = clock.measured;
    if (!measured) {
        return null;
    }
    return (
        <>
            <Field
                label={t('timeSync.card.offset', 'Measured offset')}
                value={`${formatOffset(t, measured.offset_ms)} ${offsetDirection(t, measured.offset_ms)}`}
            />
            <Field
                label={t('timeSync.card.roundTrip', 'Round trip')}
                value={formatOffset(t, measured.rtt_ms).replace('+', '')}
            />
            <Field
                label={t('timeSync.card.method', 'Measured by')}
                value={measured.method === 'timestamp'
                    ? t('timeSync.card.methodTimestamp', 'Message timestamp (to the second)')
                    : t('timeSync.card.methodExchange', 'Heartbeat exchange (to the millisecond)')}
            />
            <Field
                label={t('timeSync.card.measuredAt', 'Measured')}
                value={measured.measured_at ? new Date(`${measured.measured_at}Z`).toLocaleString() : '-'}
            />
        </>
    );
};

const HostClockCard: React.FC<{ hostId: string }> = ({ hostId }) => {
    const { t } = useTranslation();
    const [clock, setClock] = useState<HostClock | null>(null);
    const [error, setError] = useState(false);

    const load = useCallback(async () => {
        try {
            setClock(await getHostClock(hostId));
        } catch {
            setError(true);
        }
    }, [hostId]);

    useEffect(() => {
        void load();
    }, [load]);

    const body = () => {
        if (error) {
            return <Alert severity="error">{t('timeSync.card.loadError', "Could not load this host's clock.")}</Alert>;
        }
        if (!clock) {
            return <CircularProgress size={24} />;
        }
        return (
            <>
                <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 2 }}>
                    <Tooltip title={statusHelp(t, clock.status)}>
                        <Chip color={statusColor(clock.status)} label={statusLabel(t, clock.status)} />
                    </Tooltip>
                    <Typography variant="body2" color="text.secondary">
                        {t('timeSync.card.bounds', 'Bounds {{warning}} / {{critical}} ({{source}})', {
                            warning: formatOffset(t, clock.bounds.warning_ms).replace('+', ''),
                            critical: formatOffset(t, clock.bounds.critical_ms).replace('+', ''),
                            source: sourceLabel(t, clock.bounds.source),
                        })}
                    </Typography>
                </Stack>
                {clock.service_ok === false && (
                    <Alert severity="warning" sx={{ mb: 2 }}>
                        {t('timeSync.card.serviceProblem', 'The time service on this host is not running or not synchronized, so its clock will drift.')}
                    </Alert>
                )}
                <Grid container spacing={2}>
                    <Measurement clock={clock} />
                    {clock.time_service && <ClaimFields claim={clock.time_service} />}
                </Grid>
                <History clock={clock} />
            </>
        );
    };

    return (
        <Card>
            <CardContent>
                <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 2 }}>
                    <AccessTimeIcon />
                    <Typography variant="h6">{t('timeSync.card.title', 'Clock')}</Typography>
                </Stack>
                {body()}
            </CardContent>
        </Card>
    );
};

export default HostClockCard;
