// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

/**
 * Legal hold (ROADMAP 27.2, Enterprise backup_ops_engine): place a hold on
 * one of a host's snapshots (with whose hold it is and why), and the holds in
 * force with Release.  Every prune keeps a held snapshot until it is
 * released.  Shown only where the engine is licensed.
 */

import React, { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';

import Alert from '@mui/material/Alert';
import Button from '@mui/material/Button';
import Dialog from '@mui/material/Dialog';
import DialogActions from '@mui/material/DialogActions';
import DialogContent from '@mui/material/DialogContent';
import DialogTitle from '@mui/material/DialogTitle';
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
import { BackupSnapshot, getSnapshots } from '../../Services/backups';
import { LegalHold, getLegalHolds, placeLegalHold, releaseLegalHold } from '../../Services/backupLegalHold';
import { apiDetail, formatTime } from './backupLabels';

/** "Legal hold" on a host's backup card: pick a snapshot, say whose and why. */
export const LegalHoldButton: React.FC<{ hostId: string; fqdn: string; onPlaced?: () => void }> = ({
  hostId, fqdn, onPlaced,
}) => {
  const { t } = useTranslation();
  const licensed = useModuleLicensed('backup_ops_engine');
  const [open, setOpen] = useState(false);
  const [snapshots, setSnapshots] = useState<BackupSnapshot[]>([]);
  const [snapshot, setSnapshot] = useState('');
  const [owner, setOwner] = useState('');
  const [reason, setReason] = useState('');
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    getSnapshots(hostId).then((found) => {
      setSnapshots(found);
      setSnapshot(found[0]?.name ?? '');
    }).catch(() => setSnapshots([]));
  }, [open, hostId]);

  if (!licensed) return null;
  const place = async () => {
    setError(null);
    try {
      await placeLegalHold(hostId, snapshot, owner.trim(), reason.trim());
      setOpen(false);
      onPlaced?.();
    } catch (err) {
      setError(apiDetail(err, t('backups.hold.placeFailed', 'The hold could not be placed.')));
    }
  };
  return (
    <>
      <Button size="small" onClick={() => setOpen(true)}>{t('backups.hold.button', 'Legal hold')}</Button>
      {open && (
        <Dialog open onClose={() => setOpen(false)} fullWidth maxWidth="sm">
          <DialogTitle>{t('backups.hold.title', 'Place a legal hold on a snapshot of {{host}}', { host: fqdn })}</DialogTitle>
          <DialogContent>
            <Typography variant="body2" sx={{ mb: 2 }}>
              {t('backups.hold.help', 'Every prune keeps a held snapshot, whatever the retention rules say, until the hold is released.')}
            </Typography>
            <Stack spacing={2}>
              <TextField select label={t('backups.hold.snapshot', 'Snapshot')} value={snapshot}
                onChange={(e) => setSnapshot(e.target.value)}>
                {snapshots.map((s) => (
                  <MenuItem key={s.name} value={s.name}>{s.name} ({formatTime(s.created_at)})</MenuItem>
                ))}
              </TextField>
              <TextField label={t('backups.hold.owner', 'Whose hold (a case, a matter, a person)')} value={owner}
                onChange={(e) => setOwner(e.target.value)} inputProps={{ maxLength: 255 }} />
              <TextField label={t('backups.hold.reason', 'Why it is held')} value={reason} multiline minRows={2}
                onChange={(e) => setReason(e.target.value)} inputProps={{ maxLength: 1000 }} />
            </Stack>
            {error && <Alert severity="error" sx={{ mt: 2 }}>{error}</Alert>}
          </DialogContent>
          <DialogActions>
            <Button onClick={() => setOpen(false)}>{t('common.cancel', 'Cancel')}</Button>
            <Button variant="contained" onClick={place}
              disabled={!snapshot || !owner.trim() || !reason.trim()}>
              {t('backups.hold.place', 'Place the hold')}
            </Button>
          </DialogActions>
        </Dialog>
      )}
    </>
  );
};

/** The holds in force, and the latest released, with Release. */
const BackupLegalHoldsCard: React.FC<{ canManage: boolean; refreshKey?: number }> = ({ canManage, refreshKey }) => {
  const { t } = useTranslation();
  const licensed = useModuleLicensed('backup_ops_engine');
  const [holds, setHolds] = useState<LegalHold[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setHolds(await getLegalHolds());
    } catch {
      setHolds(null);
    }
  }, []);
  useEffect(() => { if (licensed) void load(); }, [licensed, load, refreshKey]);

  if (!licensed || !holds || holds.length === 0) return null;
  const release = async (id: string) => {
    setError(null);
    try {
      await releaseLegalHold(id);
      await load();
    } catch (err) {
      setError(apiDetail(err, t('backups.hold.releaseFailed', 'The hold could not be released.')));
    }
  };
  return (
    <Paper variant="outlined" sx={{ p: 2, mb: 3, overflowX: 'auto' }} data-testid="backup-legal-holds">
      <Typography variant="h6" sx={{ mb: 1 }}>{t('backups.hold.cardTitle', 'Legal holds')}</Typography>
      {error && <Alert severity="error" sx={{ mb: 1 }}>{error}</Alert>}
      <Table size="small">
        <TableHead>
          <TableRow>
            <TableCell>{t('backups.hold.host', 'Host')}</TableCell>
            <TableCell>{t('backups.hold.snapshot', 'Snapshot')}</TableCell>
            <TableCell>{t('backups.hold.ownerShort', 'Whose')}</TableCell>
            <TableCell>{t('backups.hold.reasonShort', 'Why')}</TableCell>
            <TableCell>{t('backups.hold.placed', 'Placed')}</TableCell>
            <TableCell />
          </TableRow>
        </TableHead>
        <TableBody>
          {holds.map((h) => (
            <TableRow key={h.id}>
              <TableCell>{h.fqdn}</TableCell>
              <TableCell>{h.snapshot}</TableCell>
              <TableCell>{h.owner}</TableCell>
              <TableCell>{h.reason}</TableCell>
              <TableCell>{h.placed_by} ({formatTime(h.placed_at)})</TableCell>
              <TableCell>
                {h.released_at
                  ? t('backups.hold.released', 'Released by {{who}} {{when}}', { who: h.released_by, when: formatTime(h.released_at) })
                  : canManage && (
                    <Button size="small" onClick={() => release(h.id)}>{t('backups.hold.release', 'Release')}</Button>
                  )}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </Paper>
  );
};

export default BackupLegalHoldsCard;
