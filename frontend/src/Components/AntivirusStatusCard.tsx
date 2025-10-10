import React, { useEffect, useState, useRef } from 'react';
import {
  Card,
  CardContent,
  Typography,
  Box,
  Chip,
  CircularProgress,
  Alert,
  Stack,
  Button,
} from '@mui/material';
import ShieldIcon from '@mui/icons-material/Shield';
import CheckCircleIcon from '@mui/icons-material/CheckCircle';
import CancelIcon from '@mui/icons-material/Cancel';
import WarningIcon from '@mui/icons-material/Warning';
import SecurityIcon from '@mui/icons-material/Security';
import { useTranslation } from 'react-i18next';
import { AntivirusStatus, getAntivirusStatus } from '../Services/antivirusService';

interface AntivirusStatusCardProps {
  hostId: string;
  onDeployAntivirus?: () => void;
  onEnableAntivirus?: () => void;
  onDisableAntivirus?: () => void;
  onRemoveAntivirus?: () => void;
  canDeployAntivirus?: boolean;
  canEnableAntivirus?: boolean;
  canDisableAntivirus?: boolean;
  canRemoveAntivirus?: boolean;
  isHostActive?: boolean;
  isAgentPrivileged?: boolean;
  hasOsDefault?: boolean;
  refreshTrigger?: number;
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
}) => {
  const { t } = useTranslation();
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
      fetchAntivirusStatus();
    }
  }, [hostId, t, refreshTrigger]);

  // Auto-refresh every 30 seconds
  useEffect(() => {
    if (!hostId) return;

    const intervalId = setInterval(async () => {
      try {
        const status = await getAntivirusStatus(hostId);
        setAntivirusStatus(status);
      } catch (err) {
        console.error('Error refreshing antivirus status:', err);
      }
    }, 30000); // 30 seconds

    return () => clearInterval(intervalId);
  }, [hostId]);

  if (loading) {
    return (
      <Card>
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
      <Card>
        <CardContent>
          <Alert severity="error">{error}</Alert>
        </CardContent>
      </Card>
    );
  }

  const formatDate = (dateString: string) => {
    const date = new Date(dateString);
    return date.toLocaleString();
  };

  return (
    <Card>
      <CardContent>
        <Typography variant="subtitle1" sx={{ display: 'flex', alignItems: 'center', fontWeight: 'bold', fontSize: '1.1rem', mb: 2 }}>
          <ShieldIcon sx={{ mr: 1 }} />
          {t('security.antivirus', 'Antivirus')}
        </Typography>

        {!antivirusStatus || !antivirusStatus.software_name ? (
          <Box sx={{ display: 'flex', alignItems: 'center', py: 2 }}>
            <WarningIcon sx={{ mr: 1, color: 'warning.main' }} />
            <Typography variant="body2" color="text.secondary">
              {t('security.noAntivirusDetected', 'No antivirus software detected')}
            </Typography>
          </Box>
        ) : (
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
              {antivirusStatus.enabled === true ? (
                <Chip
                  icon={<CheckCircleIcon />}
                  label={t('security.enabled', 'Enabled')}
                  color="success"
                  size="small"
                />
              ) : antivirusStatus.enabled === false ? (
                <Chip
                  icon={<CancelIcon />}
                  label={t('security.disabled', 'Disabled')}
                  color="error"
                  size="small"
                />
              ) : (
                <Chip
                  label={t('security.unknown', 'Unknown')}
                  size="small"
                />
              )}
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
        )}

        {/* Antivirus Action Buttons */}
        <Box sx={{ mt: 3, display: 'flex', gap: 1, flexWrap: 'wrap' }}>
          {/* Deploy Button */}
          {canDeployAntivirus && onDeployAntivirus && (
            <Button
              variant="contained"
              color="success"
              startIcon={<SecurityIcon />}
              onClick={onDeployAntivirus}
              disabled={
                !isHostActive ||
                !isAgentPrivileged ||
                !hasOsDefault ||
                (antivirusStatus && antivirusStatus.software_name !== null && antivirusStatus.software_name !== '')
              }
              title={
                antivirusStatus && antivirusStatus.software_name
                  ? t('security.alreadyDeployed', 'Antivirus already deployed')
                  : !hasOsDefault
                  ? t('hostDetail.noAntivirusDefault', 'No antivirus default configured for this OS')
                  : !isAgentPrivileged
                  ? t('hostDetail.notPrivileged', 'Agent not running in privileged mode')
                  : !isHostActive
                  ? t('hostDetail.hostInactive', 'Host is not active')
                  : ''
              }
            >
              {t('hostDetail.deployAntivirus', 'Deploy Antivirus')}
            </Button>
          )}

          {/* Remove Button */}
          {canRemoveAntivirus && onRemoveAntivirus && (
            <Button
              variant="contained"
              color="error"
              onClick={onRemoveAntivirus}
              disabled={
                !isHostActive ||
                !isAgentPrivileged ||
                !antivirusStatus ||
                !antivirusStatus.software_name
              }
              title={
                !antivirusStatus || !antivirusStatus.software_name
                  ? t('security.notDeployed', 'No antivirus deployed')
                  : !isAgentPrivileged
                  ? t('hostDetail.notPrivileged', 'Agent not running in privileged mode')
                  : !isHostActive
                  ? t('hostDetail.hostInactive', 'Host is not active')
                  : ''
              }
            >
              {t('security.removeAntivirus', 'Remove Antivirus')}
            </Button>
          )}

          {/* Enable Button */}
          {canEnableAntivirus && onEnableAntivirus && antivirusStatus && antivirusStatus.software_name && (
            <Button
              variant="contained"
              color="primary"
              onClick={onEnableAntivirus}
              disabled={
                !isHostActive ||
                !isAgentPrivileged ||
                antivirusStatus.enabled === true
              }
              title={
                antivirusStatus.enabled === true
                  ? t('security.alreadyEnabled', 'Antivirus already enabled')
                  : !isAgentPrivileged
                  ? t('hostDetail.notPrivileged', 'Agent not running in privileged mode')
                  : !isHostActive
                  ? t('hostDetail.hostInactive', 'Host is not active')
                  : ''
              }
            >
              {t('security.enableAntivirus', 'Enable Antivirus')}
            </Button>
          )}

          {/* Disable Button */}
          {canDisableAntivirus && onDisableAntivirus && antivirusStatus && antivirusStatus.software_name && (
            <Button
              variant="contained"
              color="warning"
              onClick={onDisableAntivirus}
              disabled={
                !isHostActive ||
                !isAgentPrivileged ||
                antivirusStatus.enabled === false
              }
              title={
                antivirusStatus.enabled === false
                  ? t('security.alreadyDisabled', 'Antivirus already disabled')
                  : !isAgentPrivileged
                  ? t('hostDetail.notPrivileged', 'Agent not running in privileged mode')
                  : !isHostActive
                  ? t('hostDetail.hostInactive', 'Host is not active')
                  : ''
              }
            >
              {t('security.disableAntivirus', 'Disable Antivirus')}
            </Button>
          )}
        </Box>
      </CardContent>
    </Card>
  );
};

export default AntivirusStatusCard;
