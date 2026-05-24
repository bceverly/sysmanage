import React, { useCallback, useEffect, useState } from 'react';
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  CardHeader,
  Chip,
  CircularProgress,
  IconButton,
  Snackbar,
  Stack,
  Tooltip,
  Typography,
} from '@mui/material';
import {
  DataGrid,
  GridColDef,
  GridRenderCellParams,
} from '@mui/x-data-grid';
import {
  Build as BuildIcon,
  Delete as DeleteIcon,
  Download as DownloadIcon,
  Refresh as RefreshIcon,
} from '@mui/icons-material';
import { useTranslation } from 'react-i18next';

import axiosInstance from '../Services/api';
import { formatUTCTimestamp } from '../utils/dateUtils';

type BundleStatus = 'queued' | 'building' | 'ready' | 'failed';

interface Bundle {
  id: string;
  product: 'server' | 'agent';
  status: BundleStatus;
  created_at: string | null;
  started_at: string | null;
  completed_at: string | null;
  size_bytes: number | null;
  error_message: string | null;
}

const statusColor = (
  s: BundleStatus,
): 'default' | 'info' | 'warning' | 'success' | 'error' => {
  switch (s) {
    case 'queued':
      return 'default';
    case 'building':
      return 'info';
    case 'ready':
      return 'success';
    case 'failed':
      return 'error';
    default:
      return 'default';
  }
};

const formatBytes = (n: number | null): string => {
  if (n === null || n === undefined) return '—';
  const units = ['B', 'KB', 'MB', 'GB'];
  let v = n;
  let u = 0;
  while (v >= 1024 && u < units.length - 1) {
    v /= 1024;
    u += 1;
  }
  return `${v.toFixed(u === 0 ? 0 : 1)} ${units[u]}`;
};

const AirGapBundlesSettings: React.FC = () => {
  const { t } = useTranslation();

  const [bundles, setBundles] = useState<Bundle[]>([]);
  const [loading, setLoading] = useState(true);
  const [building, setBuilding] = useState<'server' | 'agent' | null>(null);

  const [snackbarOpen, setSnackbarOpen] = useState(false);
  const [snackbarMessage, setSnackbarMessage] = useState('');
  const [snackbarSeverity, setSnackbarSeverity] = useState<'success' | 'error'>(
    'success',
  );

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
      const r = await axiosInstance.get<Bundle[]>('/api/airgap-bundles');
      setBundles(r.data);
    } catch (e) {
      console.error(e);
      showError(t('airgapBundles.loadError', 'Failed to load bundles'));
    } finally {
      setLoading(false);
    }
  }, [t]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  // Auto-poll while any bundle is in-flight, so the status chip ticks
  // from "queued" -> "building" -> "ready"/"failed" without manual refresh.
  useEffect(() => {
    const inFlight = bundles.some(
      (b) => b.status === 'queued' || b.status === 'building',
    );
    if (!inFlight) return;
    const id = globalThis.setInterval(() => refresh(), 5000);
    return () => globalThis.clearInterval(id);
  }, [bundles, refresh]);

  const handleBuild = async (product: 'server' | 'agent') => {
    setBuilding(product);
    try {
      await axiosInstance.post('/api/airgap-bundles', { product });
      showSuccess(
        t('airgapBundles.queued', 'Bundle build queued — refreshing list'),
      );
      await refresh();
    } catch (e: unknown) {
      const detail = (e as { response?: { data?: { detail?: string } } })
        ?.response?.data?.detail;
      showError(detail || t('airgapBundles.buildError', 'Failed to queue build'));
    } finally {
      setBuilding(null);
    }
  };

  const handleDelete = async (bundle: Bundle) => {
    if (
      !globalThis.confirm(
        t(
          'airgapBundles.confirmDelete',
          'Delete this bundle and its ISO file?',
        ),
      )
    ) {
      return;
    }
    try {
      await axiosInstance.delete(`/api/airgap-bundles/${bundle.id}`);
      showSuccess(t('airgapBundles.deleted', 'Bundle deleted'));
      await refresh();
    } catch (e: unknown) {
      const detail = (e as { response?: { data?: { detail?: string } } })
        ?.response?.data?.detail;
      showError(
        detail || t('airgapBundles.deleteError', 'Failed to delete bundle'),
      );
    }
  };

  const handleDownload = (bundle: Bundle) => {
    // Use a plain anchor click so the browser handles the streaming
    // response naturally (a single large file).
    const url = `/api/airgap-bundles/${bundle.id}/download`;
    const a = document.createElement('a');
    a.href = url;
    a.download = '';
    document.body.appendChild(a);
    a.click();
    a.remove();
  };

  const columns: GridColDef[] = [
    {
      field: 'product',
      headerName: t('airgapBundles.product', 'Product'),
      width: 110,
      renderCell: (p: GridRenderCellParams<Bundle>) => (
        <Chip
          size="small"
          label={p.row.product}
          color={p.row.product === 'server' ? 'primary' : 'secondary'}
        />
      ),
    },
    {
      field: 'status',
      headerName: t('airgapBundles.status', 'Status'),
      width: 130,
      renderCell: (p: GridRenderCellParams<Bundle>) => (
        <Chip
          size="small"
          label={p.row.status}
          color={statusColor(p.row.status)}
        />
      ),
    },
    {
      field: 'created_at',
      headerName: t('airgapBundles.createdAt', 'Created'),
      width: 180,
      valueGetter: (_v, row) =>
        row.created_at ? formatUTCTimestamp(row.created_at, '—') : '—',
    },
    {
      field: 'completed_at',
      headerName: t('airgapBundles.completedAt', 'Completed'),
      width: 180,
      valueGetter: (_v, row) =>
        row.completed_at ? formatUTCTimestamp(row.completed_at, '—') : '—',
    },
    {
      field: 'size_bytes',
      headerName: t('airgapBundles.size', 'Size'),
      width: 110,
      valueGetter: (_v, row) => formatBytes(row.size_bytes),
    },
    {
      field: 'actions',
      headerName: t('common.actions', 'Actions'),
      width: 140,
      sortable: false,
      renderCell: (p: GridRenderCellParams<Bundle>) => (
        <Stack direction="row" spacing={0.5}>
          {p.row.status === 'ready' && (
            <Tooltip title={t('airgapBundles.download', 'Download ISO')}>
              <IconButton size="small" onClick={() => handleDownload(p.row)}>
                <DownloadIcon fontSize="small" />
              </IconButton>
            </Tooltip>
          )}
          <Tooltip title={t('airgapBundles.delete', 'Delete')}>
            <IconButton size="small" onClick={() => handleDelete(p.row)}>
              <DeleteIcon fontSize="small" />
            </IconButton>
          </Tooltip>
        </Stack>
      ),
    },
  ];

  const errorRows = bundles.filter((b) => b.status === 'failed' && b.error_message);

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
      <Card>
        <CardHeader
          title={t('airgapBundles.title', 'Air-Gap Install Bundles')}
          subheader={t(
            'airgapBundles.subtitle',
            'Generate a multi-OS ISO containing sysmanage server or agent + all per-platform dependencies, ready to mount on an air-gapped host.',
          )}
          action={
            <Tooltip title={t('common.refresh', 'Refresh')}>
              <IconButton onClick={refresh}>
                <RefreshIcon />
              </IconButton>
            </Tooltip>
          }
        />
        <CardContent>
          <Stack spacing={2}>
            <Alert severity="info">
              {t(
                'airgapBundles.requiresDocker',
                'Bundle builds require Docker to be installed and running on this server — needed to fetch per-distro Linux packages. Builds typically take 5-30 minutes depending on how many platforms are enabled.',
              )}
            </Alert>
            <Stack direction="row" spacing={2}>
              <Button
                variant="contained"
                startIcon={
                  building === 'server' ? (
                    <CircularProgress size={16} />
                  ) : (
                    <BuildIcon />
                  )
                }
                disabled={building !== null}
                onClick={() => handleBuild('server')}
              >
                {t('airgapBundles.buildServer', 'Build Server Bundle')}
              </Button>
              <Button
                variant="contained"
                color="secondary"
                startIcon={
                  building === 'agent' ? (
                    <CircularProgress size={16} />
                  ) : (
                    <BuildIcon />
                  )
                }
                disabled={building !== null}
                onClick={() => handleBuild('agent')}
              >
                {t('airgapBundles.buildAgent', 'Build Agent Bundle')}
              </Button>
            </Stack>

            {errorRows.length > 0 && (
              <Alert severity="error">
                <Typography variant="subtitle2">
                  {t(
                    'airgapBundles.recentFailures',
                    'Recent build failures:',
                  )}
                </Typography>
                {errorRows.slice(0, 3).map((b) => (
                  <Typography
                    key={b.id}
                    variant="body2"
                    sx={{ fontFamily: 'monospace', mt: 1 }}
                  >
                    {b.product}: {b.error_message?.split('\n')[0]}
                  </Typography>
                ))}
              </Alert>
            )}

            <Box sx={{ height: 480 }}>
              {loading ? (
                <Box
                  sx={{
                    display: 'flex',
                    justifyContent: 'center',
                    p: 3,
                  }}
                >
                  <CircularProgress />
                </Box>
              ) : bundles.length === 0 ? (
                <Typography color="text.secondary">
                  {t(
                    'airgapBundles.empty',
                    'No bundles yet. Click a build button above to create one.',
                  )}
                </Typography>
              ) : (
                <DataGrid
                  rows={bundles}
                  columns={columns}
                  getRowId={(r) => r.id}
                  disableRowSelectionOnClick
                  density="compact"
                />
              )}
            </Box>
          </Stack>
        </CardContent>
      </Card>

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

export default AirGapBundlesSettings;
