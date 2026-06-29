import React, { useCallback, useEffect, useState } from 'react';
import { DataGrid, GridColDef } from '@mui/x-data-grid';
import { useTranslation } from 'react-i18next';
import Box from '@mui/material/Box';
import Stack from '@mui/material/Stack';
import Button from '@mui/material/Button';
import Typography from '@mui/material/Typography';
import Alert from '@mui/material/Alert';
import Chip from '@mui/material/Chip';
import IconButton from '@mui/material/IconButton';
import TextField from '@mui/material/TextField';
import Dialog from '@mui/material/Dialog';
import DialogActions from '@mui/material/DialogActions';
import DialogContent from '@mui/material/DialogContent';
import DialogContentText from '@mui/material/DialogContentText';
import DialogTitle from '@mui/material/DialogTitle';
import AddIcon from '@mui/icons-material/Add';
import DeleteIcon from '@mui/icons-material/Delete';
import ContentCopyIcon from '@mui/icons-material/ContentCopy';

import {
    ApiKey,
    createApiKey,
    listApiKeys,
    revokeApiKey,
} from '../Services/apiKeys';

const formatDate = (value?: string | null): string => {
    if (!value) return '—';
    const d = new Date(value);
    return Number.isNaN(d.getTime()) ? '—' : d.toLocaleString();
};

const ApiKeys: React.FC = () => {
    const { t } = useTranslation();

    const [keys, setKeys] = useState<ApiKey[]>([]);
    const [loading, setLoading] = useState<boolean>(true);
    const [error, setError] = useState<string | null>(null);

    // Create dialog
    const [createOpen, setCreateOpen] = useState(false);
    const [newName, setNewName] = useState('');
    const [newExpires, setNewExpires] = useState('');
    const [creating, setCreating] = useState(false);

    // One-time "here is your key" dialog
    const [createdKey, setCreatedKey] = useState<string | null>(null);
    const [copied, setCopied] = useState(false);

    // Revoke confirmation
    const [revokeTarget, setRevokeTarget] = useState<ApiKey | null>(null);

    const loadKeys = useCallback(async () => {
        setLoading(true);
        setError(null);
        try {
            setKeys(await listApiKeys());
        } catch {
            setError(t('apiKeys.loadError', 'Failed to load API keys.'));
        } finally {
            setLoading(false);
        }
    }, [t]);

    useEffect(() => {
        loadKeys();
    }, [loadKeys]);

    const handleCreate = async () => {
        if (!newName.trim()) return;
        setCreating(true);
        setError(null);
        try {
            const created = await createApiKey({
                name: newName.trim(),
                expires_at: newExpires ? new Date(newExpires).toISOString() : null,
            });
            setCreateOpen(false);
            setNewName('');
            setNewExpires('');
            setCreatedKey(created.key);
            setCopied(false);
            await loadKeys();
        } catch {
            setError(t('apiKeys.createError', 'Failed to create API key.'));
        } finally {
            setCreating(false);
        }
    };

    const handleRevoke = async () => {
        if (!revokeTarget) return;
        setError(null);
        try {
            await revokeApiKey(revokeTarget.id);
            setRevokeTarget(null);
            await loadKeys();
        } catch {
            setError(t('apiKeys.revokeError', 'Failed to revoke API key.'));
            setRevokeTarget(null);
        }
    };

    const handleCopy = async () => {
        if (!createdKey) return;
        try {
            await globalThis.navigator.clipboard.writeText(createdKey);
            setCopied(true);
        } catch {
            // Clipboard may be unavailable (insecure context) — the key is still
            // shown for manual copy, so this is non-fatal.
            setCopied(false);
        }
    };

    const columns: GridColDef[] = [
        { field: 'name', headerName: t('apiKeys.name', 'Name'), flex: 1, minWidth: 160 },
        {
            field: 'key_prefix',
            headerName: t('apiKeys.prefix', 'Key prefix'),
            width: 160,
        },
        {
            field: 'is_active',
            headerName: t('apiKeys.status', 'Status'),
            width: 120,
            renderCell: (params) =>
                params.value ? (
                    <Chip
                        label={t('apiKeys.active', 'Active')}
                        color="success"
                        size="small"
                    />
                ) : (
                    <Chip
                        label={t('apiKeys.revoked', 'Revoked')}
                        color="default"
                        size="small"
                    />
                ),
        },
        {
            field: 'created_at',
            headerName: t('apiKeys.created', 'Created'),
            width: 190,
            valueFormatter: (value) => formatDate(value as string | null),
        },
        {
            field: 'last_used_at',
            headerName: t('apiKeys.lastUsed', 'Last used'),
            width: 190,
            valueFormatter: (value) => formatDate(value as string | null),
        },
        {
            field: 'expires_at',
            headerName: t('apiKeys.expires', 'Expires'),
            width: 190,
            valueFormatter: (value) => formatDate(value as string | null),
        },
        {
            field: 'actions',
            headerName: t('common.actions', 'Actions'),
            width: 100,
            sortable: false,
            filterable: false,
            renderCell: (params) => (
                <IconButton
                    color="error"
                    size="small"
                    disabled={!params.row.is_active}
                    onClick={() => setRevokeTarget(params.row as ApiKey)}
                    title={t('apiKeys.revoke', 'Revoke')}
                >
                    <DeleteIcon />
                </IconButton>
            ),
        },
    ];

    return (
        <Box sx={{ p: 3 }}>
            <Stack
                direction="row"
                justifyContent="space-between"
                alignItems="center"
                sx={{ mb: 2 }}
            >
                <Typography variant="h5">{t('apiKeys.title', 'API Keys')}</Typography>
                <Button
                    variant="contained"
                    startIcon={<AddIcon />}
                    onClick={() => setCreateOpen(true)}
                >
                    {t('apiKeys.create', 'Create API Key')}
                </Button>
            </Stack>

            <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
                {t(
                    'apiKeys.description',
                    'API keys let automation authenticate to the API as you. Treat them like passwords.',
                )}
            </Typography>

            {error && (
                <Alert severity="error" sx={{ mb: 2 }} onClose={() => setError(null)}>
                    {error}
                </Alert>
            )}

            <Box sx={{ height: 520, width: '100%' }}>
                <DataGrid
                    rows={keys}
                    columns={columns}
                    getRowId={(row) => row.id}
                    loading={loading}
                    initialState={{
                        pagination: { paginationModel: { page: 0, pageSize: 10 } },
                    }}
                    pageSizeOptions={[10, 25, 50]}
                    disableRowSelectionOnClick
                />
            </Box>

            {/* Create dialog */}
            <Dialog
                open={createOpen}
                onClose={() => setCreateOpen(false)}
                fullWidth
                maxWidth="sm"
            >
                <DialogTitle>{t('apiKeys.create', 'Create API Key')}</DialogTitle>
                <DialogContent>
                    <TextField
                        autoFocus
                        margin="dense"
                        label={t('apiKeys.name', 'Name')}
                        fullWidth
                        value={newName}
                        onChange={(e) => setNewName(e.target.value)}
                        required
                    />
                    <TextField
                        margin="dense"
                        label={t('apiKeys.expiresOptional', 'Expires (optional)')}
                        type="datetime-local"
                        fullWidth
                        value={newExpires}
                        onChange={(e) => setNewExpires(e.target.value)}
                        slotProps={{ inputLabel: { shrink: true } }}
                    />
                </DialogContent>
                <DialogActions>
                    <Button onClick={() => setCreateOpen(false)}>
                        {t('common.cancel', 'Cancel')}
                    </Button>
                    <Button
                        onClick={handleCreate}
                        variant="contained"
                        disabled={creating || !newName.trim()}
                    >
                        {t('common.create', 'Create')}
                    </Button>
                </DialogActions>
            </Dialog>

            {/* One-time key display */}
            <Dialog
                open={createdKey !== null}
                onClose={() => setCreatedKey(null)}
                fullWidth
                maxWidth="sm"
            >
                <DialogTitle>{t('apiKeys.createdTitle', 'API key created')}</DialogTitle>
                <DialogContent>
                    <Alert severity="warning" sx={{ mb: 2 }}>
                        {t(
                            'apiKeys.copyWarning',
                            'Copy this key now — it will not be shown again.',
                        )}
                    </Alert>
                    <Stack direction="row" spacing={1} alignItems="center">
                        <TextField
                            value={createdKey || ''}
                            fullWidth
                            slotProps={{ input: { readOnly: true } }}
                        />
                        <IconButton
                            onClick={handleCopy}
                            title={t('common.copy', 'Copy')}
                            color={copied ? 'success' : 'default'}
                        >
                            <ContentCopyIcon />
                        </IconButton>
                    </Stack>
                    {copied && (
                        <Typography variant="caption" color="success.main">
                            {t('common.copied', 'Copied')}
                        </Typography>
                    )}
                </DialogContent>
                <DialogActions>
                    <Button onClick={() => setCreatedKey(null)} variant="contained">
                        {t('common.done', 'Done')}
                    </Button>
                </DialogActions>
            </Dialog>

            {/* Revoke confirmation */}
            <Dialog open={revokeTarget !== null} onClose={() => setRevokeTarget(null)}>
                <DialogTitle>{t('apiKeys.revoke', 'Revoke')}</DialogTitle>
                <DialogContent>
                    <DialogContentText>
                        {t(
                            'apiKeys.confirmRevoke',
                            'Are you sure you want to revoke this API key? Any automation using it will stop working immediately.',
                        )}
                    </DialogContentText>
                </DialogContent>
                <DialogActions>
                    <Button onClick={() => setRevokeTarget(null)}>
                        {t('common.cancel', 'Cancel')}
                    </Button>
                    <Button onClick={handleRevoke} color="error" variant="contained">
                        {t('apiKeys.revoke', 'Revoke')}
                    </Button>
                </DialogActions>
            </Dialog>
        </Box>
    );
};

export default ApiKeys;
