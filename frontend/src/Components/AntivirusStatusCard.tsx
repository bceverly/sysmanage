// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

import React, { useCallback, useEffect, useState, useRef } from 'react';
import { formatUTCTimestamp } from '../utils/dateUtils';
import {
  Card,
  CardContent,
  Typography,
  Box,
  Chip,
  CircularProgress,
  Alert,
  Stack,
} from '@mui/material';
import ShieldIcon from '@mui/icons-material/Shield';
import CheckCircleIcon from '@mui/icons-material/CheckCircle';
import CancelIcon from '@mui/icons-material/Cancel';
import WarningIcon from '@mui/icons-material/Warning';
import { useTranslation } from 'react-i18next';
import { AntivirusStatus, getAntivirusStatus } from '../Services/antivirusService';
import AntivirusActionButtons, { AntivirusAction } from './AntivirusActionButtons';

interface AntivirusStatusCardProps {
  hostId: string;
  onDeployAntivirus?: AntivirusAction;
  onEnableAntivirus?: AntivirusAction;
  onDisableAntivirus?: AntivirusAction;
  onRemoveAntivirus?: AntivirusAction;
  canDeployAntivirus?: boolean;
  canEnableAntivirus?: boolean;
  canDisableAntivirus?: boolean;
  canRemoveAntivirus?: boolean;
  isHostActive?: boolean;
  isAgentPrivileged?: boolean;
  hasOsDefault?: boolean;
  refreshTrigger?: number;
  sx?: object;
}

const AntivirusStatusCard: React.FC<AntivirusStatusCardProps> = ({
  hostId,
  onDeployAntivirus,
  onEnableAntivirus,
  onDisableAntivirus,
  onRemoveAntivirus,
  canDeployAntivirus = false,
  canEnableAntivirus = false,
  canDisableAntivirus = false,
  canRemoveAntivirus = false,
  isHostActive = false,
  isAgentPrivileged = false,
  hasOsDefault = false,
  refreshTrigger = 0,
  sx = {},
}) => {
  const { t } = useTranslation();

  // Helper to get the status chip based on enabled state
  const getStatusChip = (enabled: boolean | undefined) => {
    if (enabled === true) {
      return (
        <Chip
          icon={<CheckCircleIcon />}
          label={t('security.enabled', 'Enabled')}
          color="success"
          size="small"
        />
      );
    }
    if (enabled === false) {
      return (
        <Chip
          icon={<CancelIcon />}
          label={t('security.disabled', 'Disabled')}
          color="error"
          size="small"
        />
      );
    }
    return (
      <Chip
        label={t('security.unknown', 'Unknown')}
        size="small"
      />
    );
  };

  // Helper to get tooltip/title for deploy button
  const getDeployButtonTitle = (status: AntivirusStatus | null): string => {
    if (status?.software_name) {
      return t('security.alreadyDeployed', 'Antivirus already deployed');
    }
    if (!hasOsDefault) {
      return t('hostDetail.noAntivirusDefault', 'No antivirus default configured for this OS');
    }
    if (!isAgentPrivileged) {
      return t('hostDetail.notPrivileged', 'Agent not running in privileged mode');
    }
    if (!isHostActive) {
      return t('hostDetail.hostInactive', 'Host is not active');
    }
    return '';
  };

  // Helper to get tooltip/title for remove button
  const getRemoveButtonTitle = (status: AntivirusStatus | null): string => {
    if (!status?.software_name) {
      return t('security.notDeployed', 'No antivirus deployed');
    }
    if (!isAgentPrivileged) {
      return t('hostDetail.notPrivileged', 'Agent not running in privileged mode');
    }
    if (!isHostActive) {
      return t('hostDetail.hostInactive', 'Host is not active');
    }
    return '';
  };

  // Helper to get tooltip/title for enable button
  const getEnableButtonTitle = (status: AntivirusStatus): string => {
    if (status.enabled === true) {
      return t('security.alreadyEnabled', 'Antivirus already enabled');
    }
    if (!isAgentPrivileged) {
      return t('hostDetail.notPrivileged', 'Agent not running in privileged mode');
    }
    if (!isHostActive) {
      return t('hostDetail.hostInactive', 'Host is not active');
    }
    return '';
  };

  // Helper to get tooltip/title for disable button
  const getDisableButtonTitle = (status: AntivirusStatus): string => {
    if (status.enabled === false) {
      return t('security.alreadyDisabled', 'Antivirus already disabled');
    }
    if (!isAgentPrivileged) {
      return t('hostDetail.notPrivileged', 'Agent not running in privileged mode');
    }
    if (!isHostActive) {
      return t('hostDetail.hostInactive', 'Host is not active');
    }
    return '';
  };
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [antivirusStatus, setAntivirusStatus] = useState<AntivirusStatus | null>(null);
  const isInitialLoad = useRef(true);

  useEffect(() => {
    const fetchAntivirusStatus = async () => {
      // Only show loading spinner on initial load, not on refresh
      if (isInitialLoad.current) {
        setLoading(true);
      }
      setError(null);
      try {
        const status = await getAntivirusStatus(hostId);
        setAntivirusStatus(status);
        isInitialLoad.current = false;
      } catch (err) {
        console.error('Error fetching antivirus status:', err);
        setError(t('security.antivirusError', 'Failed to load antivirus status'));
      } finally {
        setLoading(false);
      }
    };

    if (hostId) {
      void fetchAntivirusStatus();
    }
  }, [hostId, t, refreshTrigger]);

  // A quiet re-read (no spinner): the 30 s auto-refresh, and the faster poll
  // the action buttons run while waiting for the agent to report a change.
  const refreshStatus = useCallback(() => {
    if (!hostId) return;
    getAntivirusStatus(hostId)
      .then(setAntivirusStatus)
      .catch((err) => console.error('Error refreshing antivirus status:', err));
  }, [hostId]);

  // Auto-refresh every 30 seconds
  useEffect(() => {
    if (!hostId) return;
    const intervalId = setInterval(refreshStatus, 30000);
    return () => clearInterval(intervalId);
  }, [hostId, refreshStatus]);

  if (loading) {
    return (
      <Card sx={sx}>
        <CardContent>
          <Box display="flex" justifyContent="center" alignItems="center" minHeight="150px">
            <CircularProgress />
          </Box>
        </CardContent>
      </Card>
    );
  }

  if (error) {
    return (
      <Card sx={sx}>
        <CardContent>
          <Alert severity="error">{error}</Alert>
        </CardContent>
      </Card>
    );
  }

  const formatDate = (dateString: string) => {
    return formatUTCTimestamp(dateString);
  };

  return (
    <Card sx={sx}>
      <CardContent>
        <Typography variant="subtitle1" sx={{ display: 'flex', alignItems: 'center', fontWeight: 'bold', fontSize: '1.1rem', mb: 2 }}>
          <ShieldIcon sx={{ mr: 1 }} />
          {t('security.antivirusOpenSource', 'Antivirus - Open Source')}
        </Typography>

        {antivirusStatus?.software_name ? (
          <Stack spacing={2}>
            <Box>
              <Typography variant="body2" color="text.secondary" gutterBottom>
                {t('security.software', 'Software')}
              </Typography>
              <Typography variant="body1" fontWeight="medium">
                {antivirusStatus.software_name}
              </Typography>
            </Box>

            {antivirusStatus.version && (
              <Box>
                <Typography variant="body2" color="text.secondary" gutterBottom>
                  {t('security.version', 'Version')}
                </Typography>
                <Typography variant="body1">
                  {antivirusStatus.version}
                </Typography>
              </Box>
            )}

            {antivirusStatus.install_path && (
              <Box>
                <Typography variant="body2" color="text.secondary" gutterBottom>
                  {t('security.installPath', 'Installation Path')}
                </Typography>
                <Typography variant="body1" sx={{ fontFamily: 'monospace', fontSize: '0.9rem' }}>
                  {antivirusStatus.install_path}
                </Typography>
              </Box>
            )}

            <Box>
              <Typography variant="body2" color="text.secondary" gutterBottom>
                {t('security.status', 'Status')}
              </Typography>
              {getStatusChip(antivirusStatus.enabled ?? undefined)}
            </Box>

            {antivirusStatus.last_updated && (
              <Box>
                <Typography variant="body2" color="text.secondary" gutterBottom>
                  {t('security.lastUpdated', 'Last Updated')}
                </Typography>
                <Typography variant="body2">
                  {formatDate(antivirusStatus.last_updated)}
                </Typography>
              </Box>
            )}
          </Stack>
        ) : (
          <Box sx={{ display: 'flex', alignItems: 'center', py: 2 }}>
            <WarningIcon sx={{ mr: 1, color: 'warning.main' }} />
            <Typography variant="body2" color="text.secondary">
              {t('security.noAntivirusDetected', 'No antivirus software detected')}
            </Typography>
          </Box>
        )}

        <AntivirusActionButtons
          status={antivirusStatus}
          onPoll={refreshStatus}
          onDeploy={onDeployAntivirus}
          onRemove={onRemoveAntivirus}
          onEnable={onEnableAntivirus}
          onDisable={onDisableAntivirus}
          canDeploy={canDeployAntivirus}
          canRemove={canRemoveAntivirus}
          canEnable={canEnableAntivirus}
          canDisable={canDisableAntivirus}
          blocked={{
            deploy: !isHostActive || !isAgentPrivileged || !hasOsDefault,
            other: !isHostActive || !isAgentPrivileged,
          }}
          titles={{
            deploy: getDeployButtonTitle(antivirusStatus),
            remove: getRemoveButtonTitle(antivirusStatus),
            enable: antivirusStatus ? getEnableButtonTitle(antivirusStatus) : '',
            disable: antivirusStatus ? getDisableButtonTitle(antivirusStatus) : '',
          }}
        />
      </CardContent>
    </Card>
  );
};

export default AntivirusStatusCard;
