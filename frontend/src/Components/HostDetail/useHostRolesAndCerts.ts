// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

// Certificate + server-role inventory, collection requests, service control and
// the server-roles auto-refresh effect for the Host Detail page.

import React, { useCallback, useEffect, useRef, useState } from 'react';
import type { TFunction } from 'i18next';
import axiosInstance from '../../Services/api';
import { SysManageHost } from '../../Services/hosts';
import { Certificate, HostRole } from './hostDetailTypes';
import type { SnackbarSeverity } from './useHostSnackbar';

interface UseHostRolesAndCertsArgs {
    hostId: string | undefined;
    host: SysManageHost | null;
    currentTabId: string;
    t: TFunction;
    setSnackbarMessage: React.Dispatch<React.SetStateAction<string>>;
    setSnackbarSeverity: React.Dispatch<React.SetStateAction<SnackbarSeverity>>;
    setSnackbarOpen: React.Dispatch<React.SetStateAction<boolean>>;
}

export const useHostRolesAndCerts = ({
    hostId,
    host,
    currentTabId,
    t,
    setSnackbarMessage,
    setSnackbarSeverity,
    setSnackbarOpen,
}: UseHostRolesAndCertsArgs) => {
    const [certificates, setCertificates] = useState<Certificate[]>([]);
    const [certificatesLoading, setCertificatesLoading] = useState<boolean>(false);
    const [roles, setRoles] = useState<HostRole[]>([]);
    const [rolesLoading, setRolesLoading] = useState<boolean>(false);
    const [selectedRoles, setSelectedRoles] = useState<string[]>([]);
    const [serviceControlLoading, setServiceControlLoading] = useState<boolean>(false);
    const rolesRefreshInterval = useRef<ReturnType<typeof setInterval> | null>(null);
    // Certificate-related functions
    const fetchCertificates = useCallback(async () => {
        if (!hostId) return;

        try {
            setCertificatesLoading(true);
            const response = await axiosInstance.get(`/api/v1/host/${hostId}/certificates`);

            if (response.status === 200) {
                setCertificates(response.data.certificates || []);
            }
        } catch (error) {
            console.error('Error fetching certificates:', error);
            // Don't fail the whole page load for certificate errors
            setCertificates([]);
        } finally {
            setCertificatesLoading(false);
        }
    }, [hostId]);

    const requestCertificatesCollection = useCallback(async () => {
        if (!hostId) return;

        try {
            setCertificatesLoading(true);
            const response = await axiosInstance.post(`/api/v1/host/${hostId}/request-certificates-collection`);

            if (response.status === 200) {
                setSnackbarMessage(t('hostDetail.certificateCollectionRequested', 'Certificate collection requested'));
                setSnackbarSeverity('success');
                setSnackbarOpen(true);

                // Refetch certificates after a short delay to allow collection to complete
                setTimeout(() => {
                    fetchCertificates();
                }, 3000);
            }
        } catch (error) {
            console.error('Error requesting certificate collection:', error);
            setSnackbarMessage(t('hostDetail.certificateCollectionError', 'Error requesting certificate collection'));
            setSnackbarSeverity('error');
            setSnackbarOpen(true);
        } finally {
            setCertificatesLoading(false);
        }
    }, [hostId, fetchCertificates, t, setSnackbarMessage, setSnackbarSeverity, setSnackbarOpen]);

    // Role-related functions
    const fetchRoles = useCallback(async (showLoading: boolean = true) => {
        if (!hostId) return;
        try {
            if (showLoading) {
                setRolesLoading(true);
            }
            const response = await axiosInstance.get(`/api/v1/host/${hostId}/roles`);
            if (response.status === 200) {
                setRoles(response.data.roles || []);
            }
        } catch (error) {
            console.error('Error fetching roles:', error);
            // Don't fail the whole page load for role errors
            setRoles([]);
        } finally {
            if (showLoading) {
                setRolesLoading(false);
            }
        }
    }, [hostId]);

    const requestRolesCollection = useCallback(async () => {
        if (!hostId) return;
        try {
            setRolesLoading(true);
            const response = await axiosInstance.post(`/api/v1/host/${hostId}/request-roles-collection`);
            if (response.status === 200) {
                setSnackbarMessage(t('hostDetail.roleCollectionRequested', 'Role collection requested'));
                setSnackbarSeverity('success');
                setSnackbarOpen(true);
                // Refetch roles after a short delay to allow collection to complete
                setTimeout(() => {
                    fetchRoles();
                }, 3000);
            }
        } catch (error) {
            console.error('Error requesting role collection:', error);
            setSnackbarMessage(t('hostDetail.roleCollectionError', 'Error requesting role collection'));
            setSnackbarSeverity('error');
            setSnackbarOpen(true);
        } finally {
            setRolesLoading(false);
        }
    }, [hostId, fetchRoles, t, setSnackbarMessage, setSnackbarSeverity, setSnackbarOpen]);

    // Service control handlers
    const addRoleToSelection = (roleId: string) => {
        setSelectedRoles(prev => [...prev, roleId]);
    };

    const removeRoleFromSelection = (roleId: string) => {
        setSelectedRoles(prev => prev.filter(id => id !== roleId));
    };

    const selectAllRoles = () => {
        const selectableRoles = roles.filter(role => role.service_name && role.service_name.trim() !== '').map(role => role.id);
        setSelectedRoles(selectableRoles);
    };

    const deselectAllRoles = () => {
        setSelectedRoles([]);
    };

    const handleServiceControl = async (action: 'start' | 'stop' | 'restart') => {
        if (!hostId || selectedRoles.length === 0) return;

        try {
            setServiceControlLoading(true);
            const selectedRoleData = roles.filter(role => selectedRoles.includes(role.id));
            const serviceNames = selectedRoleData.map(role => role.service_name).filter(Boolean);

            if (serviceNames.length === 0) {
                setSnackbarMessage(t('hostDetail.noServicesSelected', 'No services selected for control'));
                setSnackbarSeverity('warning');
                setSnackbarOpen(true);
                return;
            }

            const response = await axiosInstance.post(`/api/v1/host/${hostId}/service-control`, {
                action,
                services: serviceNames
            });

            if (response.status === 200) {
                setSnackbarMessage(t(`hostDetail.service${action.charAt(0).toUpperCase() + action.slice(1)}Success`, `Service ${action} requested successfully`));
                setSnackbarSeverity('success');
                setSnackbarOpen(true);
                setSelectedRoles([]);

                // Refresh roles after a delay to get updated status
                setTimeout(() => {
                    fetchRoles();
                }, 3000);
            }
        } catch (error) {
            // nosemgrep: javascript.lang.security.audit.unsafe-formatstring.unsafe-formatstring
            console.error(`Error ${action}ing services:`, error);
            // nosemgrep: javascript.lang.security.audit.unsafe-formatstring.unsafe-formatstring
            setSnackbarMessage(t(`hostDetail.service${action.charAt(0).toUpperCase() + action.slice(1)}Error`, `Error ${action}ing services`));
            setSnackbarSeverity('error');
            setSnackbarOpen(true);
        } finally {
            setServiceControlLoading(false);
        }
    };
    // Auto-refresh functionality
    useEffect(() => {
        if (currentTabId === 'server-roles' && host?.active) {
            // Start auto-refresh every 30 seconds (without loading indicator)
            const interval = setInterval(() => {
                fetchRoles(false);
            }, 30000);
            rolesRefreshInterval.current = interval;

            return () => {
                if (interval) {
                    clearInterval(interval);
                }
            };
        } else if (rolesRefreshInterval.current) {
            // Clear interval when tab is not active or host is not active
            clearInterval(rolesRefreshInterval.current);
            rolesRefreshInterval.current = null;
        }
    }, [currentTabId, host?.active, host?.id, fetchRoles, host]);

    // Cleanup interval on unmount
    useEffect(() => {
        return () => {
            if (rolesRefreshInterval.current) {
                clearInterval(rolesRefreshInterval.current);
            }
        };
    }, []);
    return {
        certificates,
        certificatesLoading,
        roles,
        rolesLoading,
        selectedRoles,
        serviceControlLoading,
        fetchCertificates,
        requestCertificatesCollection,
        fetchRoles,
        requestRolesCollection,
        addRoleToSelection,
        removeRoleFromSelection,
        selectAllRoles,
        deselectAllRoles,
        handleServiceControl,
    };
};
