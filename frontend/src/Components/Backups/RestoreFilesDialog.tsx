// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

// Restore files (Phase 24, Community): preview first, then restore -- always
// into the agent's staging directory on the host, never over the live files.
// Snapshots are not signed in Community, so the operator says so explicitly.

import React, { useCallback, useEffect, useState } from 'react';
import {
    Alert,
    Box,
    Button,
    Checkbox,
    CircularProgress,
    Dialog,
    DialogActions,
    DialogContent,
    DialogTitle,
    FormControl,
    FormControlLabel,
    InputLabel,
    MenuItem,
    Select,
    Stack,
    TextField,
    Typography,
} from '@mui/material';
import { useTranslation } from 'react-i18next';
import AsyncButton from '../AsyncButton';
import { getRun, getSnapshots, restoreFiles } from '../../Services/backups';
import type { BackupRun, BackupSnapshot } from '../../Services/backups';
import { apiDetail, formatBytes, formatTime, runStatusLabel } from './backupLabels';

const FINISHED = new Set(['ok', 'different', 'incomplete', 'failed', 'untrusted', 'busy']);
const PLAN_SHOWN = 50;

interface RestoreResult {
    files?: number;
    bytes?: number;
    refused?: unknown[];
    missing?: unknown[];
    plan?: unknown[];
    plan_count?: number;
}

const planLine = (entry: unknown): string => {
    if (typeof entry === 'string') return entry;
    const path = (entry as { path?: unknown })?.path;
    return typeof path === 'string' ? path : JSON.stringify(entry);
};

const RunOutcome: React.FC<{ run: BackupRun }> = ({ run }) => {
    const { t } = useTranslation();
    if (!FINISHED.has(run.status)) {
        return (
            <Stack direction="row" spacing={1} alignItems="center">
                <CircularProgress size={18} />
                <Typography variant="body2">{runStatusLabel(t, run)}</Typography>
            </Stack>
        );
    }
    const result = (run.result ?? {}) as RestoreResult;
    const plan = Array.isArray(result.plan) ? result.plan : [];
    return (
        <Box>
            <Alert severity={run.status === 'ok' ? 'success' : 'warning'} sx={{ mb: 1 }}>
                {runStatusLabel(t, run)}
                {run.message ? `: ${run.message}` : ''}
            </Alert>
            <Typography variant="body2">
                {t('backups.restore.counts', 'Files: {{files}}, size: {{size}}', {
                    files: result.files ?? result.plan_count ?? 0,
                    size: formatBytes(result.bytes ?? 0),
                })}
                {Array.isArray(result.refused) && result.refused.length > 0
                    && ` - ${t('backups.restore.refused', 'Refused: {{n}}', { n: result.refused.length })}`}
                {Array.isArray(result.missing) && result.missing.length > 0
                    && ` - ${t('backups.restore.missing', 'Not in the snapshot: {{n}}', { n: result.missing.length })}`}
            </Typography>
            {plan.length > 0 && (
                <Box component="pre" sx={{ maxHeight: 200, overflow: 'auto', fontSize: 12, bgcolor: 'action.hover', p: 1 }}>
                    {plan.slice(0, PLAN_SHOWN).map(planLine).join('\n')}
                    {(result.plan_count ?? plan.length) > PLAN_SHOWN
                        && `\n${t('backups.restore.more', 'Not shown: {{n}}', {
                            n: (result.plan_count ?? plan.length) - PLAN_SHOWN,
                        })}`}
                </Box>
            )}
        </Box>
    );
};

const RestoreFilesDialog: React.FC<{
    open: boolean;
    hostId: string;
    fqdn: string;
    onClose: () => void;
}> = ({ open, hostId, fqdn, onClose }) => {
    const { t } = useTranslation();
    const [snapshots, setSnapshots] = useState<BackupSnapshot[]>([]);
    const [snapshot, setSnapshot] = useState('');
    const [paths, setPaths] = useState('');
    const [excluded, setExcluded] = useState('');
    const [acknowledged, setAcknowledged] = useState(false);
    const [preview, setPreview] = useState<BackupRun | null>(null);
    const [restore, setRestore] = useState<BackupRun | null>(null);
    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
        if (!open) return;
        setPreview(null);
        setRestore(null);
        setError(null);
        setAcknowledged(false);
        getSnapshots(hostId)
            .then(rows => {
                setSnapshots(rows);
                setSnapshot(rows[0]?.name ?? '');
            })
            .catch(() => setError(t('backups.restore.loadError', 'Could not load the snapshots.')));
    }, [open, hostId, t]);

    const active = restore ?? preview;
    const refresh = useCallback(async () => {
        if (!active || FINISHED.has(active.status)) return;
        const fresh = await getRun(active.id);
        if (restore) setRestore(fresh);
        else setPreview(fresh);
    }, [active, restore]);

    useEffect(() => {
        if (!active || FINISHED.has(active.status)) return undefined;
        const timer = setInterval(() => void refresh().catch(() => undefined), 3000);
        return () => clearInterval(timer);
    }, [active, refresh]);

    const selected = snapshots.find(s => s.name === snapshot);
    const needsAck = selected ? !selected.signed : true;
    const lines = (text: string) => text.split('\n').map(p => p.trim()).filter(Boolean);
    const include = lines(paths);
    const exclude = lines(excluded);

    const send = async (dryRun: boolean) => {
        setError(null);
        try {
            const run = await restoreFiles(hostId, {
                snapshot,
                include,
                exclude,
                dry_run: dryRun,
                acknowledge_unsigned: acknowledged,
            });
            if (dryRun) {
                setPreview(run);
                setRestore(null);
            } else {
                setRestore(run);
            }
        } catch (err) {
            setError(apiDetail(err, t('backups.restore.error', 'The restore could not be requested.')));
        }
    };

    const previewDone = preview !== null && preview.status === 'ok';
    return (
        <Dialog open={open} onClose={onClose} maxWidth="md" fullWidth>
            <DialogTitle>{t('backups.restore.title', 'Restore files to {{host}}', { host: fqdn })}</DialogTitle>
            <DialogContent>
                <Stack spacing={2} sx={{ mt: 1 }}>
                    <Alert severity="info">
                        {t('backups.restore.stagingNote',
                            'Files are restored into a staging directory on the host, never over the live files. Move them into place yourself.')}
                    </Alert>
                    {error && <Alert severity="error">{error}</Alert>}
                    {snapshots.length === 0 && !error ? (
                        <Typography variant="body2">{t('backups.restore.noSnapshots', 'This host has no snapshots yet.')}</Typography>
                    ) : (
                        <FormControl fullWidth>
                            <InputLabel id="restore-snapshot">{t('backups.restore.snapshot', 'Snapshot')}</InputLabel>
                            <Select labelId="restore-snapshot" label={t('backups.restore.snapshot', 'Snapshot')}
                                value={snapshot} onChange={e => { setSnapshot(e.target.value); setPreview(null); }}>
                                {snapshots.map(s => (
                                    <MenuItem key={s.id} value={s.name}>
                                        {s.name} ({formatTime(s.created_at)}, {formatBytes(s.bytes)})
                                    </MenuItem>
                                ))}
                            </Select>
                        </FormControl>
                    )}
                    <TextField multiline minRows={3} label={t('backups.restore.paths', 'Paths to restore (one per line; empty = everything)')}
                        value={paths} onChange={e => { setPaths(e.target.value); setPreview(null); }}
                        placeholder="/etc/nginx" />
                    <TextField multiline minRows={2} label={t('backups.restore.exclude', 'Paths to leave out (one per line)')}
                        value={excluded} onChange={e => { setExcluded(e.target.value); setPreview(null); }} />
                    {needsAck && (
                        <FormControlLabel
                            control={<Checkbox checked={acknowledged} onChange={e => setAcknowledged(e.target.checked)} />}
                            label={t('backups.restore.unsignedAck', 'This snapshot is not signed. Restore it anyway.')}
                        />
                    )}
                    {preview && <RunOutcome run={preview} />}
                    {restore && (
                        <Box>
                            <RunOutcome run={restore} />
                            {restore.staging_path && (
                                <Typography variant="body2" sx={{ mt: 1 }}>
                                    {t('backups.restore.stagedAt', 'Staged on the host at')}: <code>{restore.staging_path}</code>
                                </Typography>
                            )}
                        </Box>
                    )}
                </Stack>
            </DialogContent>
            <DialogActions>
                <Button onClick={onClose}>{t('common.close', 'Close')}</Button>
                <AsyncButton onClick={() => send(true)} disabled={!snapshot || (needsAck && !acknowledged)}>
                    {t('backups.restore.preview', 'Preview')}
                </AsyncButton>
                <AsyncButton variant="contained" onClick={() => send(false)}
                    disabled={!previewDone || restore !== null || (needsAck && !acknowledged)}>
                    {t('backups.restore.confirm', 'Restore to staging')}
                </AsyncButton>
            </DialogActions>
        </Dialog>
    );
};

export default RestoreFilesDialog;
