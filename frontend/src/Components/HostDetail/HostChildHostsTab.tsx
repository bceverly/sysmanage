// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

import React from 'react';
import {
    Box,
    Card,
    CardContent,
    Typography,
    Grid,
    Chip,
    Button,
    CircularProgress,
    Paper,
    IconButton,
    Table,
    TableBody,
    TableRow,
    TableCell,
    TableContainer,
    TableHead,
} from '@mui/material';
import ComputerIcon from '@mui/icons-material/Computer';
import RefreshIcon from '@mui/icons-material/Refresh';
import DeleteIcon from '@mui/icons-material/Delete';
import RestartAltIcon from '@mui/icons-material/RestartAlt';
import PlayArrowIcon from '@mui/icons-material/PlayArrow';
import StopIcon from '@mui/icons-material/Stop';
import SystemUpdateAltIcon from '@mui/icons-material/SystemUpdateAlt';
import HelpOutlineIcon from '@mui/icons-material/HelpOutline';
import { useTranslation } from 'react-i18next';
import HypervisorStatusCard from '../HypervisorStatusCard';
import { hasPermissionSync, SecurityRoles } from '../../Services/permissions';
import { SysManageHost } from '../../Services/hosts';
import { ChildHost, VirtualizationStatus } from './hostDetailTypes';

interface HostChildHostsTabProps {
    host: SysManageHost;
    licenseModules: string[];
    virtualizationStatus: VirtualizationStatus | null;
    virtualizationLoading: boolean;
    childHosts: ChildHost[];
    childHostsLoading: boolean;
    childHostsRefreshRequested: boolean;
    childHostOperationLoading: Record<string, string | null>;
    enableWslLoading: boolean;
    initializeLxdLoading: boolean;
    initializeKvmLoading: boolean;
    initializeVmmLoading: boolean;
    initializeBhyveLoading: boolean;
    disableBhyveLoading: boolean;
    kvmModulesLoading: boolean;
    canEnableWsl: boolean;
    canEnableLxd: boolean;
    canEnableKvm: boolean;
    canEnableVmm: boolean;
    canEnableBhyve: boolean;
    handleEnableWsl: () => void;
    handleInitializeLxd: () => void;
    handleInitializeKvm: () => void;
    handleInitializeVmm: () => void;
    handleInitializeBhyve: () => void;
    handleDisableBhyve: () => void;
    handleEnableKvmModules: () => void;
    handleDisableKvmModules: () => void;
    openCreateDialogWithType: (childType: string) => void;
    requestChildHostsRefresh: (showSnackbar?: boolean) => void;
    handleChildHostStart: (child: ChildHost) => void;
    handleChildHostStop: (child: ChildHost) => void;
    handleChildHostRestart: (child: ChildHost) => void;
    handleChildHostUpdateAgent: (child: ChildHost) => void;
    handleChildHostDeleteConfirm: (child: ChildHost) => void;
    getWslEmptyMessage: () => string;
    getLxdEmptyMessage: () => string;
    getVmmEmptyMessage: () => string;
    getBhyveEmptyMessage: () => string;
}

const HostChildHostsTab: React.FC<HostChildHostsTabProps> = ({
    host,
    licenseModules,
    virtualizationStatus,
    virtualizationLoading,
    childHosts,
    childHostsLoading,
    childHostsRefreshRequested,
    childHostOperationLoading,
    enableWslLoading,
    initializeLxdLoading,
    initializeKvmLoading,
    initializeVmmLoading,
    initializeBhyveLoading,
    disableBhyveLoading,
    kvmModulesLoading,
    canEnableWsl,
    canEnableLxd,
    canEnableKvm,
    canEnableVmm,
    canEnableBhyve,
    handleEnableWsl,
    handleInitializeLxd,
    handleInitializeKvm,
    handleInitializeVmm,
    handleInitializeBhyve,
    handleDisableBhyve,
    handleEnableKvmModules,
    handleDisableKvmModules,
    openCreateDialogWithType,
    requestChildHostsRefresh,
    handleChildHostStart,
    handleChildHostStop,
    handleChildHostRestart,
    handleChildHostUpdateAgent,
    handleChildHostDeleteConfirm,
    getWslEmptyMessage,
    getLxdEmptyMessage,
    getVmmEmptyMessage,
    getBhyveEmptyMessage,
}) => {
    const { t } = useTranslation();
    return (
                <Grid container spacing={3}>
                    {/* Virtualization Capabilities - Card-based layout */}
                    <Grid size={{ xs: 12 }}>
                        <Box sx={{ mb: 2 }}>
                            <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 2 }}>
                                <Typography variant="h6" sx={{ fontWeight: 'bold' }}>
                                    {t('hostDetail.virtualizationCapabilities', 'Virtualization Capabilities')}
                                </Typography>
                                {virtualizationLoading && <CircularProgress size={20} />}
                            </Box>

                            {!virtualizationStatus && !virtualizationLoading && (
                                <Typography variant="body2" color="textSecondary">
                                    {t('hostDetail.virtualizationStatusUnavailable', 'Virtualization status not available')}
                                </Typography>
                            )}

                            {virtualizationStatus && (
                                <Grid container spacing={2}>
                                    {/* WSL Card — Windows + ``container_engine``.  The Initialize / Create
                                        buttons inside the card invoke Pro+ engine plans; without the
                                        engine licensed, the card simply hides per Phase 10.7. */}
                                    {host?.platform?.includes('Windows') && licenseModules.includes('container_engine') && (
                                        <Grid size={{ xs: 12, sm: 6, md: 4, lg: 3 }}>
                                            <HypervisorStatusCard
                                                type="wsl"
                                                capabilities={virtualizationStatus.capabilities?.wsl}
                                                onEnable={handleEnableWsl}
                                                onCreate={() => openCreateDialogWithType('wsl')}
                                                canEnable={canEnableWsl}
                                                canCreate={hasPermissionSync(SecurityRoles.CREATE_CHILD_HOST)}
                                                isLoading={virtualizationLoading}
                                                isEnableLoading={enableWslLoading}
                                                isAgentPrivileged={host?.is_agent_privileged || false}
                                                rebootRequired={virtualizationStatus.reboot_required}
                                            />
                                        </Grid>
                                    )}

                                    {/* LXD Card — Linux + ``container_engine``. */}
                                    {host?.platform?.includes('Linux') && licenseModules.includes('container_engine') && (
                                        <Grid size={{ xs: 12, sm: 6, md: 4, lg: 3 }}>
                                            <HypervisorStatusCard
                                                type="lxd"
                                                capabilities={virtualizationStatus.capabilities?.lxd}
                                                onEnable={handleInitializeLxd}
                                                onCreate={() => openCreateDialogWithType('lxd')}
                                                canEnable={canEnableLxd}
                                                canCreate={hasPermissionSync(SecurityRoles.CREATE_CHILD_HOST)}
                                                isLoading={virtualizationLoading}
                                                isEnableLoading={initializeLxdLoading}
                                                isAgentPrivileged={host?.is_agent_privileged || false}
                                            />
                                        </Grid>
                                    )}

                                    {/* KVM Card — Linux + ``virtualization_engine``. */}
                                    {host?.platform?.includes('Linux') && licenseModules.includes('virtualization_engine') && (
                                        <Grid size={{ xs: 12, sm: 6, md: 4, lg: 3 }}>
                                            <HypervisorStatusCard
                                                type="kvm"
                                                capabilities={virtualizationStatus.capabilities?.kvm}
                                                onEnable={handleInitializeKvm}
                                                onCreate={() => openCreateDialogWithType('kvm')}
                                                onEnableModules={handleEnableKvmModules}
                                                onDisableModules={handleDisableKvmModules}
                                                canEnable={canEnableKvm}
                                                canCreate={hasPermissionSync(SecurityRoles.CREATE_CHILD_HOST)}
                                                isLoading={virtualizationLoading}
                                                isEnableLoading={initializeKvmLoading}
                                                isModulesLoading={kvmModulesLoading}
                                                isAgentPrivileged={host?.is_agent_privileged || false}
                                            />
                                        </Grid>
                                    )}

                                    {/* VMM Card — OpenBSD + ``virtualization_engine``. */}
                                    {host?.platform?.includes('OpenBSD') && licenseModules.includes('virtualization_engine') && (
                                        <Grid size={{ xs: 12, sm: 6, md: 4, lg: 3 }}>
                                            <HypervisorStatusCard
                                                type="vmm"
                                                capabilities={virtualizationStatus.capabilities?.vmm}
                                                onEnable={handleInitializeVmm}
                                                onCreate={() => openCreateDialogWithType('vmm')}
                                                canEnable={canEnableVmm}
                                                canCreate={hasPermissionSync(SecurityRoles.CREATE_CHILD_HOST)}
                                                isLoading={virtualizationLoading}
                                                isEnableLoading={initializeVmmLoading}
                                                isAgentPrivileged={host?.is_agent_privileged || false}
                                            />
                                        </Grid>
                                    )}

                                    {/* bhyve Card — FreeBSD + ``virtualization_engine``. */}
                                    {host?.platform?.includes('FreeBSD') && licenseModules.includes('virtualization_engine') && (
                                        <Grid size={{ xs: 12, sm: 6, md: 4, lg: 3 }}>
                                            <HypervisorStatusCard
                                                type="bhyve"
                                                capabilities={virtualizationStatus.capabilities?.bhyve}
                                                onEnable={handleInitializeBhyve}
                                                onDisable={handleDisableBhyve}
                                                onCreate={() => openCreateDialogWithType('bhyve')}
                                                canEnable={canEnableBhyve}
                                                canCreate={hasPermissionSync(SecurityRoles.CREATE_CHILD_HOST)}
                                                isLoading={virtualizationLoading}
                                                isEnableLoading={initializeBhyveLoading}
                                                isDisableLoading={disableBhyveLoading}
                                                isAgentPrivileged={host?.is_agent_privileged || false}
                                            />
                                        </Grid>
                                    )}
                                </Grid>
                            )}
                        </Box>
                    </Grid>

                    <Grid size={{ xs: 12 }}>
                        <Card>
                            <CardContent>
                                <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 2 }}>
                                    <Typography variant="h6" sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                                        <ComputerIcon />
                                        {t('hostDetail.childHostsTitle', 'Child Hosts')}
                                    </Typography>
                                    <Box sx={{ display: 'flex', gap: 1 }}>
                                        <Button
                                            variant="outlined"
                                            size="small"
                                            startIcon={childHostsRefreshRequested ? <CircularProgress size={16} /> : <RefreshIcon />}
                                            onClick={() => requestChildHostsRefresh()}
                                            disabled={childHostsRefreshRequested || childHostsLoading}
                                        >
                                            {t('hostDetail.refreshChildHosts', 'Refresh')}
                                        </Button>
                                    </Box>
                                </Box>

                                {/* Loading state */}
                                {childHostsLoading && (
                                    <Box sx={{ display: 'flex', justifyContent: 'center', py: 4 }}>
                                        <CircularProgress />
                                    </Box>
                                )}

                                {/* Empty state */}
                                {!childHostsLoading && childHosts.length === 0 && (
                                    <Box sx={{ textAlign: 'center', py: 4 }}>
                                        <ComputerIcon sx={{ fontSize: 64, color: 'text.secondary', mb: 2 }} />
                                        <Typography variant="h6" color="textSecondary" gutterBottom>
                                            {t('hostDetail.childHostsEmpty', 'No child hosts found')}
                                        </Typography>
                                        <Typography variant="body2" color="textSecondary">
                                            {/* Windows hosts - WSL messages */}
                                            {host?.platform?.includes('Windows') && getWslEmptyMessage()}
                                            {/* Linux hosts - LXD messages */}
                                            {host?.platform?.includes('Linux') && getLxdEmptyMessage()}
                                            {/* OpenBSD hosts - VMM messages */}
                                            {host?.platform?.includes('OpenBSD') && getVmmEmptyMessage()}
                                            {/* FreeBSD hosts - bhyve messages */}
                                            {host?.platform?.includes('FreeBSD') && getBhyveEmptyMessage()}
                                        </Typography>
                                    </Box>
                                )}

                                {/* Child hosts list */}
                                {!childHostsLoading && childHosts.length > 0 && (
                                    <TableContainer component={Paper} variant="outlined">
                                        <Table size="small">
                                            <TableHead>
                                                <TableRow>
                                                    <TableCell>{t('hostDetail.childHostName', 'Name')}</TableCell>
                                                    <TableCell>{t('hostDetail.childHostType', 'Type')}</TableCell>
                                                    <TableCell>{t('hostDetail.childHostDistribution', 'Distribution')}</TableCell>
                                                    <TableCell>{t('hostDetail.childHostHostname', 'Hostname')}</TableCell>
                                                    <TableCell>{t('hosts.agentVersion', 'Agent Version')}</TableCell>
                                                    <TableCell>{t('hostDetail.childHostStatus', 'Status')}</TableCell>
                                                    <TableCell align="right">{t('hostDetail.childHostActions', 'Actions')}</TableCell>
                                                </TableRow>
                                            </TableHead>
                                            <TableBody>
                                                {childHosts.map((child) => {
                                                    const isOperationLoading = childHostOperationLoading[child.id] != null;
                                                    const currentOperation = childHostOperationLoading[child.id];
                                                    return (
                                                    <TableRow key={child.id}>
                                                        <TableCell>
                                                            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                                                                <ComputerIcon fontSize="small" />
                                                                {child.child_name}
                                                            </Box>
                                                        </TableCell>
                                                        <TableCell>
                                                            <Chip
                                                                label={child.child_type.toUpperCase()}
                                                                size="small"
                                                                color={child.child_type === 'wsl' ? 'primary' : 'default'}
                                                            />
                                                        </TableCell>
                                                        <TableCell>
                                                            {child.distribution}
                                                            {child.distribution_version && ` ${child.distribution_version}`}
                                                        </TableCell>
                                                        <TableCell>
                                                            {child.hostname || (child.status === 'running' ? '-' : t('hostDetail.childHostNotRunning', 'Not running'))}
                                                        </TableCell>
                                                        <TableCell>
                                                            {child.agent_version || '-'}
                                                        </TableCell>
                                                        <TableCell>
                                                            <Box sx={{ display: 'flex', flexDirection: 'row', flexWrap: 'wrap', gap: 0.5, alignItems: 'center' }}>
                                                                {(() => {
                                                                    let statusLabel: string;
                                                                    if (child.status === 'creating') {
                                                                        statusLabel = t('hostDetail.childHostCreating', 'Creating...');
                                                                    } else if (child.status === 'running') {
                                                                        statusLabel = t('hostDetail.childHostRunning', 'Running');
                                                                    } else if (child.status === 'stopped') {
                                                                        statusLabel = t('hostDetail.childHostStopped', 'Stopped');
                                                                    } else if (child.status === 'error') {
                                                                        statusLabel = t('hostDetail.childHostError', 'Error');
                                                                    } else {
                                                                        statusLabel = child.status;
                                                                    }

                                                                    let statusColor: 'success' | 'default' | 'error' | 'info' | 'warning';
                                                                    if (child.status === 'running') {
                                                                        statusColor = 'success';
                                                                    } else if (child.status === 'stopped') {
                                                                        statusColor = 'default';
                                                                    } else if (child.status === 'error') {
                                                                        statusColor = 'error';
                                                                    } else if (child.status === 'creating') {
                                                                        statusColor = 'info';
                                                                    } else {
                                                                        statusColor = 'warning';
                                                                    }

                                                                    return (
                                                                        <Chip
                                                                            icon={child.status === 'creating' ? <CircularProgress size={12} color="inherit" /> : undefined}
                                                                            label={statusLabel}
                                                                            size="small"
                                                                            color={statusColor}
                                                                        />
                                                                    );
                                                                })()}
                                                                {/* Show error message if status is error */}
                                                                {child.status === 'error' && child.error_message && (
                                                                    <Typography variant="caption" color="error" sx={{ maxWidth: 200 }}>
                                                                        {child.error_message}
                                                                    </Typography>
                                                                )}
                                                                {/* Show "Pending Approval" if child is running but not linked to approved host */}
                                                                {child.status === 'running' && !child.child_host_id && (
                                                                    <Chip
                                                                        icon={<HelpOutlineIcon />}
                                                                        label={t('hostDetail.pendingApproval', 'Pending Approval')}
                                                                        size="small"
                                                                        color="info"
                                                                        variant="outlined"
                                                                    />
                                                                )}
                                                                {child.reboot_required && (
                                                                    <Chip
                                                                        label={t('hosts.rebootRequired')}
                                                                        color="error"
                                                                        size="small"
                                                                        variant="outlined"
                                                                    />
                                                                )}
                                                            </Box>
                                                        </TableCell>
                                                        <TableCell align="right">
                                                            {/* Phase 10.7 fine-grained gating: per-row action buttons
                                                                require the right Pro+ engine.  WSL/LXD lifecycles run
                                                                through ``container_engine``; KVM/bhyve/VMM through
                                                                ``virtualization_engine``.  The read-only row stays
                                                                visible for OSS deployments — only the action column
                                                                hides. */}
                                                            {(() => {
                                                                const requiredEngine =
                                                                    child.child_type === 'wsl' || child.child_type === 'lxd'
                                                                        ? 'container_engine'
                                                                        : 'virtualization_engine';
                                                                if (!licenseModules.includes(requiredEngine)) {
                                                                    return null;
                                                                }
                                                                return (
                                                            <Box sx={{ display: 'flex', gap: 0.5, justifyContent: 'flex-end' }}>
                                                                {/* Start button - only show if stopped */}
                                                                {child.status === 'stopped' && (
                                                                    <IconButton
                                                                        size="small"
                                                                        color="success"
                                                                        onClick={() => handleChildHostStart(child)}
                                                                        disabled={isOperationLoading}
                                                                        title={t('hostDetail.startChildHost', 'Start')}
                                                                    >
                                                                        {currentOperation === 'start' ? <CircularProgress size={16} /> : <PlayArrowIcon fontSize="small" />}
                                                                    </IconButton>
                                                                )}
                                                                {/* Stop button - only show if running */}
                                                                {child.status === 'running' && (
                                                                    <IconButton
                                                                        size="small"
                                                                        color="warning"
                                                                        onClick={() => handleChildHostStop(child)}
                                                                        disabled={isOperationLoading}
                                                                        title={t('hostDetail.stopChildHost', 'Stop')}
                                                                    >
                                                                        {currentOperation === 'stop' ? <CircularProgress size={16} /> : <StopIcon fontSize="small" />}
                                                                    </IconButton>
                                                                )}
                                                                {/* Restart button - show for running or stopped */}
                                                                {(child.status === 'running' || child.status === 'stopped') && (
                                                                    <IconButton
                                                                        size="small"
                                                                        color="primary"
                                                                        onClick={() => handleChildHostRestart(child)}
                                                                        disabled={isOperationLoading}
                                                                        title={t('hostDetail.restartChildHost', 'Restart')}
                                                                    >
                                                                        {currentOperation === 'restart' ? <CircularProgress size={16} /> : <RestartAltIcon fontSize="small" />}
                                                                    </IconButton>
                                                                )}
                                                                {/* Update Agent button - show for children with linked agents and UPDATE_AGENT role */}
                                                                {child.child_host_id && hasPermissionSync(SecurityRoles.UPDATE_AGENT) && (
                                                                    <IconButton
                                                                        size="small"
                                                                        color="info"
                                                                        onClick={() => handleChildHostUpdateAgent(child)}
                                                                        disabled={isOperationLoading}
                                                                        title={t('hosts.updateAgent', 'Update Agent')}
                                                                    >
                                                                        {currentOperation === 'update-agent' ? <CircularProgress size={16} /> : <SystemUpdateAltIcon fontSize="small" />}
                                                                    </IconButton>
                                                                )}
                                                                {/* Delete/Cancel button - show for all statuses */}
                                                                <IconButton
                                                                    size="small"
                                                                    color="error"
                                                                    onClick={() => handleChildHostDeleteConfirm(child)}
                                                                    disabled={isOperationLoading}
                                                                    title={child.status === 'creating' || child.status === 'pending'
                                                                        ? t('hostDetail.cancelChildHost', 'Cancel')
                                                                        : t('hostDetail.deleteChildHost', 'Delete')}
                                                                >
                                                                    {currentOperation === 'delete' ? <CircularProgress size={16} /> : <DeleteIcon fontSize="small" />}
                                                                </IconButton>
                                                            </Box>
                                                                );
                                                            })()}
                                                        </TableCell>
                                                    </TableRow>
                                                    );
                                                })}
                                            </TableBody>
                                        </Table>
                                    </TableContainer>
                                )}
                            </CardContent>
                        </Card>
                    </Grid>
                </Grid>    );
};

export default HostChildHostsTab;
