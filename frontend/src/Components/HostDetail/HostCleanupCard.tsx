// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

// Old kernels and unneeded packages (ROADMAP 27.8): the host's kernels, which
// ones are kept and why, a plan to review, and removing exactly that plan.
import React, { useCallback, useEffect, useState } from 'react';
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  Stack,
  Typography,
} from '@mui/material';
import CleaningServicesIcon from '@mui/icons-material/CleaningServices';
import { useTranslation } from 'react-i18next';
import type { TFunction } from 'i18next';
import { packageCleanupService, type CleanupRun, type CleanupState } from '../../Services/packageCleanup';
import { formatUTCTimestamp } from '../../utils/dateUtils';

const POLL_MS = 3000;

const keptReason = (t: TFunction, reason: string): string => {
  switch (reason) {
    case 'running': return t('cleanup.kept.running', 'running now');
    case 'newest': return t('cleanup.kept.newest', 'newest installed (the next boot)');
    case 'last_proven': return t('cleanup.kept.lastProven', 'last kernel that booted and stayed up');
    default: return t('cleanup.kept.minimum', 'kept so two kernels remain');
  }
};

const refusalText = (t: TFunction, refusal: string): string => {
  if (refusal === 'running_kernel_not_proven') {
    return t('cleanup.refusal.notProven',
      'The host has just booted this kernel. Nothing is removed until it has stayed up for 15 minutes, so the last good kernel stays as the way back.');
  }
  return t('cleanup.refusal.unknown',
    "The running kernel is not known yet: the host's agent reports it with its next heartbeat.");
};

const statusText = (t: TFunction, run: CleanupRun): string => {
  switch (run.status) {
    case 'queued': return t('cleanup.status.queued', 'Waiting for the host');
    case 'planned': return t('cleanup.status.planned', 'Planned. Packages that can be removed: {{n}}', { n: run.packages.length });
    case 'done': return t('cleanup.status.done', 'Done. Packages removed: {{n}}', { n: run.packages.length });
    case 'refused': return t('cleanup.status.refused', 'Refused: {{error}}', { error: run.error ?? '' });
    case 'unsupported': return t('cleanup.status.unsupported', 'This host cannot clean up yet (apt hosts only, with a current agent).');
    case 'boot_path_broken': return t('cleanup.status.bootPath', 'Removed, but the boot files of a kept kernel are missing: {{error}}', { error: run.error ?? '' });
    default: return t('cleanup.status.failed', 'Failed: {{error}}', { error: run.error ?? '' });
  }
};

interface Props {
  hostId: string;
}

const HostCleanupCard: React.FC<Props> = ({ hostId }) => {
  const { t } = useTranslation();
  const [state, setState] = useState<CleanupState | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      setState(await packageCleanupService.state(hostId));
    } catch {
      setError(t('cleanup.loadError', 'The cleanup state could not be read.'));
    }
  }, [hostId, t]);

  useEffect(() => { void load(); }, [load]);

  const latest = state?.runs[0];
  const waiting = latest?.status === 'queued';
  useEffect(() => {
    if (!waiting) return undefined;
    const timer = setInterval(() => { void load(); }, POLL_MS);
    return () => clearInterval(timer);
  }, [waiting, load]);

  const act = async (call: () => Promise<CleanupRun>) => {
    setBusy(true);
    try {
      await call();
      setError(null);
      await load();
    } catch {
      setError(t('cleanup.actionError', 'That could not be done.'));
    } finally {
      setBusy(false);
    }
  };

  if (!state) return null;
  const plan = latest?.mode === 'plan' && latest.status === 'planned' ? latest : null;
  const old = state.installed_kernels.filter((k) => !state.protected.some((p) => p.release === k));

  return (
    <Card>
      <CardContent>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1 }}>
          <CleaningServicesIcon />
          <Typography variant="h6">{t('cleanup.title', 'Old kernels and unneeded packages')}</Typography>
        </Box>
        {error && <Alert severity="error" sx={{ mb: 1 }}>{error}</Alert>}
        <Typography variant="body2" sx={{ mb: 1 }}>
          {t('cleanup.kernels', 'Running {{running}}; {{installed}} kernels installed, {{old}} of them old.', {
            running: state.running_kernel ?? t('cleanup.unknown', 'unknown'),
            installed: state.installed_kernels.length,
            old: old.length,
          })}
        </Typography>
        {state.protected.length > 0 && (
          <Stack direction="row" spacing={1} sx={{ mb: 1, flexWrap: 'wrap', rowGap: 1 }}>
            {state.protected.map((p) => (
              <Chip key={p.release} size="small" color="success" variant="outlined"
                label={t('cleanup.keptChip', 'Kept: {{release}} ({{why}})', { release: p.release, why: keptReason(t, p.reason) })} />
            ))}
          </Stack>
        )}
        {state.refusal && <Alert severity="info" sx={{ mb: 1 }}>{refusalText(t, state.refusal)}</Alert>}
        {latest && (
          <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
            {statusText(t, latest)} -- {formatUTCTimestamp(latest.completed_at ?? latest.created_at ?? '', '--')}
          </Typography>
        )}
        {plan && plan.packages.length > 0 && (
          <Box sx={{ mb: 1, maxHeight: 200, overflow: 'auto' }}>
            {plan.packages.map((p) => (
              <Typography key={p.name} variant="body2" sx={{ fontFamily: 'monospace' }}>
                {p.name} {p.reason === 'old_kernel'
                  ? t('cleanup.reason.oldKernel', '(old kernel {{kernel}})', { kernel: p.kernel ?? '' })
                  : t('cleanup.reason.unneeded', '(no longer needed)')}
              </Typography>
            ))}
          </Box>
        )}
        <Stack direction="row" spacing={1}>
          <Button size="small" disabled={busy || waiting || !!state.refusal}
            onClick={() => void act(() => packageCleanupService.plan(hostId))}>
            {t('cleanup.plan', 'Plan cleanup')}
          </Button>
          {plan && plan.packages.length > 0 && (
            <Button size="small" color="warning" disabled={busy || waiting}
              onClick={() => void act(() => packageCleanupService.apply(hostId, plan.packages.map((p) => p.name)))}>
              {t('cleanup.apply', 'Remove the packages listed ({{n}})', { n: plan.packages.length })}
            </Button>
          )}
        </Stack>
      </CardContent>
    </Card>
  );
};

export default HostCleanupCard;
