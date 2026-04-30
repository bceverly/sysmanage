import React, { useState, useEffect, useCallback } from 'react';
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
  Divider,
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
  Delete as DeleteIcon,
  Edit as EditIcon,
  RemoveCircleOutline as RemoveIcon,
} from '@mui/icons-material';
import { useTranslation } from 'react-i18next';
import {
  CONSTRAINT_TYPES,
  PackageConstraint,
  PackageProfile,
  VERSION_OPS,
  VersionOp,
  packageProfilesService,
} from '../Services/packageProfiles';

// Synthetic per-row id used for React keys.  The DB ``id`` is optional
// (new rows don't have one), so the form state carries a stable client-
// side handle to avoid array-index keys (SonarQube).
type ConstraintRow = PackageConstraint & { _uid: string };

let _uidSeq = 0;
const _newUid = () => {
  _uidSeq += 1;
  return `c-${_uidSeq}-${Date.now().toString(36)}`;
};

const PackageProfilesSettings: React.FC = () => {
  const { t } = useTranslation();

  const [profiles, setProfiles] = useState<PackageProfile[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [snackbarOpen, setSnackbarOpen] = useState(false);
  const [snackbarMessage, setSnackbarMessage] = useState('');
  const [snackbarSeverity, setSnackbarSeverity] = useState<'success' | 'error'>('success');

  const [dialogOpen, setDialogOpen] = useState(false);
  const [editing, setEditing] = useState<PackageProfile | null>(null);
  const [form, setForm] = useState<{
    name: string;
    description: string;
    enabled: boolean;
    constraints: ConstraintRow[];
  }>({
    name: '',
    description: '',
    enabled: true,
    constraints: [],
  });

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
      // List endpoint returns profiles without constraints; constraints
      // are loaded when editing via the GET-by-id endpoint.
      const list = await packageProfilesService.list();
      setProfiles(list);
    } catch (e) {
      console.error(e);
      setError(t('packageProfiles.loadError', 'Failed to load compliance profiles'));
    } finally {
      setLoading(false);
    }
  }, [t]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const openCreate = () => {
    setEditing(null);
    setForm({ name: '', description: '', enabled: true, constraints: [] });
    setDialogOpen(true);
  };

  const openEdit = async (p: PackageProfile) => {
    try {
      const full = await packageProfilesService.get(p.id);
      setEditing(full);
      setForm({
        name: full.name,
        description: full.description ?? '',
        enabled: full.enabled,
        constraints: (full.constraints ?? []).map((c) => ({
          ...c,
          _uid: c.id ?? _newUid(),
        })),
      });
      setDialogOpen(true);
    } catch (e) {
      console.error(e);
      showError(t('packageProfiles.loadError', 'Failed to load compliance profile'));
    }
  };

  const addConstraint = () => {
    setForm({
      ...form,
      constraints: [
        ...form.constraints,
        {
          _uid: _newUid(),
          package_name: '',
          package_manager: null,
          constraint_type: 'REQUIRED',
          version_op: null,
          version: null,
        },
      ],
    });
  };

  const updateConstraint = (idx: number, patch: Partial<PackageConstraint>) => {
    setForm({
      ...form,
      constraints: form.constraints.map((c, i) => (i === idx ? { ...c, ...patch } : c)),
    });
  };

  const removeConstraint = (idx: number) => {
    setForm({
      ...form,
      constraints: form.constraints.filter((_, i) => i !== idx),
    });
  };

  const handleSave = async () => {
    if (!form.name.trim()) {
      showError(t('packageProfiles.nameRequired', 'Name is required'));
      return;
    }
    for (const c of form.constraints) {
      if (!c.package_name.trim()) {
        showError(t('packageProfiles.constraintPackageRequired', 'Every constraint needs a package name'));
        return;
      }
      if (c.version_op && !c.version) {
        showError(t('packageProfiles.constraintVersionRequired', 'Version operator requires a version value'));
        return;
      }
    }
    const payload = {
      name: form.name.trim(),
      description: form.description.trim() || null,
      enabled: form.enabled,
      constraints: form.constraints.map((c) => ({
        package_name: c.package_name.trim(),
        package_manager: c.package_manager?.trim() || null,
        constraint_type: c.constraint_type,
        version_op: c.version_op || null,
        version: c.version?.trim() || null,
      })),
    };
    try {
      if (editing) {
        await packageProfilesService.update(editing.id, payload);
        showSuccess(t('packageProfiles.updated', 'Compliance profile saved'));
      } else {
        await packageProfilesService.create(payload);
        showSuccess(t('packageProfiles.created', 'Compliance profile created'));
      }
      setDialogOpen(false);
      await refresh();
    } catch (e: unknown) {
      const detail = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      showError(detail || t('packageProfiles.saveError', 'Failed to save compliance profile'));
    }
  };

  const handleDelete = async (p: PackageProfile) => {
    if (!globalThis.confirm(t('packageProfiles.confirmDelete', 'Delete compliance profile "{{name}}"?', { name: p.name }))) {
      return;
    }
    try {
      await packageProfilesService.remove(p.id);
      showSuccess(t('packageProfiles.deleted', 'Compliance profile deleted'));
      await refresh();
    } catch (e: unknown) {
      const detail = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      showError(detail || t('packageProfiles.deleteError', 'Failed to delete compliance profile'));
    }
  };

  const columns: GridColDef[] = [
    {
      field: 'name',
      headerName: t('packageProfiles.name', 'Name'),
      flex: 1,
      minWidth: 180,
    },
    {
      field: 'description',
      headerName: t('packageProfiles.description', 'Description'),
      flex: 1.5,
      minWidth: 200,
      valueGetter: (_v, row) => row.description || '',
    },
    {
      field: 'enabled',
      headerName: t('packageProfiles.enabled', 'Enabled'),
      width: 110,
      renderCell: (params: GridRenderCellParams<PackageProfile>) =>
        params.row.enabled ? (
          <Chip size="small" color="success" label={t('common.yes', 'Yes')} />
        ) : (
          <Chip size="small" label={t('common.no', 'No')} />
        ),
    },
    {
      field: 'actions',
      headerName: t('common.actions', 'Actions'),
      sortable: false,
      width: 130,
      renderCell: (params: GridRenderCellParams<PackageProfile>) => (
        <Stack direction="row" spacing={0.5}>
          <Tooltip title={t('common.edit', 'Edit')}>
            <IconButton size="small" onClick={() => openEdit(params.row)}>
              <EditIcon fontSize="small" />
            </IconButton>
          </Tooltip>
          <Tooltip title={t('common.delete', 'Delete')}>
            <IconButton size="small" onClick={() => handleDelete(params.row)}>
              <DeleteIcon fontSize="small" />
            </IconButton>
          </Tooltip>
        </Stack>
      ),
    },
  ];

  const renderProfilesContent = () => {
    if (loading) {
      return (
        <Box sx={{ display: 'flex', justifyContent: 'center', p: 3 }}>
          <CircularProgress />
        </Box>
      );
    }
    if (profiles.length === 0) {
      return (
        <Typography color="text.secondary">
          {t('packageProfiles.empty', 'No compliance profiles defined yet.')}
        </Typography>
      );
    }
    return (
      <Box sx={{ height: 400 }}>
        <DataGrid
          rows={profiles}
          columns={columns}
          getRowId={(row) => row.id}
          disableRowSelectionOnClick
          density="compact"
          hideFooter={profiles.length <= 25}
        />
      </Box>
    );
  };

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
      {error && <Alert severity="error">{error}</Alert>}

      <Card>
        <CardHeader
          title={t('packageProfiles.title', 'Compliance Profiles')}
          subheader={t(
            'packageProfiles.subtitle',
            'Required and blocked package definitions evaluated against host inventory',
          )}
          action={
            <Button startIcon={<AddIcon />} variant="contained" onClick={openCreate}>
              {t('packageProfiles.add', 'Add Profile')}
            </Button>
          }
        />
        <CardContent>{renderProfilesContent()}</CardContent>
      </Card>

      <Dialog
        open={dialogOpen}
        onClose={() => setDialogOpen(false)}
        maxWidth="md"
        fullWidth
      >
        <DialogTitle>
          {editing
            ? t('packageProfiles.edit', 'Edit Compliance Profile')
            : t('packageProfiles.add', 'Add Compliance Profile')}
        </DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <TextField
              label={t('packageProfiles.name', 'Name')}
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
              fullWidth
              required
            />
            <TextField
              label={t('packageProfiles.description', 'Description')}
              value={form.description}
              onChange={(e) => setForm({ ...form, description: e.target.value })}
              fullWidth
              multiline
              rows={2}
            />
            <FormControlLabel
              control={
                <Checkbox
                  checked={form.enabled}
                  onChange={(e) => setForm({ ...form, enabled: e.target.checked })}
                />
              }
              label={t('packageProfiles.enabled', 'Enabled')}
            />

            <Divider />

            <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
              <Typography variant="subtitle1">
                {t('packageProfiles.constraints', 'Constraints')}
              </Typography>
              <Button
                size="small"
                startIcon={<AddIcon />}
                onClick={addConstraint}
              >
                {t('packageProfiles.addConstraint', 'Add Constraint')}
              </Button>
            </Box>

            {form.constraints.length === 0 ? (
              <Typography variant="body2" color="text.secondary">
                {t('packageProfiles.noConstraints', 'No constraints — add at least one.')}
              </Typography>
            ) : (
              <Stack spacing={1}>
                {form.constraints.map((c, idx) => (
                  <Box
                    key={c._uid}
                    sx={{
                      display: 'grid',
                      gridTemplateColumns: '1.5fr 1fr 1fr 1fr 1fr 40px',
                      gap: 1,
                      alignItems: 'center',
                    }}
                  >
                    <TextField
                      size="small"
                      label={t('packageProfiles.packageName', 'Package')}
                      value={c.package_name}
                      onChange={(e) => updateConstraint(idx, { package_name: e.target.value })}
                      required
                    />
                    <TextField
                      size="small"
                      label={t('packageProfiles.packageManager', 'Manager (any)')}
                      value={c.package_manager ?? ''}
                      onChange={(e) =>
                        updateConstraint(idx, { package_manager: e.target.value || null })
                      }
                    />
                    <FormControl size="small">
                      <InputLabel>{t('packageProfiles.constraintType', 'Type')}</InputLabel>
                      <Select
                        label={t('packageProfiles.constraintType', 'Type')}
                        value={c.constraint_type}
                        onChange={(e) =>
                          updateConstraint(idx, {
                            constraint_type: e.target.value,
                          })
                        }
                      >
                        {CONSTRAINT_TYPES.map((ct) => (
                          <MenuItem key={ct} value={ct}>
                            {ct === 'REQUIRED'
                              ? t('packageProfiles.required', 'Required')
                              : t('packageProfiles.blocked', 'Blocked')}
                          </MenuItem>
                        ))}
                      </Select>
                    </FormControl>
                    <FormControl size="small">
                      <InputLabel>{t('packageProfiles.versionOp', 'Op')}</InputLabel>
                      <Select
                        label={t('packageProfiles.versionOp', 'Op')}
                        value={c.version_op ?? ''}
                        onChange={(e) =>
                          updateConstraint(idx, {
                            version_op: (e.target.value || null) as VersionOp | null,
                          })
                        }
                      >
                        <MenuItem value="">
                          <em>{t('packageProfiles.versionOpAny', '(any)')}</em>
                        </MenuItem>
                        {VERSION_OPS.map((op) => (
                          <MenuItem key={op} value={op}>
                            {op}
                          </MenuItem>
                        ))}
                      </Select>
                    </FormControl>
                    <TextField
                      size="small"
                      label={t('packageProfiles.version', 'Version')}
                      value={c.version ?? ''}
                      onChange={(e) =>
                        updateConstraint(idx, { version: e.target.value || null })
                      }
                    />
                    <Tooltip title={t('common.delete', 'Delete')}>
                      <IconButton size="small" onClick={() => removeConstraint(idx)}>
                        <RemoveIcon fontSize="small" />
                      </IconButton>
                    </Tooltip>
                  </Box>
                ))}
              </Stack>
            )}
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setDialogOpen(false)}>
            {t('common.cancel', 'Cancel')}
          </Button>
          <Button onClick={handleSave} variant="contained">
            {t('common.save', 'Save')}
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

export default PackageProfilesSettings;
