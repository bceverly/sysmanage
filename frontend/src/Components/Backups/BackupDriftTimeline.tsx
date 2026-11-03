// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

// The drift timeline (Pro+ backup_engine, 24.7): what changed between each
// snapshot and the one before it, newest first -- packages installed,
// removed or upgraded, and the file changes no package accounts for.  Logs,
// caches and the host's own ignore patterns are hidden unless "Show
// everything" is on, and how many were hidden is always said.  A
// ``?driftPath=`` in the URL (the link from configuration drift) narrows the
// timeline to that path.

import React, { useCallback, useEffect, useState } from 'react';
import {
    Accordion,
    AccordionDetails,
    AccordionSummary,
    Alert,
    Box,
    Button,
    Card,
    CardContent,
    Chip,
    FormControlLabel,
    Stack,
    Switch,
    TextField,
    Typography,
} from '@mui/material';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import { useTranslation } from 'react-i18next';
import type { TFunction } from 'i18next';
import AsyncButton from '../AsyncButton';
import {
    computeDrift, getDriftTimeline, setDriftIgnore,
    type DriftChange, type DriftEntry, type DriftPackage, type DriftTimeline,
} from '../../Services/backups';
import { apiDetail } from './backupLabels';
import { hasPermission, SecurityRoles } from '../../Services/permissions';

const SHOWN = 200;

const changeWord = (t: TFunction, change: string): string => ({
    A: t('backups.drift.added', 'added'),
    D: t('backups.drift.deleted', 'deleted'),
    M: t('backups.drift.modified', 'modified'),
    I: t('backups.drift.installed', 'installed'),
    R: t('backups.drift.removed', 'removed'),
    U: t('backups.drift.upgraded', 'upgraded'),
}[change] ?? change);

const packageLine = (t: TFunction, p: DriftPackage): string => {
    const versions = p.change === 'U' ? `${p.from ?? ''} -> ${p.to ?? ''}`
        : (p.to || p.from || '');
    const arch = p.arch ? `:${p.arch}` : '';
    return `${changeWord(t, p.change)}: ${p.name}${arch} ${versions} (${p.manager})`;
};

const fileLine = (t: TFunction, c: DriftChange): string => {
    const what = c.what ? ` (${c.what})` : '';
    return `${changeWord(t, c.change)}: ${c.path}${what}`;
};

const Entry: React.FC<{ entry: DriftEntry }> = ({ entry }) => {
    const { t } = useTranslation();
    if (entry.status !== 'ok') {
        return (
            <Alert severity="warning">
                {t('backups.drift.failed', 'The comparison of {{from}} and {{to}} failed', { from: entry.from, to: entry.to })}
                {entry.message ? `: ${entry.message}` : ''}
            </Alert>
        );
    }
    const files = entry.changes;
    return (
        <Accordion disableGutters>
            <AccordionSummary expandIcon={<ExpandMoreIcon />}>
                <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
                    <Typography variant="body2" sx={{ fontFamily: 'monospace' }}>
                        {entry.from} {'->'} {entry.to}
                    </Typography>
                    <Chip size="small" label={t('backups.drift.packagesCount', 'Packages: {{n}}',
                        { n: entry.packages_changed ?? entry.packages.length })} />
                    <Chip size="small" label={t('backups.drift.filesCount', 'Files: {{n}}', { n: files.length })} />
                    {entry.hidden > 0 && (
                        <Typography variant="caption" color="text.secondary">
                            {t('backups.drift.hidden', 'Hidden as expected churn: {{n}}', { n: entry.hidden })}
                        </Typography>
                    )}
                </Stack>
            </AccordionSummary>
            <AccordionDetails>
                {entry.packages.length > 0 && (
                    <Box component="pre" sx={{ fontSize: 12, bgcolor: 'action.hover', p: 1, overflow: 'auto' }}>
                        {entry.packages.map(p => packageLine(t, p)).join('\n')}
                    </Box>
                )}
                {files.length > 0 ? (
                    <Box component="pre" sx={{ fontSize: 12, bgcolor: 'action.hover', p: 1, maxHeight: 320, overflow: 'auto' }}>
                        {files.slice(0, SHOWN).map(c => fileLine(t, c)).join('\n')}
                        {files.length > SHOWN && `\n${t('backups.restore.more', 'Not shown: {{n}}', { n: files.length - SHOWN })}`}
                    </Box>
                ) : (
                    <Typography variant="body2" color="text.secondary">
                        {t('backups.drift.noFiles', 'No file changes beyond what the packages account for.')}
                    </Typography>
                )}
                {(entry.truncated || entry.packages_truncated) && (
                    <Typography variant="caption" color="text.secondary">
                        {t('backups.drift.truncated', 'Only the first 1000 changes of each kind are kept.')}
                    </Typography>
                )}
            </AccordionDetails>
        </Accordion>
    );
};

const IgnoreEditor: React.FC<{ hostId: string; ignore: string[]; onSaved: () => void }> = ({
    hostId, ignore, onSaved,
}) => {
    const { t } = useTranslation();
    const [text, setText] = useState(ignore.join('\n'));
    const [error, setError] = useState<string | null>(null);
    useEffect(() => setText(ignore.join('\n')), [ignore]);
    const save = async () => {
        setError(null);
        try {
            await setDriftIgnore(hostId, text.split('\n').map(x => x.trim()).filter(Boolean));
            onSaved();
        } catch (err) {
            setError(apiDetail(err, t('backups.drift.ignoreError', 'The patterns could not be saved.')));
        }
    };
    return (
        <Stack spacing={1}>
            {error && <Alert severity="error">{error}</Alert>}
            <TextField multiline minRows={2} size="small" value={text} onChange={e => setText(e.target.value)}
                label={t('backups.drift.ignore', 'Also hide on this host (one path pattern per line)')}
                placeholder="/srv/app/cache" />
            <Box><AsyncButton size="small" onClick={save}>{t('common.save', 'Save')}</AsyncButton></Box>
        </Stack>
    );
};

const BackupDriftTimeline: React.FC<{ hostId: string }> = ({ hostId }) => {
    const { t } = useTranslation();
    const [canManage, setCanManage] = useState(false);
    useEffect(() => {
        hasPermission(SecurityRoles.MANAGE_BACKUPS).then(setCanManage).catch(() => setCanManage(false));
    }, []);
    const path = new URLSearchParams(globalThis.location?.search ?? '').get('driftPath');
    const [everything, setEverything] = useState(false);
    const [data, setData] = useState<DriftTimeline | null>(null);
    const [error, setError] = useState<string | null>(null);

    const load = useCallback(async () => {
        try {
            setData(await getDriftTimeline(hostId, !everything, path));
            setError(null);
        } catch (err) {
            setError(apiDetail(err, t('backups.drift.loadError', 'Could not load the drift timeline.')));
        }
    }, [hostId, everything, path, t]);

    useEffect(() => { void load(); }, [load]);

    const compare = async () => {
        const pair = data?.missing[data.missing.length - 1];
        await computeDrift(hostId, pair?.from, pair?.to);
        await load();
    };

    return (
        <Card>
            <CardContent>
                <Typography variant="h6" gutterBottom>{t('backups.drift.title', 'Drift timeline')}</Typography>
                <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
                    {t('backups.drift.intro', 'What changed between each backup and the one before it: packages installed, removed or upgraded, and the file changes no package accounts for.')}
                </Typography>
                {path && (
                    <Alert severity="info" sx={{ mb: 1 }}>
                        {t('backups.drift.narrowed', 'Showing changes at or beneath {{path}} only.', { path })}
                    </Alert>
                )}
                {error && <Alert severity="error">{error}</Alert>}
                <Stack direction="row" spacing={2} alignItems="center" sx={{ mb: 1 }}>
                    <FormControlLabel control={<Switch checked={everything} onChange={e => setEverything(e.target.checked)} />}
                        label={t('backups.drift.everything', 'Show everything, logs and caches included')} />
                    {canManage && data && data.missing.length > 0 && !data.running && (
                        <AsyncButton size="small" onClick={compare}>
                            {t('backups.drift.compare', 'Compare the newest backups not yet compared')}
                        </AsyncButton>
                    )}
                    {data?.running && (
                        <Typography variant="caption">{t('backups.drift.running', 'A comparison is running.')}</Typography>
                    )}
                    <Button size="small" onClick={() => void load()}>{t('common.refresh', 'Refresh')}</Button>
                </Stack>
                {data?.entries.length === 0 && (
                    <Typography variant="body2">{t('backups.drift.none', 'No backups have been compared yet.')}</Typography>
                )}
                {data?.entries.map(entry => <Entry key={`${entry.from}-${entry.to}`} entry={entry} />)}
                {canManage && data && (
                    <Box sx={{ mt: 2 }}>
                        <IgnoreEditor hostId={hostId} ignore={data.ignore} onSaved={() => void load()} />
                    </Box>
                )}
            </CardContent>
        </Card>
    );
};

export default BackupDriftTimeline;
