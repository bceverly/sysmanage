// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

// The SysManage server's own backup on the Backups page (ROADMAP 25.9): a
// warning while it has no good backup, with Back up this SysManage server
// when it has no policy yet.  Nothing once it is backed up.

import React, { useState } from 'react';
import { Alert, Button } from '@mui/material';
import type { TFunction } from 'i18next';
import { useTranslation } from 'react-i18next';
import type { BackupHost, ServerBackupStatus } from '../../Services/backups';
import BackupServerDialog from './BackupServerDialog';

/** Why the server is warned on. */
export const serverMessage = (t: TFunction, server: ServerBackupStatus): string => {
    if (server.status === 'no_good_backup') {
        return t('backups.server.noGoodBackup',
            'This SysManage server ({{host}}) has no recent good backup. Its row below says why.',
            { host: server.fqdn ?? '' });
    }
    if (server.status === 'no_policy') {
        return server.fqdn
            ? t('backups.server.noPolicy',
                'This SysManage server ({{host}}) is not backed up. If it is lost, every agent must enroll again, and the OpenBAO secrets and the databases are gone.',
                { host: server.fqdn })
            : t('backups.server.noPolicyMany',
                'This SysManage server is not backed up. If it is lost, every agent must enroll again, and the OpenBAO secrets and the databases are gone.');
    }
    return t('backups.server.unknown',
        'SysManage cannot tell which host is this server, so it cannot tell whether the server is backed up. Pick its host to back it up.');
};

const BackupServerCard: React.FC<{
    server?: ServerBackupStatus;
    hosts: BackupHost[];
    canManage: boolean;
    onChanged: () => void;
}> = ({ server, hosts, canManage, onChanged }) => {
    const { t } = useTranslation();
    const [open, setOpen] = useState(false);
    if (!server?.warn) return null;
    const offer = canManage && server.status !== 'no_good_backup';
    return (
        <>
            <Alert severity="warning" sx={{ mb: 2 }}
                action={offer ? (
                    <Button color="inherit" size="small" onClick={() => setOpen(true)}>
                        {t('backups.server.backUp', 'Back up this SysManage server')}
                    </Button>
                ) : undefined}>
                {serverMessage(t, server)}
            </Alert>
            {offer && (
                <BackupServerDialog open={open} hostId={server.host_id}
                    hosts={hosts.map(h => ({ host_id: h.host_id, fqdn: h.fqdn }))}
                    onClose={() => setOpen(false)} onSaved={onChanged} />
            )}
        </>
    );
};

export default BackupServerCard;
