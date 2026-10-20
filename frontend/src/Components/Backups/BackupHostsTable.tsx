// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

// Every approved host's backup standing (Phase 24), worst first, with what
// an operator can do about it: configure, back up now, restore files.

import React, { useState } from 'react';
import {
    Button,
    Chip,
    LinearProgress,
    Stack,
    Table,
    TableBody,
    TableCell,
    TableHead,
    TableRow,
    Tooltip,
    Typography,
} from '@mui/material';
import { useTranslation } from 'react-i18next';
import AsyncButton from '../AsyncButton';
import { backupNow, BACKUP_STATUS_ORDER } from '../../Services/backups';
import type { BackupHost } from '../../Services/backups';
import BackupPolicyDialog from './BackupPolicyDialog';
import RestoreFilesDialog from './RestoreFilesDialog';
import {
    apiDetail,
    coverageLabel,
    formatBytes,
    formatTime,
    reasonLabel,
    statusColor,
    statusLabel,
} from './backupLabels';

const rank = (row: BackupHost) => BACKUP_STATUS_ORDER.indexOf(row.status);

export const sortHosts = (rows: BackupHost[]): BackupHost[] =>
    [...rows].sort((a, b) => rank(a) - rank(b) || a.fqdn.localeCompare(b.fqdn));

const Progress: React.FC<{ row: BackupHost }> = ({ row }) => {
    const { t } = useTranslation();
    const progress = row.running?.progress;
    if (!row.running) return null;
    return (
        <Tooltip title={progress?.phase ?? ''}>
            <Stack spacing={0.5} sx={{ mt: 0.5, minWidth: 140 }}>
                <LinearProgress />
                <Typography variant="caption" color="text.secondary">
                    {progress
                        ? t('backups.hosts.progress', '{{paths}} paths, {{size}} read', {
                              paths: progress.paths ?? 0,
                              size: formatBytes(progress.read_bytes ?? 0),
                          })
                        : t('backups.run.queued', 'Queued')}
                </Typography>
            </Stack>
        </Tooltip>
    );
};

const StatusCell: React.FC<{ row: BackupHost }> = ({ row }) => {
    const { t } = useTranslation();
    return (
        <TableCell>
            <Chip size="small" color={statusColor(row.status)} label={statusLabel(t, row.status)} />
            {!row.equipped && row.reason && (
                <Typography variant="caption" display="block" color="warning.main">
                    {reasonLabel(t, row.reason)}
                </Typography>
            )}
            <Progress row={row} />
        </TableCell>
    );
};

const BackupHostsTable: React.FC<{
    rows: BackupHost[];
    hasTarget: boolean;
    canManage: boolean;
    canRestore: boolean;
    onChanged: () => void;
    onError: (message: string) => void;
}> = ({ rows, hasTarget, canManage, canRestore, onChanged, onError }) => {
    const { t } = useTranslation();
    const [editing, setEditing] = useState<BackupHost | null>(null);
    const [restoring, setRestoring] = useState<BackupHost | null>(null);

    const runNow = async (row: BackupHost) => {
        try {
            await backupNow(row.host_id);
            onChanged();
        } catch (err) {
            onError(apiDetail(err, t('backups.hosts.backupNowError', 'The backup could not be started.')));
        }
    };

    return (
        <>
            <Table size="small">
                <TableHead>
                    <TableRow>
                        <TableCell>{t('backups.hosts.host', 'Host')}</TableCell>
                        <TableCell>{t('backups.hosts.status', 'Status')}</TableCell>
                        <TableCell>{t('backups.hosts.lastBackup', 'Last backup')}</TableCell>
                        <TableCell>{t('backups.hosts.nextDue', 'Next due')}</TableCell>
                        <TableCell>{t('backups.hosts.size', 'Repository')}</TableCell>
                        <TableCell>{t('backups.hosts.coverage', 'Coverage')}</TableCell>
                        <TableCell align="right">{t('backups.hosts.actions', 'Actions')}</TableCell>
                    </TableRow>
                </TableHead>
                <TableBody>
                    {sortHosts(rows).map(row => (
                        <TableRow key={row.host_id}>
                            <TableCell>
                                <Typography variant="body2">{row.fqdn}</Typography>
                                {row.policy?.restate_version && (
                                    <Typography variant="caption" color="text.secondary">
                                        {t('backups.hosts.restateVersion', 'restate {{version}}', {
                                            version: row.policy.restate_version,
                                        })}
                                    </Typography>
                                )}
                            </TableCell>
                            <StatusCell row={row} />
                            <TableCell>
                                {formatTime(row.last_good_capture?.finished_at)}
                                {row.snapshot_count > 0 && (
                                    <Typography variant="caption" display="block" color="text.secondary">
                                        {t('backups.hosts.snapshots', 'Snapshots: {{n}}', { n: row.snapshot_count })}
                                    </Typography>
                                )}
                            </TableCell>
                            <TableCell>{formatTime(row.next_due)}</TableCell>
                            <TableCell>{formatBytes(row.policy?.repository_bytes)}</TableCell>
                            <TableCell>{coverageLabel(t, row.coverage)}</TableCell>
                            <TableCell align="right">
                                <Stack direction="row" spacing={1} justifyContent="flex-end">
                                    {canManage && hasTarget && (
                                        <Button size="small" onClick={() => setEditing(row)}>
                                            {t('backups.hosts.configure', 'Configure')}
                                        </Button>
                                    )}
                                    {canManage && row.policy && (
                                        <AsyncButton size="small" variant="outlined"
                                            disabled={!row.equipped || !row.policy.configured || row.running?.action === 'capture'}
                                            onClick={() => runNow(row)}
                                            busyLabel={t('backups.hosts.starting', 'Starting...')}>
                                            {t('backups.hosts.backupNow', 'Back up now')}
                                        </AsyncButton>
                                    )}
                                    {canRestore && row.snapshot_count > 0 && (
                                        <Button size="small" onClick={() => setRestoring(row)}>
                                            {t('backups.hosts.restore', 'Restore files')}
                                        </Button>
                                    )}
                                </Stack>
                            </TableCell>
                        </TableRow>
                    ))}
                </TableBody>
            </Table>
            {editing && (
                <BackupPolicyDialog open hostId={editing.host_id} fqdn={editing.fqdn} policy={editing.policy}
                    onClose={() => setEditing(null)} onSaved={onChanged} />
            )}
            {restoring && (
                <RestoreFilesDialog open hostId={restoring.host_id} fqdn={restoring.fqdn}
                    onClose={() => setRestoring(null)} />
            )}
        </>
    );
};

export default BackupHostsTable;
