// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

/**
 * Authoring and assigning file watch lists (Phase 21.1 S7).
 *
 * A watch list names the paths a host hashes every interval, so the
 * golden-host differ can compare them between hosts. No file CONTENT is ever
 * collected or shown here, which is what makes it safe to watch a secret.
 */

import React, { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import Alert from '@mui/material/Alert';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Chip from '@mui/material/Chip';
import Dialog from '@mui/material/Dialog';
import DialogActions from '@mui/material/DialogActions';
import DialogContent from '@mui/material/DialogContent';
import DialogTitle from '@mui/material/DialogTitle';
import IconButton from '@mui/material/IconButton';
import Stack from '@mui/material/Stack';
import Table from '@mui/material/Table';
import TableBody from '@mui/material/TableBody';
import TableCell from '@mui/material/TableCell';
import TableHead from '@mui/material/TableHead';
import TableRow from '@mui/material/TableRow';
import TextField from '@mui/material/TextField';
import Tooltip from '@mui/material/Tooltip';
import Typography from '@mui/material/Typography';
import DeleteIcon from '@mui/icons-material/Delete';

import {
    FileWatch,
    createFileWatch,
    deleteFileWatch,
    listFileWatches,
} from '../Services/fileWatchService';

const messageFrom = (err: unknown, fallback: string): string => {
    const detail = (err as { response?: { data?: { detail?: unknown } } })?.response
        ?.data?.detail;
    return typeof detail === 'string' && detail ? detail : fallback;
};

interface Props {
    canEdit: boolean;
}

const FileWatchPanel: React.FC<Props> = ({ canEdit }) => {
    const { t } = useTranslation();
    const [watches, setWatches] = useState<FileWatch[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const [open, setOpen] = useState(false);
    const [name, setName] = useState('');
    const [paths, setPaths] = useState('');
    const [saving, setSaving] = useState(false);

    const load = useCallback(async () => {
        setLoading(true);
        try {
            setWatches(await listFileWatches());
            setError(null);
        } catch (err) {
            setError(
                messageFrom(
                    err,
                    t('fileWatch.loadError', 'Could not load file watch lists'),
                ),
            );
        } finally {
            setLoading(false);
        }
    }, [t]);

    useEffect(() => {
        load();
    }, [load]);

    const submit = async () => {
        setSaving(true);
        try {
            await createFileWatch({
                name,
                paths: paths
                    .split('\n')
                    .map((line) => line.trim())
                    .filter(Boolean)
                    .map((path) => ({ path })),
            });
            setOpen(false);
            setName('');
            setPaths('');
            await load();
        } catch (err) {
            // The server refuses a list it cannot collect honestly — a
            // relative path, a duplicate, an empty list. Surfaced verbatim
            // rather than replaced: a path an operator believes is watched,
            // and is not, produces a comparison that looks complete.
            setError(
                messageFrom(err, t('fileWatch.saveError', 'Could not save the list')),
            );
        } finally {
            setSaving(false);
        }
    };

    const remove = async (watchId: string) => {
        try {
            await deleteFileWatch(watchId);
            await load();
        } catch (err) {
            setError(
                messageFrom(err, t('fileWatch.deleteError', 'Could not delete the list')),
            );
        }
    };

    return (
        <Box>
            <Stack direction="row" alignItems="center" sx={{ mb: 2 }} spacing={2}>
                <Typography variant="h6" sx={{ flexGrow: 1 }}>
                    {t('fileWatch.title', 'File watch lists')}
                </Typography>
                {canEdit && (
                    <Button variant="contained" onClick={() => setOpen(true)}>
                        {t('fileWatch.add', 'New list')}
                    </Button>
                )}
            </Stack>

            <Alert severity="info" sx={{ mb: 2 }}>
                {t(
                    'fileWatch.contentNotice',
                    'Only a checksum and file permissions are collected — never the contents. It is therefore safe to watch secrets, though drift will report that a file changed rather than what changed inside it.',
                )}
            </Alert>

            {error && (
                <Alert severity="error" sx={{ mb: 2 }} onClose={() => setError(null)}>
                    {error}
                </Alert>
            )}

            {!loading && watches.length === 0 && (
                <Typography color="text.secondary">
                    {t('fileWatch.empty', 'No file watch lists yet.')}
                </Typography>
            )}

            {watches.length > 0 && (
                <Table size="small">
                    <TableHead>
                        <TableRow>
                            <TableCell>{t('fileWatch.name', 'Name')}</TableCell>
                            <TableCell>{t('fileWatch.pathCount', 'Paths')}</TableCell>
                            <TableCell>{t('fileWatch.status', 'Status')}</TableCell>
                            {canEdit && <TableCell align="right" />}
                        </TableRow>
                    </TableHead>
                    <TableBody>
                        {watches.map((watch) => (
                            <TableRow key={watch.id}>
                                <TableCell>{watch.name}</TableCell>
                                <TableCell>{watch.path_count}</TableCell>
                                <TableCell>
                                    <Chip
                                        size="small"
                                        color={watch.enabled ? 'success' : 'default'}
                                        label={
                                            watch.enabled
                                                ? t('fileWatch.enabled', 'Enabled')
                                                : t('fileWatch.disabled', 'Disabled')
                                        }
                                    />
                                </TableCell>
                                {canEdit && (
                                    <TableCell align="right">
                                        <Tooltip
                                            title={t('fileWatch.delete', 'Delete list')}
                                        >
                                            <IconButton
                                                size="small"
                                                onClick={() => remove(watch.id)}
                                                aria-label={t(
                                                    'fileWatch.delete',
                                                    'Delete list',
                                                )}
                                            >
                                                <DeleteIcon fontSize="small" />
                                            </IconButton>
                                        </Tooltip>
                                    </TableCell>
                                )}
                            </TableRow>
                        ))}
                    </TableBody>
                </Table>
            )}

            <Dialog open={open} onClose={() => setOpen(false)} fullWidth maxWidth="sm">
                <DialogTitle>{t('fileWatch.add', 'New list')}</DialogTitle>
                <DialogContent>
                    <Stack spacing={2} sx={{ mt: 1 }}>
                        <TextField
                            label={t('fileWatch.name', 'Name')}
                            value={name}
                            onChange={(e) => setName(e.target.value)}
                            fullWidth
                        />
                        <TextField
                            label={t('fileWatch.paths', 'Paths, one per line')}
                            value={paths}
                            onChange={(e) => setPaths(e.target.value)}
                            multiline
                            minRows={6}
                            fullWidth
                            helperText={t(
                                'fileWatch.pathsHelp',
                                'Absolute paths only. A relative path resolves differently on each host, so the same list would watch different files.',
                            )}
                        />
                    </Stack>
                </DialogContent>
                <DialogActions>
                    <Button onClick={() => setOpen(false)}>
                        {t('fileWatch.cancel', 'Cancel')}
                    </Button>
                    <Button
                        variant="contained"
                        onClick={submit}
                        disabled={saving || !name.trim() || !paths.trim()}
                    >
                        {t('fileWatch.save', 'Save')}
                    </Button>
                </DialogActions>
            </Dialog>
        </Box>
    );
};

export default FileWatchPanel;
