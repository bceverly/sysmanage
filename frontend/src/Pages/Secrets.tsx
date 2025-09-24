import React, { useState, useEffect, useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import {
  IoKey,
  IoAdd,
  IoEye,
  IoPencil,
  IoTrash
} from 'react-icons/io5';
import {
  Box,
  Card,
  CardContent,
  Typography,
  Button,
  TextField,
  Select,
  MenuItem,
  FormControl,
  InputLabel,
  Grid,
  Alert,
  Snackbar,
  IconButton,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Stack
} from '@mui/material';
import { DataGrid, GridColDef, GridRowSelectionModel } from '@mui/x-data-grid';
import { useTablePageSize } from '../hooks/useTablePageSize';
import { secretsService, SecretResponse, SecretWithContent, SecretType } from '../Services/secrets';
import './css/Secrets.css';

const Secrets: React.FC = () => {
  const { t } = useTranslation();
  const [secrets, setSecrets] = useState<SecretResponse[]>([]);
  const [secretTypes, setSecretTypes] = useState<SecretType[]>([]);
  const [loading, setLoading] = useState(false);

  // Secret form state
  const [showAddSecretDialog, setShowAddSecretDialog] = useState(false);
  const [isEditMode, setIsEditMode] = useState(false);
  const [editingSecretId, setEditingSecretId] = useState<string | null>(null);
  const [secretName, setSecretName] = useState('');
  const [secretFilename, setSecretFilename] = useState('');
  const [selectedSecretType, setSelectedSecretType] = useState('api_keys');
  const [secretContent, setSecretContent] = useState('');
  const [keyVisibility, setKeyVisibility] = useState('github');

  // Secret viewing state
  const [viewingSecret, setViewingSecret] = useState<SecretWithContent | null>(null);
  const [showViewDialog, setShowViewDialog] = useState(false);

  // Confirmation dialog state
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const [deleteMessage, setDeleteMessage] = useState('');
  const [pendingDeleteAction, setPendingDeleteAction] = useState<(() => void) | null>(null);

  // Selection state
  const [selectedSecrets, setSelectedSecrets] = useState<GridRowSelectionModel>([]);

  // Table pagination
  const { pageSize, pageSizeOptions } = useTablePageSize();

  // UI state
  const [notification, setNotification] = useState<{
    open: boolean;
    message: string;
    severity: 'success' | 'error' | 'info' | 'warning';
  }>({ open: false, message: '', severity: 'info' });

  const showNotification = (message: string, severity: 'success' | 'error' | 'info' | 'warning' = 'info') => {
    setNotification({ open: true, message, severity });
  };

  const handleCloseNotification = () => {
    setNotification({ ...notification, open: false });
  };

  // Load data
  const loadSecrets = useCallback(async () => {
    try {
      setLoading(true);
      const data = await secretsService.getSecrets();
      setSecrets(data);
    } catch (error) {
      console.error('Failed to load secrets:', error);
      showNotification(t('secrets.loadError', 'Failed to load secrets'), 'error');
    } finally {
      setLoading(false);
    }
  }, [t]);

  const loadSecretTypes = useCallback(async () => {
    try {
      const data = await secretsService.getSecretTypes();
      setSecretTypes(data.types || []);
    } catch (error) {
      console.error('Failed to load secret types:', error);
      // Fallback to default types
      setSecretTypes([
        {
          value: 'api_keys',
          label: t('secrets.type.api_keys', 'API Keys'),
          supports_visibility: true,
          visibility_label: t('secrets.apiProvider', 'API Provider'),
          visibility_options: [
            { value: 'github', label: t('secrets.api_provider.github', 'Github') },
            { value: 'salesforce', label: t('secrets.api_provider.salesforce', 'Salesforce') }
          ]
        },
        {
          value: 'database_credentials',
          label: t('secrets.type.database_credentials', 'Database Credentials'),
          supports_visibility: true,
          visibility_label: t('secrets.databaseEngine', 'Database Engine'),
          visibility_options: [
            { value: 'mysql', label: t('secrets.database_engine.mysql', 'mysql') },
            { value: 'oracle', label: t('secrets.database_engine.oracle', 'Oracle') },
            { value: 'postgresql', label: t('secrets.database_engine.postgresql', 'PostgreSQL') },
            { value: 'sqlserver', label: t('secrets.database_engine.sqlserver', 'Microsoft SQL Server') },
            { value: 'sqlite', label: t('secrets.database_engine.sqlite', 'sqlite3') }
          ]
        },
        {
          value: 'ssh_key',
          label: t('secrets.type.ssh_key', 'SSH Key'),
          supports_visibility: true,
          visibility_label: t('secrets.keyType', 'Key Type'),
          visibility_options: [
            { value: 'public', label: t('secrets.key_type.public', 'Public') },
            { value: 'private', label: t('secrets.key_type.private', 'Private') },
            { value: 'ca', label: t('secrets.key_type.ca', 'CA') }
          ]
        },
        {
          value: 'ssl_certificate',
          label: t('secrets.type.ssl_certificate', 'SSL Certificate'),
          supports_visibility: true,
          visibility_label: t('secrets.certificateType', 'Certificate Type'),
          visibility_options: [
            { value: 'root', label: t('secrets.certificate_type.root', 'Root Certificate') },
            { value: 'intermediate', label: t('secrets.certificate_type.intermediate', 'Intermediate Certificate') },
            { value: 'chain', label: t('secrets.certificate_type.chain', 'Chain Certificate') },
            { value: 'key_file', label: t('secrets.certificate_type.key_file', 'Key File') },
            { value: 'certificate', label: t('secrets.certificate_type.certificate', 'Issued Certificate') }
          ]
        }
      ]);
    }
  }, [t]);

  useEffect(() => {
    loadSecrets();
    loadSecretTypes();
  }, [loadSecrets, loadSecretTypes]);

  const formatTimestamp = (timestamp: string) => {
    return new Date(timestamp).toLocaleString();
  };

  const getSelectedSecretType = (): SecretType | undefined => {
    return secretTypes.find(type => type.value === selectedSecretType);
  };

  const handleAddSecret = () => {
    setSecretName('');
    setSecretFilename('');
    setSelectedSecretType('api_keys');
    setSecretContent('');
    setKeyVisibility('github');
    setIsEditMode(false);
    setEditingSecretId(null);
    setShowAddSecretDialog(true);
  };

  const handleEditSecret = async (secretId: string) => {
    try {
      // Get secret metadata
      const secretData = await secretsService.getSecret(secretId);
      setSecretName(secretData.name);
      setSecretFilename(secretData.filename || '');
      setSelectedSecretType(secretData.secret_type);
      setKeyVisibility(secretData.secret_subtype || 'private');
      setSecretContent(''); // Don't pre-fill content for security
      setIsEditMode(true);
      setEditingSecretId(secretId);
      setShowAddSecretDialog(true);
    } catch (error) {
      console.error('Failed to load secret:', error);
      showNotification(t('secrets.loadError', 'Failed to load secret'), 'error');
    }
  };

  const handleViewSecret = async (secretId: string) => {
    try {
      setLoading(true);
      const secretData = await secretsService.getSecretContent(secretId);
      setViewingSecret(secretData);
      setShowViewDialog(true);
    } catch (error) {
      console.error('Failed to load secret content:', error);
      showNotification(t('secrets.loadContentError', 'Failed to load secret content'), 'error');
    } finally {
      setLoading(false);
    }
  };

  const handleSaveSecret = async () => {
    if (!secretName.trim()) {
      showNotification(t('secrets.nameRequired', 'Secret name is required'), 'error');
      return;
    }

    if (!secretContent.trim()) {
      showNotification(t('secrets.contentRequired', 'Secret content is required'), 'error');
      return;
    }

    try {
      setLoading(true);
      const secretData = {
        name: secretName,
        filename: secretFilename,
        secret_type: selectedSecretType,
        content: secretContent,
        secret_subtype: keyVisibility
      };

      if (isEditMode && editingSecretId) {
        await secretsService.updateSecret(editingSecretId, secretData);
      } else {
        await secretsService.createSecret(secretData);
      }

      showNotification(
        isEditMode
          ? t('secrets.updateSuccess', 'Secret updated successfully')
          : t('secrets.createSuccess', 'Secret created successfully'),
        'success'
      );

      handleCloseAddSecretDialog();
      loadSecrets();
    } catch (error) {
      console.error('Failed to save secret:', error);
      showNotification(
        isEditMode
          ? t('secrets.updateError', 'Failed to update secret')
          : t('secrets.createError', 'Failed to create secret'),
        'error'
      );
    } finally {
      setLoading(false);
    }
  };

  const handleDeleteSelected = async () => {
    if (selectedSecrets.length === 0) return;

    const confirmMessage = selectedSecrets.length === 1
      ? t('secrets.confirmDelete', 'Are you sure you want to delete this secret?')
      : t('secrets.confirmDeleteMultiple', 'Are you sure you want to delete {count} secrets?').replace('{count}', selectedSecrets.length.toString());

    setDeleteMessage(confirmMessage);
    setPendingDeleteAction(() => async () => {
      await executeDeleteSelected();
    });
    setShowDeleteConfirm(true);
  };

  const executeDeleteSelected = async () => {
    try {
      setLoading(true);

      if (selectedSecrets.length === 1) {
        // Single delete
        await secretsService.deleteSecret(selectedSecrets[0] as string);
      } else {
        // Multiple delete
        await secretsService.deleteSecrets(selectedSecrets as string[]);
      }

      showNotification(
        selectedSecrets.length === 1
          ? t('secrets.deleteSuccess', 'Secret deleted successfully')
          : t('secrets.deleteMultipleSuccess', 'Secrets deleted successfully'),
        'success'
      );

      setSelectedSecrets([]);
      loadSecrets();
    } catch (error) {
      console.error('Failed to delete secrets:', error);
      showNotification(t('secrets.deleteError', 'Failed to delete secrets'), 'error');
    } finally {
      setLoading(false);
    }
  };

  const handleConfirmDelete = async () => {
    if (pendingDeleteAction) {
      await pendingDeleteAction();
    }
    setShowDeleteConfirm(false);
    setPendingDeleteAction(null);
    setDeleteMessage('');
  };

  const handleCancelDelete = () => {
    setShowDeleteConfirm(false);
    setPendingDeleteAction(null);
    setDeleteMessage('');
  };

  const handleCloseAddSecretDialog = () => {
    setShowAddSecretDialog(false);
    setSecretName('');
    setSecretFilename('');
    setSecretContent('');
    setKeyVisibility('github');
    setIsEditMode(false);
    setEditingSecretId(null);
  };

  const handleCloseViewDialog = () => {
    setShowViewDialog(false);
    setViewingSecret(null);
  };

  // DataGrid columns definition
  const columns: GridColDef[] = [
    {
      field: 'name',
      headerName: t('secrets.secretName', 'Secret Name'),
      width: 200,
      flex: 1,
    },
    {
      field: 'filename',
      headerName: t('secrets.secretFilename', 'Filename'),
      width: 150,
      renderCell: (params) => (
        <Box sx={{ display: 'flex', alignItems: 'center', height: '100%' }}>
          <Typography variant="body2">
            {params.value || '-'}
          </Typography>
        </Box>
      ),
    },
    {
      field: 'secret_type',
      headerName: t('secrets.secretType', 'Secret Type'),
      width: 150,
      renderCell: (params) => {
        return t(`secrets.type.${params.value}`, params.value);
      },
    },
    {
      field: 'secret_subtype',
      headerName: t('secrets.secretSubtype', 'Secret Subtype'),
      width: 150,
      renderCell: (params) => {
        if (!params.value || !params.row.secret_type) return '';

        // Map the subtype based on the secret type
        if (params.row.secret_type === 'ssh_key') {
          return t(`secrets.key_type.${params.value}`, params.value);
        } else if (params.row.secret_type === 'ssl_certificate') {
          return t(`secrets.certificate_type.${params.value}`, params.value);
        } else if (params.row.secret_type === 'database_credentials') {
          return t(`secrets.database_engine.${params.value}`, params.value);
        } else if (params.row.secret_type === 'api_keys') {
          return t(`secrets.api_provider.${params.value}`, params.value);
        }
        return params.value;
      },
    },
    {
      field: 'created_at',
      headerName: t('secrets.createdDatetime', 'Created Datetime'),
      width: 180,
      renderCell: (params) => (
        <Box sx={{ display: 'flex', alignItems: 'center', height: '100%' }}>
          <Typography variant="body2">
            {formatTimestamp(params.value)}
          </Typography>
        </Box>
      ),
    },
    {
      field: 'actions',
      headerName: t('common.actions', 'Actions'),
      width: 120,
      sortable: false,
      filterable: false,
      disableColumnMenu: true,
      renderCell: (params) => (
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5, height: '100%' }}>
          <IconButton
            size="small"
            onClick={() => handleViewSecret(params.row.id)}
            title={t('secrets.viewSecret', 'View Secret')}
            sx={{ color: 'primary.main' }}
          >
            <IoEye />
          </IconButton>
          <IconButton
            size="small"
            onClick={() => handleEditSecret(params.row.id)}
            title={t('secrets.editSecret', 'Edit Secret')}
            sx={{ color: 'primary.main' }}
          >
            <IoPencil />
          </IconButton>
        </Box>
      ),
    },
  ];

  return (
    <Box className="secrets-container" sx={{ p: 3 }}>
      <Typography variant="h4" component="h1" gutterBottom>
        <IoKey style={{ marginRight: '0.5rem', verticalAlign: 'middle' }} />
        {t('secrets.title', 'Secrets')}
      </Typography>

      <Card>
        <CardContent>
          <Box sx={{ mb: 2, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <Typography variant="h6">
              {t('secrets.savedSecrets', 'Saved Secrets')}
            </Typography>
          </Box>

          <div style={{ height: 400, width: '100%' }}>
            <DataGrid
              rows={secrets}
              columns={columns}
              loading={loading}
              initialState={{
                pagination: {
                  paginationModel: { pageSize: pageSize, page: 0 },
                },
              }}
              pageSizeOptions={pageSizeOptions}
              checkboxSelection
              rowSelectionModel={selectedSecrets}
              onRowSelectionModelChange={setSelectedSecrets}
              disableRowSelectionOnClick
              localeText={{
                MuiTablePagination: {
                  labelRowsPerPage: t('common.rowsPerPage', 'Rows per page:'),
                  labelDisplayedRows: ({ from, to, count }: { from: number, to: number, count: number }) =>
                    `${from}–${to} ${t('common.of', 'of')} ${count !== -1 ? count : `${t('common.of', 'of')} ${to}`}`,
                },
                noRowsLabel: t('secrets.noSecrets', 'No secrets found'),
                noResultsOverlayLabel: t('secrets.noSecrets', 'No secrets found'),
                footerRowSelected: (count: number) =>
                  count !== 1
                    ? `${count.toLocaleString()} ${t('common.rowsSelected', 'rows selected')}`
                    : `${count.toLocaleString()} ${t('common.rowSelected', 'row selected')}`,
              }}
            />
          </div>

          <Box component="section">&nbsp;</Box>
          <Stack direction="row" spacing={2}>
            <Button
              variant="outlined"
              startIcon={<IoAdd />}
              onClick={handleAddSecret}
            >
              {t('secrets.addSecret', 'Add Secret')}
            </Button>
            <Button
              variant="outlined"
              color="error"
              startIcon={<IoTrash />}
              onClick={handleDeleteSelected}
              disabled={selectedSecrets.length === 0}
            >
              {t('secrets.deleteSelected', 'Delete Selected')}
            </Button>
          </Stack>
        </CardContent>
      </Card>

      {/* Add/Edit Secret Dialog */}
      <Dialog
        open={showAddSecretDialog}
        onClose={handleCloseAddSecretDialog}
        maxWidth="md"
        fullWidth
      >
        <DialogTitle>
          <Typography variant="h6" component="div">
            {isEditMode ? t('secrets.editSecret', 'Edit Secret') : t('secrets.addSecret', 'Add Secret')}
          </Typography>
        </DialogTitle>
        <DialogContent>
          <Box sx={{ mt: 2 }}>
            <TextField
              fullWidth
              label={t('secrets.secretName', 'Secret Name')}
              value={secretName}
              onChange={(e) => setSecretName(e.target.value)}
              margin="normal"
              required
            />

            <TextField
              fullWidth
              label={t('secrets.secretFilename', 'Filename')}
              value={secretFilename}
              onChange={(e) => setSecretFilename(e.target.value)}
              margin="normal"
              placeholder="e.g., id_rsa.pub, server.crt, database.conf"
            />

            <FormControl fullWidth margin="normal">
              <InputLabel>{t('secrets.secretType', 'Secret Type')}</InputLabel>
              <Select
                value={selectedSecretType}
                label={t('secrets.secretType', 'Secret Type')}
                onChange={(e) => setSelectedSecretType(e.target.value)}
              >
                {secretTypes.map((type) => (
                  <MenuItem key={type.value} value={type.value}>
                    {t(`secrets.type.${type.value}`, type.value)}
                  </MenuItem>
                ))}
              </Select>
            </FormControl>

            <TextField
              fullWidth
              label={isEditMode
                ? t('secrets.replaceExistingSecret', 'Replace existing secret')
                : t('secrets.secretContent', 'Secret Content')
              }
              value={secretContent}
              onChange={(e) => setSecretContent(e.target.value)}
              margin="normal"
              multiline
              rows={6}
              required
              placeholder={isEditMode
                ? t('secrets.replaceExistingSecretHint', 'Enter new secret content to replace the existing secret')
                : t('secrets.pasteSecretHint', 'Paste your secret content here')
              }
            />

            {getSelectedSecretType()?.supports_visibility && (
              <FormControl fullWidth margin="normal">
                <InputLabel>{t(getSelectedSecretType()?.visibility_label || 'secrets.keyVisibility')}</InputLabel>
                <Select
                  value={keyVisibility}
                  label={t(getSelectedSecretType()?.visibility_label || 'secrets.keyVisibility')}
                  onChange={(e) => setKeyVisibility(e.target.value)}
                >
                  {getSelectedSecretType()?.visibility_options?.map((option) => (
                    <MenuItem key={option.value} value={option.value}>
                      {(() => {
                        if (selectedSecretType === 'ssh_key') {
                          return t(`secrets.key_type.${option.value}`, option.value);
                        } else if (selectedSecretType === 'ssl_certificate') {
                          return t(`secrets.certificate_type.${option.value}`, option.value);
                        } else if (selectedSecretType === 'database_credentials') {
                          return t(`secrets.database_engine.${option.value}`, option.value);
                        } else if (selectedSecretType === 'api_keys') {
                          return t(`secrets.api_provider.${option.value}`, option.value);
                        }
                        return option.value;
                      })()}
                    </MenuItem>
                  ))}
                </Select>
              </FormControl>
            )}
          </Box>
        </DialogContent>
        <DialogActions>
          <Button onClick={handleCloseAddSecretDialog}>
            {t('common.cancel', 'Cancel')}
          </Button>
          <Button
            variant="contained"
            onClick={handleSaveSecret}
            disabled={loading}
          >
            {isEditMode ? t('common.save', 'Save') : t('common.save', 'Save')}
          </Button>
        </DialogActions>
      </Dialog>

      {/* View Secret Dialog */}
      <Dialog
        open={showViewDialog}
        onClose={handleCloseViewDialog}
        maxWidth="md"
        fullWidth
      >
        {viewingSecret && (
          <>
            <DialogTitle>
              <Typography variant="h6" component="div">
                {viewingSecret.name}
              </Typography>
            </DialogTitle>
            <DialogContent>
              <Box sx={{ mb: 2 }}>
                <Grid container spacing={2}>
                  <Grid item xs={12} md={6}>
                    <Typography variant="body2" gutterBottom>
                      <strong>{t('secrets.secretType', 'Secret Type')}:</strong> {t(`secrets.type.${viewingSecret.secret_type}`, viewingSecret.secret_type)}
                    </Typography>
                  </Grid>
                  {viewingSecret.filename && (
                    <Grid item xs={12} md={6}>
                      <Typography variant="body2" gutterBottom>
                        <strong>{t('secrets.secretFilename', 'Filename')}:</strong> {viewingSecret.filename}
                      </Typography>
                    </Grid>
                  )}
                  {viewingSecret.secret_subtype && (
                    <Grid item xs={12} md={6}>
                      <Typography variant="body2" gutterBottom>
                        <strong>
                          {t(secretTypes.find(t => t.value === viewingSecret.secret_type)?.visibility_label || 'secrets.keyVisibility')}:
                        </strong>{' '}
                        {(() => {
                          if (viewingSecret.secret_type === 'ssh_key') {
                            return t(`secrets.key_type.${viewingSecret.secret_subtype}`, viewingSecret.secret_subtype);
                          } else if (viewingSecret.secret_type === 'ssl_certificate') {
                            return t(`secrets.certificate_type.${viewingSecret.secret_subtype}`, viewingSecret.secret_subtype);
                          } else if (viewingSecret.secret_type === 'database_credentials') {
                            return t(`secrets.database_engine.${viewingSecret.secret_subtype}`, viewingSecret.secret_subtype);
                          } else if (viewingSecret.secret_type === 'api_keys') {
                            return t(`secrets.api_provider.${viewingSecret.secret_subtype}`, viewingSecret.secret_subtype);
                          }
                          return viewingSecret.secret_subtype;
                        })()}
                      </Typography>
                    </Grid>
                  )}
                  <Grid item xs={12} md={6}>
                    <Typography variant="body2" gutterBottom>
                      <strong>{t('secrets.createdAt', 'Created At')}:</strong> {formatTimestamp(viewingSecret.created_at)}
                    </Typography>
                  </Grid>
                  <Grid item xs={12} md={6}>
                    <Typography variant="body2" gutterBottom>
                      <strong>{t('secrets.updatedAt', 'Updated At')}:</strong> {formatTimestamp(viewingSecret.updated_at)}
                    </Typography>
                  </Grid>
                </Grid>
              </Box>

              <Typography variant="subtitle2" gutterBottom>
                {t('secrets.secretContent', 'Secret Content')}
              </Typography>
              <Box sx={{
                bgcolor: '#1e1e1e',
                color: '#d4d4d4',
                p: 2,
                borderRadius: 1,
                fontFamily: 'monospace',
                fontSize: '0.875rem',
                maxHeight: 300,
                overflow: 'auto',
                whiteSpace: 'pre-wrap',
                wordBreak: 'break-all'
              }}>
                {t('secrets.contentHidden', '[Content Hidden for Security]')}
              </Box>
            </DialogContent>
            <DialogActions>
              <Button onClick={handleCloseViewDialog}>
                {t('common.close', 'Close')}
              </Button>
            </DialogActions>
          </>
        )}
      </Dialog>

      {/* Delete Confirmation Dialog */}
      <Dialog
        open={showDeleteConfirm}
        onClose={handleCancelDelete}
        maxWidth="sm"
        fullWidth
      >
        <DialogTitle>
          <Typography variant="h6" component="div">
            {t('common.confirmAction', 'Confirm Action')}
          </Typography>
        </DialogTitle>
        <DialogContent>
          <Typography variant="body1">
            {deleteMessage}
          </Typography>
        </DialogContent>
        <DialogActions>
          <Button onClick={handleCancelDelete}>
            {t('common.cancel', 'Cancel')}
          </Button>
          <Button
            variant="contained"
            color="error"
            onClick={handleConfirmDelete}
            disabled={loading}
          >
            {t('common.delete', 'Delete')}
          </Button>
        </DialogActions>
      </Dialog>

      {/* Notification Snackbar */}
      <Snackbar
        open={notification.open}
        autoHideDuration={6000}
        onClose={handleCloseNotification}
      >
        <Alert
          onClose={handleCloseNotification}
          severity={notification.severity}
          sx={{ width: '100%' }}
        >
          {notification.message}
        </Alert>
      </Snackbar>
    </Box>
  );
};

export default Secrets;