// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

/**
 * Fleet restores (ROADMAP 27.2, Enterprise backup_ops_engine): one restore
 * asked of many hosts -- the same paths on each, from each host's own newest
 * snapshot or its newest taken before a moment -- released a few hosts at a
 * time.  The jobs, each host's outcome, and Cancel.  Shown only where the
 * engine is licensed, to people with the Restore Files role.
 */

import React, { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import type { TFunction } from 'i18next';

import Alert from '@mui/material/Alert';
import Autocomplete from '@mui/material/Autocomplete';
import Button from '@mui/material/Button';
import Checkbox from '@mui/material/Checkbox';
import Chip from '@mui/material/Chip';
import Dialog from '@mui/material/Dialog';
import DialogActions from '@mui/material/DialogActions';
import DialogContent from '@mui/material/DialogContent';
import DialogTitle from '@mui/material/DialogTitle';
import FormControlLabel from '@mui/material/FormControlLabel';
import MenuItem from '@mui/material/MenuItem';
import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import Table from '@mui/material/Table';
import TableBody from '@mui/material/TableBody';
import TableCell from '@mui/material/TableCell';
import TableHead from '@mui/material/TableHead';
import TableRow from '@mui/material/TableRow';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';

import { useModuleLicensed } from '../../hooks/useModuleLicensed';
import {
  FleetRestore,
  cancelFleetRestore,
  createFleetRestore,
  getFleetRestore,
  listFleetRestores,
} from '../../Services/backupFleetRestore';
import { apiDetail, formatTime } from './backupLabels';

interface HostOption {
  host_id: string;
  fqdn: string;
}

const lines = (text: string): string[] =>
  text.split('\n').map((l) => l.trim()).filter(Boolean);

export const jobStatusLabel = (t: TFunction, status: string): string => {
  switch (status) {
    case 'awaiting_approval': return t('backups.fleet.status.awaiting', 'Awaiting approval');
    case 'running': return t('backups.fleet.status.running', 'Running');
    case 'completed': return t('backups.fleet.status.completed', 'Completed');
    case 'canceled': return t('backups.fleet.status.canceled', 'Canceled');
    case 'rejected': return t('backups.fleet.status.rejected', 'Not approved');
    default: return status;
  }
};

export const hostStatusLabel = (t: TFunction, status: string): string => {
  switch (status) {
    case 'waiting': return t('backups.fleet.host.waiting', 'Waiting');
    case 'running': return t('backups.fleet.host.running', 'Restoring');
    case 'ok': return t('backups.fleet.host.ok', 'Restored');
    case 'failed': return t('backups.fleet.host.failed', 'Failed');
    case 'skipped': return t('backups.fleet.host.skipped', 'Skipped');
    case 'canceled': return t('backups.fleet.host.canceled', 'Canceled');
    default: return status;
  }
};

const hostColor = (status: string): 'success' | 'error' | 'warning' | 'default' | 'info' => {
  if (status === 'ok') return 'success';
  if (status === 'failed') return 'error';
  if (status === 'skipped') return 'warning';
  if (status === 'running') return 'info';
  return 'default';
};

const NewFleetRestoreDialog: React.FC<{
  hosts: HostOption[];
  onClose: () => void;
  onCreated: () => void;
}> = ({ hosts, onClose, onCreated }) => {
  const { t } = useTranslation();
  const [name, setName] = useState('');
  const [chosen, setChosen] = useState<HostOption[]>([]);
  const [include, setInclude] = useState('');
  const [exclude, setExclude] = useState('');
  const [before, setBefore] = useState('');
  const [where, setWhere] = useState<'staging' | 'in_place'>('staging');
  const [confirmInPlace, setConfirmInPlace] = useState(false);
  const [preview, setPreview] = useState(false);
  const [unsigned, setUnsigned] = useState(false);
  const [concurrency, setConcurrency] = useState(5);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const inPlace = where === 'in_place';
  const ready = name.trim() && chosen.length > 0 && lines(include).length > 0
    && (!inPlace || preview || confirmInPlace);

  const create = async () => {
    setBusy(true);
    setError(null);
    try {
      await createFleetRestore({
        name: name.trim(),
        host_ids: chosen.map((h) => h.host_id),
        include: lines(include),
        exclude: lines(exclude),
        before: before ? new Date(before).toISOString() : null,
        in_place: inPlace,
        acknowledge_in_place: inPlace && confirmInPlace,
        dry_run: preview,
        acknowledge_unsigned: unsigned,
        concurrency,
      });
      onCreated();
    } catch (err) {
      setError(apiDetail(err, t('backups.fleet.createFailed', 'The fleet restore could not be started.')));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog open onClose={onClose} fullWidth maxWidth="sm">
      <DialogTitle>{t('backups.fleet.newTitle', 'Restore the same paths on many hosts')}</DialogTitle>
      <DialogContent>
        <Typography variant="body2" sx={{ mb: 2 }}>
          {t('backups.fleet.help', 'Each host restores from its own snapshot: its newest, or its newest taken before the time you give -- the last good one before an incident. A few hosts restore at a time, so the storage host is never overwhelmed.')}
        </Typography>
        <Stack spacing={2}>
          <TextField label={t('backups.fleet.name', 'Name')} value={name} onChange={(e) => setName(e.target.value)}
            slotProps={{ htmlInput: { maxLength: 255 } }} />
          <Autocomplete multiple options={hosts} value={chosen} getOptionLabel={(h) => h.fqdn}
            isOptionEqualToValue={(a, b) => a.host_id === b.host_id}
            onChange={(_e, value) => setChosen(value)}
            renderInput={(params) => <TextField {...params} label={t('backups.fleet.hosts', 'Hosts')} />} />
          <TextField label={t('backups.fleet.include', 'Paths to restore, one per line')} value={include}
            onChange={(e) => setInclude(e.target.value)} multiline minRows={2} placeholder="/etc/nginx" />
          <TextField label={t('backups.fleet.exclude', 'Paths to leave out, one per line (optional)')} value={exclude}
            onChange={(e) => setExclude(e.target.value)} multiline minRows={1} />
          <TextField type="datetime-local" label={t('backups.fleet.before', 'From the newest snapshot before (optional)')}
            value={before} onChange={(e) => setBefore(e.target.value)} slotProps={{ inputLabel: { shrink: true } }} />
          <TextField select label={t('backups.fleet.where', 'Restore to')} value={where}
            onChange={(e) => setWhere(e.target.value as 'staging' | 'in_place')}>
            <MenuItem value="staging">{t('backups.fleet.staging', 'A staging folder on each host')}</MenuItem>
            <MenuItem value="in_place">{t('backups.fleet.inPlace', "Over each host's own files")}</MenuItem>
          </TextField>
          {inPlace && !preview && (
            <FormControlLabel control={<Checkbox checked={confirmInPlace} onChange={(e) => setConfirmInPlace(e.target.checked)} />}
              label={t('backups.fleet.confirmInPlace', "I understand each host's files at these paths will be replaced")} />
          )}
          <FormControlLabel control={<Checkbox checked={preview} onChange={(e) => setPreview(e.target.checked)} />}
            label={t('backups.fleet.preview', 'Preview only: list what would be restored, change nothing')} />
          <FormControlLabel control={<Checkbox checked={unsigned} onChange={(e) => setUnsigned(e.target.checked)} />}
            label={t('backups.fleet.unsigned', 'Restore from unsigned snapshots too')} />
          <TextField type="number" label={t('backups.fleet.concurrency', 'Hosts at a time')} value={concurrency}
            onChange={(e) => setConcurrency(Math.max(1, Math.min(50, Number(e.target.value) || 1)))}
            slotProps={{ htmlInput: { min: 1, max: 50 } }} />
        </Stack>
        {error && <Alert severity="error" sx={{ mt: 2 }}>{error}</Alert>}
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>{t('common.cancel', 'Cancel')}</Button>
        <Button variant="contained" onClick={create} disabled={!ready || busy}>
          {t('backups.fleet.start', 'Start the fleet restore')}
        </Button>
      </DialogActions>
    </Dialog>
  );
};

const FleetRestoreDetail: React.FC<{ id: string; onClose: () => void }> = ({ id, onClose }) => {
  const { t } = useTranslation();
  const [job, setJob] = useState<FleetRestore | null>(null);
  useEffect(() => {
    getFleetRestore(id).then(setJob).catch(() => setJob(null));
  }, [id]);
  return (
    <Dialog open onClose={onClose} fullWidth maxWidth="md">
      <DialogTitle>{job?.name ?? ''}</DialogTitle>
      <DialogContent>
        {job && (
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>{t('backups.fleet.host.host', 'Host')}</TableCell>
                <TableCell>{t('backups.fleet.host.state', 'State')}</TableCell>
                <TableCell>{t('backups.fleet.host.snapshot', 'Snapshot')}</TableCell>
                <TableCell>{t('backups.fleet.host.note', 'Note')}</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {(job.targets ?? []).map((h) => (
                <TableRow key={h.host_id}>
                  <TableCell>{h.fqdn ?? h.host_id}</TableCell>
                  <TableCell><Chip size="small" color={hostColor(h.status)} label={hostStatusLabel(t, h.status)} /></TableCell>
                  <TableCell>{h.snapshot ?? '--'}</TableCell>
                  <TableCell>{h.message ?? ''}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>{t('common.close', 'Close')}</Button>
      </DialogActions>
    </Dialog>
  );
};

const BackupFleetRestoresCard: React.FC<{ canRestore: boolean; hosts: HostOption[]; refreshKey?: number }> = ({
  canRestore, hosts, refreshKey,
}) => {
  const { t } = useTranslation();
  const licensed = useModuleLicensed('backup_ops_engine');
  const [jobs, setJobs] = useState<FleetRestore[] | null>(null);
  const [creating, setCreating] = useState(false);
  const [showing, setShowing] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setJobs(await listFleetRestores());
    } catch {
      setJobs(null);
    }
  }, []);
  useEffect(() => { if (licensed && canRestore) void load(); }, [licensed, canRestore, load, refreshKey]);

  if (!licensed || !canRestore || jobs === null) return null;
  const cancel = async (id: string) => {
    setError(null);
    try {
      await cancelFleetRestore(id);
      await load();
    } catch (err) {
      setError(apiDetail(err, t('backups.fleet.cancelFailed', 'The fleet restore could not be canceled.')));
    }
  };
  return (
    <Paper variant="outlined" sx={{ p: 2, mb: 3, overflowX: 'auto' }} data-testid="backup-fleet-restores">
      <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 1 }}>
        <Typography variant="h6">{t('backups.fleet.cardTitle', 'Fleet restores')}</Typography>
        <Button size="small" variant="outlined" onClick={() => setCreating(true)} disabled={hosts.length === 0}>
          {t('backups.fleet.new', 'New fleet restore')}
        </Button>
      </Stack>
      {error && <Alert severity="error" sx={{ mb: 1 }}>{error}</Alert>}
      {jobs.length === 0 ? (
        <Typography variant="body2" color="text.secondary">
          {t('backups.fleet.none', 'No fleet restores yet.')}
        </Typography>
      ) : (
        <Table size="small">
          <TableHead>
            <TableRow>
              <TableCell>{t('backups.fleet.name', 'Name')}</TableCell>
              <TableCell>{t('backups.fleet.state', 'State')}</TableCell>
              <TableCell>{t('backups.fleet.progress', 'Hosts')}</TableCell>
              <TableCell>{t('backups.fleet.asked', 'Asked for')}</TableCell>
              <TableCell />
            </TableRow>
          </TableHead>
          <TableBody>
            {jobs.map((j) => (
              <TableRow key={j.id}>
                <TableCell>{j.name}</TableCell>
                <TableCell>{jobStatusLabel(t, j.status)}</TableCell>
                <TableCell>
                  <Stack direction="row" spacing={0.5} sx={{ flexWrap: 'wrap', rowGap: 0.5 }}>
                    {Object.entries(j.counts).map(([status, n]) => (
                      <Chip key={status} size="small" color={hostColor(status)}
                        label={`${hostStatusLabel(t, status)}: ${n}`} />
                    ))}
                  </Stack>
                </TableCell>
                <TableCell>{j.created_by}, {formatTime(j.created_at)}</TableCell>
                <TableCell align="right">
                  <Button size="small" onClick={() => setShowing(j.id)}>{t('backups.fleet.details', 'Hosts')}</Button>
                  {(j.status === 'running' || j.status === 'awaiting_approval') && (
                    <Button size="small" color="warning" onClick={() => cancel(j.id)}>
                      {t('backups.fleet.cancel', 'Cancel')}
                    </Button>
                  )}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}
      {creating && (
        <NewFleetRestoreDialog hosts={hosts} onClose={() => setCreating(false)}
          onCreated={() => { setCreating(false); void load(); }} />
      )}
      {showing && <FleetRestoreDetail id={showing} onClose={() => setShowing(null)} />}
    </Paper>
  );
};

export default BackupFleetRestoresCard;
