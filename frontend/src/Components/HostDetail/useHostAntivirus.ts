// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

// Antivirus deploy/enable/disable/remove actions for the Host Detail page.

import React, { useState } from 'react';
import type { TFunction } from 'i18next';
import axiosInstance from '../../Services/api';
import { SysManageHost } from '../../Services/hosts';
import type { SnackbarSeverity } from './useHostSnackbar';

interface UseHostAntivirusArgs {
    host: SysManageHost | null;
    t: TFunction;
    setSnackbarMessage: React.Dispatch<React.SetStateAction<string>>;
    setSnackbarSeverity: React.Dispatch<React.SetStateAction<SnackbarSeverity>>;
    setSnackbarOpen: React.Dispatch<React.SetStateAction<boolean>>;
}

export const useHostAntivirus = ({
    host,
    t,
    setSnackbarMessage,
    setSnackbarSeverity,
    setSnackbarOpen,
}: UseHostAntivirusArgs) => {
    const [antivirusRefreshTrigger, setAntivirusRefreshTrigger] = useState<number>(0);

    const handleDeployAntivirus = async () => {
        if (!host?.id) return;

        try {
            // Call backend API to deploy antivirus to this specific host
            const response = await axiosInstance.post('/api/v1/deploy', {
                host_ids: [host.id]
            });

            if (response.data.failed_hosts?.length > 0) {
                const failedHost = response.data.failed_hosts[0];
                setSnackbarMessage(t('hostDetail.antivirusDeployFailed', 'Failed to deploy antivirus: {reason}', { reason: failedHost.reason }));
                setSnackbarSeverity('error');
            } else {
                setSnackbarMessage(t('hostDetail.antivirusDeploySuccess', 'Antivirus deployment initiated successfully'));
                setSnackbarSeverity('success');
                // Trigger refresh after a short delay to allow agent to update
                setTimeout(() => setAntivirusRefreshTrigger(prev => prev + 1), 10000);
            }
            setSnackbarOpen(true);
        } catch (error) {
            console.error('Failed to deploy antivirus:', error);
            setSnackbarMessage(t('hostDetail.antivirusDeployFailed', 'Failed to deploy antivirus'));
            setSnackbarSeverity('error');
            setSnackbarOpen(true);
        }
    };

    const handleEnableAntivirus = async () => {
        if (!host?.id) return;

        try {
            await axiosInstance.post(`/api/v1/hosts/${host.id}/antivirus/enable`);
            setSnackbarMessage(t('security.antivirusEnableSuccess', 'Antivirus enable initiated successfully'));
            setSnackbarSeverity('success');
            setSnackbarOpen(true);
            // Trigger refresh after a short delay
            setTimeout(() => setAntivirusRefreshTrigger(prev => prev + 1), 10000);
        } catch (error) {
            console.error('Failed to enable antivirus:', error);
            setSnackbarMessage(t('security.antivirusEnableFailed', 'Failed to enable antivirus'));
            setSnackbarSeverity('error');
            setSnackbarOpen(true);
        }
    };

    const handleDisableAntivirus = async () => {
        if (!host?.id) return;

        try {
            await axiosInstance.post(`/api/v1/hosts/${host.id}/antivirus/disable`);
            setSnackbarMessage(t('security.antivirusDisableSuccess', 'Antivirus disable initiated successfully'));
            setSnackbarSeverity('success');
            setSnackbarOpen(true);
            // Trigger refresh after a short delay
            setTimeout(() => setAntivirusRefreshTrigger(prev => prev + 1), 10000);
        } catch (error) {
            console.error('Failed to disable antivirus:', error);
            setSnackbarMessage(t('security.antivirusDisableFailed', 'Failed to disable antivirus'));
            setSnackbarSeverity('error');
            setSnackbarOpen(true);
        }
    };

    const handleRemoveAntivirus = async () => {
        if (!host?.id) return;

        try {
            await axiosInstance.post(`/api/v1/hosts/${host.id}/antivirus/remove`);
            setSnackbarMessage(t('security.antivirusRemoveSuccess', 'Antivirus removal initiated successfully'));
            setSnackbarSeverity('success');
            setSnackbarOpen(true);
            // Trigger refresh after a short delay
            setTimeout(() => setAntivirusRefreshTrigger(prev => prev + 1), 10000);
        } catch (error) {
            console.error('Failed to remove antivirus:', error);
            setSnackbarMessage(t('security.antivirusRemoveFailed', 'Failed to remove antivirus'));
            setSnackbarSeverity('error');
            setSnackbarOpen(true);
        }
    };

    return {
        antivirusRefreshTrigger,
        handleDeployAntivirus,
        handleEnableAntivirus,
        handleDisableAntivirus,
        handleRemoveAntivirus,
    };
};
