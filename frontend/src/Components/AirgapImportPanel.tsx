// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

/**
 * Air-Gap Repositories → Import-from-device panel.
 *
 * Shows the operator-selected import drive's live status and an Import
 * button that's enabled only when that drive currently holds readable
 * ISO media.  A Rescan button re-probes after the operator fixes
 * something (inserts a disc, etc.).  Import queues an ingest run, then
 * this panel POLLS that run to COMPLETE/FAILED — showing the live stage
 * (QUEUED → VERIFYING_SIG → COPYING → COMPLETE) inline — and calls
 * ``onComplete`` so the parent refreshes the repository list without a
 * manual page reload.
 *
 * The drive itself is chosen in Settings → Server Role (ImportDeviceCard);
 * this panel only consumes the choice + triggers/tracks the import.
 */
import React, { useCallback, useEffect, useRef, useState } from 'react';
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  CircularProgress,
  LinearProgress,
  Typography,
} from '@mui/material';
import RefreshIcon from '@mui/icons-material/Refresh';
import FileDownloadIcon from '@mui/icons-material/FileDownload';
import { useTranslation } from 'react-i18next';

import axiosInstance from '../Services/api';

const STATUS_URL = '/api/v1/airgap/import-device/status';
const INGEST_URL = '/api/v1/airgap/repository/ingest-device';
const RUNS_URL = '/api/v1/airgap/repository/ingest-runs';

const TERMINAL = new Set(['COMPLETE', 'FAILED']);

interface DeviceStatus {
  device: string | null;
  ready: boolean;
  reason?: string;
  label?: string | null;
  fstype?: string | null;
}

interface IngestRun {
  id: string;
  status: string;
  error_message?: string | null;
  file_count?: number | null;
  byte_count?: number | null;
  created_at?: string | null;
}

interface Props {
  onComplete?: () => void;
}

const fmtBytes = (n: number | null | undefined): string => {
  if (n == null) return '';
  const u = ['B', 'KB', 'MB', 'GB', 'TB'];
  let v = n;
  let i = 0;
  while (v >= 1024 && i < u.length - 1) {
    v /= 1024;
    i += 1;
  }
  return `${v.toFixed(v < 10 && i > 0 ? 1 : 0)} ${u[i]}`;
};

const AirgapImportPanel: React.FC<Props> = ({ onComplete }) => {
  const { t } = useTranslation();
  const [status, setStatus] = useState<DeviceStatus | null>(null);
  const [scanning, setScanning] = useState(false);
  const [importing, setImporting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [run, setRun] = useState<IngestRun | null>(null);

  // Track which run we're following + whether the last poll was terminal,
  // so onComplete fires exactly once per finished import.
  const trackedId = useRef<string | null>(null);
  const firedComplete = useRef<string | null>(null);

  const rescan = useCallback(async () => {
    setScanning(true);
    try {
      const r = await axiosInstance.get<DeviceStatus>(STATUS_URL);
      setStatus(r.data);
      setError(null);
    } catch {
      setError(t('airgapImport.statusError', 'Could not probe the import device.'));
    } finally {
      setScanning(false);
    }
  }, [t]);

  const fetchLatestRun = useCallback(async (): Promise<IngestRun | null> => {
    try {
      const r = await axiosInstance.get<{ runs: IngestRun[] }>(`${RUNS_URL}?limit=1`);
      return r.data.runs?.[0] || null;
    } catch {
      return null;
    }
  }, []);

  useEffect(() => {
    rescan();
    // On mount, surface any already-in-flight run (e.g. after a reload).
    fetchLatestRun().then((latest) => {
      if (latest) {
        setRun(latest);
        if (!TERMINAL.has(latest.status)) trackedId.current = latest.id;
      }
    });
  }, [rescan, fetchLatestRun]);

  // Poll while we're tracking a non-terminal run.
  useEffect(() => {
    if (!run || TERMINAL.has(run.status)) return undefined;
    const timer = globalThis.setInterval(async () => {
      const latest = await fetchLatestRun();
      if (!latest) return;
      setRun(latest);
      if (
        latest.status === 'COMPLETE' &&
        firedComplete.current !== latest.id
      ) {
        firedComplete.current = latest.id;
        onComplete?.();
      }
    }, 4000);
    return () => globalThis.clearInterval(timer);
  }, [run, fetchLatestRun, onComplete]);

  const doImport = async () => {
    setImporting(true);
    setError(null);
    try {
      const r = await axiosInstance.post<{ run_id: string; device: string }>(
        INGEST_URL,
      );
      trackedId.current = r.data.run_id;
      // Kick off tracking immediately with an optimistic QUEUED row.
      setRun({ id: r.data.run_id, status: 'QUEUED' });
    } catch (e: unknown) {
      const detail = (e as { response?: { data?: { detail?: string } } })
        ?.response?.data?.detail;
      setError(detail || t('airgapImport.importError', 'Could not start import.'));
    } finally {
      setImporting(false);
    }
  };

  const noDevice = !status?.device;
  const inFlight = run != null && !TERMINAL.has(run.status);

  const runColor = (s: string): 'success' | 'error' | 'info' => {
    if (s === 'COMPLETE') return 'success';
    if (s === 'FAILED') return 'error';
    return 'info';
  };

  const runLabel = (s: string): string => {
    const map: Record<string, string> = {
      QUEUED: t('airgapImport.run.queued', 'Queued'),
      VERIFYING_SIG: t('airgapImport.run.verifying', 'Verifying signature'),
      VERIFIED: t('airgapImport.run.verified', 'Verified'),
      COPYING: t('airgapImport.run.copying', 'Copying packages'),
      COMPLETE: t('airgapImport.run.complete', 'Complete'),
      FAILED: t('airgapImport.run.failed', 'Failed'),
    };
    return map[s] || s;
  };

  return (
    <Card sx={{ mb: 2 }}>
      <CardContent>
        <Typography variant="h6" gutterBottom>
          {t('airgapImport.title', 'Import from Media')}
        </Typography>

        {error && (
          <Alert severity="error" sx={{ mb: 1 }} onClose={() => setError(null)}>
            {error}
          </Alert>
        )}

        {noDevice ? (
          <Alert severity="info">
            {t(
              'airgapImport.noDevice',
              'No import drive selected. Choose one in Settings → Server Role.',
            )}
          </Alert>
        ) : (
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, flexWrap: 'wrap' }}>
            <Typography variant="body2">
              {t('airgapImport.device', 'Drive')}: <code>{status?.device}</code>
            </Typography>
            <Chip
              size="small"
              color={status?.ready ? 'success' : 'default'}
              label={
                status?.ready
                  ? t('airgapImport.ready', 'Ready{{label}}', {
                      label: status?.label ? ` · ${status.label}` : '',
                    })
                  : status?.reason || t('airgapImport.notReady', 'Not ready')
              }
            />
            <Button
              size="small"
              variant="outlined"
              startIcon={scanning ? <CircularProgress size={16} /> : <RefreshIcon />}
              onClick={rescan}
              disabled={scanning || inFlight}
            >
              {t('airgapImport.rescan', 'Rescan')}
            </Button>
            <Button
              size="small"
              variant="contained"
              startIcon={importing ? <CircularProgress size={16} /> : <FileDownloadIcon />}
              onClick={doImport}
              disabled={!status?.ready || importing || inFlight}
            >
              {t('airgapImport.import', 'Import ISO')}
            </Button>
          </Box>
        )}

        {run && (
          <Box sx={{ mt: 2 }}>
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
              <Typography variant="body2">
                {t('airgapImport.runStatus', 'Import status')}:
              </Typography>
              <Chip size="small" color={runColor(run.status)} label={runLabel(run.status)} />
              {run.status === 'COMPLETE' && run.file_count != null && (
                <Typography variant="caption" color="text.secondary">
                  {t('airgapImport.runStats', '{{files}} files · {{size}}', {
                    files: run.file_count,
                    size: fmtBytes(run.byte_count),
                  })}
                </Typography>
              )}
            </Box>
            {inFlight && <LinearProgress sx={{ mt: 1 }} />}
            {run.status === 'FAILED' && run.error_message && (
              <Alert severity="error" sx={{ mt: 1 }}>
                {run.error_message}
              </Alert>
            )}
            {run.status === 'COMPLETE' && (
              <Alert severity="success" sx={{ mt: 1 }}>
                {t(
                  'airgapImport.runDone',
                  'Import complete — the repository list below is refreshed.',
                )}
              </Alert>
            )}
          </Box>
        )}
      </CardContent>
    </Card>
  );
};

export default AirgapImportPanel;
