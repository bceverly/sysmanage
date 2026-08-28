// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import Alert from '@mui/material/Alert';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Chip from '@mui/material/Chip';
import CircularProgress from '@mui/material/CircularProgress';
import Dialog from '@mui/material/Dialog';
import DialogActions from '@mui/material/DialogActions';
import DialogContent from '@mui/material/DialogContent';
import DialogContentText from '@mui/material/DialogContentText';
import DialogTitle from '@mui/material/DialogTitle';
import FormControlLabel from '@mui/material/FormControlLabel';
import IconButton from '@mui/material/IconButton';
import MenuItem from '@mui/material/MenuItem';
import Stack from '@mui/material/Stack';
import Switch from '@mui/material/Switch';
import TextField from '@mui/material/TextField';
import Tooltip from '@mui/material/Tooltip';
import Typography from '@mui/material/Typography';
import AddIcon from '@mui/icons-material/Add';
import DeleteIcon from '@mui/icons-material/Delete';
import EditIcon from '@mui/icons-material/Edit';
import HistoryIcon from '@mui/icons-material/History';
import { DataGrid, GridColDef } from '@mui/x-data-grid';

import { formatUTCTimestamp } from '../utils/dateUtils';
import { hasPermission, SecurityRoles } from '../Services/permissions';
import {
    ConfigProfile,
    ConfigProfileVersion,
    createConfigProfile,
    deleteConfigProfile,
    getConfigMgmtEngineCatalog,
    getConfigProfiles,
    getConfigProfileVersions,
    updateConfigProfile,
} from '../Services/configManagementService';

/**
 * Fallback engine list, used ONLY if the catalog request fails.
 *
 * The server is the authority and the catalog endpoint is the source; this
 * exists so a transient failure leaves an authoring form that still works
 * rather than an empty dropdown. Identities (`chef`), never binaries
 * (`chef-client`), matching the agent and server registries.
 */
const FALLBACK_ENGINES = ['ansible-core', 'puppet', 'salt', 'chef', 'dsc'];

interface ProfileForm {
    name: string;
    engine: string;
    content: string;
    description: string;
    is_active: boolean;
}

const emptyForm = (): ProfileForm => ({
    name: '',
    engine: 'ansible-core',
    content: '',
    description: '',
    is_active: true,
});

/** Pull the server's explanation out of an axios error, or fall back. */
const messageFrom = (err: unknown, fallback: string): string => {
    const detail = (err as { response?: { data?: { detail?: unknown } } })?.response
        ?.data?.detail;
    return typeof detail === 'string' && detail ? detail : fallback;
};

const ConfigProfiles: React.FC = () => {
    const { t } = useTranslation();
    const [profiles, setProfiles] = useState<ConfigProfile[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const [dialogError, setDialogError] = useState<string | null>(null);

    const [dialogOpen, setDialogOpen] = useState(false);
    const [editId, setEditId] = useState<string | null>(null);
    const [form, setForm] = useState<ProfileForm>(emptyForm());
    const [saving, setSaving] = useState(false);

    const [deleteTarget, setDeleteTarget] = useState<ConfigProfile | null>(null);
    const [versionsFor, setVersionsFor] = useState<ConfigProfile | null>(null);
    const [versions, setVersions] = useState<ConfigProfileVersion[]>([]);

    const [engineNames, setEngineNames] = useState<string[]>(FALLBACK_ENGINES);
    const [canAdd, setCanAdd] = useState(false);
    const [canEdit, setCanEdit] = useState(false);
    const [canDelete, setCanDelete] = useState(false);

    const load = useCallback(async () => {
        try {
            setProfiles(await getConfigProfiles());
            setError(null);
        } catch (err) {
            setError(
                messageFrom(
                    err,
                    t('configProfiles.loadFailed', 'Could not load configuration profiles'),
                ),
            );
        } finally {
            setLoading(false);
        }
    }, [t]);

    useEffect(() => {
        load();
    }, [load]);

    useEffect(() => {
        const loadEngines = async () => {
            try {
                const catalog = await getConfigMgmtEngineCatalog();
                if (catalog.engines.length > 0) {
                    setEngineNames(catalog.engines.map((e) => e.engine));
                }
            } catch (err) {
                // Keep the fallback list: an empty dropdown on the authoring
                // form reads as a broken page, and the server validates the
                // engine anyway.
                console.error('Failed to load the engine catalog:', err);
            }
        };
        loadEngines();
    }, []);

    useEffect(() => {
        const check = async () => {
            try {
                const [add, edit, remove] = await Promise.all([
                    hasPermission(SecurityRoles.ADD_SCRIPT),
                    hasPermission(SecurityRoles.EDIT_SCRIPT),
                    hasPermission(SecurityRoles.DELETE_SCRIPT),
                ]);
                setCanAdd(add);
                setCanEdit(edit);
                setCanDelete(remove);
            } catch (err) {
                // Fail closed and say so: silently leaving every flag false
                // gives an operator a page of dead buttons with no reason.
                console.error('Failed to resolve config profile permissions:', err);
            }
        };
        check();
    }, []);

    const openCreate = () => {
        setEditId(null);
        setForm(emptyForm());
        setDialogError(null);
        setDialogOpen(true);
    };

    const openEdit = useCallback((row: ConfigProfile) => {
        setEditId(row.id);
        setForm({
            name: row.name,
            engine: row.engine,
            content: row.content,
            description: row.description ?? '',
            is_active: row.is_active,
        });
        setDialogError(null);
        setDialogOpen(true);
    }, []);

    const save = async () => {
        setSaving(true);
        setDialogError(null);
        try {
            if (editId) {
                await updateConfigProfile(editId, {
                    name: form.name,
                    engine: form.engine,
                    content: form.content,
                    description: form.description,
                    is_active: form.is_active,
                });
            } else {
                await createConfigProfile({
                    name: form.name,
                    engine: form.engine,
                    content: form.content,
                    description: form.description,
                });
            }
            setDialogOpen(false);
            await load();
        } catch (err) {
            // Kept IN the dialog: closing it would discard a long profile body
            // the operator would then have to retype.
            setDialogError(
                messageFrom(err, t('configProfiles.saveFailed', 'Could not save the profile')),
            );
        } finally {
            setSaving(false);
        }
    };

    const confirmDelete = async () => {
        if (!deleteTarget) return;
        try {
            await deleteConfigProfile(deleteTarget.id);
            setDeleteTarget(null);
            await load();
        } catch (err) {
            setError(
                messageFrom(err, t('configProfiles.deleteFailed', 'Could not delete the profile')),
            );
            setDeleteTarget(null);
        }
    };

    const openVersions = useCallback(async (row: ConfigProfile) => {
        setVersionsFor(row);
        setVersions([]);
        try {
            setVersions(await getConfigProfileVersions(row.id));
        } catch (err) {
            setError(
                messageFrom(
                    err,
                    t('configProfiles.versionsFailed', 'Could not load the version history'),
                ),
            );
        }
    }, [t]);

    const columns: GridColDef[] = useMemo(
        () => [
            { field: 'name', headerName: t('configProfiles.name', 'Name'), flex: 1, minWidth: 160 },
            {
                field: 'engine',
                headerName: t('configProfiles.engine', 'Engine'),
                width: 140,
                renderCell: (params) => <Chip size="small" label={params.value} />,
            },
            {
                field: 'version',
                headerName: t('configProfiles.version', 'Version'),
                width: 100,
            },
            {
                field: 'description',
                headerName: t('configProfiles.description', 'Description'),
                flex: 1,
                minWidth: 180,
            },
            {
                field: 'is_active',
                headerName: t('configProfiles.active', 'Active'),
                width: 110,
                renderCell: (params) =>
                    params.value ? (
                        <Chip
                            size="small"
                            color="success"
                            label={t('configProfiles.activeYes', 'Active')}
                        />
                    ) : (
                        <Chip size="small" label={t('configProfiles.activeNo', 'Inactive')} />
                    ),
            },
            {
                field: 'updated_at',
                headerName: t('configProfiles.updated', 'Updated'),
                width: 190,
                renderCell: (params) =>
                    params.value ? formatUTCTimestamp(params.value as string) : '',
            },
            {
                field: 'actions',
                headerName: t('configProfiles.actions', 'Actions'),
                width: 150,
                sortable: false,
                filterable: false,
                renderCell: (params) => (
                    <Stack direction="row" spacing={0.5}>
                        <Tooltip title={t('configProfiles.history', 'Version history')}>
                            <span>
                                <IconButton
                                    size="small"
                                    aria-label={t('configProfiles.history', 'Version history')}
                                    onClick={() => openVersions(params.row as ConfigProfile)}
                                >
                                    <HistoryIcon fontSize="small" />
                                </IconButton>
                            </span>
                        </Tooltip>
                        <Tooltip title={t('configProfiles.edit', 'Edit')}>
                            <span>
                                <IconButton
                                    size="small"
                                    aria-label={t('configProfiles.edit', 'Edit')}
                                    disabled={!canEdit}
                                    onClick={() => openEdit(params.row as ConfigProfile)}
                                >
                                    <EditIcon fontSize="small" />
                                </IconButton>
                            </span>
                        </Tooltip>
                        <Tooltip title={t('configProfiles.delete', 'Delete')}>
                            <span>
                                <IconButton
                                    size="small"
                                    aria-label={t('configProfiles.delete', 'Delete')}
                                    disabled={!canDelete}
                                    onClick={() => setDeleteTarget(params.row as ConfigProfile)}
                                >
                                    <DeleteIcon fontSize="small" />
                                </IconButton>
                            </span>
                        </Tooltip>
                    </Stack>
                ),
            },
        ],
        [t, canEdit, canDelete, openEdit, openVersions],
    );

    if (loading) {
        return (
            <Box sx={{ display: 'flex', justifyContent: 'center', p: 4 }}>
                <CircularProgress />
            </Box>
        );
    }

    const isDsc = form.engine === 'dsc';

    return (
        <Box sx={{ p: 3 }}>
            <Box
                sx={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                    mb: 1,
                }}
            >
                <Typography variant="h5">
                    {t('configProfiles.title', 'Configuration Profiles')}
                </Typography>
                <Button
                    variant="contained"
                    startIcon={<AddIcon />}
                    disabled={!canAdd}
                    onClick={openCreate}
                >
                    {t('configProfiles.addProfile', 'New Profile')}
                </Button>
            </Box>
            <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
                {t(
                    'configProfiles.intro',
                    'Author a configuration once and apply it to many hosts. Editing the ' +
                        'engine or the body keeps the previous body as a version, so you ' +
                        'can always see what a profile contained when it ran.',
                )}
            </Typography>

            {error && (
                <Alert severity="error" sx={{ mb: 2 }} onClose={() => setError(null)}>
                    {error}
                </Alert>
            )}

            <div style={{ width: '100%', height: 520 }}>
                <DataGrid
                    rows={profiles}
                    columns={columns}
                    getRowId={(row) => row.id}
                    initialState={{ pagination: { paginationModel: { pageSize: 25 } } }}
                    pageSizeOptions={[10, 25, 50]}
                    disableRowSelectionOnClick
                />
            </div>

            <Dialog
                open={dialogOpen}
                onClose={() => setDialogOpen(false)}
                maxWidth="md"
                fullWidth
            >
                <DialogTitle>
                    {editId
                        ? t('configProfiles.editTitle', 'Edit Configuration Profile')
                        : t('configProfiles.createTitle', 'New Configuration Profile')}
                </DialogTitle>
                <DialogContent>
                    {dialogError && (
                        <Alert severity="error" sx={{ mb: 2 }}>
                            {dialogError}
                        </Alert>
                    )}
                    <Stack spacing={2} sx={{ mt: 1 }}>
                        <TextField
                            label={t('configProfiles.name', 'Name')}
                            value={form.name}
                            onChange={(e) => setForm({ ...form, name: e.target.value })}
                            fullWidth
                            required
                        />
                        <TextField
                            select
                            label={t('configProfiles.engine', 'Engine')}
                            value={form.engine}
                            onChange={(e) => setForm({ ...form, engine: e.target.value })}
                            fullWidth
                        >
                            {engineNames.map((engine) => (
                                <MenuItem key={engine} value={engine}>
                                    {engine}
                                </MenuItem>
                            ))}
                        </TextField>
                        <TextField
                            label={t('configProfiles.description', 'Description')}
                            value={form.description}
                            onChange={(e) =>
                                setForm({ ...form, description: e.target.value })
                            }
                            fullWidth
                        />
                        <TextField
                            label={
                                isDsc
                                    ? t('configProfiles.contentDsc', 'DSC resources (JSON)')
                                    : t('configProfiles.contentBody', 'Profile content (YAML)')
                            }
                            value={form.content}
                            onChange={(e) => setForm({ ...form, content: e.target.value })}
                            fullWidth
                            required
                            multiline
                            minRows={12}
                            slotProps={{
                                htmlInput: { style: { fontFamily: 'monospace' } },
                            }}
                        />
                        {editId && (
                            <FormControlLabel
                                control={
                                    <Switch
                                        checked={form.is_active}
                                        onChange={(e) =>
                                            setForm({ ...form, is_active: e.target.checked })
                                        }
                                    />
                                }
                                label={t('configProfiles.active', 'Active')}
                            />
                        )}
                    </Stack>
                </DialogContent>
                <DialogActions>
                    <Button onClick={() => setDialogOpen(false)}>
                        {t('common.cancel', 'Cancel')}
                    </Button>
                    <Button
                        variant="contained"
                        onClick={save}
                        disabled={saving || !form.name.trim() || !form.content.trim()}
                    >
                        {t('common.save', 'Save')}
                    </Button>
                </DialogActions>
            </Dialog>

            <Dialog open={Boolean(deleteTarget)} onClose={() => setDeleteTarget(null)}>
                <DialogTitle>{t('configProfiles.deleteTitle', 'Delete Profile')}</DialogTitle>
                <DialogContent>
                    <DialogContentText>
                        {t(
                            'configProfiles.deleteBody',
                            'This removes the profile, its version history and its ' +
                                'assignments. Records of past runs are kept.',
                        )}
                    </DialogContentText>
                </DialogContent>
                <DialogActions>
                    <Button onClick={() => setDeleteTarget(null)}>
                        {t('common.cancel', 'Cancel')}
                    </Button>
                    <Button color="error" variant="contained" onClick={confirmDelete}>
                        {t('configProfiles.delete', 'Delete')}
                    </Button>
                </DialogActions>
            </Dialog>

            <Dialog
                open={Boolean(versionsFor)}
                onClose={() => setVersionsFor(null)}
                maxWidth="md"
                fullWidth
            >
                <DialogTitle>
                    {t('configProfiles.historyTitle', 'Version History')}
                </DialogTitle>
                <DialogContent>
                    {versions.length === 0 ? (
                        <DialogContentText>
                            {t(
                                'configProfiles.noVersions',
                                'No earlier versions yet. A version is kept each time the ' +
                                    'engine or the body changes.',
                            )}
                        </DialogContentText>
                    ) : (
                        <Stack spacing={2} sx={{ mt: 1 }}>
                            {versions.map((version) => (
                                <Box key={version.id}>
                                    <Typography variant="subtitle2">
                                        {t('configProfiles.versionLabel', 'Version {{n}}', {
                                            n: version.version,
                                        })}
                                        {version.created_at
                                            ? ` — ${formatUTCTimestamp(version.created_at)}`
                                            : ''}
                                    </Typography>
                                    <TextField
                                        value={version.content}
                                        fullWidth
                                        multiline
                                        maxRows={12}
                                        slotProps={{
                                            htmlInput: {
                                                readOnly: true,
                                                style: { fontFamily: 'monospace' },
                                            },
                                        }}
                                    />
                                </Box>
                            ))}
                        </Stack>
                    )}
                </DialogContent>
                <DialogActions>
                    <Button onClick={() => setVersionsFor(null)}>
                        {t('common.close', 'Close')}
                    </Button>
                </DialogActions>
            </Dialog>
        </Box>
    );
};

export default ConfigProfiles;
