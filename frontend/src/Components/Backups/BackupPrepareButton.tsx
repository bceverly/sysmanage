// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

// "Prepare storage" for one host's repository (Phase 24, 2026-10-22).  The
// storage host's agent gives the repository its own ZFS dataset or btrfs
// subvolume and an NFS export limited to this host, mapped to the backup
// account, and makes it append-only.  Started by an administrator, never
// automatically: it creates filesystems and changes exports on the storage
// host.  Run again, it re-exports to the host's current address.

import React, { useState } from 'react';
import { Alert, Button, Dialog, DialogActions, DialogContent, DialogContentText, DialogTitle } from '@mui/material';
import { useTranslation } from 'react-i18next';
import AsyncButton from '../AsyncButton';
import { backupNow } from '../../Services/backups';
import { apiDetail } from './backupLabels';

const BackupPrepareButton: React.FC<{ hostId: string; disabled?: boolean; onStarted: () => void }> = ({
    hostId,
    disabled = false,
    onStarted,
}) => {
    const { t } = useTranslation();
    const [open, setOpen] = useState(false);
    const [error, setError] = useState<string | null>(null);

    const start = async () => {
        try {
            await backupNow(hostId, 'prepare');
            setOpen(false);
            onStarted();
        } catch (err) {
            setError(apiDetail(err, t('backups.prepare.error', 'Preparing the storage could not be started.')));
        }
    };

    return (
        <>
            <Button size="small" disabled={disabled} onClick={() => { setError(null); setOpen(true); }}>
                {t('backups.action.prepare', 'Prepare storage')}
            </Button>
            <Dialog open={open} onClose={() => setOpen(false)} maxWidth="sm" fullWidth>
                <DialogTitle>{t('backups.prepare.title', 'Prepare the storage for this host?')}</DialogTitle>
                <DialogContent>
                    {error && <Alert severity="error" sx={{ mb: 1 }}>{error}</Alert>}
                    <DialogContentText>
                        {t('backups.prepare.body',
                            'The storage host gives this host\'s repository its own ZFS dataset or btrfs subvolume, exports it over NFS to this host\'s address only with every file mapped to the backup account, and makes it append-only. It never moves existing backups: a repository that already holds files on the shared filesystem is refused, with the steps to move it. Run it again after this host\'s address changes.')}
                    </DialogContentText>
                </DialogContent>
                <DialogActions>
                    <Button onClick={() => setOpen(false)}>{t('common.cancel', 'Cancel')}</Button>
                    <AsyncButton variant="contained" onClick={start}>{t('backups.action.prepare', 'Prepare storage')}</AsyncButton>
                </DialogActions>
            </Dialog>
        </>
    );
};

export default BackupPrepareButton;
