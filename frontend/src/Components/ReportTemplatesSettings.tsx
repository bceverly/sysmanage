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
  FormControl,
  FormControlLabel,
  FormGroup,
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
} from '@mui/icons-material';
import { useTranslation } from 'react-i18next';
import {
  ReportTemplate,
  ReportTemplateField,
  reportTemplatesService,
} from '../Services/reportTemplates';

const ReportTemplatesSettings: React.FC = () => {
  const { t } = useTranslation();

  const [templates, setTemplates] = useState<ReportTemplate[]>([]);
  const [baseTypes, setBaseTypes] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);

  const [dialogOpen, setDialogOpen] = useState(false);
  const [editing, setEditing] = useState<ReportTemplate | null>(null);
  const [form, setForm] = useState({
    name: '',
    description: '',
    base_report_type: '',
    selected_fields: [] as string[],
    enabled: true,
  });
  const [availableFields, setAvailableFields] = useState<ReportTemplateField[]>([]);

  const [snackbarOpen, setSnackbarOpen] = useState(false);
  const [snackbarMessage, setSnackbarMessage] = useState('');
  const [snackbarSeverity, setSnackbarSeverity] = useState<'success' | 'error'>('success');

  const showError = (m: string) => {
    setSnackbarMessage(m);
    setSnackbarSeverity('error');
    setSnackbarOpen(true);
  };
  const showSuccess = (m: string) => {
    setSnackbarMessage(m);
    setSnackbarSeverity('success');
    setSnackbarOpen(true);
  };

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const [list, types] = await Promise.all([
        reportTemplatesService.list(),
        reportTemplatesService.baseTypes(),
      ]);
      setTemplates(list);
      setBaseTypes(types);
    } catch (e) {
      console.error(e);
      showError(t('reportTemplates.loadError', 'Failed to load report templates'));
    } finally {
      setLoading(false);
    }
  }, [t]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const loadFieldsFor = useCallback(async (baseType: string) => {
    if (!baseType) {
      setAvailableFields([]);
      return;
    }
    try {
      const r = await reportTemplatesService.fieldsFor(baseType);
      setAvailableFields(r.fields);
    } catch (e) {
      console.error(e);
      setAvailableFields([]);
    }
  }, []);

  const openCreate = () => {
    setEditing(null);
    setForm({
      name: '',
      description: '',
      base_report_type: baseTypes[0] || '',
      selected_fields: [],
      enabled: true,
    });
    if (baseTypes[0]) loadFieldsFor(baseTypes[0]);
    setDialogOpen(true);
  };

  const openEdit = async (tmpl: ReportTemplate) => {
    setEditing(tmpl);
    setForm({
      name: tmpl.name,
      description: tmpl.description ?? '',
      base_report_type: tmpl.base_report_type,
      selected_fields: tmpl.selected_fields ?? [],
      enabled: tmpl.enabled,
    });
    await loadFieldsFor(tmpl.base_report_type);
    setDialogOpen(true);
  };

  const handleBaseTypeChange = async (newType: string) => {
    setForm((f) => ({ ...f, base_report_type: newType, selected_fields: [] }));
    await loadFieldsFor(newType);
  };

  const toggleField = (code: string) => {
    setForm((f) => ({
      ...f,
      selected_fields: f.selected_fields.includes(code)
        ? f.selected_fields.filter((c) => c !== code)
        : [...f.selected_fields, code],
    }));
  };

  const handleSave = async () => {
    if (!form.name.trim()) {
      showError(t('reportTemplates.nameRequired', 'Name is required'));
      return;
    }
    if (!form.base_report_type) {
      showError(t('reportTemplates.baseRequired', 'Base report type is required'));
      return;
    }
    if (form.selected_fields.length === 0) {
      showError(t('reportTemplates.fieldsRequired', 'Select at least one field'));
      return;
    }
    const payload = {
      name: form.name.trim(),
      description: form.description.trim() || null,
      base_report_type: form.base_report_type,
      selected_fields: form.selected_fields,
      enabled: form.enabled,
    };
    try {
      if (editing) {
        await reportTemplatesService.update(editing.id, payload);
        showSuccess(t('reportTemplates.updated', 'Template saved'));
      } else {
        await reportTemplatesService.create(payload);
        showSuccess(t('reportTemplates.created', 'Template created'));
      }
      setDialogOpen(false);
      await refresh();
    } catch (e: unknown) {
      const detail = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      showError(detail || t('reportTemplates.saveError', 'Failed to save template'));
    }
  };

  const handleDelete = async (tmpl: ReportTemplate) => {
    if (!globalThis.confirm(t('reportTemplates.confirmDelete', 'Delete report template "{{name}}"?', { name: tmpl.name }))) {
      return;
    }
    try {
      await reportTemplatesService.remove(tmpl.id);
      showSuccess(t('reportTemplates.deleted', 'Template deleted'));
      await refresh();
    } catch (e: unknown) {
      const detail = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      showError(detail || t('reportTemplates.deleteError', 'Failed to delete template'));
    }
  };

  const columns: GridColDef[] = [
    {
      field: 'name',
      headerName: t('reportTemplates.name', 'Name'),
      flex: 1,
      minWidth: 180,
    },
    {
      field: 'base_report_type',
      headerName: t('reportTemplates.baseType', 'Base Report Type'),
      width: 200,
    },
    {
      field: 'selected_fields',
      headerName: t('reportTemplates.fields', 'Fields'),
      flex: 1,
      minWidth: 220,
      renderCell: (params: GridRenderCellParams<ReportTemplate>) => (
        <Stack direction="row" spacing={0.5} sx={{ flexWrap: 'wrap', gap: 0.5 }}>
          {(params.row.selected_fields || []).slice(0, 6).map((f) => (
            <Chip key={f} size="small" label={f} />
          ))}
          {(params.row.selected_fields || []).length > 6 && (
            <Chip
              size="small"
              label={`+${(params.row.selected_fields || []).length - 6}`}
              variant="outlined"
            />
          )}
        </Stack>
      ),
    },
    {
      field: 'enabled',
      headerName: t('reportTemplates.enabled', 'Enabled'),
      width: 110,
      renderCell: (params: GridRenderCellParams<ReportTemplate>) =>
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
      width: 120,
      renderCell: (params: GridRenderCellParams<ReportTemplate>) => (
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

  const renderTemplatesContent = () => {
    if (loading) {
      return (
        <Box sx={{ display: 'flex', justifyContent: 'center', p: 3 }}>
          <CircularProgress />
        </Box>
      );
    }
    if (templates.length === 0) {
      return (
        <Typography color="text.secondary">
          {t('reportTemplates.empty', 'No report templates defined yet.')}
        </Typography>
      );
    }
    return (
      <Box sx={{ height: 420 }}>
        <DataGrid
          rows={templates}
          columns={columns}
          getRowId={(row) => row.id}
          disableRowSelectionOnClick
          density="compact"
          hideFooter={templates.length <= 25}
        />
      </Box>
    );
  };

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
      <Card>
        <CardHeader
          title={t('reportTemplates.title', 'Report Templates')}
          subheader={t(
            'reportTemplates.subtitle',
            'Custom layouts the report renderer applies on top of the built-in report types',
          )}
          action={
            <Button startIcon={<AddIcon />} variant="contained" onClick={openCreate}>
              {t('reportTemplates.add', 'Add Template')}
            </Button>
          }
        />
        <CardContent>{renderTemplatesContent()}</CardContent>
      </Card>

      <Dialog
        open={dialogOpen}
        onClose={() => setDialogOpen(false)}
        maxWidth="md"
        fullWidth
      >
        <DialogTitle>
          {editing
            ? t('reportTemplates.edit', 'Edit Report Template')
            : t('reportTemplates.add', 'Add Report Template')}
        </DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <TextField
              label={t('reportTemplates.name', 'Name')}
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
              fullWidth
              required
            />
            <TextField
              label={t('reportTemplates.description', 'Description')}
              value={form.description}
              onChange={(e) => setForm({ ...form, description: e.target.value })}
              fullWidth
              multiline
              rows={2}
            />
            <FormControl fullWidth>
              <InputLabel>{t('reportTemplates.baseType', 'Base Report Type')}</InputLabel>
              <Select
                label={t('reportTemplates.baseType', 'Base Report Type')}
                value={form.base_report_type}
                onChange={(e) => handleBaseTypeChange(e.target.value)}
              >
                {baseTypes.map((bt) => (
                  <MenuItem key={bt} value={bt}>
                    {bt}
                  </MenuItem>
                ))}
              </Select>
            </FormControl>
            <FormControlLabel
              control={
                <Checkbox
                  checked={form.enabled}
                  onChange={(e) => setForm({ ...form, enabled: e.target.checked })}
                />
              }
              label={t('reportTemplates.enabled', 'Enabled')}
            />
            <Box>
              <Typography variant="subtitle2" sx={{ mb: 1 }}>
                {t('reportTemplates.fieldsLabel', 'Fields (in order)')}
              </Typography>
              {availableFields.length === 0 ? (
                <Typography variant="body2" color="text.secondary">
                  {t(
                    'reportTemplates.noFields',
                    'Pick a base report type to see available fields.',
                  )}
                </Typography>
              ) : (
                <FormGroup>
                  {availableFields.map((f) => (
                    <FormControlLabel
                      key={f.code}
                      control={
                        <Checkbox
                          checked={form.selected_fields.includes(f.code)}
                          onChange={() => toggleField(f.code)}
                        />
                      }
                      label={`${f.label} (${f.code})`}
                    />
                  ))}
                </FormGroup>
              )}
            </Box>
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

export default ReportTemplatesSettings;
