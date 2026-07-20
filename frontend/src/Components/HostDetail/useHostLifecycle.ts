// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

// Host lifecycle actions (reboot/shutdown/hostname/agent-update), diagnostics
// request + management, and the reboot-orchestration polling effect for the
// Host Detail page.

import React, { useEffect, useState } from 'react';
import type { TFunction } from 'i18next';
import axiosInstance from '../../Services/api';
import {
    SysManageHost,
    DiagnosticReport,
    DiagnosticDetailResponse,
    RebootPreCheckResponse,
    RebootOrchestrationStatus,
    doGetHostByID,
    doGetHostDiagnostics,
    doRequestHostDiagnostics,
    doGetDiagnosticDetail,
    doDeleteDiagnostic,
    doRebootHost,
    doShutdownHost,
    doUpdateAgent,
    doRequestSystemInfo,
    doRefreshUserAccessData,
    doRefreshSoftwareData,
    doRefreshUpdatesCheck,
    doChangeHostname,
    doRebootPreCheck,
    doOrchestratedReboot,
    getRebootOrchestrationStatus,
} from '../../Services/hosts';
import type { SnackbarSeverity } from './useHostSnackbar';

interface UseHostLifecycleArgs {
    hostId: string | undefined;
    host: SysManageHost | null;
    setHost: React.Dispatch<React.SetStateAction<SysManageHost | null>>;
    supportsChildHosts: () => boolean;
    fetchVirtualizationStatus: () => Promise<void>;
    t: TFunction;
    setSnackbarMessage: React.Dispatch<React.SetStateAction<string>>;
    setSnackbarSeverity: React.Dispatch<React.SetStateAction<SnackbarSeverity>>;
    setSnackbarOpen: React.Dispatch<React.SetStateAction<boolean>>;
}

export const useHostLifecycle = ({
    hostId,
    host,
    setHost,
    supportsChildHosts,
    fetchVirtualizationStatus,
    t,
    setSnackbarMessage,
    setSnackbarSeverity,
    setSnackbarOpen,
}: UseHostLifecycleArgs) => {
    const [diagnosticsData, setDiagnosticsData] = useState<DiagnosticReport[]>([]);
    const [diagnosticsLoading, setDiagnosticsLoading] = useState<boolean>(false);
    const [deleteConfirmOpen, setDeleteConfirmOpen] = useState<boolean>(false);
    const [diagnosticToDelete, setDiagnosticToDelete] = useState<string | null>(null);
    const [rebootConfirmOpen, setRebootConfirmOpen] = useState<boolean>(false);
    const [shutdownConfirmOpen, setShutdownConfirmOpen] = useState<boolean>(false);
    const [rebootPreCheckData, setRebootPreCheckData] = useState<RebootPreCheckResponse | null>(null);
    const [rebootPreCheckLoading, setRebootPreCheckLoading] = useState<boolean>(false);
    const [rebootOrchestrationId, setRebootOrchestrationId] = useState<string | null>(null);
    const [rebootOrchestrationStatus, setRebootOrchestrationStatus] = useState<RebootOrchestrationStatus | null>(null);
    const [diagnosticDetailOpen, setDiagnosticDetailOpen] = useState<boolean>(false);
    const [selectedDiagnostic, setSelectedDiagnostic] = useState<DiagnosticDetailResponse | null>(null);
    const [diagnosticDetailLoading, setDiagnosticDetailLoading] = useState<boolean>(false);
    const [hostnameEditOpen, setHostnameEditOpen] = useState<boolean>(false);
    const [newHostname, setNewHostname] = useState<string>('');
    const [hostnameEditLoading, setHostnameEditLoading] = useState<boolean>(false);
    // Poll reboot orchestration status every 5 seconds when active
    useEffect(() => {
        if (!rebootOrchestrationId || !host?.id) return;

        const pollStatus = async () => {
            try {
                const status = await getRebootOrchestrationStatus(host.id, rebootOrchestrationId);
                setRebootOrchestrationStatus(status);

                if (status.status === 'completed' || status.status === 'failed') {
                    setRebootOrchestrationId(null);
                    if (status.status === 'completed') {
                        setSnackbarMessage(
                            status.error_message
                                ? t('hosts.rebootOrchestration.completedWithErrors', 'Orchestrated reboot completed: {{error}}', { error: status.error_message })
                                : t('hosts.rebootOrchestration.completed', 'Orchestrated reboot completed successfully')
                        );
                        setSnackbarSeverity(status.error_message ? 'warning' : 'success');
                    } else {
                        setSnackbarMessage(t('hosts.rebootOrchestration.failed', 'Orchestrated reboot failed: {{error}}', { error: status.error_message || 'Unknown error' }));
                        setSnackbarSeverity('error');
                    }
                    setSnackbarOpen(true);
                }
            } catch (error) {
                console.error('Failed to poll orchestration status:', error);
            }
        };

        pollStatus();
        const interval = setInterval(pollStatus, 5000);
        return () => clearInterval(interval);
    }, [rebootOrchestrationId, host?.id, t, setSnackbarMessage, setSnackbarSeverity, setSnackbarOpen]);
    const handleRequestDiagnostics = async () => {
        if (!hostId) return;

        try {
            setDiagnosticsLoading(true);

            // Build list of requests to make
            const requests: Promise<unknown>[] = [
                doRequestHostDiagnostics(hostId),
                doRequestSystemInfo(hostId),
                doRefreshUserAccessData(hostId),
                doRefreshSoftwareData(hostId),
                doRefreshUpdatesCheck(hostId)
            ];

            // If host supports child hosts (Windows), also request virtualization check
            if (supportsChildHosts()) {
                requests.push(
                    axiosInstance.get(`/api/v1/host/${hostId}/virtualization`).catch(err => {
                        console.log('Virtualization check request failed (optional):', err);
                        return null;
                    })
                );
            }

            // Request diagnostics, system info, user access data, software inventory, package updates, and virtualization check
            await Promise.all(requests);

            // Show success message
            console.log('Host data requested successfully');
            
            // Refresh host data to get updated diagnostics request status
            const updatedHost = await doGetHostByID(hostId);
            setHost(updatedHost);
            
            // Start polling for completion if request is pending
            if (updatedHost?.diagnostics_request_status === 'pending') {
                const pollForCompletion = async (attempts = 0, maxAttempts = 20) => {
                    if (attempts >= maxAttempts) {
                        console.log('Diagnostics polling completed after max attempts');
                        return;
                    }
                    
                    setTimeout(async () => {
                        try {
                            const currentHost = await doGetHostByID(hostId);
                            setHost(currentHost);
                            
                            // If status is still pending, continue polling; otherwise refresh diagnostics data and virtualization status
                            if (currentHost?.diagnostics_request_status === 'pending') {
                                // Continue polling
                                pollForCompletion(attempts + 1, maxAttempts);
                            } else {
                                const updatedDiagnostics = await doGetHostDiagnostics(hostId);
                                setDiagnosticsData(updatedDiagnostics);
                                // Also refresh virtualization status if this host supports child hosts
                                if (supportsChildHosts()) {
                                    await fetchVirtualizationStatus();
                                }
                                console.log('Diagnostics request completed');
                            }
                        } catch (err) {
                            console.warn('Failed to refresh host data:', err);
                            pollForCompletion(attempts + 1, maxAttempts);
                        }
                    }, 3000); // Poll every 3 seconds
                };
                
                pollForCompletion();
            }
        } catch (error) {
            console.error('Error requesting diagnostics:', error);
        } finally {
            setDiagnosticsLoading(false);
        }
    };
    const handleDeleteDiagnostic = (diagnosticId: string) => {
        setDiagnosticToDelete(diagnosticId);
        setDeleteConfirmOpen(true);
    };

    const handleViewDiagnosticDetail = async (diagnosticId: string) => {
        try {
            setDiagnosticDetailLoading(true);
            setDiagnosticDetailOpen(true);
            const diagnosticDetail = await doGetDiagnosticDetail(diagnosticId);
            setSelectedDiagnostic(diagnosticDetail);
        } catch (error) {
            console.error('Error fetching diagnostic detail:', error);
            setSnackbarMessage(t('hostDetail.diagnosticLoadFailed', 'Failed to load diagnostic details'));
            setSnackbarSeverity('error');
            setSnackbarOpen(true);
            setDiagnosticDetailOpen(false);
        } finally {
            setDiagnosticDetailLoading(false);
        }
    };

    const handleRebootClick = async () => {
        if (supportsChildHosts() && host?.id) {
            setRebootPreCheckLoading(true);
            try {
                const preCheck = await doRebootPreCheck(host.id);
                setRebootPreCheckData(preCheck);
            } catch (error) {
                console.error('Failed to pre-check reboot:', error);
                setRebootPreCheckData(null);
            } finally {
                setRebootPreCheckLoading(false);
            }
        } else {
            setRebootPreCheckData(null);
        }
        setRebootConfirmOpen(true);
    };

    const handleShutdownClick = () => {
        setShutdownConfirmOpen(true);
    };

    const handleUpdateAgent = async () => {
        if (!host?.id) return;
        try {
            await doUpdateAgent(host.id);
            setSnackbarMessage(t('hosts.updateAgentRequested', 'Agent update requested successfully'));
            setSnackbarSeverity('success');
            setSnackbarOpen(true);
        } catch (error) {
            console.error('Failed to request agent update:', error);
            setSnackbarMessage(t('hosts.updateAgentFailed', 'Failed to request agent update'));
            setSnackbarSeverity('error');
            setSnackbarOpen(true);
        }
    };

    const handleRebootConfirm = async () => {
        if (!host?.id) return;

        try {
            if (rebootPreCheckData?.has_running_children && rebootPreCheckData?.has_container_engine) {
                // Pro+: Use orchestrated reboot
                const result = await doOrchestratedReboot(host.id);
                setRebootOrchestrationId(result.orchestration_id);
                setSnackbarMessage(t('hosts.rebootOrchestration.initiated', 'Orchestrated reboot initiated — stopping {{count}} child host(s)', { count: result.child_count }));
                setSnackbarSeverity('success');
            } else {
                // Standard reboot (no children or no Pro+)
                await doRebootHost(host.id);
                setSnackbarMessage(t('hosts.rebootRequested', 'Reboot requested successfully'));
                setSnackbarSeverity('success');
            }
            setSnackbarOpen(true);
            setRebootConfirmOpen(false);
            setRebootPreCheckData(null);
        } catch (error) {
            console.error('Failed to request reboot:', error);
            setSnackbarMessage(t('hosts.rebootFailed', 'Failed to request reboot'));
            setSnackbarSeverity('error');
            setSnackbarOpen(true);
        }
    };

    const handleHostnameEditClick = () => {
        if (host) {
            setNewHostname(host.fqdn);
            setHostnameEditOpen(true);
        }
    };

    const handleHostnameChange = async () => {
        if (!host?.id || !newHostname.trim()) return;

        setHostnameEditLoading(true);
        try {
            await doChangeHostname(host.id, newHostname.trim());
            setSnackbarMessage(t('hostDetail.hostnameChangeRequested', 'Hostname change requested'));
            setSnackbarSeverity('success');
            setSnackbarOpen(true);
            setHostnameEditOpen(false);
        } catch (error) {
            console.error('Failed to change hostname:', error);
            setSnackbarMessage(t('hostDetail.hostnameChangeFailed', 'Failed to change hostname'));
            setSnackbarSeverity('error');
            setSnackbarOpen(true);
        } finally {
            setHostnameEditLoading(false);
        }
    };


    const handleShutdownConfirm = async () => {
        if (!host?.id) return;

        try {
            await doShutdownHost(host.id);
            setSnackbarMessage(t('hosts.shutdownRequested', 'Shutdown requested successfully'));
            setSnackbarOpen(true);
            setShutdownConfirmOpen(false);
        } catch (error) {
            console.error('Failed to request shutdown:', error);
            setSnackbarMessage(t('hosts.shutdownFailed', 'Failed to request shutdown'));
            setSnackbarOpen(true);
        }
    };

    const handleConfirmDelete = async () => {
        if (!diagnosticToDelete) return;
        
        try {
            console.log('Deleting diagnostic:', diagnosticToDelete);
            await doDeleteDiagnostic(diagnosticToDelete);
            console.log('Diagnostic deleted successfully, refreshing data...');
            
            // Refresh diagnostics data after deletion
            if (hostId) {
                try {
                    const updatedDiagnostics = await doGetHostDiagnostics(hostId);
                    setDiagnosticsData(updatedDiagnostics);
                    console.log('Diagnostics data refreshed:', updatedDiagnostics.length, 'reports');
                    
                    // Also refresh host data to update the processing pill status
                    // This is especially important if we just deleted the last diagnostic
                    const updatedHost = await doGetHostByID(hostId);
                    setHost(updatedHost);
                    console.log('Host data refreshed, diagnostics_request_status:', updatedHost?.diagnostics_request_status);
                } catch (refreshError) {
                    console.error('Error refreshing data after deletion:', refreshError);
                    // Still show success since deletion worked
                }
            }
            
            setSnackbarMessage(t('hostDetail.diagnosticDeleted', 'Diagnostic report deleted successfully'));
            setSnackbarSeverity('success');
            setSnackbarOpen(true);
            
        } catch (error) {
            console.error('Error deleting diagnostic:', error);
            setSnackbarMessage(t('hostDetail.diagnosticDeleteFailed', 'Failed to delete diagnostic report'));
            setSnackbarSeverity('error');
            setSnackbarOpen(true);
        } finally {
            setDeleteConfirmOpen(false);
            setDiagnosticToDelete(null);
        }
    };

    const handleCancelDelete = () => {
        setDeleteConfirmOpen(false);
        setDiagnosticToDelete(null);
    };
    return {
        diagnosticsData,
        setDiagnosticsData,
        diagnosticsLoading,
        deleteConfirmOpen,
        rebootConfirmOpen,
        setRebootConfirmOpen,
        shutdownConfirmOpen,
        setShutdownConfirmOpen,
        rebootPreCheckData,
        setRebootPreCheckData,
        rebootPreCheckLoading,
        rebootOrchestrationId,
        rebootOrchestrationStatus,
        diagnosticDetailOpen,
        setDiagnosticDetailOpen,
        selectedDiagnostic,
        diagnosticDetailLoading,
        hostnameEditOpen,
        setHostnameEditOpen,
        newHostname,
        setNewHostname,
        hostnameEditLoading,
        handleDeleteDiagnostic,
        handleViewDiagnosticDetail,
        handleRebootClick,
        handleShutdownClick,
        handleUpdateAgent,
        handleRebootConfirm,
        handleHostnameEditClick,
        handleHostnameChange,
        handleShutdownConfirm,
        handleConfirmDelete,
        handleCancelDelete,
        handleRequestDiagnostics,
    };
};
