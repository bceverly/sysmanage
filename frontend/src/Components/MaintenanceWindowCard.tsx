import React, { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import Card from '@mui/material/Card';
import CardContent from '@mui/material/CardContent';
import Typography from '@mui/material/Typography';
import Chip from '@mui/material/Chip';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Dialog from '@mui/material/Dialog';
import DialogTitle from '@mui/material/DialogTitle';
import DialogContent from '@mui/material/DialogContent';
import DialogActions from '@mui/material/DialogActions';
import TextField from '@mui/material/TextField';
import Stack from '@mui/material/Stack';
import ScheduleIcon from '@mui/icons-material/Schedule';

import {
    HostWindowStatus,
    maintenanceWindowsService,
} from '../Services/maintenanceWindows';
import { formatUTCTimestamp } from '../utils/dateUtils';

interface Props {
    hostId: string;
}

const STATE_COLOR: Record<
    HostWindowStatus['state'],
    'default' | 'success' | 'error' | 'warning'
> = {
    unrestricted: 'default',
    in_window: 'success',
    blocked: 'warning',
    override: 'error',
};

const MaintenanceWindowCard: React.FC<Props> = ({ hostId }) => {
    const { t } = useTranslation();
    const [status, setStatus] = useState<HostWindowStatus | null>(null);
    const [overrideOpen, setOverrideOpen] = useState(false);
    const [reason, setReason] = useState('');
    const [duration, setDuration] = useState(120);
    const [busy, setBusy] = useState(false);

    const load = useCallback(async () => {
        try {
            setStatus(await maintenanceWindowsService.hostStatus(hostId));
        } catch (err) {
            console.error('Error loading maintenance status:', err);
        }
    }, [hostId]);

    useEffect(() => {
        load();
    }, [load]);

    const submitOverride = async () => {
        setBusy(true);
        try {
            await maintenanceWindowsService.createOverride(hostId, reason, duration);
            setOverrideOpen(false);
            setReason('');
            await load();
        } catch (err) {
            console.error('Error creating override:', err);
        } finally {
            setBusy(false);
        }
    };

    if (!status) {
        return null;
    }

    const stateLabel = t(
        `maintenanceWindows.state.${status.state}`,
        status.state,
    );

    return (
        <Card sx={{ height: '100%' }}>
            <CardContent>
                <Typography
                    variant="subtitle1"
                    sx={{
                        mb: 2,
                        display: 'flex',
                        alignItems: 'center',
                        fontWeight: 'bold',
                    }}
                >
                    <ScheduleIcon sx={{ mr: 1 }} />
                    {t('maintenanceWindows.hostCardTitle', 'Maintenance Window')}
                </Typography>

                <Box sx={{ mb: 1 }}>
                    <Chip
                        size="small"
                        color={STATE_COLOR[status.state]}
                        label={stateLabel}
                    />
                </Box>

                {status.state === 'override' && status.override && (
                    <Typography variant="body2" color="text.secondary">
                        {t(
                            'maintenanceWindows.overrideActive',
                            'Emergency override active until {{time}}',
                            { time: formatUTCTimestamp(status.override.expires_at) },
                        )}
                    </Typography>
                )}
                {status.state === 'blocked' && status.active_blackout && (
                    <Typography variant="body2" color="text.secondary">
                        {t('maintenanceWindows.inBlackout', 'In blackout: {{name}}', {
                            name: status.active_blackout,
                        })}
                    </Typography>
                )}
                {status.next_window && (
                    <Box sx={{ mt: 1 }}>
                        <Typography variant="body2" color="text.secondary">
                            {status.state === 'in_window'
                                ? t('maintenanceWindows.currentWindow', 'Current window')
                                : t('maintenanceWindows.nextWindow', 'Next window')}
                        </Typography>
                        <Typography variant="body1">
                            {status.next_window.name}
                        </Typography>
                        <Typography variant="body2" color="text.secondary">
                            {formatUTCTimestamp(status.next_window.starts_at)}
                        </Typography>
                    </Box>
                )}
                {status.state === 'unrestricted' && (
                    <Typography variant="body2" color="text.secondary">
                        {t(
                            'maintenanceWindows.unrestrictedHint',
                            'No maintenance window applies — changes run immediately.',
                        )}
                    </Typography>
                )}

                {(status.state === 'blocked' || status.state === 'in_window') && (
                    <Button
                        size="small"
                        color="error"
                        sx={{ mt: 2 }}
                        onClick={() => setOverrideOpen(true)}
                    >
                        {t('maintenanceWindows.emergencyOverride', 'Emergency override')}
                    </Button>
                )}
            </CardContent>

            <Dialog open={overrideOpen} onClose={() => setOverrideOpen(false)}>
                <DialogTitle>
                    {t('maintenanceWindows.emergencyOverride', 'Emergency override')}
                </DialogTitle>
                <DialogContent>
                    <Stack spacing={2} sx={{ mt: 1, minWidth: 320 }}>
                        <Typography variant="body2" color="text.secondary">
                            {t(
                                'maintenanceWindows.overrideExplain',
                                'Temporarily allow changes to reach this host regardless ' +
                                    'of its windows. This action is audited.',
                            )}
                        </Typography>
                        <TextField
                            label={t('maintenanceWindows.overrideReason', 'Reason')}
                            value={reason}
                            required
                            multiline
                            minRows={2}
                            size="small"
                            onChange={(e) => setReason(e.target.value)}
                        />
                        <TextField
                            type="number"
                            label={t(
                                'maintenanceWindows.overrideDuration',
                                'Duration (minutes)',
                            )}
                            value={duration}
                            size="small"
                            onChange={(e) => setDuration(Number(e.target.value) || 0)}
                        />
                    </Stack>
                </DialogContent>
                <DialogActions>
                    <Button onClick={() => setOverrideOpen(false)}>
                        {t('common.cancel', 'Cancel')}
                    </Button>
                    <Button
                        color="error"
                        variant="contained"
                        disabled={busy || !reason.trim() || duration <= 0}
                        onClick={submitOverride}
                    >
                        {t('maintenanceWindows.confirmOverride', 'Override')}
                    </Button>
                </DialogActions>
            </Dialog>
        </Card>
    );
};

export default MaintenanceWindowCard;
