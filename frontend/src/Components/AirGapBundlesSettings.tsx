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
  ContentCopy as ContentCopyIcon,
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
  product: 'server' | 'agent' | 'proplus';
  status: BundleStatus;
  created_at: string | null;
  started_at: string | null;
  completed_at: string | null;
  size_bytes: number | null;
  error_message: string | null;
  version: string | null;
}

interface DockerStatus {
  installed: boolean;
  running: boolean;
  version: string | null;
  user_in_group: boolean;
  process_user: string;
  error: string | null;
  permission_denied: boolean;
}

interface ResourceStatus {
  ram_total_mb: number | null;
  ram_available_mb: number | null;
  swap_total_mb: number | null;
  swap_free_mb: number | null;
  available_mb: number | null;
  disk_free_gb: number | null;
  disk_total_gb: number | null;
  min_available_mb: number;
  min_disk_gb: number;
  severity: 'ok' | 'warn' | 'insufficient';
  sufficient: boolean;
  reason: string | null;
}

const buildInstallCommand = (status: DockerStatus): string => {
  const user = status.process_user || 'sysmanage';
  const restart =
    user === 'sysmanage'
      ? 'sudo systemctl restart sysmanage'
      : '# then kill your dev server (make start) and run it again so the new group takes effect';
  if (!status.installed) {
    return `sudo apt install -y docker.io && sudo systemctl enable --now docker && sudo usermod -aG docker ${user} && ${restart}`;
  }
  if (!status.running && !status.permission_denied) {
    return 'sudo systemctl enable --now docker';
  }
  // permission_denied OR user_in_group is false: just need the group fix.
  return `sudo usermod -aG docker ${user}\n${restart}`;
};

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
  const [building, setBuilding] = useState<'server' | 'agent' | 'proplus' | null>(
    null,
  );
  const [docker, setDocker] = useState<DockerStatus | null>(null);
  const [resources, setResources] = useState<ResourceStatus | null>(null);

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

  const refreshDocker = useCallback(async () => {
    try {
      const r = await axiosInstance.get<DockerStatus>(
        '/api/airgap-bundles/docker-status',
      );
      setDocker(r.data);
    } catch (e) {
      console.error(e);
      // Don't snackbar — banner remains hidden if probe fails.
    }
  }, []);

  const refreshResources = useCallback(async () => {
    try {
      const r = await axiosInstance.get<ResourceStatus>(
        '/api/airgap-bundles/resource-status',
      );
      setResources(r.data);
    } catch (e) {
      console.error(e);
      // Leave resources null on probe failure -> non-blocking (the
      // server-side gate still enforces it on the actual build call).
    }
  }, []);

  useEffect(() => {
    refresh();
    refreshDocker();
    refreshResources();
  }, [refresh, refreshDocker, refreshResources]);

  // Auto-poll while any bundle is in-flight, so the status chip ticks
  // from "queued" -> "building" -> "ready"/"failed" without manual refresh.
  useEffect(() => {
    const inFlight = bundles.some(
      (b) => b.status === 'queued' || b.status === 'building',
    );
    if (!inFlight) return;
    const id = globalThis.setInterval(() => {
      refresh();
      refreshResources();
    }, 5000);
    return () => globalThis.clearInterval(id);
  }, [bundles, refresh, refreshResources]);

  const handleBuild = async (product: 'server' | 'agent' | 'proplus') => {
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

  const handleDownload = async (bundle: Bundle) => {
    // Bundle ISOs are multi-GB.  Buffering one through fetch()/Blob
    // (the old approach) loads the whole file into browser memory and
    // OOM-crashes the tab — and on the server side it used to crash the
    // backend too.  Instead: mint a short-lived single-bundle token
    // (authenticated POST), then point the browser straight at the
    // token-authed streaming route so it downloads to disk without
    // buffering.  A plain anchor click can't carry the Bearer header,
    // which is exactly why the token route exists.
    try {
      const tok = await axiosInstance.post<{ token: string }>(
        `/api/airgap-bundles/${bundle.id}/download-token`,
      );
      const filename = `sysmanage-${bundle.product}-bundle${
        bundle.version ? `-${bundle.version}` : ''
      }.iso`;
      const url = `/api/airgap-bundles/${bundle.id}/download-stream?token=${encodeURIComponent(
        tok.data.token,
      )}`;
      const a = document.createElement('a');
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      a.remove();
    } catch (e: unknown) {
      console.error(e);
      showError(
        t('airgapBundles.downloadError', 'Failed to download bundle'),
      );
    }
  };

  const columns: GridColDef[] = [
    {
      field: 'product',
      headerName: t('airgapBundles.bundle', 'Bundle'),
      width: 110,
      renderCell: (p: GridRenderCellParams<Bundle>) => {
        let chipColor: 'primary' | 'secondary' | 'success' = 'secondary';
        if (p.row.product === 'server') chipColor = 'primary';
        else if (p.row.product === 'proplus') chipColor = 'success';
        return <Chip size="small" label={p.row.product} color={chipColor} />;
      },
    },
    {
      field: 'version',
      headerName: t('airgapBundles.version', 'Version'),
      width: 120,
      valueGetter: (_v, row) => row.version || '—',
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

  // Docker is "ready" when the binary is installed, the daemon
  // responds to `docker info`, and the sysmanage user is in the
  // docker group (so the background build subprocess can talk to
  // the socket).  Any of those failing → block the Build buttons
  // and surface an install banner with the exact remediation.
  const dockerReady =
    docker !== null && docker.installed && docker.running && docker.user_in_group;

  // Resource gate for the heavy Docker builds (server/agent).  Null =
  // probe pending/failed -> don't block in the UI (the server still
  // enforces it).  Only an explicit "insufficient" disables the
  // buttons; a "warn" is allowed but flagged.
  const resourcesReady = resources === null ? true : resources.sufficient;

  const copyInstallCommand = async (cmd: string) => {
    try {
      await globalThis.navigator.clipboard.writeText(cmd);
      showSuccess(t('airgapBundles.copied', 'Command copied to clipboard'));
    } catch (e) {
      console.error(e);
      showError(t('airgapBundles.copyError', 'Could not access the clipboard'));
    }
  };

  const renderResourceBanner = () => {
    if (resources === null) return null;
    if (resources.severity === 'ok') return null; // keep the UI clean when fine
    const stats = (
      <Typography
        variant="caption"
        sx={{ fontFamily: 'monospace', display: 'block', mt: 0.5 }}
      >
        {`RAM available: ${resources.ram_available_mb ?? '—'} MB`}
        {resources.swap_free_mb != null
          ? ` · swap free: ${resources.swap_free_mb} MB`
          : ''}
        {resources.disk_free_gb != null
          ? ` · disk free: ${resources.disk_free_gb} GB`
          : ''}
      </Typography>
    );
    const insufficient = resources.severity === 'insufficient';
    return (
      <Alert severity={insufficient ? 'error' : 'warning'}>
        <Typography variant="subtitle2" gutterBottom>
          {insufficient
            ? t(
                'airgapBundles.resourcesInsufficient',
                'This server does not have enough free memory or disk to build a Server or Agent bundle — those buttons are disabled until resources are freed (add swap or grow the VM).',
              )
            : t(
                'airgapBundles.resourcesLow',
                'Low resources — the build can run but will lean on swap and may be slow.',
              )}
        </Typography>
        {resources.reason && (
          <Typography
            variant="caption"
            sx={{ fontFamily: 'monospace', display: 'block' }}
          >
            {resources.reason}
          </Typography>
        )}
        {stats}
        <Stack direction="row" spacing={1} sx={{ mt: 1 }}>
          <Button
            size="small"
            onClick={refreshResources}
            startIcon={<RefreshIcon />}
          >
            {t('airgapBundles.recheckResources', 'Re-check resources')}
          </Button>
        </Stack>
      </Alert>
    );
  };

  const renderDockerBanner = () => {
    if (docker === null) {
      // Probe still pending — show the original neutral notice so
      // the layout doesn't shift in/out.
      return (
        <Alert severity="info">
          {t(
            'airgapBundles.requiresDocker',
            'Bundle builds require Docker to be installed and running on this server — needed to fetch per-distro Linux packages. Builds typically take 5-30 minutes depending on how many platforms are enabled.',
          )}
        </Alert>
      );
    }
    if (dockerReady) {
      return (
        <Alert severity="success">
          {t('airgapBundles.dockerReady', 'Docker is ready')}
          {docker.version ? ` — ${docker.version}` : ''}.{' '}
          {t(
            'airgapBundles.dockerReadyHint',
            'Builds typically take 5-30 minutes depending on how many platforms are enabled.',
          )}
        </Alert>
      );
    }
    // Something's off — describe what and offer the install line.
    let summary: string;
    if (!docker.installed) {
      summary = t(
        'airgapBundles.dockerNotInstalled',
        'Docker is not installed on this server. Bundle builds need Docker to fetch per-distro Linux packages.',
      );
    } else if (docker.permission_denied) {
      // Daemon is up; we just can't read the socket.  This usually
      // means the current process user isn't in the docker group,
      // OR usermod was run but the process hasn't been restarted yet
      // (group membership is fixed at process spawn time).
      summary = t(
        'airgapBundles.dockerPermissionDenied',
        'The Docker daemon is running but the {{user}} user (the one running this sysmanage process) cannot read /var/run/docker.sock. Add the user to the docker group, then restart the sysmanage process so the new group set takes effect.',
        { user: docker.process_user || 'sysmanage' },
      );
    } else if (!docker.running) {
      summary = t(
        'airgapBundles.dockerNotRunning',
        'Docker is installed but the daemon is not reachable. Start it with: sudo systemctl enable --now docker.',
      );
    } else {
      summary = t(
        'airgapBundles.dockerNoGroup',
        'Docker is running but the {{user}} user is not in the docker group, so the build subprocess cannot reach the daemon socket.',
        { user: docker.process_user || 'sysmanage' },
      );
    }
    const installCommand = buildInstallCommand(docker);
    return (
      <Alert severity="warning">
        <Typography variant="subtitle2" gutterBottom>
          {summary}
        </Typography>
        {docker.error && (
          <Typography
            variant="caption"
            sx={{ fontFamily: 'monospace', display: 'block', mb: 1 }}
          >
            {docker.error}
          </Typography>
        )}
        <Typography variant="body2" gutterBottom>
          {t(
            'airgapBundles.dockerInstallHint',
            'Run this on the sysmanage server as a user with sudo:',
          )}
        </Typography>
        <Box
          sx={{
            display: 'flex',
            alignItems: 'flex-start',
            gap: 1,
            // Dark slab so text contrast is independent of the
            // Alert's warning palette (which tinted nested text yellow).
            backgroundColor: 'grey.900',
            color: 'common.white',
            border: '1px solid',
            borderColor: 'grey.700',
            borderRadius: 1,
            p: 1,
            fontFamily: 'monospace',
            fontSize: '0.85rem',
            whiteSpace: 'pre-wrap',
            wordBreak: 'break-all',
          }}
        >
          <Box sx={{ flex: 1 }}>{installCommand}</Box>
          <Tooltip title={t('airgapBundles.copy', 'Copy to clipboard')}>
            <IconButton
              size="small"
              onClick={() => copyInstallCommand(installCommand)}
              sx={{ color: 'common.white' }}
            >
              <ContentCopyIcon fontSize="small" />
            </IconButton>
          </Tooltip>
        </Box>
        <Stack direction="row" spacing={1} sx={{ mt: 1 }}>
          <Button size="small" onClick={refreshDocker} startIcon={<RefreshIcon />}>
            {t('airgapBundles.recheckDocker', 'Re-check Docker')}
          </Button>
        </Stack>
      </Alert>
    );
  };

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
            {renderDockerBanner()}
            {renderResourceBanner()}
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
                disabled={building !== null || !dockerReady || !resourcesReady}
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
                disabled={building !== null || !dockerReady || !resourcesReady}
                onClick={() => handleBuild('agent')}
              >
                {t('airgapBundles.buildAgent', 'Build Agent Bundle')}
              </Button>
              {/* Pro+ overlay bundle.  Doesn't need Docker — just
                  copies the build host's modules + license artifacts.
                  The whole tab is already Pro+-gated, so reaching
                  this button at all means the build host has the
                  artifacts to package up. */}
              <Button
                variant="contained"
                color="success"
                startIcon={
                  building === 'proplus' ? (
                    <CircularProgress size={16} />
                  ) : (
                    <BuildIcon />
                  )
                }
                disabled={building !== null}
                onClick={() => handleBuild('proplus')}
              >
                {t('airgapBundles.buildProplus', 'Build Pro+ Bundle')}
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
