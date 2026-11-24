// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

/**
 * Four-eyes restore approval (ROADMAP 27.2, Enterprise backup_ops_engine):
 * the setting (off by default) and the restores waiting for a second person
 * with the restore role.  The requester can withdraw their own request but
 * never approve it.  Shown only where the engine is licensed.
 */

import React, { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import type { TFunction } from 'i18next';

import Alert from '@mui/material/Alert';
import Button from '@mui/material/Button';
import Chip from '@mui/material/Chip';
import FormControlLabel from '@mui/material/FormControlLabel';
import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import Switch from '@mui/material/Switch';
import Table from '@mui/material/Table';
import TableBody from '@mui/material/TableBody';
import TableCell from '@mui/material/TableCell';
import TableHead from '@mui/material/TableHead';
import TableRow from '@mui/material/TableRow';
import Typography from '@mui/material/Typography';

import { useModuleLicensed } from '../../hooks/useModuleLicensed';
import {
  FourEyes, RestoreRequest, approveRestore, getFourEyes, rejectRestore, setFourEyes, withdrawRestore,
} from '../../Services/backupFourEyes';
import { apiDetail, formatTime } from './backupLabels';

export const requestStatusLabel = (t: TFunction, status: string): string => {
  const labels: Record<string, string> = {
    pending: t('backups.approvals.pending', 'Waiting for approval'),
    approved: t('backups.approvals.approved', 'Approved and sent'),
    rejected: t('backups.approvals.rejected', 'Rejected'),
    withdrawn: t('backups.approvals.withdrawn', 'Withdrawn'),
    expired: t('backups.approvals.expired', 'Expired'),
  };
  return labels[status] ?? status;
};

const BackupApprovalsCard: React.FC<{
  canManage: boolean; canRestore: boolean; onChanged?: () => void;
}> = ({ canManage, canRestore, onChanged }) => {
  const { t } = useTranslation();
  const licensed = useModuleLicensed('backup_ops_engine');
  const [data, setData] = useState<FourEyes | null>(null);
  const [error, setError] = useState<string | null>(null);
  const me = localStorage.getItem('userid') ?? '';

  const load = useCallback(async () => {
    try {
      setData(await getFourEyes());
    } catch {
      setData(null);
    }
  }, []);
  useEffect(() => { if (licensed) void load(); }, [licensed, load]);

  const act = async (action: () => Promise<unknown>, failure: string) => {
    setError(null);
    try {
      await action();
      await load();
      onChanged?.();
    } catch (err) {
      setError(apiDetail(err, failure));
    }
  };

  if (!licensed || !data) return null;
  const shown = data.requests.filter((r) => r.status === 'pending' || data.enabled);
  const decide = (request: RestoreRequest) => {
    if (request.status !== 'pending') return null;
    if (request.requested_by === me) {
      return (
        <Button size="small" onClick={() => act(() => withdrawRestore(request.id),
          t('backups.approvals.withdrawFailed', 'The request could not be withdrawn.'))}>
          {t('backups.approvals.withdraw', 'Withdraw')}
        </Button>
      );
    }
    if (!canRestore) return null;
    return (
      <Stack direction="row" spacing={1}>
        <Button size="small" variant="contained" color="warning"
          onClick={() => act(() => approveRestore(request.id),
            t('backups.approvals.approveFailed', 'The restore could not be approved.'))}>
          {t('backups.approvals.approve', 'Approve and restore')}
        </Button>
        <Button size="small" onClick={() => act(() => rejectRestore(request.id, null),
          t('backups.approvals.rejectFailed', 'The request could not be rejected.'))}>
          {t('backups.approvals.reject', 'Reject')}
        </Button>
      </Stack>
    );
  };

  return (
    <Paper variant="outlined" sx={{ p: 2, mb: 3, overflowX: 'auto' }} data-testid="backup-approvals">
      <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 1 }}>
        <Typography variant="h6">{t('backups.approvals.title', 'Restores awaiting approval')}</Typography>
        <FormControlLabel
          control={<Switch checked={data.enabled} disabled={!canManage}
            onChange={(e) => act(() => setFourEyes(e.target.checked),
              t('backups.approvals.settingFailed', 'The setting could not be saved.'))} />}
          label={t('backups.approvals.setting', 'Restores over a host\'s own files need a second approver')} />
      </Stack>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
        {t('backups.approvals.help', 'A request no one approves within {{hours}} hours expires. Restores into staging and previews never wait.', { hours: data.ttl_hours })}
      </Typography>
      {error && <Alert severity="error" sx={{ mb: 1 }}>{error}</Alert>}
      {shown.length === 0 ? (
        <Typography variant="body2">{t('backups.approvals.none', 'No restore is waiting.')}</Typography>
      ) : (
        <Table size="small">
          <TableHead>
            <TableRow>
              <TableCell>{t('backups.approvals.host', 'Host')}</TableCell>
              <TableCell>{t('backups.approvals.what', 'What')}</TableCell>
              <TableCell>{t('backups.approvals.requested', 'Asked for by')}</TableCell>
              <TableCell>{t('backups.approvals.status', 'Status')}</TableCell>
              <TableCell />
            </TableRow>
          </TableHead>
          <TableBody>
            {shown.map((r) => (
              <TableRow key={r.id}>
                <TableCell>{r.kind === 'fleet_restore' ? t('backups.approvals.fleet', 'Fleet restore') : r.fqdn}</TableCell>
                <TableCell>
                  {r.kind === 'fleet_restore'
                    ? t('backups.approvals.fleetWhat', '"{{name}}" over the files of {{count}} hosts', { name: r.name ?? '', count: r.hosts ?? 0 })
                    : t('backups.approvals.paths', '{{paths}} from {{snapshot}}', { paths: r.include.join(', '), snapshot: r.snapshot })}
                  {r.packages && <Chip size="small" sx={{ ml: 1 }} label={t('backups.approvals.packages', 'with packages')} />}
                </TableCell>
                <TableCell>{r.requested_by} ({formatTime(r.requested_at)})</TableCell>
                <TableCell>
                  {requestStatusLabel(t, r.status)}
                  {r.decided_by && r.status !== 'pending' ? ` (${r.decided_by})` : ''}
                </TableCell>
                <TableCell>{decide(r)}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}
    </Paper>
  );
};

export default BackupApprovalsCard;
