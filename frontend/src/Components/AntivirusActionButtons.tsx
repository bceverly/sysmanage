// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

import React, { useEffect } from 'react';
import { Alert, Box, Button, CircularProgress, Typography } from '@mui/material';
import SecurityIcon from '@mui/icons-material/Security';
import { useTranslation } from 'react-i18next';
import type { AntivirusStatus } from '../Services/antivirusService';
import { useActionInFlight, useAgentCommandProgress } from '../hooks/useActionInFlight';

/** A handler resolves false when the server refused (nothing to wait for). */
export type AntivirusAction = () => Promise<boolean | void> | void;

type ActionKey = 'deploy' | 'remove' | 'enable' | 'disable';

// What the agent's next antivirus report must show for each action to be done.
const DONE: Record<ActionKey, (s: AntivirusStatus | null) => boolean> = {
  deploy: (s) => Boolean(s?.software_name),
  remove: (s) => !s?.software_name,
  enable: (s) => s?.enabled === true,
  disable: (s) => s?.enabled === false,
};

// Poll this often while waiting for the agent (the card's own poll is 30 s).
const FAST_POLL_MS = 5000;

interface AntivirusActionButtonsProps {
  status: AntivirusStatus | null;
  onPoll: () => void;
  onDeploy?: AntivirusAction;
  onRemove?: AntivirusAction;
  onEnable?: AntivirusAction;
  onDisable?: AntivirusAction;
  canDeploy: boolean;
  canRemove: boolean;
  canEnable: boolean;
  canDisable: boolean;
  /** Host inactive / agent unprivileged / no OS default: nothing may run. */
  blocked: { deploy: boolean; other: boolean };
  titles: Record<ActionKey, string>;
}

const AntivirusActionButtons: React.FC<AntivirusActionButtonsProps> = ({
  status,
  onPoll,
  onDeploy,
  onRemove,
  onEnable,
  onDisable,
  canDeploy,
  canRemove,
  canEnable,
  canDisable,
  blocked,
  titles,
}) => {
  const { t } = useTranslation();
  const { busy, run } = useActionInFlight();
  const { awaitingKey, timedOut, begin } = useAgentCommandProgress<AntivirusStatus>(status);
  const active = (busy ?? awaitingKey) as ActionKey | null;

  useEffect(() => {
    if (!awaitingKey) return undefined;
    const timer = setInterval(onPoll, FAST_POLL_MS);
    return () => clearInterval(timer);
  }, [awaitingKey, onPoll]);

  const trigger = (key: ActionKey, handler?: AntivirusAction) => () => {
    if (!handler || active) return;
    void run(key, () => {
      const result = handler();
      // A synchronous handler has already queued its request: wait for the
      // agent straight away.  A promise resolving false was refused.
      if (!result || typeof (result as Promise<unknown>).then !== 'function') {
        begin(key, DONE[key]);
        return undefined;
      }
      return (result as Promise<boolean | void>).then((accepted) => {
        if (accepted !== false) begin(key, DONE[key]);
      });
    });
  };

  const progressLabel: Record<ActionKey, string> = {
    deploy: t('security.deployingAntivirus', 'Deploying...'),
    remove: t('security.removingAntivirus', 'Removing...'),
    enable: t('security.enablingAntivirus', 'Enabling...'),
    disable: t('security.disablingAntivirus', 'Disabling...'),
  };
  const label = (key: ActionKey, idle: string) => (active === key ? progressLabel[key] : idle);
  const icon = (key: ActionKey, idle?: React.ReactNode) =>
    active === key ? <CircularProgress size={16} color="inherit" /> : idle;

  const installed = Boolean(status?.software_name);

  return (
    <>
      <Box sx={{ mt: 3, display: 'flex', gap: 1, flexWrap: 'wrap' }}>
        {canDeploy && onDeploy && (
          <Button variant="contained" color="success" startIcon={icon('deploy', <SecurityIcon />)}
            onClick={trigger('deploy', onDeploy)}
            disabled={Boolean(active) || blocked.deploy || installed}
            title={titles.deploy}>
            {label('deploy', t('hostDetail.deployAntivirus', 'Deploy Antivirus'))}
          </Button>
        )}
        {canRemove && onRemove && (
          <Button variant="contained" color="error" startIcon={icon('remove')}
            onClick={trigger('remove', onRemove)}
            disabled={Boolean(active) || blocked.other || !installed}
            title={titles.remove}>
            {label('remove', t('security.removeAntivirus', 'Remove Antivirus'))}
          </Button>
        )}
        {canEnable && onEnable && installed && (
          <Button variant="contained" color="primary" startIcon={icon('enable')}
            onClick={trigger('enable', onEnable)}
            disabled={Boolean(active) || blocked.other || status?.enabled === true}
            title={titles.enable}>
            {label('enable', t('security.enableAntivirus', 'Enable Antivirus'))}
          </Button>
        )}
        {canDisable && onDisable && installed && (
          <Button variant="contained" color="warning" startIcon={icon('disable')}
            onClick={trigger('disable', onDisable)}
            disabled={Boolean(active) || blocked.other || status?.enabled === false}
            title={titles.disable}>
            {label('disable', t('security.disableAntivirus', 'Disable Antivirus'))}
          </Button>
        )}
      </Box>
      {awaitingKey && (
        <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 1 }}
          data-testid="antivirus-awaiting">
          {t('security.awaitingAgent', 'Waiting for the agent to report the change. This can take a few minutes.')}
        </Typography>
      )}
      {timedOut && (
        <Alert severity="warning" sx={{ mt: 1 }} data-testid="antivirus-timed-out">
          {t('security.agentNotConfirmed',
            'The agent has not confirmed the change yet. It may still be working; check the host again later.')}
        </Alert>
      )}
    </>
  );
};

export default AntivirusActionButtons;
