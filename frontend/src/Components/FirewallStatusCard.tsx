import React, { useEffect, useState, useRef, useCallback } from 'react';
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
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
  IconButton,
} from '@mui/material';
import SecurityIcon from '@mui/icons-material/Security';
import CheckCircleIcon from '@mui/icons-material/CheckCircle';
import CancelIcon from '@mui/icons-material/Cancel';
import WarningIcon from '@mui/icons-material/Warning';
import DeleteIcon from '@mui/icons-material/Delete';
import AddIcon from '@mui/icons-material/Add';
import { useTranslation } from 'react-i18next';
import { FirewallStatus, PortWithProtocols, getFirewallStatus } from '../Services/firewallService';
import { SecurityRoles, hasPermission } from '../Services/permissions';
import { deployFirewall, enableFirewall, disableFirewall, restartFirewall } from '../Services/firewallOperationsService';
import axiosInstance from '../Services/api';

interface FirewallStatusCardProps {
  hostId: string;
  refreshTrigger?: number;
}

interface FirewallRole {
  id: string;
  name: string;
}

interface HostFirewallRoleAssignment {
  id: string;
  firewall_role_id: string;
  firewall_role_name: string;
  created_at: string;
}

interface ExpectedPorts {
  ipv4_ports: PortWithProtocols[];
  ipv6_ports: PortWithProtocols[];
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

  // Firewall roles state
  const [hostFirewallRoles, setHostFirewallRoles] = useState<HostFirewallRoleAssignment[]>([]);
  const [allFirewallRoles, setAllFirewallRoles] = useState<FirewallRole[]>([]);
  const [expectedPorts, setExpectedPorts] = useState<ExpectedPorts | null>(null);
  const [rolesDialogOpen, setRolesDialogOpen] = useState(false);
  const [selectedRoleToAdd, setSelectedRoleToAdd] = useState<string>('');
  const [pendingRoles, setPendingRoles] = useState<HostFirewallRoleAssignment[]>([]);
  const [rolesToRemove, setRolesToRemove] = useState<string[]>([]);
  const [savingRoles, setSavingRoles] = useState(false);

  // Permission states
  const [canDeployFirewall, setCanDeployFirewall] = useState<boolean>(false);
  const [canRemoveFirewall, setCanRemoveFirewall] = useState<boolean>(false);
  const [canEnableFirewall, setCanEnableFirewall] = useState<boolean>(false);
  const [canDisableFirewall, setCanDisableFirewall] = useState<boolean>(false);
  const [canRestartFirewall, setCanRestartFirewall] = useState<boolean>(false);
  const [canAssignFirewallRoles, setCanAssignFirewallRoles] = useState<boolean>(false);
  const [canViewFirewallRoles, setCanViewFirewallRoles] = useState<boolean>(false);

  // Check permissions
  useEffect(() => {
    const checkPermissions = async () => {
      const [deploy, remove, enable, disable, restart, assignRoles, viewRoles] = await Promise.all([
        hasPermission(SecurityRoles.DEPLOY_FIREWALL),
        hasPermission(SecurityRoles.REMOVE_FIREWALL),
        hasPermission(SecurityRoles.ENABLE_FIREWALL),
        hasPermission(SecurityRoles.DISABLE_FIREWALL),
        hasPermission(SecurityRoles.RESTART_FIREWALL),
        hasPermission(SecurityRoles.ASSIGN_HOST_FIREWALL_ROLES),
        hasPermission(SecurityRoles.VIEW_FIREWALL_ROLES),
      ]);
      setCanDeployFirewall(deploy);
      setCanRemoveFirewall(remove);
      setCanEnableFirewall(enable);
      setCanDisableFirewall(disable);
      setCanRestartFirewall(restart);
      setCanAssignFirewallRoles(assignRoles);
      setCanViewFirewallRoles(viewRoles);
    };
    checkPermissions();
  }, []);

  // Load host firewall roles
  const loadHostFirewallRoles = useCallback(async () => {
    if (!canViewFirewallRoles) return;
    try {
      const response = await axiosInstance.get<HostFirewallRoleAssignment[]>(
        `/api/firewall-roles/host/${hostId}/roles`
      );
      setHostFirewallRoles(response.data);
    } catch (err) {
      console.error('Error loading host firewall roles:', err);
    }
  }, [hostId, canViewFirewallRoles]);

  // Load all available firewall roles
  const loadAllFirewallRoles = useCallback(async () => {
    if (!canViewFirewallRoles) return;
    try {
      const response = await axiosInstance.get<FirewallRole[]>('/api/firewall-roles/');
      setAllFirewallRoles(response.data);
    } catch (err) {
      console.error('Error loading firewall roles:', err);
    }
  }, [canViewFirewallRoles]);

  // Load expected ports from firewall roles
  const loadExpectedPorts = useCallback(async () => {
    if (!canViewFirewallRoles) return;
    try {
      const response = await axiosInstance.get<ExpectedPorts>(
        `/api/firewall-roles/host/${hostId}/expected-ports`
      );
      setExpectedPorts(response.data);
    } catch (err) {
      console.error('Error loading expected ports:', err);
    }
  }, [hostId, canViewFirewallRoles]);

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

  // Load firewall roles when permission is available
  useEffect(() => {
    if (hostId && canViewFirewallRoles) {
      loadHostFirewallRoles();
      loadAllFirewallRoles();
      loadExpectedPorts();
    }
  }, [hostId, canViewFirewallRoles, loadHostFirewallRoles, loadAllFirewallRoles, loadExpectedPorts, refreshTrigger]);

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

  // Open roles dialog
  const handleOpenRolesDialog = () => {
    setPendingRoles([...hostFirewallRoles]);
    setRolesToRemove([]);
    setSelectedRoleToAdd('');
    setRolesDialogOpen(true);
  };

  // Close roles dialog
  const handleCloseRolesDialog = () => {
    setRolesDialogOpen(false);
    setPendingRoles([]);
    setRolesToRemove([]);
    setSelectedRoleToAdd('');
  };

  // Add role to pending list
  const handleAddRoleToPending = () => {
    if (!selectedRoleToAdd) return;

    // Check if already in pending list
    if (pendingRoles.some(r => r.firewall_role_id === selectedRoleToAdd)) {
      return;
    }

    // If it was previously marked for removal, unmark it
    if (rolesToRemove.includes(selectedRoleToAdd)) {
      setRolesToRemove(rolesToRemove.filter(id => id !== selectedRoleToAdd));
      // Find the original assignment
      const original = hostFirewallRoles.find(r => r.firewall_role_id === selectedRoleToAdd);
      if (original) {
        setPendingRoles([...pendingRoles, original]);
      }
    } else {
      // Add as new
      const role = allFirewallRoles.find(r => r.id === selectedRoleToAdd);
      if (role) {
        setPendingRoles([
          ...pendingRoles,
          {
            id: `new-${Date.now()}`, // Temporary ID for new assignments
            firewall_role_id: role.id,
            firewall_role_name: role.name,
            created_at: new Date().toISOString(),
          },
        ]);
      }
    }
    setSelectedRoleToAdd('');
  };

  // Remove role from pending list
  const handleRemoveRoleFromPending = (roleId: string) => {
    const role = pendingRoles.find(r => r.firewall_role_id === roleId);
    if (!role) return;

    // If it's an existing assignment (not a new one), mark for removal
    if (!role.id.startsWith('new-')) {
      setRolesToRemove([...rolesToRemove, roleId]);
    }
    setPendingRoles(pendingRoles.filter(r => r.firewall_role_id !== roleId));
  };

  // Save role changes
  const handleSaveRoles = async () => {
    setSavingRoles(true);
    try {
      // Remove roles marked for removal
      for (const roleId of rolesToRemove) {
        const assignment = hostFirewallRoles.find(r => r.firewall_role_id === roleId);
        if (assignment) {
          await axiosInstance.delete(`/api/firewall-roles/host/${hostId}/roles/${assignment.id}`);
        }
      }

      // Add new roles
      for (const role of pendingRoles) {
        if (role.id.startsWith('new-')) {
          await axiosInstance.post(`/api/firewall-roles/host/${hostId}/roles`, {
            firewall_role_id: role.firewall_role_id,
          });
        }
      }

      // Reload host firewall roles and expected ports
      await loadHostFirewallRoles();
      await loadExpectedPorts();
      handleCloseRolesDialog();
    } catch (err) {
      console.error('Error saving firewall roles:', err);
      setError(t('security.firewallRolesSaveError', 'Failed to save firewall roles'));
    } finally {
      setSavingRoles(false);
    }
  };

  // Get available roles (not already assigned in pending list)
  const getAvailableRoles = () => {
    return allFirewallRoles.filter(
      role => !pendingRoles.some(p => p.firewall_role_id === role.id)
    );
  };

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

  // Merge actual ports with expected ports from firewall roles
  // Expected ports that aren't in actual ports will be shown as well
  const mergePorts = (actualPorts: PortWithProtocols[], expectedPorts: PortWithProtocols[]): PortWithProtocols[] => {
    const merged = [...actualPorts];

    for (const expectedPort of expectedPorts) {
      // Check if this port is already in the actual ports
      const exists = merged.some(p => p.port === expectedPort.port);
      if (!exists) {
        merged.push(expectedPort);
      }
    }

    // Sort by port number
    return merged.sort((a, b) => parseInt(a.port) - parseInt(b.port));
  };

  const actualIpv4Ports = parsePortsWithProtocols(firewallStatus?.ipv4_ports || null);
  const actualIpv6Ports = parsePortsWithProtocols(firewallStatus?.ipv6_ports || null);

  // Merge with expected ports from firewall roles
  const ipv4Ports = expectedPorts
    ? mergePorts(actualIpv4Ports, expectedPorts.ipv4_ports)
    : actualIpv4Ports;
  const ipv6Ports = expectedPorts
    ? mergePorts(actualIpv6Ports, expectedPorts.ipv6_ports)
    : actualIpv6Ports;

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

  const isFirewallInstalledAndEnabled = firewallStatus?.firewall_name && firewallStatus?.enabled;

  return (
    <>
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

              {/* Firewall Roles - only show if user can view and there are roles */}
              {canViewFirewallRoles && (
                <Box>
                  <Typography variant="body2" color="text.secondary" gutterBottom>
                    {t('security.firewallRoles', 'Firewall Roles')}
                  </Typography>
                  {hostFirewallRoles.length === 0 ? (
                    <Typography variant="body2" color="text.secondary" fontStyle="italic">
                      {t('security.noFirewallRolesAssigned', 'No firewall roles assigned')}
                    </Typography>
                  ) : (
                    <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.5 }}>
                      {hostFirewallRoles.map((assignment) => (
                        <Chip
                          key={assignment.id}
                          label={assignment.firewall_role_name}
                          size="small"
                          color="primary"
                          variant="outlined"
                        />
                      ))}
                    </Box>
                  )}
                </Box>
              )}

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
              {(canAssignFirewallRoles || canRemoveFirewall || canEnableFirewall || canDisableFirewall || canRestartFirewall) && (
                <Box sx={{ display: 'flex', gap: 1, mt: 2, flexWrap: 'wrap' }}>
                  {/* Edit Roles Button - only show if firewall is installed and enabled */}
                  {canAssignFirewallRoles && isFirewallInstalledAndEnabled && (
                    <Button
                      variant="outlined"
                      color="primary"
                      size="small"
                      onClick={handleOpenRolesDialog}
                    >
                      {t('security.editRoles', 'Edit Roles')}
                    </Button>
                  )}

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

      {/* Edit Roles Dialog */}
      <Dialog open={rolesDialogOpen} onClose={handleCloseRolesDialog} maxWidth="sm" fullWidth>
        <DialogTitle>{t('security.editFirewallRoles', 'Edit Firewall Roles')}</DialogTitle>
        <DialogContent dividers>
          <Stack spacing={3}>
            {/* Add Role Section */}
            <Box>
              <Typography variant="subtitle2" gutterBottom>
                {t('security.addRole', 'Add Role')}
              </Typography>
              <Stack direction="row" spacing={2} alignItems="center">
                <FormControl sx={{ minWidth: 250 }} size="small">
                  <InputLabel>{t('security.selectRole', 'Select Role')}</InputLabel>
                  <Select
                    value={selectedRoleToAdd}
                    label={t('security.selectRole', 'Select Role')}
                    onChange={(e) => setSelectedRoleToAdd(e.target.value)}
                  >
                    {getAvailableRoles().map((role) => (
                      <MenuItem key={role.id} value={role.id}>
                        {role.name}
                      </MenuItem>
                    ))}
                  </Select>
                </FormControl>
                <Button
                  variant="outlined"
                  startIcon={<AddIcon />}
                  onClick={handleAddRoleToPending}
                  disabled={!selectedRoleToAdd}
                >
                  {t('common.add', 'Add')}
                </Button>
              </Stack>
            </Box>

            {/* Assigned Roles Section */}
            <Box>
              <Typography variant="subtitle2" gutterBottom>
                {t('security.assignedRoles', 'Assigned Roles')}
              </Typography>
              {pendingRoles.length === 0 ? (
                <Typography variant="body2" color="text.secondary" fontStyle="italic">
                  {t('security.noRolesAssigned', 'No roles assigned')}
                </Typography>
              ) : (
                <Stack spacing={1}>
                  {pendingRoles.map((role) => (
                    <Box
                      key={role.firewall_role_id}
                      sx={{
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'space-between',
                        p: 1,
                        border: '1px solid',
                        borderColor: 'divider',
                        borderRadius: 1,
                      }}
                    >
                      <Typography variant="body2">{role.firewall_role_name}</Typography>
                      <IconButton
                        size="small"
                        color="error"
                        onClick={() => handleRemoveRoleFromPending(role.firewall_role_id)}
                      >
                        <DeleteIcon fontSize="small" />
                      </IconButton>
                    </Box>
                  ))}
                </Stack>
              )}
            </Box>
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={handleCloseRolesDialog}>{t('common.cancel', 'Cancel')}</Button>
          <Button
            variant="contained"
            onClick={handleSaveRoles}
            disabled={savingRoles}
          >
            {savingRoles ? <CircularProgress size={24} /> : t('common.save', 'Save')}
          </Button>
        </DialogActions>
      </Dialog>
    </>
  );
};

export default FirewallStatusCard;
