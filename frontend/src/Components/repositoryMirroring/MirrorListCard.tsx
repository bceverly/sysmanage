// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

import React, { useEffect, useState } from 'react';
import {
  Alert,
  Button,
  Card,
  CardContent,
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
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  TextField,
  Tooltip,
  Typography,
} from '@mui/material';
import AddIcon from '@mui/icons-material/Add';
import DeleteIcon from '@mui/icons-material/Delete';
import EditIcon from '@mui/icons-material/Edit';
import SyncIcon from '@mui/icons-material/Sync';
import CameraAltIcon from '@mui/icons-material/CameraAlt';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import ExpandLessIcon from '@mui/icons-material/ExpandLess';
import { useTranslation } from 'react-i18next';
import {
  createMirror,
  deleteMirror,
  listKnownVersions,
  MirrorKnownVersion,
  MirrorPlatform,
  MirrorPlatformConfig,
  MirrorRepository,
  MirrorRepositoryCreate,
  snapshotMirror,
  syncMirror,
  updateMirror,
} from '../../Services/repositoryMirroring';
import { EMPTY_DRAFT_FOR, isDraftValid } from './helpers';
import ActionStatusChip from './ActionStatusChip';
import ComponentsMultiSelect from './ComponentsMultiSelect';
import SnapshotsExpandRow from './SnapshotsExpandRow';

// ---------------------------------------------------------------------
// Mirror list card with Add/Edit dialog
// ---------------------------------------------------------------------

interface MirrorListCardProps {
  platform: MirrorPlatform;
  config: MirrorPlatformConfig;
  mirrors: MirrorRepository[];
  onChange: () => void;
}

const MirrorListCard: React.FC<MirrorListCardProps> = ({
  platform,
  config,
  mirrors,
  onChange,
}) => {
  const { t } = useTranslation();
  const [dialogOpen, setDialogOpen] = useState(false);
  const [draft, setDraft] = useState<MirrorRepositoryCreate>(EMPTY_DRAFT_FOR(platform));
  const [editingId, setEditingId] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [knownVersions, setKnownVersions] = useState<MirrorKnownVersion[]>([]);
  const [selectedVersionId, setSelectedVersionId] = useState<string>('');
  // Which mirror's snapshots expand-row is open.  A single Set rather
  // than a per-row boolean keeps state flat and lets us toggle by id.
  const [expandedSnapshots, setExpandedSnapshots] = useState<Set<string>>(() => new Set());
  const toggleSnapshots = (id: string) =>
    setExpandedSnapshots((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });

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
                {/* Expand chevron — narrow column so it doesn't steal layout. */}
                <TableCell sx={{ width: 32, p: 0 }} />
                <TableCell>{t('mirror.col.name', 'Name')}</TableCell>
                <TableCell>{t('mirror.col.osVersion', 'OS / Version')}</TableCell>
                <TableCell>{t('mirror.col.upstream', 'Upstream')}</TableCell>
                <TableCell>{t('mirror.col.cron', 'Cron')}</TableCell>
                {/* One column per actionable lifecycle, replacing the
                    single ambiguous Status column.  Sync/Snapshot/Restore
                    are the operator-triggered ones; integrity_check + gc
                    don't have UI buttons yet so they're collapsed into
                    the snapshot chip's hidden-state for now. */}
                <TableCell>{t('mirror.col.statusSync', 'Sync')}</TableCell>
                <TableCell>{t('mirror.col.statusSnapshot', 'Snapshot')}</TableCell>
                <TableCell>{t('mirror.col.statusRestore', 'Restore')}</TableCell>
                <TableCell>{t('mirror.col.actions', 'Actions')}</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {mirrors.map((m) => (
                <React.Fragment key={m.id}>
                <TableRow>
                  <TableCell sx={{ width: 32, p: 0 }}>
                    <Tooltip
                      title={
                        expandedSnapshots.has(m.id)
                          ? t('mirror.expand.collapse', 'Hide snapshots')
                          : t('mirror.expand.expand', 'Show snapshots')
                      }
                      arrow
                    >
                      <IconButton size="small" onClick={() => toggleSnapshots(m.id)}>
                        {expandedSnapshots.has(m.id) ? (
                          <ExpandLessIcon fontSize="small" />
                        ) : (
                          <ExpandMoreIcon fontSize="small" />
                        )}
                      </IconButton>
                    </Tooltip>
                  </TableCell>
                  <TableCell>{m.name}</TableCell>
                  <TableCell>{versionLabelFor(m)}</TableCell>
                  <TableCell sx={{ maxWidth: 300, overflow: 'hidden', textOverflow: 'ellipsis' }}>
                    {m.upstream_url}
                  </TableCell>
                  <TableCell>{m.sync_cron}</TableCell>
                  <TableCell>
                    <ActionStatusChip
                      label={t('mirror.chip.label.sync', 'sync')}
                      status={m.last_sync_status}
                      errorText={m.last_sync_error}
                      inFlightMessageId={m.last_sync_message_id}
                      at={m.last_sync_at}
                    />
                  </TableCell>
                  <TableCell>
                    <ActionStatusChip
                      label={t('mirror.chip.label.snapshot', 'snap')}
                      status={m.last_snapshot_status}
                      errorText={m.last_snapshot_error}
                      inFlightMessageId={m.last_snapshot_message_id}
                      at={m.last_snapshot_at}
                    />
                  </TableCell>
                  <TableCell>
                    <ActionStatusChip
                      label={t('mirror.chip.label.restore', 'restore')}
                      status={m.last_restore_status}
                      errorText={m.last_restore_error}
                      inFlightMessageId={m.last_restore_message_id}
                      at={m.last_restore_at}
                    />
                  </TableCell>
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
                <SnapshotsExpandRow
                  mirror={m}
                  colSpan={9}
                  expanded={expandedSnapshots.has(m.id)}
                  onRestoreDispatched={onChange}
                />
                </React.Fragment>
              ))}
              {mirrors.length === 0 && (
                <TableRow>
                  <TableCell colSpan={9} align="center">
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
              onChange={(e) => {
                // The backend uses ``name`` verbatim as a directory
                // segment under ``mirror_root_path`` and the engine
                // rejects anything outside ``[a-z0-9_-]`` with a 400
                // "invalid characters in path segment".  Filter at the
                // input layer so the user never gets that 400: spaces
                // and dots collapse to hyphens (the most common
                // freeform typing patterns), everything else outside
                // the safe class is dropped, and the result is
                // lowercased.
                const safe = e.target.value
                  .toLowerCase()
                  .replaceAll(/[\s.]+/g, '-')
                  .replaceAll(/[^a-z0-9_-]/g, '')
                  .replaceAll(/-+/g, '-');
                setDraft({ ...draft, name: safe });
              }}
              required
              fullWidth
              autoFocus
              helperText={t(
                'mirror.field.name_helper',
                'Lowercase letters, digits, hyphens, underscores. Spaces and dots become hyphens.',
              )}
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
          {/* Disable Save when any field the engine's
              ``validate_mirror_config`` would reject is empty.  This
              keeps the user from learning about required fields via a
              400 round-trip — mirrors the server-side rules exactly so
              a click that's enabled always corresponds to a server
              that'll accept it. */}
          <Button
            variant="contained"
            onClick={saveDialog}
            disabled={busy || !isDraftValid(draft)}
          >
            {busy ? t('mirror.saving', 'Saving…') : t('mirror.save', 'Save')}
          </Button>
        </DialogActions>
      </Dialog>
    </Card>
  );
};

export default MirrorListCard;
