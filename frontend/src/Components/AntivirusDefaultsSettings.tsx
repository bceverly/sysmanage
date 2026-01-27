import React, { useState, useEffect, useCallback } from 'react';
import {
  Box,
  Card,
  CardContent,
  Typography,
  Button,
  Alert,
  Snackbar,
  Stack,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
  CircularProgress,
  IconButton,
  Grid,
  Divider,
} from '@mui/material';
import {
  Save as SaveIcon,
  Security as SecurityIcon,
  Edit as EditIcon,
  Cancel as CancelIcon,
} from '@mui/icons-material';
import { useTranslation } from 'react-i18next';
import axiosInstance from '../Services/api';
import { hasPermission, SecurityRoles } from '../Services/permissions';

interface AntivirusDefault {
  os_name: string;
  antivirus_package: string | null;
}

// Mapping of operating systems to available open-source antivirus packages
// Grouped by major OS type and alphabetized within each group
const ANTIVIRUS_OPTIONS: Record<string, string[]> = {
  // Linux
  'AlmaLinux': ['clamav', 'chkrootkit', 'rkhunter'],
  'CentOS': ['clamav', 'chkrootkit', 'rkhunter'],
  'CentOS Stream': ['clamav', 'chkrootkit', 'rkhunter'],
  'Debian': ['clamav', 'chkrootkit', 'rkhunter'],
  'Fedora': ['clamav', 'chkrootkit', 'rkhunter'],
  'openSUSE': ['clamav', 'chkrootkit', 'rkhunter'],
  'RHEL': ['clamav', 'chkrootkit', 'rkhunter'],
  'Rocky Linux': ['clamav', 'chkrootkit', 'rkhunter'],
  'SLES': ['clamav', 'chkrootkit', 'rkhunter'],
  'Ubuntu': ['clamav', 'chkrootkit', 'rkhunter'],
  // BSD
  'FreeBSD': ['clamav', 'rkhunter'],
  'NetBSD': ['clamav', 'rkhunter'],
  'OpenBSD': ['clamav'],
  // macOS
  'macOS': ['clamav'],
  // Windows
  'Windows': ['clamav'],
};

// Operating system groups for display (alphabetized by group name)
const OS_GROUPS = {
  'BSD': ['FreeBSD', 'NetBSD', 'OpenBSD'],
  'Linux': [
    'AlmaLinux', 'CentOS', 'CentOS Stream', 'Debian', 'Fedora',
    'openSUSE', 'RHEL', 'Rocky Linux', 'SLES', 'Ubuntu'
  ],
  'macOS': ['macOS'],
  'Windows': ['Windows'],
};

const AntivirusDefaultsSettings: React.FC = () => {
  const { t } = useTranslation();

  // State management
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [editMode, setEditMode] = useState(false);
  const [antivirusDefaults, setAntivirusDefaults] = useState<Record<string, string>>({});
  const [editedDefaults, setEditedDefaults] = useState<Record<string, string>>({});

  // UI state
  const [snackbarOpen, setSnackbarOpen] = useState(false);
  const [snackbarMessage, setSnackbarMessage] = useState('');
  const [snackbarSeverity, setSnackbarSeverity] = useState<'success' | 'error'>('success');

  // Permission state
  const [canManageAntivirusDefaults, setCanManageAntivirusDefaults] = useState<boolean>(false);

  // Helper functions
  const showSnackbar = useCallback((message: string, severity: 'success' | 'error') => {
    setSnackbarMessage(message);
    setSnackbarSeverity(severity);
    setSnackbarOpen(true);
  }, []);

  const loadDefaults = useCallback(async () => {
    setLoading(true);
    try {
      const response = await axiosInstance.get<AntivirusDefault[]>('/api/antivirus-defaults/');

      // Convert array to object for easier state management
      const defaultsMap: Record<string, string> = {};
      response.data.forEach((item) => {
        defaultsMap[item.os_name] = item.antivirus_package || '';
      });
      setAntivirusDefaults(defaultsMap);
    } catch (error) {
      console.error('Error loading antivirus defaults:', error);
      showSnackbar(t('antivirus.errors.loadFailed', 'Failed to load antivirus defaults'), 'error');
    } finally {
      setLoading(false);
    }
  }, [t, showSnackbar]);

  // Check permissions
  useEffect(() => {
    const checkPermission = async () => {
      const canManage = await hasPermission(SecurityRoles.MANAGE_ANTIVIRUS_DEFAULTS);
      setCanManageAntivirusDefaults(canManage);
    };
    checkPermission();
  }, []);

  // Load defaults on component mount
  useEffect(() => {
    loadDefaults();
  }, [loadDefaults]);

  const handleEdit = () => {
    setEditedDefaults({ ...antivirusDefaults });
    setEditMode(true);
  };

  const handleCancel = () => {
    setEditedDefaults({});
    setEditMode(false);
  };

  const handleAntivirusChange = (osName: string, packageName: string) => {
    setEditedDefaults((prev) => ({
      ...prev,
      [osName]: packageName,
    }));
  };

  const handleSave = async () => {
    if (!canManageAntivirusDefaults) {
      showSnackbar(t('antivirus.errors.permissionDenied', 'You do not have permission to manage antivirus defaults'), 'error');
      return;
    }

    setSaving(true);
    try {
      // Convert the defaults map to array format for the API
      // Helper to get antivirus package value, handling empty strings
      const getAntivirusPackage = (osName: string): string | null => {
        if (!Object.hasOwn(editedDefaults, osName)) return null; // nosemgrep: detect-object-injection
        const value = editedDefaults[osName]; // nosemgrep: detect-object-injection
        if (value === '') return null;
        return value || null;
      };

      // Safely access with Object.hasOwn check to prevent prototype pollution
      const defaultsArray = Object.keys(ANTIVIRUS_OPTIONS).map((osName) => ({
        os_name: osName,
        antivirus_package: getAntivirusPackage(osName),
      }));

      await axiosInstance.put('/api/antivirus-defaults/', {
        defaults: defaultsArray,
      });

      showSnackbar(t('antivirus.saveSuccess', 'Antivirus defaults saved successfully'), 'success');
      await loadDefaults();
      setEditMode(false);
      setEditedDefaults({});
    } catch (error) {
      console.error('Error saving antivirus defaults:', error);
      showSnackbar(t('antivirus.errors.saveFailed', 'Failed to save antivirus defaults'), 'error');
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <Box display="flex" justifyContent="center" alignItems="center" minHeight="200px">
        <CircularProgress />
      </Box>
    );
  }

  return (
    <Box>
      <Card>
        <CardContent>
          <Stack spacing={3}>
            {/* Header with Edit Icon */}
            <Box display="flex" alignItems="center" justifyContent="space-between">
              <Box display="flex" alignItems="center" gap={2}>
                <SecurityIcon color="primary" fontSize="large" />
                <Box>
                  <Typography variant="h5" component="h2">
                    {t('antivirus.title', 'Antivirus Defaults')}
                  </Typography>
                  <Typography variant="body2" color="text.secondary">
                    {t('antivirus.description', 'Configure default antivirus software for each operating system')}
                  </Typography>
                </Box>
              </Box>
              {!editMode && canManageAntivirusDefaults && (
                <IconButton onClick={handleEdit} color="primary">
                  <EditIcon />
                </IconButton>
              )}
            </Box>

            {!canManageAntivirusDefaults && (
              <Alert severity="warning">
                {t('antivirus.permissionWarning', 'You do not have permission to modify antivirus defaults. Contact your administrator to gain the MANAGE_ANTIVIRUS_DEFAULTS role.')}
              </Alert>
            )}

            {/* View Mode - Static List Grouped by OS Type */}
            {!editMode && (
              <Stack spacing={3}>
                {Object.entries(OS_GROUPS).map(([groupName, osList]) => (
                  <Box key={groupName}>
                    <Typography variant="h6" gutterBottom sx={{ color: 'primary.main', mb: 2 }}>
                      {groupName}
                    </Typography>
                    <Grid container spacing={2}>
                      {osList.map((osName) => (
                        <Grid size={{ xs: 12, sm: 6, md: 4 }} key={osName}>
                          <Box sx={{ p: 1.5, border: '1px solid', borderColor: 'divider', borderRadius: 1 }}>
                            <Typography variant="body2" fontWeight="medium">
                              {osName}
                            </Typography>
                            <Typography variant="caption" color="text.secondary">
                              {antivirusDefaults[osName] || t('antivirus.none', 'None')} {/* nosemgrep: detect-object-injection */}
                            </Typography>
                          </Box>
                        </Grid>
                      ))}
                    </Grid>
                    {groupName !== 'Windows' && <Divider sx={{ mt: 2 }} />}
                  </Box>
                ))}
              </Stack>
            )}

            {/* Edit Mode - Dropdowns Grouped by OS Type */}
            {editMode && (
              <Stack spacing={3}>
                {Object.entries(OS_GROUPS).map(([groupName, osList]) => (
                  <Box key={groupName}>
                    <Typography variant="h6" gutterBottom sx={{ color: 'primary.main', mb: 2 }}>
                      {groupName}
                    </Typography>
                    <Grid container spacing={2}>
                      {osList.map((osName) => (
                        <Grid size={{ xs: 12, sm: 6, md: 4 }} key={osName}>
                          <Typography variant="body2" fontWeight="medium" gutterBottom>
                            {osName}
                          </Typography>
                          <FormControl fullWidth size="small">
                            <InputLabel id={`antivirus-${osName}-label`}>
                              {t('antivirus.selectProgram', 'Select Antivirus Program')}
                            </InputLabel>
                            {/* nosemgrep: detect-object-injection */}
                            <Select
                              labelId={`antivirus-${osName}-label`}
                              id={`antivirus-${osName}`}
                              value={editedDefaults[osName] || ''}
                              onChange={(e) => handleAntivirusChange(osName, e.target.value)}
                              label={t('antivirus.selectProgram', 'Select Antivirus Program')}
                            >
                              <MenuItem value="">
                                {t('antivirus.none', 'None')}
                              </MenuItem>
                              {(ANTIVIRUS_OPTIONS[osName] ?? []).map((packageName) => (
                                <MenuItem key={packageName} value={packageName}>
                                  {packageName}
                                </MenuItem>
                              ))}
                            </Select>
                          </FormControl>
                        </Grid>
                      ))}
                    </Grid>
                    {groupName !== 'Windows' && <Divider sx={{ mt: 2 }} />}
                  </Box>
                ))}

                {/* Save and Cancel Buttons */}
                <Box display="flex" justifyContent="flex-end" gap={2} sx={{ mt: 3 }}>
                  <Button
                    variant="outlined"
                    startIcon={<CancelIcon />}
                    onClick={handleCancel}
                    disabled={saving}
                  >
                    {t('common.cancel', 'Cancel')}
                  </Button>
                  <Button
                    variant="contained"
                    color="primary"
                    startIcon={saving ? <CircularProgress size={20} /> : <SaveIcon />}
                    onClick={handleSave}
                    disabled={saving}
                  >
                    {t('antivirus.save', 'Save')}
                  </Button>
                </Box>
              </Stack>
            )}
          </Stack>
        </CardContent>
      </Card>

      {/* Snackbar for notifications */}
      <Snackbar
        open={snackbarOpen}
        autoHideDuration={6000}
        onClose={() => setSnackbarOpen(false)}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'right' }}
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

export default AntivirusDefaultsSettings;
