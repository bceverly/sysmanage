import React, { useEffect, useState } from 'react';
import {
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Typography,
  Button,
  CircularProgress,
  Box,
  Alert,
  LinearProgress,
  Chip,
} from '@mui/material';
import {
  CloudOff,
  Refresh,
  Warning,
  Error as ErrorIcon,
} from '@mui/icons-material';
import { useTranslation } from 'react-i18next';
import { connectionMonitor, ConnectionStatus } from '../Services/connectionMonitor';

interface ServerDownModalProps {
  open: boolean;
}

const ServerDownModal: React.FC<ServerDownModalProps> = ({ open }) => {
  const { t } = useTranslation();
  const [status, setStatus] = useState<ConnectionStatus>({
    isConnected: true,
    lastConnected: null,
    retryCount: 0,
    nextRetryIn: 0,
  });

  useEffect(() => {
    const unsubscribe = connectionMonitor.onStatusChange(setStatus);
    return unsubscribe;
  }, []);

  const handleRetryNow = () => {
    connectionMonitor.retryNow();
  };

  const handleResetRetries = () => {
    connectionMonitor.resetRetryCount();
  };

  const formatTimeRemaining = (seconds: number): string => {
    if (seconds <= 0) return t('serverDown.retrying', 'Retrying...');
    
    if (seconds < 60) {
      return t('serverDown.secondsRemaining', `${seconds}s`, { seconds });
    }
    
    const minutes = Math.floor(seconds / 60);
    const remainingSeconds = seconds % 60;
    return t('serverDown.timeRemaining', `${minutes}m ${remainingSeconds}s`, { minutes, seconds: remainingSeconds });
  };

  const getProgressValue = (): number => {
    if (status.nextRetryIn <= 0) return 100;
    
    // Calculate progress based on retry delay
    const maxDelay = Math.min(5 * Math.pow(2, status.retryCount), 300);
    const progress = ((maxDelay - status.nextRetryIn) / maxDelay) * 100;
    return Math.max(0, Math.min(100, progress));
  };

  const getStatusIcon = () => {
    if (status.retryCount === 0) {
      return <CloudOff color="warning" sx={{ fontSize: 48 }} />;
    } else if (status.retryCount >= 10) {
      return <ErrorIcon color="error" sx={{ fontSize: 48 }} />;
    } else {
      return <Warning color="warning" sx={{ fontSize: 48 }} />;
    }
  };

  const getAlertSeverity = (): 'warning' | 'error' => {
    return status.retryCount >= 10 ? 'error' : 'warning';
  };

  const getTitle = (): string => {
    if (status.retryCount >= 10) {
      return t('serverDown.titleFailed', 'Server Unavailable');
    }
    return t('serverDown.title', 'Connection Interrupted');
  };

  const getMessage = (): string => {
    if (status.retryCount >= 10) {
      return t('serverDown.messageFailed', 
        'Unable to connect to the server after multiple attempts. Please contact support or try again later.');
    }
    
    return t('serverDown.message', 
      'The connection to the server has been interrupted. Attempting to reconnect automatically.');
  };

  return (
    <Dialog
      open={open}
      maxWidth="sm"
      fullWidth
      disableEscapeKeyDown
      aria-labelledby="server-down-dialog-title"
      PaperProps={{
        sx: {
          borderRadius: 2,
          minHeight: 400,
        },
      }}
    >
      <DialogTitle
        id="server-down-dialog-title"
        sx={{
          textAlign: 'center',
          pb: 1,
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          gap: 2,
        }}
      >
        {getStatusIcon()}
        <Typography variant="h5" component="div">
          {getTitle()}
        </Typography>
      </DialogTitle>

      <DialogContent sx={{ pt: 1 }}>
        <Alert 
          severity={getAlertSeverity()} 
          sx={{ mb: 3 }}
        >
          {getMessage()}
        </Alert>

        <Box sx={{ mb: 3 }}>
          <Typography variant="body2" color="text.secondary" gutterBottom>
            {t('serverDown.details', 'Connection Details:')}
          </Typography>
          
          <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 1, mb: 2 }}>
            <Chip
              size="small"
              label={t('serverDown.attempts', `Attempts: ${status.retryCount}`, { count: status.retryCount })}
              color={status.retryCount >= 10 ? 'error' : 'default'}
            />
            {status.lastConnected && (
              <Chip
                size="small"
                label={t('serverDown.lastConnected', 
                  { time: status.lastConnected.toLocaleTimeString() })}
                color="default"
              />
            )}
          </Box>

          {status.nextRetryIn > 0 && (
            <Box sx={{ mb: 2 }}>
              <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 1 }}>
                <Typography variant="body2">
                  {t('serverDown.nextRetry', 'Next retry in:')}
                </Typography>
                <Typography variant="body2" fontWeight="bold">
                  {formatTimeRemaining(status.nextRetryIn)}
                </Typography>
              </Box>
              <LinearProgress
                variant="determinate"
                value={getProgressValue()}
                sx={{
                  height: 6,
                  borderRadius: 3,
                  backgroundColor: 'rgba(0, 0, 0, 0.1)',
                  '& .MuiLinearProgress-bar': {
                    borderRadius: 3,
                  },
                }}
              />
            </Box>
          )}

          {status.error && (
            <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>
              {t('serverDown.error', 'Error')}: {status.error}
            </Typography>
          )}
        </Box>
      </DialogContent>

      <DialogActions sx={{ justifyContent: 'center', pb: 3 }}>
        <Button
          onClick={handleRetryNow}
          startIcon={status.nextRetryIn > 0 ? <CircularProgress size={16} /> : <Refresh />}
          variant="contained"
          disabled={status.nextRetryIn > 0}
          size="large"
        >
          {status.nextRetryIn > 0 
            ? t('serverDown.retrying', 'Retrying...') 
            : t('serverDown.retryNow', 'Retry Now')
          }
        </Button>

        {status.retryCount > 3 && status.retryCount < 10 && (
          <Button
            onClick={handleResetRetries}
            variant="outlined"
            size="large"
          >
            {t('serverDown.resetRetries', 'Reset Retries')}
          </Button>
        )}
      </DialogActions>
    </Dialog>
  );
};

export default ServerDownModal;