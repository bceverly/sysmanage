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
import RestoreNotes from './RestoreNotes';
import PackageRestoreSummary from './PackageRestoreSummary';
import type { BackupRun, BackupSnapshot, OffsiteCopy } from '../../Services/backups';
import { apiDetail, formatBytes, formatTime, runStatusLabel } from './backupLabels';
import { FINISHED } from './pollRun';

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
    // restate 2.2 nests a restore's counts and plan under ``restore``;
    // earlier results had them at the top.
    const raw = (run.result ?? {}) as RestoreResult & { restore?: RestoreResult };
    const result: RestoreResult = { ...raw, ...raw.restore };
    const plan = Array.isArray(result.plan) ? result.plan : [];
    const nothing = run.status === 'ok' && !(result.files ?? result.plan_count ?? 0);
    return (
        <Box>
            {nothing ? (
                <Alert severity="warning" sx={{ mb: 1 }}>
                    {t('backups.restore.nothing', 'Nothing in the snapshot matches these paths. Check the spelling, and give absolute paths such as /home/alice/notes.txt.')}
                </Alert>
            ) : (
                <Alert severity={run.status === 'ok' ? 'success' : 'warning'} sx={{ mb: 1 }}>
                    {runStatusLabel(t, run)}
                    {run.message ? `: ${run.message}` : ''}
                </Alert>
            )}
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
            <RestoreNotes run={run} />
            <PackageRestoreSummary run={run} />
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
    /** Packages can be put back first (Pro+ 24.6: the engine and the ability). */
    canPackages?: boolean;
    /** The host's off-site copies (27.3): a restore may come from one. */
    offsite?: OffsiteCopy[];
    onClose: () => void;
}> = ({ open, hostId, fqdn, canBrowse = false, canPackages = false, offsite = [], onClose }) => {
    const { t } = useTranslation();
    const [catalog, setCatalog] = useState<BackupSnapshot[]>([]);
    // '' = this site's storage; else the off-site copy's id.
    const [source, setSource] = useState('');
    const copies = offsite.filter(copy => copy.readable);
    const copy = copies.find(c => c.id === source);
    const [snapshot, setSnapshot] = useState('');
    const [paths, setPaths] = useState('');
    const [excluded, setExcluded] = useState('');
    const [acknowledged, setAcknowledged] = useState(false);
    const [preview, setPreview] = useState<BackupRun | null>(null);
    const [restore, setRestore] = useState<BackupRun | null>(null);
    // Four-eyes approval (27.2, Enterprise): held for a second approver.
    const [awaiting, setAwaiting] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [browsing, setBrowsing] = useState(false);
    const [inPlace, setInPlace] = useState(false);
    const [placeAck, setPlaceAck] = useState(false);
    const [packages, setPackages] = useState(false);
    const [packagesAck, setPackagesAck] = useState(false);

    useEffect(() => {
        if (!open) return;
        setPreview(null);
        setRestore(null);
        setError(null);
        setAcknowledged(false);
        setInPlace(false);
        setPlaceAck(false);
        setPackages(false);
        setPackagesAck(false);
        setSource('');
        getSnapshots(hostId)
            .then(rows => {
                setCatalog(rows);
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

    // From the off-site copy: the snapshots it holds, newest first, with
    // what this site's catalog still knows of each (signed, size).
    const snapshots: BackupSnapshot[] = copy
        ? [...(copy.snapshots ?? [])].reverse().map(name =>
            catalog.find(s => s.name === name)
            ?? ({ id: name, name, signed: false, created_at: null, bytes: null } as unknown as BackupSnapshot))
        : catalog;
    const chooseSource = (value: string) => {
        setSource(value);
        const chosen = copies.find(c => c.id === value);
        const names = chosen ? [...(chosen.snapshots ?? [])].reverse() : catalog.map(s => s.name);
        setSnapshot(names[0] ?? '');
        setPreview(null);
        setBrowsing(false);
    };
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
                packages,
                acknowledge_packages: packages && packagesAck,
                ...(copy ? { offsite: true } : {}),
            });
            if (dryRun) {
                setPreview(run);
                setRestore(null);
            } else if ((run.status as string) === 'awaiting_approval') {
                setAwaiting(true);
            } else {
                setRestore(run);
            }
        } catch (err) {
            setError(apiDetail(err, t('backups.restore.error', 'The restore could not be requested.')));
        }
    };

    const previewDone = preview !== null && preview.status === 'ok';
    // A preview writes nothing, so it does not need the unsigned-snapshot
    // acknowledgment; only the restore itself does (Bryan, 2026-10-30).
    const previewBlocked = inPlace && include.length === 0;
    const blocked = previewBlocked || (needsAck && !acknowledged);
    const chooseDestination = (place: boolean) => {
        setInPlace(place);
        setPlaceAck(false);
        setPreview(null);
        if (!place) setPackages(false);  // packages go onto the host itself
    };
    const choosePackages = (wanted: boolean) => {
        setPackages(wanted);
        setPackagesAck(false);
        setPreview(null);
        if (wanted) setInPlace(true);
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
                    {copies.length > 0 && (
                        <FormControl fullWidth>
                            <InputLabel id="restore-source">{t('backups.restore.source', 'Restore from')}</InputLabel>
                            <Select labelId="restore-source" label={t('backups.restore.source', 'Restore from')}
                                value={source} onChange={e => chooseSource(e.target.value)}
                                inputProps={{ 'data-testid': 'restore-source' }}>
                                <MenuItem value="">{t('backups.restore.sourceHere', 'This site\'s backup storage')}</MenuItem>
                                {copies.map(c => (
                                    <MenuItem key={c.id} value={c.id}>
                                        {t('backups.restore.sourceOffsite', 'Off-site copy at {{target}}', { target: c.target ?? '?' })}
                                    </MenuItem>
                                ))}
                            </Select>
                        </FormControl>
                    )}
                    {copy && (
                        <Alert severity="info">
                            {t('backups.restore.offsiteNote',
                                'Read from the off-site copy at {{target}} through its proxy: this site\'s backup storage is not used, so this works while it is down.',
                                { target: copy.target ?? '?' })}
                        </Alert>
                    )}
                    {snapshots.length === 0 && !error ? (
                        <Typography variant="body2">{t('backups.restore.noSnapshots', 'This host has no snapshots yet.')}</Typography>
                    ) : (
                        <FormControl fullWidth>
                            <InputLabel id="restore-snapshot">{t('backups.restore.snapshot', 'Snapshot')}</InputLabel>
                            <Select labelId="restore-snapshot" label={t('backups.restore.snapshot', 'Snapshot')}
                                value={snapshot} onChange={e => { setSnapshot(e.target.value); setPreview(null); }}>
                                {snapshots.map(s => (
                                    <MenuItem key={s.id} value={s.name}>
                                        {s.name}{s.created_at ? ` (${formatTime(s.created_at)}, ${formatBytes(s.bytes)})` : ''}
                                        {s.signed ? ` - ${t('backups.restore.signed', 'signed')}` : ` - ${t('backups.restore.unsigned', 'not signed')}`}
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
                                <SnapshotBrowser hostId={hostId} snapshot={snapshot} picked={include} offsite={!!copy}
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
                    {canPackages && (
                        <FormControlLabel
                            control={<Checkbox checked={packages} onChange={e => choosePackages(e.target.checked)} />}
                            label={t('backups.restore.packages', 'Put the snapshot\'s packages back first, at their versions')}
                        />
                    )}
                    {packages && (
                        <FormControlLabel
                            control={<Checkbox checked={packagesAck} onChange={e => setPackagesAck(e.target.checked)} />}
                            label={t('backups.restore.packagesAck', 'Install packages on {{host}}, and remove the packages the snapshot did not have, to match it.', { host: fqdn })}
                        />
                    )}
                    {preview && <RunOutcome run={preview} />}
                    {awaiting && (
                        <Alert severity="info">
                            {t('backups.restore.awaitingApproval', 'Requested. A restore over the host\'s own files needs a second person with the restore role to approve it; it is sent when they do (Backups page, "Restores awaiting approval").')}
                        </Alert>
                    )}
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
                <AsyncButton onClick={() => send(true)} disabled={!snapshot || previewBlocked}>
                    {t('backups.restore.preview', 'Preview')}
                </AsyncButton>
                <AsyncButton variant="contained" color={inPlace ? 'warning' : 'primary'} onClick={() => send(false)}
                    disabled={!previewDone || restore !== null || awaiting || blocked || (inPlace && !placeAck)
                        || (packages && !packagesAck)}>
                    {inPlace ? t('backups.restore.confirmPlace', 'Restore into place')
                        : t('backups.restore.confirm', 'Restore to staging')}
                </AsyncButton>
            </DialogActions>
        </Dialog>
    );
};

export default RestoreFilesDialog;
