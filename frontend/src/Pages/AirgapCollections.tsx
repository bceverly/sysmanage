// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

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
  Add as AddIcon,
  Delete as DeleteIcon,
  Download as DownloadIcon,
  Refresh as RefreshIcon,
} from '@mui/icons-material';
import { useTranslation } from 'react-i18next';

import axiosInstance from '../Services/api';
import { formatUTCTimestamp } from '../utils/dateUtils';
import {
  CollectionRun,
  DiscInfo,
  IN_FLIGHT_STATUSES,
  Manifest,
  MirrorPickItem,
  RUNS_URL,
  RunStatus,
  RunStatusCell,
  ServerInfo,
  formatBytes,
} from '../Components/AirgapCollectionsHelpers';
import {
  DiscPickerDialog,
  NewRunDialog,
} from '../Components/AirgapCollectionsDialogs';

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
    const inFlight = runs.some((r) => IN_FLIGHT_STATUSES.has(r.status as RunStatus));
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
        '/api/v1/mirror-repositories',
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
      // Native streaming download.  Mint a short-lived, single-run token
      // (authenticated POST), then point the browser straight at the
      // token-authed download route so it streams to disk.  We must NOT
      // pull the response into a Blob — a multi-GB ISO buffered in memory
      // OOMs the browser tab (and can take the backend down behind a
      // buffering proxy).  The mint POST performs the same readiness
      // checks (404/409/410) the old GET did, so the catch below still
      // drives the manifest fallback correctly.
      const tokenResp = await axiosInstance.post(
        `${RUNS_URL}/${run.id}/iso-token`,
      );
      const dlToken = (tokenResp.data as { token: string }).token;
      const discQuery = discIndex && discIndex > 1 ? `&disc=${discIndex}` : '';
      const url = `${RUNS_URL}/${run.id}/iso-download?token=${encodeURIComponent(
        dlToken,
      )}${discQuery}`;
      const a = document.createElement('a');
      a.href = url;
      a.download = `${run.iso_label}-${run.id}.iso`;
      document.body.appendChild(a);
      a.click();
      a.remove();
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
        field: 'iso_size_bytes',
        headerName: t('airgapCollections.column.size', 'Size'),
        width: 110,
        // Show the ACTUAL built ISO size; before it's built (null) fall
        // back to the configured media size so the column isn't blank.
        valueGetter: (_v, row: CollectionRun) =>
          formatBytes(
            row.iso_size_bytes ?? row.media_size_bytes,
          ),
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
        {loading && (
          <Box sx={{ display: 'flex', justifyContent: 'center', p: 3 }}>
            <CircularProgress />
          </Box>
        )}
        {!loading && runs.length === 0 && (
          <Typography color="text.secondary">
            {t(
              'airgapCollections.empty',
              'No collection runs yet. Click "New Collection Run" to start one.',
            )}
          </Typography>
        )}
        {!loading && runs.length > 0 && (
          <DataGrid
            rows={runs}
            columns={columns}
            getRowId={(r) => r.id}
            disableRowSelectionOnClick
            density="compact"
          />
        )}
      </Box>

      <NewRunDialog
        open={dialogOpen}
        onClose={() => setDialogOpen(false)}
        submitting={submitting}
        onCreate={handleCreate}
        isoLabel={formIsoLabel}
        onIsoLabelChange={setFormIsoLabel}
        mediaSizeMB={formMediaSizeMB}
        onMediaSizeMBChange={setFormMediaSizeMB}
        includeCve={formIncludeCve}
        onIncludeCveChange={setFormIncludeCve}
        includeCompliance={formIncludeCompliance}
        onIncludeComplianceChange={setFormIncludeCompliance}
        mirrorIds={formMirrorIds}
        onMirrorIdsChange={setFormMirrorIds}
        availableMirrors={availableMirrors}
        pickedHostMismatch={pickedHostMismatch}
        burnDevice={formBurnDevice}
        onBurnDeviceChange={setFormBurnDevice}
      />

      {/* Multi-disc picker.  Opens when handleDownloadClick sees the
          run produced >1 disc; closes on disc selection or cancel. */}
      <DiscPickerDialog
        run={discPickerRun}
        entries={discPickerEntries}
        onClose={() => setDiscPickerRun(null)}
        onSelect={(run, discIndex) => {
          setDiscPickerRun(null);
          void handleDownload(run, discIndex);
        }}
      />

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
