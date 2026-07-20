// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

// Child-host + virtualization state, fetchers, handlers, the create-child form,
// per-hypervisor enablement actions, the child-hosts auto-refresh effect and the
// empty-state message helpers for the Host Detail page.

import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type { TFunction } from 'i18next';
import axios from 'axios';
import axiosInstance from '../../Services/api';
import { distributionService } from '../../Services/childHostDistributions';
import { SysManageHost } from '../../Services/hosts';
import { ChildHost, VirtualizationStatus, ChildHostFormData, AvailableDistribution } from './hostDetailTypes';
import type { SnackbarSeverity } from './useHostSnackbar';

// Validation for the create-child-host form. Returns a translated error message
// for the first failed check, or null when the form is valid.  Extracted to
// module scope (takes ``t``) to keep the handleCreateChildHost callback simple.
const validateChildHostForm = (
    t: TFunction,
    formData: ChildHostFormData,
    computedFqdn: string,
): string | null => {
    if (!formData.distribution) {
        // Error is shown inline on the field (no snackbar).
        return null;
    }
    if (!formData.hostname || !computedFqdn) {
        return t('hostDetail.childHostHostnameRequired', 'Please enter a hostname');
    }
    if (!formData.username) {
        return t('hostDetail.childHostUsernameRequired', 'Please enter a username');
    }
    if (!formData.password) {
        return t('hostDetail.childHostPasswordRequired', 'Please enter a password');
    }
    if (formData.password !== formData.confirmPassword) {
        return t('hostDetail.childHostPasswordMismatch', 'Passwords do not match');
    }
    const needsVmName =
        formData.childType === 'vmm' ||
        formData.childType === 'kvm' ||
        formData.childType === 'bhyve';
    if (needsVmName && !formData.vmName) {
        return t('hostDetail.childHostVmNameRequired', 'Please enter a VM name');
    }
    // For VMM specifically, require root password (KVM uses cloud-init with user password).
    if (formData.childType === 'vmm') {
        if (!formData.rootPassword) {
            return t('hostDetail.childHostRootPasswordRequired', 'Please enter a root password');
        }
        if (formData.rootPassword !== formData.confirmRootPassword) {
            return t('hostDetail.childHostRootPasswordMismatch', 'Root passwords do not match');
        }
    }
    return null;
};

// Pure builder for the create-child request payload. Mirrors the per-type
// branching that used to live inline in handleCreateChildHost.
const buildCreateChildRequest = (
    formData: ChildHostFormData,
    computedFqdn: string,
): Record<string, string | boolean> => {
    const requestData: Record<string, string | boolean> = {
        child_type: formData.childType,
        distribution: formData.distribution,
        hostname: computedFqdn, // Always send the computed FQDN
        username: formData.username,
        password: formData.password,
        auto_approve: formData.autoApprove,
    };

    // For LXD, also send container name.
    if (formData.childType === 'lxd' && formData.containerName) {
        requestData.container_name = formData.containerName;
    }

    // For VMM, send vm_name, iso_url, and root_password.
    if (formData.childType === 'vmm') {
        requestData.vm_name = formData.vmName || formData.hostname;
        // For VMM, the install_identifier contains the ISO URL.
        if (formData.distribution) {
            requestData.iso_url = formData.distribution;
        }
        requestData.root_password = formData.rootPassword;
    }

    // For KVM and bhyve, send vm_name and cloud_image_url.
    if (formData.childType === 'kvm' || formData.childType === 'bhyve') {
        requestData.vm_name = formData.vmName || formData.hostname;
        if (formData.distribution) {
            requestData.cloud_image_url = formData.distribution;
        }
    }

    return requestData;
};

interface UseChildHostsArgs {
    hostId: string | undefined;
    host: SysManageHost | null;
    licenseModules: string[];
    currentTabId: string;
    supportsChildHosts: () => boolean;
    t: TFunction;
    setSnackbarMessage: React.Dispatch<React.SetStateAction<string>>;
    setSnackbarSeverity: React.Dispatch<React.SetStateAction<SnackbarSeverity>>;
    setSnackbarOpen: React.Dispatch<React.SetStateAction<boolean>>;
}

export const useChildHosts = ({
    hostId,
    host,
    licenseModules,
    currentTabId,
    supportsChildHosts,
    t,
    setSnackbarMessage,
    setSnackbarSeverity,
    setSnackbarOpen,
}: UseChildHostsArgs) => {
    const childHostsRefreshInterval = useRef<ReturnType<typeof setInterval> | null>(null);
    const childHostsLastAgentRefresh = useRef<number>(0);

    // Child hosts state
    const [childHosts, setChildHosts] = useState<ChildHost[]>([]);
    const [childHostsLoading, setChildHostsLoading] = useState<boolean>(false);
    const [childHostsRefreshRequested, setChildHostsRefreshRequested] = useState<boolean>(false);

    // Virtualization status state
    const [virtualizationStatus, setVirtualizationStatus] = useState<VirtualizationStatus | null>(null);
    const [virtualizationLoading, setVirtualizationLoading] = useState<boolean>(false);
    const [enableWslLoading, setEnableWslLoading] = useState<boolean>(false);
    const [initializeLxdLoading, setInitializeLxdLoading] = useState<boolean>(false);
    const [initializeVmmLoading, setInitializeVmmLoading] = useState<boolean>(false);
    const [initializeKvmLoading, setInitializeKvmLoading] = useState<boolean>(false);
    const [initializeBhyveLoading, setInitializeBhyveLoading] = useState<boolean>(false);
    const [disableBhyveLoading, setDisableBhyveLoading] = useState<boolean>(false);
    const [kvmModulesLoading, setKvmModulesLoading] = useState<boolean>(false);

    // Create child host modal state
    const explicitChildTypeRef = useRef<string | null>(null);
    const [createChildHostOpen, setCreateChildHostOpen] = useState<boolean>(false);
    const [createChildHostLoading, setCreateChildHostLoading] = useState<boolean>(false);
    const [childHostFormData, setChildHostFormData] = useState<ChildHostFormData>({
        childType: 'wsl',  // 'wsl' for Windows, 'lxd' for Linux, 'vmm' for OpenBSD
        distribution: '',
        containerName: '',  // For LXD containers
        vmName: '',  // For VMM virtual machines
        hostname: '',
        username: '',
        password: '',
        confirmPassword: '',
        rootPassword: '',  // For VMM: separate root password
        confirmRootPassword: '',  // For VMM: confirm root password
        autoApprove: false,  // Automatically approve when the child host connects
    });
    const [childHostCreationProgress, setChildHostCreationProgress] = useState<string>('');
    const [childHostFormValidated, setChildHostFormValidated] = useState<boolean>(false);
    const [availableDistributions, setAvailableDistributions] = useState<AvailableDistribution[]>([]);

    // Compute FQDN from hostname - appends server domain if not already an FQDN
    const getServerDomain = useCallback(() => {
        const hostname = globalThis.location.hostname;
        // Extract domain from hostname (e.g., "t14.theeverlys.com" -> "theeverlys.com")
        const parts = hostname.split('.');
        if (parts.length >= 2) {
            return parts.slice(1).join('.');
        }
        return hostname;
    }, []);

    const computedFqdn = useMemo(() => {
        const hostname = childHostFormData.hostname.trim().toLowerCase();
        if (!hostname) return '';
        // If already contains a dot, it's already an FQDN
        if (hostname.includes('.')) {
            return hostname;
        }
        // Append the server's domain
        return `${hostname}.${getServerDomain()}`;
    }, [childHostFormData.hostname, getServerDomain]);

    // Fetch distributions when create child host dialog opens
    const fetchDistributions = useCallback(async (childType: string) => {
        try {
            const distributions = await distributionService.getAll(childType);
            const activeDistributions = distributions
                .filter(d => d.is_active)
                .map(d => ({
                    id: d.id,
                    display_name: d.display_name,
                    install_identifier: d.install_identifier || '',
                    child_type: d.child_type,
                }));
            setAvailableDistributions(activeDistributions);
        } catch (error) {
            console.error('Error fetching distributions:', error);
            setAvailableDistributions([]);
        }
    }, []);

    // Auto-detect child type based on platform — ONLY when the dialog
    // was opened without an explicit type via openCreateDialogWithType.
    // We must NOT clear ``explicitChildTypeRef.current`` here: in React
    // 18 dev StrictMode the effect fires twice on mount/open, and on the
    // second fire a cleared ref would let the auto-detect block overwrite
    // the explicit choice (e.g. clicking "Create Container" on the LXD
    // card and ending up with childType='kvm').  Leave the ref alone;
    // it gets overwritten on the next openCreateDialogWithType call.
    useEffect(() => {
        if (createChildHostOpen && host) {
            if (explicitChildTypeRef.current) {
                return;
            }
            const platform = host.platform || '';
            const isLinux = platform.toLowerCase().includes('linux');
            const isOpenBSD = platform.includes('OpenBSD');
            const isFreeBSD = platform.includes('FreeBSD');
            let childType = 'wsl';
            if (isFreeBSD) {
                childType = 'bhyve';
            } else if (isOpenBSD) {
                childType = 'vmm';
            } else if (isLinux) {
                if (virtualizationStatus?.capabilities?.kvm?.initialized) {
                    childType = 'kvm';
                } else {
                    childType = 'lxd';
                }
            }
            setChildHostFormData(prev => ({
                ...prev,
                childType,
                distribution: '',
            }));
            fetchDistributions(childType);
        }
    }, [createChildHostOpen, host, fetchDistributions, virtualizationStatus]);

    // Child host control state (start/stop/restart/delete)
    const [childHostOperationLoading, setChildHostOperationLoading] = useState<Record<string, string | null>>({});
    const [deleteChildHostConfirmOpen, setDeleteChildHostConfirmOpen] = useState<boolean>(false);
    const [childHostToDelete, setChildHostToDelete] = useState<ChildHost | null>(null);

    const fetchChildHosts = useCallback(async (showLoading: boolean = true) => {
        if (!hostId) return;
        // Child-host management is a Professional+ feature (container_engine module).
        // Without the license the endpoint returns 402, so don't probe it in
        // Community Edition — avoids noisy console errors on every host-detail load.
        if (!licenseModules.includes('container_engine')) return;
        try {
            if (showLoading) {
                setChildHostsLoading(true);
            }
            const response = await axiosInstance.get(`/api/v1/host/${hostId}/children`);
            if (response.status === 200) {
                setChildHosts(response.data || []);
            }
        } catch (error) {
            console.error('Error fetching child hosts:', error);
            // Don't fail the whole page load for child host errors
            setChildHosts([]);
        } finally {
            if (showLoading) {
                setChildHostsLoading(false);
            }
        }
    }, [hostId, licenseModules]);

    // Fetch virtualization status
    const fetchVirtualizationStatus = useCallback(async () => {
        if (!hostId) return;
        // Virtualization status rides the same container_engine Pro+ license; skip
        // the call (it 402s) when the module isn't licensed.
        if (!licenseModules.includes('container_engine')) return;
        try {
            setVirtualizationLoading(true);
            const response = await axiosInstance.get(`/api/v1/host/${hostId}/virtualization/status`);
            if (response.status === 200) {
                setVirtualizationStatus(response.data);
            }
        } catch (error) {
            console.error('Error fetching virtualization status:', error);
            // Don't fail the whole page load for virtualization errors
            setVirtualizationStatus(null);
        } finally {
            setVirtualizationLoading(false);
        }
    }, [hostId, licenseModules]);

    const requestChildHostsRefresh = useCallback(async (showSnackbar: boolean = true) => {
        if (!hostId) return;
        try {
            setChildHostsRefreshRequested(true);
            // Request the agent to list child hosts with fresh status and refresh virtualization status
            const [childHostsResponse] = await Promise.all([
                axiosInstance.post(`/api/v1/host/${hostId}/children/refresh`),
                // Also request virtualization status refresh
                axiosInstance.get(`/api/v1/host/${hostId}/virtualization`).catch(err => {
                    console.log('Virtualization check request failed (optional):', err);
                    return null;
                })
            ]);
            if (childHostsResponse.status === 200) {
                if (showSnackbar) {
                    setSnackbarMessage(t('hostDetail.childHostsRefreshRequested', 'Child hosts refresh requested'));
                    setSnackbarSeverity('success');
                    setSnackbarOpen(true);
                }
                // Refetch child hosts and virtualization status after a short delay to allow collection to complete
                setTimeout(() => {
                    fetchChildHosts(false);
                    fetchVirtualizationStatus();
                    setChildHostsRefreshRequested(false);
                }, 3000);
            }
        } catch (error) {
            console.error('Error requesting child hosts refresh:', error);
            if (showSnackbar) {
                setSnackbarMessage(t('hostDetail.childHostsRefreshError', 'Error requesting child hosts refresh'));
                setSnackbarSeverity('error');
                setSnackbarOpen(true);
            }
            setChildHostsRefreshRequested(false);
        }
    }, [hostId, fetchChildHosts, fetchVirtualizationStatus, t, setSnackbarMessage, setSnackbarSeverity, setSnackbarOpen]);

    // Child host control functions (start/stop/restart/delete)
    const handleChildHostStart = useCallback(async (child: ChildHost) => {
        if (!hostId) return;
        try {
            setChildHostOperationLoading(prev => ({ ...prev, [child.id]: 'start' }));
            await axiosInstance.post(`/api/v1/host/${hostId}/children/${child.id}/start`);
            setSnackbarMessage(t('hostDetail.childHostStartRequested', 'Start requested for {{name}}', { name: child.child_name }));
            setSnackbarSeverity('success');
            setSnackbarOpen(true);
            // Refresh after a short delay
            setTimeout(() => {
                fetchChildHosts(false);
            }, 3000);
        } catch (error) {
            console.error('Error starting child host:', error);
            setSnackbarMessage(t('hostDetail.childHostStartError', 'Error starting child host'));
            setSnackbarSeverity('error');
            setSnackbarOpen(true);
        } finally {
            setChildHostOperationLoading(prev => ({ ...prev, [child.id]: null }));
        }
    }, [hostId, fetchChildHosts, t, setSnackbarMessage, setSnackbarSeverity, setSnackbarOpen]);

    const handleChildHostStop = useCallback(async (child: ChildHost) => {
        if (!hostId) return;
        try {
            setChildHostOperationLoading(prev => ({ ...prev, [child.id]: 'stop' }));
            await axiosInstance.post(`/api/v1/host/${hostId}/children/${child.id}/stop`);
            setSnackbarMessage(t('hostDetail.childHostStopRequested', 'Stop requested for {{name}}', { name: child.child_name }));
            setSnackbarSeverity('success');
            setSnackbarOpen(true);
            // Refresh after a short delay
            setTimeout(() => {
                fetchChildHosts(false);
            }, 3000);
        } catch (error) {
            console.error('Error stopping child host:', error);
            setSnackbarMessage(t('hostDetail.childHostStopError', 'Error stopping child host'));
            setSnackbarSeverity('error');
            setSnackbarOpen(true);
        } finally {
            setChildHostOperationLoading(prev => ({ ...prev, [child.id]: null }));
        }
    }, [hostId, fetchChildHosts, t, setSnackbarMessage, setSnackbarSeverity, setSnackbarOpen]);

    const handleChildHostRestart = useCallback(async (child: ChildHost) => {
        if (!hostId) return;
        try {
            setChildHostOperationLoading(prev => ({ ...prev, [child.id]: 'restart' }));
            await axiosInstance.post(`/api/v1/host/${hostId}/children/${child.id}/restart`);
            setSnackbarMessage(t('hostDetail.childHostRestartRequested', 'Restart requested for {{name}}', { name: child.child_name }));
            setSnackbarSeverity('success');
            setSnackbarOpen(true);
            // Refresh after a short delay
            setTimeout(() => {
                fetchChildHosts(false);
            }, 5000);
        } catch (error) {
            console.error('Error restarting child host:', error);
            setSnackbarMessage(t('hostDetail.childHostRestartError', 'Error restarting child host'));
            setSnackbarSeverity('error');
            setSnackbarOpen(true);
        } finally {
            setChildHostOperationLoading(prev => ({ ...prev, [child.id]: null }));
        }
    }, [hostId, fetchChildHosts, t, setSnackbarMessage, setSnackbarSeverity, setSnackbarOpen]);

    const handleChildHostUpdateAgent = useCallback(async (child: ChildHost) => {
        if (!hostId) return;
        try {
            setChildHostOperationLoading(prev => ({ ...prev, [child.id]: 'update-agent' }));
            await axiosInstance.post(`/api/v1/host/${hostId}/children/${child.id}/update-agent`);
            setSnackbarMessage(t('hosts.updateAgentRequested', 'Agent update requested successfully'));
            setSnackbarSeverity('success');
            setSnackbarOpen(true);
            // Refresh after a short delay
            setTimeout(() => {
                fetchChildHosts(false);
            }, 5000);
        } catch (error) {
            console.error('Error requesting child host agent update:', error);
            setSnackbarMessage(t('hosts.updateAgentFailed', 'Failed to request agent update'));
            setSnackbarSeverity('error');
            setSnackbarOpen(true);
        } finally {
            setChildHostOperationLoading(prev => ({ ...prev, [child.id]: null }));
        }
    }, [hostId, fetchChildHosts, t, setSnackbarMessage, setSnackbarSeverity, setSnackbarOpen]);

    const handleChildHostDeleteConfirm = useCallback((child: ChildHost) => {
        setChildHostToDelete(child);
        setDeleteChildHostConfirmOpen(true);
    }, []);

    const handleChildHostDeleteCancel = useCallback(() => {
        setChildHostToDelete(null);
        setDeleteChildHostConfirmOpen(false);
    }, []);

    const handleChildHostDelete = useCallback(async () => {
        if (!hostId || !childHostToDelete) return;
        try {
            setChildHostOperationLoading(prev => ({ ...prev, [childHostToDelete.id]: 'delete' }));
            setDeleteChildHostConfirmOpen(false);
            await axiosInstance.delete(`/api/v1/host/${hostId}/children/${childHostToDelete.id}`);
            setSnackbarMessage(t('hostDetail.childHostDeleteRequested', 'Delete requested for {{name}}', { name: childHostToDelete.child_name }));
            setSnackbarSeverity('success');
            setSnackbarOpen(true);
            // Refresh after a short delay
            setTimeout(() => {
                fetchChildHosts(false);
            }, 3000);
        } catch (error) {
            // Check if this is a 404 (child host already removed)
            if (axios.isAxiosError(error) && error.response?.status === 404) {
                setSnackbarMessage(t('hostDetail.childHostNotFound', 'Child host not found - it may have already been deleted'));
                setSnackbarSeverity('warning');
                setSnackbarOpen(true);
                // Refresh the list to remove the stale entry
                setTimeout(() => {
                    fetchChildHosts(false);
                }, 1000);
            } else {
                console.error('Error deleting child host:', error);
                let errorMessage = t('hostDetail.childHostDeleteError', 'Error deleting child host');
                if (axios.isAxiosError(error) && error.response?.data?.detail) {
                    errorMessage = error.response.data.detail;
                }
                setSnackbarMessage(errorMessage);
                setSnackbarSeverity('error');
                setSnackbarOpen(true);
            }
        } finally {
            setChildHostOperationLoading(prev => ({ ...prev, [childHostToDelete.id]: null }));
            setChildHostToDelete(null);
        }
    }, [hostId, childHostToDelete, fetchChildHosts, t, setSnackbarMessage, setSnackbarSeverity, setSnackbarOpen]);

    // Enable WSL on Windows host
    const handleEnableWsl = useCallback(async () => {
        if (!hostId) return;
        try {
            setEnableWslLoading(true);
            const response = await axiosInstance.post(`/api/v1/host/${hostId}/virtualization/enable-wsl`);
            if (response.status === 200) {
                const result = response.data;
                if (result.reboot_required) {
                    setSnackbarMessage(t('hostDetail.wslEnabledRebootRequired', 'WSL has been enabled. A reboot is required to complete the installation.'));
                } else {
                    setSnackbarMessage(t('hostDetail.wslEnabledSuccess', 'WSL has been enabled successfully.'));
                }
                setSnackbarSeverity('success');
                setSnackbarOpen(true);
                // Refresh virtualization status
                setTimeout(() => {
                    fetchVirtualizationStatus();
                }, 3000);
            }
        } catch (error) {
            console.error('Error enabling WSL:', error);
            setSnackbarMessage(t('hostDetail.wslEnableFailed', 'Failed to enable WSL'));
            setSnackbarSeverity('error');
            setSnackbarOpen(true);
        } finally {
            setEnableWslLoading(false);
        }
    }, [hostId, fetchVirtualizationStatus, t, setSnackbarMessage, setSnackbarSeverity, setSnackbarOpen]);

    // Initialize LXD on Linux host
    const handleInitializeLxd = useCallback(async () => {
        if (!hostId) return;
        try {
            setInitializeLxdLoading(true);
            const response = await axiosInstance.post(`/api/v1/host/${hostId}/virtualization/initialize-lxd`);
            if (response.status === 200) {
                setSnackbarMessage(t('hostDetail.lxdInitializedSuccess', 'LXD initialization requested. The agent will install and configure LXD.'));
                setSnackbarSeverity('success');
                setSnackbarOpen(true);
                // Refresh virtualization status after a delay
                setTimeout(() => {
                    fetchVirtualizationStatus();
                }, 5000);
            }
        } catch (error) {
            console.error('Error initializing LXD:', error);
            setSnackbarMessage(t('hostDetail.lxdInitializeFailed', 'Failed to initialize LXD'));
            setSnackbarSeverity('error');
            setSnackbarOpen(true);
        } finally {
            setInitializeLxdLoading(false);
        }
    }, [hostId, fetchVirtualizationStatus, t, setSnackbarMessage, setSnackbarSeverity, setSnackbarOpen]);

    // Initialize VMM on OpenBSD host
    const handleInitializeVmm = useCallback(async () => {
        if (!hostId) return;
        try {
            setInitializeVmmLoading(true);
            const response = await axiosInstance.post(`/api/v1/host/${hostId}/virtualization/initialize-vmm`);
            if (response.status === 200) {
                setSnackbarMessage(t('hostDetail.vmmInitializedSuccess', 'VMM initialization requested. The agent will enable and start the vmd daemon.'));
                setSnackbarSeverity('success');
                setSnackbarOpen(true);
                // Refresh virtualization status after a delay
                setTimeout(() => {
                    fetchVirtualizationStatus();
                }, 5000);
            }
        } catch (error) {
            console.error('Error initializing VMM:', error);
            setSnackbarMessage(t('hostDetail.vmmInitializeFailed', 'Failed to initialize VMM'));
            setSnackbarSeverity('error');
            setSnackbarOpen(true);
        } finally {
            setInitializeVmmLoading(false);
        }
    }, [hostId, fetchVirtualizationStatus, t, setSnackbarMessage, setSnackbarSeverity, setSnackbarOpen]);

    // Initialize KVM on Linux host
    const handleInitializeKvm = useCallback(async () => {
        if (!hostId) return;
        try {
            setInitializeKvmLoading(true);
            const response = await axiosInstance.post(`/api/v1/host/${hostId}/virtualization/initialize-kvm`);
            if (response.status === 200) {
                setSnackbarMessage(t('hostDetail.kvmInitializedSuccess', 'KVM initialization requested. The agent will install and configure libvirt.'));
                setSnackbarSeverity('success');
                setSnackbarOpen(true);
                // Refresh virtualization status after a delay
                setTimeout(() => {
                    fetchVirtualizationStatus();
                }, 5000);
            }
        } catch (error) {
            console.error('Error initializing KVM:', error);
            setSnackbarMessage(t('hostDetail.kvmInitializeFailed', 'Failed to initialize KVM'));
            setSnackbarSeverity('error');
            setSnackbarOpen(true);
        } finally {
            setInitializeKvmLoading(false);
        }
    }, [hostId, fetchVirtualizationStatus, t, setSnackbarMessage, setSnackbarSeverity, setSnackbarOpen]);

    // Initialize bhyve on FreeBSD host
    const handleInitializeBhyve = useCallback(async () => {
        if (!hostId) return;
        try {
            setInitializeBhyveLoading(true);
            const response = await axiosInstance.post(`/api/v1/host/${hostId}/virtualization/initialize-bhyve`);
            if (response.status === 200) {
                setSnackbarMessage(t('hostDetail.bhyveInitializedSuccess', 'bhyve initialization requested. The agent will load vmm.ko and configure the system.'));
                setSnackbarSeverity('success');
                setSnackbarOpen(true);
                // Refresh virtualization status after a delay
                setTimeout(() => {
                    fetchVirtualizationStatus();
                }, 5000);
            }
        } catch (error) {
            console.error('Error initializing bhyve:', error);
            setSnackbarMessage(t('hostDetail.bhyveInitializeFailed', 'Failed to initialize bhyve'));
            setSnackbarSeverity('error');
            setSnackbarOpen(true);
        } finally {
            setInitializeBhyveLoading(false);
        }
    }, [hostId, fetchVirtualizationStatus, t, setSnackbarMessage, setSnackbarSeverity, setSnackbarOpen]);

    // Disable bhyve on FreeBSD host
    const handleDisableBhyve = useCallback(async () => {
        if (!hostId) return;
        try {
            setDisableBhyveLoading(true);
            const response = await axiosInstance.post(`/api/v1/host/${hostId}/virtualization/disable-bhyve`);
            if (response.status === 200) {
                setSnackbarMessage(t('hostDetail.bhyveDisabledSuccess', 'bhyve disable requested. The agent will unload vmm.ko and update the configuration.'));
                setSnackbarSeverity('success');
                setSnackbarOpen(true);
                // Refresh virtualization status after a delay
                setTimeout(() => {
                    fetchVirtualizationStatus();
                }, 5000);
            }
        } catch (error) {
            console.error('Error disabling bhyve:', error);
            setSnackbarMessage(t('hostDetail.bhyveDisableFailed', 'Failed to disable bhyve'));
            setSnackbarSeverity('error');
            setSnackbarOpen(true);
        } finally {
            setDisableBhyveLoading(false);
        }
    }, [hostId, fetchVirtualizationStatus, t, setSnackbarMessage, setSnackbarSeverity, setSnackbarOpen]);

    // Enable KVM modules via modprobe
    const handleEnableKvmModules = useCallback(async () => {
        if (!hostId) return;
        try {
            setKvmModulesLoading(true);
            const response = await axiosInstance.post(`/api/v1/host/${hostId}/virtualization/enable-kvm-modules`);
            if (response.status === 200) {
                setSnackbarMessage(t('hostDetail.kvmModulesEnableSuccess', 'KVM modules enable requested. The agent will load the kernel modules.'));
                setSnackbarSeverity('success');
                setSnackbarOpen(true);
                // Refresh virtualization status after a delay (needs time for queue round-trip)
                setTimeout(() => {
                    fetchVirtualizationStatus();
                }, 6000);
            }
        } catch (error) {
            console.error('Error enabling KVM modules:', error);
            setSnackbarMessage(t('hostDetail.kvmModulesEnableFailed', 'Failed to enable KVM modules'));
            setSnackbarSeverity('error');
            setSnackbarOpen(true);
        } finally {
            setKvmModulesLoading(false);
        }
    }, [hostId, fetchVirtualizationStatus, t, setSnackbarMessage, setSnackbarSeverity, setSnackbarOpen]);

    // Disable KVM modules via modprobe -r
    const handleDisableKvmModules = useCallback(async () => {
        if (!hostId) return;
        try {
            setKvmModulesLoading(true);
            const response = await axiosInstance.post(`/api/v1/host/${hostId}/virtualization/disable-kvm-modules`);
            if (response.status === 200) {
                setSnackbarMessage(t('hostDetail.kvmModulesDisableSuccess', 'KVM modules disable requested. The agent will unload the kernel modules.'));
                setSnackbarSeverity('success');
                setSnackbarOpen(true);
                // Refresh virtualization status after a delay (needs time for queue round-trip)
                setTimeout(() => {
                    fetchVirtualizationStatus();
                }, 6000);
            }
        } catch (error) {
            console.error('Error disabling KVM modules:', error);
            setSnackbarMessage(t('hostDetail.kvmModulesDisableFailed', 'Failed to disable KVM modules. Ensure no VMs are running.'));
            setSnackbarSeverity('error');
            setSnackbarOpen(true);
        } finally {
            setKvmModulesLoading(false);
        }
    }, [hostId, fetchVirtualizationStatus, t, setSnackbarMessage, setSnackbarSeverity, setSnackbarOpen]);

    // Open create dialog with a specific child type (called from HypervisorStatusCard)
    const openCreateDialogWithType = useCallback((childType: string) => {
        explicitChildTypeRef.current = childType;
        setChildHostFormData(prev => ({
            ...prev,
            childType,
            distribution: '',  // Reset distribution when type changes
            containerName: '',
            vmName: '',
            hostname: '',
            username: '',
            password: '',
            confirmPassword: '',
            rootPassword: '',
            confirmRootPassword: '',
            autoApprove: false,
        }));
        fetchDistributions(childType);
        setCreateChildHostOpen(true);
    }, [fetchDistributions]);

    // Create child host
    // Complex form validation and conditional request building for multiple child host types (WSL, LXD, VMM, KVM, bhyve)
    const handleCreateChildHost = useCallback(async () => {
        if (!hostId) return;

        // Mark form as validated to show inline errors
        setChildHostFormValidated(true);

        // Validate form (pure helper returns the first failed check, or null)
        const validationError = validateChildHostForm(t, childHostFormData, computedFqdn);
        if (validationError) {
            setSnackbarMessage(validationError);
            setSnackbarSeverity('error');
            setSnackbarOpen(true);
            return;
        }
        // A missing distribution is shown inline (no snackbar) and blocks submit.
        if (!childHostFormData.distribution) {
            return;
        }

        try {
            setCreateChildHostLoading(true);
            setChildHostCreationProgress(t('hostDetail.childHostCreationStarting', 'Starting child host creation...'));

            // Build request based on child type (pure helper)
            const requestData = buildCreateChildRequest(childHostFormData, computedFqdn);

            const response = await axiosInstance.post(`/api/v1/host/${hostId}/virtualization/create-child`, requestData);

            if (response.status === 200) {
                const result = response.data;
                if (result.success) {
                    setSnackbarMessage(t('hostDetail.childHostCreated', 'Child host created successfully'));
                    setSnackbarSeverity('success');
                    setSnackbarOpen(true);
                    setCreateChildHostOpen(false);
                    // Reset form
                    setChildHostFormValidated(false);
                    setChildHostFormData({
                        childType: childHostFormData.childType,  // Keep the child type
                        distribution: '',
                        containerName: '',
                        vmName: '',
                        hostname: '',
                        username: '',
                        password: '',
                        confirmPassword: '',
                        rootPassword: '',
                        confirmRootPassword: '',
                        autoApprove: false,
                    });
                    // Refresh child hosts list
                    setTimeout(() => {
                        fetchChildHosts();
                    }, 3000);
                } else if (result.reboot_required) {
                    setSnackbarMessage(t('hostDetail.childHostNeedsReboot', 'WSL needs to be enabled. A reboot is required first.'));
                    setSnackbarSeverity('warning');
                    setSnackbarOpen(true);
                } else {
                    setSnackbarMessage(result.error || t('hostDetail.childHostCreationFailed', 'Failed to create child host'));
                    setSnackbarSeverity('error');
                    setSnackbarOpen(true);
                }
            }
        } catch (error: unknown) {
            console.error('Error creating child host:', error);
            // Extract error message from axios error response
            let errorMessage = t('hostDetail.childHostCreationFailed', 'Failed to create child host');
            if (axios.isAxiosError(error) && error.response?.data?.detail) {
                errorMessage = error.response.data.detail;
            }
            setSnackbarMessage(errorMessage);
            setSnackbarSeverity('error');
            setSnackbarOpen(true);
        } finally {
            setCreateChildHostLoading(false);
            setChildHostCreationProgress('');
        }
    }, [hostId, childHostFormData, computedFqdn, fetchChildHosts, t, setSnackbarMessage, setSnackbarSeverity, setSnackbarOpen]);

    // Auto-refresh Child Hosts and Virtualization Status every 15 seconds when on Child Hosts tab
    // Also trigger an agent refresh when first opening the tab (to get live status from WSL)
    // Pause auto-refresh when Create Child Host modal is open to prevent interference
    useEffect(() => {
        if (currentTabId === 'child-hosts' && host?.active && supportsChildHosts() && !createChildHostOpen) {
            // When tab is first opened, request fresh status from agent
            // Only do this once every 30 seconds to avoid spamming
            const now = Date.now();
            if (now - childHostsLastAgentRefresh.current > 30000) {
                childHostsLastAgentRefresh.current = now;
                // Request fresh child host status from agent (silently, no snackbar)
                requestChildHostsRefresh(false);
            }

            // Start auto-refresh every 15 seconds (without loading indicator)
            const interval = setInterval(() => {
                fetchChildHosts(false);
                fetchVirtualizationStatus();
            }, 15000);
            childHostsRefreshInterval.current = interval;

            return () => {
                if (interval) {
                    clearInterval(interval);
                }
            };
        } else if (childHostsRefreshInterval.current) {
            // Clear interval when tab is not active, host is not active, or modal is open
            clearInterval(childHostsRefreshInterval.current);
            childHostsRefreshInterval.current = null;
        }
    }, [currentTabId, host?.active, host?.id, fetchChildHosts, fetchVirtualizationStatus, supportsChildHosts, host, requestChildHostsRefresh, createChildHostOpen]);

    const getWslEmptyMessage = (): string => {
        if (virtualizationStatus?.capabilities?.wsl?.enabled) {
            return t('hostDetail.childHostsEmptyWslEnabled', 'Click "Create Child Host" to create a new WSL instance.');
        }
        if (virtualizationStatus?.capabilities?.wsl?.needs_enable) {
            return t('hostDetail.childHostsEmptyWslNotEnabled', 'Enable WSL to create virtual machines on this host.');
        }
        return t('hostDetail.childHostsEmptyDescription', 'WSL instances and other virtual machines on this Windows host will appear here.');
    };

    // Helper function to get empty state message for Linux hosts (LXD)
    const getLxdEmptyMessage = (): string => {
        if (virtualizationStatus?.capabilities?.lxd?.installed && virtualizationStatus?.capabilities?.lxd?.initialized) {
            return t('hostDetail.childHostsEmptyLxdReady', 'Click "Create Child Host" to create a new LXD container.');
        }
        if (virtualizationStatus?.capabilities?.lxd?.available) {
            return t('hostDetail.childHostsEmptyLxdNotReady', 'Enable LXD to create containers on this host.');
        }
        return t('hostDetail.childHostsEmptyLxdNotAvailable', 'LXD is not available on this host. Ubuntu 22.04 or newer is required.');
    };

    // Helper function to get empty state message for OpenBSD hosts (VMM)
    const getVmmEmptyMessage = (): string => {
        if (virtualizationStatus?.capabilities?.vmm?.enabled && virtualizationStatus?.capabilities?.vmm?.running) {
            return t('hostDetail.childHostsEmptyVmmReady', 'Click "Create Child Host" to create a new VMM virtual machine.');
        }
        if (virtualizationStatus?.capabilities?.vmm?.available) {
            return t('hostDetail.childHostsEmptyVmmNotReady', 'Enable VMM to create virtual machines on this host.');
        }
        return t('hostDetail.childHostsEmptyVmmNotAvailable', 'VMM is not available on this host.');
    };

    // Helper function to get empty state message for FreeBSD hosts (bhyve)
    const getBhyveEmptyMessage = (): string => {
        if (virtualizationStatus?.capabilities?.bhyve?.enabled && virtualizationStatus?.capabilities?.bhyve?.running) {
            return t('hostDetail.childHostsEmptyBhyveReady', 'Click "Create Child Host" to create a new bhyve virtual machine.');
        }
        if (virtualizationStatus?.capabilities?.bhyve?.available) {
            return t('hostDetail.childHostsEmptyBhyveNotReady', 'Enable bhyve to create virtual machines on this host.');
        }
        return t('hostDetail.childHostsEmptyBhyveNotAvailable', 'bhyve is not available on this host.');
    };

    // Helper function to get the create child host dialog title
    const getCreateChildHostTitle = (): string => {
        switch (childHostFormData.childType) {
            case 'lxd':
                return t('hostDetail.createLxdContainerTitle', 'Create LXD Container');
            case 'vmm':
                return t('hostDetail.createVmmVmTitle', 'Create VMM Virtual Machine');
            case 'kvm':
                return t('hostDetail.createKvmVmTitle', 'Create KVM Virtual Machine');
            case 'bhyve':
                return t('hostDetail.createBhyveVmTitle', 'Create bhyve Virtual Machine');
            default:
                return t('hostDetail.createChildHostTitle', 'Create WSL Instance');
        }
    };
    return {
        childHosts,
        setChildHosts,
        childHostsLoading,
        childHostsRefreshRequested,
        virtualizationStatus,
        virtualizationLoading,
        enableWslLoading,
        initializeLxdLoading,
        initializeVmmLoading,
        initializeKvmLoading,
        initializeBhyveLoading,
        disableBhyveLoading,
        kvmModulesLoading,
        createChildHostOpen,
        setCreateChildHostOpen,
        createChildHostLoading,
        childHostFormData,
        setChildHostFormData,
        childHostCreationProgress,
        childHostFormValidated,
        setChildHostFormValidated,
        availableDistributions,
        computedFqdn,
        childHostOperationLoading,
        deleteChildHostConfirmOpen,
        childHostToDelete,
        fetchChildHosts,
        fetchVirtualizationStatus,
        requestChildHostsRefresh,
        handleChildHostStart,
        handleChildHostStop,
        handleChildHostRestart,
        handleChildHostUpdateAgent,
        handleChildHostDeleteConfirm,
        handleChildHostDeleteCancel,
        handleChildHostDelete,
        handleEnableWsl,
        handleInitializeLxd,
        handleInitializeVmm,
        handleInitializeKvm,
        handleInitializeBhyve,
        handleDisableBhyve,
        handleEnableKvmModules,
        handleDisableKvmModules,
        openCreateDialogWithType,
        handleCreateChildHost,
        getWslEmptyMessage,
        getLxdEmptyMessage,
        getVmmEmptyMessage,
        getBhyveEmptyMessage,
        getCreateChildHostTitle,
    };
};
