// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

import React, { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import Alert from '@mui/material/Alert';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Chip from '@mui/material/Chip';
import Dialog from '@mui/material/Dialog';
import DialogActions from '@mui/material/DialogActions';
import DialogContent from '@mui/material/DialogContent';
import DialogContentText from '@mui/material/DialogContentText';
import DialogTitle from '@mui/material/DialogTitle';
import FormControlLabel from '@mui/material/FormControlLabel';
import Stack from '@mui/material/Stack';
import Switch from '@mui/material/Switch';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';

import {
    ConfigInventory,
    createInventory,
    deleteInventory,
    getInventories,
    previewInventory,
} from '../Services/configFleetService';

/** Pull the server's explanation out of an axios error, or fall back. */
const messageFrom = (err: unknown, fallback: string): string => {
    const detail = (err as { response?: { data?: { detail?: unknown } } })?.response
        ?.data?.detail;
    return typeof detail === 'string' && detail ? detail : fallback;
};

interface Props {
    canEdit: boolean;
    onChanged?: () => void;
}

/**
 * Named host selections that fleet jobs run against.
 *
 * The preview is the point of this panel rather than an extra. An inventory
 * resolves at launch, so "who am I about to change" is a question only the
 * server can answer, and it is the one an operator needs answered before
 * pressing a button that touches four thousand machines.
 */
const ConfigInventoriesPanel: React.FC<Props> = ({ canEdit, onChanged }) => {
    const { t } = useTranslation();
    const [rows, setRows] = useState<ConfigInventory[]>([]);
    const [error, setError] = useState<string | null>(null);
    const [creating, setCreating] = useState(false);
    const [name, setName] = useState('');
    const [description, setDescription] = useState('');
    const [allHosts, setAllHosts] = useState(false);
    const [saving, setSaving] = useState(false);
    const [preview, setPreview] = useState<{ name: string; hosts: string[] } | null>(
        null,
    );
    const [confirmDelete, setConfirmDelete] = useState<ConfigInventory | null>(null);

    const load = useCallback(async () => {
        try {
            setRows(await getInventories());
            setError(null);
        } catch (err) {
            setError(
                messageFrom(
                    err,
                    t('configFleet.inventoriesFailed', 'Could not load inventories'),
                ),
            );
        }
    }, [t]);

    useEffect(() => {
        load();
    }, [load]);

    const resetForm = () => {
        setName('');
        setDescription('');
        setAllHosts(false);
        setCreating(false);
    };

    const save = async () => {
        setSaving(true);
        try {
            await createInventory({
                name,
                description: description || null,
                all_hosts: allHosts,
            });
            resetForm();
            await load();
            onChanged?.();
        } catch (err) {
            setError(
                messageFrom(
                    err,
                    t('configFleet.inventorySaveFailed', 'Could not save the inventory'),
                ),
            );
        } finally {
            setSaving(false);
        }
    };

    const showPreview = async (row: ConfigInventory) => {
        try {
            setPreview({ name: row.name, hosts: await previewInventory(row.id) });
        } catch (err) {
            setError(
                messageFrom(
                    err,
                    t('configFleet.previewFailed', 'Could not resolve this inventory'),
                ),
            );
        }
    };

    const remove = async () => {
        if (!confirmDelete) return;
        try {
            await deleteInventory(confirmDelete.id);
            setConfirmDelete(null);
            await load();
            onChanged?.();
        } catch (err) {
            // A 409 here is the server refusing to delete an inventory a job
            // template still names; its detail says how many, which is more
            // useful than anything this component could invent.
            setError(
                messageFrom(
                    err,
                    t('configFleet.inventoryDeleteFailed', 'Could not delete the inventory'),
                ),
            );
            setConfirmDelete(null);
        }
    };

    return (
        <Box>
            {error && (
                <Alert severity="error" sx={{ mb: 2 }} onClose={() => setError(null)}>
                    {error}
                </Alert>
            )}

            {canEdit && (
                <Button
                    variant="contained"
                    sx={{ mb: 2 }}
                    onClick={() => setCreating(true)}
                >
                    {t('configFleet.newInventory', 'New inventory')}
                </Button>
            )}

            {rows.length === 0 ? (
                <Alert severity="info">
                    {t(
                        'configFleet.noInventories',
                        'No inventories yet. An inventory names the hosts a fleet job runs against.',
                    )}
                </Alert>
            ) : (
                <Stack spacing={1}>
                    {rows.map((row) => (
                        <Box
                            key={row.id}
                            sx={{
                                border: 1,
                                borderColor: 'divider',
                                borderRadius: 1,
                                p: 2,
                            }}
                        >
                            <Stack
                                direction="row"
                                spacing={2}
                                alignItems="center"
                                flexWrap="wrap"
                            >
                                <Typography variant="subtitle1" sx={{ flexGrow: 1 }}>
                                    {row.name}
                                </Typography>
                                {row.all_hosts && (
                                    <Chip
                                        size="small"
                                        color="warning"
                                        label={t('configFleet.allHosts', 'Every host')}
                                    />
                                )}
                                <Chip
                                    size="small"
                                    label={t('configFleet.hostCount', '{{count}} hosts', {
                                        count: row.host_count ?? 0,
                                    })}
                                />
                                <Button size="small" onClick={() => showPreview(row)}>
                                    {t('configFleet.preview', 'Preview')}
                                </Button>
                                {canEdit && (
                                    <Button
                                        size="small"
                                        color="error"
                                        onClick={() => setConfirmDelete(row)}
                                    >
                                        {t('common.delete', 'Delete')}
                                    </Button>
                                )}
                            </Stack>
                            {row.description && (
                                <Typography variant="body2" color="text.secondary">
                                    {row.description}
                                </Typography>
                            )}
                        </Box>
                    ))}
                </Stack>
            )}

            <Dialog open={creating} onClose={resetForm} maxWidth="sm" fullWidth>
                <DialogTitle>
                    {t('configFleet.newInventory', 'New inventory')}
                </DialogTitle>
                <DialogContent>
                    <Stack spacing={2} sx={{ mt: 1 }}>
                        <TextField
                            label={t('configFleet.name', 'Name')}
                            value={name}
                            onChange={(e) => setName(e.target.value)}
                            fullWidth
                        />
                        <TextField
                            label={t('configFleet.description', 'Description')}
                            value={description}
                            onChange={(e) => setDescription(e.target.value)}
                            fullWidth
                        />
                        <FormControlLabel
                            control={
                                <Switch
                                    checked={allHosts}
                                    onChange={(e) => setAllHosts(e.target.checked)}
                                />
                            }
                            label={t(
                                'configFleet.allHostsLabel',
                                'Every active host in this tenant',
                            )}
                        />
                        <Typography variant="caption" color="text.secondary">
                            {t(
                                'configFleet.membersHint',
                                'Add hosts, tags or sites to this inventory after creating it. ' +
                                    'They are resolved each time a job launches, so a host added ' +
                                    'to a tag is picked up automatically.',
                            )}
                        </Typography>
                    </Stack>
                </DialogContent>
                <DialogActions>
                    <Button onClick={resetForm} disabled={saving}>
                        {t('common.cancel', 'Cancel')}
                    </Button>
                    <Button variant="contained" onClick={save} disabled={saving || !name}>
                        {t('common.save', 'Save')}
                    </Button>
                </DialogActions>
            </Dialog>

            <Dialog
                open={Boolean(preview)}
                onClose={() => setPreview(null)}
                maxWidth="sm"
                fullWidth
            >
                <DialogTitle>
                    {t('configFleet.previewTitle', 'Hosts selected by {{name}}', {
                        name: preview?.name || '',
                    })}
                </DialogTitle>
                <DialogContent>
                    {preview?.hosts.length === 0 ? (
                        <Alert severity="warning">
                            {t(
                                'configFleet.previewEmpty',
                                'This inventory currently selects no active hosts. A job ' +
                                    'launched against it would do nothing.',
                            )}
                        </Alert>
                    ) : (
                        <Stack spacing={0.5}>
                            {(preview?.hosts || []).map((host) => (
                                <Typography key={host} variant="body2">
                                    {host}
                                </Typography>
                            ))}
                        </Stack>
                    )}
                </DialogContent>
                <DialogActions>
                    <Button onClick={() => setPreview(null)}>
                        {t('common.close', 'Close')}
                    </Button>
                </DialogActions>
            </Dialog>

            <Dialog open={Boolean(confirmDelete)} onClose={() => setConfirmDelete(null)}>
                <DialogTitle>
                    {t('configFleet.deleteInventoryTitle', 'Delete this inventory?')}
                </DialogTitle>
                <DialogContent>
                    <DialogContentText>
                        {t(
                            'configFleet.deleteInventoryBody',
                            'Job templates that use {{name}} must be deleted first.',
                            { name: confirmDelete?.name || '' },
                        )}
                    </DialogContentText>
                </DialogContent>
                <DialogActions>
                    <Button onClick={() => setConfirmDelete(null)}>
                        {t('common.cancel', 'Cancel')}
                    </Button>
                    <Button color="error" variant="contained" onClick={remove}>
                        {t('common.delete', 'Delete')}
                    </Button>
                </DialogActions>
            </Dialog>
        </Box>
    );
};

export default ConfigInventoriesPanel;
