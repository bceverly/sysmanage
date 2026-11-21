// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

/**
 * Restore readiness (ROADMAP 27.1, Enterprise backup_ops_engine): could each
 * host's backup be restored, how recent is it against its recovery point
 * objective, and how long would it take?  A host whose repository has not
 * been proven readable recently is "unproven", however recent its backups.
 * Shown only where the engine is licensed.
 */

import React, { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import type { TFunction } from 'i18next';

import Alert from '@mui/material/Alert';
import Button from '@mui/material/Button';
import Chip from '@mui/material/Chip';
import Dialog from '@mui/material/Dialog';
import DialogActions from '@mui/material/DialogActions';
import DialogContent from '@mui/material/DialogContent';
import DialogTitle from '@mui/material/DialogTitle';
import IconButton from '@mui/material/IconButton';
import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import Table from '@mui/material/Table';
import TableBody from '@mui/material/TableBody';
import TableCell from '@mui/material/TableCell';
import TableHead from '@mui/material/TableHead';
import TableRow from '@mui/material/TableRow';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import EditIcon from '@mui/icons-material/Edit';

import { useModuleLicensed } from '../../hooks/useModuleLicensed';
import {
  FleetReadiness, HostReadiness, READINESS_ORDER, ReadinessState, getReadiness, setRpo,
} from '../../Services/backupReadiness';
import { formatTime } from './backupLabels';

type ChipColor = 'default' | 'success' | 'warning' | 'error';

export const readinessLabel = (t: TFunction, state: ReadinessState): string => {
  const labels: Record<ReadinessState, string> = {
    never_backed_up: t('backups.readiness.never', 'Never backed up'),
    rpo_breached: t('backups.readiness.breached', 'Recovery point missed'),
    unproven: t('backups.readiness.unproven', 'Unproven'),
    ready: t('backups.readiness.ready', 'Ready'),
  };
  return labels[state];
};

const COLORS: Record<ReadinessState, ChipColor> = {
  never_backed_up: 'error', rpo_breached: 'error', unproven: 'warning', ready: 'success',
};

/** "about 8 min", "about 2.5 h" -- an expected restore time, never exact. */
export const formatDuration = (t: TFunction, seconds: number | null): string => {
  if (seconds === null) return t('backups.readiness.rtoUnknown', 'unknown');
  if (seconds < 90) return t('backups.readiness.aboutMinute', 'about a minute');
  if (seconds < 5400) {
    return t('backups.readiness.aboutMinutes', 'about {{n}} min', { n: Math.round(seconds / 60) });
  }
  return t('backups.readiness.aboutHours', 'about {{n}} h', { n: Math.round(seconds / 360) / 10 });
};

const basisLabel = (t: TFunction, basis: string | null): string => {
  switch (basis) {
    case 'restore': return t('backups.readiness.basisRestore', 'from a past restore');
    case 'verify': return t('backups.readiness.basisVerify', 'from a full-read verification');
    case 'capture': return t('backups.readiness.basisCapture', 'estimated from its backups');
    default: return '';
  }
};

const proofLabel = (t: TFunction, row: HostReadiness): string => {
  if (!row.proof) return t('backups.readiness.neverProven', 'never proven');
  const when = formatTime(row.proof.at);
  const how = row.proof.kind === 'drill'
    ? t('backups.readiness.drill', 'restore drill {{when}}', { when })
    : t('backups.readiness.verified', 'verified {{when}}', { when });
  return row.proof.fresh ? how : t('backups.readiness.stale', '{{how}} (too old)', { how });
};

function RpoDialog({ row, onClose, onSaved }: Readonly<{
  row: HostReadiness; onClose: () => void; onSaved: () => void;
}>) {
  const { t } = useTranslation();
  const [value, setValue] = useState(String(row.rpo.target_hours));
  const [error, setError] = useState<string | null>(null);
  const save = async (hours: number | null) => {
    try {
      await setRpo(row.host_id, hours);
      onSaved();
    } catch {
      setError(t('backups.readiness.saveFailed', 'The recovery point objective could not be saved.'));
    }
  };
  const hours = Number(value);
  const valid = Number.isInteger(hours) && hours >= 1 && hours <= 24 * 366;
  return (
    <Dialog open onClose={onClose}>
      <DialogTitle>{t('backups.readiness.rpoTitle', 'Recovery point objective for {{host}}', { host: row.fqdn })}</DialogTitle>
      <DialogContent>
        <Typography variant="body2" sx={{ mb: 2 }}>
          {t('backups.readiness.rpoHelp', 'The oldest its last good backup may be before it counts as missed. Leave it at the default, twice the backup interval, unless this host needs a tighter one.')}
        </Typography>
        <TextField type="number" label={t('backups.readiness.rpoHours', 'Hours')} value={value}
          onChange={(e) => setValue(e.target.value)} error={!valid} slotProps={{ htmlInput: { min: 1 } }} />
        {error && <Alert severity="error" sx={{ mt: 2 }}>{error}</Alert>}
      </DialogContent>
      <DialogActions>
        <Button onClick={() => save(null)}>{t('backups.readiness.rpoDefault', 'Use the default')}</Button>
        <Button onClick={onClose}>{t('common.cancel', 'Cancel')}</Button>
        <Button variant="contained" disabled={!valid} onClick={() => save(hours)}>{t('common.save', 'Save')}</Button>
      </DialogActions>
    </Dialog>
  );
}

const BackupReadinessCard: React.FC<{ canManage: boolean; refreshKey?: number }> = ({ canManage, refreshKey }) => {
  const { t } = useTranslation();
  const licensed = useModuleLicensed('backup_ops_engine');
  const [data, setData] = useState<FleetReadiness | null>(null);
  const [editing, setEditing] = useState<HostReadiness | null>(null);
  const [allShown, setAllShown] = useState(false);

  const load = useCallback(async () => {
    try {
      setData(await getReadiness());
    } catch {
      setData(null);
    }
  }, []);
  useEffect(() => { if (licensed) void load(); }, [licensed, load, refreshKey]);

  if (!licensed || !data || data.hosts.length === 0) return null;
  const rows = allShown ? data.hosts : data.hosts.filter((h) => h.state !== 'ready');
  return (
    <Paper variant="outlined" sx={{ p: 2, mb: 3, overflowX: 'auto' }} data-testid="backup-readiness">
      <Typography variant="h6" sx={{ mb: 1 }}>{t('backups.readiness.title', 'Restore readiness')}</Typography>
      <Stack direction="row" spacing={1} sx={{ mb: 2, flexWrap: 'wrap', rowGap: 1 }}>
        {READINESS_ORDER.filter((s) => data.counts[s]).map((s) => (
          <Chip key={s} color={COLORS[s]} variant="outlined" label={`${readinessLabel(t, s)}: ${data.counts[s]}`} />
        ))}
        <Chip variant={allShown ? 'filled' : 'outlined'} onClick={() => setAllShown((v) => !v)}
          label={allShown ? t('backups.readiness.onlyProblems', 'Only hosts needing a look') : t('backups.readiness.showAll', 'Show every host')} />
      </Stack>
      {rows.length === 0 ? (
        <Alert severity="success">{t('backups.readiness.allReady', 'Every host is ready: backed up within its objective and proven readable.')}</Alert>
      ) : (
        <Table size="small">
          <TableHead>
            <TableRow>
              <TableCell>{t('backups.readiness.host', 'Host')}</TableCell>
              <TableCell>{t('backups.readiness.state', 'Readiness')}</TableCell>
              <TableCell>{t('backups.readiness.rpo', 'Last good backup / objective')}</TableCell>
              <TableCell>{t('backups.readiness.rto', 'Expected restore time')}</TableCell>
              <TableCell>{t('backups.readiness.proof', 'Proof')}</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {rows.map((row) => (
              <TableRow key={row.policy_id}>
                <TableCell>{row.fqdn}</TableCell>
                <TableCell><Chip size="small" color={COLORS[row.state]} label={readinessLabel(t, row.state)} /></TableCell>
                <TableCell>
                  {row.rpo.age_hours === null
                    ? t('backups.readiness.noBackup', 'none / {{target}} h', { target: row.rpo.target_hours })
                    : t('backups.readiness.age', '{{age}} h ago / {{target}} h', { age: row.rpo.age_hours, target: row.rpo.target_hours })}
                  {canManage && (
                    <IconButton size="small" aria-label={t('backups.readiness.editRpo', 'Change the recovery point objective')}
                      onClick={() => setEditing(row)}><EditIcon fontSize="inherit" /></IconButton>
                  )}
                </TableCell>
                <TableCell title={basisLabel(t, row.rto.basis)}>{formatDuration(t, row.rto.seconds)}</TableCell>
                <TableCell>{proofLabel(t, row)}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}
      {editing && (
        <RpoDialog row={editing} onClose={() => setEditing(null)}
          onSaved={() => { setEditing(null); void load(); }} />
      )}
    </Paper>
  );
};

export default BackupReadinessCard;
