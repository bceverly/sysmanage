import React, { useEffect, useState } from 'react';
import { Box, Chip, Tooltip } from '@mui/material';
import {
  CloudDone,
  CloudOff,
  Sync,
  Warning,
} from '@mui/icons-material';
import { useTranslation } from 'react-i18next';
import { connectionMonitor, ConnectionStatus } from '../Services/connectionMonitor';

const ConnectionStatusIndicator: React.FC = () => {
  const { t } = useTranslation();
  const [status, setStatus] = useState<ConnectionStatus>({
    isConnected: true,
    lastConnected: new Date(),
    retryCount: 0,
    nextRetryIn: 0,
  });

  useEffect(() => {
    const unsubscribe = connectionMonitor.onStatusChange(setStatus);
    return unsubscribe;
  }, []);

  const getIndicatorProps = () => {
    if (status.isConnected) {
      return {
        icon: <CloudDone />,
        label: t('connectionStatus.connected', 'Connected'),
        color: 'success' as const,
        tooltip: t('connectionStatus.connectedTooltip', 'Connected to server'),
      };
    }

    if (status.nextRetryIn > 0) {
      return {
        icon: <Sync className="animate-spin" />,
        label: t('connectionStatus.retrying', 'Retrying'),
        color: 'warning' as const,
        tooltip: t('connectionStatus.retryingTooltip', 'Attempting to reconnect to server'),
      };
    }

    if (status.retryCount >= 10) {
      return {
        icon: <CloudOff />,
        label: t('connectionStatus.offline', 'Offline'),
        color: 'error' as const,
        tooltip: t('connectionStatus.offlineTooltip', 'Unable to connect to server'),
      };
    }

    return {
      icon: <Warning />,
      label: t('connectionStatus.disconnected', 'Disconnected'),
      color: 'warning' as const,
      tooltip: t('connectionStatus.disconnectedTooltip', 'Connection lost, retrying...'),
    };
  };

  const { icon, label, color, tooltip } = getIndicatorProps();

  // Don't show indicator when connected (to keep navbar clean)
  if (status.isConnected) {
    return null;
  }

  return (
    <Box sx={{ display: 'flex', alignItems: 'center' }}>
      <Tooltip title={tooltip} arrow>
        <Chip
          icon={icon}
          label={label}
          color={color}
          size="small"
          variant="outlined"
          sx={{
            fontSize: '0.75rem',
            height: 24,
            '& .MuiChip-icon': {
              fontSize: 16,
            },
            '& .animate-spin': {
              animation: 'spin 1s linear infinite',
            },
            '@keyframes spin': {
              from: { transform: 'rotate(0deg)' },
              to: { transform: 'rotate(360deg)' },
            },
          }}
        />
      </Tooltip>
    </Box>
  );
};

export default ConnectionStatusIndicator;