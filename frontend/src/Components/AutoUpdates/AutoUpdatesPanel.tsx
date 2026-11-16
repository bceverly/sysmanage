// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

// Automatic updates at a glance (ROADMAP 26.1, Enterprise): the hold on
// every policy, and the runs that need someone to look -- failed, partly
// failed, never reported, or a reboot that did not come back.

import React, { useCallback, useEffect, useState } from 'react';
import {
  Alert,
  Button,
  Card,
  CardContent,
  CardHeader,
  Chip,
  FormControlLabel,
  Stack,
  Switch,
  Typography,
} from '@mui/material';
import { useTranslation } from 'react-i18next';
import {
  autoUpdatesService,
  type AutoUpdateRun,
  type AutoUpdateSettings,
} from '../../Services/autoUpdates';
import { formatUTCTimestamp } from '../../utils/dateUtils';
import { rebootLabel, runStatusColor, runStatusLabel } from './autoUpdateLabels';

const PROBLEMS = new Set(['failed', 'partial', 'timed_out']);

const AutoUpdatesPanel: React.FC = () => {
  const { t } = useTranslation();
  const [settings, setSettings] = useState<AutoUpdateSettings | null>(null);
  const [problems, setProblems] = useState<AutoUpdateRun[]>([]);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const [s, runs] = await Promise.all([
        autoUpdatesService.settings(),
        autoUpdatesService.runs({ limit: 200 }),
      ]);
      setSettings(s);
      setProblems(
        runs.filter(
          (r) => !r.acknowledged_at && (PROBLEMS.has(r.status) || r.reboot_status === 'not_back'),
        ),
      );
    } catch {
      setSettings(null); // no Enterprise engine: the panel is not shown
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  if (settings === null) return null;

  const toggleHold = async (hold: boolean) => {
    let reason: string | undefined;
    if (hold) {
      reason =
        globalThis.prompt(t('autoUpdates.holdReason', 'Why hold every automatic update?')) ??
        undefined;
      if (!reason?.trim()) return;
    }
    try {
      await autoUpdatesService.holdAll(hold, reason);
      setError(null);
      await load();
    } catch {
      setError(t('autoUpdates.saveError', 'Could not save the change'));
    }
  };

  const acknowledge = async (run: AutoUpdateRun) => {
    try {
      await autoUpdatesService.acknowledge(run.id);
      await load();
    } catch {
      setError(t('autoUpdates.saveError', 'Could not save the change'));
    }
  };

  return (
    <Card>
      <CardHeader
        title={t('autoUpdates.title', 'Automatic updates')}
        subheader={t(
          'autoUpdates.subtitle',
          'Profiles with "Apply automatically" on update their hosts on schedule.',
        )}
        action={
          <FormControlLabel
            control={
              <Switch
                checked={settings.hold_all}
                onChange={(e) => void toggleHold(e.target.checked)}
              />
            }
            label={t('autoUpdates.holdAll', 'Hold every policy')}
          />
        }
      />
      <CardContent>
        {error && <Alert severity="error" sx={{ mb: 1 }}>{error}</Alert>}
        {settings.hold_all && (
          <Alert severity="warning" sx={{ mb: 2 }}>
            {t('autoUpdates.heldBy', 'On hold since {{when}} by {{who}}: {{reason}}', {
              when: formatUTCTimestamp(settings.hold_at ?? '', '--'),
              who: settings.hold_by ?? '',
              reason: settings.hold_reason ?? '',
            })}
          </Alert>
        )}
        {problems.length === 0 ? (
          <Typography variant="body2" color="text.secondary">
            {t('autoUpdates.noProblems', 'No automatic run needs attention.')}
          </Typography>
        ) : (
          <Stack spacing={1}>
            {problems.map((run) => (
              <Stack key={run.id} direction="row" spacing={1} sx={{ alignItems: 'center', flexWrap: 'wrap' }}>
                <Chip size="small" color={runStatusColor(run.status)} label={runStatusLabel(t, run.status)} />
                {run.reboot_status === 'not_back' && (
                  <Chip size="small" color="error" label={rebootLabel(t, run.reboot_status)} />
                )}
                <Typography variant="body2">
                  {run.hostname ?? run.host_id} -- {run.profile_name} --{' '}
                  {formatUTCTimestamp(run.queued_at ?? '', '--')}
                </Typography>
                <Button size="small" onClick={() => void acknowledge(run)}>
                  {t('autoUpdates.acknowledge', 'Acknowledge')}
                </Button>
              </Stack>
            ))}
          </Stack>
        )}
      </CardContent>
    </Card>
  );
};

export default AutoUpdatesPanel;
