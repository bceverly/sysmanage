// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

// Ubuntu Pro attach/detach/service-management state and handlers for the Host
// Detail page, including the 30s auto-refresh of the Ubuntu Pro info.

import React, { useEffect, useState } from 'react';
import type { TFunction } from 'i18next';
import axiosInstance from '../../Services/api';
import {
    SysManageHost,
    UbuntuProInfo,
    doGetHostUbuntuPro,
    doAttachUbuntuPro,
    doDetachUbuntuPro,
    doEnableUbuntuProService,
    doDisableUbuntuProService,
} from '../../Services/hosts';
import type { SnackbarSeverity } from './useHostSnackbar';

interface UseHostUbuntuProArgs {
    hostId: string | undefined;
    host: SysManageHost | null;
    ubuntuProInfo: UbuntuProInfo | null;
    setUbuntuProInfo: React.Dispatch<React.SetStateAction<UbuntuProInfo | null>>;
    isUbuntu: () => boolean;
    t: TFunction;
    setSnackbarMessage: React.Dispatch<React.SetStateAction<string>>;
    setSnackbarSeverity: React.Dispatch<React.SetStateAction<SnackbarSeverity>>;
    setSnackbarOpen: React.Dispatch<React.SetStateAction<boolean>>;
}

export const useHostUbuntuPro = ({
    hostId,
    host,
    ubuntuProInfo,
    setUbuntuProInfo,
    isUbuntu,
    t,
    setSnackbarMessage,
    setSnackbarSeverity,
    setSnackbarOpen,
}: UseHostUbuntuProArgs) => {
    // Ubuntu Pro state
    const [ubuntuProTokenDialog, setUbuntuProTokenDialog] = useState<boolean>(false);
    const [ubuntuProToken, setUbuntuProToken] = useState<string>('');
    const [ubuntuProAttaching, setUbuntuProAttaching] = useState<boolean>(false);
    const [ubuntuProDetaching, setUbuntuProDetaching] = useState<boolean>(false);
    const [ubuntuProDetachConfirmOpen, setUbuntuProDetachConfirmOpen] = useState<boolean>(false);

    // Ubuntu Pro service editing state
    const [servicesEditMode, setServicesEditMode] = useState<boolean>(false);
    const [editedServices, setEditedServices] = useState<{[serviceName: string]: boolean}>({});
    const [servicesSaving, setServicesSaving] = useState<boolean>(false);
    const [servicesMessage, setServicesMessage] = useState<string>('');

    // Auto-refresh Ubuntu Pro information every 30 seconds
    useEffect(() => {
        let interval: ReturnType<typeof globalThis.setInterval> | null = null;

        if (hostId && isUbuntu() && ubuntuProInfo?.available) {
            interval = globalThis.setInterval(async () => {
                try {
                    const ubuntuProData = await doGetHostUbuntuPro(hostId);
                    setUbuntuProInfo(ubuntuProData);
                    // Clear service messages on refresh (as requested by user)
                    if (servicesMessage) {
                        setServicesMessage('');
                    }
                } catch {
                    // Silently ignore errors during auto-refresh
                }
            }, 30000); // 30 seconds
        }

        return () => {
            if (interval) {
                globalThis.clearInterval(interval);
            }
        };
    }, [hostId, isUbuntu, ubuntuProInfo?.available, servicesMessage, setUbuntuProInfo]);

    const handleUbuntuProAttach = async () => {
        // Try to load master Ubuntu Pro token
        try {
            const response = await axiosInstance.get('/api/v1/ubuntu-pro/');
            const masterKey = response.data.master_key;
            if (masterKey?.trim()) {
                // Master key exists - attach directly without showing the token

                setUbuntuProAttaching(true);
                try {
                    await doAttachUbuntuPro(hostId!, masterKey.trim());
                    setSnackbarMessage(t('hostDetail.ubuntuProAttachSuccess', 'Ubuntu Pro attach requested'));
                    setSnackbarSeverity('success');
                    setSnackbarOpen(true);
                    // Start polling - attaching state stays active until attached
                    startUbuntuProPolling();
                } catch {
                    setSnackbarMessage(t('hostDetail.ubuntuProAttachError', 'Failed to attach Ubuntu Pro'));
                    setSnackbarSeverity('error');
                    setSnackbarOpen(true);
                    setUbuntuProAttaching(false);
                }
                return;
            }
        } catch (error) {
            console.log('No master Ubuntu Pro token configured or error loading:', error);
        }

        // No master key - show dialog for manual token entry
        setUbuntuProTokenDialog(true);
    };

    const handleUbuntuProDetach = () => {
        setUbuntuProDetachConfirmOpen(true);
    };

    const handleConfirmUbuntuProDetach = async () => {
        if (!hostId || !host) return;

        setUbuntuProDetachConfirmOpen(false);
        setUbuntuProDetaching(true);
        try {
            await doDetachUbuntuPro(hostId);
            setSnackbarMessage(t('hostDetail.ubuntuProDetachSuccess', 'Ubuntu Pro detach requested'));
            setSnackbarSeverity('success');
            setSnackbarOpen(true);
            // Poll until detached
            let pollCount = 0;
            const maxPolls = 30;
            const pollInterval = setInterval(async () => {
                pollCount++;
                try {
                    const ubuntuProData = await doGetHostUbuntuPro(hostId);
                    setUbuntuProInfo(ubuntuProData);
                    if (!ubuntuProData.attached || pollCount >= maxPolls) {
                        clearInterval(pollInterval);
                        setUbuntuProDetaching(false);
                    }
                } catch {
                    if (pollCount >= maxPolls) {
                        clearInterval(pollInterval);
                        setUbuntuProDetaching(false);
                    }
                }
            }, 2000);
        } catch {
            setSnackbarMessage(t('hostDetail.ubuntuProDetachError', 'Failed to detach Ubuntu Pro'));
            setSnackbarSeverity('error');
            setSnackbarOpen(true);
            setUbuntuProDetaching(false);
        }
    };

    const handleCancelUbuntuProDetach = () => {
        setUbuntuProDetachConfirmOpen(false);
    };

    const startUbuntuProPolling = () => {
        if (!hostId) return;
        let pollCount = 0;
        const maxPolls = 30; // Poll for up to ~60 seconds
        const pollInterval = setInterval(async () => {
            pollCount++;
            try {
                const ubuntuProData = await doGetHostUbuntuPro(hostId);
                setUbuntuProInfo(ubuntuProData);
                if (ubuntuProData.attached || pollCount >= maxPolls) {
                    clearInterval(pollInterval);
                    setUbuntuProAttaching(false);
                }
            } catch {
                if (pollCount >= maxPolls) {
                    clearInterval(pollInterval);
                    setUbuntuProAttaching(false);
                }
            }
        }, 2000);
    };

    const handleUbuntuProTokenSubmit = async () => {
        if (!hostId || !host || !ubuntuProToken.trim()) return;

        setUbuntuProAttaching(true);
        setUbuntuProTokenDialog(false);

        try {
            await doAttachUbuntuPro(hostId, ubuntuProToken.trim());
            setSnackbarMessage(t('hostDetail.ubuntuProAttachSuccess', 'Ubuntu Pro attach requested'));
            setSnackbarSeverity('success');
            setSnackbarOpen(true);
            setUbuntuProToken('');
            // Start polling - attaching state stays active until attached
            startUbuntuProPolling();
        } catch {
            setSnackbarMessage(t('hostDetail.ubuntuProAttachError', 'Failed to attach Ubuntu Pro'));
            setSnackbarSeverity('error');
            setSnackbarOpen(true);
            setUbuntuProAttaching(false);
            setUbuntuProToken('');
        }
    };

    const handleUbuntuProTokenCancel = () => {
        setUbuntuProTokenDialog(false);
        setUbuntuProToken('');
    };

    const getEditedServiceLabel = (serviceName: string, serviceStatus: string): string => {
        const isEnabled = editedServices[serviceName] ?? (serviceStatus === 'enabled');
        return isEnabled ? t('hostDetail.enabled', 'Enabled') : t('hostDetail.disabled', 'Disabled');
    };

    // Ubuntu Pro service management handlers
    const handleServicesEditToggle = () => {
        if (servicesEditMode) {
            // Cancel editing - reset changes
            setEditedServices({});
            setServicesMessage('');
        } else {
            // Start editing - initialize with current service states
            const currentStates: {[serviceName: string]: boolean} = {};
            ubuntuProInfo?.services.forEach(service => {
                if (service.status !== 'n/a') {
                    currentStates[service.name] = service.status === 'enabled';
                }
            });
            setEditedServices(currentStates);
        }
        setServicesEditMode(!servicesEditMode);
    };

    const handleServiceToggle = (serviceName: string, enabled: boolean) => {
        setEditedServices(prev => ({
            ...prev,
            [serviceName]: enabled
        }));
    };

    const handleServicesSave = async () => {
        if (!hostId || !host || !ubuntuProInfo) return;

        setServicesSaving(true);
        setServicesMessage('');

        try {
            const servicesToChange: Array<{service: string, enable: boolean}> = [];

            // Compare current states with edited states
            ubuntuProInfo.services.forEach(service => {
                if (service.status !== 'n/a') {
                    const currentEnabled = service.status === 'enabled';
                    const newEnabled = editedServices[service.name];

                    if (newEnabled !== undefined && currentEnabled !== newEnabled) {
                        servicesToChange.push({
                            service: service.name,
                            enable: newEnabled
                        });
                    }
                }
            });

            // Apply changes
            for (const change of servicesToChange) {
                if (change.enable) {
                    await doEnableUbuntuProService(hostId, change.service);
                } else {
                    await doDisableUbuntuProService(hostId, change.service);
                }
            }

            if (servicesToChange.length > 0) {
                setServicesMessage(t('hostDetail.servicesUpdatedCount', '{{count}} service(s) updated', { count: servicesToChange.length }));
                setSnackbarMessage(t('hostDetail.servicesUpdateRequested', 'Ubuntu Pro services update requested'));
                setSnackbarSeverity('success');
                setSnackbarOpen(true);
            } else {
                setServicesMessage(t('hostDetail.noChangesMade', 'No changes made'));
            }

            setServicesEditMode(false);
            setEditedServices({});

        } catch (error) {
            console.error('Error updating Ubuntu Pro services:', error);
            setServicesMessage(t('hostDetail.errorUpdatingServices', 'Error updating services'));
            setSnackbarMessage(t('hostDetail.servicesUpdateError', 'Error updating Ubuntu Pro services'));
            setSnackbarSeverity('error');
            setSnackbarOpen(true);
        } finally {
            setServicesSaving(false);
        }
    };

    return {
        ubuntuProTokenDialog,
        ubuntuProToken,
        setUbuntuProToken,
        ubuntuProAttaching,
        ubuntuProDetaching,
        ubuntuProDetachConfirmOpen,
        servicesEditMode,
        editedServices,
        servicesSaving,
        servicesMessage,
        handleUbuntuProAttach,
        handleUbuntuProDetach,
        handleConfirmUbuntuProDetach,
        handleCancelUbuntuProDetach,
        handleUbuntuProTokenSubmit,
        handleUbuntuProTokenCancel,
        getEditedServiceLabel,
        handleServicesEditToggle,
        handleServiceToggle,
        handleServicesSave,
    };
};
