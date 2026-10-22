// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

// "Repack" for one host's repository (2026-10-21).  restate 2.0.0.8 writes
// seekable packs, so a restore of a few files reads only what it needs; packs
// written before stay whole until rewritten.  The rewrite runs on the storage
// host against its own disk, reads and writes the whole repository, and holds
// it while it runs (backups of this host wait), so it is started by hand.

import React, { useState } from 'react';
import { Alert, Button, Dialog, DialogActions, DialogContent, DialogContentText, DialogTitle } from '@mui/material';
import { useTranslation } from 'react-i18next';
import AsyncButton from '../AsyncButton';
import { backupNow } from '../../Services/backups';
import { apiDetail } from './backupLabels';

const BackupRepackButton: React.FC<{ hostId: string; disabled?: boolean; onStarted: () => void }> = ({
    hostId,
    disabled = false,
    onStarted,
}) => {
    const { t } = useTranslation();
    const [open, setOpen] = useState(false);
    const [error, setError] = useState<string | null>(null);

    const start = async () => {
        try {
            await backupNow(hostId, 'repack');
            setOpen(false);
            onStarted();
        } catch (err) {
            setError(apiDetail(err, t('backups.repack.error', 'The repack could not be started.')));
        }
    };

    return (
        <>
            <Button size="small" disabled={disabled} onClick={() => { setError(null); setOpen(true); }}>
                {t('backups.repack.button', 'Repack')}
            </Button>
            <Dialog open={open} onClose={() => setOpen(false)} maxWidth="sm" fullWidth>
                <DialogTitle>{t('backups.repack.title', 'Repack this host\'s backups?')}</DialogTitle>
                <DialogContent>
                    {error && <Alert severity="error" sx={{ mb: 1 }}>{error}</Alert>}
                    <DialogContentText>
                        {t('backups.repack.body',
                            'The storage host rewrites this host\'s older backup packs so that restoring a few files reads only what it needs (restate 2.0.0.8 or later). It reads and rewrites the whole repository on the storage host, which can take a long time, and this host\'s backups wait until it is done. No snapshot is lost.')}
                    </DialogContentText>
                </DialogContent>
                <DialogActions>
                    <Button onClick={() => setOpen(false)}>{t('common.cancel', 'Cancel')}</Button>
                    <AsyncButton variant="contained" onClick={start}>{t('backups.repack.button', 'Repack')}</AsyncButton>
                </DialogActions>
            </Dialog>
        </>
    );
};

export default BackupRepackButton;
