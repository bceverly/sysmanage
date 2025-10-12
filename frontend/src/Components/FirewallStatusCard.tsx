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
import SecurityIcon from '@mui/icons-material/Security';
import CheckCircleIcon from '@mui/icons-material/CheckCircle';
import CancelIcon from '@mui/icons-material/Cancel';
import WarningIcon from '@mui/icons-material/Warning';
import { useTranslation } from 'react-i18next';
import { FirewallStatus, PortWithProtocols, getFirewallStatus } from '../Services/firewallService';
import { SecurityRoles, hasPermission } from '../Services/permissions';
import { deployFirewall, enableFirewall, disableFirewall, restartFirewall } from '../Services/firewallOperationsService';

interface FirewallStatusCardProps {
  hostId: string;
  refreshTrigger?: number;
}

const FirewallStatusCard: React.FC<FirewallStatusCardProps> = ({
  hostId,
  refreshTrigger = 0,
}) => {
  const { t } = useTranslation();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [firewallStatus, setFirewallStatus] = useState<FirewallStatus | null>(null);
  const isInitialLoad = useRef(true);

  // Permission states
  const [canDeployFirewall, setCanDeployFirewall] = useState<boolean>(false);
  const [canRemoveFirewall, setCanRemoveFirewall] = useState<boolean>(false);
  const [canEnableFirewall, setCanEnableFirewall] = useState<boolean>(false);
  const [canDisableFirewall, setCanDisableFirewall] = useState<boolean>(false);
  const [canRestartFirewall, setCanRestartFirewall] = useState<boolean>(false);

  // Check permissions
  useEffect(() => {
    const checkPermissions = async () => {
      const [deploy, remove, enable, disable, restart] = await Promise.all([
        hasPermission(SecurityRoles.DEPLOY_FIREWALL),
        hasPermission(SecurityRoles.REMOVE_FIREWALL),
        hasPermission(SecurityRoles.ENABLE_FIREWALL),
        hasPermission(SecurityRoles.DISABLE_FIREWALL),
        hasPermission(SecurityRoles.RESTART_FIREWALL)
      ]);
      setCanDeployFirewall(deploy);
      setCanRemoveFirewall(remove);
      setCanEnableFirewall(enable);
      setCanDisableFirewall(disable);
      setCanRestartFirewall(restart);
    };
    checkPermissions();
  }, []);

  useEffect(() => {
    const fetchFirewallStatus = async () => {
      // Only show loading spinner on initial load, not on refresh
      if (isInitialLoad.current) {
        setLoading(true);
      }
      setError(null);
      try {
        const status = await getFirewallStatus(hostId);
        setFirewallStatus(status);
        isInitialLoad.current = false;
      } catch (err) {
        console.error('Error fetching firewall status:', err);
        setError(t('security.firewallError', 'Failed to load firewall status'));
      } finally {
        setLoading(false);
      }
    };

    if (hostId) {
      fetchFirewallStatus();
    }
  }, [hostId, t, refreshTrigger]);

  // Auto-refresh every 30 seconds
  useEffect(() => {
    if (!hostId) return;

    const intervalId = setInterval(async () => {
      try {
        const status = await getFirewallStatus(hostId);
        setFirewallStatus(status);
      } catch (err) {
        console.error('Error refreshing firewall status:', err);
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

  const parsePortsWithProtocols = (portsJson: string | null): PortWithProtocols[] => {
    if (!portsJson) return [];
    try {
      const parsed = JSON.parse(portsJson);
      return Array.isArray(parsed) ? parsed : [];
    } catch {
      return [];
    }
  };

  const ipv4Ports = parsePortsWithProtocols(firewallStatus?.ipv4_ports || null);
  const ipv6Ports = parsePortsWithProtocols(firewallStatus?.ipv6_ports || null);

  const handleDeployFirewall = async () => {
    try {
      await deployFirewall(hostId);
      // Refresh firewall status after a delay to allow command to execute
      setTimeout(async () => {
        try {
          const status = await getFirewallStatus(hostId);
          setFirewallStatus(status);
        } catch (err) {
          console.error('Error refreshing firewall status:', err);
        }
      }, 10000);
    } catch (err) {
      console.error('Error deploying firewall:', err);
      setError(t('security.firewallDeployError', 'Failed to deploy firewall'));
    }
  };

  const handleRemoveFirewall = async () => {
    // TODO: Implement remove firewall functionality
    console.log('Remove firewall clicked');
  };

  const handleEnableFirewall = async () => {
    try {
      await enableFirewall(hostId);
      // Refresh firewall status after a delay to allow command to execute
      setTimeout(async () => {
        try {
          const status = await getFirewallStatus(hostId);
          setFirewallStatus(status);
        } catch (err) {
          console.error('Error refreshing firewall status:', err);
        }
      }, 10000);
    } catch (err) {
      console.error('Error enabling firewall:', err);
      setError(t('security.firewallEnableError', 'Failed to enable firewall'));
    }
  };

  const handleDisableFirewall = async () => {
    try {
      await disableFirewall(hostId);
      // Refresh firewall status after a delay
      setTimeout(async () => {
        try {
          const status = await getFirewallStatus(hostId);
          setFirewallStatus(status);
        } catch (err) {
          console.error('Error refreshing firewall status:', err);
        }
      }, 10000);
    } catch (err) {
      console.error('Error disabling firewall:', err);
      setError(t('security.firewallDisableError', 'Failed to disable firewall'));
    }
  };

  const handleRestartFirewall = async () => {
    try {
      await restartFirewall(hostId);
      // Refresh firewall status after a delay
      setTimeout(async () => {
        try {
          const status = await getFirewallStatus(hostId);
          setFirewallStatus(status);
        } catch (err) {
          console.error('Error refreshing firewall status:', err);
        }
      }, 10000);
    } catch (err) {
      console.error('Error restarting firewall:', err);
      setError(t('security.firewallRestartError', 'Failed to restart firewall'));
    }
  };

  return (
    <Card>
      <CardContent>
        <Typography variant="subtitle1" sx={{ display: 'flex', alignItems: 'center', fontWeight: 'bold', fontSize: '1.1rem', mb: 2 }}>
          <SecurityIcon sx={{ mr: 1 }} />
          {t('security.firewall', 'Firewall')}
        </Typography>

        {!firewallStatus || !firewallStatus.firewall_name ? (
          <Box sx={{ display: 'flex', alignItems: 'center', py: 2 }}>
            <WarningIcon sx={{ mr: 1, color: 'warning.main' }} />
            <Typography variant="body2" color="text.secondary">
              {t('security.noFirewallDetected', 'No firewall detected')}
            </Typography>
          </Box>
        ) : (
          <Stack spacing={2}>
            <Box>
              <Typography variant="body2" color="text.secondary" gutterBottom>
                {t('security.firewallSoftware', 'Firewall Software')}
              </Typography>
              <Typography variant="body1" fontWeight="medium">
                {firewallStatus.firewall_name}
              </Typography>
            </Box>

            <Box>
              <Typography variant="body2" color="text.secondary" gutterBottom>
                {t('security.status', 'Status')}
              </Typography>
              {firewallStatus.enabled ? (
                <Chip
                  icon={<CheckCircleIcon />}
                  label={t('security.enabled', 'Enabled')}
                  color="success"
                  size="small"
                />
              ) : (
                <Chip
                  icon={<CancelIcon />}
                  label={t('security.disabled', 'Disabled')}
                  color="error"
                  size="small"
                />
              )}
            </Box>

            {ipv4Ports.length > 0 && (
              <Box>
                <Typography variant="body2" color="text.secondary" gutterBottom>
                  {t('security.ipv4OpenPorts', 'IPv4 Open Ports')}
                </Typography>
                <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.5 }}>
                  {ipv4Ports.map((portInfo, idx) => (
                    <Chip
                      key={idx}
                      label={`${portInfo.port} (${portInfo.protocols.join('/')})`}
                      size="small"
                      variant="outlined"
                    />
                  ))}
                </Box>
              </Box>
            )}

            {ipv6Ports.length > 0 && (
              <Box>
                <Typography variant="body2" color="text.secondary" gutterBottom>
                  {t('security.ipv6OpenPorts', 'IPv6 Open Ports')}
                </Typography>
                <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.5 }}>
                  {ipv6Ports.map((portInfo, idx) => (
                    <Chip
                      key={idx}
                      label={`${portInfo.port} (${portInfo.protocols.join('/')})`}
                      size="small"
                      variant="outlined"
                    />
                  ))}
                </Box>
              </Box>
            )}

            {ipv4Ports.length === 0 && ipv6Ports.length === 0 && (
              <Box>
                <Typography variant="body2" color="text.secondary">
                  {t('security.noOpenPorts', 'No open ports detected')}
                </Typography>
              </Box>
            )}

            {firewallStatus.last_updated && (
              <Box>
                <Typography variant="body2" color="text.secondary" gutterBottom>
                  {t('security.lastUpdated', 'Last Updated')}
                </Typography>
                <Typography variant="body2">
                  {formatDate(firewallStatus.last_updated)}
                </Typography>
              </Box>
            )}

            {/* Firewall Action Buttons - only show when firewall is detected */}
            {(canRemoveFirewall || canEnableFirewall || canDisableFirewall || canRestartFirewall) && (
              <Box sx={{ display: 'flex', gap: 1, mt: 2, flexWrap: 'wrap' }}>
                {/* Remove Button */}
                {canRemoveFirewall && (
                  <Button
                    variant="contained"
                    color="error"
                    size="small"
                    onClick={handleRemoveFirewall}
                  >
                    {t('security.removeFirewall', 'Remove Firewall')}
                  </Button>
                )}

                {/* Enable Button - only show if firewall is disabled */}
                {canEnableFirewall && !firewallStatus.enabled && (
                  <Button
                    variant="contained"
                    color="primary"
                    size="small"
                    onClick={handleEnableFirewall}
                  >
                    {t('security.enableFirewall', 'Enable Firewall')}
                  </Button>
                )}

                {/* Disable Button - only show if firewall is enabled */}
                {canDisableFirewall && firewallStatus.enabled && (
                  <Button
                    variant="contained"
                    color="warning"
                    size="small"
                    onClick={handleDisableFirewall}
                  >
                    {t('security.disableFirewall', 'Disable Firewall')}
                  </Button>
                )}

                {/* Restart Button - only show if firewall is enabled */}
                {canRestartFirewall && firewallStatus.enabled && (
                  <Button
                    variant="contained"
                    color="primary"
                    size="small"
                    onClick={handleRestartFirewall}
                  >
                    {t('security.restartFirewall', 'Restart Firewall')}
                  </Button>
                )}
              </Box>
            )}
          </Stack>
        )}

        {/* Deploy button when no firewall is detected */}
        {(!firewallStatus || !firewallStatus.firewall_name) && canDeployFirewall && (
          <Box sx={{ display: 'flex', gap: 1, mt: 2 }}>
            <Button
              variant="contained"
              color="success"
              size="small"
              onClick={handleDeployFirewall}
            >
              {t('security.deployFirewall', 'Deploy Firewall')}
            </Button>
          </Box>
        )}
      </CardContent>
    </Card>
  );
};

export default FirewallStatusCard;
