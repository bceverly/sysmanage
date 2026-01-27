import React, { useState, useEffect, useCallback } from 'react';
import {
  Card,
  CardContent,
  CardHeader,
  Typography,
  Button,
  Grid,
  Chip,
  Box,
  Alert,
  CircularProgress,
  FormControl,
  FormControlLabel,
  InputLabel,
  Select,
  MenuItem,
  TextField,
  Switch,
  SelectChangeEvent
} from '@mui/material';
import {
  Analytics as AnalyticsIcon,
  CheckCircle as CheckCircleIcon,
  Warning as WarningIcon,
  Error as ErrorIcon,
  Refresh as RefreshIcon,
  Save as SaveIcon,
  Computer as ComputerIcon,
  Link as LinkIcon
} from '@mui/icons-material';
import { useTranslation } from 'react-i18next';
import axios from 'axios';
import axiosInstance from '../Services/api';
import { hasPermission, SecurityRoles } from '../Services/permissions';

interface GrafanaServer {
  id: string;
  fqdn: string;
  role: string;
  package_name: string;
  package_version?: string;
  is_active: boolean;
}

interface GrafanaSettings {
  enabled: boolean;
  use_managed_server: boolean;
  host_id?: string;
  manual_url?: string;
  api_key?: string;
}

interface GrafanaBuildInfo {
  version?: string;
  [key: string]: unknown;
}

interface GrafanaHealthStatus {
  healthy: boolean;
  version?: string;
  build_info?: GrafanaBuildInfo;
  error?: string;
}

const GrafanaIntegrationCard: React.FC = () => {
  const { t } = useTranslation();
  const [servers, setServers] = useState<GrafanaServer[]>([]);
  const [settings, setSettings] = useState<GrafanaSettings>({
    enabled: false,
    use_managed_server: true,
    host_id: undefined,
    manual_url: undefined,
    api_key: undefined
  });
  const [healthStatus, setHealthStatus] = useState<GrafanaHealthStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [checkingHealth, setCheckingHealth] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [canEnableGrafanaIntegration, setCanEnableGrafanaIntegration] = useState<boolean>(false);

  // Load initial data
  const loadData = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);

      const [serversData, settingsData] = await Promise.all([
        axiosInstance.get('/api/grafana/grafana-servers'),
        axiosInstance.get('/api/grafana/settings')
      ]);

      setServers(serversData.data.grafana_servers || []);
      setSettings(settingsData.data);
    } catch (err: unknown) {
      console.error('Error loading Grafana data:', err);
      const errorMessage = axios.isAxiosError(err)
        ? err.response?.data?.detail || 'Failed to load Grafana configuration'
        : 'Failed to load Grafana configuration';
      setError(errorMessage);
    } finally {
      setLoading(false);
    }
  }, []);

  // Check Grafana health
  const checkHealth = useCallback(async () => {
    if (!settings.enabled) return;

    try {
      setCheckingHealth(true);
      const response = await axiosInstance.get('/api/grafana/health');
      setHealthStatus(response.data);
    } catch (err: unknown) {
      // Only log non-400 errors to reduce console spam
      const errorResponse = axios.isAxiosError(err) ? err.response : undefined;
      if (errorResponse?.status !== 400) {
        console.error('Error checking Grafana health:', err);
      }
      setHealthStatus({
        healthy: false,
        error: errorResponse?.data?.detail || 'Health check failed'
      });
    } finally {
      setCheckingHealth(false);
    }
  }, [settings.enabled]);

  // Save settings
  const saveSettings = useCallback(async () => {
    try {
      setSaving(true);
      setError(null);

      await axiosInstance.post('/api/grafana/settings', settings);

      // Refresh health status if enabled
      if (settings.enabled) {
        await checkHealth();
      } else {
        setHealthStatus(null);
      }
    } catch (err: unknown) {
      console.error('Error saving Grafana settings:', err);
      const errorMessage = axios.isAxiosError(err)
        ? err.response?.data?.detail || 'Failed to save settings'
        : 'Failed to save settings';
      setError(errorMessage);
    } finally {
      setSaving(false);
    }
  }, [settings, checkHealth]);

  // Check permissions
  useEffect(() => {
    const checkPermission = async () => {
      const enableGrafana = await hasPermission(SecurityRoles.ENABLE_GRAFANA_INTEGRATION);
      setCanEnableGrafanaIntegration(enableGrafana);
    };
    checkPermission();
  }, []);

  // Load data on mount
  useEffect(() => {
    loadData();
  }, [loadData]);

  // Check health when settings change and enabled, but only after initial load
  useEffect(() => {
    if (settings.enabled && !loading && (settings.host_id || settings.manual_url)) {
      const timer = setTimeout(() => {
        checkHealth();
      }, 2000); // Delay to avoid rapid calls
      return () => clearTimeout(timer);
    }
    return undefined;
  }, [settings.enabled, settings.host_id, settings.manual_url, loading, checkHealth]);

  const handleEnabledChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    setSettings(prev => ({ ...prev, enabled: event.target.checked }));
  };

  const handleManagedServerChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    const useManagedServer = event.target.checked;
    setSettings(prev => ({
      ...prev,
      use_managed_server: useManagedServer,
      host_id: useManagedServer ? prev.host_id : undefined,
      manual_url: useManagedServer ? undefined : prev.manual_url
    }));
  };

  const handleHostChange = (event: SelectChangeEvent) => {
    setSettings(prev => ({ ...prev, host_id: event.target.value }));
  };

  const handleManualUrlChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    setSettings(prev => ({ ...prev, manual_url: event.target.value }));
  };

  const handleApiKeyChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    setSettings(prev => ({ ...prev, api_key: event.target.value }));
  };

  const getStatusColor = () => {
    if (!settings.enabled) return 'default';
    if (checkingHealth) return 'default';
    if (!healthStatus) return 'warning';
    return healthStatus.healthy ? 'success' : 'error';
  };

  const getStatusIcon = () => {
    if (!settings.enabled) return <AnalyticsIcon />;
    if (checkingHealth) return <CircularProgress size={20} />;
    if (!healthStatus) return <WarningIcon />;
    return healthStatus.healthy ? <CheckCircleIcon /> : <ErrorIcon />;
  };

  const getStatusText = () => {
    if (!settings.enabled) return t('grafana.status.disabled', 'Disabled');
    if (checkingHealth) return t('grafana.status.checking', 'Checking...');
    if (!healthStatus) return t('grafana.status.unknown', 'Unknown');
    return healthStatus.healthy
      ? t('grafana.status.healthy', 'Healthy')
      : t('grafana.status.unhealthy', 'Unhealthy');
  };

  const selectedServer = servers.find(server => server.id === settings.host_id);

  if (loading) {
    return (
      <Card>
        <CardHeader
          avatar={<AnalyticsIcon />}
          title={t('grafana.title', 'Grafana Integration')}
        />
        <CardContent>
          <Box display="flex" justifyContent="center" py={2}>
            <CircularProgress />
          </Box>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader
        avatar={<AnalyticsIcon />}
        title={t('grafana.title', 'Grafana Integration')}
        action={
          <Button
            onClick={loadData}
            disabled={loading}
            startIcon={<RefreshIcon />}
            size="small"
          >
            {t('common.refresh', 'Refresh')}
          </Button>
        }
      />
      <CardContent>
        {error && (
          <Alert severity="error" sx={{ mb: 2 }}>
            {error}
          </Alert>
        )}

        <Grid container spacing={2}>
          {/* Status */}
          <Grid size={12}>
            <Box display="flex" alignItems="center" gap={1} mb={2}>
              <Typography variant="subtitle2">
                {t('grafana.status.label', 'Status')}:
              </Typography>
              <Chip
                icon={getStatusIcon()}
                label={getStatusText()}
                color={getStatusColor()}
                size="small"
              />
              {healthStatus?.version && (
                <Chip
                  label={`v${healthStatus.version}`}
                  size="small"
                  variant="outlined"
                />
              )}
            </Box>
          </Grid>

          {/* Enable/Disable */}
          <Grid size={12}>
            <FormControlLabel
              control={
                <Switch
                  checked={settings.enabled}
                  onChange={handleEnabledChange}
                  disabled={!canEnableGrafanaIntegration}
                />
              }
              label={t('grafana.enabled.label', 'Enable Grafana Integration')}
            />
          </Grid>

          {settings.enabled && (
            <>
              {/* Server Type Selection */}
              <Grid size={12}>
                <FormControlLabel
                  control={
                    <Switch
                      checked={settings.use_managed_server}
                      onChange={handleManagedServerChange}
                    />
                  }
                  label={t('grafana.useManagedServer.label', 'Use Managed Server')}
                />
              </Grid>

              {settings.use_managed_server ? (
                /* Managed Server Dropdown */
                <Grid size={12}>
                  <FormControl fullWidth>
                    <InputLabel>{t('grafana.selectServer.label', 'Select Grafana Server')}</InputLabel>
                    <Select
                      value={servers.some(s => s.id === settings.host_id) ? settings.host_id : ''}
                      onChange={handleHostChange}
                      label={t('grafana.selectServer.label', 'Select Grafana Server')}
                      startAdornment={<ComputerIcon sx={{ mr: 1, color: 'action.active' }} />}
                    >
                      {servers.length === 0 ? (
                        <MenuItem disabled>
                          {t('grafana.noServers', 'No Grafana servers found')}
                        </MenuItem>
                      ) : (
                        servers.map(server => (
                          <MenuItem key={server.id} value={server.id}>
                            <Box>
                              <Typography variant="body2">
                                {server.fqdn}
                              </Typography>
                              <Typography variant="caption" color="textSecondary">
                                {server.package_version && `v${server.package_version}`}
                                {server.is_active ? (
                                  <Chip label={t('common.active', 'Active')} size="small" color="success" sx={{ ml: 1 }} />
                                ) : (
                                  <Chip label={t('common.inactive', 'Inactive')} size="small" color="warning" sx={{ ml: 1 }} />
                                )}
                              </Typography>
                            </Box>
                          </MenuItem>
                        ))
                      )}
                    </Select>
                  </FormControl>
                  {selectedServer && (
                    <Typography variant="caption" color="textSecondary" sx={{ mt: 1, display: 'block' }}>
                      {t('grafana.serverUrl.label', 'URL')}: http://{selectedServer.fqdn}:3000
                    </Typography>
                  )}
                </Grid>
              ) : (
                /* Manual URL Input */
                <Grid size={12}>
                  <TextField
                    fullWidth
                    label={t('grafana.manualUrl.label', 'Grafana URL')}
                    value={settings.manual_url || ''}
                    onChange={handleManualUrlChange}
                    placeholder="https://grafana.example.com"
                    slotProps={{
                      input: {
                        startAdornment: <LinkIcon sx={{ mr: 1, color: 'action.active' }} />,
                      },
                    }}
                    helperText={t('grafana.manualUrl.help', 'Enter the full URL to your Grafana instance')}
                  />
                </Grid>
              )}

              {/* API Key (Optional) */}
              <Grid size={12}>
                <TextField
                  fullWidth
                  label={t('grafana.apiKey.label', 'API Key (Optional)')}
                  value={settings.api_key || ''}
                  onChange={handleApiKeyChange}
                  type="password"
                  helperText={t('grafana.apiKey.help', 'Optional API key with Editor role permissions for enhanced features and version detection')}
                />
              </Grid>

              {/* Health Status Details */}
              {healthStatus && !healthStatus.healthy && healthStatus.error && (
                <Grid size={12}>
                  <Alert severity="error">
                    <Typography variant="body2">
                      {t('grafana.healthError.label', 'Health Check Error')}: {healthStatus.error}
                    </Typography>
                  </Alert>
                </Grid>
              )}
            </>
          )}

          {/* Save Button */}
          <Grid size={12}>
            <Box display="flex" justifyContent="flex-end" gap={1}>
              <Button
                onClick={checkHealth}
                disabled={!settings.enabled || checkingHealth}
                startIcon={checkingHealth ? <CircularProgress size={16} /> : <RefreshIcon />}
              >
                {t('grafana.checkHealth', 'Check Health')}
              </Button>
              {canEnableGrafanaIntegration && (
                <Button
                  onClick={saveSettings}
                  disabled={saving}
                  startIcon={saving ? <CircularProgress size={16} /> : <SaveIcon />}
                  variant="contained"
                >
                  {t('common.save', 'Save')}
                </Button>
              )}
            </Box>
          </Grid>
        </Grid>
      </CardContent>
    </Card>
  );
};

export default GrafanaIntegrationCard;