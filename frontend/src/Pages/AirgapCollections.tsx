/**
 * Air-Gap Collection Runs page (Phase 11).
 *
 * Surface the collector-side of the air-gap topology: list past
 * runs, kick off a new one-shot run, download produced ISOs.
 *
 * Only renders meaningful content on ``role: collector`` deployments;
 * the page itself shows a "not applicable" notice everywhere else so
 * a direct URL hit doesn't blow up.  Pro+ + role gating is enforced
 * server-side too (handler returns 402 when the collector engine
 * isn't loaded).
 *
 * Recurring runs go through the separate schedules API; this page is
 * deliberately scoped to ad-hoc operator-triggered runs only.
 */
import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Alert,
  Box,
  Button,
  Checkbox,
  Chip,
  CircularProgress,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  FormControlLabel,
  IconButton,
  Snackbar,
  Stack,
  TextField,
  Tooltip,
  Typography,
} from '@mui/material';
import {
  DataGrid,
  GridColDef,
  GridRenderCellParams,
} from '@mui/x-data-grid';
import {
  Add as AddIcon,
  Delete as DeleteIcon,
  Download as DownloadIcon,
  Refresh as RefreshIcon,
} from '@mui/icons-material';
import { useTranslation } from 'react-i18next';

import axiosInstance from '../Services/api';
import { formatUTCTimestamp } from '../utils/dateUtils';

type RunStatus =
  | 'QUEUED'
  | 'MIRRORING'
  | 'STAGING_COMPLETE'
  | 'ISO_BUILT'
  | 'BURNING'
  | 'COMPLETE'
  | 'FAILED';

const IN_FLIGHT_STATUSES: RunStatus[] = [
  'QUEUED',
  'MIRRORING',
  'STAGING_COMPLETE',
  'ISO_BUILT',
  'BURNING',
];

interface CollectionRun {
  id: string;
  iso_label: string;
  media_size_bytes: number;
  include_cve: boolean;
  include_compliance: boolean;
  status: RunStatus | string;
  started_at: string | null;
  completed_at: string | null;
  error_message: string | null;
  cron_schedule: string | null;
  parent_run_id: string | null;
  created_at: string | null;
}

interface Manifest {
  id: string;
  disc_index: number;
  disc_count: number;
  iso_path: string;
  iso_sha256: string;
  iso_size_bytes: number;
  signer_fingerprint: string;
  signature_algorithm: string;
  format_version: number;
  created_at: string | null;
}

interface ServerInfo {
  role?: string;
}

const RUNS_URL = '/api/v1/airgap/collector/runs';

const statusColor = (
  s: string,
): 'default' | 'info' | 'success' | 'error' => {
  switch (s) {
    case 'QUEUED':
      return 'default';
    case 'MIRRORING':
    case 'STAGING_COMPLETE':
    case 'ISO_BUILT':
    case 'BURNING':
      return 'info';
    case 'COMPLETE':
      return 'success';
    case 'FAILED':
      return 'error';
    default:
      return 'default';
  }
};

const formatBytes = (n: number | null | undefined): string => {
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

const AirgapCollections: React.FC = () => {
  const { t } = useTranslation();

  const [serverRole, setServerRole] = useState<string>('standard');
  const [roleLoaded, setRoleLoaded] = useState(false);

  const [runs, setRuns] = useState<CollectionRun[]>([]);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);

  const [dialogOpen, setDialogOpen] = useState(false);
  const [formIsoLabel, setFormIsoLabel] = useState('');
  const [formMediaSizeMB, setFormMediaSizeMB] = useState<number>(4700);
  const [formIncludeCve, setFormIncludeCve] = useState(true);
  const [formIncludeCompliance, setFormIncludeCompliance] = useState(true);

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

  // Fetch server role once on mount — same pattern AirgapRepositories
  // uses.  The page renders the "not applicable" placeholder when the
  // role isn't ``collector``.
  useEffect(() => {
    let cancelled = false;
    fetch('/api/v1/server-info')
      .then((r) => (r.ok ? r.json() : null))
      .then((info: ServerInfo | null) => {
        if (cancelled) return;
        setServerRole(info?.role || 'standard');
        setRoleLoaded(true);
      })
      .catch(() => {
        if (cancelled) return;
        setRoleLoaded(true);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const r = await axiosInstance.get<CollectionRun[]>(RUNS_URL);
      setRuns(r.data);
    } catch (e: unknown) {
      const status = (e as { response?: { status?: number } })?.response?.status;
      if (status === 402) {
        // License gate — surface a friendly message instead of a
        // generic error.  The page still renders so the operator can
        // see why nothing's loading.
        showError(
          t(
            'airgapCollections.licenseRequired',
            'Air-gap collector engine not loaded; Pro+ license required.',
          ),
        );
      } else {
        showError(t('airgapCollections.loadError', 'Failed to load runs'));
      }
    } finally {
      setLoading(false);
    }
  }, [t]);

  useEffect(() => {
    if (!roleLoaded) return;
    if (serverRole !== 'collector') {
      setLoading(false);
      return;
    }
    refresh();
  }, [roleLoaded, serverRole, refresh]);

  // Auto-poll while any run is mid-lifecycle so chips advance from
  // QUEUED -> MIRRORING -> ... -> COMPLETE without a manual refresh.
  // Stops polling once everything's settled to avoid hammering the API.
  useEffect(() => {
    const inFlight = runs.some((r) => IN_FLIGHT_STATUSES.includes(r.status as RunStatus));
    if (!inFlight) return;
    const id = globalThis.setInterval(() => refresh(), 5000);
    return () => globalThis.clearInterval(id);
  }, [runs, refresh]);

  const handleOpenDialog = () => {
    setFormIsoLabel('');
    setFormMediaSizeMB(4700);
    setFormIncludeCve(true);
    setFormIncludeCompliance(true);
    setDialogOpen(true);
  };

  const handleCreate = async () => {
    const label = formIsoLabel.trim();
    if (!label) {
      showError(
        t('airgapCollections.dialog.isoLabelRequired', 'ISO label is required'),
      );
      return;
    }
    setSubmitting(true);
    try {
      await axiosInstance.post(RUNS_URL, {
        iso_label: label,
        // The API takes bytes; the dialog asks for MB because that's
        // how operators think about optical media (CD-700, DVD-4700,
        // BD-25000).  We multiply by 1_000_000 (decimal MB) to match
        // the DVD-5 default of 4.7 GB = 4_700_000_000 bytes.
        media_size_bytes: formMediaSizeMB * 1_000_000,
        include_cve: formIncludeCve,
        include_compliance: formIncludeCompliance,
      });
      showSuccess(
        t('airgapCollections.created', 'Collection run queued'),
      );
      setDialogOpen(false);
      await refresh();
    } catch (e: unknown) {
      const detail = (e as { response?: { data?: { detail?: string } } })
        ?.response?.data?.detail;
      showError(
        detail || t('airgapCollections.createError', 'Failed to create run'),
      );
    } finally {
      setSubmitting(false);
    }
  };

  const handleDelete = async (run: CollectionRun) => {
    if (
      !globalThis.confirm(
        t(
          'airgapCollections.confirmDelete',
          'Delete this collection run and its manifests?',
        ),
      )
    ) {
      return;
    }
    try {
      await axiosInstance.delete(`${RUNS_URL}/${run.id}`);
      showSuccess(t('airgapCollections.deleted', 'Collection run deleted'));
      await refresh();
    } catch (e: unknown) {
      const detail = (e as { response?: { data?: { detail?: string } } })
        ?.response?.data?.detail;
      showError(
        detail || t('airgapCollections.deleteError', 'Failed to delete run'),
      );
    }
  };

  const handleDownload = async (run: CollectionRun) => {
    // The download flow needs an authenticated request (Bearer JWT)
    // and the server returns a file stream — so we mirror the bundle
    // download pattern: fetch manifests, pick disc 1, then fetch the
    // ISO blob through axios and hand it to a hidden anchor.
    try {
      const list = await axiosInstance.get<Manifest[]>(
        `${RUNS_URL}/${run.id}/manifests`,
      );
      const disc1 = list.data.find((m) => m.disc_index === 1) || list.data[0];
      if (!disc1) {
        showError(
          t(
            'airgapCollections.noManifestFound',
            'Run has no manifest yet — try again once status is COMPLETE.',
          ),
        );
        return;
      }
      const response = await axiosInstance.get(
        `/api/v1/airgap/collector/manifests/${disc1.id}/download`,
        { responseType: 'blob' },
      );
      const blob = new Blob([response.data], {
        type: 'application/octet-stream',
      });
      const url = globalThis.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `airgap-${run.iso_label}-disc${disc1.disc_index}.iso`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      globalThis.URL.revokeObjectURL(url);
    } catch (e: unknown) {
      const detail = (e as { response?: { data?: { detail?: string } } })
        ?.response?.data?.detail;
      showError(
        detail || t('airgapCollections.downloadError', 'Failed to download ISO'),
      );
    }
  };

  const columns: GridColDef[] = useMemo(
    () => [
      {
        field: 'iso_label',
        headerName: t('airgapCollections.column.isoLabel', 'ISO Label'),
        flex: 1,
        minWidth: 160,
      },
      {
        field: 'status',
        headerName: t('airgapCollections.column.status', 'Status'),
        width: 160,
        renderCell: (p: GridRenderCellParams<CollectionRun>) => (
          <Chip
            size="small"
            label={p.row.status}
            color={statusColor(p.row.status)}
          />
        ),
      },
      {
        field: 'created_at',
        headerName: t('airgapCollections.column.created', 'Created'),
        width: 180,
        valueGetter: (_v, row: CollectionRun) =>
          row.created_at ? formatUTCTimestamp(row.created_at, '—') : '—',
      },
      {
        field: 'started_at',
        headerName: t('airgapCollections.column.started', 'Started'),
        width: 180,
        valueGetter: (_v, row: CollectionRun) =>
          row.started_at ? formatUTCTimestamp(row.started_at, '—') : '—',
      },
      {
        field: 'completed_at',
        headerName: t('airgapCollections.column.completed', 'Completed'),
        width: 180,
        valueGetter: (_v, row: CollectionRun) =>
          row.completed_at ? formatUTCTimestamp(row.completed_at, '—') : '—',
      },
      {
        field: 'media_size_bytes',
        headerName: t('airgapCollections.column.size', 'Size'),
        width: 110,
        valueGetter: (_v, row: CollectionRun) => formatBytes(row.media_size_bytes),
      },
      {
        field: 'actions',
        headerName: t('airgapCollections.column.actions', 'Actions'),
        width: 140,
        sortable: false,
        renderCell: (p: GridRenderCellParams<CollectionRun>) => (
          <Stack direction="row" spacing={0.5}>
            {p.row.status === 'COMPLETE' && (
              <Tooltip
                title={t('airgapCollections.actions.download', 'Download ISO')}
              >
                <IconButton size="small" onClick={() => handleDownload(p.row)}>
                  <DownloadIcon fontSize="small" />
                </IconButton>
              </Tooltip>
            )}
            <Tooltip title={t('airgapCollections.actions.delete', 'Delete')}>
              <IconButton size="small" onClick={() => handleDelete(p.row)}>
                <DeleteIcon fontSize="small" />
              </IconButton>
            </Tooltip>
          </Stack>
        ),
      },
    ],
    // Re-create columns when language changes so headerNames update.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [t],
  );

  if (!roleLoaded) {
    return (
      <Box sx={{ p: 4, display: 'flex', justifyContent: 'center' }}>
        <CircularProgress />
      </Box>
    );
  }

  if (serverRole !== 'collector') {
    return (
      <Box sx={{ p: 4 }}>
        <Typography variant="h4" gutterBottom>
          {t('airgapCollections.title', 'Air-Gap Collection Runs')}
        </Typography>
        <Alert severity="info">
          {t(
            'airgapCollections.notApplicable',
            'This page is only meaningful on collector-role deployments.',
          )}
        </Alert>
      </Box>
    );
  }

  return (
    <Box sx={{ p: 4 }}>
      <Stack
        direction="row"
        alignItems="center"
        justifyContent="space-between"
        sx={{ mb: 2 }}
      >
        <Box>
          <Typography variant="h4" gutterBottom>
            {t('airgapCollections.title', 'Air-Gap Collection Runs')}
          </Typography>
          <Typography variant="body2" color="text.secondary">
            {t(
              'airgapCollections.subtitle',
              'Trigger one-shot collection runs that mirror configured repositories, build a signed ISO, and write a manifest for ingestion on the air-gapped side.',
            )}
          </Typography>
        </Box>
        <Stack direction="row" spacing={1}>
          <Tooltip title={t('airgapCollections.refresh', 'Refresh')}>
            <IconButton onClick={refresh}>
              <RefreshIcon />
            </IconButton>
          </Tooltip>
          <Button
            variant="contained"
            startIcon={<AddIcon />}
            onClick={handleOpenDialog}
          >
            {t('airgapCollections.newRun', 'New Collection Run')}
          </Button>
        </Stack>
      </Stack>

      <Box sx={{ height: 540 }}>
        {loading ? (
          <Box sx={{ display: 'flex', justifyContent: 'center', p: 3 }}>
            <CircularProgress />
          </Box>
        ) : runs.length === 0 ? (
          <Typography color="text.secondary">
            {t(
              'airgapCollections.empty',
              'No collection runs yet. Click "New Collection Run" to start one.',
            )}
          </Typography>
        ) : (
          <DataGrid
            rows={runs}
            columns={columns}
            getRowId={(r) => r.id}
            disableRowSelectionOnClick
            density="compact"
          />
        )}
      </Box>

      <Dialog
        open={dialogOpen}
        onClose={() => setDialogOpen(false)}
        fullWidth
        maxWidth="sm"
      >
        <DialogTitle>
          {t('airgapCollections.dialog.title', 'New Collection Run')}
        </DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <TextField
              autoFocus
              required
              fullWidth
              label={t('airgapCollections.dialog.isoLabel', 'ISO Label')}
              value={formIsoLabel}
              onChange={(e) => setFormIsoLabel(e.target.value)}
              inputProps={{ maxLength: 80 }}
              helperText={t(
                'airgapCollections.dialog.isoLabelHelper',
                'Short identifier embedded in the produced ISO (e.g. "monthly-2026-05").',
              )}
            />
            <TextField
              required
              fullWidth
              type="number"
              label={t('airgapCollections.dialog.mediaSizeMb', 'Media Size (MB)')}
              value={formMediaSizeMB}
              onChange={(e) =>
                setFormMediaSizeMB(Math.max(1, parseInt(e.target.value, 10) || 0))
              }
              helperText={t(
                'airgapCollections.dialog.mediaSizeHelper',
                'Maximum size per disc in MB. Defaults to 4700 (DVD-5).',
              )}
            />
            <FormControlLabel
              control={
                <Checkbox
                  checked={formIncludeCve}
                  onChange={(e) => setFormIncludeCve(e.target.checked)}
                />
              }
              label={t(
                'airgapCollections.dialog.includeCve',
                'Include CVE feed snapshot',
              )}
            />
            <FormControlLabel
              control={
                <Checkbox
                  checked={formIncludeCompliance}
                  onChange={(e) => setFormIncludeCompliance(e.target.checked)}
                />
              }
              label={t(
                'airgapCollections.dialog.includeCompliance',
                'Include compliance bundle',
              )}
            />
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setDialogOpen(false)} disabled={submitting}>
            {t('airgapCollections.dialog.cancel', 'Cancel')}
          </Button>
          <Button
            variant="contained"
            onClick={handleCreate}
            disabled={submitting}
            startIcon={submitting ? <CircularProgress size={16} /> : undefined}
          >
            {t('airgapCollections.dialog.submit', 'Queue Run')}
          </Button>
        </DialogActions>
      </Dialog>

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

export default AirgapCollections;
