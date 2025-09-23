import React, { useState, useEffect } from 'react';
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
  List,
  ListItem,
  ListItemText,
  Collapse
} from '@mui/material';
import {
  Security as SecurityIcon,
  CheckCircle as CheckCircleIcon,
  Warning as WarningIcon,
  Error as ErrorIcon,
  PlayArrow as PlayIcon,
  Stop as StopIcon,
  Refresh as RefreshIcon,
  ExpandMore as ExpandMoreIcon,
  ExpandLess as ExpandLessIcon
} from '@mui/icons-material';
import { useTranslation } from 'react-i18next';
import { openBAOService, OpenBAOStatus, OpenBAOConfig, OpenBAOOperationResult, OpenBAOHealth } from '../Services/openBAOService';

const OpenBAOStatusCard: React.FC = () => {
  const { t } = useTranslation();
  const [status, setStatus] = useState<OpenBAOStatus | null>(null);
  const [config, setConfig] = useState<OpenBAOConfig | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [operationLoading, setOperationLoading] = useState(false);
  const [operationResult, setOperationResult] = useState<OpenBAOOperationResult | null>(null);
  const [showLogs, setShowLogs] = useState(false);

  // Load OpenBAO status and config
  const loadData = async () => {
    try {
      setLoading(true);
      setError(null);

      const [statusData, configData] = await Promise.all([
        openBAOService.getStatus(),
        openBAOService.getConfig()
      ]);

      setStatus(statusData);
      setConfig(configData);
    } catch (err) {
      console.error('Failed to load OpenBAO data:', err);
      setError(t('openbao.loadError', 'Failed to load OpenBAO status'));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();

    // Auto-refresh every 30 seconds when component is active
    const interval = setInterval(loadData, 30000);
    return () => clearInterval(interval);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleStart = async () => {
    try {
      setOperationLoading(true);
      setOperationResult(null);

      const result = await openBAOService.start();
      setOperationResult(result);

      // Update status immediately
      setStatus(result.status);

      // Auto-clear result after 5 seconds
      setTimeout(() => {
        setOperationResult(null);
      }, 5000);
    } catch (err) {
      console.error('Failed to start OpenBAO:', err);
      setOperationResult({
        success: false,
        message: t('openbao.startError', 'Failed to start OpenBAO'),
        status: status!
      });
    } finally {
      setOperationLoading(false);
    }
  };

  const handleStop = async () => {
    try {
      setOperationLoading(true);
      setOperationResult(null);

      const result = await openBAOService.stop();
      setOperationResult(result);

      // Update status immediately
      setStatus(result.status);

      // Auto-clear result after 5 seconds
      setTimeout(() => {
        setOperationResult(null);
      }, 5000);
    } catch (err) {
      console.error('Failed to stop OpenBAO:', err);
      setOperationResult({
        success: false,
        message: t('openbao.stopError', 'Failed to stop OpenBAO'),
        status: status!
      });
    } finally {
      setOperationLoading(false);
    }
  };

  const handleRefresh = () => {
    loadData();
  };

  const getStatusIcon = () => {
    if (!status) return <WarningIcon color="disabled" />;

    if (!config?.enabled) {
      return <WarningIcon color="warning" />;
    }

    if (!status.running) {
      return <ErrorIcon color="error" />;
    }

    return <CheckCircleIcon color="success" />;
  };

  const getStatusText = () => {
    if (!status) return t('openbao.unknown', 'Unknown');

    if (!config?.enabled) {
      return t('openbao.disabled', 'Disabled');
    }

    if (!status.running) {
      return t('openbao.stopped', 'Stopped');
    }

    return t('openbao.running', 'Running');
  };

  const getStatusColor = (): 'default' | 'success' | 'warning' | 'error' => {
    if (!status) return 'default';

    if (!config?.enabled) return 'warning';
    if (!status.running) return 'error';

    return 'success';
  };

  const formatHealthInfo = (health: OpenBAOHealth | null) => {
    if (!health) return null;

    if (health.error) {
      return (
        <Alert severity="warning" sx={{ mt: 1 }}>
          {health.error}
        </Alert>
      );
    }

    return (
      <Box sx={{ mt: 1 }}>
        <Typography variant="body2" color="text.secondary" gutterBottom>
          {t('openbao.serverHealth', 'Server Health')}:
        </Typography>
        <Grid container spacing={1}>
          {Object.entries(health).map(([key, value]) => (
            <Grid item xs={12} sm={6} key={key}>
              <Typography variant="caption" color="text.secondary">
                {key}:
              </Typography>
              <Typography variant="body2" sx={{ ml: 1 }}>
                {String(value)}
              </Typography>
            </Grid>
          ))}
        </Grid>
      </Box>
    );
  };

  if (loading) {
    return (
      <Card>
        <CardHeader
          avatar={<SecurityIcon />}
          title={t('openbao.title', 'OpenBAO Vault')}
          subheader={t('openbao.subtitle', 'Secrets management and SSH key storage')}
        />
        <CardContent>
          <Box display="flex" justifyContent="center" p={2}>
            <CircularProgress />
          </Box>
        </CardContent>
      </Card>
    );
  }

  if (error) {
    return (
      <Card>
        <CardHeader
          avatar={<SecurityIcon />}
          title={t('openbao.title', 'OpenBAO Vault')}
          subheader={t('openbao.subtitle', 'Secrets management and SSH key storage')}
        />
        <CardContent>
          <Alert severity="error">{error}</Alert>
          <Box mt={2}>
            <Button variant="outlined" onClick={handleRefresh} startIcon={<RefreshIcon />}>
              {t('common.retry', 'Retry')}
            </Button>
          </Box>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader
        avatar={<SecurityIcon />}
        title={t('openbao.title', 'OpenBAO Vault')}
        subheader={t('openbao.subtitle', 'Secrets management and SSH key storage')}
        action={
          <Box display="flex" alignItems="center" gap={1}>
            {getStatusIcon()}
            <Chip
              label={getStatusText()}
              color={getStatusColor()}
              size="small"
            />
          </Box>
        }
      />
      <CardContent>
        {status && config && (
          <Grid container spacing={2}>
            <Grid item xs={12} sm={6}>
              <Typography variant="body2" color="text.secondary" gutterBottom>
                {t('openbao.serverUrl', 'Server URL')}
              </Typography>
              <Typography variant="body1">
                {config.url}
              </Typography>
            </Grid>

            <Grid item xs={12} sm={6}>
              <Typography variant="body2" color="text.secondary" gutterBottom>
                {t('openbao.processId', 'Process ID')}
              </Typography>
              <Typography variant="body1">
                {status.pid || t('common.na', 'N/A')}
              </Typography>
            </Grid>

            <Grid item xs={12} sm={6}>
              <Typography variant="body2" color="text.secondary" gutterBottom>
                {t('openbao.mountPath', 'Mount Path')}
              </Typography>
              <Typography variant="body1">
                {config.mount_path}
              </Typography>
            </Grid>

            <Grid item xs={12} sm={6}>
              <Typography variant="body2" color="text.secondary" gutterBottom>
                {t('openbao.devMode', 'Development Mode')}
              </Typography>
              <Typography variant="body1">
                {config.dev_mode ? t('common.yes', 'Yes') : t('common.no', 'No')}
              </Typography>
            </Grid>

            {/* Health Information */}
            {status.running && status.health && (
              <Grid item xs={12}>
                {formatHealthInfo(status.health)}
              </Grid>
            )}

            {/* Operation Result */}
            {operationResult && (
              <Grid item xs={12}>
                <Alert severity={operationResult.success ? 'success' : 'error'} sx={{ mt: 1 }}>
                  {operationResult.message}
                </Alert>
              </Grid>
            )}

            {/* Action Buttons */}
            <Grid item xs={12}>
              <Box mt={2} display="flex" gap={1} flexWrap="wrap">
                {status.running ? (
                  <Button
                    variant="outlined"
                    color="error"
                    onClick={handleStop}
                    disabled={operationLoading || !config.enabled}
                    startIcon={operationLoading ? <CircularProgress size={16} /> : <StopIcon />}
                  >
                    {operationLoading ? t('openbao.stopping', 'Stopping...') : t('openbao.stop', 'Stop')}
                  </Button>
                ) : (
                  <Button
                    variant="contained"
                    color="success"
                    onClick={handleStart}
                    disabled={operationLoading || !config.enabled}
                    startIcon={operationLoading ? <CircularProgress size={16} /> : <PlayIcon />}
                  >
                    {operationLoading ? t('openbao.starting', 'Starting...') : t('openbao.start', 'Start')}
                  </Button>
                )}

                <Button
                  variant="outlined"
                  onClick={handleRefresh}
                  disabled={operationLoading}
                  startIcon={<RefreshIcon />}
                >
                  {t('common.refresh', 'Refresh')}
                </Button>

                {status.recent_logs && status.recent_logs.length > 0 && (
                  <Button
                    variant="outlined"
                    onClick={() => setShowLogs(!showLogs)}
                    startIcon={showLogs ? <ExpandLessIcon /> : <ExpandMoreIcon />}
                  >
                    {showLogs ? t('openbao.hideLogs', 'Hide Logs') : t('openbao.showLogs', 'Show Logs')}
                  </Button>
                )}
              </Box>

              {!config.enabled && (
                <Typography variant="caption" color="text.secondary" sx={{ mt: 1, display: 'block' }}>
                  {t('openbao.disabledNote', 'Enable OpenBAO in sysmanage.yaml to use vault features')}
                </Typography>
              )}
            </Grid>

            {/* Recent Logs */}
            <Grid item xs={12}>
              <Collapse in={showLogs}>
                <Box sx={{ mt: 2 }}>
                  <Typography variant="body2" color="text.secondary" gutterBottom>
                    {t('openbao.recentLogs', 'Recent Logs')}:
                  </Typography>
                  <Box
                    sx={{
                      backgroundColor: '#2d2d2d',
                      color: '#ffffff',
                      p: 2,
                      borderRadius: 1,
                      overflow: 'auto',
                      fontSize: '0.75rem',
                      fontFamily: 'monospace',
                      maxHeight: 200
                    }}
                  >
                    {status.recent_logs && status.recent_logs.length > 0 ? (
                      <List dense>
                        {status.recent_logs.map((log, index) => (
                          <ListItem key={index} disablePadding>
                            <ListItemText
                              primary={log}
                              primaryTypographyProps={{
                                fontSize: '0.75rem',
                                fontFamily: 'monospace',
                                color: '#ffffff'
                              }}
                            />
                          </ListItem>
                        ))}
                      </List>
                    ) : (
                      <Typography variant="body2" sx={{ color: '#ffffff' }}>
                        {t('openbao.noLogs', 'No recent logs available')}
                      </Typography>
                    )}
                  </Box>
                </Box>
              </Collapse>
            </Grid>
          </Grid>
        )}
      </CardContent>
    </Card>
  );
};

export default OpenBAOStatusCard;