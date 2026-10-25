// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

// Restore files (Phase 24, Community): preview first, then restore -- into
// the agent's staging directory on the host (the default), or into place over
// the host's own files at the paths named (24.9).  Into place needs specific
// paths and its own confirmation; restate checks the whole selection before
// writing and each file against the snapshot before it replaces the old one.
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
    Radio,
    RadioGroup,
    Select,
    Stack,
    TextField,
    Typography,
} from '@mui/material';
import { useTranslation } from 'react-i18next';
import AsyncButton from '../AsyncButton';
import { getRun, getSnapshots, restoreFiles } from '../../Services/backups';
import SnapshotBrowser from './SnapshotBrowser';
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
    /** false: restate planned from the snapshot's index and read no backed-up data. */
    content_read?: boolean;
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
            {result.content_read === false && (
                <Typography variant="caption" display="block" color="text.secondary">
                    {t('backups.restore.planned',
                        'Planned from the snapshot index. The backed-up data was not read, so its integrity was not checked here; the weekly check does that.')}
                </Typography>
            )}
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
    /** The host's restate can list a snapshot's folders (2.1.0.4+). */
    canBrowse?: boolean;
    onClose: () => void;
}> = ({ open, hostId, fqdn, canBrowse = false, onClose }) => {
    const { t } = useTranslation();
    const [snapshots, setSnapshots] = useState<BackupSnapshot[]>([]);
    const [snapshot, setSnapshot] = useState('');
    const [paths, setPaths] = useState('');
    const [excluded, setExcluded] = useState('');
    const [acknowledged, setAcknowledged] = useState(false);
    const [preview, setPreview] = useState<BackupRun | null>(null);
    const [restore, setRestore] = useState<BackupRun | null>(null);
    const [error, setError] = useState<string | null>(null);
    const [browsing, setBrowsing] = useState(false);
    const [inPlace, setInPlace] = useState(false);
    const [placeAck, setPlaceAck] = useState(false);

    useEffect(() => {
        if (!open) return;
        setPreview(null);
        setRestore(null);
        setError(null);
        setAcknowledged(false);
        setInPlace(false);
        setPlaceAck(false);
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
                in_place: inPlace,
                acknowledge_in_place: inPlace && placeAck,
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
    const blocked = (needsAck && !acknowledged) || (inPlace && include.length === 0);
    const chooseDestination = (place: boolean) => {
        setInPlace(place);
        setPlaceAck(false);
        setPreview(null);
    };
    return (
        <Dialog open={open} onClose={onClose} maxWidth="md" fullWidth>
            <DialogTitle>{t('backups.restore.title', 'Restore files to {{host}}', { host: fqdn })}</DialogTitle>
            <DialogContent>
                <Stack spacing={2} sx={{ mt: 1 }}>
                    <RadioGroup value={inPlace ? 'place' : 'staging'}
                        onChange={e => chooseDestination(e.target.value === 'place')}>
                        <FormControlLabel value="staging" control={<Radio size="small" />}
                            label={t('backups.restore.toStaging', 'Into a staging directory on the host')} />
                        <FormControlLabel value="place" control={<Radio size="small" />}
                            label={t('backups.restore.toPlace', 'Into place, replacing the host\'s files')} />
                    </RadioGroup>
                    {inPlace ? (
                        <Alert severity="warning">
                            {t('backups.restore.placeNote',
                                'The files at these paths on the host are replaced with the snapshot\'s copies. restate checks the whole selection before it writes anything, and each file against the snapshot before it replaces the old one. Name specific paths, such as /etc/nginx; a whole host is not restored in place. Preview first to see what would change.')}
                        </Alert>
                    ) : (
                        <Alert severity="info">
                            {t('backups.restore.stagingNote',
                                'Files are restored into a staging directory on the host, never over the live files. Move them into place yourself.')}
                        </Alert>
                    )}
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
                    {canBrowse && snapshot && (
                        <Box>
                            <Button size="small" onClick={() => setBrowsing(b => !b)}>
                                {browsing ? t('backups.browse.hide', 'Hide the snapshot\'s folders')
                                    : t('backups.browse.show', 'Browse the snapshot\'s folders')}
                            </Button>
                            {browsing && (
                                <SnapshotBrowser hostId={hostId} snapshot={snapshot} picked={include}
                                    onPick={path => { setPaths(text => (text.trim() ? `${text.trim()}\n${path}` : path)); setPreview(null); }} />
                            )}
                        </Box>
                    )}
                    <TextField multiline minRows={3}
                        label={inPlace ? t('backups.restore.placePaths', 'Paths to put back (one per line)')
                            : t('backups.restore.paths', 'Paths to restore (one per line; empty = everything)')}
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
                    {inPlace && (
                        <FormControlLabel
                            control={<Checkbox checked={placeAck} onChange={e => setPlaceAck(e.target.checked)} />}
                            label={t('backups.restore.placeAck', 'Replace the files at these paths on {{host}}.', { host: fqdn })}
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
                <AsyncButton onClick={() => send(true)} disabled={!snapshot || blocked}>
                    {t('backups.restore.preview', 'Preview')}
                </AsyncButton>
                <AsyncButton variant="contained" color={inPlace ? 'warning' : 'primary'} onClick={() => send(false)}
                    disabled={!previewDone || restore !== null || blocked || (inPlace && !placeAck)}>
                    {inPlace ? t('backups.restore.confirmPlace', 'Restore into place')
                        : t('backups.restore.confirm', 'Restore to staging')}
                </AsyncButton>
            </DialogActions>
        </Dialog>
    );
};

export default RestoreFilesDialog;
