import React, { useState, useEffect, useCallback } from 'react';
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  CardHeader,
  Chip,
  CircularProgress,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  FormControl,
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
  Block as BlockIcon,
  ContentCopy as ContentCopyIcon,
  Refresh as RefreshIcon,
} from '@mui/icons-material';
import { useTranslation } from 'react-i18next';
import {
  DynamicSecretLease,
  KindCatalog,
  LEASE_KINDS,
  LeaseKind,
  LeaseStatus,
  dynamicSecretsService,
} from '../Services/dynamicSecrets';
import { formatUTCTimestamp } from '../utils/dateUtils';

const STATUS_FILTERS: ('ALL' | LeaseStatus)[] = [
  'ALL',
  'ACTIVE',
  'REVOKED',
  'EXPIRED',
  'FAILED',
];

const DynamicSecretsSettings: React.FC = () => {
  const { t } = useTranslation();

  const [leases, setLeases] = useState<DynamicSecretLease[]>([]);
  const [catalog, setCatalog] = useState<KindCatalog | null>(null);
  const [statusFilter, setStatusFilter] = useState<'ALL' | LeaseStatus>('ACTIVE');
  const [loading, setLoading] = useState(true);

  const [issueDialogOpen, setIssueDialogOpen] = useState(false);
  const [form, setForm] = useState({
    name: '',
    kind: 'token' as LeaseKind,
    backend_role: 'default',
    ttl_seconds: 1800,
    note: '',
  });
  const [issuing, setIssuing] = useState(false);

  const [revealedSecret, setRevealedSecret] = useState<{
    name: string;
    secret: string;
    expires_at: string | null;
    kind: LeaseKind;
  } | null>(null);

  const [snackbarOpen, setSnackbarOpen] = useState(false);
  const [snackbarMessage, setSnackbarMessage] = useState('');
  const [snackbarSeverity, setSnackbarSeverity] = useState<'success' | 'error'>('success');

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
      const filter = statusFilter === 'ALL' ? undefined : { status: statusFilter };
      const [list, kinds] = await Promise.all([
        dynamicSecretsService.list(filter),
        catalog ? Promise.resolve(catalog) : dynamicSecretsService.kinds(),
      ]);
      setLeases(list);
      if (!catalog) setCatalog(kinds);
    } catch (e) {
      console.error(e);
      showError(t('dynamicSecrets.loadError', 'Failed to load leases'));
    } finally {
      setLoading(false);
    }
  }, [statusFilter, catalog, t]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const openIssue = () => {
    setForm({
      name: '',
      kind: 'token',
      backend_role: 'default',
      ttl_seconds: catalog?.ttl.default ?? 1800,
      note: '',
    });
    setIssueDialogOpen(true);
  };

  const handleIssue = async () => {
    if (!form.name.trim()) {
      showError(t('dynamicSecrets.nameRequired', 'Name is required'));
      return;
    }
    if (!form.backend_role.trim()) {
      showError(t('dynamicSecrets.roleRequired', 'Backend role is required'));
      return;
    }
    setIssuing(true);
    try {
      const r = await dynamicSecretsService.issue({
        name: form.name.trim(),
        kind: form.kind,
        backend_role: form.backend_role.trim(),
        ttl_seconds: form.ttl_seconds,
        note: form.note.trim() || null,
      });
      setIssueDialogOpen(false);
      setRevealedSecret({
        name: r.lease.name,
        secret: r.secret,
        expires_at: r.lease.expires_at,
        kind: r.lease.kind,
      });
      await refresh();
    } catch (e: unknown) {
      const detail = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      showError(detail || t('dynamicSecrets.issueError', 'Failed to issue lease'));
    } finally {
      setIssuing(false);
    }
  };

  const handleRevoke = async (lease: DynamicSecretLease) => {
    if (!globalThis.confirm(t('dynamicSecrets.confirmRevoke', 'Revoke "{{name}}" now?', { name: lease.name }))) {
      return;
    }
    try {
      await dynamicSecretsService.revoke(lease.id);
      showSuccess(t('dynamicSecrets.revoked', 'Lease revoked'));
      await refresh();
    } catch (e: unknown) {
      const detail = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      showError(detail || t('dynamicSecrets.revokeError', 'Failed to revoke'));
    }
  };

  const handleReconcile = async () => {
    try {
      const r = await dynamicSecretsService.reconcile();
      showSuccess(
        t('dynamicSecrets.reconciled', '{{count}} expired lease(s) marked', {
          count: r.transitioned_count,
        }),
      );
      await refresh();
    } catch (e: unknown) {
      const detail = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      showError(detail || t('dynamicSecrets.reconcileError', 'Reconcile failed'));
    }
  };

  const copySecret = async (s: string) => {
    try {
      await globalThis.navigator.clipboard.writeText(s);
      showSuccess(t('dynamicSecrets.copied', 'Secret copied to clipboard'));
    } catch (e) {
      console.error(e);
      showError(t('dynamicSecrets.copyError', 'Copy failed'));
    }
  };

  const _statusColor = (s: LeaseStatus): 'success' | 'default' | 'warning' | 'error' => {
    if (s === 'ACTIVE') return 'success';
    if (s === 'REVOKED') return 'default';
    if (s === 'EXPIRED') return 'warning';
    return 'error';
  };
  const statusChip = (s: LeaseStatus) => (
    <Chip size="small" color={_statusColor(s)} label={s} />
  );

  const renderLeasesContent = () => {
    if (loading) {
      return (
        <Box sx={{ display: 'flex', justifyContent: 'center', p: 3 }}>
          <CircularProgress />
        </Box>
      );
    }
    if (leases.length === 0) {
      return (
        <Typography color="text.secondary">
          {t('dynamicSecrets.empty', 'No leases match the current filter.')}
        </Typography>
      );
    }
    return (
      <Box sx={{ height: 480 }}>
        <DataGrid
          rows={leases}
          columns={columns}
          getRowId={(row) => row.id}
          disableRowSelectionOnClick
          density="compact"
        />
      </Box>
    );
  };

  const columns: GridColDef[] = [
    {
      field: 'name',
      headerName: t('dynamicSecrets.name', 'Name'),
      flex: 1,
      minWidth: 160,
    },
    {
      field: 'kind',
      headerName: t('dynamicSecrets.kind', 'Kind'),
      width: 120,
    },
    {
      field: 'backend_role',
      headerName: t('dynamicSecrets.role', 'Role'),
      width: 160,
    },
    {
      field: 'status',
      headerName: t('dynamicSecrets.status', 'Status'),
      width: 130,
      renderCell: (p: GridRenderCellParams<DynamicSecretLease>) => statusChip(p.row.status),
    },
    {
      field: 'issued_at',
      headerName: t('dynamicSecrets.issuedAt', 'Issued'),
      width: 170,
      valueGetter: (_v, row) => (row.issued_at ? formatUTCTimestamp(row.issued_at, '—') : '—'),
    },
    {
      field: 'expires_at',
      headerName: t('dynamicSecrets.expiresAt', 'Expires'),
      width: 170,
      valueGetter: (_v, row) => (row.expires_at ? formatUTCTimestamp(row.expires_at, '—') : '—'),
    },
    {
      field: 'actions',
      headerName: t('common.actions', 'Actions'),
      sortable: false,
      width: 100,
      renderCell: (p: GridRenderCellParams<DynamicSecretLease>) => (
        <Stack direction="row" spacing={0.5}>
          {p.row.status === 'ACTIVE' && (
            <Tooltip title={t('dynamicSecrets.revoke', 'Revoke')}>
              <IconButton size="small" onClick={() => handleRevoke(p.row)}>
                <BlockIcon fontSize="small" />
              </IconButton>
            </Tooltip>
          )}
        </Stack>
      ),
    },
  ];

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
      <Card>
        <CardHeader
          title={t('dynamicSecrets.title', 'Dynamic Secrets')}
          subheader={t(
            'dynamicSecrets.subtitle',
            'Short-lived credentials issued via OpenBAO/Vault that auto-expire',
          )}
          action={
            <Stack direction="row" spacing={1}>
              <Button
                variant="outlined"
                startIcon={<RefreshIcon />}
                onClick={handleReconcile}
              >
                {t('dynamicSecrets.reconcile', 'Reconcile')}
              </Button>
              <Button startIcon={<AddIcon />} variant="contained" onClick={openIssue}>
                {t('dynamicSecrets.issue', 'Issue Lease')}
              </Button>
            </Stack>
          }
        />
        <CardContent>
          <Stack spacing={2}>
            <FormControl size="small" sx={{ minWidth: 200 }}>
              <InputLabel>{t('dynamicSecrets.statusFilter', 'Status filter')}</InputLabel>
              <Select
                label={t('dynamicSecrets.statusFilter', 'Status filter')}
                value={statusFilter}
                onChange={(e) => setStatusFilter(e.target.value)}
              >
                {STATUS_FILTERS.map((s) => (
                  <MenuItem key={s} value={s}>
                    {s}
                  </MenuItem>
                ))}
              </Select>
            </FormControl>
            {renderLeasesContent()}
          </Stack>
        </CardContent>
      </Card>

      {/* Issue dialog */}
      <Dialog
        open={issueDialogOpen}
        onClose={() => setIssueDialogOpen(false)}
        maxWidth="sm"
        fullWidth
      >
        <DialogTitle>{t('dynamicSecrets.issueTitle', 'Issue New Lease')}</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <TextField
              label={t('dynamicSecrets.name', 'Name')}
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
              fullWidth
              required
            />
            <FormControl fullWidth>
              <InputLabel>{t('dynamicSecrets.kind', 'Kind')}</InputLabel>
              <Select
                label={t('dynamicSecrets.kind', 'Kind')}
                value={form.kind}
                onChange={(e) => setForm({ ...form, kind: e.target.value })}
              >
                {LEASE_KINDS.map((k) => (
                  <MenuItem key={k} value={k}>
                    {k}
                  </MenuItem>
                ))}
              </Select>
            </FormControl>
            <TextField
              label={t('dynamicSecrets.role', 'Backend Role')}
              value={form.backend_role}
              onChange={(e) => setForm({ ...form, backend_role: e.target.value })}
              fullWidth
              required
            />
            <TextField
              label={t('dynamicSecrets.ttl', 'TTL (seconds)')}
              type="number"
              value={form.ttl_seconds}
              onChange={(e) =>
                setForm({
                  ...form,
                  ttl_seconds: Math.max(
                    catalog?.ttl.min ?? 60,
                    Math.min(
                      catalog?.ttl.max ?? 86400,
                      Number.parseInt(e.target.value || '0', 10),
                    ),
                  ),
                })
              }
              slotProps={{
                htmlInput: {
                  min: catalog?.ttl.min ?? 60,
                  max: catalog?.ttl.max ?? 86400,
                },
              }}
              fullWidth
              helperText={t(
                'dynamicSecrets.ttlHelp',
                'Lease lifetime — between {{min}} and {{max}} seconds',
                {
                  min: catalog?.ttl.min ?? 60,
                  max: catalog?.ttl.max ?? 86400,
                },
              )}
            />
            <TextField
              label={t('dynamicSecrets.note', 'Note (optional)')}
              value={form.note}
              onChange={(e) => setForm({ ...form, note: e.target.value })}
              fullWidth
              multiline
              rows={2}
            />
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setIssueDialogOpen(false)}>
            {t('common.cancel', 'Cancel')}
          </Button>
          <Button
            onClick={handleIssue}
            variant="contained"
            disabled={issuing}
            startIcon={issuing ? <CircularProgress size={16} /> : null}
          >
            {t('dynamicSecrets.issue', 'Issue')}
          </Button>
        </DialogActions>
      </Dialog>

      {/* Reveal dialog (shown once) */}
      <Dialog
        open={!!revealedSecret}
        onClose={() => setRevealedSecret(null)}
        maxWidth="sm"
        fullWidth
      >
        <DialogTitle>
          {t('dynamicSecrets.revealTitle', 'Lease Issued — Copy Now')}
        </DialogTitle>
        <DialogContent>
          <Alert severity="warning" sx={{ mb: 2 }}>
            {t(
              'dynamicSecrets.revealWarning',
              'This is the only time the secret will be shown. Copy it now — there is no recovery once you close this dialog.',
            )}
          </Alert>
          {revealedSecret && (
            <Stack spacing={2}>
              <TextField
                label={t('dynamicSecrets.name', 'Name')}
                value={revealedSecret.name}
                fullWidth
                slotProps={{ input: { readOnly: true } }}
              />
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                <TextField
                  label={t('dynamicSecrets.secret', 'Secret value')}
                  value={revealedSecret.secret}
                  fullWidth
                  multiline
                  slotProps={{
                    input: {
                      readOnly: true,
                      sx: { fontFamily: 'monospace' },
                    },
                  }}
                  onFocus={(e) => e.target.select()}
                />
                <Tooltip title={t('dynamicSecrets.copy', 'Copy')}>
                  <IconButton onClick={() => copySecret(revealedSecret.secret)}>
                    <ContentCopyIcon />
                  </IconButton>
                </Tooltip>
              </Box>
              {revealedSecret.expires_at && (
                <Typography variant="body2" color="text.secondary">
                  {t('dynamicSecrets.expiresOn', 'Expires:')}{' '}
                  {formatUTCTimestamp(revealedSecret.expires_at, '—')}
                </Typography>
              )}
            </Stack>
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setRevealedSecret(null)} variant="contained">
            {t('common.close', 'Close')}
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

export default DynamicSecretsSettings;
