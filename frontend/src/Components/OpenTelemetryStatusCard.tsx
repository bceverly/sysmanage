import React, { useState, useEffect, useCallback } from 'react';
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
} from '@mui/material';
import {
  CheckCircle as CheckCircleIcon,
  Error as ErrorIcon,
  Refresh as RefreshIcon,
  TrendingUp as TrendingUpIcon,
} from '@mui/icons-material';
import { useTranslation } from 'react-i18next';
import axiosInstance from '../Services/api';

interface OpenTelemetryStatus {
  enabled: boolean;
  collector_url?: string;
  prometheus_port?: number;
  instrumentation?: {
    fastapi: boolean;
    sqlalchemy: boolean;
    requests: boolean;
    logging: boolean;
  };
  metrics_count?: number;
  traces_count?: number;
}

const OpenTelemetryStatusCard: React.FC = () => {
  const { t } = useTranslation();
  const [status, setStatus] = useState<OpenTelemetryStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchStatus = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const response = await axiosInstance.get('/api/telemetry/opentelemetry/status');
      setStatus(response.data);
    } catch (err: unknown) {
      console.error('Error fetching OpenTelemetry status:', err);
      const errorMessage = err && typeof err === 'object' && 'response' in err ?
        (err as {response?: {data?: {detail?: string}}}).response?.data?.detail || 'Failed to fetch OpenTelemetry status' :
        'Failed to fetch OpenTelemetry status';
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

  const isEnabled = status?.enabled ?? false;

  return (
    <Card>
      <CardContent>
        <Box display="flex" justifyContent="space-between" alignItems="center" mb={2}>
          <Box display="flex" alignItems="center" gap={1}>
            <TrendingUpIcon color={isEnabled ? 'success' : 'disabled'} />
            <Typography variant="h6">
              {t('telemetry.opentelemetry.title', 'OpenTelemetry Status')}
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
              {t('telemetry.opentelemetry.status', 'Status')}:
            </Typography>
            <Chip
              icon={isEnabled ? <CheckCircleIcon /> : <ErrorIcon />}
              label={isEnabled ? t('common.enabled', 'Enabled') : t('common.disabled', 'Disabled')}
              color={isEnabled ? 'success' : 'default'}
              size="small"
            />
          </Box>

          {status && isEnabled && (
            <>
              <Divider />

              <Box>
                <Typography variant="subtitle2" gutterBottom>
                  {t('telemetry.opentelemetry.configuration', 'Configuration')}
                </Typography>
                <List dense>
                  {status.collector_url && (
                    <ListItem>
                      <ListItemText
                        primary={t('telemetry.opentelemetry.collectorUrl', 'Collector URL')}
                        secondary={status.collector_url}
                      />
                    </ListItem>
                  )}
                  {status.prometheus_port && (
                    <ListItem>
                      <ListItemText
                        primary={t('telemetry.opentelemetry.prometheusPort', 'Prometheus Port')}
                        secondary={status.prometheus_port}
                      />
                    </ListItem>
                  )}
                </List>
              </Box>

              {status.instrumentation && (
                <>
                  <Divider />
                  <Box>
                    <Typography variant="subtitle2" gutterBottom>
                      {t('telemetry.opentelemetry.instrumentation', 'Instrumentation')}
                    </Typography>
                    <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
                      {status.instrumentation.fastapi && (
                        <Chip label={t('telemetry.instrumentation.fastapi', 'FastAPI')} size="small" color="primary" />
                      )}
                      {status.instrumentation.sqlalchemy && (
                        <Chip label={t('telemetry.instrumentation.sqlalchemy', 'SQLAlchemy')} size="small" color="primary" />
                      )}
                      {status.instrumentation.requests && (
                        <Chip label={t('telemetry.instrumentation.requests', 'Requests')} size="small" color="primary" />
                      )}
                      {status.instrumentation.logging && (
                        <Chip label={t('telemetry.instrumentation.logging', 'Logging')} size="small" color="primary" />
                      )}
                    </Stack>
                  </Box>
                </>
              )}

              {(status.metrics_count !== undefined || status.traces_count !== undefined) && (
                <>
                  <Divider />
                  <Box>
                    <Typography variant="subtitle2" gutterBottom>
                      {t('telemetry.opentelemetry.statistics', 'Statistics')}
                    </Typography>
                    <Stack direction="row" spacing={2}>
                      {status.metrics_count !== undefined && (
                        <Box>
                          <Typography variant="body2" color="text.secondary">
                            {t('telemetry.opentelemetry.metricsCount', 'Metrics')}
                          </Typography>
                          <Typography variant="h6">{status.metrics_count}</Typography>
                        </Box>
                      )}
                      {status.traces_count !== undefined && (
                        <Box>
                          <Typography variant="body2" color="text.secondary">
                            {t('telemetry.opentelemetry.tracesCount', 'Traces')}
                          </Typography>
                          <Typography variant="h6">{status.traces_count}</Typography>
                        </Box>
                      )}
                    </Stack>
                  </Box>
                </>
              )}

              <Divider />
              <Alert severity="info" variant="outlined">
                <Typography variant="body2">
                  {t('telemetry.opentelemetry.enableHint', 'To enable OpenTelemetry, set OTEL_ENABLED=true environment variable and restart the server.')}
                </Typography>
              </Alert>
            </>
          )}

          {!isEnabled && (
            <Alert severity="info" variant="outlined">
              <Typography variant="body2">
                {t('telemetry.opentelemetry.disabledMessage', 'OpenTelemetry instrumentation is currently disabled. Set OTEL_ENABLED=true to enable distributed tracing and metrics collection.')}
              </Typography>
            </Alert>
          )}
        </Stack>
      </CardContent>
    </Card>
  );
};

export default OpenTelemetryStatusCard;