// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

import React, { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import Card from '@mui/material/Card';
import CardContent from '@mui/material/CardContent';
import Typography from '@mui/material/Typography';
import Chip from '@mui/material/Chip';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import ScheduleIcon from '@mui/icons-material/Schedule';

import {
    HostWindowStatus,
    maintenanceWindowsService,
} from '../Services/maintenanceWindows';
import { formatUTCTimestamp } from '../utils/dateUtils';
import EmergencyOverrideDialog from './EmergencyOverrideDialog';

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

    const load = useCallback(async () => {
        try {
            setStatus(await maintenanceWindowsService.hostStatus(hostId));
        } catch (err) {
            console.error('Error loading maintenance status:', err);
        }
    }, [hostId]);

    useEffect(() => {
        void load();
    }, [load]);

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
                            'No maintenance window applies -- changes run immediately.',
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

            <EmergencyOverrideDialog
                hostId={hostId}
                open={overrideOpen}
                onClose={() => setOverrideOpen(false)}
                onDone={() => { void load(); }}
            />
        </Card>
    );
};

export default MaintenanceWindowCard;
