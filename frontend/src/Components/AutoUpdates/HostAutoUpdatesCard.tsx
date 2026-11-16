// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

// A host's automatic updates (ROADMAP 26.1, Enterprise): the policy it
// follows and why, its opt-out, and its automatic runs beside the manual
// history.  Renders nothing without the Enterprise engine (402).

import React, { useCallback, useEffect, useState } from 'react';
import {
  Alert,
  Box,
  Card,
  CardContent,
  CardHeader,
  Chip,
  FormControlLabel,
  Stack,
  Switch,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  Typography,
} from '@mui/material';
import { useTranslation } from 'react-i18next';
import { autoUpdatesService, type HostAutoUpdates } from '../../Services/autoUpdates';
import { formatUTCTimestamp } from '../../utils/dateUtils';
import {
  packageReasonLabel,
  policyRuleLabel,
  rebootLabel,
  runStatusColor,
  runStatusLabel,
  skipReasonLabel,
} from './autoUpdateLabels';

interface Props {
  hostId: string;
  canManage: boolean;
}

const HostAutoUpdatesCard: React.FC<Props> = ({ hostId, canManage }) => {
  const { t } = useTranslation();
  const [data, setData] = useState<HostAutoUpdates | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setData(await autoUpdatesService.host(hostId));
    } catch {
      setData(null); // no Enterprise engine, or no access: show nothing
    }
  }, [hostId]);

  useEffect(() => {
    void load();
  }, [load]);

  if (data === null) return null;

  const toggleOptOut = async (optOut: boolean) => {
    let reason: string | undefined;
    if (optOut) {
      reason =
        globalThis.prompt(
          t('autoUpdates.optOutReason', 'Why must this host never be updated automatically?'),
        ) ?? undefined;
      if (!reason?.trim()) return;
    }
    try {
      await autoUpdatesService.optOut(hostId, optOut, reason);
      setError(null);
      await load();
    } catch {
      setError(t('autoUpdates.saveError', 'Could not save the change'));
    }
  };

  const describePolicy = () => {
    if (data.opt_out) {
      return t('autoUpdates.optedOut', 'Never updated automatically: {{reason}}', {
        reason: data.opt_out_reason ?? '',
      });
    }
    if (!data.policy) {
      return t('autoUpdates.noPolicy', 'No automatic update policy covers this host.');
    }
    return t('autoUpdates.followsPolicy', 'Follows "{{name}}": {{rule}}.', {
      name: data.policy.name,
      rule: policyRuleLabel(t, data.policy.rule),
    });
  };

  return (
    <Card sx={{ mb: 2 }}>
      <CardHeader
        title={t('autoUpdates.hostTitle', 'Automatic updates')}
        action={
          <FormControlLabel
            control={
              <Switch
                checked={data.opt_out}
                disabled={!canManage}
                onChange={(e) => void toggleOptOut(e.target.checked)}
              />
            }
            label={t('autoUpdates.optOut', 'Never update automatically')}
          />
        }
      />
      <CardContent>
        {error && <Alert severity="error" sx={{ mb: 1 }}>{error}</Alert>}
        {data.hold_all && (
          <Alert severity="warning" sx={{ mb: 1 }}>
            {t('autoUpdates.allHeld', 'Every automatic update policy is on hold.')}
          </Alert>
        )}
        <Typography variant="body2" sx={{ mb: 2 }}>{describePolicy()}</Typography>
        {data.runs.length > 0 && (
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>{t('autoUpdates.when', 'When')}</TableCell>
                <TableCell>{t('autoUpdates.policy', 'Policy')}</TableCell>
                <TableCell>{t('autoUpdates.result', 'Result')}</TableCell>
                <TableCell>{t('autoUpdates.details', 'Details')}</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {data.runs.map((run) => (
                <TableRow key={run.id}>
                  <TableCell>{formatUTCTimestamp(run.queued_at ?? '', '--')}</TableCell>
                  <TableCell>{run.profile_name}</TableCell>
                  <TableCell>
                    <Stack direction="row" spacing={0.5} sx={{ flexWrap: 'wrap' }}>
                      <Chip
                        size="small"
                        color={runStatusColor(run.status)}
                        label={runStatusLabel(t, run.status)}
                      />
                      {['queued', 'back', 'not_back'].includes(run.reboot_status) && (
                        <Chip
                          size="small"
                          color={run.reboot_status === 'not_back' ? 'error' : 'default'}
                          label={rebootLabel(t, run.reboot_status)}
                        />
                      )}
                    </Stack>
                  </TableCell>
                  <TableCell>
                    <Box sx={{ fontSize: '0.85em' }}>
                      {run.reason && <div>{skipReasonLabel(t, run.reason)}</div>}
                      {run.packages.length > 0 && (
                        <div>
                          {t('autoUpdates.appliedOf', '{{applied}} of {{total}} applied', {
                            applied: run.applied_count,
                            total: run.packages.length,
                          })}
                          {': '}
                          {run.packages.map((p) => p.package_name).join(', ')}
                        </div>
                      )}
                      {run.failures.map((f) => (
                        <div key={`f-${f.package_name}`}>
                          {f.package_name}: {f.error}
                        </div>
                      ))}
                      {run.skipped.map((s) => (
                        <div key={`s-${s.package_name}-${s.package_manager}`}>
                          {s.package_name}: {packageReasonLabel(t, s.reason)}
                        </div>
                      ))}
                    </Box>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </CardContent>
    </Card>
  );
};

export default HostAutoUpdatesCard;
