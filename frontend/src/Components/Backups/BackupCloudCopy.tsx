// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

/**
 * The off-site cloud copy card (ROADMAP 27.3): "two is one, one is none".
 * The storage host's datasets, encrypted with a key only the operator holds,
 * in their own S3 bucket (Glacier Deep Archive by default).  Setting it up
 * and running it is Professional+; the record of what is in the bucket, the
 * restore and the key export work in every edition, also after a lapse.
 * Hidden on an air-gapped site.
 */

import React, { useCallback, useEffect, useState } from 'react';
import {
    Alert, Button, Chip, Paper, Stack, Table, TableBody, TableCell, TableHead, TableRow, Typography,
} from '@mui/material';
import { useTranslation } from 'react-i18next';
import type { TFunction } from 'i18next';

import {
    CloudCopy, CloudCopyOverview, CloudCopyRun, checkCloudCopy, getCloudCopies, getCloudCopyRuns,
    rotateCloudCopyKey, runCloudCopy, updateCloudCopy,
} from '../../Services/backupCloudCopy';
import { apiDetail, formatBytes, formatTime } from './backupLabels';
import {
    CloudCopyDialog, CloudKeyExportDialog, CloudRestoreDialog, CloudSetupGuideDialog,
} from './CloudCopyDialogs';

type Open = null | 'setup' | 'edit' | 'restore' | 'export' | 'guide';

// A job's result arrives from the storage host after the button returns, so
// the card keeps asking while one is waiting or running.
const POLL_MS = 3000;
const inFlight = (run: CloudCopyRun | undefined) => run?.status === 'queued' || run?.status === 'running';

// What the storage host last reported about a job in flight (about every 30 seconds).
const progressText = (progress: CloudCopyRun['progress'], t: TFunction): string | null => {
    if (!progress) return null;
    const count = (key: string) => Number(progress[key] ?? 0);
    if (progress.phase === 'thawing') {
        return t('backups.cloudCopy.progress.thawing', 'Thawing: {{ready}} of {{total}} parts ready', {
            ready: count('parts_ready'), total: count('parts_total'),
        });
    }
    if (progress.phase === 'receiving') {
        return t('backups.cloudCopy.progress.receiving', '{{size}} downloaded and received so far', {
            size: formatBytes(count('bytes_received')),
        });
    }
    if (progress.dataset === undefined) return null;
    return t('backups.cloudCopy.progress.upload', '{{dataset}}: {{size}} sent so far ({{done}} of {{total}} datasets done)', {
        dataset: String(progress.dataset), size: formatBytes(count('bytes_uploaded')),
        done: count('datasets_done'), total: count('datasets_total'),
    });
};

const RunLine: React.FC<{ run: CloudCopyRun | undefined }> = ({ run }) => {
    const { t } = useTranslation();
    if (!run) return null;
    const labels: Record<string, string> = {
        check: t('backups.cloudCopy.action.check', 'Check'),
        upload: t('backups.cloudCopy.action.upload', 'Upload'),
        restore: t('backups.cloudCopy.action.restore', 'Restore'),
    };
    const statuses: Record<string, string> = {
        queued: t('backups.cloudCopy.status.queued', 'queued'),
        running: t('backups.cloudCopy.status.running', 'running'),
        ok: t('backups.cloudCopy.status.ok', 'done'),
        partial: t('backups.cloudCopy.status.partial', 'partly done'),
        failed: t('backups.cloudCopy.status.failed', 'failed'),
        interrupted: t('backups.cloudCopy.status.interrupted', 'interrupted, resumes next run'),
    };
    const progress = inFlight(run) ? progressText(run.progress, t) : null;
    return (
        <>
        <Typography variant="body2">
            {t('backups.cloudCopy.lastRun', 'Last job: {{action}} {{status}}, {{when}}', {
                action: labels[run.action], status: statuses[run.status], when: formatTime(run.finished_at ?? run.queued_at),
            })}
            {run.message ? ` - ${run.message}` : ''}
        </Typography>
        {progress && <Typography variant="body2" color="text.secondary">{progress}</Typography>}
        </>
    );
};

const CopyPanel: React.FC<{
    copy: CloudCopy;
    targetName: string;
    canManage: boolean;
    canRestore: boolean;
    onOpen: (what: Open) => void;
    onChanged: () => void;
    onRefresh: () => void;
}> = ({ copy, targetName, canManage, canRestore, onOpen, onChanged, onRefresh }) => {
    const { t } = useTranslation();
    const [runs, setRuns] = useState<CloudCopyRun[]>([]);
    const [error, setError] = useState('');
    const [notice, setNotice] = useState('');

    useEffect(() => {
        getCloudCopyRuns(copy.id).then(setRuns).catch(() => setRuns([]));
    }, [copy.id, copy.last_run_id]);

    const busy = inFlight(runs[0]);
    useEffect(() => {
        if (!busy) return undefined;
        const timer = setInterval(() => {
            getCloudCopyRuns(copy.id).then(next => {
                setRuns(next);
                onRefresh();
            }).catch(() => undefined);
        }, POLL_MS);
        return () => clearInterval(timer);
    }, [busy, copy.id, onRefresh]);

    const act = (call: () => Promise<unknown>, done?: (result: unknown) => string) => async () => {
        setError('');
        setNotice('');
        try {
            const result = await call();
            if (done) setNotice(done(result));
            onChanged();
        } catch (err) {
            setError(apiDetail(err, t('backups.cloudCopy.actionFailed', 'That could not be done.')));
        }
    };

    const lock = copy.lock_verified === true ? t('backups.cloudCopy.lockOn', 'Object Lock on')
        : copy.lock_verified === false ? t('backups.cloudCopy.lockOff', 'Object Lock OFF') : null;

    return (
        <Stack spacing={1} sx={{ mb: 2 }}>
            <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap">
                <Typography variant="subtitle1">
                    {t('backups.cloudCopy.where', '{{target}} to s3://{{bucket}}/{{prefix}} ({{region}}, {{storageClass}})', {
                        target: targetName, bucket: copy.bucket, prefix: copy.prefix, region: copy.region,
                        storageClass: copy.storage_class,
                    })}
                </Typography>
                {!copy.enabled && <Chip size="small" label={t('backups.cloudCopy.off', 'Off')} />}
                {copy.overdue && <Chip size="small" color="error" label={t('backups.cloudCopy.overdue', 'Overdue')} />}
                {lock && <Chip size="small" color={copy.lock_verified ? 'success' : 'warning'} label={lock} />}
            </Stack>
            <Typography variant="body2">
                {t('backups.cloudCopy.stored', '{{size}} stored; last good upload {{when}}; next {{next}}', {
                    size: formatBytes(copy.bytes_stored),
                    when: copy.last_ok_at ? formatTime(copy.last_ok_at) : t('backups.cloudCopy.never', 'never'),
                    next: copy.enabled && copy.next_run_at ? formatTime(copy.next_run_at) : '-',
                })}
                {copy.cost ? ` ${t('backups.cloudCopy.cost', '(about {{usd}} a month)', { usd: `$${copy.cost.monthly_usd.toFixed(2)}` })}` : ''}
            </Typography>
            <RunLine run={runs[0]} />
            {copy.last_error && <Alert severity="warning">{copy.last_error}</Alert>}
            {!copy.licensed && (
                <Alert severity="info">
                    {t('backups.cloudCopy.frozen', 'Without Professional+ the copy is frozen: no new uploads, and everything in the bucket can still be restored.')}
                </Alert>
            )}
            {copy.datasets.length > 0 && (
                <Table size="small">
                    <TableHead>
                        <TableRow>
                            <TableCell>{t('backups.cloudCopy.dataset', 'Dataset')}</TableCell>
                            <TableCell>{t('backups.cloudCopy.lastUpload', 'Last upload')}</TableCell>
                            <TableCell>{t('backups.cloudCopy.lastFull', 'Last full')}</TableCell>
                            <TableCell align="right">{t('backups.cloudCopy.size', 'Stored')}</TableCell>
                        </TableRow>
                    </TableHead>
                    <TableBody>
                        {copy.datasets.map(d => (
                            <TableRow key={d.dataset}>
                                <TableCell>{d.dataset}</TableCell>
                                <TableCell>{formatTime(d.last_uploaded_at ?? null)}</TableCell>
                                <TableCell>{formatTime(d.last_full_at)}</TableCell>
                                <TableCell align="right">{formatBytes(d.bytes_stored)}</TableCell>
                            </TableRow>
                        ))}
                    </TableBody>
                </Table>
            )}
            {error && <Alert severity="error">{error}</Alert>}
            {notice && <Alert severity="success" onClose={() => setNotice('')}>{notice}</Alert>}
            <Stack direction="row" spacing={1} flexWrap="wrap">
                {canManage && copy.licensed && (
                    <Button size="small" onClick={act(() => runCloudCopy(copy.id))}>{t('backups.cloudCopy.runNow', 'Run now')}</Button>
                )}
                {canManage && (
                    <Button size="small" onClick={act(() => checkCloudCopy(copy.id))}>{t('backups.cloudCopy.check', 'Check the bucket')}</Button>
                )}
                {canRestore && <Button size="small" onClick={() => onOpen('restore')}>{t('backups.cloudCopy.restore', 'Restore')}</Button>}
                {canManage && copy.licensed && <Button size="small" onClick={() => onOpen('edit')}>{t('backups.cloudCopy.settings', 'Settings')}</Button>}
                {copy.licensed && <Button size="small" onClick={() => onOpen('guide')}>{t('backups.cloudCopy.guide', 'Bucket setup')}</Button>}
                {canManage && copy.licensed && (
                    <Button size="small" onClick={act(() => rotateCloudCopyKey(copy.id), result => t('backups.cloudCopy.rotated',
                        'New key {{key}} made. The next upload is a full copy under it. Export the keys again: an earlier export does not hold this key.',
                        { key: (result as CloudCopy).key_id ?? '' }))}>
                        {t('backups.cloudCopy.rotate', 'New key')}
                    </Button>
                )}
                {canManage && canRestore && (
                    <Button size="small" onClick={() => onOpen('export')}>{t('backups.cloudCopy.export', 'Export keys')}</Button>
                )}
                {canManage && copy.enabled && (
                    <Button size="small" color="warning" onClick={act(() => updateCloudCopy(copy.id, { enabled: false }))}>
                        {t('backups.cloudCopy.turnOff', 'Turn off')}
                    </Button>
                )}
                {canManage && !copy.enabled && copy.licensed && (
                    <Button size="small" onClick={act(() => updateCloudCopy(copy.id, { enabled: true }))}>
                        {t('backups.cloudCopy.turnOn', 'Turn on')}
                    </Button>
                )}
            </Stack>
        </Stack>
    );
};

const BackupCloudCopy: React.FC<{ canManage: boolean; canRestore: boolean; refreshKey?: number }> = ({
    canManage, canRestore, refreshKey,
}) => {
    const { t } = useTranslation();
    const [data, setData] = useState<CloudCopyOverview | null>(null);
    const [open, setOpen] = useState<{ what: Open; copy: CloudCopy | null }>({ what: null, copy: null });
    const [tick, setTick] = useState(0);

    const load = useCallback(() => {
        getCloudCopies().then(setData).catch(() => setData(null));
    }, []);
    useEffect(load, [load, refreshKey, tick]);
    const refresh = useCallback(() => setTick(n => n + 1), []);

    if (!data || !data.available) return null;
    if (!data.copies.length && !data.licensed) return null;
    const changed = () => {
        setOpen({ what: null, copy: null });
        setTick(n => n + 1);
    };
    const name = (id: string) => data.targets.find(tg => tg.id === id)?.name ?? id;
    const free = data.targets.some(tg => tg.has_storage_host && !data.copies.some(c => c.target_id === tg.id));

    return (
        <Paper sx={{ p: 2, mb: 2 }}>
            <Typography variant="h6">{t('backups.cloudCopy.title', 'Cloud copy (off-site)')}</Typography>
            <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
                {t('backups.cloudCopy.intro', "Two is one, one is none: an encrypted copy of the storage host's backups in your own S3 bucket, for the day the site is gone.")}
            </Typography>
            {data.copies.map(copy => (
                <CopyPanel key={copy.id} copy={copy} targetName={name(copy.target_id)} canManage={canManage}
                           canRestore={canRestore} onChanged={changed} onRefresh={refresh}
                           onOpen={what => setOpen({ what, copy })} />
            ))}
            {canManage && data.licensed && free && (
                <Button variant="outlined" onClick={() => setOpen({ what: 'setup', copy: null })}>
                    {t('backups.cloudCopy.setUp', 'Set up the cloud copy')}
                </Button>
            )}
            {(open.what === 'setup' || open.what === 'edit') && (
                <CloudCopyDialog copy={open.copy} overview={data} onClose={() => setOpen({ what: null, copy: null })} onSaved={changed} />
            )}
            {open.what === 'restore' && open.copy && (
                <CloudRestoreDialog copy={open.copy} onClose={() => setOpen({ what: null, copy: null })} onStarted={changed} />
            )}
            {open.what === 'export' && open.copy && (
                <CloudKeyExportDialog copy={open.copy} onClose={() => setOpen({ what: null, copy: null })} />
            )}
            {open.what === 'guide' && open.copy && (
                <CloudSetupGuideDialog copy={open.copy} onClose={() => setOpen({ what: null, copy: null })} />
            )}
        </Paper>
    );
};

export default BackupCloudCopy;
