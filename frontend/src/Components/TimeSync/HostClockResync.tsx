// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

// Spot resync on the host's Clock card (Phase 23.3 S5): one button, the last
// few resyncs with what they found, polled while one is in flight.

import React, { useCallback, useEffect, useState } from 'react';
import { Alert, Box, Button, Chip, Stack, Tooltip, Typography } from '@mui/material';
import SyncIcon from '@mui/icons-material/Sync';
import { useTranslation } from 'react-i18next';
import { errorCode } from '../../Services/machines';
import { hasPermission, SecurityRoles } from '../../Services/permissions';
import { getResyncs, resyncHost } from '../../Services/timeSync';
import type { ClockResync } from '../../Services/timeSync';
import { formatOffset, resyncErrorText, resyncStatusColor, resyncStatusLabel } from './timeSyncLabels';

const POLL_MS = 5000;
const SHOWN = 3;

const inFlight = (rows: ClockResync[]) => rows.some(r => r.status === 'queued' || r.status === 'sent');

const ResyncRow: React.FC<{ row: ClockResync }> = ({ row }) => {
    const { t } = useTranslation();
    const when = row.requested_at ? new Date(`${row.requested_at}Z`).toLocaleString() : '';
    return (
        <Stack direction="row" spacing={1} alignItems="center" sx={{ flexWrap: 'wrap', rowGap: 0.5 }}>
            <Chip size="small" color={resyncStatusColor(row.status)} label={resyncStatusLabel(t, row.status)} />
            <Typography variant="caption" color="text.secondary">{when}</Typography>
            {row.status === 'succeeded' && row.reported_after_ms !== null && (
                <Typography variant="caption">
                    {t('timeSync.resync.after', 'Service now reports {{offset}}', {
                        offset: formatOffset(t, row.reported_after_ms),
                    })}
                </Typography>
            )}
            {row.error && (
                <Tooltip title={row.detail ?? ''}>
                    <Typography variant="caption" color="error">{resyncErrorText(t, row.error)}</Typography>
                </Tooltip>
            )}
        </Stack>
    );
};

const HostClockResync: React.FC<{ hostId: string; onDone?: () => void }> = ({ hostId, onDone }) => {
    const { t } = useTranslation();
    const [rows, setRows] = useState<ClockResync[]>([]);
    const [canResync, setCanResync] = useState(false);
    const [error, setError] = useState<string | null>(null);

    const load = useCallback(async () => {
        try {
            setRows(await getResyncs({ hostId, limit: SHOWN }));
        } catch {
            setRows([]);
        }
    }, [hostId]);

    useEffect(() => {
        void load();
        void hasPermission(SecurityRoles.RESYNC_HOST_CLOCK).then(setCanResync).catch(() => setCanResync(false));
    }, [load]);

    const busy = inFlight(rows);
    useEffect(() => {
        if (!busy) {
            return undefined;
        }
        const timer = globalThis.setTimeout(() => {
            void load().then(() => onDone?.());
        }, POLL_MS);
        return () => globalThis.clearTimeout(timer);
    }, [busy, rows, load, onDone]);

    const resync = async () => {
        setError(null);
        try {
            await resyncHost(hostId);
        } catch (e) {
            setError(errorCode(e) === 'already_running'
                ? t('timeSync.resync.alreadyRunning', 'A resynchronization is already in progress.')
                : t('timeSync.resync.requestFailed', 'The resynchronization could not be requested.'));
        }
        await load();
    };

    return (
        <Box sx={{ mt: 2 }}>
            <Stack direction="row" spacing={2} alignItems="center" sx={{ mb: 1 }}>
                <Tooltip title={canResync ? '' : t('timeSync.resync.needsRole', 'Requires the Resync Host Clock role.')}>
                    <span>
                        <Button
                            size="small"
                            variant="outlined"
                            startIcon={<SyncIcon />}
                            disabled={!canResync || busy}
                            onClick={() => void resync()}
                        >
                            {t('timeSync.resync.button', 'Resynchronize now')}
                        </Button>
                    </span>
                </Tooltip>
            </Stack>
            {error && <Alert severity="error" sx={{ mb: 1 }}>{error}</Alert>}
            <Stack spacing={0.5}>
                {rows.map(row => <ResyncRow key={row.id} row={row} />)}
            </Stack>
        </Box>
    );
};

export default HostClockResync;
