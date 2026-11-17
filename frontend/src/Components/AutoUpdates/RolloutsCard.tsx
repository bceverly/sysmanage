// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

// Fleet-by-fleet rollouts (ROADMAP 26.4, Enterprise): each rollout's fleets
// in order, the one in progress, every host's latest run there and why the
// rest did not apply; why a halted rollout stopped and which hosts caused
// it, with "Resume" and "Cancel" (each asks for a reason).

import React, { useCallback, useEffect, useState } from 'react';
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  CardHeader,
  Chip,
  Collapse,
  Stack,
  Typography,
} from '@mui/material';
import { useTranslation } from 'react-i18next';
import { autoUpdatesService, type Rollout, type RolloutStage } from '../../Services/autoUpdates';
import { formatUTCTimestamp } from '../../utils/dateUtils';
import {
  fleetStatusLabel,
  haltReasonLabel,
  rebootLabel,
  rolloutStatusColor,
  rolloutStatusLabel,
  runStatusColor,
  runStatusLabel,
  skipReasonLabel,
} from './autoUpdateLabels';

function fleetName(t: ReturnType<typeof useTranslation>['t'], stage: RolloutStage): string {
  return stage.remaining ? t('autoUpdates.fleet.remaining', 'The remaining hosts') : stage.name;
}

const Fleet: React.FC<{ stage: RolloutStage; current: boolean }> = ({ stage, current }) => {
  const { t } = useTranslation();
  const [open, setOpen] = useState(current);
  const counts = stage.counts;
  return (
    <Box sx={{ pl: 1, borderLeft: 2, borderColor: current ? 'primary.main' : 'divider', mb: 1 }}>
      <Stack direction="row" spacing={1} sx={{ alignItems: 'center', flexWrap: 'wrap' }}>
        <Typography variant="body2" sx={{ fontWeight: current ? 600 : 400 }}>
          {fleetName(t, stage)}
        </Typography>
        <Chip size="small" label={fleetStatusLabel(t, stage.status)} />
        <Typography variant="caption" color="text.secondary">
          {t('autoUpdates.fleet.hosts', '{{count}} host(s)', { count: stage.host_ids.length })}
          {counts && stage.status !== 'pending'
            ? ` -- ${t('autoUpdates.fleet.counts', '{{applied}} applied, {{failed}} failed, {{inFlight}} in progress, {{other}} not applied', {
                applied: counts.applied ?? 0,
                failed: counts.failed ?? 0,
                inFlight: counts.in_flight ?? 0,
                other: counts.other ?? 0,
              })}`
            : ''}
        </Typography>
        {stage.soak_until && stage.status === 'running' && (counts?.in_flight ?? 1) === 0 && (
          <Typography variant="caption">
            {t('autoUpdates.fleet.soakUntil', 'soak time ends {{when}}', {
              when: formatUTCTimestamp(stage.soak_until, '--'),
            })}
          </Typography>
        )}
        {stage.forced && (
          <Typography variant="caption">
            {t('autoUpdates.fleet.resumedBy', 'resumed by {{who}}', { who: stage.resumed_by ?? '' })}
          </Typography>
        )}
        {stage.hosts.length > 0 && stage.status !== 'pending' && (
          <Button size="small" onClick={() => setOpen(!open)}>
            {open ? t('autoUpdates.fleet.hide', 'Hide hosts') : t('autoUpdates.fleet.show', 'Show hosts')}
          </Button>
        )}
      </Stack>
      <Collapse in={open && stage.status !== 'pending'}>
        <Stack spacing={0.5} sx={{ mt: 0.5, mb: 1 }}>
          {stage.hosts.map((host) => (
            <Stack key={host.host_id} direction="row" spacing={1} sx={{ alignItems: 'center', flexWrap: 'wrap' }}>
              <Typography variant="body2">{host.hostname ?? host.host_id}</Typography>
              {host.status ? (
                <Chip size="small" color={runStatusColor(host.status)} label={runStatusLabel(t, host.status)} />
              ) : (
                <Chip size="small" label={t('autoUpdates.fleet.noRun', 'Not planned yet')} />
              )}
              {host.status === 'waiting' && host.release_at && (
                <Typography variant="caption">
                  {t('autoUpdates.startsAt', 'Starts when its window opens: {{when}}', {
                    when: formatUTCTimestamp(host.release_at, '--'),
                  })}
                </Typography>
              )}
              {host.reason && (
                <Typography variant="caption" color="text.secondary">
                  {skipReasonLabel(t, host.reason)}
                </Typography>
              )}
              {host.reboot_status && !['none', 'not_wanted'].includes(host.reboot_status) && (
                <Chip size="small" variant="outlined" label={rebootLabel(t, host.reboot_status)} />
              )}
            </Stack>
          ))}
        </Stack>
      </Collapse>
    </Box>
  );
};

const RolloutsCard: React.FC = () => {
  const { t } = useTranslation();
  const [rollouts, setRollouts] = useState<Rollout[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setRollouts(await autoUpdatesService.rollouts({ limit: 10 }));
    } catch {
      setRollouts(null);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  if (!rollouts || rollouts.length === 0) return null;

  const act = async (rollout: Rollout, action: 'resume' | 'cancel') => {
    const question =
      action === 'resume'
        ? t('autoUpdates.rollout.resumeReason', 'Why continue past this fleet?')
        : t('autoUpdates.rollout.cancelReason', 'Why cancel this rollout?');
    const reason = globalThis.prompt(question);
    if (!reason?.trim()) return;
    try {
      if (action === 'resume') await autoUpdatesService.resumeRollout(rollout.id, reason.trim());
      else await autoUpdatesService.cancelRollout(rollout.id, reason.trim());
      setError(null);
      await load();
    } catch {
      setError(t('autoUpdates.saveError', 'Could not save the change'));
    }
  };

  const names = (rollout: Rollout) => {
    const byId = new Map<string, string>();
    rollout.stages.forEach((s) => s.hosts.forEach((h) => byId.set(h.host_id, h.hostname ?? h.host_id)));
    return (rollout.halt_detail.culprits ?? []).map((id) => byId.get(id) ?? id).join(', ');
  };

  return (
    <Card>
      <CardHeader
        title={t('autoUpdates.rollout.title', 'Fleet-by-fleet rollouts')}
        subheader={t(
          'autoUpdates.rollout.subtitle',
          'Policies that roll out fleet by fleet: one fleet at a time, each healthy before the next.',
        )}
      />
      <CardContent>
        {error && <Alert severity="error" sx={{ mb: 1 }}>{error}</Alert>}
        <Stack spacing={2}>
          {rollouts.map((rollout) => (
            <Box key={rollout.id}>
              <Stack direction="row" spacing={1} sx={{ alignItems: 'center', flexWrap: 'wrap', mb: 1 }}>
                <Typography variant="subtitle2">{rollout.profile_name}</Typography>
                <Chip
                  size="small"
                  color={rolloutStatusColor(rollout.status)}
                  label={rolloutStatusLabel(t, rollout.status)}
                />
                <Typography variant="caption" color="text.secondary">
                  {t('autoUpdates.rollout.started', 'started {{when}}', {
                    when: formatUTCTimestamp(rollout.started_at ?? '', '--'),
                  })}
                </Typography>
                {rollout.status === 'halted' && (
                  <Button size="small" variant="outlined" onClick={() => void act(rollout, 'resume')}>
                    {t('autoUpdates.rollout.resume', 'Resume')}
                  </Button>
                )}
                {(rollout.status === 'halted' || rollout.status === 'running') && (
                  <Button size="small" color="error" onClick={() => void act(rollout, 'cancel')}>
                    {t('autoUpdates.rollout.cancel', 'Cancel')}
                  </Button>
                )}
              </Stack>
              {rollout.status === 'halted' && (
                <Alert severity="error" sx={{ mb: 1 }}>
                  {t('autoUpdates.rollout.haltedBecause', 'Halted at {{fleet}}: {{reason}} ({{hosts}}). Nothing more is patched until someone resumes or cancels it.', {
                    fleet: fleetName(t, rollout.stages[rollout.stage_index]),
                    reason: haltReasonLabel(t, rollout.halt_reason),
                    hosts: names(rollout),
                  })}
                </Alert>
              )}
              {rollout.status === 'canceled' && rollout.end_reason && (
                <Typography variant="caption" color="text.secondary" component="div" sx={{ mb: 1 }}>
                  {t('autoUpdates.rollout.canceledBy', 'Canceled by {{who}}: {{reason}}', {
                    who: rollout.ended_by ?? '',
                    reason: rollout.end_reason,
                  })}
                </Typography>
              )}
              {rollout.stages.map((stage, index) => (
                <Fleet
                  key={`${rollout.id}-${index}`}
                  stage={stage}
                  current={rollout.status !== 'completed' && index === rollout.stage_index}
                />
              ))}
            </Box>
          ))}
        </Stack>
      </CardContent>
    </Card>
  );
};

export default RolloutsCard;
