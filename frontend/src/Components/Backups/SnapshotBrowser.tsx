// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

// Click through a snapshot's folders and pick paths to restore (ROADMAP
// 24.9, restate 2.1.0.4's `list`).  Each folder is one read-only job on the
// host that reads the snapshot's index only -- no backed-up data -- so it
// comes back in seconds; the component polls the run until it ends.

import React, { useEffect, useState } from 'react';
import {
    Alert,
    Box,
    Breadcrumbs,
    Button,
    CircularProgress,
    Link,
    Stack,
    Table,
    TableBody,
    TableCell,
    TableRow,
    Tooltip,
    Typography,
} from '@mui/material';
import { useTranslation } from 'react-i18next';
import { browseSnapshot, getRun } from '../../Services/backups';
import type { BackupRun } from '../../Services/backups';
import { apiDetail, formatBytes } from './backupLabels';

const FINISHED = new Set(['ok', 'different', 'incomplete', 'failed', 'untrusted', 'busy']);
const POLL_MS = 1500;

export interface SnapshotEntry {
    name: string;
    type: 'file' | 'dir' | 'link' | 'other';
    size?: number;
    mtime?: string;
    target?: string;
    name_base64?: string;
}

interface Listing {
    path: string;
    entries: SnapshotEntry[];
    truncated: boolean;
}

const join = (dir: string, name: string): string => (dir === '/' ? `/${name}` : `${dir}/${name}`);

const listingOf = (run: BackupRun): Listing | null => {
    const found = (run.result as { list?: Listing } | null)?.list;
    return found && Array.isArray(found.entries) ? found : null;
};

// Folders first, then by name, as a file manager shows them.
const ordered = (entries: SnapshotEntry[]): SnapshotEntry[] =>
    [...entries].sort((a, b) =>
        (a.type === 'dir' ? 0 : 1) - (b.type === 'dir' ? 0 : 1) || a.name.localeCompare(b.name));

const SnapshotBrowser: React.FC<{
    hostId: string;
    snapshot: string;
    picked: string[];
    onPick: (path: string) => void;
}> = ({ hostId, snapshot, picked, onPick }) => {
    const { t } = useTranslation();
    const [path, setPath] = useState('/');
    const [run, setRun] = useState<BackupRun | null>(null);
    const [error, setError] = useState<string | null>(null);

    useEffect(() => setPath('/'), [snapshot]);

    useEffect(() => {
        let alive = true;
        let timer: ReturnType<typeof setTimeout> | undefined;
        setRun(null);
        setError(null);
        const poll = async (id: string) => {
            const fresh = await getRun(id);
            if (!alive) return;
            setRun(fresh);
            if (!FINISHED.has(fresh.status)) timer = setTimeout(() => void poll(id).catch(() => undefined), POLL_MS);
        };
        browseSnapshot(hostId, snapshot, path)
            .then(started => { if (alive) { setRun(started); void poll(started.id); } })
            .catch(err => { if (alive) setError(apiDetail(err, t('backups.browse.error', 'This folder could not be listed.'))); });
        return () => { alive = false; if (timer) clearTimeout(timer); };
    }, [hostId, snapshot, path, t]);

    const parts = path.split('/').filter(Boolean);
    const listing = run && FINISHED.has(run.status) ? listingOf(run) : null;
    const failed = run && FINISHED.has(run.status) && !listing;

    return (
        <Box data-testid="snapshot-browser" sx={{ border: 1, borderColor: 'divider', borderRadius: 1, p: 1 }}>
            <Breadcrumbs sx={{ mb: 1 }}>
                <Link component="button" type="button" onClick={() => setPath('/')}>/</Link>
                {parts.map((part, i) => (
                    <Link key={part + i} component="button" type="button"
                        onClick={() => setPath('/' + parts.slice(0, i + 1).join('/'))}>{part}</Link>
                ))}
            </Breadcrumbs>
            {error && <Alert severity="error">{error}</Alert>}
            {failed && (
                <Alert severity="error">{run?.message || t('backups.browse.error', 'This folder could not be listed.')}</Alert>
            )}
            {!error && !listing && !failed && (
                <Stack direction="row" spacing={1} alignItems="center">
                    <CircularProgress size={16} />
                    <Typography variant="body2">{t('backups.browse.loading', 'Reading the snapshot index...')}</Typography>
                </Stack>
            )}
            {listing && (
                <Table size="small">
                    <TableBody>
                        {path !== '/' && (
                            <TableRow hover sx={{ cursor: 'pointer' }}
                                onClick={() => setPath('/' + parts.slice(0, -1).join('/'))}>
                                <TableCell colSpan={3}>..</TableCell>
                            </TableRow>
                        )}
                        {ordered(listing.entries).map(entry => {
                            const full = join(path, entry.name);
                            // A name that is not valid text cannot be typed back as a path.
                            const pickable = !entry.name_base64;
                            const isDir = entry.type === 'dir';
                            return (
                                <TableRow key={entry.name_base64 ?? entry.name} hover>
                                    <TableCell sx={{ cursor: isDir && pickable ? 'pointer' : 'default', wordBreak: 'break-all' }}
                                        onClick={() => { if (isDir && pickable) setPath(full); }}>
                                        {isDir ? `${entry.name}/` : entry.name}
                                        {entry.type === 'link' && entry.target ? ` -> ${entry.target}` : ''}
                                    </TableCell>
                                    <TableCell>{entry.type === 'file' ? formatBytes(entry.size) : ''}</TableCell>
                                    <TableCell align="right">
                                        <Tooltip title={pickable ? '' : t('backups.browse.notText', 'This name is not valid text, so it cannot be picked here.')}>
                                            <span>
                                                <Button size="small" disabled={!pickable || picked.includes(full)}
                                                    onClick={() => onPick(full)}>
                                                    {picked.includes(full) ? t('backups.browse.added', 'Added') : t('backups.browse.add', 'Add')}
                                                </Button>
                                            </span>
                                        </Tooltip>
                                    </TableCell>
                                </TableRow>
                            );
                        })}
                    </TableBody>
                </Table>
            )}
            {listing?.truncated && (
                <Typography variant="caption" color="warning.main">
                    {t('backups.browse.truncated', 'This folder has more entries than can be shown; type a path to reach the rest.')}
                </Typography>
            )}
        </Box>
    );
};

export default SnapshotBrowser;
