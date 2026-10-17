// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

import React, { useState } from 'react';
import { useTranslation } from 'react-i18next';
import Alert from '@mui/material/Alert';
import Button from '@mui/material/Button';

import type { HostWindowStatus } from '../../Services/maintenanceWindows';
import { formatUTCTimestamp } from '../../utils/dateUtils';
import EmergencyOverrideDialog from '../EmergencyOverrideDialog';

interface Props {
    hostId: string;
    status: HostWindowStatus | null;
    onReleased: () => void;
}

/**
 * Shown on every tab of the host page while a maintenance window holds some
 * of this host's commands, so a queued action never looks like a dead button.
 */
const HeldCommandsBanner: React.FC<Props> = ({ hostId, status, onReleased }) => {
    const { t } = useTranslation();
    const [overrideOpen, setOverrideOpen] = useState(false);
    const count = status?.held_commands?.count ?? 0;
    if (!status || count === 0) {
        return null;
    }
    const text = status.next_window
        ? t(
            'hostDetail.heldCommands',
            "{{count}} commands are waiting for the '{{name}}' maintenance window, which opens at {{time}}.",
            {
                count,
                name: status.next_window.name,
                time: formatUTCTimestamp(status.next_window.starts_at ?? ''),
            },
        )
        : t(
            'hostDetail.heldCommandsBlackout',
            "{{count}} commands are waiting for the '{{name}}' blackout to end.",
            { count, name: status.active_blackout ?? '' },
        );
    return (
        <>
            <Alert
                severity="warning"
                sx={{ mb: 2 }}
                data-testid="held-commands-banner"
                action={
                    <Button color="inherit" size="small" onClick={() => setOverrideOpen(true)}>
                        {t('maintenanceWindows.emergencyOverride', 'Emergency override')}
                    </Button>
                }
            >
                {text}
            </Alert>
            <EmergencyOverrideDialog
                hostId={hostId}
                open={overrideOpen}
                onClose={() => setOverrideOpen(false)}
                onDone={onReleased}
            />
        </>
    );
};

export default HeldCommandsBanner;
