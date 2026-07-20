// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

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
import type { TFunction } from 'i18next';

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

interface StatusIndicatorProps {
  checked: boolean;
  label: string;
}

const StatusIndicator: React.FC<StatusIndicatorProps> = ({ checked, label }) => (
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

// Status indicators shown per hypervisor type. Pure (depends only on type,
// capabilities and t) — extracted to module scope to keep the component's
// cognitive complexity low.
const getStatusIndicators = (
  type: HypervisorType,
  capabilities: HypervisorCapabilities | undefined,
  t: TFunction,
): { checked: boolean; label: string }[] => {
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

// Icon for the enable/install/init action button, derived from the current state.
const getActionIcon = (state: string): React.ReactElement => {
  if (state === 'not_installed') return <DownloadIcon />;
  if (state === 'not_enabled' || state === 'needs_enable') return <PlayArrowIcon />;
  if (state === 'needs_init') return <SettingsIcon />;
  return <PlayArrowIcon />;
};

interface HypervisorInfo {
  name: string;
  description: string;
  icon: React.ReactElement;
  createLabel: string;
  enableLabel: string;
  disableLabel?: string;
}

// Per-type display info (name/description/icon/labels). Pure — extracted to
// module scope to keep the component's cognitive complexity low.
const getHypervisorInfo = (type: HypervisorType, t: TFunction): HypervisorInfo => {
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
    default: {
      // Handle any future hypervisor types not yet in the union
      const unknownType: string = type;
      return {
        name: unknownType.toUpperCase(),
        description: '',
        icon: <ComputerIcon />,
        createLabel: t('hostDetail.hypervisor.createLabel', 'Create'),
        enableLabel: t('hostDetail.hypervisor.enableLabel', 'Enable'),
      };
    }
  }
};

type StateResult = { state: string; color: 'default' | 'error' | 'success' | 'warning' | 'info'; label: string };

const isBsdType = (type: HypervisorType): boolean => type === 'vmm' || type === 'bhyve';
const isLinuxType = (type: HypervisorType): boolean => type === 'kvm' || type === 'lxd';

const isHypervisorReady = (type: HypervisorType, caps: HypervisorCapabilities): boolean => {
  if (type === 'wsl' && caps.enabled) return true;
  if (isBsdType(type) && caps.running) return true;
  if (isLinuxType(type) && caps.initialized) return true;
  return false;
};

const needsInitialization = (type: HypervisorType, caps: HypervisorCapabilities): boolean => {
  if (type === 'kvm' && caps.running && !caps.initialized) return true;
  if (type === 'lxd' && caps.installed && !caps.initialized) return true;
  return false;
};

const isBsdEnabledButNotRunning = (type: HypervisorType, caps: HypervisorCapabilities): boolean =>
  isBsdType(type) && !!caps.enabled && !caps.running;

const needsEnabling = (type: HypervisorType, caps: HypervisorCapabilities): boolean => {
  if (type === 'wsl' && caps.needs_enable) return true;
  if (isBsdType(type) && caps.needs_enable) return true;
  return false;
};

// State-determination rules, evaluated top-to-bottom. Each rule's `when`
// predicate is checked against the (guaranteed non-null) capabilities; the
// first match wins. `key` maps to the state/color/labelKey/defaultLabel tuple.
type StateRule = {
  when: (type: HypervisorType, caps: HypervisorCapabilities) => boolean;
  state: string;
  color: StateResult['color'];
  labelKey: string;
  defaultLabel: string;
};

const HYPERVISOR_STATE_RULES: StateRule[] = [
  // BIOS virtualization requirement (WSL specific)
  { when: (_t, c) => !!c.needs_bios_virtualization, state: 'bios_required', color: 'error', labelKey: 'biosRequired', defaultLabel: 'BIOS Virtualization Required' },
  // Not available at all
  { when: (_t, c) => !c.available, state: 'not_available', color: 'default', labelKey: 'notAvailable', defaultLabel: 'Not Available' },
  // BSD hypervisors require kernel support
  { when: (ty, c) => isBsdType(ty) && !c.kernel_supported, state: 'no_kernel_support', color: 'error', labelKey: 'noKernelSupport', defaultLabel: 'No Kernel Support' },
  // Fully ready
  { when: isHypervisorReady, state: 'ready', color: 'success', labelKey: 'ready', defaultLabel: 'Ready' },
  // Needs initialization
  { when: needsInitialization, state: 'needs_init', color: 'warning', labelKey: 'needsInit', defaultLabel: 'Needs Initialization' },
  // BSD hypervisor enabled but not running
  { when: isBsdEnabledButNotRunning, state: 'not_running', color: 'warning', labelKey: 'notRunning', defaultLabel: 'Not Running' },
  // Installed but not enabled
  { when: (_t, c) => !!c.installed && !c.enabled, state: 'not_enabled', color: 'warning', labelKey: 'notEnabled', defaultLabel: 'Not Enabled' },
  // Available but not installed
  { when: (_t, c) => !!c.available && !c.installed, state: 'not_installed', color: 'warning', labelKey: 'notInstalled', defaultLabel: 'Not Installed' },
  // Needs enabling (WSL, VMM, bhyve)
  { when: needsEnabling, state: 'needs_enable', color: 'warning', labelKey: 'notEnabled', defaultLabel: 'Not Enabled' },
];

// Determine current state and what action is needed. Pure — extracted to module
// scope to keep the component's cognitive complexity low.
const getHypervisorState = (
  type: HypervisorType,
  capabilities: HypervisorCapabilities | undefined,
  t: TFunction,
): StateResult => {
  const createState = (
    state: string,
    color: StateResult['color'],
    labelKey: string,
    defaultLabel: string,
  ): StateResult => ({
    state,
    color,
    label: t(`hostDetail.hypervisor.state.${labelKey}`, defaultLabel),
  });

  if (!capabilities) {
    return createState('unknown', 'default', 'unknown', 'Unknown');
  }
  const matched = HYPERVISOR_STATE_RULES.find((rule) => rule.when(type, capabilities));
  if (matched) {
    return createState(matched.state, matched.color, matched.labelKey, matched.defaultLabel);
  }
  // Fallback
  return createState('available', 'info', 'available', 'Available');
};

// Props for the action-buttons region, split out of the main component so its
// many render guards don't inflate the component's cognitive complexity.
interface HypervisorActionsProps {
  type: HypervisorType;
  capabilities: HypervisorCapabilities | undefined;
  stateInfo: StateResult;
  hypervisorInfo: HypervisorInfo;
  isReady: boolean;
  canShowEnableButton: boolean;
  canEnable: boolean;
  canCreate: boolean;
  isEnableLoading: boolean;
  isDisableLoading: boolean;
  isModulesLoading: boolean;
  isAgentPrivileged: boolean;
  rebootRequired: boolean;
  onEnable?: () => void;
  onDisable?: () => void;
  onCreate?: () => void;
  onEnableModules?: () => void;
  onDisableModules?: () => void;
  t: TFunction;
}

const HypervisorActions: React.FC<HypervisorActionsProps> = ({
  type,
  capabilities,
  stateInfo,
  hypervisorInfo,
  isReady,
  canShowEnableButton,
  canEnable,
  canCreate,
  isEnableLoading,
  isDisableLoading,
  isModulesLoading,
  isAgentPrivileged,
  rebootRequired,
  onEnable,
  onDisable,
  onCreate,
  onEnableModules,
  onDisableModules,
  t,
}) => {
  const privilegedTitle = isAgentPrivileged
    ? ''
    : t('hostDetail.privilegedModeRequired', 'Privileged mode required');

  const showEnable = canShowEnableButton && canEnable && !!onEnable;
  const showLoadModules =
    type === 'kvm' && !!capabilities?.modules_available && !capabilities?.modules_loaded && canEnable && !!onEnableModules;
  const showUnloadModules = type === 'kvm' && !!capabilities?.modules_loaded && canEnable && !!onDisableModules;
  const showCreate = isReady && canCreate && !!onCreate && !(type === 'kvm' && capabilities?.needs_modprobe);
  const showDisable = type === 'bhyve' && isReady && canEnable && !!onDisable;
  const showUnavailableMsg = stateInfo.state === 'not_available' || stateInfo.state === 'no_kernel_support';

  return (
    <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap' }}>
      {/* Enable/Install Button */}
      {showEnable && (
        <Tooltip title={privilegedTitle}>
          <span>
            <Button
              variant="contained"
              color="primary"
              size="small"
              startIcon={isEnableLoading ? <CircularProgress size={16} color="inherit" /> : getActionIcon(stateInfo.state)}
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
      {showLoadModules && (
        <Tooltip title={privilegedTitle}>
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

      {showUnloadModules && (
        <Tooltip title={privilegedTitle}>
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
      {showCreate && (
        <Tooltip title={privilegedTitle}>
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
      {showDisable && (
        <Tooltip title={privilegedTitle}>
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
      {showUnavailableMsg && (
        <Typography variant="caption" color="text.disabled" sx={{ fontStyle: 'italic' }}>
          {stateInfo.state === 'no_kernel_support'
            ? t('hostDetail.hypervisor.noKernelSupportMessage', 'Kernel does not support this hypervisor')
            : t('hostDetail.hypervisor.notAvailableMessage', 'Not available on this platform')}
        </Typography>
      )}

      {/* BIOS virtualization message */}
      {stateInfo.state === 'bios_required' && (
        <Typography variant="caption" color="error" sx={{ fontStyle: 'italic' }}>
          {t('hostDetail.hypervisor.biosVirtualizationMessage', 'Enable virtualization in BIOS/UEFI settings')}
        </Typography>
      )}
    </Box>
  );
};

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

  const hypervisorInfo = getHypervisorInfo(type, t);
  const stateInfo = getHypervisorState(type, capabilities, t);
  const isReady = stateInfo.state === 'ready';
  const canShowEnableButton = !isReady &&
    stateInfo.state !== 'not_available' &&
    stateInfo.state !== 'bios_required' &&
    stateInfo.state !== 'no_kernel_support' &&
    stateInfo.state !== 'unknown';

  const indicators = getStatusIndicators(type, capabilities, t);

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
          {indicators.map((indicator) => (
            <StatusIndicator key={indicator.label} {...indicator} />
          ))}
        </Stack>

        {/* Action Buttons */}
        <HypervisorActions
          type={type}
          capabilities={capabilities}
          stateInfo={stateInfo}
          hypervisorInfo={hypervisorInfo}
          isReady={isReady}
          canShowEnableButton={canShowEnableButton}
          canEnable={canEnable}
          canCreate={canCreate}
          isEnableLoading={isEnableLoading}
          isDisableLoading={isDisableLoading}
          isModulesLoading={isModulesLoading}
          isAgentPrivileged={isAgentPrivileged}
          rebootRequired={rebootRequired}
          onEnable={onEnable}
          onDisable={onDisable}
          onCreate={onCreate}
          onEnableModules={onEnableModules}
          onDisableModules={onDisableModules}
          t={t}
        />
      </CardContent>
    </Card>
  );
};

export default HypervisorStatusCard;
