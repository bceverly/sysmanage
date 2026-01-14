import React from 'react';
import {
  Card,
  CardContent,
  Typography,
  Box,
  Chip,
  Button,
  CircularProgress,
  Stack,
  Tooltip,
} from '@mui/material';
import CheckCircleIcon from '@mui/icons-material/CheckCircle';
import CancelIcon from '@mui/icons-material/Cancel';
import AddIcon from '@mui/icons-material/Add';
import PlayArrowIcon from '@mui/icons-material/PlayArrow';
import StopIcon from '@mui/icons-material/Stop';
import SettingsIcon from '@mui/icons-material/Settings';
import DownloadIcon from '@mui/icons-material/Download';
import ComputerIcon from '@mui/icons-material/Computer';
import StorageIcon from '@mui/icons-material/Storage';
import DnsIcon from '@mui/icons-material/Dns';
import TerminalIcon from '@mui/icons-material/Terminal';
import MemoryIcon from '@mui/icons-material/Memory';
import { useTranslation } from 'react-i18next';

export interface HypervisorCapabilities {
  available?: boolean;
  installed?: boolean;
  enabled?: boolean;
  running?: boolean;
  initialized?: boolean;
  needs_enable?: boolean;
  needs_install?: boolean;
  needs_init?: boolean;
  needs_bios_virtualization?: boolean;
  kernel_supported?: boolean;
  version?: string;
  // KVM-specific module state
  modules_loaded?: boolean;
  modules_available?: boolean;
  needs_modprobe?: boolean;
  cpu_vendor?: string;
  // bhyve-specific UEFI firmware state
  uefi_available?: boolean;
}

export type HypervisorType = 'bhyve' | 'kvm' | 'lxd' | 'vmm' | 'wsl';

interface HypervisorStatusCardProps {
  type: HypervisorType;
  capabilities: HypervisorCapabilities | undefined;
  onEnable?: () => void;
  onDisable?: () => void;
  onCreate?: () => void;
  onEnableModules?: () => void;
  onDisableModules?: () => void;
  canEnable?: boolean;
  canCreate?: boolean;
  isLoading?: boolean;
  isEnableLoading?: boolean;
  isDisableLoading?: boolean;
  isModulesLoading?: boolean;
  isAgentPrivileged?: boolean;
  rebootRequired?: boolean;
}

const HypervisorStatusCard: React.FC<HypervisorStatusCardProps> = ({
  type,
  capabilities,
  onEnable,
  onDisable,
  onCreate,
  onEnableModules,
  onDisableModules,
  canEnable = false,
  canCreate = false,
  isLoading = false,
  isEnableLoading = false,
  isDisableLoading = false,
  isModulesLoading = false,
  isAgentPrivileged = false,
  rebootRequired = false,
}) => {
  const { t } = useTranslation();

  // Get hypervisor display info
  const getHypervisorInfo = () => {
    switch (type) {
      case 'bhyve':
        return {
          name: t('hostDetail.hypervisor.bhyve.name', 'bhyve'),
          description: t('hostDetail.hypervisor.bhyve.description', 'FreeBSD hypervisor'),
          icon: <ComputerIcon />,
          createLabel: t('hostDetail.hypervisor.bhyve.createLabel', 'Create VM'),
          enableLabel: t('hostDetail.hypervisor.bhyve.enableLabel', 'Enable bhyve'),
          disableLabel: t('hostDetail.hypervisor.bhyve.disableLabel', 'Disable bhyve'),
        };
      case 'kvm':
        return {
          name: t('hostDetail.hypervisor.kvm.name', 'KVM/QEMU'),
          description: t('hostDetail.hypervisor.kvm.description', 'Linux kernel-based virtualization'),
          icon: <StorageIcon />,
          createLabel: t('hostDetail.hypervisor.kvm.createLabel', 'Create VM'),
          enableLabel: t('hostDetail.hypervisor.kvm.enableLabel', 'Enable KVM'),
        };
      case 'lxd':
        return {
          name: t('hostDetail.hypervisor.lxd.name', 'LXD'),
          description: t('hostDetail.hypervisor.lxd.description', 'Linux container management'),
          icon: <DnsIcon />,
          createLabel: t('hostDetail.hypervisor.lxd.createLabel', 'Create Container'),
          enableLabel: t('hostDetail.hypervisor.lxd.enableLabel', 'Enable LXD'),
        };
      case 'vmm':
        return {
          name: t('hostDetail.hypervisor.vmm.name', 'VMM/vmd'),
          description: t('hostDetail.hypervisor.vmm.description', 'OpenBSD virtual machine monitor'),
          icon: <ComputerIcon />,
          createLabel: t('hostDetail.hypervisor.vmm.createLabel', 'Create VM'),
          enableLabel: t('hostDetail.hypervisor.vmm.enableLabel', 'Enable VMM'),
        };
      case 'wsl':
        return {
          name: t('hostDetail.hypervisor.wsl.name', 'WSL'),
          description: t('hostDetail.hypervisor.wsl.description', 'Windows Subsystem for Linux'),
          icon: <TerminalIcon />,
          createLabel: t('hostDetail.hypervisor.wsl.createLabel', 'Create Instance'),
          enableLabel: t('hostDetail.hypervisor.wsl.enableLabel', 'Enable WSL'),
        };
      default:
        return {
          name: type.toUpperCase(),
          description: '',
          icon: <ComputerIcon />,
          createLabel: t('hostDetail.hypervisor.createLabel', 'Create'),
          enableLabel: t('hostDetail.hypervisor.enableLabel', 'Enable'),
        };
    }
  };

  const hypervisorInfo = getHypervisorInfo();

  // Determine current state and what action is needed
  const getState = () => {
    if (!capabilities) {
      return { state: 'unknown', color: 'default' as const, label: t('hostDetail.hypervisor.state.unknown', 'Unknown') };
    }

    // Check for BIOS virtualization requirement (WSL specific)
    if (capabilities.needs_bios_virtualization) {
      return {
        state: 'bios_required',
        color: 'error' as const,
        label: t('hostDetail.hypervisor.state.biosRequired', 'BIOS Virtualization Required')
      };
    }

    // Not available at all
    if (!capabilities.available) {
      return {
        state: 'not_available',
        color: 'default' as const,
        label: t('hostDetail.hypervisor.state.notAvailable', 'Not Available')
      };
    }

    // Check for VMM or bhyve kernel support
    if ((type === 'vmm' || type === 'bhyve') && capabilities.available && !capabilities.kernel_supported) {
      return {
        state: 'no_kernel_support',
        color: 'error' as const,
        label: t('hostDetail.hypervisor.state.noKernelSupport', 'No Kernel Support')
      };
    }

    // Fully ready
    if (type === 'wsl' && capabilities.enabled) {
      return { state: 'ready', color: 'success' as const, label: t('hostDetail.hypervisor.state.ready', 'Ready') };
    }
    if ((type === 'vmm' || type === 'bhyve') && capabilities.running) {
      return { state: 'ready', color: 'success' as const, label: t('hostDetail.hypervisor.state.ready', 'Ready') };
    }
    if ((type === 'kvm' || type === 'lxd') && capabilities.initialized) {
      return { state: 'ready', color: 'success' as const, label: t('hostDetail.hypervisor.state.ready', 'Ready') };
    }

    // Needs initialization (running but not initialized)
    if (type === 'kvm' && capabilities.running && !capabilities.initialized) {
      return {
        state: 'needs_init',
        color: 'warning' as const,
        label: t('hostDetail.hypervisor.state.needsInit', 'Needs Initialization')
      };
    }
    if (type === 'lxd' && capabilities.installed && !capabilities.initialized) {
      return {
        state: 'needs_init',
        color: 'warning' as const,
        label: t('hostDetail.hypervisor.state.needsInit', 'Needs Initialization')
      };
    }

    // Needs to be enabled/started
    if ((type === 'vmm' || type === 'bhyve') && capabilities.enabled && !capabilities.running) {
      return {
        state: 'not_running',
        color: 'warning' as const,
        label: t('hostDetail.hypervisor.state.notRunning', 'Not Running')
      };
    }

    // Installed but not enabled
    if (capabilities.installed && !capabilities.enabled) {
      return {
        state: 'not_enabled',
        color: 'warning' as const,
        label: t('hostDetail.hypervisor.state.notEnabled', 'Not Enabled')
      };
    }

    // Available but not installed
    if (capabilities.available && !capabilities.installed) {
      return {
        state: 'not_installed',
        color: 'warning' as const,
        label: t('hostDetail.hypervisor.state.notInstalled', 'Not Installed')
      };
    }

    // WSL needs enable
    if (type === 'wsl' && capabilities.needs_enable) {
      return {
        state: 'needs_enable',
        color: 'warning' as const,
        label: t('hostDetail.hypervisor.state.notEnabled', 'Not Enabled')
      };
    }

    // VMM or bhyve needs enable
    if ((type === 'vmm' || type === 'bhyve') && capabilities.needs_enable) {
      return {
        state: 'needs_enable',
        color: 'warning' as const,
        label: t('hostDetail.hypervisor.state.notEnabled', 'Not Enabled')
      };
    }

    // Available (generic fallback)
    return {
      state: 'available',
      color: 'info' as const,
      label: t('hostDetail.hypervisor.state.available', 'Available')
    };
  };

  const stateInfo = getState();
  const isReady = stateInfo.state === 'ready';
  const canShowEnableButton = !isReady &&
    stateInfo.state !== 'not_available' &&
    stateInfo.state !== 'bios_required' &&
    stateInfo.state !== 'no_kernel_support' &&
    stateInfo.state !== 'unknown';

  // Status indicators
  const StatusIndicator = ({
    checked,
    label
  }: {
    checked: boolean;
    label: string;
  }) => (
    <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
      {checked ? (
        <CheckCircleIcon sx={{ fontSize: 16, color: 'success.main' }} />
      ) : (
        <CancelIcon sx={{ fontSize: 16, color: 'text.disabled' }} />
      )}
      <Typography variant="caption" color={checked ? 'text.primary' : 'text.disabled'}>
        {label}
      </Typography>
    </Box>
  );

  // Get status indicators based on hypervisor type
  const getStatusIndicators = () => {
    if (!capabilities) return [];

    switch (type) {
      case 'kvm':
        return [
          { checked: !!capabilities.available, label: t('hostDetail.hypervisor.indicator.available', 'Available') },
          { checked: !!capabilities.modules_loaded, label: t('hostDetail.hypervisor.indicator.modulesLoaded', 'Modules Loaded') },
          { checked: !!capabilities.installed, label: t('hostDetail.hypervisor.indicator.installed', 'Installed') },
          { checked: !!capabilities.enabled, label: t('hostDetail.hypervisor.indicator.enabled', 'Enabled') },
          { checked: !!capabilities.running, label: t('hostDetail.hypervisor.indicator.running', 'Running') },
          { checked: !!capabilities.initialized, label: t('hostDetail.hypervisor.indicator.initialized', 'Initialized') },
        ];
      case 'lxd':
        return [
          { checked: !!capabilities.available, label: t('hostDetail.hypervisor.indicator.available', 'Available') },
          { checked: !!capabilities.installed, label: t('hostDetail.hypervisor.indicator.installed', 'Installed') },
          { checked: !!capabilities.initialized, label: t('hostDetail.hypervisor.indicator.initialized', 'Initialized') },
        ];
      case 'vmm':
        return [
          { checked: !!capabilities.available, label: t('hostDetail.hypervisor.indicator.available', 'Available') },
          { checked: !!capabilities.kernel_supported, label: t('hostDetail.hypervisor.indicator.kernelSupport', 'Kernel Support') },
          { checked: !!capabilities.enabled, label: t('hostDetail.hypervisor.indicator.enabled', 'Enabled') },
          { checked: !!capabilities.running, label: t('hostDetail.hypervisor.indicator.running', 'Running') },
        ];
      case 'bhyve':
        return [
          { checked: !!capabilities.available, label: t('hostDetail.hypervisor.indicator.available', 'Available') },
          { checked: !!capabilities.kernel_supported, label: t('hostDetail.hypervisor.indicator.cpuSupport', 'CPU Support') },
          { checked: !!capabilities.enabled, label: t('hostDetail.hypervisor.indicator.enabled', 'Enabled') },
          { checked: !!capabilities.running, label: t('hostDetail.hypervisor.indicator.running', 'Running') },
          { checked: !!capabilities.uefi_available, label: t('hostDetail.hypervisor.indicator.uefiAvailable', 'UEFI Firmware') },
        ];
      case 'wsl':
        return [
          { checked: !!capabilities.available, label: t('hostDetail.hypervisor.indicator.available', 'Available') },
          { checked: !!capabilities.enabled, label: t('hostDetail.hypervisor.indicator.enabled', 'Enabled') },
        ];
      default:
        return [];
    }
  };

  const indicators = getStatusIndicators();

  // Get action button icon
  const getActionIcon = () => {
    if (stateInfo.state === 'not_installed') return <DownloadIcon />;
    if (stateInfo.state === 'not_enabled' || stateInfo.state === 'needs_enable') return <PlayArrowIcon />;
    if (stateInfo.state === 'needs_init') return <SettingsIcon />;
    return <PlayArrowIcon />;
  };

  return (
    <Card
      variant="outlined"
      sx={{
        height: '100%',
        opacity: stateInfo.state === 'not_available' || stateInfo.state === 'no_kernel_support' ? 0.6 : 1,
        borderColor: isReady ? 'success.main' : undefined,
        borderWidth: isReady ? 2 : 1,
      }}
    >
      <CardContent sx={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
        {/* Header */}
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1 }}>
          <Box sx={{ color: isReady ? 'success.main' : 'text.secondary' }}>
            {hypervisorInfo.icon}
          </Box>
          <Box sx={{ flex: 1 }}>
            <Typography variant="subtitle1" sx={{ fontWeight: 'bold', lineHeight: 1.2 }}>
              {hypervisorInfo.name}
            </Typography>
            <Typography variant="caption" color="text.secondary">
              {hypervisorInfo.description}
            </Typography>
          </Box>
          {isLoading && <CircularProgress size={20} />}
        </Box>

        {/* Status Chip */}
        <Box sx={{ mb: 2 }}>
          <Chip
            label={stateInfo.label}
            color={stateInfo.color}
            size="small"
          />
          {rebootRequired && type === 'wsl' && (
            <Chip
              label={t('hostDetail.hypervisor.rebootRequired', 'Reboot Required')}
              color="warning"
              size="small"
              sx={{ ml: 1 }}
            />
          )}
        </Box>

        {/* Status Indicators */}
        <Stack spacing={0.5} sx={{ flex: 1, mb: 2 }}>
          {indicators.map((indicator, index) => (
            <StatusIndicator key={index} {...indicator} />
          ))}
        </Stack>

        {/* Action Buttons */}
        <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap' }}>
          {/* Enable/Install Button */}
          {canShowEnableButton && canEnable && onEnable && (
            <Tooltip
              title={!isAgentPrivileged ? t('hostDetail.privilegedModeRequired', 'Privileged mode required') : ''}
            >
              <span>
                <Button
                  variant="contained"
                  color="primary"
                  size="small"
                  startIcon={isEnableLoading ? <CircularProgress size={16} color="inherit" /> : getActionIcon()}
                  onClick={onEnable}
                  disabled={isEnableLoading || !isAgentPrivileged || rebootRequired}
                  fullWidth
                >
                  {hypervisorInfo.enableLabel}
                </Button>
              </span>
            </Tooltip>
          )}

          {/* KVM Module Control Buttons */}
          {type === 'kvm' && capabilities?.modules_available && !capabilities?.modules_loaded && canEnable && onEnableModules && (
            <Tooltip
              title={!isAgentPrivileged ? t('hostDetail.privilegedModeRequired', 'Privileged mode required') : ''}
            >
              <span>
                <Button
                  variant="contained"
                  color="warning"
                  size="small"
                  startIcon={isModulesLoading ? <CircularProgress size={16} color="inherit" /> : <MemoryIcon />}
                  onClick={onEnableModules}
                  disabled={isModulesLoading || !isAgentPrivileged}
                  fullWidth
                >
                  {t('hostDetail.hypervisor.kvm.loadModules', 'Load Modules')}
                </Button>
              </span>
            </Tooltip>
          )}

          {type === 'kvm' && capabilities?.modules_loaded && canEnable && onDisableModules && (
            <Tooltip
              title={!isAgentPrivileged ? t('hostDetail.privilegedModeRequired', 'Privileged mode required') : ''}
            >
              <span>
                <Button
                  variant="outlined"
                  color="warning"
                  size="small"
                  startIcon={isModulesLoading ? <CircularProgress size={16} color="inherit" /> : <StopIcon />}
                  onClick={onDisableModules}
                  disabled={isModulesLoading || !isAgentPrivileged}
                  fullWidth
                >
                  {t('hostDetail.hypervisor.kvm.unloadModules', 'Unload Modules')}
                </Button>
              </span>
            </Tooltip>
          )}

          {/* Create Button - hidden for KVM if modules need to be loaded first */}
          {isReady && canCreate && onCreate && !(type === 'kvm' && capabilities?.needs_modprobe) && (
            <Tooltip
              title={!isAgentPrivileged ? t('hostDetail.privilegedModeRequired', 'Privileged mode required') : ''}
            >
              <span>
                <Button
                  variant="contained"
                  color="success"
                  size="small"
                  startIcon={<AddIcon />}
                  onClick={onCreate}
                  disabled={!isAgentPrivileged}
                  fullWidth
                >
                  {hypervisorInfo.createLabel}
                </Button>
              </span>
            </Tooltip>
          )}

          {/* Disable Button for bhyve */}
          {type === 'bhyve' && isReady && canEnable && onDisable && (
            <Tooltip
              title={!isAgentPrivileged ? t('hostDetail.privilegedModeRequired', 'Privileged mode required') : ''}
            >
              <span>
                <Button
                  variant="outlined"
                  color="warning"
                  size="small"
                  startIcon={isDisableLoading ? <CircularProgress size={16} color="inherit" /> : <StopIcon />}
                  onClick={onDisable}
                  disabled={isDisableLoading || !isAgentPrivileged}
                  fullWidth
                >
                  {hypervisorInfo.disableLabel}
                </Button>
              </span>
            </Tooltip>
          )}

          {/* Not available message */}
          {(stateInfo.state === 'not_available' || stateInfo.state === 'no_kernel_support') && (
            <Typography variant="caption" color="text.disabled" sx={{ fontStyle: 'italic' }}>
              {stateInfo.state === 'no_kernel_support'
                ? t('hostDetail.hypervisor.noKernelSupportMessage', 'Kernel does not support this hypervisor')
                : t('hostDetail.hypervisor.notAvailableMessage', 'Not available on this platform')
              }
            </Typography>
          )}

          {/* BIOS virtualization message */}
          {stateInfo.state === 'bios_required' && (
            <Typography variant="caption" color="error" sx={{ fontStyle: 'italic' }}>
              {t('hostDetail.hypervisor.biosVirtualizationMessage', 'Enable virtualization in BIOS/UEFI settings')}
            </Typography>
          )}
        </Box>
      </CardContent>
    </Card>
  );
};

export default HypervisorStatusCard;
