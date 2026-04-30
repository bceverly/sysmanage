import React, { useState, useEffect, useCallback, useMemo } from 'react';
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
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
  PlayArrow as PlayArrowIcon,
  CloudSync as CloudSyncIcon,
  CheckCircle as CheckCircleIcon,
  Cancel as CancelIcon,
  HourglassEmpty as HourglassEmptyIcon,
  ExpandLess as ExpandLessIcon,
  ExpandMore as ExpandMoreIcon,
} from '@mui/icons-material';
import { TFunction } from 'i18next';
import { useTranslation } from 'react-i18next';
import {
  ComplianceStatus,
  HostComplianceStatus,
  PackageProfile,
  packageProfilesService,
} from '../Services/packageProfiles';
import { formatUTCTimestamp } from '../utils/dateUtils';

interface HostCompliancePanelProps {
  hostId: string;
}

interface RowShape {
  id: string;
  profile: PackageProfile;
  status: HostComplianceStatus | null;
}

const statusChip = (status: ComplianceStatus | null, t: TFunction) => {
  if (status === 'COMPLIANT') {
    return (
      <Chip
        size="small"
        color="success"
        icon={<CheckCircleIcon />}
        label={t('compliance.compliant', 'Compliant')}
      />
    );
  }
  if (status === 'NON_COMPLIANT') {
    return (
      <Chip
        size="small"
        color="error"
        icon={<CancelIcon />}
        label={t('compliance.nonCompliant', 'Non-Compliant')}
      />
    );
  }
  if (status === 'PENDING') {
    return (
      <Chip
        size="small"
        color="warning"
        icon={<HourglassEmptyIcon />}
        label={t('compliance.pending', 'Pending')}
      />
    );
  }
  return (
    <Chip size="small" label={t('compliance.notScanned', 'Not Scanned')} variant="outlined" />
  );
};

const HostCompliancePanel: React.FC<HostCompliancePanelProps> = ({ hostId }) => {
  const { t } = useTranslation();

  const [profiles, setProfiles] = useState<PackageProfile[]>([]);
  const [statuses, setStatuses] = useState<HostComplianceStatus[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [scanningProfileId, setScanningProfileId] = useState<string | null>(null);

  const [snackbarOpen, setSnackbarOpen] = useState(false);
  const [snackbarMessage, setSnackbarMessage] = useState('');
  const [snackbarSeverity, setSnackbarSeverity] = useState<'success' | 'error'>('success');

  const [expandedRowIds, setExpandedRowIds] = useState<Set<string>>(new Set());

  const showError = (msg: string) => {
    setSnackbarMessage(msg);
    setSnackbarSeverity('error');
    setSnackbarOpen(true);
  };
  const showSuccess = (msg: string) => {
    setSnackbarMessage(msg);
    setSnackbarSeverity('success');
    setSnackbarOpen(true);
  };

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [p, s] = await Promise.all([
        packageProfilesService.list(),
        packageProfilesService.statusForHost(hostId),
      ]);
      setProfiles(p);
      setStatuses(s);
    } catch (e) {
      console.error(e);
      setError(t('compliance.loadError', 'Failed to load compliance data'));
    } finally {
      setLoading(false);
    }
  }, [hostId, t]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const rows: RowShape[] = useMemo(() => {
    const byProfile = new Map<string, HostComplianceStatus>();
    statuses.forEach((s) => byProfile.set(s.profile_id, s));
    return profiles.map((p) => ({
      id: p.id,
      profile: p,
      status: byProfile.get(p.id) ?? null,
    }));
  }, [profiles, statuses]);

  const toggleExpand = (id: string) => {
    setExpandedRowIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const handleScan = async (profileId: string) => {
    setScanningProfileId(profileId);
    try {
      const r = await packageProfilesService.scanHost(profileId, hostId);
      showSuccess(
        t('compliance.scanResult', 'Scan complete: {{status}} ({{count}} violation(s))', {
          status: r.status,
          count: r.violations?.length ?? 0,
        }),
      );
      await refresh();
    } catch (e: unknown) {
      const detail = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      showError(detail || t('compliance.scanError', 'Scan failed'));
    } finally {
      setScanningProfileId(null);
    }
  };

  const handleDispatch = async (profileId: string) => {
    setScanningProfileId(profileId);
    try {
      await packageProfilesService.dispatchToAgent(profileId, hostId);
      showSuccess(
        t(
          'compliance.dispatchSent',
          'Live-scan dispatched to agent — result will arrive shortly',
        ),
      );
      await refresh();
    } catch (e: unknown) {
      const detail = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      showError(detail || t('compliance.dispatchError', 'Failed to dispatch live scan'));
    } finally {
      setScanningProfileId(null);
    }
  };

  const columns: GridColDef[] = [
    {
      field: 'expand',
      headerName: '',
      width: 50,
      sortable: false,
      renderCell: (params: GridRenderCellParams<RowShape>) => {
        const violations = params.row.status?.violations ?? [];
        if (violations.length === 0) return null;
        return (
          <IconButton
            size="small"
            onClick={() => toggleExpand(params.row.id)}
            aria-label={t('compliance.expandViolations', 'Toggle violations')}
          >
            {expandedRowIds.has(params.row.id) ? <ExpandLessIcon /> : <ExpandMoreIcon />}
          </IconButton>
        );
      },
    },
    {
      field: 'profile_name',
      headerName: t('compliance.profile', 'Profile'),
      flex: 1,
      minWidth: 180,
      valueGetter: (_v, row) => row.profile.name,
    },
    {
      field: 'status',
      headerName: t('compliance.status', 'Status'),
      width: 170,
      renderCell: (params: GridRenderCellParams<RowShape>) =>
        statusChip(params.row.status?.status ?? null, t),
    },
    {
      field: 'violations',
      headerName: t('compliance.violations', 'Violations'),
      width: 130,
      valueGetter: (_v, row) => row.status?.violations?.length ?? 0,
    },
    {
      field: 'last_scan_at',
      headerName: t('compliance.lastScan', 'Last Scan'),
      width: 180,
      valueGetter: (_v, row) =>
        row.status?.last_scan_at ? formatUTCTimestamp(row.status.last_scan_at, '—') : '—',
    },
    {
      field: 'actions',
      headerName: t('common.actions', 'Actions'),
      sortable: false,
      width: 200,
      renderCell: (params: GridRenderCellParams<RowShape>) => {
        const isScanning = scanningProfileId === params.row.id;
        return (
          <Stack direction="row" spacing={0.5}>
            <Tooltip title={t('compliance.scanNow', 'Scan against cached inventory')}>
              <span>
                <Button
                  size="small"
                  startIcon={isScanning ? <CircularProgress size={14} /> : <PlayArrowIcon />}
                  onClick={() => handleScan(params.row.id)}
                  disabled={isScanning}
                >
                  {t('compliance.scanNow', 'Scan')}
                </Button>
              </span>
            </Tooltip>
            <Tooltip title={t('compliance.dispatchTooltip', 'Ask the agent for a live scan')}>
              <span>
                <Button
                  size="small"
                  startIcon={<CloudSyncIcon />}
                  onClick={() => handleDispatch(params.row.id)}
                  disabled={isScanning}
                >
                  {t('compliance.dispatch', 'Live Scan')}
                </Button>
              </span>
            </Tooltip>
          </Stack>
        );
      },
    },
  ];

  if (loading) {
    return (
      <Box sx={{ display: 'flex', justifyContent: 'center', p: 4 }}>
        <CircularProgress />
      </Box>
    );
  }

  if (error) {
    return <Alert severity="error">{error}</Alert>;
  }

  if (profiles.length === 0) {
    return (
      <Card>
        <CardContent>
          <Typography color="text.secondary">
            {t(
              'compliance.noProfiles',
              'No compliance profiles defined. Create one in Settings → Compliance Profiles.',
            )}
          </Typography>
        </CardContent>
      </Card>
    );
  }

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
      <Box sx={{ height: 480 }}>
        <DataGrid
          rows={rows}
          columns={columns}
          getRowId={(row) => row.id}
          disableRowSelectionOnClick
          density="compact"
        />
      </Box>

      {/* Violations detail for expanded rows */}
      {Array.from(expandedRowIds).map((rowId) => {
        const row = rows.find((r) => r.id === rowId);
        if (!row?.status?.violations?.length) return null;
        return (
          <Card key={`violations-${rowId}`} variant="outlined">
            <CardContent>
              <Typography variant="subtitle1" sx={{ mb: 1 }}>
                {t('compliance.violationsFor', 'Violations — {{name}}', {
                  name: row.profile.name,
                })}
              </Typography>
              <Stack spacing={1}>
                {row.status.violations.map((v, i) => {
                  const pkg = String(v.package_name ?? '');
                  const reason = v.reason ? String(v.reason) : JSON.stringify(v);
                  // Stable enough for our use:  expanded violations list
                  // is a snapshot rendered from immutable data after each
                  // refresh, so position-derived keys are safe here.
                  return (
                    <Box
                      key={`${rowId}-v-${i}-${pkg}`}
                      sx={{
                        p: 1,
                        borderRadius: 1,
                        bgcolor: 'error.light',
                        color: 'error.contrastText',
                      }}
                    >
                      <Typography variant="body2" sx={{ fontWeight: 600 }}>
                        {pkg || t('compliance.unknownPackage', '(unknown)')}
                      </Typography>
                      <Typography variant="body2">{reason}</Typography>
                    </Box>
                  );
                })}
              </Stack>
            </CardContent>
          </Card>
        );
      })}

      <Snackbar
        open={snackbarOpen}
        autoHideDuration={5000}
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

export default HostCompliancePanel;
