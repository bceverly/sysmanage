// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

// Software inventory, installation history, and package install/uninstall/search
// state, effects and handlers for the Host Detail page.

import React, { useCallback, useEffect, useRef, useState } from 'react';
import type { TFunction } from 'i18next';
import axiosInstance from '../../Services/api';
import { SysManageHost, SoftwarePackage, PaginationInfo, doGetHostSoftware, doRequestPackages } from '../../Services/hosts';
import { SysManageUser } from '../../Services/users';
import { InstallationHistoryItem } from './hostDetailTypes';
import type { SnackbarSeverity } from './useHostSnackbar';

interface TabDef { id: string; }

interface UseHostSoftwareArgs {
    hostId: string | undefined;
    host: SysManageHost | null;
    currentTabId: string;
    currentUser: SysManageUser | null;
    tabDefinitions: TabDef[];
    setCurrentTab: React.Dispatch<React.SetStateAction<number>>;
    t: TFunction;
    setSnackbarMessage: React.Dispatch<React.SetStateAction<string>>;
    setSnackbarSeverity: React.Dispatch<React.SetStateAction<SnackbarSeverity>>;
    setSnackbarOpen: React.Dispatch<React.SetStateAction<boolean>>;
}

export const useHostSoftware = ({
    hostId,
    host,
    currentTabId,
    currentUser,
    tabDefinitions,
    setCurrentTab,
    t,
    setSnackbarMessage,
    setSnackbarSeverity,
    setSnackbarOpen,
}: UseHostSoftwareArgs) => {
    const [softwarePackages, setSoftwarePackages] = useState<SoftwarePackage[]>([]);
    const [loadingSoftware, setLoadingSoftware] = useState<boolean>(false);
    const [softwarePagination, setSoftwarePagination] = useState<PaginationInfo>({
        page: 1,
        page_size: 100,
        total_items: 0,
        total_pages: 0,
        has_next: false,
        has_prev: false
    });
    const [softwareSearchTerm, setSoftwareSearchTerm] = useState<string>('');

    const [packageInstallDialogOpen, setPackageInstallDialogOpen] = useState<boolean>(false);
    const packageSearchInputRef = useRef<HTMLInputElement>(null);

    const [searchResults, setSearchResults] = useState<Array<{name: string, description?: string, version?: string}>>([]);
    const [selectedPackages, setSelectedPackages] = useState<Set<string>>(new Set());
    const [isSearching, setIsSearching] = useState<boolean>(false);

    const [installationHistory, setInstallationHistory] = useState<InstallationHistoryItem[]>([]);
    const [installationHistoryLoading, setInstallationHistoryLoading] = useState<boolean>(false);
    const [selectedInstallationLog, setSelectedInstallationLog] = useState<InstallationHistoryItem | null>(null);
    const [installationLogDialogOpen, setInstallationLogDialogOpen] = useState<boolean>(false);
    const [installationDeleteConfirmOpen, setInstallationDeleteConfirmOpen] = useState<boolean>(false);
    const [installationToDelete, setInstallationToDelete] = useState<InstallationHistoryItem | null>(null);

    const [uninstallConfirmOpen, setUninstallConfirmOpen] = useState<boolean>(false);
    const [packageToUninstall, setPackageToUninstall] = useState<SoftwarePackage | null>(null);

    const [requestPackagesConfirmOpen, setRequestPackagesConfirmOpen] = useState<boolean>(false);

    const fetchInstallationHistory = useCallback(async () => {
        if (!hostId) return;

        setInstallationHistoryLoading(true);
        try {
            const response = await axiosInstance.get(`/api/v1/packages/installation-history/${hostId}`);
            setInstallationHistory(response.data.installations || []);
        } catch (error) {
            console.error('Error fetching installation history:', error);
            setInstallationHistory([]);
        } finally {
            setInstallationHistoryLoading(false);
        }
    }, [hostId]);

    const performPackageSearch = useCallback(async (query: string) => {
        if (!hostId || !query.trim()) return;

        setIsSearching(true);
        try {
            // Get host information to determine OS for package search
            const response = await axiosInstance.get(`/api/v1/packages/search?query=${encodeURIComponent(query)}&limit=20`);

            if (response.data && Array.isArray(response.data)) {
                // Get list of already installed package names
                const installedPackageNames = new Set(
                    softwarePackages
                        .filter(pkg => pkg.package_name) // Filter out packages without names
                        .map(pkg => pkg.package_name.toLowerCase())
                );

                // Filter out already installed packages
                const results = response.data
                    .filter((pkg: { name: string; description: string; version: string }) =>
                        !installedPackageNames.has(pkg.name.toLowerCase())
                    )
                    .map((pkg: { name: string; description: string; version: string }) => ({
                        name: pkg.name,
                        description: pkg.description,
                        version: pkg.version
                    }));
                setSearchResults(results);
            } else {
                setSearchResults([]);
            }
        } catch (error) {
            console.error('Error searching packages:', error);
            // Check if it's an authentication error
            const axiosError = error as { response?: { status?: number; data?: { detail?: string } } };
            if (axiosError.response?.status === 401 || axiosError.response?.status === 403) {
                console.error('Authentication error while searching packages. User may need to log in again.');
                // You could trigger a re-login here or show an auth error message
            }
            // Fall back to empty results on error
            setSearchResults([]);
        } finally {
            setIsSearching(false);
        }
    }, [hostId, softwarePackages]);

    const handleRequestPackages = () => {
        setRequestPackagesConfirmOpen(true);
    };

    const handleRequestPackagesConfirm = async () => {
        if (!host?.id) return;
        setRequestPackagesConfirmOpen(false);

        try {
            await doRequestPackages(host.id);
            setSnackbarMessage(t('hosts.packagesRequested', 'Package collection requested successfully'));
            setSnackbarOpen(true);
        } catch (error) {
            console.error('Failed to request package collection:', error);
            setSnackbarMessage(t('hosts.packagesRequestFailed', 'Failed to request package collection'));
            setSnackbarOpen(true);
        }
    };

    const handlePackageSelect = (packageName: string) => {
        const newSelected = new Set(selectedPackages);
        if (newSelected.has(packageName)) {
            newSelected.delete(packageName);
        } else {
            newSelected.add(packageName);
        }
        setSelectedPackages(newSelected);
    };

    const handleInstallPackages = async () => {
        if (!hostId || selectedPackages.size === 0) return;

        try {
            const response = await axiosInstance.post(`/api/v1/packages/install/${hostId}`, {
                package_names: Array.from(selectedPackages),
                requested_by: currentUser ? `${currentUser.first_name || ''} ${currentUser.last_name || ''}`.trim() || currentUser.userid : 'Unknown User'
            });

            if (response.data.success) {
                // Close dialog and reset state
                setPackageInstallDialogOpen(false);
                if (packageSearchInputRef.current) {
                    packageSearchInputRef.current.value = '';
                }
                setSearchResults([]);
                setSelectedPackages(new Set());

                // Navigate to Software Changes tab to show progress
                const swChangesIdx = tabDefinitions.findIndex(td => td.id === 'software-changes');
                if (swChangesIdx >= 0) setCurrentTab(swChangesIdx);

                // Show success message
                setSnackbarMessage(response.data.message || t('hostDetail.packagesInstallQueued', 'Package installation has been queued'));
                setSnackbarSeverity('success');
                setSnackbarOpen(true);
            } else {
                throw new Error(response.data.message || 'Unknown error');
            }
        } catch (error: unknown) {
            console.error('Error installing packages:', error);
            const axiosError = error as { response?: { data?: { detail?: string } }; message?: string };
            const errorMessage = axiosError.response?.data?.detail || axiosError.message || t('hostDetail.packagesInstallError', 'Error queueing package installation');
            setSnackbarMessage(errorMessage);
            setSnackbarSeverity('error');
            setSnackbarOpen(true);
        }
    };

    const handleClosePackageDialog = () => {
        setPackageInstallDialogOpen(false);
        if (packageSearchInputRef.current) {
            packageSearchInputRef.current.value = '';
        }
        setSearchResults([]);
        setSelectedPackages(new Set());
    };

    // Uninstall handlers
    const handleUninstallPackage = (pkg: SoftwarePackage) => {
        setPackageToUninstall(pkg);
        setUninstallConfirmOpen(true);
    };

    const handleUninstallConfirm = async () => {
        if (!hostId || !packageToUninstall) return;

        try {
            const response = await axiosInstance.post(`/api/v1/packages/uninstall/${hostId}`, {
                package_names: [packageToUninstall.package_name],
                requested_by: currentUser ? `${currentUser.first_name || ''} ${currentUser.last_name || ''}`.trim() || currentUser.userid : 'Unknown User'
            });

            if (response.data.success) {
                // Close dialog and reset state
                setUninstallConfirmOpen(false);
                setPackageToUninstall(null);

                // Navigate to Software Changes tab to show progress
                const swChangesIdx = tabDefinitions.findIndex(td => td.id === 'software-changes');
                if (swChangesIdx >= 0) setCurrentTab(swChangesIdx);

                // Show success message
                setSnackbarMessage(response.data.message || t('hostDetail.packageUninstallQueued', 'Package uninstallation has been queued'));
                setSnackbarSeverity('success');
                setSnackbarOpen(true);
            } else {
                throw new Error(response.data.message || 'Unknown error');
            }
        } catch (error: unknown) {
            const axiosError = error as { response?: { data?: { detail?: string } }; message?: string };
            const errorMessage = axiosError.response?.data?.detail || axiosError.message || t('hostDetail.packageUninstallError', 'Error queueing package uninstallation');
            setSnackbarMessage(errorMessage);
            setSnackbarSeverity('error');
            setSnackbarOpen(true);
        }
    };

    const handleUninstallCancel = () => {
        setUninstallConfirmOpen(false);
        setPackageToUninstall(null);
    };

    // Installation history handlers

    const handleViewInstallationLog = (installation: InstallationHistoryItem) => {
        setSelectedInstallationLog(installation);
        setInstallationLogDialogOpen(true);
    };

    const handleCloseInstallationLogDialog = () => {
        setInstallationLogDialogOpen(false);
        setSelectedInstallationLog(null);
    };

    const handleDeleteInstallation = (installation: InstallationHistoryItem) => {
        setInstallationToDelete(installation);
        setInstallationDeleteConfirmOpen(true);
    };

    const handleConfirmDeleteInstallation = async () => {
        if (!installationToDelete) return;

        try {
            await axiosInstance.delete(`/api/v1/packages/installation-history/${installationToDelete.request_id}`);
            setSnackbarMessage(t('hostDetail.installationDeleted', 'Installation record deleted successfully'));
            setSnackbarSeverity('success');
            setSnackbarOpen(true);
            // Refresh the installation history
            fetchInstallationHistory();
        } catch (error) {
            console.error('Error deleting installation record:', error);
            setSnackbarMessage(t('hostDetail.installationDeleteError', 'Failed to delete installation record'));
            setSnackbarSeverity('error');
            setSnackbarOpen(true);
        } finally {
            setInstallationDeleteConfirmOpen(false);
            setInstallationToDelete(null);
        }
    };

    const handleCancelDeleteInstallation = () => {
        setInstallationDeleteConfirmOpen(false);
        setInstallationToDelete(null);
    };

    // Load software packages lazily when Software tab is selected or pagination changes
    useEffect(() => {
        const loadSoftwarePackages = async () => {
            if (currentTabId === 'software' && hostId) {
                try {
                    setLoadingSoftware(true);
                    const response = await doGetHostSoftware(
                        hostId,
                        softwarePagination.page,
                        softwarePagination.page_size,
                        softwareSearchTerm || undefined
                    );
                    setSoftwarePackages(response.items);
                    setSoftwarePagination(response.pagination);
                } catch (error) {
                    console.error('Failed to load software packages:', error);
                } finally {
                    setLoadingSoftware(false);
                }
            }
        };
        loadSoftwarePackages();
    }, [currentTabId, hostId, softwarePagination.page, softwarePagination.page_size, softwareSearchTerm]);

    // Load installation history when Software Changes tab is selected
    useEffect(() => {
        if (currentTabId === 'software-changes') {
            fetchInstallationHistory();
        }
    }, [currentTabId, hostId, fetchInstallationHistory]);

    // Auto-refresh installation history every 30 seconds when on Software Changes tab
    useEffect(() => {
        let interval: ReturnType<typeof globalThis.setInterval> | null = null;
        if (hostId && currentTabId === 'software-changes') {
            interval = globalThis.setInterval(async () => {
                try {
                    await fetchInstallationHistory();
                } catch (error) {
                    console.error('Auto-refresh error for installation history:', error);
                }
            }, 30000); // 30 seconds
        }
        return () => {
            if (interval) {
                globalThis.clearInterval(interval);
            }
        };
    }, [hostId, currentTabId, fetchInstallationHistory]);
    return {
        softwarePackages,
        setSoftwarePackages,
        loadingSoftware,
        softwarePagination,
        setSoftwarePagination,
        softwareSearchTerm,
        setSoftwareSearchTerm,
        packageInstallDialogOpen,
        setPackageInstallDialogOpen,
        packageSearchInputRef,
        searchResults,
        selectedPackages,
        isSearching,
        installationHistory,
        installationHistoryLoading,
        selectedInstallationLog,
        installationLogDialogOpen,
        installationDeleteConfirmOpen,
        installationToDelete,
        uninstallConfirmOpen,
        packageToUninstall,
        requestPackagesConfirmOpen,
        setRequestPackagesConfirmOpen,
        fetchInstallationHistory,
        performPackageSearch,
        handleRequestPackages,
        handleRequestPackagesConfirm,
        handlePackageSelect,
        handleInstallPackages,
        handleClosePackageDialog,
        handleUninstallPackage,
        handleUninstallConfirm,
        handleUninstallCancel,
        handleViewInstallationLog,
        handleCloseInstallationLogDialog,
        handleDeleteInstallation,
        handleConfirmDeleteInstallation,
        handleCancelDeleteInstallation,
    };
};
