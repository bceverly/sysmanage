// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

import React, { useState, useEffect, useCallback } from 'react';
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  CardHeader,
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
  Edit as EditIcon,
  Pause as PauseIcon,
  PlayArrow as PlayArrowIcon,
  PlayCircleOutline as ResumeIcon,
} from '@mui/icons-material';
import { useTranslation } from 'react-i18next';
import axiosInstance from '../Services/api';
import {
  UpgradeProfile,
  upgradeProfilesService,
} from '../Services/upgradeProfiles';
import { formatUTCTimestamp } from '../utils/dateUtils';
import { autoUpdatesService } from '../Services/autoUpdates';
import AutoUpdatesPanel from './AutoUpdates/AutoUpdatesPanel';
import AutomaticFields from './AutoUpdates/AutomaticFields';

interface TagOption {
  id: string;
  name: string;
}

interface HostOption {
  id: string;
  fqdn: string;
}

// 26.1: the automatic fields, blank for a new profile.
const AUTO_DEFAULTS = {
  auto_apply: false,
  reboot_mode: 'never' as 'never' | 'when_needed',
  excluded_packages: '',
  require_backup_hours: '' as number | '',
  host_ids: [] as string[],
};

const PACKAGE_MANAGER_OPTIONS = [
  'apt',
  'dnf',
  'yum',
  'zypper',
  'pacman',
  'apk',
  'pkg',
  'snap',
  'flatpak',
  'brew',
  'winget',
  'chocolatey',
];

const UpgradeProfilesSettings: React.FC = () => {
  const { t } = useTranslation();

  const [profiles, setProfiles] = useState<UpgradeProfile[]>([]);
  const [tags, setTags] = useState<TagOption[]>([]);
  const [hosts, setHosts] = useState<HostOption[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [snackbarOpen, setSnackbarOpen] = useState(false);
  const [snackbarMessage, setSnackbarMessage] = useState('');
  const [snackbarSeverity, setSnackbarSeverity] = useState<'success' | 'error'>('success');

  const [dialogOpen, setDialogOpen] = useState(false);
  const [editing, setEditing] = useState<UpgradeProfile | null>(null);
  const [form, setForm] = useState({
    name: '',
    description: '',
    cron: '0 3 * * *',
    enabled: true,
    security_only: false,
    package_managers: [] as string[],
    staggered_window_min: 0,
    tag_id: '',
    ...AUTO_DEFAULTS,
  });

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
      const [p, tagResp, hostResp] = await Promise.all([
        upgradeProfilesService.list(),
        axiosInstance.get('/api/v1/tags'),
        axiosInstance.get('/api/v1/hosts').catch(() => ({ data: [] })),
      ]);
      setProfiles(p);
      setTags(tagResp.data || []);
      setHosts(Array.isArray(hostResp.data) ? hostResp.data : []);
    } catch (e) {
      console.error(e);
      setError(t('upgradeProfiles.loadError', 'Failed to load update profiles'));
    } finally {
      setLoading(false);
    }
  }, [t]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const openCreate = () => {
    setEditing(null);
    setForm({
      name: '',
      description: '',
      cron: '0 3 * * *',
      enabled: true,
      security_only: false,
      package_managers: [],
      staggered_window_min: 0,
      tag_id: '',
      ...AUTO_DEFAULTS,
    });
    setDialogOpen(true);
  };
  const openEdit = (p: UpgradeProfile) => {
    setEditing(p);
    setForm({
      name: p.name,
      description: p.description ?? '',
      cron: p.cron,
      enabled: p.enabled,
      security_only: p.security_only,
      package_managers: p.package_managers ?? [],
      staggered_window_min: p.staggered_window_min,
      tag_id: p.tag_id ?? '',
      auto_apply: Boolean(p.auto_apply),
      reboot_mode: p.reboot_mode ?? 'never',
      excluded_packages: p.excluded_packages ?? '',
      require_backup_hours: p.require_backup_hours ?? '',
      host_ids: p.host_ids ?? [],
    });
    setDialogOpen(true);
  };

  const handleSave = async () => {
    if (!form.name.trim()) {
      showError(t('upgradeProfiles.nameRequired', 'Name is required'));
      return;
    }
    if (!form.cron.trim()) {
      showError(t('upgradeProfiles.cronRequired', 'Cron schedule is required'));
      return;
    }
    if (form.staggered_window_min < 0 || form.staggered_window_min > 720) {
      showError(t('upgradeProfiles.windowRange', 'Staggered window must be between 0 and 720 minutes'));
      return;
    }
    const payload = {
      name: form.name.trim(),
      description: form.description.trim() || null,
      cron: form.cron.trim(),
      enabled: form.enabled,
      security_only: form.security_only,
      package_managers: form.package_managers.length ? form.package_managers : null,
      staggered_window_min: form.staggered_window_min,
      tag_id: form.tag_id || null,
      auto_apply: form.auto_apply,
      reboot_mode: form.reboot_mode,
      excluded_packages: form.excluded_packages.trim() || null,
      require_backup_hours: form.require_backup_hours === '' ? (editing ? 0 : null) : form.require_backup_hours,
      host_ids: form.host_ids,
    };
    try {
      if (editing) {
        await upgradeProfilesService.update(editing.id, payload);
        showSuccess(t('upgradeProfiles.updated', 'Update profile saved'));
      } else {
        await upgradeProfilesService.create(payload);
        showSuccess(t('upgradeProfiles.created', 'Update profile created'));
      }
      setDialogOpen(false);
      await refresh();
    } catch (e: unknown) {
      const detail = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      showError(detail || t('upgradeProfiles.saveError', 'Failed to save update profile'));
    }
  };

  const handleDelete = async (p: UpgradeProfile) => {
    if (!globalThis.confirm(t('upgradeProfiles.confirmDelete', 'Delete update profile "{{name}}"?', { name: p.name }))) {
      return;
    }
    try {
      await upgradeProfilesService.remove(p.id);
      showSuccess(t('upgradeProfiles.deleted', 'Update profile deleted'));
      await refresh();
    } catch (e: unknown) {
      const detail = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      showError(detail || t('upgradeProfiles.deleteError', 'Failed to delete update profile'));
    }
  };

  const handleTrigger = async (p: UpgradeProfile) => {
    if (!globalThis.confirm(t('upgradeProfiles.confirmTrigger', 'Trigger "{{name}}" now? Updates will dispatch to matching hosts.', { name: p.name }))) {
      return;
    }
    try {
      const r = await upgradeProfilesService.trigger(p.id);
      showSuccess(
        t('upgradeProfiles.ranNow', 'Updating {{queued}}, skipped {{skipped}}, nothing to do on {{nothing}}', {
          queued: r.queued,
          skipped: r.skipped,
          nothing: r.nothing,
        }),
      );
      await refresh();
    } catch (e: unknown) {
      const detail = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      showError(detail || t('upgradeProfiles.triggerError', 'Failed to trigger profile'));
    }
  };

  const handleHold = async (p: UpgradeProfile) => {
    let reason: string | undefined;
    if (!p.held) {
      reason =
        globalThis.prompt(t('upgradeProfiles.holdReason', 'Why hold "{{name}}"?', { name: p.name })) ??
        undefined;
      if (!reason?.trim()) return;
    }
    try {
      await autoUpdatesService.holdProfile(p.id, !p.held, reason);
      await refresh();
    } catch (e: unknown) {
      const detail = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      showError(detail || t('upgradeProfiles.saveError', 'Failed to save update profile'));
    }
  };

  const tagNameById = new Map<string, string>();
  tags.forEach((tag) => tagNameById.set(tag.id, tag.name));

  const columns: GridColDef[] = [
    {
      field: 'name',
      headerName: t('upgradeProfiles.name', 'Name'),
      flex: 1,
      minWidth: 160,
    },
    {
      field: 'enabled',
      headerName: t('upgradeProfiles.enabled', 'Enabled'),
      width: 110,
      renderCell: (params: GridRenderCellParams<UpgradeProfile>) =>
        params.row.enabled ? (
          <Chip size="small" color="success" label={t('common.yes', 'Yes')} />
        ) : (
          <Chip size="small" label={t('common.no', 'No')} />
        ),
    },
    {
      field: 'auto_apply',
      headerName: t('upgradeProfiles.automatic', 'Automatic'),
      width: 120,
      renderCell: (params: GridRenderCellParams<UpgradeProfile>) => {
        if (!params.row.auto_apply) return <Chip size="small" label={t('common.no', 'No')} />;
        return params.row.held ? (
          <Tooltip title={params.row.hold_reason ?? ''}>
            <Chip size="small" color="warning" label={t('upgradeProfiles.held', 'On hold')} />
          </Tooltip>
        ) : (
          <Chip size="small" color="success" label={t('common.yes', 'Yes')} />
        );
      },
    },
    {
      field: 'cron',
      headerName: t('upgradeProfiles.cron', 'Cron Schedule'),
      width: 160,
    },
    {
      field: 'security_only',
      headerName: t('upgradeProfiles.securityOnly', 'Security Updates Only'),
      width: 130,
      renderCell: (params: GridRenderCellParams<UpgradeProfile>) =>
        params.row.security_only ? (
          <Chip size="small" color="warning" label={t('common.yes', 'Yes')} />
        ) : (
          <Chip size="small" label={t('common.no', 'No')} />
        ),
    },
    {
      field: 'staggered_window_min',
      headerName: t('upgradeProfiles.window', 'Staggered Window (minutes)'),
      width: 130,
    },
    {
      field: 'tag_id',
      headerName: t('upgradeProfiles.tag', 'Tag'),
      width: 140,
      valueGetter: (_v, row) => {
        if (row.host_ids?.length) {
          return t('upgradeProfiles.listedHosts', '{{count}} listed host(s)', { count: row.host_ids.length });
        }
        return row.tag_id ? (tagNameById.get(row.tag_id) || row.tag_id) : t('upgradeProfiles.allHosts', 'All Hosts');
      },
    },
    {
      field: 'last_run',
      headerName: t('upgradeProfiles.lastRun', 'Last Run'),
      width: 170,
      valueGetter: (_v, row) =>
        row.last_run ? formatUTCTimestamp(row.last_run, '--') : '--',
    },
    {
      field: 'next_run',
      headerName: t('upgradeProfiles.nextRun', 'Next Run'),
      width: 170,
      valueGetter: (_v, row) =>
        row.next_run ? formatUTCTimestamp(row.next_run, '--') : '--',
    },
    {
      field: 'last_status',
      headerName: t('upgradeProfiles.lastStatus', 'Last Status'),
      width: 130,
      valueGetter: (_v, row) => row.last_status || '--',
    },
    {
      field: 'actions',
      headerName: t('common.actions', 'Actions'),
      sortable: false,
      width: 200,
      renderCell: (params: GridRenderCellParams<UpgradeProfile>) => (
        <Stack direction="row" spacing={0.5}>
          {params.row.auto_apply && (
            <Tooltip
              title={
                params.row.held
                  ? t('upgradeProfiles.release', 'Release the hold')
                  : t('upgradeProfiles.hold', 'Hold this policy')
              }
            >
              <IconButton size="small" onClick={() => void handleHold(params.row)}>
                {params.row.held ? <ResumeIcon fontSize="small" /> : <PauseIcon fontSize="small" />}
              </IconButton>
            </Tooltip>
          )}
          <Tooltip title={t('upgradeProfiles.trigger', 'Trigger Now')}>
            <IconButton size="small" color="primary" onClick={() => handleTrigger(params.row)}>
              <PlayArrowIcon fontSize="small" />
            </IconButton>
          </Tooltip>
          <Tooltip title={t('common.edit', 'Edit')}>
            <IconButton size="small" onClick={() => openEdit(params.row)}>
              <EditIcon fontSize="small" />
            </IconButton>
          </Tooltip>
          <Tooltip title={t('common.delete', 'Delete')}>
            <IconButton size="small" onClick={() => handleDelete(params.row)}>
              <DeleteIcon fontSize="small" />
            </IconButton>
          </Tooltip>
        </Stack>
      ),
    },
  ];

  const renderProfilesContent = () => {
    if (loading) {
      return (
        <Box sx={{ display: 'flex', justifyContent: 'center', p: 3 }}>
          <CircularProgress />
        </Box>
      );
    }
    if (profiles.length === 0) {
      return (
        <Typography color="text.secondary">
          {t('upgradeProfiles.empty', 'No update profiles defined yet.')}
        </Typography>
      );
    }
    return (
      <Box sx={{ height: 480 }}>
        <DataGrid
          rows={profiles}
          columns={columns}
          getRowId={(row) => row.id}
          disableRowSelectionOnClick
          density="compact"
        />
      </Box>
    );
  };

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
      {error && <Alert severity="error">{error}</Alert>}

      <AutoUpdatesPanel />

      <Card>
        <CardHeader
          title={t('upgradeProfiles.title', 'Update Profiles')}
          subheader={t(
            'upgradeProfiles.subtitle',
            'Schedule recurring fleet updates with cron, security-only, and staggered rollout',
          )}
          action={
            <Button startIcon={<AddIcon />} variant="contained" onClick={openCreate}>
              {t('upgradeProfiles.add', 'Add Profile')}
            </Button>
          }
        />
        <CardContent>{renderProfilesContent()}</CardContent>
      </Card>

      <Dialog open={dialogOpen} onClose={() => setDialogOpen(false)} maxWidth="sm" fullWidth>
        <DialogTitle>
          {editing
            ? t('upgradeProfiles.edit', 'Edit Update Profile')
            : t('upgradeProfiles.addDialogTitle', 'Add Update Profile')}
        </DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <TextField
              label={t('upgradeProfiles.name', 'Name')}
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
              fullWidth
              required
            />
            <TextField
              label={t('upgradeProfiles.description', 'Description')}
              value={form.description}
              onChange={(e) => setForm({ ...form, description: e.target.value })}
              fullWidth
              multiline
              rows={2}
            />
            <TextField
              label={t('upgradeProfiles.cron', 'Cron Schedule')}
              value={form.cron}
              onChange={(e) => setForm({ ...form, cron: e.target.value })}
              fullWidth
              helperText={t(
                'upgradeProfiles.cronHelp',
                'POSIX cron -- minute hour day-of-month month day-of-week',
              )}
              required
            />
            <FormControlLabel
              control={
                <Checkbox
                  checked={form.enabled}
                  onChange={(e) => setForm({ ...form, enabled: e.target.checked })}
                />
              }
              label={t('upgradeProfiles.enabled', 'Enabled')}
            />
            <FormControlLabel
              control={
                <Checkbox
                  checked={form.security_only}
                  onChange={(e) => setForm({ ...form, security_only: e.target.checked })}
                />
              }
              label={t('upgradeProfiles.securityOnly', 'Security Updates Only')}
            />
            <TextField
              label={t('upgradeProfiles.window', 'Staggered Window (minutes)')}
              type="number"
              value={form.staggered_window_min}
              onChange={(e) =>
                setForm({
                  ...form,
                  staggered_window_min: Math.max(
                    0,
                    Math.min(720, Number.parseInt(e.target.value || '0', 10)),
                  ),
                })
              }
              fullWidth
              slotProps={{ htmlInput: { min: 0, max: 720 } }}
              helperText={t(
                'upgradeProfiles.windowHelp',
                'Spread agent dispatches over this many minutes (0-720)',
              )}
            />
            <FormControl fullWidth>
              <InputLabel>{t('upgradeProfiles.tag', 'Tag')}</InputLabel>
              <Select
                multiple={false}
                label={t('upgradeProfiles.tag', 'Tag')}
                value={form.tag_id}
                onChange={(e) => setForm({ ...form, tag_id: e.target.value })}
              >
                <MenuItem value="">
                  <em>{t('upgradeProfiles.allHosts', 'All Hosts')}</em>
                </MenuItem>
                {tags.map((tag) => (
                  <MenuItem key={tag.id} value={tag.id}>
                    {tag.name}
                  </MenuItem>
                ))}
              </Select>
            </FormControl>
            <FormControl fullWidth>
              <InputLabel>{t('upgradeProfiles.packageManagers', 'Package Managers')}</InputLabel>
              <Select
                multiple
                label={t('upgradeProfiles.packageManagers', 'Package Managers')}
                value={form.package_managers}
                onChange={(e) =>
                  setForm({
                    ...form,
                    package_managers:
                      typeof e.target.value === 'string'
                        ? e.target.value.split(',')
                        : e.target.value,
                  })
                }
                renderValue={(selected) => (selected as readonly string[]).join(', ')}
              >
                {PACKAGE_MANAGER_OPTIONS.map((pm) => (
                  <MenuItem key={pm} value={pm}>
                    <Checkbox checked={form.package_managers.includes(pm)} />
                    {pm}
                  </MenuItem>
                ))}
              </Select>
            </FormControl>
            <AutomaticFields form={form} setForm={setForm} hosts={hosts} />
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setDialogOpen(false)}>
            {t('common.cancel', 'Cancel')}
          </Button>
          <Button onClick={handleSave} variant="contained">
            {t('common.save', 'Save')}
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

export default UpgradeProfilesSettings;
