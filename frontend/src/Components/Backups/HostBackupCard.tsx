// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

// A host's backup on its Info tab (Phase 24): status, last backup and check,
// snapshots, and the same actions as the Backups page.

import React, { useCallback, useEffect, useState } from 'react';
import { Alert, Button, Card, CardContent, Chip, Stack, Typography } from '@mui/material';
import BackupIcon from '@mui/icons-material/Backup';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router';
import AsyncButton from '../AsyncButton';
import { backupNow, getHostBackup } from '../../Services/backups';
import type { HostBackup } from '../../Services/backups';
import { hasPermission, SecurityRoles } from '../../Services/permissions';
import BackupPolicyDialog from './BackupPolicyDialog';
import RestoreFilesDialog from './RestoreFilesDialog';
import {
    apiDetail,
    coverageLabel,
    formatBytes,
    formatTime,
    reasonLabel,
    runStatusLabel,
    statusColor,
    statusLabel,
} from './backupLabels';

const HostBackupCard: React.FC<{ hostId: string }> = ({ hostId }) => {
    const { t } = useTranslation();
    const navigate = useNavigate();
    const [data, setData] = useState<HostBackup | null>(null);
    const [canManage, setCanManage] = useState(false);
    const [canRestore, setCanRestore] = useState(false);
    const [editing, setEditing] = useState(false);
    const [restoring, setRestoring] = useState(false);
    const [error, setError] = useState<string | null>(null);

    const load = useCallback(async () => {
        try {
            setData(await getHostBackup(hostId));
        } catch {
            setData(null);
        }
    }, [hostId]);

    useEffect(() => {
        void load();
        Promise.all([hasPermission(SecurityRoles.MANAGE_BACKUPS), hasPermission(SecurityRoles.RESTORE_FILES)])
            .then(([manage, restore]) => {
                setCanManage(manage);
                setCanRestore(restore);
            })
            .catch(() => undefined);
    }, [load]);

    if (!data) return null;

    const runNow = async () => {
        setError(null);
        try {
            await backupNow(hostId);
            await load();
        } catch (err) {
            setError(apiDetail(err, t('backups.hosts.backupNowError', 'The backup could not be started.')));
        }
    };

    return (
        <Card>
            <CardContent>
                <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 1 }}>
                    <BackupIcon />
                    <Typography variant="h6" sx={{ flexGrow: 1 }}>{t('backups.card.title', 'Backup')}</Typography>
                    <Chip size="small" color={statusColor(data.status)} label={statusLabel(t, data.status)} />
                </Stack>
                {error && <Alert severity="error" sx={{ mb: 1 }}>{error}</Alert>}
                {!data.equipped && data.reason && (
                    <Alert severity="warning" sx={{ mb: 1 }}>{reasonLabel(t, data.reason)}</Alert>
                )}
                {!data.target && (
                    <Typography variant="body2" color="text.secondary">
                        {t('backups.card.noTarget', 'No backup target is set up yet.')}
                    </Typography>
                )}
                <Typography variant="body2">
                    {t('backups.hosts.coverage', 'Coverage')}: {coverageLabel(t, data.coverage)}
                </Typography>
                {data.policy && (
                    <>
                        <Typography variant="body2">
                            {t('backups.hosts.lastBackup', 'Last backup')}: {formatTime(data.last_capture?.finished_at)}
                            {data.last_capture && ` (${runStatusLabel(t, data.last_capture)})`}
                        </Typography>
                        <Typography variant="body2">
                            {t('backups.card.lastCheck', 'Last check')}: {formatTime(data.last_check?.finished_at)}
                            {data.last_check && ` (${runStatusLabel(t, data.last_check)})`}
                        </Typography>
                        <Typography variant="body2">
                            {t('backups.hosts.nextDue', 'Next due')}: {formatTime(data.next_due)}
                        </Typography>
                        <Typography variant="body2">
                            {t('backups.hosts.snapshots', 'Snapshots: {{n}}', { n: data.snapshot_count })}
                            {' - '}{formatBytes(data.policy.repository_bytes)}
                        </Typography>
                    </>
                )}
                <Stack direction="row" spacing={1} sx={{ mt: 1, flexWrap: 'wrap', rowGap: 1 }}>
                    {canManage && data.target && (
                        <Button size="small" onClick={() => setEditing(true)}>
                            {t('backups.hosts.configure', 'Configure')}
                        </Button>
                    )}
                    {canManage && data.policy && (
                        <AsyncButton size="small" variant="outlined" onClick={runNow}
                            disabled={!data.equipped || !data.policy.configured || data.running?.action === 'capture'}
                            busyLabel={t('backups.hosts.starting', 'Starting...')}>
                            {t('backups.hosts.backupNow', 'Back up now')}
                        </AsyncButton>
                    )}
                    {canRestore && data.snapshot_count > 0 && (
                        <Button size="small" onClick={() => setRestoring(true)}>
                            {t('backups.hosts.restore', 'Restore files')}
                        </Button>
                    )}
                    <Button size="small" onClick={() => void navigate('/backups')}>
                        {t('backups.card.open', 'All backups')}
                    </Button>
                </Stack>
                {editing && (
                    <BackupPolicyDialog open hostId={hostId} fqdn={data.fqdn} policy={data.policy}
                        onClose={() => setEditing(false)} onSaved={() => void load()} />
                )}
                {restoring && (
                    <RestoreFilesDialog open hostId={hostId} fqdn={data.fqdn} onClose={() => setRestoring(false)} />
                )}
            </CardContent>
        </Card>
    );
};

export default HostBackupCard;
