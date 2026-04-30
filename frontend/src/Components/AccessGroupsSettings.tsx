import React, { useState, useEffect, useCallback, useMemo } from 'react';
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  CardHeader,
  Checkbox,
  Chip,
  CircularProgress,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  FormControl,
  FormControlLabel,
  IconButton,
  InputLabel,
  MenuItem,
  Select,
  Snackbar,
  Stack,
  TextField,
  Tooltip,
  Typography,
} from '@mui/material';
import {
  DataGrid,
  GridColDef,
  GridRenderCellParams,
} from '@mui/x-data-grid';
import {
  Add as AddIcon,
  Block as BlockIcon,
  ContentCopy as ContentCopyIcon,
  Delete as DeleteIcon,
  Edit as EditIcon,
  Key as KeyIcon,
} from '@mui/icons-material';
import { useTranslation } from 'react-i18next';
import {
  AccessGroup,
  RegistrationKey,
  accessGroupsService,
  registrationKeysService,
} from '../Services/accessGroups';
import { formatUTCTimestamp } from '../utils/dateUtils';

interface GroupRow extends AccessGroup {
  _depth: number;
}

const AccessGroupsSettings: React.FC = () => {
  const { t } = useTranslation();

  const [groups, setGroups] = useState<AccessGroup[]>([]);
  const [keys, setKeys] = useState<RegistrationKey[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [snackbarOpen, setSnackbarOpen] = useState(false);
  const [snackbarMessage, setSnackbarMessage] = useState('');
  const [snackbarSeverity, setSnackbarSeverity] = useState<'success' | 'error'>('success');

  // Group dialog state
  const [groupDialogOpen, setGroupDialogOpen] = useState(false);
  const [editingGroup, setEditingGroup] = useState<AccessGroup | null>(null);
  const [groupName, setGroupName] = useState('');
  const [groupDescription, setGroupDescription] = useState('');
  const [groupParentId, setGroupParentId] = useState<string>('');

  // Key dialog state
  const [keyDialogOpen, setKeyDialogOpen] = useState(false);
  const [keyName, setKeyName] = useState('');
  const [keyAccessGroupId, setKeyAccessGroupId] = useState<string>('');
  const [keyAutoApprove, setKeyAutoApprove] = useState(false);
  const [keyMaxUses, setKeyMaxUses] = useState<string>('');
  const [keyExpiresAt, setKeyExpiresAt] = useState<string>('');

  // Reveal-secret dialog (after creation)
  const [revealedKey, setRevealedKey] = useState<RegistrationKey | null>(null);

  const showError = (msg: string) => {
    setSnackbarMessage(msg);
    setSnackbarSeverity('error');
    setSnackbarOpen(true);
  };
  const showSuccess = (msg: string) => {
    setSnackbarMessage(msg);
    setSnackbarSeverity('success');
    setSnackbarOpen(true);
  };

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [g, k] = await Promise.all([
        accessGroupsService.list(),
        registrationKeysService.list(),
      ]);
      setGroups(g);
      setKeys(k);
    } catch (e) {
      setError(t('accessGroups.loadError', 'Failed to load access groups'));
      console.error(e);
    } finally {
      setLoading(false);
    }
  }, [t]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const groupNameById = useMemo(() => {
    const m = new Map<string, string>();
    groups.forEach((g) => m.set(g.id, g.name));
    return m;
  }, [groups]);

  // Order groups so parents come before children (helpful for the parent dropdown).
  const orderedGroups = useMemo(() => {
    const byParent = new Map<string | null, AccessGroup[]>();
    groups.forEach((g) => {
      const k = g.parent_id ?? null;
      const arr = byParent.get(k) || [];
      arr.push(g);
      byParent.set(k, arr);
    });
    const out: { group: AccessGroup; depth: number }[] = [];
    const walk = (parent: string | null, depth: number) => {
      const children = (byParent.get(parent) || []).slice().sort((a, b) =>
        a.name.localeCompare(b.name),
      );
      children.forEach((c) => {
        out.push({ group: c, depth });
        walk(c.id, depth + 1);
      });
    };
    walk(null, 0);
    return out;
  }, [groups]);

  // ---- Group CRUD ----------------------------------------------------------

  const openCreateGroup = () => {
    setEditingGroup(null);
    setGroupName('');
    setGroupDescription('');
    setGroupParentId('');
    setGroupDialogOpen(true);
  };
  const openEditGroup = (g: AccessGroup) => {
    setEditingGroup(g);
    setGroupName(g.name);
    setGroupDescription(g.description ?? '');
    setGroupParentId(g.parent_id ?? '');
    setGroupDialogOpen(true);
  };

  const handleSaveGroup = async () => {
    if (!groupName.trim()) {
      showError(t('accessGroups.nameRequired', 'Name is required'));
      return;
    }
    try {
      if (editingGroup) {
        await accessGroupsService.update(editingGroup.id, {
          name: groupName.trim(),
          description: groupDescription.trim() || null,
          parent_id: groupParentId || '',
        });
        showSuccess(t('accessGroups.updated', 'Access group updated'));
      } else {
        await accessGroupsService.create({
          name: groupName.trim(),
          description: groupDescription.trim() || null,
          parent_id: groupParentId || null,
        });
        showSuccess(t('accessGroups.created', 'Access group created'));
      }
      setGroupDialogOpen(false);
      await refresh();
    } catch (e: unknown) {
      const detail = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      showError(detail || t('accessGroups.saveError', 'Failed to save access group'));
    }
  };

  const handleDeleteGroup = async (g: AccessGroup) => {
    if (!globalThis.confirm(t('accessGroups.confirmDelete', 'Delete access group "{{name}}"?', { name: g.name }))) {
      return;
    }
    try {
      await accessGroupsService.remove(g.id);
      showSuccess(t('accessGroups.deleted', 'Access group deleted'));
      await refresh();
    } catch (e: unknown) {
      const detail = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      showError(detail || t('accessGroups.deleteError', 'Failed to delete access group'));
    }
  };

  // ---- Registration-key CRUD ----------------------------------------------

  const openCreateKey = () => {
    setKeyName('');
    setKeyAccessGroupId('');
    setKeyAutoApprove(false);
    setKeyMaxUses('');
    setKeyExpiresAt('');
    setKeyDialogOpen(true);
  };

  const handleCreateKey = async () => {
    if (!keyName.trim()) {
      showError(t('accessGroups.nameRequired', 'Name is required'));
      return;
    }
    try {
      const created = await registrationKeysService.create({
        name: keyName.trim(),
        access_group_id: keyAccessGroupId || null,
        auto_approve: keyAutoApprove,
        max_uses: keyMaxUses ? Number.parseInt(keyMaxUses, 10) : null,
        expires_at: keyExpiresAt ? new Date(keyExpiresAt).toISOString() : null,
      });
      setKeyDialogOpen(false);
      setRevealedKey(created);
      await refresh();
    } catch (e: unknown) {
      const detail = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      showError(detail || t('accessGroups.keyCreateError', 'Failed to create registration key'));
    }
  };

  const handleRevokeKey = async (k: RegistrationKey) => {
    if (!globalThis.confirm(t('accessGroups.confirmRevoke', 'Revoke registration key "{{name}}"?', { name: k.name }))) {
      return;
    }
    try {
      await registrationKeysService.revoke(k.id);
      showSuccess(t('accessGroups.revoked', 'Registration key revoked'));
      await refresh();
    } catch (e: unknown) {
      const detail = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      showError(detail || t('accessGroups.revokeError', 'Failed to revoke registration key'));
    }
  };

  const handleDeleteKey = async (k: RegistrationKey) => {
    if (!globalThis.confirm(t('accessGroups.confirmDeleteKey', 'Delete registration key "{{name}}"?', { name: k.name }))) {
      return;
    }
    try {
      await registrationKeysService.remove(k.id);
      showSuccess(t('accessGroups.keyDeleted', 'Registration key deleted'));
      await refresh();
    } catch (e: unknown) {
      const detail = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      showError(detail || t('accessGroups.keyDeleteError', 'Failed to delete registration key'));
    }
  };

  const copySecret = async (secret: string) => {
    try {
      await globalThis.navigator.clipboard.writeText(secret);
      showSuccess(t('accessGroups.copied', 'Copied to clipboard'));
    } catch (e) {
      console.error(e);
      showError(t('accessGroups.copyError', 'Failed to copy'));
    }
  };

  // ---- Grid column defs ---------------------------------------------------

  const groupColumns: GridColDef[] = [
    {
      field: 'name',
      headerName: t('accessGroups.name', 'Name'),
      flex: 1,
      minWidth: 180,
      renderCell: (params: GridRenderCellParams<GroupRow>) => {
        const depth = params.row._depth ?? 0;
        return (
          <Box sx={{ pl: depth * 2 }}>
            {depth > 0 ? '↳ ' : ''}
            {params.row.name}
          </Box>
        );
      },
    },
    {
      field: 'description',
      headerName: t('accessGroups.description', 'Description'),
      flex: 1.5,
      minWidth: 200,
      valueGetter: (_v, row) => row.description || '',
    },
    {
      field: 'parent_id',
      headerName: t('accessGroups.parent', 'Parent'),
      flex: 1,
      minWidth: 160,
      valueGetter: (_v, row) =>
        row.parent_id ? (groupNameById.get(row.parent_id) || row.parent_id) : '—',
    },
    {
      field: 'actions',
      headerName: t('common.actions', 'Actions'),
      sortable: false,
      width: 130,
      renderCell: (params: GridRenderCellParams<AccessGroup>) => (
        <Stack direction="row" spacing={0.5}>
          <Tooltip title={t('common.edit', 'Edit')}>
            <IconButton size="small" onClick={() => openEditGroup(params.row)}>
              <EditIcon fontSize="small" />
            </IconButton>
          </Tooltip>
          <Tooltip title={t('common.delete', 'Delete')}>
            <IconButton size="small" onClick={() => handleDeleteGroup(params.row)}>
              <DeleteIcon fontSize="small" />
            </IconButton>
          </Tooltip>
        </Stack>
      ),
    },
  ];

  const keyColumns: GridColDef[] = [
    {
      field: 'name',
      headerName: t('accessGroups.keyName', 'Name'),
      flex: 1,
      minWidth: 160,
    },
    {
      field: 'access_group_id',
      headerName: t('accessGroups.keyAccessGroup', 'Access Group'),
      flex: 1,
      minWidth: 160,
      valueGetter: (_v, row) =>
        row.access_group_id ? (groupNameById.get(row.access_group_id) || row.access_group_id) : '—',
    },
    {
      field: 'auto_approve',
      headerName: t('accessGroups.keyAutoApprove', 'Auto-Approve'),
      width: 130,
      renderCell: (params: GridRenderCellParams<RegistrationKey>) =>
        params.row.auto_approve ? (
          <Chip size="small" color="success" label={t('common.yes', 'Yes')} />
        ) : (
          <Chip size="small" label={t('common.no', 'No')} />
        ),
    },
    {
      field: 'use_count',
      headerName: t('accessGroups.useCount', 'Used'),
      width: 110,
      valueGetter: (_v, row) =>
        row.max_uses ? `${row.use_count} / ${row.max_uses}` : `${row.use_count}`,
    },
    {
      field: 'expires_at',
      headerName: t('accessGroups.keyExpires', 'Expires'),
      width: 170,
      valueGetter: (_v, row) =>
        row.expires_at ? formatUTCTimestamp(row.expires_at, '—') : t('accessGroups.keyNeverExpires', 'Never'),
    },
    {
      field: 'revoked',
      headerName: t('common.status', 'Status'),
      width: 130,
      renderCell: (params: GridRenderCellParams<RegistrationKey>) =>
        params.row.revoked ? (
          <Chip size="small" color="error" label={t('accessGroups.revokedStatus', 'Revoked')} />
        ) : (
          <Chip size="small" color="success" label={t('common.active', 'Active')} />
        ),
    },
    {
      field: 'actions',
      headerName: t('common.actions', 'Actions'),
      sortable: false,
      width: 140,
      renderCell: (params: GridRenderCellParams<RegistrationKey>) => (
        <Stack direction="row" spacing={0.5}>
          {!params.row.revoked && (
            <Tooltip title={t('accessGroups.revoke', 'Revoke')}>
              <IconButton size="small" onClick={() => handleRevokeKey(params.row)}>
                <BlockIcon fontSize="small" />
              </IconButton>
            </Tooltip>
          )}
          <Tooltip title={t('common.delete', 'Delete')}>
            <IconButton size="small" onClick={() => handleDeleteKey(params.row)}>
              <DeleteIcon fontSize="small" />
            </IconButton>
          </Tooltip>
        </Stack>
      ),
    },
  ];

  const groupRows: GroupRow[] = orderedGroups.map(({ group, depth }) => ({
    ...group,
    _depth: depth,
  }));

  const renderLoadingBox = () => (
    <Box sx={{ display: 'flex', justifyContent: 'center', p: 3 }}>
      <CircularProgress />
    </Box>
  );

  const renderGroupsContent = () => {
    if (loading) return renderLoadingBox();
    if (groups.length === 0) {
      return (
        <Typography color="text.secondary">
          {t('accessGroups.empty', 'No access groups defined yet.')}
        </Typography>
      );
    }
    return (
      <Box sx={{ height: 360 }}>
        <DataGrid
          rows={groupRows}
          columns={groupColumns}
          getRowId={(row) => row.id}
          disableRowSelectionOnClick
          density="compact"
          hideFooter={groupRows.length <= 25}
        />
      </Box>
    );
  };

  const renderKeysContent = () => {
    if (loading) return renderLoadingBox();
    if (keys.length === 0) {
      return (
        <Typography color="text.secondary">
          {t('accessGroups.keysEmpty', 'No registration keys yet.')}
        </Typography>
      );
    }
    return (
      <Box sx={{ height: 360 }}>
        <DataGrid
          rows={keys}
          columns={keyColumns}
          getRowId={(row) => row.id}
          disableRowSelectionOnClick
          density="compact"
          hideFooter={keys.length <= 25}
        />
      </Box>
    );
  };

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
      {error && <Alert severity="error">{error}</Alert>}

      {/* Access Groups */}
      <Card>
        <CardHeader
          title={t('accessGroups.title', 'Access Groups')}
          subheader={t('accessGroups.subtitle', 'Hierarchical groups for scoping hosts and users')}
          action={
            <Button startIcon={<AddIcon />} variant="contained" onClick={openCreateGroup}>
              {t('accessGroups.add', 'Add Group')}
            </Button>
          }
        />
        <CardContent>{renderGroupsContent()}</CardContent>
      </Card>

      {/* Registration Keys */}
      <Card>
        <CardHeader
          title={t('accessGroups.regKeysTitle', 'Registration Keys')}
          subheader={t(
            'accessGroups.regKeysSubtitle',
            'Tokens that scope incoming agent registrations to an access group',
          )}
          action={
            <Button startIcon={<KeyIcon />} variant="contained" onClick={openCreateKey}>
              {t('accessGroups.addKey', 'Add Key')}
            </Button>
          }
        />
        <CardContent>{renderKeysContent()}</CardContent>
      </Card>

      {/* Group dialog */}
      <Dialog open={groupDialogOpen} onClose={() => setGroupDialogOpen(false)} maxWidth="sm" fullWidth>
        <DialogTitle>
          {editingGroup
            ? t('accessGroups.editGroup', 'Edit Access Group')
            : t('accessGroups.add', 'Add Group')}
        </DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <TextField
              label={t('accessGroups.name', 'Name')}
              value={groupName}
              onChange={(e) => setGroupName(e.target.value)}
              fullWidth
              required
            />
            <TextField
              label={t('accessGroups.description', 'Description')}
              value={groupDescription}
              onChange={(e) => setGroupDescription(e.target.value)}
              fullWidth
              multiline
              rows={2}
            />
            <FormControl fullWidth>
              <InputLabel>{t('accessGroups.parent', 'Parent')}</InputLabel>
              <Select
                label={t('accessGroups.parent', 'Parent')}
                value={groupParentId}
                onChange={(e) => setGroupParentId(e.target.value)}
              >
                <MenuItem value="">
                  <em>{t('accessGroups.noParent', '(no parent / root)')}</em>
                </MenuItem>
                {orderedGroups
                  .filter(({ group }) => group.id !== editingGroup?.id)
                  .map(({ group, depth }) => (
                    <MenuItem key={group.id} value={group.id}>
                      {' '.repeat(depth * 2)}
                      {group.name}
                    </MenuItem>
                  ))}
              </Select>
            </FormControl>
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setGroupDialogOpen(false)}>
            {t('common.cancel', 'Cancel')}
          </Button>
          <Button onClick={handleSaveGroup} variant="contained">
            {t('common.save', 'Save')}
          </Button>
        </DialogActions>
      </Dialog>

      {/* Registration key create dialog */}
      <Dialog open={keyDialogOpen} onClose={() => setKeyDialogOpen(false)} maxWidth="sm" fullWidth>
        <DialogTitle>{t('accessGroups.addKey', 'Add Registration Key')}</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <TextField
              label={t('accessGroups.keyName', 'Name')}
              value={keyName}
              onChange={(e) => setKeyName(e.target.value)}
              fullWidth
              required
            />
            <FormControl fullWidth>
              <InputLabel>{t('accessGroups.keyAccessGroup', 'Access Group')}</InputLabel>
              <Select
                label={t('accessGroups.keyAccessGroup', 'Access Group')}
                value={keyAccessGroupId}
                onChange={(e) => setKeyAccessGroupId(e.target.value)}
              >
                <MenuItem value="">
                  <em>{t('accessGroups.noGroup', '(none)')}</em>
                </MenuItem>
                {orderedGroups.map(({ group, depth }) => (
                  <MenuItem key={group.id} value={group.id}>
                    {' '.repeat(depth * 2)}
                    {group.name}
                  </MenuItem>
                ))}
              </Select>
            </FormControl>
            <FormControlLabel
              control={
                <Checkbox
                  checked={keyAutoApprove}
                  onChange={(e) => setKeyAutoApprove(e.target.checked)}
                />
              }
              label={t('accessGroups.keyAutoApproveLabel', 'Auto-approve registrations using this key')}
            />
            <TextField
              label={t('accessGroups.keyMaxUses', 'Max Uses (blank = unlimited)')}
              value={keyMaxUses}
              onChange={(e) => setKeyMaxUses(e.target.value.replaceAll(/\D/g, ''))}
              fullWidth
            />
            <TextField
              label={t('accessGroups.keyExpires', 'Expires At')}
              type="datetime-local"
              value={keyExpiresAt}
              onChange={(e) => setKeyExpiresAt(e.target.value)}
              fullWidth
              slotProps={{ inputLabel: { shrink: true } }}
            />
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setKeyDialogOpen(false)}>
            {t('common.cancel', 'Cancel')}
          </Button>
          <Button onClick={handleCreateKey} variant="contained">
            {t('accessGroups.generateKey', 'Generate Key')}
          </Button>
        </DialogActions>
      </Dialog>

      {/* Reveal-secret dialog */}
      <Dialog
        open={!!revealedKey}
        onClose={() => setRevealedKey(null)}
        maxWidth="sm"
        fullWidth
      >
        <DialogTitle>{t('accessGroups.keyRevealTitle', 'Registration Key Created')}</DialogTitle>
        <DialogContent>
          <Alert severity="warning" sx={{ mb: 2 }}>
            {t(
              'accessGroups.keyRevealWarning',
              'This is the only time the key value will be shown. Copy it now — there is no recovery.',
            )}
          </Alert>
          {revealedKey?.key && (
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
              <TextField
                value={revealedKey.key}
                fullWidth
                slotProps={{
                  input: {
                    readOnly: true,
                    sx: { fontFamily: 'monospace' },
                  },
                }}
                onFocus={(e) => e.target.select()}
              />
              <Tooltip title={t('accessGroups.copy', 'Copy')}>
                <IconButton onClick={() => copySecret(revealedKey.key ?? '')}>
                  <ContentCopyIcon />
                </IconButton>
              </Tooltip>
            </Box>
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setRevealedKey(null)} variant="contained">
            {t('common.close', 'Close')}
          </Button>
        </DialogActions>
      </Dialog>

      <Snackbar
        open={snackbarOpen}
        autoHideDuration={4000}
        onClose={() => setSnackbarOpen(false)}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'right' }}
      >
        <Alert
          severity={snackbarSeverity}
          onClose={() => setSnackbarOpen(false)}
          variant="filled"
        >
          {snackbarMessage}
        </Alert>
      </Snackbar>
    </Box>
  );
};

export default AccessGroupsSettings;
