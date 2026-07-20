// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

// OpenTelemetry + Graylog state, fetchers, handlers, and the Info-tab
// auto-refresh / eligibility effects for the Host Detail page.

import React, { useCallback, useEffect, useRef, useState } from 'react';
import type { TFunction } from 'i18next';
import { SysManageHost, SoftwarePackage, doGetHostSoftware } from '../../Services/hosts';
import {
    doCheckOpenTelemetryEligibility,
    doDeployOpenTelemetry,
    doGetOpenTelemetryStatus,
    doStartOpenTelemetry,
    doStopOpenTelemetry,
    doRestartOpenTelemetry,
    doConnectOpenTelemetryToGrafana,
    doDisconnectOpenTelemetryFromGrafana,
    doRemoveOpenTelemetry,
} from '../../Services/opentelemetry';
import { doCheckGraylogHealth, doGetGraylogAttachment } from '../../Services/graylog';
import { OpenTelemetryStatus } from './hostDetailTypes';
import type { SnackbarSeverity } from './useHostSnackbar';

interface UseHostObservabilityArgs {
    hostId: string | undefined;
    host: SysManageHost | null;
    currentTabId: string;
    t: TFunction;
    setSnackbarMessage: React.Dispatch<React.SetStateAction<string>>;
    setSnackbarSeverity: React.Dispatch<React.SetStateAction<SnackbarSeverity>>;
    setSnackbarOpen: React.Dispatch<React.SetStateAction<boolean>>;
    setSoftwarePackages: React.Dispatch<React.SetStateAction<SoftwarePackage[]>>;
}

export const useHostObservability = ({
    hostId,
    host,
    currentTabId,
    t,
    setSnackbarMessage,
    setSnackbarSeverity,
    setSnackbarOpen,
    setSoftwarePackages,
}: UseHostObservabilityArgs) => {
    const [openTelemetryStatus, setOpenTelemetryStatus] = useState<OpenTelemetryStatus>(null);
    const [openTelemetryLoading, setOpenTelemetryLoading] = useState<boolean>(false);
    const [graylogAttached, setGraylogAttached] = useState<boolean>(false);
    const [graylogLoading, setGraylogLoading] = useState<boolean>(false);
    const [graylogMechanism, setGraylogMechanism] = useState<string | null>(null);
    const [graylogTargetHostname, setGraylogTargetHostname] = useState<string | null>(null);
    const [graylogTargetIp, setGraylogTargetIp] = useState<string | null>(null);
    const [graylogPort, setGraylogPort] = useState<number | null>(null);
    const openTelemetryRefreshInterval = useRef<ReturnType<typeof setInterval> | null>(null);
    const graylogRefreshInterval = useRef<ReturnType<typeof setInterval> | null>(null);

    const [canDeployOpenTelemetry, setCanDeployOpenTelemetry] = useState<boolean>(false);  // User has permission to see button
    const [openTelemetryEligible, setOpenTelemetryEligible] = useState<boolean>(false);  // Deployment is actually allowed
    const [openTelemetryDeploying, setOpenTelemetryDeploying] = useState<boolean>(false);

    const [canAttachGraylog, setCanAttachGraylog] = useState<boolean>(false);  // Graylog integration enabled and healthy
    const [graylogEligible, setGraylogEligible] = useState<boolean>(false);  // Agent is privileged
    const [graylogAttachModalOpen, setGraylogAttachModalOpen] = useState<boolean>(false);

    const fetchOpenTelemetryStatus = useCallback(async () => {
        if (!hostId) return;
        try {
            setOpenTelemetryLoading(true);
            const status = await doGetOpenTelemetryStatus(hostId);
            setOpenTelemetryStatus(status);
        } catch (err) {
            console.error('Error fetching OpenTelemetry status:', err);
        } finally {
            setOpenTelemetryLoading(false);
        }
    }, [hostId]);

    const fetchGraylogAttachment = useCallback(async () => {
        if (!hostId) return;
        try {
            setGraylogLoading(true);
            const attachment = await doGetGraylogAttachment(hostId);
            setGraylogAttached(attachment.is_attached);
            setGraylogMechanism(attachment.mechanism);
            setGraylogTargetHostname(attachment.target_hostname);
            setGraylogTargetIp(attachment.target_ip);
            setGraylogPort(attachment.port);
        } catch (err) {
            console.error('Error fetching Graylog attachment:', err);
        } finally {
            setGraylogLoading(false);
        }
    }, [hostId]);

    // OpenTelemetry service control handlers
    const handleOpenTelemetryStart = async () => {
        if (!hostId) return;
        try {
            setOpenTelemetryLoading(true);
            await doStartOpenTelemetry(hostId);
            setSnackbarMessage(t('hostDetail.opentelemetryStartSuccess', 'OpenTelemetry service started successfully'));
            setSnackbarSeverity('success');
            setSnackbarOpen(true);
            // Refresh status after a delay
            setTimeout(() => fetchOpenTelemetryStatus(), 2000);
        } catch (error) {
            console.error('Error starting OpenTelemetry:', error);
            setSnackbarMessage(t('hostDetail.opentelemetryOperationFailed', 'OpenTelemetry operation failed'));
            setSnackbarSeverity('error');
            setSnackbarOpen(true);
        } finally {
            setOpenTelemetryLoading(false);
        }
    };

    const handleOpenTelemetryStop = async () => {
        if (!hostId) return;
        try {
            setOpenTelemetryLoading(true);
            await doStopOpenTelemetry(hostId);
            setSnackbarMessage(t('hostDetail.opentelemetryStopSuccess', 'OpenTelemetry service stopped successfully'));
            setSnackbarSeverity('success');
            setSnackbarOpen(true);
            // Refresh status after a delay
            setTimeout(() => fetchOpenTelemetryStatus(), 2000);
        } catch (error) {
            console.error('Error stopping OpenTelemetry:', error);
            setSnackbarMessage(t('hostDetail.opentelemetryOperationFailed', 'OpenTelemetry operation failed'));
            setSnackbarSeverity('error');
            setSnackbarOpen(true);
        } finally {
            setOpenTelemetryLoading(false);
        }
    };

    const handleOpenTelemetryRestart = async () => {
        if (!hostId) return;
        try {
            setOpenTelemetryLoading(true);
            await doRestartOpenTelemetry(hostId);
            setSnackbarMessage(t('hostDetail.opentelemetryRestartSuccess', 'OpenTelemetry service restarted successfully'));
            setSnackbarSeverity('success');
            setSnackbarOpen(true);
            // Refresh status after a delay
            setTimeout(() => fetchOpenTelemetryStatus(), 2000);
        } catch (error) {
            console.error('Error restarting OpenTelemetry:', error);
            setSnackbarMessage(t('hostDetail.opentelemetryOperationFailed', 'OpenTelemetry operation failed'));
            setSnackbarSeverity('error');
            setSnackbarOpen(true);
        } finally {
            setOpenTelemetryLoading(false);
        }
    };

    const handleOpenTelemetryConnect = async () => {
        if (!hostId) return;
        try {
            setOpenTelemetryLoading(true);
            await doConnectOpenTelemetryToGrafana(hostId);
            setSnackbarMessage(t('hostDetail.opentelemetryConnectSuccess', 'OpenTelemetry connected to Grafana successfully'));
            setSnackbarSeverity('success');
            setSnackbarOpen(true);
            // Refresh status after a delay
            setTimeout(() => fetchOpenTelemetryStatus(), 2000);
        } catch (error) {
            console.error('Error connecting OpenTelemetry to Grafana:', error);
            setSnackbarMessage(t('hostDetail.opentelemetryOperationFailed', 'OpenTelemetry operation failed'));
            setSnackbarSeverity('error');
            setSnackbarOpen(true);
        } finally {
            setOpenTelemetryLoading(false);
        }
    };

    const handleOpenTelemetryDisconnect = async () => {
        if (!hostId) return;
        try {
            setOpenTelemetryLoading(true);
            await doDisconnectOpenTelemetryFromGrafana(hostId);
            setSnackbarMessage(t('hostDetail.opentelemetryDisconnectSuccess', 'OpenTelemetry disconnected from Grafana successfully'));
            setSnackbarSeverity('success');
            setSnackbarOpen(true);
            // Refresh status after a delay
            setTimeout(() => fetchOpenTelemetryStatus(), 2000);
        } catch (error) {
            console.error('Error disconnecting OpenTelemetry from Grafana:', error);
            setSnackbarMessage(t('hostDetail.opentelemetryOperationFailed', 'OpenTelemetry operation failed'));
            setSnackbarSeverity('error');
            setSnackbarOpen(true);
        } finally {
            setOpenTelemetryLoading(false);
        }
    };

    const handleRemoveOpenTelemetry = async () => {
        if (!hostId) return;
        try {
            setOpenTelemetryLoading(true);
            await doRemoveOpenTelemetry(hostId);
            setSnackbarMessage(t('hostDetail.opentelemetryRemoveSuccess', 'OpenTelemetry removal queued successfully'));
            setSnackbarSeverity('success');
            setSnackbarOpen(true);
            // Refresh status after a delay
            setTimeout(() => fetchOpenTelemetryStatus(), 2000);
        } catch (error) {
            console.error('Error removing OpenTelemetry:', error);
            setSnackbarMessage(t('hostDetail.opentelemetryOperationFailed', 'OpenTelemetry operation failed'));
            setSnackbarSeverity('error');
            setSnackbarOpen(true);
        } finally {
            setOpenTelemetryLoading(false);
        }
    };

    const handleAttachToGraylog = () => {
        setGraylogAttachModalOpen(true);
    };

    const handleGraylogAttachModalClose = () => {
        setGraylogAttachModalOpen(false);
        // Refresh Graylog attachment status after modal closes
        fetchGraylogAttachment();
    };

    const handleDeployOpenTelemetry = async () => {
        if (!hostId) return;

        try {
            setOpenTelemetryDeploying(true);

            const result = await doDeployOpenTelemetry(hostId);

            // Show success message
            setSnackbarMessage(result.message || t('hostDetail.opentelemetryDeploySuccess', 'OpenTelemetry deployment queued successfully'));
            setSnackbarSeverity('success');
            setSnackbarOpen(true);

            // Refresh software data after a delay to show the deployment
            setTimeout(async () => {
                try {
                    const softwareData = await doGetHostSoftware(hostId);
                    setSoftwarePackages(softwareData.items);

                    // Re-check eligibility
                    const eligibility = await doCheckOpenTelemetryEligibility(hostId);
                    setCanDeployOpenTelemetry(eligibility.has_permission || false);
                    setOpenTelemetryEligible(eligibility.eligible || false);
                } catch (error) {
                    console.error('Error refreshing software data:', error);
                }
            }, 5000);
        } catch (error) {
            console.error('Error deploying OpenTelemetry:', error);
            setSnackbarMessage(String(error) || t('hostDetail.opentelemetryDeployFailed', 'Failed to deploy OpenTelemetry'));
            setSnackbarSeverity('error');
            setSnackbarOpen(true);
        } finally {
            setOpenTelemetryDeploying(false);
        }
    };

    // Fetch OpenTelemetry status when Info tab is active
    useEffect(() => {
        if (currentTabId === 'info' && host?.active) {
            fetchOpenTelemetryStatus();
        }
    }, [currentTabId, host?.active, host, fetchOpenTelemetryStatus]);

    // Auto-refresh OpenTelemetry status every 30 seconds when on Info tab
    useEffect(() => {
        if (currentTabId === 'info' && host?.active) {
            // Start auto-refresh every 30 seconds
            const interval = setInterval(() => {
                fetchOpenTelemetryStatus();
            }, 30000);
            openTelemetryRefreshInterval.current = interval;

            return () => {
                if (interval) {
                    clearInterval(interval);
                }
            };
        } else if (openTelemetryRefreshInterval.current) {
            // Clear interval when tab is not active or host is not active
            clearInterval(openTelemetryRefreshInterval.current);
            openTelemetryRefreshInterval.current = null;
        }
    }, [currentTabId, host?.active, host?.id, fetchOpenTelemetryStatus, host]);

    // Fetch Graylog attachment status when Info tab is active
    useEffect(() => {
        if (currentTabId === 'info' && host?.active) {
            fetchGraylogAttachment();
        }
    }, [currentTabId, host?.active, host, fetchGraylogAttachment]);

    // Auto-refresh Graylog status every 30 seconds when on Info tab
    useEffect(() => {
        if (currentTabId === 'info' && host?.active) {
            // Start auto-refresh every 30 seconds
            const interval = setInterval(() => {
                fetchGraylogAttachment();
            }, 30000);
            graylogRefreshInterval.current = interval;

            return () => {
                if (interval) {
                    clearInterval(interval);
                }
            };
        } else if (graylogRefreshInterval.current) {
            // Clear interval when tab is not active or host is not active
            clearInterval(graylogRefreshInterval.current);
            graylogRefreshInterval.current = null;
        }
    }, [currentTabId, host?.active, host?.id, fetchGraylogAttachment, host]);

    // Cleanup intervals on unmount
    useEffect(() => {
        return () => {
            if (openTelemetryRefreshInterval.current) {
                clearInterval(openTelemetryRefreshInterval.current);
            }
            if (graylogRefreshInterval.current) {
                clearInterval(graylogRefreshInterval.current);
            }
        };
    }, []);

    // Check OpenTelemetry eligibility when host is loaded
    useEffect(() => {
        const checkOpenTelemetryEligibility = async () => {
            if (!hostId || !host) return;

            // Don't check eligibility if host is not active (down)
            if (!host.active) {
                setCanDeployOpenTelemetry(false);
                setOpenTelemetryEligible(false);
                return;
            }

            try {
                const eligibility = await doCheckOpenTelemetryEligibility(hostId);
                setCanDeployOpenTelemetry(eligibility.has_permission || false);  // Show button if user has RBAC permission
                setOpenTelemetryEligible(eligibility.eligible || false);  // Enable button only if eligible to deploy
            } catch (error) {
                console.log('Failed to check OpenTelemetry eligibility:', error);
                setCanDeployOpenTelemetry(false);
                setOpenTelemetryEligible(false);
            }
        };

        checkOpenTelemetryEligibility();
    }, [hostId, host]);

    // Check Graylog eligibility when host is loaded
    useEffect(() => {
        const checkGraylogEligibility = async () => {
            if (!hostId || !host) return;

            // Don't check eligibility if host is not active (down)
            if (!host.active) {
                setCanAttachGraylog(false);
                setGraylogEligible(false);
                return;
            }

            try {
                // Check if Graylog integration is enabled and healthy
                const graylogHealth = await doCheckGraylogHealth();
                setCanAttachGraylog(graylogHealth.healthy);

                // Check if agent is running in privileged mode
                setGraylogEligible(host.is_agent_privileged || false);
            } catch {
                // Graylog not configured or unavailable — not an error condition
                setCanAttachGraylog(false);
                setGraylogEligible(false);
            }
        };

        checkGraylogEligibility();
    }, [hostId, host]);

    return {
        openTelemetryStatus,
        openTelemetryLoading,
        openTelemetryDeploying,
        canDeployOpenTelemetry,
        openTelemetryEligible,
        graylogAttached,
        graylogLoading,
        graylogMechanism,
        graylogTargetHostname,
        graylogTargetIp,
        graylogPort,
        canAttachGraylog,
        graylogEligible,
        graylogAttachModalOpen,
        fetchOpenTelemetryStatus,
        fetchGraylogAttachment,
        handleOpenTelemetryStart,
        handleOpenTelemetryStop,
        handleOpenTelemetryRestart,
        handleOpenTelemetryConnect,
        handleOpenTelemetryDisconnect,
        handleRemoveOpenTelemetry,
        handleAttachToGraylog,
        handleGraylogAttachModalClose,
        handleDeployOpenTelemetry,
    };
};
