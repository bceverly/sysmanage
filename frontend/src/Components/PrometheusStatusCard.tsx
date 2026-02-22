import React, { useState, useEffect, useCallback } from 'react';
import { formatUTCTimestamp } from '../utils/dateUtils';
import {
  Card,
  CardContent,
  Typography,
  Box,
  Chip,
  Button,
  CircularProgress,
  Alert,
  Stack,
  Divider,
  List,
  ListItem,
  ListItemText,
  Link,
} from '@mui/material';
import {
  CheckCircle as CheckCircleIcon,
  Error as ErrorIcon,
  Refresh as RefreshIcon,
  Storage as StorageIcon,
  OpenInNew as OpenInNewIcon,
} from '@mui/icons-material';
import { useTranslation } from 'react-i18next';
import axiosInstance from '../Services/api';

interface PrometheusStatus {
  running: boolean;
  version?: string;
  url?: string;
  scrape_interval?: string;
  retention_time?: string;
  storage_size?: string;
  targets_count?: number;
  healthy_targets?: number;
  metrics_count?: number;
  last_scrape?: string;
}

const PrometheusStatusCard: React.FC = () => {
  const { t } = useTranslation();
  const [status, setStatus] = useState<PrometheusStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchStatus = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const response = await axiosInstance.get('/api/telemetry/prometheus/status');
      setStatus(response.data);
    } catch (err: unknown) {
      console.error('Error fetching Prometheus status:', err);
      const errorMessage = err && typeof err === 'object' && 'response' in err ?
        (err as {response?: {data?: {detail?: string}}}).response?.data?.detail || 'Failed to fetch Prometheus status' :
        'Failed to fetch Prometheus status';
      setError(errorMessage);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchStatus();
  }, [fetchStatus]);

  if (loading) {
    return (
      <Card>
        <CardContent>
          <Box display="flex" justifyContent="center" alignItems="center" py={3}>
            <CircularProgress />
          </Box>
        </CardContent>
      </Card>
    );
  }

  const isRunning = status?.running ?? false;

  return (
    <Card>
      <CardContent>
        <Box display="flex" justifyContent="space-between" alignItems="center" mb={2}>
          <Box display="flex" alignItems="center" gap={1}>
            <StorageIcon color={isRunning ? 'success' : 'disabled'} />
            <Typography variant="h6">
              {t('telemetry.prometheus.title', 'Prometheus Status')}
            </Typography>
          </Box>
          <Button
            startIcon={<RefreshIcon />}
            onClick={fetchStatus}
            disabled={loading}
            size="small"
          >
            {t('common.refresh', 'Refresh')}
          </Button>
        </Box>

        {error && (
          <Alert severity="error" sx={{ mb: 2 }}>
            {error}
          </Alert>
        )}

        <Stack spacing={2}>
          <Box display="flex" alignItems="center" gap={1}>
            <Typography variant="body2" color="text.secondary">
              {t('telemetry.prometheus.status', 'Status')}:
            </Typography>
            <Chip
              icon={isRunning ? <CheckCircleIcon /> : <ErrorIcon />}
              label={isRunning ? t('common.running', 'Running') : t('common.stopped', 'Stopped')}
              color={isRunning ? 'success' : 'default'}
              size="small"
            />
          </Box>

          {status && isRunning && (
            <>
              <Divider />

              <Box>
                <Typography variant="subtitle2" gutterBottom>
                  {t('telemetry.prometheus.information', 'Information')}
                </Typography>
                <List dense>
                  {status.version && (
                    <ListItem>
                      <ListItemText
                        primary={t('telemetry.prometheus.version', 'Version')}
                        secondary={status.version}
                      />
                    </ListItem>
                  )}
                  {status.url && (
                    <ListItem>
                      <ListItemText
                        primary={t('telemetry.prometheus.url', 'URL')}
                        secondary={
                          <Link href={status.url} target="_blank" rel="noopener noreferrer">
                            {status.url} <OpenInNewIcon fontSize="small" sx={{ verticalAlign: 'middle' }} />
                          </Link>
                        }
                      />
                    </ListItem>
                  )}
                  {status.scrape_interval && (
                    <ListItem>
                      <ListItemText
                        primary={t('telemetry.prometheus.scrapeInterval', 'Scrape Interval')}
                        secondary={status.scrape_interval}
                      />
                    </ListItem>
                  )}
                  {status.retention_time && (
                    <ListItem>
                      <ListItemText
                        primary={t('telemetry.prometheus.retentionTime', 'Retention Time')}
                        secondary={status.retention_time}
                      />
                    </ListItem>
                  )}
                </List>
              </Box>

              {(status.targets_count !== undefined || status.metrics_count !== undefined) && (
                <>
                  <Divider />
                  <Box>
                    <Typography variant="subtitle2" gutterBottom>
                      {t('telemetry.prometheus.statistics', 'Statistics')}
                    </Typography>
                    <Stack direction="row" spacing={2} flexWrap="wrap">
                      {status.targets_count !== undefined && (
                        <Box>
                          <Typography variant="body2" color="text.secondary">
                            {t('telemetry.prometheus.targets', 'Targets')}
                          </Typography>
                          <Typography variant="h6">
                            {status.healthy_targets ?? 0} / {status.targets_count}
                          </Typography>
                        </Box>
                      )}
                      {status.metrics_count !== undefined && (
                        <Box>
                          <Typography variant="body2" color="text.secondary">
                            {t('telemetry.prometheus.metricsCount', 'Metrics')}
                          </Typography>
                          <Typography variant="h6">{status.metrics_count}</Typography>
                        </Box>
                      )}
                      {status.storage_size && (
                        <Box>
                          <Typography variant="body2" color="text.secondary">
                            {t('telemetry.prometheus.storageSize', 'Storage Size')}
                          </Typography>
                          <Typography variant="h6">{status.storage_size}</Typography>
                        </Box>
                      )}
                    </Stack>
                  </Box>
                </>
              )}

              {status.last_scrape && (
                <>
                  <Divider />
                  <Box>
                    <Typography variant="body2" color="text.secondary">
                      {t('telemetry.prometheus.lastScrape', 'Last Scrape')}:{' '}
                      {formatUTCTimestamp(status.last_scrape)}
                    </Typography>
                  </Box>
                </>
              )}

              <Divider />
              <Alert severity="info" variant="outlined">
                <Typography variant="body2">
                  {t('telemetry.prometheus.manageHint', 'Prometheus is managed by the telemetry stack. Use "make start-telemetry" to start or "make stop-telemetry" to stop.')}
                </Typography>
              </Alert>
            </>
          )}

          {!isRunning && (
            <Alert severity="warning" variant="outlined">
              <Typography variant="body2">
                {t('telemetry.prometheus.notRunningMessage', 'Prometheus is not running. Start the telemetry stack with "make start-telemetry" or "make start".')}
              </Typography>
            </Alert>
          )}
        </Stack>
      </CardContent>
    </Card>
  );
};

export default PrometheusStatusCard;