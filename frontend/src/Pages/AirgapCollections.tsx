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
  FormControl,
  FormControlLabel,
  IconButton,
  InputLabel,
  MenuItem,
  Select,
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

interface RunTarget {
  // Option-B: operator picks a mirror; backend derives distro/version.
  mirror_id: string;
  distro?: string | null;
  version?: string | null;
  repos: string[];
  mirror_name?: string | null;
  source_snapshot_id?: string | null;
}

// Trimmed projection of a MirrorRepository row — just what the
// run-create dialog needs to render its picker.
interface MirrorPickItem {
  id: string;
  name: string;
  package_manager: string;
  host_id: string;
  enabled: boolean;
  known_version_id: string | null;
}

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
  worker_message_id?: string | null;
  burn_device?: string | null;
  targets?: RunTarget[];
}

// Distros the Pro+ engine accepts (validate_collection_request gate).
// Keep in sync with airgap_collector_engine.SUPPORTED_DISTROS.
// SUPPORTED_DISTROS used to drive the picker; now the picker reads
// mirrors from /api/mirror-repositories so this constant has no
// runtime consumer.  Kept as a doc-style reference of what the Pro+
// engine accepts in case a future feature needs it again.

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

interface DiscInfo {
  disc_index: number;
  filename: string;
  size_bytes: number;
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

const formatElapsed = (since: Date): string => {
  const ms = Date.now() - since.getTime();
  if (ms < 60_000) return `${Math.max(1, Math.round(ms / 1000))}s`;
  if (ms < 3_600_000) return `${Math.round(ms / 60_000)}m`;
  return `${Math.round(ms / 3_600_000)}h`;
};

/**
 * Status cell for a collection run.  For in-flight runs (QUEUED →
 * BURNING) it shows the status chip plus a live elapsed-time that
 * ticks every second — same UX as the mirror ActionStatusChip — so the
 * operator can see at a glance that a run is progressing (or how long
 * it's been wedged at QUEUED, which is the symptom that says the
 * orchestrator isn't advancing it).  Self-tickers per in-flight row
 * avoid rebuilding the whole DataGrid column array every second.
 */
const RunStatusCell: React.FC<{ row: CollectionRun }> = ({ row }) => {
  const inFlight = IN_FLIGHT_STATUSES.includes(row.status as RunStatus);
  // Throwaway tick state forces a 1s re-render while in-flight; the
  // interval is torn down the moment the run settles.
  const [, setTick] = useState(0);
  useEffect(() => {
    if (!inFlight) return undefined;
    const h = setInterval(() => setTick((n) => n + 1), 1000);
    return () => clearInterval(h);
  }, [inFlight]);

  // Anchor elapsed on started_at (set when the orchestrator dispatches
  // the first plan) and fall back to created_at for runs still sitting
  // at QUEUED before the orchestrator has touched them.
  const anchorRaw = row.started_at || row.created_at;
  const anchor = anchorRaw ? new Date(anchorRaw) : null;
  const elapsed = inFlight && anchor ? formatElapsed(anchor) : '';

  return (
    <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.75 }}>
      <Chip size="small" label={row.status} color={statusColor(row.status)} />
      {elapsed && (
        <Typography variant="caption" color="text.secondary">
          {elapsed}
        </Typography>
      )}
    </Box>
  );
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
  // Mirror-id picker state.  Multi-select; all picks must share a
  // host_id (the backend enforces this and 400s otherwise — we mirror
  // the validation client-side so the user gets feedback before
  // submit).
  const [formMirrorIds, setFormMirrorIds] = useState<string[]>([]);
  const [availableMirrors, setAvailableMirrors] = useState<MirrorPickItem[]>([]);
  // Optional optical-burn device.  Empty string = "don't burn, just
  // build the ISO file" (the typical flow).  Non-empty = orchestrator
  // dispatches a burn plan after ISO_BUILT.
  const [formBurnDevice, setFormBurnDevice] = useState<string>('');

  const [snackbarOpen, setSnackbarOpen] = useState(false);
  const [snackbarMessage, setSnackbarMessage] = useState('');
  const [snackbarSeverity, setSnackbarSeverity] = useState<
    'success' | 'error' | 'info'
  >('success');

  // Multi-disc picker.  Opened when the operator clicks Download on a
  // run that produced >1 disc.  Each entry is one downloadable ISO;
  // the picker calls handleDownload(run, disc_index) on selection.
  const [discPickerRun, setDiscPickerRun] = useState<CollectionRun | null>(null);
  const [discPickerEntries, setDiscPickerEntries] = useState<DiscInfo[]>([]);

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
  const showInfo = (m: string) => {
    setSnackbarMessage(m);
    setSnackbarSeverity('info');
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

  const handleOpenDialog = async () => {
    setFormIsoLabel('');
    setFormMediaSizeMB(4700);
    setFormIncludeCve(true);
    setFormIncludeCompliance(true);
    setFormMirrorIds([]);
    setFormBurnDevice('');
    setDialogOpen(true);
    // Lazy-load configured mirrors so the picker has fresh data
    // each time the dialog opens.  Filter to enabled-only here —
    // the backend would reject disabled picks but no point showing
    // them.
    try {
      const r = await axiosInstance.get<MirrorPickItem[]>(
        '/api/mirror-repositories',
      );
      setAvailableMirrors(r.data.filter((m) => m.enabled));
    } catch {
      // Non-fatal: show a hint inside the dialog if the list is
      // empty.  Submit-time backend validation catches a stale
      // local list.
      setAvailableMirrors([]);
    }
  };

  // Check that every picked mirror has the same host_id.  Backend
  // does the authoritative check; this exists so the operator sees
  // the constraint before clicking Submit.
  const pickedHostMismatch = useMemo(() => {
    if (formMirrorIds.length < 2) return false;
    const hosts = new Set(
      formMirrorIds
        .map((id) => availableMirrors.find((m) => m.id === id)?.host_id)
        .filter(Boolean),
    );
    return hosts.size > 1;
  }, [formMirrorIds, availableMirrors]);

  const handleCreate = async () => {
    const label = formIsoLabel.trim();
    if (!label) {
      showError(
        t('airgapCollections.dialog.isoLabelRequired', 'ISO label is required'),
      );
      return;
    }
    // Option-B input shape: send a mirror_id per target; backend
    // derives distro/version from the mirror's catalog row.
    if (formMirrorIds.length === 0) {
      showError(
        t(
          'airgapCollections.dialog.mirrorsRequired',
          'At least one mirror target is required.',
        ),
      );
      return;
    }
    if (pickedHostMismatch) {
      showError(
        t(
          'airgapCollections.dialog.hostMismatch',
          'All picked mirrors must live on the same host.',
        ),
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
        targets: formMirrorIds.map((id) => ({ mirror_id: id })),
        // Empty string = no burn step (build downloadable ISO and stop).
        // Trimmed so a stray space doesn't get treated as a device path.
        burn_device: formBurnDevice.trim() || null,
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

  const handleDownloadClick = async (run: CollectionRun) => {
    // Entry point from the Download icon.  Probes /discs first:
    //   * empty: surface "no ISO on disk" (rare; status said ready)
    //   * 1: skip the picker and download immediately
    //   * >1: open the picker; operator picks a disc
    try {
      const list = await axiosInstance.get<DiscInfo[]>(
        `${RUNS_URL}/${run.id}/discs`,
      );
      const discs = list.data;
      if (discs.length === 0) {
        showError(
          t(
            'airgapCollections.noIsoOnDisk',
            'No ISO file found on disk yet — re-poll in a moment.',
          ),
        );
        return;
      }
      if (discs.length === 1) {
        await handleDownload(run, discs[0].disc_index);
        return;
      }
      // Multi-disc: open the picker.  The picker's onSelect calls
      // back into handleDownload with the chosen disc_index.
      setDiscPickerRun(run);
      setDiscPickerEntries(discs);
      showInfo(
        t(
          'airgapCollections.multiDiscInfo',
          'This run produced {{count}} discs. Pick which to download.',
          { count: discs.length },
        ),
      );
    } catch (e: unknown) {
      // /discs is new — fall back to the legacy single-disc path so
      // older backends still work.
      const status = (e as { response?: { status?: number } })?.response?.status;
      if (status === 404) {
        await handleDownload(run);
      } else {
        const detail = (e as { response?: { data?: { detail?: string } } })
          ?.response?.data?.detail;
        showError(
          detail ||
            t('airgapCollections.downloadError', 'Failed to download ISO'),
        );
      }
    }
  };

  const handleDownload = async (run: CollectionRun, discIndex?: number) => {
    // Three paths:
    //   1. Raw ISO from /runs/{id}/iso[?disc=N] — works as soon as the
    //      run reaches ISO_BUILT.  This is the typical "build an ISO
    //      and download it" flow; no optical disc, no signed manifest.
    //   2. Signed manifest disc from /manifests/{id}/download — used
    //      when the run actually burned to disc and produced a
    //      manifest envelope.  Only kicks in when the ISO endpoint
    //      can't satisfy the request (e.g. file purged).
    // The optional ``discIndex`` argument selects which disc to
    // download on multi-disc runs (passed via ?disc=N).  Omit for the
    // first-disc / single-disc default.
    try {
      const apiUrl =
        discIndex && discIndex > 1
          ? `${RUNS_URL}/${run.id}/iso?disc=${discIndex}`
          : `${RUNS_URL}/${run.id}/iso`;
      const response = await axiosInstance.get(apiUrl, {
        responseType: 'blob',
      });
      const blob = new Blob([response.data], {
        type: 'application/octet-stream',
      });
      const blobUrl = globalThis.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = blobUrl;
      a.download = `${run.iso_label}-${run.id}.iso`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      globalThis.URL.revokeObjectURL(blobUrl);
      return;
    } catch (isoErr: unknown) {
      const status = (isoErr as { response?: { status?: number } })?.response
        ?.status;
      // Only fall back to manifest download for "file gone" /
      // "wrong status" outcomes.  401/403/etc. should bubble up as
      // the original error.
      if (status !== 410 && status !== 404 && status !== 409) {
        const detail = (isoErr as { response?: { data?: { detail?: string } } })
          ?.response?.data?.detail;
        showError(
          detail ||
            t('airgapCollections.downloadError', 'Failed to download ISO'),
        );
        return;
      }
    }
    try {
      const list = await axiosInstance.get<Manifest[]>(
        `${RUNS_URL}/${run.id}/manifests`,
      );
      const disc1 = list.data.find((m) => m.disc_index === 1) || list.data[0];
      if (!disc1) {
        showError(
          t(
            'airgapCollections.noManifestFound',
            'Run has no downloadable ISO yet — wait until status reaches ISO_BUILT or COMPLETE.',
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
        width: 180,
        renderCell: (p: GridRenderCellParams<CollectionRun>) => (
          <RunStatusCell row={p.row} />
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
            {/* Show the download icon as soon as the ISO file exists
                on disk (ISO_BUILT) — operators shouldn't have to wait
                through an optional BURNING stage to get the ISO. */}
            {(p.row.status === 'ISO_BUILT' ||
              p.row.status === 'BURNING' ||
              p.row.status === 'COMPLETE') && (
              <Tooltip
                title={t('airgapCollections.actions.download', 'Download ISO')}
              >
                <IconButton size="small" onClick={() => handleDownloadClick(p.row)}>
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

            {/* Mirror picker.  Option-B sources the bundle from
                snapshots of configured mirror_repository rows — the
                operator picks which ones to bundle and the backend
                handles snapshot dispatch + distro/version derivation. */}
            <Typography variant="subtitle2" sx={{ mt: 1 }}>
              {t('airgapCollections.dialog.mirrorsTitle', 'Mirrors')}
            </Typography>
            <Typography variant="caption" color="text.secondary">
              {t(
                'airgapCollections.dialog.mirrorsHelper',
                'Pick one or more configured mirrors. The bundle is built from a fresh snapshot of each mirror tree taken at run creation. All picks must share a host.',
              )}
            </Typography>
            {availableMirrors.length === 0 ? (
              <Alert severity="info" sx={{ mt: 1 }}>
                {t(
                  'airgapCollections.dialog.noMirrors',
                  'No enabled mirrors configured. Go to Settings → Repository Mirroring to add one, then try again.',
                )}
              </Alert>
            ) : (
              <FormControl size="small" fullWidth>
                <InputLabel id="mirror-picker-label">
                  {t('airgapCollections.dialog.mirrorPicker', 'Pick mirrors')}
                </InputLabel>
                <Select
                  labelId="mirror-picker-label"
                  multiple
                  value={formMirrorIds}
                  label={t(
                    'airgapCollections.dialog.mirrorPicker',
                    'Pick mirrors',
                  )}
                  onChange={(e) =>
                    setFormMirrorIds(
                      typeof e.target.value === 'string'
                        ? e.target.value.split(',')
                        : (e.target.value as string[]),
                    )
                  }
                  renderValue={(selected) =>
                    (selected as string[])
                      .map(
                        (id) =>
                          availableMirrors.find((m) => m.id === id)?.name ?? id,
                      )
                      .join(', ')
                  }
                >
                  {availableMirrors.map((m) => (
                    <MenuItem key={m.id} value={m.id}>
                      <Checkbox checked={formMirrorIds.includes(m.id)} />
                      <Typography variant="body2">
                        {m.name}{' '}
                        <Typography
                          variant="caption"
                          color="text.secondary"
                          component="span"
                        >
                          ({m.package_manager}
                          {m.known_version_id ? '' : ' — no catalog version!'})
                        </Typography>
                      </Typography>
                    </MenuItem>
                  ))}
                </Select>
              </FormControl>
            )}
            {pickedHostMismatch && (
              <Alert severity="warning" sx={{ mt: 1 }}>
                {t(
                  'airgapCollections.dialog.hostMismatchWarning',
                  'The mirrors you picked span multiple hosts. The collection plan dispatches to a single host, so all picks must share one.',
                )}
              </Alert>
            )}

            <TextField
              fullWidth
              size="small"
              label={t(
                'airgapCollections.dialog.burnDevice',
                'Optical burn device (optional)',
              )}
              placeholder="/dev/sr0"
              value={formBurnDevice}
              onChange={(e) => setFormBurnDevice(e.target.value)}
              helperText={t(
                'airgapCollections.dialog.burnDeviceHelper',
                'Leave blank to build a downloadable ISO file only. Setting a device adds a BURNING stage after ISO_BUILT.',
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

      {/* Multi-disc picker.  Opens when handleDownloadClick sees the
          run produced >1 disc; closes on disc selection or cancel. */}
      <Dialog
        open={discPickerRun !== null}
        onClose={() => setDiscPickerRun(null)}
        fullWidth
        maxWidth="xs"
      >
        <DialogTitle>
          {t(
            'airgapCollections.discPicker.title',
            'Pick a disc to download',
          )}
        </DialogTitle>
        <DialogContent>
          <Stack spacing={1} sx={{ mt: 1 }}>
            {discPickerEntries.map((d) => (
              <Button
                key={d.disc_index}
                variant="outlined"
                startIcon={<DownloadIcon />}
                onClick={async () => {
                  if (!discPickerRun) return;
                  const run = discPickerRun;
                  setDiscPickerRun(null);
                  await handleDownload(run, d.disc_index);
                }}
              >
                {t('airgapCollections.discPicker.row', 'Disc {{n}} — {{size}}', {
                  n: d.disc_index,
                  size: formatBytes(d.size_bytes),
                })}
              </Button>
            ))}
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setDiscPickerRun(null)}>
            {t('airgapCollections.discPicker.cancel', 'Cancel')}
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
