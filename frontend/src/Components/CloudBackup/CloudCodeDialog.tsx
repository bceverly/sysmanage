// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

// The two-factor code for an iCloud sign-in that is waiting for it (24.12).
// The server holds it only until the storage host's job collects it.

import React, { useEffect, useState } from 'react';
import {
    Alert, Button, Dialog, DialogActions, DialogContent, DialogContentText, DialogTitle, TextField,
} from '@mui/material';
import { useTranslation } from 'react-i18next';
import { sendCloudCode } from '../../Services/cloudBackup';
import { apiDetail } from '../Backups/backupLabels';

interface Props {
    runId: string | null;
    accountName: string;
    onClose: () => void;
    onSent: () => void;
}

const CloudCodeDialog: React.FC<Props> = ({ runId, accountName, onClose, onSent }) => {
    const { t } = useTranslation();
    const [code, setCode] = useState('');
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState('');

    useEffect(() => {
        setCode('');
        setError('');
    }, [runId]);

    const send = async () => {
        if (!runId) return;
        setBusy(true);
        setError('');
        try {
            await sendCloudCode(runId, code.replace(/\s/g, ''));
            setCode('');
            onSent();
        } catch (err) {
            setError(apiDetail(err, t('cloudBackup.code.failed', 'The code could not be sent.')));
        } finally {
            setBusy(false);
        }
    };

    const ready = /^\d{6}$/.test(code.replace(/\s/g, ''));
    return (
        <Dialog open={runId !== null} onClose={busy ? undefined : onClose} maxWidth="xs" fullWidth>
            <DialogTitle>{t('cloudBackup.code.title', 'Enter the two-factor code')}</DialogTitle>
            <DialogContent>
                <DialogContentText sx={{ mb: 2 }}>
                    {t('cloudBackup.code.help',
                        'Apple has sent a six-digit code to the devices signed in to {{account}}. Type it here within 15 minutes.',
                        { account: accountName })}
                </DialogContentText>
                <TextField autoFocus fullWidth label={t('cloudBackup.code.label', 'Six-digit code')} value={code}
                    onChange={e => setCode(e.target.value)} autoComplete="one-time-code"
                    slotProps={{ htmlInput: { inputMode: 'numeric', maxLength: 7, 'data-testid': 'cloud-code' } }}
                    onKeyDown={e => { if (e.key === 'Enter' && ready) void send(); }} />
                {error && <Alert severity="error" sx={{ mt: 2 }}>{error}</Alert>}
            </DialogContent>
            <DialogActions>
                <Button onClick={onClose} disabled={busy}>{t('common.cancel', 'Cancel')}</Button>
                <Button variant="contained" onClick={() => void send()} disabled={busy || !ready}>
                    {t('cloudBackup.code.send', 'Send code')}
                </Button>
            </DialogActions>
        </Dialog>
    );
};

export default CloudCodeDialog;
