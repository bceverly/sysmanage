// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

// Resync every clock out of bounds at once (Phase 23.3 S5).  The server
// releases them in waves; this says how many and what happened to them.

import React, { useEffect, useState } from 'react';
import {
    Alert,
    Button,
    Dialog,
    DialogActions,
    DialogContent,
    DialogContentText,
    DialogTitle,
} from '@mui/material';
import SyncIcon from '@mui/icons-material/Sync';
import { useTranslation } from 'react-i18next';
import { hasPermission, SecurityRoles } from '../../Services/permissions';
import { resyncFleet } from '../../Services/timeSync';
import type { FleetClocks, FleetResync } from '../../Services/timeSync';

interface Props {
    data: FleetClocks;
    onDone: () => void;
}

const FleetResyncButton: React.FC<Props> = ({ data, onDone }) => {
    const { t } = useTranslation();
    const [allowed, setAllowed] = useState(false);
    const [open, setOpen] = useState(false);
    const [result, setResult] = useState<FleetResync | null>(null);
    const [failed, setFailed] = useState(false);
    const outOfBounds = (data.counts.warning ?? 0) + (data.counts.critical ?? 0);

    useEffect(() => {
        void hasPermission(SecurityRoles.RESYNC_HOST_CLOCK).then(setAllowed).catch(() => setAllowed(false));
    }, []);

    if (!allowed || data.server.reason === 'server_off') {
        return null; // stepping hosts to a wrong server clock would make them wrong too
    }

    const run = async () => {
        setOpen(false);
        setFailed(false);
        try {
            setResult(await resyncFleet(['warning', 'critical']));
            onDone();
        } catch {
            setFailed(true);
        }
    };

    return (
        <>
            <Button
                variant="contained"
                startIcon={<SyncIcon />}
                disabled={outOfBounds === 0}
                onClick={() => setOpen(true)}
            >
                {t('timeSync.resync.fleetButton', 'Resynchronize clocks out of bounds')}
            </Button>
            <Dialog open={open} onClose={() => setOpen(false)}>
                <DialogTitle>{t('timeSync.resync.fleetTitle', 'Resynchronize clocks')}</DialogTitle>
                <DialogContent>
                    <DialogContentText>
                        {t('timeSync.resync.fleetConfirm', 'Step the clock of every host at warning or critical ({{count}} hosts) through its own time service. They are sent in waves; hosts without administrator rights are skipped and listed.', { count: outOfBounds })}
                    </DialogContentText>
                </DialogContent>
                <DialogActions>
                    <Button onClick={() => setOpen(false)}>{t('timeSync.resync.cancel', 'Cancel')}</Button>
                    <Button variant="contained" onClick={() => void run()}>
                        {t('timeSync.resync.confirm', 'Resynchronize')}
                    </Button>
                </DialogActions>
            </Dialog>
            {result && (
                <Alert severity="info" sx={{ mt: 2 }} onClose={() => setResult(null)}>
                    {t('timeSync.resync.fleetResult', '{{requested}} resynchronizations requested: {{sent}} sent, {{unsupported}} not possible, {{running}} already in progress.', {
                        requested: result.requested,
                        sent: result.counts.sent ?? 0,
                        unsupported: result.counts.unsupported ?? 0,
                        running: result.already_running,
                    })}
                </Alert>
            )}
            {failed && (
                <Alert severity="error" sx={{ mt: 2 }}>
                    {t('timeSync.resync.requestFailed', 'The resynchronization could not be requested.')}
                </Alert>
            )}
        </>
    );
};

export default FleetResyncButton;
