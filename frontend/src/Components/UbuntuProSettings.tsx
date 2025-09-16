import React, { useState, useEffect, useCallback } from 'react';
import {
  Box,
  Card,
  CardContent,
  Typography,
  TextField,
  Button,
  Switch,
  FormControlLabel,
  Alert,
  Snackbar,
  InputAdornment,
  IconButton,
  Stack,
  Chip,
  CircularProgress,
} from '@mui/material';
import {
  Visibility as VisibilityIcon,
  VisibilityOff as VisibilityOffIcon,
  Save as SaveIcon,
  Delete as DeleteIcon,
  Security as SecurityIcon,
} from '@mui/icons-material';
import { useTranslation } from 'react-i18next';
import axiosInstance from '../Services/api';

interface MasterKeyStatus {
  has_master_key: boolean;
  organization_name: string | null;
  auto_attach_enabled: boolean;
}

const UbuntuProSettings: React.FC = () => {
  const { t } = useTranslation();

  // State management
  const [keyStatus, setKeyStatus] = useState<MasterKeyStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  // Form state
  const [masterKey, setMasterKey] = useState('');
  const [organizationName, setOrganizationName] = useState('');
  const [autoAttachEnabled, setAutoAttachEnabled] = useState(false);
  const [showMasterKey, setShowMasterKey] = useState(false);

  // UI state
  const [snackbarOpen, setSnackbarOpen] = useState(false);
  const [snackbarMessage, setSnackbarMessage] = useState('');
  const [snackbarSeverity, setSnackbarSeverity] = useState<'success' | 'error'>('success');

  // Helper functions
  const showSnackbar = useCallback((message: string, severity: 'success' | 'error') => {
    setSnackbarMessage(message);
    setSnackbarSeverity(severity);
    setSnackbarOpen(true);
  }, []);

  const loadSettings = useCallback(async () => {
    try {
      const response = await axiosInstance.get('/api/ubuntu-pro/');
      const data = response.data;
      setMasterKey(data.master_key || '');
      setOrganizationName(data.organization_name || '');
      setAutoAttachEnabled(data.auto_attach_enabled || false);
    } catch (error) {
      console.error('Error loading Ubuntu Pro settings:', error);
      showSnackbar(t('ubuntuPro.errors.loadFailed', 'Failed to load Ubuntu Pro settings'), 'error');
    } finally {
      setLoading(false);
    }
  }, [t, showSnackbar]);

  const loadKeyStatus = useCallback(async () => {
    try {
      const response = await axiosInstance.get('/api/ubuntu-pro/master-key/status');
      setKeyStatus(response.data);
    } catch (error) {
      console.error('Error loading master key status:', error);
    }
  }, []);

  // Load settings on component mount
  useEffect(() => {
    loadSettings();
    loadKeyStatus();
  }, [loadSettings, loadKeyStatus]);

  const saveSettings = async () => {
    setSaving(true);
    try {
      const payload = {
        master_key: masterKey.trim() || null,
        organization_name: organizationName.trim() || null,
        auto_attach_enabled: autoAttachEnabled,
      };

      await axiosInstance.put('/api/ubuntu-pro/', payload);
      loadKeyStatus(); // Refresh status
      showSnackbar(t('ubuntuPro.messages.saveSuccess', 'Ubuntu Pro settings saved successfully'), 'success');
    } catch (error: unknown) {
      console.error('Error saving Ubuntu Pro settings:', error);
      const message = (error as {response?: {data?: {detail?: string}}})?.response?.data?.detail || t('ubuntuPro.errors.saveFailed', 'Failed to save Ubuntu Pro settings');
      showSnackbar(message, 'error');
    } finally {
      setSaving(false);
    }
  };

  const clearMasterKey = async () => {
    setSaving(true);
    try {
      await axiosInstance.delete('/api/ubuntu-pro/master-key');
      setMasterKey('');
      loadKeyStatus();
      showSnackbar(t('ubuntuPro.messages.keyCleared', 'Master key cleared successfully'), 'success');
    } catch (error: unknown) {
      console.error('Error clearing master key:', error);
      const message = (error as {response?: {data?: {detail?: string}}})?.response?.data?.detail || t('ubuntuPro.errors.clearFailed', 'Failed to clear master key');
      showSnackbar(message, 'error');
    } finally {
      setSaving(false);
    }
  };

  const validateMasterKey = (key: string) => {
    if (!key.trim()) return true; // Empty is valid (will be stored as null)
    return key.startsWith('C') && key.length >= 24;
  };

  const isFormValid = () => {
    return validateMasterKey(masterKey) && organizationName.length <= 255;
  };

  if (loading) {
    return (
      <Box display="flex" justifyContent="center" alignItems="center" height="200px">
        <CircularProgress />
      </Box>
    );
  }

  return (
    <Box>
      <Card>
        <CardContent>
          <Stack spacing={3}>
            {/* Header */}
            <Box display="flex" alignItems="center" gap={1}>
              <SecurityIcon color="primary" />
              <Typography variant="h6">
                {t('ubuntuPro.settings.title', 'Ubuntu Pro Settings')}
              </Typography>
            </Box>

            <Typography variant="body2" color="text.secondary">
              {t('ubuntuPro.settings.description',
                'Configure a master Ubuntu Pro key for bulk enrollment of hosts. This key will be pre-filled in enrollment dialogs.')}
            </Typography>

            {/* Status indicators */}
            <Box display="flex" gap={2}>
              {keyStatus?.has_master_key && (
                <Chip
                  icon={<SecurityIcon />}
                  label={t('ubuntuPro.status.keyConfigured', 'Master key configured')}
                  color="success"
                  size="small"
                />
              )}
              {keyStatus?.auto_attach_enabled && (
                <Chip
                  label={t('ubuntuPro.status.autoAttachEnabled', 'Auto-attach enabled')}
                  color="primary"
                  size="small"
                />
              )}
            </Box>

            {/* Organization name */}
            <TextField
              label={t('ubuntuPro.fields.organizationName', 'Organization Name')}
              value={organizationName}
              onChange={(e) => setOrganizationName(e.target.value)}
              fullWidth
              variant="outlined"
              helperText={t('ubuntuPro.fields.organizationNameHelp',
                'Optional organization name for Ubuntu Pro enrollment')}
              error={organizationName.length > 255}
            />

            {/* Master key */}
            <TextField
              label={t('ubuntuPro.fields.masterKey', 'Ubuntu Pro Master Key')}
              type={showMasterKey ? 'text' : 'password'}
              value={masterKey}
              onChange={(e) => setMasterKey(e.target.value)}
              fullWidth
              variant="outlined"
              helperText={t('ubuntuPro.fields.masterKeyHelp',
                'Contract-based Ubuntu Pro key starting with "C". Leave empty to remove.')}
              error={!validateMasterKey(masterKey)}
              InputProps={{
                endAdornment: (
                  <InputAdornment position="end">
                    <IconButton
                      onClick={() => setShowMasterKey(!showMasterKey)}
                      edge="end"
                      aria-label={t('common.togglePasswordVisibility', 'Toggle password visibility')}
                    >
                      {showMasterKey ? <VisibilityOffIcon /> : <VisibilityIcon />}
                    </IconButton>
                  </InputAdornment>
                ),
              }}
            />

            {/* Validation error for master key */}
            {masterKey.trim() && !validateMasterKey(masterKey) && (
              <Alert severity="error">
                {t('ubuntuPro.validation.invalidKey',
                  'Ubuntu Pro key must start with "C" and be at least 24 characters long')}
              </Alert>
            )}

            {/* Auto attach setting */}
            <FormControlLabel
              control={
                <Switch
                  checked={autoAttachEnabled}
                  onChange={(e) => setAutoAttachEnabled(e.target.checked)}
                  color="primary"
                />
              }
              label={t('ubuntuPro.fields.autoAttachEnabled', 'Auto-attach Enabled')}
            />
            <Typography variant="caption" color="text.secondary" sx={{ mt: -1 }}>
              {t('ubuntuPro.fields.autoAttachEnabledHelp',
                'Automatically attach new Ubuntu hosts to Pro using the master key')}
            </Typography>

            {/* Action buttons */}
            <Stack direction="row" spacing={2} sx={{ mt: 3 }}>
              <Button
                variant="contained"
                startIcon={saving ? <CircularProgress size={20} /> : <SaveIcon />}
                onClick={saveSettings}
                disabled={!isFormValid() || saving}
              >
                {t('common.save', 'Save')}
              </Button>

              {keyStatus?.has_master_key && (
                <Button
                  variant="outlined"
                  color="error"
                  startIcon={<DeleteIcon />}
                  onClick={clearMasterKey}
                  disabled={saving}
                >
                  {t('ubuntuPro.actions.clearKey', 'Clear Key')}
                </Button>
              )}
            </Stack>
          </Stack>
        </CardContent>
      </Card>

      {/* Success/Error Snackbar */}
      <Snackbar
        open={snackbarOpen}
        autoHideDuration={6000}
        onClose={() => setSnackbarOpen(false)}
      >
        <Alert
          onClose={() => setSnackbarOpen(false)}
          severity={snackbarSeverity}
          sx={{ width: '100%' }}
        >
          {snackbarMessage}
        </Alert>
      </Snackbar>
    </Box>
  );
};

export default UbuntuProSettings;