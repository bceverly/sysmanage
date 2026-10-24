// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

// What changed on this host since its newest snapshot (ROADMAP 24.2,
// restate 2.1.0.4's `status` as a job): how many paths were added, deleted
// and modified, and the first of each with what changed (content, mode,
// owner).  A file whose size, times and inode are unchanged is not read, so
// the check is quick.

import React, { useEffect, useState } from 'react';
import {
    Alert,
    Button,
    CircularProgress,
    Dialog,
    DialogActions,
    DialogContent,
    DialogTitle,
    Stack,
    Table,
    TableBody,
    TableCell,
    TableHead,
    TableRow,
    Typography,
} from '@mui/material';
import { useTranslation } from 'react-i18next';
import type { TFunction } from 'i18next';
import { backupChanges, getRun } from '../../Services/backups';
import type { BackupRun } from '../../Services/backups';
import { apiDetail } from './backupLabels';

const FINISHED = new Set(['ok', 'different', 'incomplete', 'failed', 'untrusted', 'busy']);
const POLL_MS = 2000;
const SHOWN = 200;

interface Change {
    change: 'A' | 'D' | 'M';
    path: string;
    what?: string;
}

interface Diff {
    added: number;
    deleted: number;
    modified: number;
    changes: Change[];
    truncated?: boolean;
}

const diffOf = (run: BackupRun): Diff | null => {
    const found = (run.result as { diff?: Diff } | null)?.diff;
    return found && Array.isArray(found.changes) ? found : null;
};

const changeLabel = (t: TFunction, change: Change['change']): string =>
    ({ A: t('backups.changes.added', 'Added'), D: t('backups.changes.deleted', 'Deleted'),
       M: t('backups.changes.modified', 'Modified') })[change] ?? change;

const BackupChangesDialog: React.FC<{ hostId: string; fqdn: string; onClose: () => void }> = ({
    hostId,
    fqdn,
    onClose,
}) => {
    const { t } = useTranslation();
    const [run, setRun] = useState<BackupRun | null>(null);
    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
        let alive = true;
        let timer: ReturnType<typeof setTimeout> | undefined;
        const poll = async (id: string) => {
            const fresh = await getRun(id);
            if (!alive) return;
            setRun(fresh);
            if (!FINISHED.has(fresh.status)) timer = setTimeout(() => void poll(id).catch(() => undefined), POLL_MS);
        };
        backupChanges(hostId)
            .then(started => { if (alive) { setRun(started); void poll(started.id); } })
            .catch(err => { if (alive) setError(apiDetail(err, t('backups.changes.error', 'The check could not be started.'))); });
        return () => { alive = false; if (timer) clearTimeout(timer); };
    }, [hostId, t]);

    const done = run && FINISHED.has(run.status);
    const diff = done ? diffOf(run) : null;

    return (
        <Dialog open onClose={onClose} maxWidth="md" fullWidth>
            <DialogTitle>{t('backups.changes.title', 'What changed on {{host}} since its last backup', { host: fqdn })}</DialogTitle>
            <DialogContent>
                {error && <Alert severity="error">{error}</Alert>}
                {!error && !done && (
                    <Stack direction="row" spacing={1} alignItems="center">
                        <CircularProgress size={16} />
                        <Typography variant="body2">{t('backups.changes.running', 'Comparing the host with its newest snapshot...')}</Typography>
                    </Stack>
                )}
                {done && !diff && (
                    <Alert severity="error">{run?.message || t('backups.changes.error', 'The check could not be started.')}</Alert>
                )}
                {diff && (
                    <>
                        <Typography variant="body2" sx={{ mb: 1 }}>
                            {t('backups.changes.counts', 'Added: {{added}}, deleted: {{deleted}}, modified: {{modified}}',
                                { added: diff.added, deleted: diff.deleted, modified: diff.modified })}
                        </Typography>
                        {diff.changes.length > 0 && (
                            <Table size="small">
                                <TableHead>
                                    <TableRow>
                                        <TableCell>{t('backups.changes.change', 'Change')}</TableCell>
                                        <TableCell>{t('backups.changes.path', 'File or folder')}</TableCell>
                                        <TableCell>{t('backups.changes.what', 'What changed')}</TableCell>
                                    </TableRow>
                                </TableHead>
                                <TableBody>
                                    {diff.changes.slice(0, SHOWN).map(change => (
                                        <TableRow key={change.change + change.path}>
                                            <TableCell>{changeLabel(t, change.change)}</TableCell>
                                            <TableCell sx={{ wordBreak: 'break-all' }}>{change.path}</TableCell>
                                            <TableCell>{change.what ?? ''}</TableCell>
                                        </TableRow>
                                    ))}
                                </TableBody>
                            </Table>
                        )}
                        {(diff.truncated || diff.changes.length > SHOWN) && (
                            <Typography variant="caption" color="text.secondary">
                                {t('backups.changes.more', 'Only the first changes are shown.')}
                            </Typography>
                        )}
                    </>
                )}
            </DialogContent>
            <DialogActions>
                <Button onClick={onClose}>{t('common.close', 'Close')}</Button>
            </DialogActions>
        </Dialog>
    );
};

export default BackupChangesDialog;
