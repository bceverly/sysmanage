// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

// Initial data-loading effects for the Host Detail page: Pro+ license modules,
// the main host/storage/network/user/diagnostics fetch, and the 60s user/group
// auto-refresh.  State stays in the parent; this hook only owns the effects.

import React, { useEffect } from 'react';
import type { TFunction } from 'i18next';
import type { NavigateFunction } from 'react-router-dom';
import axiosInstance from '../../Services/api';
import {
    SysManageHost,
    StorageDevice as StorageDeviceType,
    NetworkInterface as NetworkInterfaceType,
    UserAccount,
    UserGroup,
    DiagnosticReport,
    UbuntuProInfo,
    doGetHostByID,
    doGetHostStorage,
    doGetHostNetwork,
    doGetHostUsers,
    doGetHostGroups,
    doGetHostDiagnostics,
    doGetHostUbuntuPro,
} from '../../Services/hosts';
import { SysManageUser, doGetMe } from '../../Services/users';
import { getLicenseInfo } from '../../Services/license';
import {
    resolveAntivirusOsName,
    isUbuntuHost,
    supportsChildHosts,
    resolveWithLegacyFallback,
    runOptionalFetch,
} from './hostDetailHelpers';

interface UseHostDataArgs {
    hostId: string | undefined;
    navigate: NavigateFunction;
    t: TFunction;
    setHost: React.Dispatch<React.SetStateAction<SysManageHost | null>>;
    setStorageDevices: React.Dispatch<React.SetStateAction<StorageDeviceType[]>>;
    setNetworkInterfaces: React.Dispatch<React.SetStateAction<NetworkInterfaceType[]>>;
    setUserAccounts: React.Dispatch<React.SetStateAction<UserAccount[]>>;
    setUserGroups: React.Dispatch<React.SetStateAction<UserGroup[]>>;
    setDiagnosticsData: React.Dispatch<React.SetStateAction<DiagnosticReport[]>>;
    setCurrentUser: React.Dispatch<React.SetStateAction<SysManageUser | null>>;
    setUbuntuProInfo: React.Dispatch<React.SetStateAction<UbuntuProInfo | null>>;
    setHasAntivirusOsDefault: React.Dispatch<React.SetStateAction<boolean>>;
    setLoading: React.Dispatch<React.SetStateAction<boolean>>;
    setError: React.Dispatch<React.SetStateAction<string | null>>;
    setLicenseModules: React.Dispatch<React.SetStateAction<string[]>>;
    setLicenseFeatures: React.Dispatch<React.SetStateAction<string[]>>;
    fetchCertificates: () => Promise<void>;
    fetchRoles: (showLoading?: boolean) => Promise<void>;
    fetchChildHosts: (showLoading?: boolean) => Promise<void>;
    fetchVirtualizationStatus: () => Promise<void>;
}

export const useHostData = ({
    hostId,
    navigate,
    t,
    setHost,
    setStorageDevices,
    setNetworkInterfaces,
    setUserAccounts,
    setUserGroups,
    setDiagnosticsData,
    setCurrentUser,
    setUbuntuProInfo,
    setHasAntivirusOsDefault,
    setLoading,
    setError,
    setLicenseModules,
    setLicenseFeatures,
    fetchCertificates,
    fetchRoles,
    fetchChildHosts,
    fetchVirtualizationStatus,
}: UseHostDataArgs) => {
    // Check Pro+ license modules for plugin tab filtering
    useEffect(() => {
        const checkLicenseModules = async () => {
            try {
                const licenseInfo = await getLicenseInfo();
                setLicenseModules(licenseInfo.modules || []);
                setLicenseFeatures(licenseInfo.features || []);
            } catch {
                // License check unavailable — proceed without Pro+ features
                setLicenseModules([]);
                setLicenseFeatures([]);
            }
        };
        checkLicenseModules();
    }, [setLicenseModules, setLicenseFeatures]);
    // Main initialization effect that loads host data, storage, network, users, certificates, and optional subsystems with proper error handling
    useEffect(() => { // NOSONAR
        if (!localStorage.getItem('bearer_token')) {
            navigate("/login");
            return;
        }

        if (!hostId) {
            setError(t('hostDetail.invalidId', 'Invalid host ID'));
            setLoading(false);
            return;
        }

        const fetchHost = async () => { // NOSONAR
            try {
                setLoading(true);
                const hostData = await doGetHostByID(hostId);
                setHost(hostData);

                // Check if there's an antivirus default for this host's OS
                try {
                    const osName = resolveAntivirusOsName(
                        hostData.platform ?? '',
                        hostData.platform_release ?? '',
                    );
                    if (osName) {
                        const response = await axiosInstance.get(`/api/v1/antivirus-defaults/${osName}`);
                        setHasAntivirusOsDefault(response.data?.antivirus_package !== null);
                    } else {
                        setHasAntivirusOsDefault(false);
                    }
                } catch {
                    // If 404 or any error, assume no default is configured
                    setHasAntivirusOsDefault(false);
                }

                // Fetch normalized storage, network, user access, and diagnostics data
                // Note: Software packages are loaded lazily when the Software tab is opened (not here)
                try {
                    const [storageData, networkData, usersData, groupsData, diagnosticsData, currentUserData] = await Promise.all([
                        doGetHostStorage(hostId),
                        doGetHostNetwork(hostId),
                        doGetHostUsers(hostId),
                        doGetHostGroups(hostId),
                        doGetHostDiagnostics(hostId),
                        doGetMe()
                    ]);

                    // If normalized data is empty, fall back to parsing legacy JSON
                    setStorageDevices(resolveWithLegacyFallback(storageData, hostData.storage_details, 'storage'));
                    setNetworkInterfaces(resolveWithLegacyFallback(networkData, hostData.network_details, 'network'));

                    // Set user access data
                    setUserAccounts(usersData);
                    setUserGroups(groupsData);

                    // Software data will be loaded lazily when Software tab is opened

                    // Set diagnostics data
                    setDiagnosticsData(diagnosticsData);

                    // Set current user data
                    setCurrentUser(currentUserData);

                    // Fetch Ubuntu Pro data (only for Ubuntu hosts)
                    if (isUbuntuHost(hostData.platform, hostData.platform_release)) {
                        await runOptionalFetch('Ubuntu Pro data', async () => {
                            const ubuntuProData = await doGetHostUbuntuPro(hostId);
                            setUbuntuProInfo(ubuntuProData);
                        });
                    }

                    // Fetch certificates data
                    await runOptionalFetch('Certificates data', fetchCertificates);
                    // Fetch roles data
                    await runOptionalFetch('Roles data', () => fetchRoles());
                    // Fetch child hosts data and virtualization status if supported
                    // Windows hosts support WSL, Linux hosts support LXD (Ubuntu 22.04+)
                    if (supportsChildHosts(hostData.platform)) {
                        await runOptionalFetch('Child hosts data', async () => {
                            await fetchChildHosts();
                            await fetchVirtualizationStatus();
                        });
                    }
                } catch (_error) {
                    // Log but don't fail the whole request - hardware/software/diagnostics data is optional
                    console.warn('Failed to fetch hardware/software/diagnostics data:', _error);
                }
                
                setError(null);
            } catch (err) {
                console.error('Error fetching host:', err);
                setError(t('hostDetail.loadError', 'Failed to load host details'));
            } finally {
                setLoading(false);
            }
        };

        fetchHost();
    }, [hostId, navigate, t, fetchCertificates, fetchRoles, fetchChildHosts, fetchVirtualizationStatus, setDiagnosticsData, setHost, setStorageDevices, setNetworkInterfaces, setUserAccounts, setUserGroups, setCurrentUser, setUbuntuProInfo, setHasAntivirusOsDefault, setLoading, setError]);
    // Auto-refresh user accounts and groups every 60 seconds
    useEffect(() => {
        let interval: ReturnType<typeof globalThis.setInterval> | null = null;

        if (hostId) {
            interval = globalThis.setInterval(async () => {
                try {
                    const [usersData, groupsData] = await Promise.all([
                        doGetHostUsers(hostId),
                        doGetHostGroups(hostId),
                    ]);
                    setUserAccounts(usersData);
                    setUserGroups(groupsData);
                } catch {
                    // Silently ignore errors during auto-refresh
                }
            }, 60000); // 60 seconds
        }

        return () => {
            if (interval) {
                globalThis.clearInterval(interval);
            }
        };
    }, [hostId, setUserAccounts, setUserGroups]);
};
