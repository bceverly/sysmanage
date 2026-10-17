// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

import React, { useState } from 'react';
import { useTranslation } from 'react-i18next';
import Alert from '@mui/material/Alert';
import Button from '@mui/material/Button';
import Dialog from '@mui/material/Dialog';
import DialogTitle from '@mui/material/DialogTitle';
import DialogContent from '@mui/material/DialogContent';
import DialogActions from '@mui/material/DialogActions';
import TextField from '@mui/material/TextField';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';

import { maintenanceWindowsService } from '../Services/maintenanceWindows';

interface Props {
    hostId: string;
    open: boolean;
    onClose: () => void;
    // Called after the override was created (the host's held commands are
    // released on the server's next tick).
    onDone?: () => void;
}

/**
 * The time-boxed emergency override for one host -- shared by the host's
 * Maintenance Window card, the "commands held" banner on the host page and
 * the Held commands list.  Administrators only on the server; a refusal is
 * shown in the dialog rather than swallowed.
 */
const EmergencyOverrideDialog: React.FC<Props> = ({ hostId, open, onClose, onDone }) => {
    const { t } = useTranslation();
    const [reason, setReason] = useState('');
    const [duration, setDuration] = useState(120);
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState<string | null>(null);

    const close = () => {
        setError(null);
        onClose();
    };

    const submit = async () => {
        setBusy(true);
        setError(null);
        try {
            await maintenanceWindowsService.createOverride(hostId, reason, duration);
            setReason('');
            onClose();
            onDone?.();
        } catch (err) {
            const detail = (err as { response?: { data?: { detail?: unknown } } })
                ?.response?.data?.detail;
            setError(
                typeof detail === 'string' && detail
                    ? detail
                    : t('maintenanceWindows.overrideFailed', 'The override could not be created.'),
            );
        } finally {
            setBusy(false);
        }
    };

    return (
        <Dialog open={open} onClose={close}>
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
                    {error && <Alert severity="error">{error}</Alert>}
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
                        label={t('maintenanceWindows.overrideDuration', 'Duration (minutes)')}
                        value={duration}
                        size="small"
                        onChange={(e) => setDuration(Number(e.target.value) || 0)}
                    />
                </Stack>
            </DialogContent>
            <DialogActions>
                <Button onClick={close}>{t('common.cancel', 'Cancel')}</Button>
                <Button
                    color="error"
                    variant="contained"
                    disabled={busy || !reason.trim() || duration <= 0}
                    onClick={submit}
                >
                    {t('maintenanceWindows.confirmOverride', 'Override')}
                </Button>
            </DialogActions>
        </Dialog>
    );
};

export default EmergencyOverrideDialog;
