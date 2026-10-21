// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

// "Clear" for the Recent jobs list (2026-10-21).  Finished jobs leave the
// list; queued and running ones stay.  Nothing is deleted: the status above
// still reads each kind's newest result, the audit log keeps every change,
// and the scheduler removes jobs older than 30 days on its own.

import React, { useState } from 'react';
import { Alert, Button, Dialog, DialogActions, DialogContent, DialogContentText, DialogTitle } from '@mui/material';
import { useTranslation } from 'react-i18next';
import AsyncButton from '../AsyncButton';
import { clearRuns } from '../../Services/backups';
import { apiDetail } from './backupLabels';

const BackupClearJobs: React.FC<{ onCleared: () => void }> = ({ onCleared }) => {
    const { t } = useTranslation();
    const [open, setOpen] = useState(false);
    const [error, setError] = useState<string | null>(null);

    const clear = async () => {
        try {
            await clearRuns();
            setOpen(false);
            onCleared();
        } catch (err) {
            setError(apiDetail(err, t('backups.runs.clearError', 'The job list could not be cleared.')));
        }
    };

    return (
        <>
            <Button size="small" onClick={() => { setError(null); setOpen(true); }}>
                {t('backups.runs.clear', 'Clear list')}
            </Button>
            <Dialog open={open} onClose={() => setOpen(false)} maxWidth="xs" fullWidth>
                <DialogTitle>{t('backups.runs.clearTitle', 'Clear the job list?')}</DialogTitle>
                <DialogContent>
                    {error && <Alert severity="error" sx={{ mb: 1 }}>{error}</Alert>}
                    <DialogContentText>
                        {t('backups.runs.clearBody',
                            'Finished jobs leave this list; queued and running jobs stay. Nothing is removed from the audit log, and the backup status above is not affected.')}
                    </DialogContentText>
                </DialogContent>
                <DialogActions>
                    <Button onClick={() => setOpen(false)}>{t('common.cancel', 'Cancel')}</Button>
                    <AsyncButton variant="contained" onClick={clear}>{t('backups.runs.clear', 'Clear list')}</AsyncButton>
                </DialogActions>
            </Dialog>
        </>
    );
};

export default BackupClearJobs;
