// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

// A host that cannot reach the backup storage (Phase 24): its agent could
// not open NFS's port on the storage host, so backups are not offered to it
// (production, 2026-10-30: the server's own cloud droplet and the home NAS).
// "Check again" asks the agent once more.

import React, { useEffect, useRef, useState } from 'react';
import { Button, Stack, Typography } from '@mui/material';
import { useTranslation } from 'react-i18next';
import { checkBackupReach } from '../../Services/backups';
import type { BackupReach } from '../../Services/backups';
import { apiDetail, reachMessage } from './backupLabels';

// How long the agent usually takes to answer before the view re-reads.
const RECHECK_WAIT_MS = 6000;

const StorageReachNote: React.FC<{
    hostId: string;
    reach: BackupReach | null | undefined;
    canManage: boolean;
    onChanged: () => void;
}> = ({ hostId, reach, canManage, onChanged }) => {
    const { t } = useTranslation();
    const [busy, setBusy] = useState(false);
    const [note, setNote] = useState<string | null>(null);
    const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);

    useEffect(() => () => { if (timer.current) clearTimeout(timer.current); }, []);

    if (!reach || reach.reachable) return null;

    const recheck = async () => {
        setBusy(true);
        setNote(null);
        try {
            await checkBackupReach(hostId);
            setNote(t('backups.equip.checking', 'Asked the agent; the status updates in a few seconds.'));
            timer.current = setTimeout(() => {
                setBusy(false);
                onChanged();
            }, RECHECK_WAIT_MS);
        } catch (err) {
            setNote(apiDetail(err, t('backups.equip.recheckError', 'The check could not be requested.')));
            setBusy(false);
        }
    };

    return (
        <Stack spacing={0.5} sx={{ mt: 0.5 }}>
            <Typography variant="caption" color="warning.main" display="block">
                {reachMessage(t, reach)}
            </Typography>
            {canManage && (
                <div>
                    <Button size="small" onClick={() => void recheck()} disabled={busy}>
                        {t('backups.equip.recheck', 'Check again')}
                    </Button>
                </div>
            )}
            {note && <Typography variant="caption" color="text.secondary">{note}</Typography>}
        </Stack>
    );
};

export default StorageReachNote;
