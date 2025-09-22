import React, { useState, useEffect } from 'react';
import {
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Button,
  TextField,
  FormControlLabel,
  Switch,
  Alert,
  Box,
  Typography,
  Chip,
  Stack,
  List,
  ListItem,
  ListItemText,
  IconButton,
  InputAdornment,
  CircularProgress,
} from '@mui/material';
import {
  Visibility as VisibilityIcon,
  VisibilityOff as VisibilityOffIcon,
  Security as SecurityIcon,
  Computer as ComputerIcon,
} from '@mui/icons-material';
import { useTranslation } from 'react-i18next';
import axiosInstance from '../Services/api';

interface Host {
  id: string;
  fqdn: string;
  ipv4?: string;
  ipv6?: string;
  active: boolean;
  status: string;
}

interface UbuntuProEnrollmentDialogProps {
  open: boolean;
  onClose: () => void;
  hosts: Host[];
  onEnrollmentComplete?: () => void;
}

interface EnrollmentResult {
  host_id: string;
  hostname?: string;
  success: boolean;
  message?: string;
  error?: string;
}

const UbuntuProEnrollmentDialog: React.FC<UbuntuProEnrollmentDialogProps> = ({
  open,
  onClose,
  hosts,
  onEnrollmentComplete,
}) => {
  const { t } = useTranslation();

  // Form state
  const [useMasterKey, setUseMasterKey] = useState(true);
  const [customKey, setCustomKey] = useState('');
  const [showCustomKey, setShowCustomKey] = useState(false);

  // UI state
  const [loading, setLoading] = useState(false);
  const [masterKeyAvailable, setMasterKeyAvailable] = useState(false);
  const [organizationName, setOrganizationName] = useState<string | null>(null);
  const [enrollmentResults, setEnrollmentResults] = useState<EnrollmentResult[]>([]);
  const [showResults, setShowResults] = useState(false);

  // Load master key status when dialog opens
  useEffect(() => {
    if (open) {
      loadMasterKeyStatus();
      setEnrollmentResults([]);
      setShowResults(false);
      setCustomKey('');
      setUseMasterKey(true);
    }
  }, [open]);

  const loadMasterKeyStatus = async () => {
    try {
      const response = await axiosInstance.get('/api/ubuntu-pro/master-key/status');
      const data = response.data;
      setMasterKeyAvailable(data.has_master_key);
      setOrganizationName(data.organization_name);

      // If no master key available, switch to custom key mode
      if (!data.has_master_key) {
        setUseMasterKey(false);
      }
    } catch (error) {
      console.error('Error loading master key status:', error);
      setMasterKeyAvailable(false);
      setUseMasterKey(false);
    }
  };

  const validateCustomKey = (key: string) => {
    if (!key.trim()) return false;
    return key.startsWith('C') && key.length >= 24;
  };

  const isFormValid = () => {
    if (useMasterKey) {
      return masterKeyAvailable;
    } else {
      return validateCustomKey(customKey);
    }
  };

  const handleEnroll = async () => {
    if (!isFormValid()) return;

    setLoading(true);
    try {
      const payload = {
        host_ids: hosts.map(h => h.id),
        use_master_key: useMasterKey,
        custom_key: useMasterKey ? null : customKey,
      };

      const response = await axiosInstance.post('/api/ubuntu-pro/enroll', payload);
      setEnrollmentResults(response.data.results || []);
      setShowResults(true);

      // Call completion callback if all enrollments succeeded
      const allSucceeded = response.data.results.every((result: EnrollmentResult) => result.success);
      if (allSucceeded && onEnrollmentComplete) {
        onEnrollmentComplete();
      }
    } catch (error: unknown) {
      console.error('Error enrolling hosts:', error);
      const errorMessage = (error as {response?: {data?: {detail?: string}}})?.response?.data?.detail || t('ubuntuPro.errors.enrollmentFailed', 'Enrollment failed');

      // Show error as a result
      setEnrollmentResults([{
        host_id: '',
        hostname: 'Error',
        success: false,
        error: errorMessage,
      }]);
      setShowResults(true);
    } finally {
      setLoading(false);
    }
  };

  const handleClose = () => {
    if (!loading) {
      setShowResults(false);
      setEnrollmentResults([]);
      onClose();
    }
  };

  const renderHostList = () => (
    <Box>
      <Typography variant="subtitle2" sx={{ mb: 2 }}>
        {t('ubuntuPro.enrollment.selectedHosts', 'Selected Hosts')} ({hosts.length})
      </Typography>
      <List dense>
        {hosts.slice(0, 5).map((host) => (
          <ListItem key={host.id} sx={{ py: 0.5 }}>
            <ComputerIcon sx={{ mr: 1, fontSize: 20 }} />
            <ListItemText
              primary={host.fqdn}
              secondary={host.ipv4}
              primaryTypographyProps={{ fontSize: '0.875rem' }}
              secondaryTypographyProps={{ fontSize: '0.75rem' }}
            />
          </ListItem>
        ))}
        {hosts.length > 5 && (
          <ListItem>
            <ListItemText
              primary={t('ubuntuPro.enrollment.andMore', 'And {count} more...', { count: hosts.length - 5 })}
              primaryTypographyProps={{ fontSize: '0.875rem', fontStyle: 'italic' }}
            />
          </ListItem>
        )}
      </List>
    </Box>
  );

  const renderEnrollmentForm = () => (
    <Stack spacing={3}>
      {renderHostList()}

      {/* Master key status */}
      <Box>
        <Typography variant="subtitle2" sx={{ mb: 1 }}>
          {t('ubuntuPro.enrollment.keySource', 'Enrollment Key Source')}
        </Typography>

        <Stack spacing={2}>
          {masterKeyAvailable && (
            <Box>
              <FormControlLabel
                control={
                  <Switch
                    checked={useMasterKey}
                    onChange={(e) => setUseMasterKey(e.target.checked)}
                    color="primary"
                  />
                }
                label={t('ubuntuPro.enrollment.useMasterKey', 'Use configured master key')}
              />

              {useMasterKey && organizationName && (
                <Box sx={{ ml: 4, mt: 1 }}>
                  <Chip
                    icon={<SecurityIcon />}
                    label={t('ubuntuPro.enrollment.organization', 'Organization: {name}', { name: organizationName })}
                    size="small"
                    color="primary"
                  />
                </Box>
              )}
            </Box>
          )}

          {!masterKeyAvailable && (
            <Alert severity="info">
              {t('ubuntuPro.enrollment.noMasterKey',
                'No master key is configured. Please enter a custom Ubuntu Pro key below.')}
            </Alert>
          )}

          {(!useMasterKey || !masterKeyAvailable) && (
            <TextField
              label={t('ubuntuPro.enrollment.customKey', 'Ubuntu Pro Key')}
              type={showCustomKey ? 'text' : 'password'}
              value={customKey}
              onChange={(e) => setCustomKey(e.target.value)}
              fullWidth
              variant="outlined"
              helperText={t('ubuntuPro.enrollment.customKeyHelp',
                'Contract-based Ubuntu Pro key starting with "C"')}
              error={customKey.trim() !== '' && !validateCustomKey(customKey)}
              InputProps={{
                endAdornment: (
                  <InputAdornment position="end">
                    <IconButton
                      onClick={() => setShowCustomKey(!showCustomKey)}
                      edge="end"
                      aria-label={t('common.togglePasswordVisibility', 'Toggle password visibility')}
                    >
                      {showCustomKey ? <VisibilityOffIcon /> : <VisibilityIcon />}
                    </IconButton>
                  </InputAdornment>
                ),
              }}
            />
          )}

          {customKey.trim() !== '' && !validateCustomKey(customKey) && (
            <Alert severity="error">
              {t('ubuntuPro.validation.invalidKey',
                'Ubuntu Pro key must start with "C" and be at least 24 characters long')}
            </Alert>
          )}
        </Stack>
      </Box>
    </Stack>
  );

  const renderResults = () => (
    <Stack spacing={2}>
      <Typography variant="h6">
        {t('ubuntuPro.enrollment.results', 'Enrollment Results')}
      </Typography>

      {enrollmentResults.map((result, index) => (
        <Alert
          key={index}
          severity={result.success ? 'success' : 'error'}
        >
          <Typography variant="subtitle2">
            {result.hostname || `Host ${result.host_id}`}
          </Typography>
          <Typography variant="body2">
            {result.success ? result.message : result.error}
          </Typography>
        </Alert>
      ))}

      <Box sx={{ mt: 2 }}>
        <Typography variant="body2" color="text.secondary">
          {t('ubuntuPro.enrollment.resultsNote',
            'Please check the host details or agent logs for more information about the enrollment process.')}
        </Typography>
      </Box>
    </Stack>
  );

  return (
    <Dialog
      open={open}
      onClose={handleClose}
      maxWidth="md"
      fullWidth
      disableEscapeKeyDown={loading}
    >
      <DialogTitle>
        <Box display="flex" alignItems="center" gap={1}>
          <SecurityIcon />
          {t('ubuntuPro.enrollment.title', 'Ubuntu Pro Enrollment')}
        </Box>
      </DialogTitle>

      <DialogContent>
        {showResults ? renderResults() : renderEnrollmentForm()}
      </DialogContent>

      <DialogActions>
        {showResults ? (
          <Button onClick={handleClose} variant="contained">
            {t('common.close', 'Close')}
          </Button>
        ) : (
          <>
            <Button onClick={handleClose} disabled={loading}>
              {t('common.cancel', 'Cancel')}
            </Button>
            <Button
              onClick={handleEnroll}
              variant="contained"
              disabled={!isFormValid() || loading}
              startIcon={loading ? <CircularProgress size={20} /> : <SecurityIcon />}
            >
              {loading
                ? t('ubuntuPro.enrollment.enrolling', 'Enrolling...')
                : t('ubuntuPro.enrollment.enroll', 'Enroll Hosts')
              }
            </Button>
          </>
        )}
      </DialogActions>
    </Dialog>
  );
};

export default UbuntuProEnrollmentDialog;