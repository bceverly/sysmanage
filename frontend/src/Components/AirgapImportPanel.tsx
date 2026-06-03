/**
 * Air-Gap Repositories → Import-from-device panel.
 *
 * Shows the operator-selected import drive's live status and an Import
 * button that's enabled only when that drive currently holds readable
 * ISO media.  A Rescan button re-probes after the operator fixes
 * something (inserts a disc, etc.).  Import queues an ingest run; the
 * existing repository list/freshness below it then reflects the result
 * once the ingest tick finishes.
 *
 * The drive itself is chosen in Settings → Server Role (ImportDeviceCard);
 * this panel only consumes the choice + triggers the import.
 */
import React, { useCallback, useEffect, useState } from 'react';
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  CircularProgress,
  Snackbar,
  Typography,
} from '@mui/material';
import RefreshIcon from '@mui/icons-material/Refresh';
import FileDownloadIcon from '@mui/icons-material/FileDownload';
import { useTranslation } from 'react-i18next';

import axiosInstance from '../Services/api';

const STATUS_URL = '/api/v1/airgap/import-device/status';
const INGEST_URL = '/api/v1/airgap/repository/ingest-device';

interface DeviceStatus {
  device: string | null;
  ready: boolean;
  reason?: string;
  label?: string | null;
  fstype?: string | null;
}

const AirgapImportPanel: React.FC = () => {
  const { t } = useTranslation();
  const [status, setStatus] = useState<DeviceStatus | null>(null);
  const [scanning, setScanning] = useState(false);
  const [importing, setImporting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [ok, setOk] = useState<string | null>(null);

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

  useEffect(() => {
    rescan();
  }, [rescan]);

  const doImport = async () => {
    setImporting(true);
    setError(null);
    setOk(null);
    try {
      const r = await axiosInstance.post<{ run_id: string; device: string }>(
        INGEST_URL,
      );
      setOk(
        t('airgapImport.queued', 'Import queued from {{dev}} (run {{id}}).', {
          dev: r.data.device,
          id: r.data.run_id.slice(0, 8),
        }),
      );
    } catch (e: unknown) {
      const detail = (e as { response?: { data?: { detail?: string } } })
        ?.response?.data?.detail;
      setError(detail || t('airgapImport.importError', 'Could not start import.'));
    } finally {
      setImporting(false);
    }
  };

  const noDevice = !status?.device;

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
              disabled={scanning}
            >
              {t('airgapImport.rescan', 'Rescan')}
            </Button>
            <Button
              size="small"
              variant="contained"
              startIcon={importing ? <CircularProgress size={16} /> : <FileDownloadIcon />}
              onClick={doImport}
              disabled={!status?.ready || importing}
            >
              {t('airgapImport.import', 'Import ISO')}
            </Button>
          </Box>
        )}

        <Snackbar
          open={!!ok}
          autoHideDuration={6000}
          onClose={() => setOk(null)}
          anchorOrigin={{ vertical: 'bottom', horizontal: 'right' }}
        >
          <Alert severity="success" variant="filled" onClose={() => setOk(null)}>
            {ok}
          </Alert>
        </Snackbar>
      </CardContent>
    </Card>
  );
};

export default AirgapImportPanel;
