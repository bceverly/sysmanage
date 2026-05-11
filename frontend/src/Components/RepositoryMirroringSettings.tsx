/**
 * Settings panel for the Pro+ Repository Mirroring feature.
 *
 * Phase 10.4.2 layout — tab strip per platform:
 *
 *     [ Linux ] [ FreeBSD ]
 *     ────────────────────────────────────────────────────
 *     <PlatformPanel> for the active tab:
 *       1. Platform-config card (host picker + filesystem
 *          + retention + bandwidth defaults)
 *       2. Mirror-tooling setup status card (Phase 10.4.1)
 *       3. Repository table for mirrors that hang off this
 *          platform's config + Add Mirror button
 *
 * If the active platform has no config yet, the panel shows an
 * empty-state "Configure {Platform} mirroring" form instead.
 *
 * The component is rendered from a Settings tab that's already
 * gated on ``isModuleLicensed('repository_mirroring_engine')`` —
 * we don't re-check inside.  All API calls 402 if the engine is
 * unlicensed; we surface those as inline error alerts.
 */

import React, { useEffect, useMemo, useState } from 'react';
import {
  Alert,
  Autocomplete,
  Box,
  Button,
  Card,
  CardContent,
  Checkbox,
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
  Stack,
  Tab,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Tabs,
  TextField,
  Typography,
} from '@mui/material';
import AddIcon from '@mui/icons-material/Add';
import DeleteIcon from '@mui/icons-material/Delete';
import EditIcon from '@mui/icons-material/Edit';
import SyncIcon from '@mui/icons-material/Sync';
import CameraAltIcon from '@mui/icons-material/CameraAlt';
import { useTranslation } from 'react-i18next';
import axiosInstance from '../Services/api';

import {
  createMirror,
  createPlatformConfig,
  deleteMirror,
  deletePlatformConfig,
  listKnownVersions,
  listMirrors,
  listPlatformConfigs,
  MirrorKnownVersion,
  MirrorPlatform,
  MirrorPlatformConfig,
  MirrorRepository,
  MirrorRepositoryCreate,
  snapshotMirror,
  syncMirror,
  updateMirror,
  updatePlatformConfig,
} from '../Services/repositoryMirroring';
import MirrorSetupStatusCard from './MirrorSetupStatusCard';

// Phase 10.4.3: each tab is one PM, so the package_manager dropdown
// drops out of the Add Mirror dialog — the platform === the PM.

// Match a host's reported platform/release strings against the
// distro family that natively runs the given PM.  Hosts that don't
// match are filtered out of the picker so an Ubuntu host doesn't
// show up under the RHEL/Fedora tab (where ``dnf`` mirroring would
// be meaningless).  We look at ``platform_release`` because it
// carries either a friendly distro name (``Ubuntu 26.04``) or the
// kernel uname (``5.15.0-...el9uek...``) — the ``.el`` substring
// is the canonical RHEL-family marker in kernel strings, which is
// how Linux distros tag their kernel package builds.
const hostMatchesPm = (
  host: { platform: string | null; platform_release?: string | null },
  pm: MirrorPlatform,
): boolean => {
  const platform = (host.platform || '').toLowerCase();
  const release = (host.platform_release || '').toLowerCase();
  if (pm === 'pkg') return platform === 'freebsd';
  if (platform !== 'linux') return false;
  if (pm === 'apt') return /\b(ubuntu|debian|mint|kali|raspbian|pop!_os|elementary)\b/.test(release);
  if (pm === 'dnf') {
    return (
      /\.el\d/.test(release) ||  // kernel uname tag, e.g. el9, el8
      /\.fc\d/.test(release) ||  // Fedora kernel tag
      /\b(rhel|red hat|fedora|oracle linux|rocky|alma|centos|amazon linux|amzn)\b/.test(release)
    );
  }
  if (pm === 'zypper') {
    return /\b(opensuse|suse|sled|sles)\b/.test(release);
  }
  return false;
};

interface HostSummary {
  id: string;
  fqdn: string;
  platform: string | null;
  platform_release: string | null;
}

const EMPTY_DRAFT_FOR = (
  pm: MirrorRepository['package_manager'],
): MirrorRepositoryCreate => ({
  name: '',
  package_manager: pm,
  upstream_url: '',
  host_id: '',
  bandwidth_cap_kbps: 0,
  sync_cron: '0 4 * * *',
  enabled: true,
});

const RepositoryMirroringSettings: React.FC = () => {
  const { t } = useTranslation();
  const [activePlatform, setActivePlatform] = useState<MirrorPlatform>('apt');
  const [configs, setConfigs] = useState<MirrorPlatformConfig[]>([]);
  const [mirrors, setMirrors] = useState<MirrorRepository[]>([]);
  const [hosts, setHosts] = useState<HostSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = async () => {
    setLoading(true);
    setError(null);
    try {
      const [c, m, h] = await Promise.all([
        listPlatformConfigs(),
        listMirrors(),
        axiosInstance.get<HostSummary[]>('/api/hosts').then((r) => r.data),
      ]);
      setConfigs(c);
      setMirrors(m);
      setHosts(h);
    } catch {
      setError(t('mirror.loadError', 'Could not load repository mirrors.'));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    refresh();
    // refresh is stable for the component lifetime; mount-only fetch
    // is intentional.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Auto-poll while any mirror has an in-flight sync/snapshot/restore
  // op (status == 'DISPATCHED').  Once every row is settled (SUCCESS,
  // FAILED, or NULL) the interval clears so we don't pin a backend
  // connection.  Re-arms automatically when the next op fires.
  useEffect(() => {
    const inflight = mirrors.some((m) => m.last_sync_status === 'DISPATCHED');
    if (!inflight) return;
    const handle = setInterval(() => {
      // Only refetch the mirror list (lightweight) rather than the
      // full configs+hosts+mirrors triple-load so the polling cost is
      // a single GET every 10s.
      listMirrors().then(setMirrors).catch(() => { /* keep last-known on error */ });
    }, 10000);
    return () => clearInterval(handle);
  }, [mirrors]);

  if (loading) {
    return (
      <Box sx={{ display: 'flex', justifyContent: 'center', p: 4 }}>
        <CircularProgress />
      </Box>
    );
  }

  return (
    <Box sx={{ p: 3 }}>
      {error && (
        <Alert severity="error" sx={{ mb: 2 }}>
          {error}
        </Alert>
      )}
      <Tabs
        value={activePlatform}
        onChange={(_, v) => setActivePlatform(v)}
        sx={{ borderBottom: 1, borderColor: 'divider', mb: 2 }}
      >
        <Tab value="apt" label={t('mirror.platform.apt', 'Ubuntu/Debian')} />
        <Tab value="dnf" label={t('mirror.platform.dnf', 'RHEL/Fedora')} />
        <Tab value="zypper" label={t('mirror.platform.zypper', 'openSUSE/SLES')} />
        <Tab value="pkg" label={t('mirror.platform.pkg', 'FreeBSD')} />
      </Tabs>
      <PlatformPanel
        platform={activePlatform}
        config={configs.find((c) => c.platform === activePlatform) ?? null}
        hosts={hosts}
        mirrors={mirrors}
        onChange={refresh}
      />
    </Box>
  );
};

// ---------------------------------------------------------------------
// Per-platform panel
// ---------------------------------------------------------------------

interface PlatformPanelProps {
  platform: MirrorPlatform;
  config: MirrorPlatformConfig | null;
  hosts: HostSummary[];
  mirrors: MirrorRepository[];
  onChange: () => void;
}

const PlatformPanel: React.FC<PlatformPanelProps> = ({
  platform,
  config,
  hosts,
  mirrors,
  onChange,
}) => {
  if (!config) {
    return <ConfigureEmptyState platform={platform} hosts={hosts} onCreated={onChange} />;
  }

  const platformMirrors = mirrors.filter((m) => m.platform_config_id === config.id);
  const hostName = hosts.find((h) => h.id === config.host_id)?.fqdn ?? config.host_id;

  return (
    <Stack spacing={2}>
      <MirrorSetupStatusCard
        hostId={config.host_id}
        hostFqdn={hostName}
        packageManager={platform}
      />
      <PlatformConfigCard
        config={config}
        hosts={hosts}
        onSaved={onChange}
        onRemoved={onChange}
        mirrorCount={platformMirrors.length}
      />
      <MirrorListCard
        platform={platform}
        config={config}
        mirrors={platformMirrors}
        onChange={onChange}
      />
    </Stack>
  );
};

// ---------------------------------------------------------------------
// Empty state — no platform config yet
// ---------------------------------------------------------------------

const ConfigureEmptyState: React.FC<{
  platform: MirrorPlatform;
  hosts: HostSummary[];
  onCreated: () => void;
}> = ({ platform, hosts, onCreated }) => {
  const { t } = useTranslation();
  const [hostId, setHostId] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const eligible = useMemo(
    () => hosts.filter((h) => hostMatchesPm(h, platform)),
    [hosts, platform],
  );

  const submit = async () => {
    if (!hostId) return;
    setBusy(true);
    setError(null);
    try {
      await createPlatformConfig({ platform, host_id: hostId });
      onCreated();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card variant="outlined">
      <CardContent>
        <Typography variant="h6">
          {t('mirror.configureTitle', 'Configure {{platform}} mirroring', {
            platform: ({
              apt: 'Ubuntu/Debian',
              dnf: 'RHEL/Fedora',
              zypper: 'openSUSE/SLES',
              pkg: 'FreeBSD',
            } as const)[platform],
          })}
        </Typography>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
          {t(
            'mirror.configureSubtitle',
            'Pick the host that will run this platform\'s mirror plans. Only hosts whose platform matches the tab are listed.',
          )}
        </Typography>
        {error && (
          <Alert severity="error" sx={{ mb: 2 }}>
            {error}
          </Alert>
        )}
        <Stack direction="row" spacing={2} alignItems="center">
          <Autocomplete
            sx={{ minWidth: 360 }}
            options={eligible}
            getOptionLabel={(o) => o.fqdn}
            value={eligible.find((h) => h.id === hostId) ?? null}
            onChange={(_, v) => setHostId(v?.id ?? null)}
            renderInput={(params) => (
              <TextField {...params} label={t('mirror.field.host', 'Mirror host')} />
            )}
          />
          <Button
            variant="contained"
            onClick={submit}
            disabled={!hostId || busy}
          >
            {busy
              ? t('mirror.saving', 'Saving…')
              : t('mirror.create', 'Create')}
          </Button>
        </Stack>
        {eligible.length === 0 && (
          <Typography variant="caption" color="text.secondary" sx={{ mt: 1, display: 'block' }}>
            {t(
              'mirror.noEligibleHosts',
              'No registered {{family}} hosts available — register one and refresh.',
              {
                family: ({
                  apt: 'Ubuntu/Debian',
                  dnf: 'RHEL/Fedora',
                  zypper: 'openSUSE/SLES',
                  pkg: 'FreeBSD',
                } as const)[platform],
              },
            )}
          </Typography>
        )}
      </CardContent>
    </Card>
  );
};

// ---------------------------------------------------------------------
// Platform config card (host + filesystem defaults for this platform)
// ---------------------------------------------------------------------

const PlatformConfigCard: React.FC<{
  config: MirrorPlatformConfig;
  hosts: HostSummary[];
  onSaved: () => void;
  onRemoved: () => void;
  mirrorCount: number;
}> = ({ config, hosts, onSaved, onRemoved, mirrorCount }) => {
  const { t } = useTranslation();
  const [draft, setDraft] = useState({ ...config });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => setDraft({ ...config }), [config]);

  const save = async () => {
    setBusy(true);
    setError(null);
    try {
      await updatePlatformConfig(config.id, {
        platform: draft.platform,
        host_id: draft.host_id,
        mirror_root_path: draft.mirror_root_path,
        integrity_check_cadence_hours: draft.integrity_check_cadence_hours,
        retention_window_days: draft.retention_window_days,
        default_bandwidth_cap_kbps: draft.default_bandwidth_cap_kbps,
        snapshot_count_to_keep: draft.snapshot_count_to_keep,
      });
      onSaved();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const removeConfig = async () => {
    if (mirrorCount > 0) {
      setError(
        t(
          'mirror.deleteConfigInUse',
          'Delete the {{n}} mirror(s) under this platform first.',
          { n: mirrorCount },
        ),
      );
      return;
    }
    if (
      !globalThis.confirm(
        t('mirror.deleteConfigConfirm', 'Remove this platform configuration?'),
      )
    )
      return;
    try {
      await deletePlatformConfig(config.id);
      onRemoved();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  const eligibleHosts = hosts.filter((h) => hostMatchesPm(h, config.platform));

  return (
    <Card variant="outlined">
      <CardContent>
        <Typography variant="h6" sx={{ mb: 1 }}>
          {t('mirror.platformSettings.title', 'Platform Settings')}
        </Typography>
        {error && (
          <Alert severity="error" sx={{ mb: 2 }}>
            {error}
          </Alert>
        )}
        <Stack spacing={2}>
          <Autocomplete
            options={eligibleHosts}
            getOptionLabel={(o) => o.fqdn}
            value={eligibleHosts.find((h) => h.id === draft.host_id) ?? null}
            onChange={(_, v) => setDraft({ ...draft, host_id: v?.id ?? '' })}
            renderInput={(params) => (
              <TextField {...params} label={t('mirror.field.host', 'Mirror host')} />
            )}
          />
          <TextField
            label={t('mirror.field.mirrorRootPath', 'Mirror root path')}
            value={draft.mirror_root_path}
            onChange={(e) => setDraft({ ...draft, mirror_root_path: e.target.value })}
            fullWidth
          />
          <Stack direction="row" spacing={2}>
            <TextField
              type="number"
              label={t('mirror.field.retention', 'Retention (days)')}
              value={draft.retention_window_days}
              onChange={(e) =>
                setDraft({
                  ...draft,
                  retention_window_days: Number(e.target.value || 0),
                })
              }
              sx={{ flex: 1 }}
            />
            <TextField
              type="number"
              label={t('mirror.field.integrityCadence', 'Integrity check (hrs)')}
              value={draft.integrity_check_cadence_hours}
              onChange={(e) =>
                setDraft({
                  ...draft,
                  integrity_check_cadence_hours: Number(e.target.value || 0),
                })
              }
              sx={{ flex: 1 }}
            />
            <TextField
              type="number"
              label={t('mirror.field.bandwidthCap', 'Default cap (kbps, 0=off)')}
              value={draft.default_bandwidth_cap_kbps}
              onChange={(e) =>
                setDraft({
                  ...draft,
                  default_bandwidth_cap_kbps: Number(e.target.value || 0),
                })
              }
              sx={{ flex: 1 }}
            />
            <TextField
              type="number"
              label={t('mirror.field.snapshotKeep', 'Snapshots to keep')}
              value={draft.snapshot_count_to_keep}
              onChange={(e) =>
                setDraft({
                  ...draft,
                  snapshot_count_to_keep: Number(e.target.value || 0),
                })
              }
              sx={{ flex: 1 }}
            />
          </Stack>
          <Stack direction="row" spacing={1} justifyContent="flex-end">
            <Button color="error" onClick={removeConfig} disabled={busy}>
              {t('mirror.deletePlatform', 'Remove platform')}
            </Button>
            <Button variant="contained" onClick={save} disabled={busy}>
              {busy
                ? t('mirror.saving', 'Saving…')
                : t('mirror.save', 'Save')}
            </Button>
          </Stack>
        </Stack>
      </CardContent>
    </Card>
  );
};

// ---------------------------------------------------------------------
// APT components multi-select (Phase 10.4.4)
// ---------------------------------------------------------------------
//
// Keyed off the catalog entry's ``os_family`` so Ubuntu mirrors show
// Ubuntu-specific components and Debian mirrors show Debian-specific
// components.  When no catalog row is selected yet, we fall back to
// the union of common values so the operator isn't blocked.

const COMPONENTS_BY_FAMILY: Record<string, string[]> = {
  ubuntu: ['main', 'restricted', 'universe', 'multiverse'],
  debian: ['main', 'contrib', 'non-free', 'non-free-firmware'],
};
const COMPONENTS_FALLBACK = [
  'main', 'restricted', 'universe', 'multiverse',
  'contrib', 'non-free', 'non-free-firmware',
];

const ComponentsMultiSelect: React.FC<{
  osFamily: string | undefined;
  value: string[];
  onChange: (next: string[]) => void;
}> = ({ osFamily, value, onChange }) => {
  const { t } = useTranslation();
  const options = (osFamily && COMPONENTS_BY_FAMILY[osFamily]) || COMPONENTS_FALLBACK;
  return (
    <FormControl fullWidth required>
      <InputLabel id="apt-components-label">
        {t('mirror.field.components', 'Components')}
      </InputLabel>
      <Select
        labelId="apt-components-label"
        label={t('mirror.field.components', 'Components')}
        multiple
        value={value}
        onChange={(e) => {
          const v = e.target.value;
          onChange(typeof v === 'string' ? v.split(',') : v);
        }}
        renderValue={(selected: string[]) => selected.join(' ')}
      >
        {options.map((c) => (
          <MenuItem key={c} value={c}>
            <Checkbox checked={value.includes(c)} />
            {c}
          </MenuItem>
        ))}
      </Select>
    </FormControl>
  );
};

// ---------------------------------------------------------------------
// Mirror list card with Add/Edit dialog
// ---------------------------------------------------------------------

const MirrorListCard: React.FC<{
  platform: MirrorPlatform;
  config: MirrorPlatformConfig;
  mirrors: MirrorRepository[];
  onChange: () => void;
}> = ({ platform, config, mirrors, onChange }) => {
  const { t } = useTranslation();
  const [dialogOpen, setDialogOpen] = useState(false);
  const [draft, setDraft] = useState<MirrorRepositoryCreate>(EMPTY_DRAFT_FOR(platform));
  const [editingId, setEditingId] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [knownVersions, setKnownVersions] = useState<MirrorKnownVersion[]>([]);
  const [selectedVersionId, setSelectedVersionId] = useState<string>('');

  // Load the catalog on mount + whenever the platform changes — used
  // both by the Add/Edit dialog dropdown AND by the table to resolve
  // each row's known_version_id into a friendly OS/version label.
  useEffect(() => {
    listKnownVersions(platform).then(setKnownVersions).catch(() => {
      /* if the catalog fails to load we fall back to suite/repoid/etc. */
    });
  }, [platform]);

  const versionLabelFor = (m: MirrorRepository): string => {
    if (m.known_version_id) {
      const kv = knownVersions.find((v) => v.id === m.known_version_id);
      if (kv) return kv.label;
    }
    // Legacy free-text rows (created before the dropdown landed) —
    // fall back to whatever per-PM identifier the row carries.
    return m.suite || m.repoid || m.repo_alias || m.release || '—';
  };

  const applyVersionToDraft = (versionId: string) => {
    setSelectedVersionId(versionId);
    const kv = knownVersions.find((v) => v.id === versionId);
    if (!kv) return;
    setDraft({
      ...draft,
      upstream_url: kv.default_upstream_url,
      suite: kv.default_suite ?? undefined,
      repoid: kv.default_repoid ?? undefined,
      repo_alias: kv.default_repo_alias ?? undefined,
      release: kv.default_release ?? undefined,
      known_version_id: kv.id,
    });
  };

  const openCreate = () => {
    setDraft({ ...EMPTY_DRAFT_FOR(platform), host_id: config.host_id });
    setEditingId(null);
    setSelectedVersionId('');
    setError(null);
    setDialogOpen(true);
  };

  const openEdit = (m: MirrorRepository) => {
    setDraft({
      name: m.name,
      package_manager: m.package_manager,
      upstream_url: m.upstream_url,
      host_id: m.host_id,
      suite: m.suite ?? undefined,
      components: m.components ?? undefined,
      architectures: m.architectures ?? undefined,
      repoid: m.repoid ?? undefined,
      gpgkey_url: m.gpgkey_url ?? undefined,
      repo_alias: m.repo_alias ?? undefined,
      release: m.release ?? undefined,
      signing_key_url: m.signing_key_url ?? undefined,
      bandwidth_cap_kbps: m.bandwidth_cap_kbps,
      sync_cron: m.sync_cron,
      network_tier: m.network_tier ?? undefined,
      enabled: m.enabled,
      known_version_id: m.known_version_id ?? undefined,
    });
    setEditingId(m.id);
    setSelectedVersionId(m.known_version_id ?? '');
    setError(null);
    setDialogOpen(true);
  };

  const saveDialog = async () => {
    setBusy(true);
    setError(null);
    try {
      if (editingId) {
        await updateMirror(editingId, draft);
      } else {
        await createMirror({ ...draft, host_id: config.host_id });
      }
      setDialogOpen(false);
      onChange();
    } catch (e: unknown) {
      setError(
        e instanceof Error
          ? e.message
          : t('mirror.saveError', 'Could not save mirror — check the form.'),
      );
    } finally {
      setBusy(false);
    }
  };

  const handleAction = async (
    fn: (id: string) => Promise<unknown>,
    id: string,
    errKey: string,
  ) => {
    try {
      await fn(id);
      onChange();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : t(errKey));
    }
  };

  return (
    <Card variant="outlined">
      <CardContent>
        <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 1 }}>
          <Typography variant="h6">
            {t('mirror.listTitle', 'Mirror Repositories')}
          </Typography>
          <Button startIcon={<AddIcon />} variant="contained" size="small" onClick={openCreate}>
            {t('mirror.add', 'Add Mirror')}
          </Button>
        </Stack>
        {error && (
          <Alert severity="error" sx={{ mb: 2 }} onClose={() => setError(null)}>
            {error}
          </Alert>
        )}
        <TableContainer>
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>{t('mirror.col.name', 'Name')}</TableCell>
                <TableCell>{t('mirror.col.osVersion', 'OS / Version')}</TableCell>
                <TableCell>{t('mirror.col.upstream', 'Upstream')}</TableCell>
                <TableCell>{t('mirror.col.cron', 'Cron')}</TableCell>
                <TableCell>{t('mirror.col.lastSync', 'Last sync')}</TableCell>
                <TableCell>{t('mirror.col.status', 'Status')}</TableCell>
                <TableCell>{t('mirror.col.actions', 'Actions')}</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {mirrors.map((m) => (
                <TableRow key={m.id}>
                  <TableCell>{m.name}</TableCell>
                  <TableCell>{versionLabelFor(m)}</TableCell>
                  <TableCell sx={{ maxWidth: 300, overflow: 'hidden', textOverflow: 'ellipsis' }}>
                    {m.upstream_url}
                  </TableCell>
                  <TableCell>{m.sync_cron}</TableCell>
                  <TableCell>{m.last_sync_at ? new Date(m.last_sync_at).toLocaleString() : '—'}</TableCell>
                  <TableCell>{m.last_sync_status ?? '—'}</TableCell>
                  <TableCell>
                    <IconButton size="small" title={t('mirror.action.sync', 'Sync now')}
                      onClick={() => handleAction(syncMirror, m.id, 'mirror.syncError')}>
                      <SyncIcon fontSize="small" />
                    </IconButton>
                    <IconButton size="small" title={t('mirror.action.snapshot', 'Snapshot')}
                      onClick={() => handleAction(snapshotMirror, m.id, 'mirror.snapshotError')}>
                      <CameraAltIcon fontSize="small" />
                    </IconButton>
                    <IconButton size="small" title={t('mirror.action.edit', 'Edit')} onClick={() => openEdit(m)}>
                      <EditIcon fontSize="small" />
                    </IconButton>
                    <IconButton
                      size="small"
                      title={t('mirror.action.delete', 'Delete')}
                      onClick={() => {
                        if (globalThis.confirm(t('mirror.deleteConfirm', 'Delete this mirror?'))) {
                          handleAction(deleteMirror, m.id, 'mirror.deleteError');
                        }
                      }}
                    >
                      <DeleteIcon fontSize="small" />
                    </IconButton>
                  </TableCell>
                </TableRow>
              ))}
              {mirrors.length === 0 && (
                <TableRow>
                  <TableCell colSpan={7} align="center">
                    <Typography variant="body2" color="text.secondary">
                      {t('mirror.empty', 'No mirrors configured for this platform yet.')}
                    </Typography>
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </TableContainer>
      </CardContent>
      <Dialog open={dialogOpen} onClose={() => setDialogOpen(false)} maxWidth="sm" fullWidth>
        <DialogTitle>
          {editingId ? t('mirror.editTitle', 'Edit Mirror') : t('mirror.addTitle', 'Add Mirror')}
        </DialogTitle>
        <DialogContent sx={{ pt: 4 }}>
          {/* The first TextField gets an explicit top margin so its
              floating label has unconditional clearance from the
              DialogTitle.  ``pt: 4`` on DialogContent alone isn't
              always enough — MUI's outlined label is positioned
              absolutely and can clip against an ``overflow-y: auto``
              parent on tight viewports. */}
          <Stack spacing={2} sx={{ mt: 1 }}>
            <TextField
              label={t('mirror.field.name', 'Name (used as on-disk subdir)')}
              value={draft.name}
              onChange={(e) => setDraft({ ...draft, name: e.target.value })}
              required
              fullWidth
              autoFocus
            />
            {/* Phase 10.4.4 — version dropdown sourced from the
                pre-populated ``mirror_known_version`` catalog.  Picking
                a row auto-fills upstream_url + the per-PM identifier
                (suite/repoid/repo_alias/release) so we can't fat-finger
                a wrong value.  The catalog is admin-extensible via
                future migrations rather than auto-discovery, keeping
                the supported set reviewable in code. */}
            <FormControl fullWidth required>
              <InputLabel id="known-version-label">
                {t('mirror.field.version', 'Version')}
              </InputLabel>
              <Select
                labelId="known-version-label"
                label={t('mirror.field.version', 'Version')}
                value={selectedVersionId}
                onChange={(e) => applyVersionToDraft(e.target.value)}
              >
                {knownVersions.map((v) => (
                  <MenuItem key={v.id} value={v.id}>
                    {v.label}
                  </MenuItem>
                ))}
              </Select>
            </FormControl>
            <TextField
              label={t('mirror.field.upstream', 'Upstream URL')}
              helperText={t(
                'mirror.field.upstreamHelp',
                'Auto-filled from the version above; override only if you have a region-specific mirror to point at.',
              )}
              value={draft.upstream_url}
              onChange={(e) => setDraft({ ...draft, upstream_url: e.target.value })}
              required
              fullWidth
            />

            {/* Optional per-PM extras that aren't version identifiers
                — components (apt), GPG/signing key URLs.  These stay
                free-text because they're per-deployment, not per-version. */}
            {draft.package_manager === 'apt' && (
              <>
                <ComponentsMultiSelect
                  osFamily={
                    knownVersions.find((v) => v.id === selectedVersionId)?.os_family
                  }
                  value={(draft.components ?? '').split(/\s+/).filter(Boolean)}
                  onChange={(arr) =>
                    setDraft({
                      ...draft,
                      components: arr.length ? arr.join(' ') : undefined,
                    })
                  }
                />
                <TextField
                  label={t('mirror.field.signingKey', 'Signing key URL (optional)')}
                  value={draft.signing_key_url ?? ''}
                  onChange={(e) =>
                    setDraft({ ...draft, signing_key_url: e.target.value || undefined })
                  }
                  fullWidth
                />
              </>
            )}
            {draft.package_manager === 'dnf' && (
              <TextField
                label={t('mirror.field.gpgkey', 'GPG key URL (optional)')}
                value={draft.gpgkey_url ?? ''}
                onChange={(e) =>
                  setDraft({ ...draft, gpgkey_url: e.target.value || undefined })
                }
                fullWidth
              />
            )}
            {draft.package_manager === 'zypper' && (
              <TextField
                label={t('mirror.field.signingKey', 'Signing key URL (optional)')}
                value={draft.signing_key_url ?? ''}
                onChange={(e) =>
                  setDraft({ ...draft, signing_key_url: e.target.value || undefined })
                }
                fullWidth
              />
            )}

            <TextField
              label={t('mirror.field.cron', 'Sync cron')}
              value={draft.sync_cron}
              onChange={(e) => setDraft({ ...draft, sync_cron: e.target.value })}
              fullWidth
            />
            <TextField
              type="number"
              label={t('mirror.field.cap', 'Bandwidth cap (kbps, 0=off)')}
              value={draft.bandwidth_cap_kbps}
              onChange={(e) =>
                setDraft({ ...draft, bandwidth_cap_kbps: Number(e.target.value || 0) })
              }
              fullWidth
            />
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setDialogOpen(false)}>{t('mirror.cancel', 'Cancel')}</Button>
          <Button variant="contained" onClick={saveDialog} disabled={busy}>
            {busy ? t('mirror.saving', 'Saving…') : t('mirror.save', 'Save')}
          </Button>
        </DialogActions>
      </Dialog>
    </Card>
  );
};

export default RepositoryMirroringSettings;
