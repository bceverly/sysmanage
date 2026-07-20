// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

// Memoized storage/network/user/group filtering + shell parsing for Host Detail.

import { useCallback, useMemo } from 'react';
import {
    SysManageHost,
    StorageDevice as StorageDeviceType,
    NetworkInterface as NetworkInterfaceType,
    UserAccount,
    UserGroup,
} from '../../Services/hosts';
import { HostFilterMode } from './hostDetailTypes';

interface UseHostInventoryFiltersArgs {
    host: SysManageHost | null;
    storageDevices: StorageDeviceType[];
    networkInterfaces: NetworkInterfaceType[];
    userAccounts: UserAccount[];
    userGroups: UserGroup[];
    storageFilter: 'all' | 'physical' | 'logical';
    networkFilter: 'all' | 'active' | 'inactive';
    userFilter: HostFilterMode;
    groupFilter: HostFilterMode;
}

export const useHostInventoryFilters = ({
    host,
    storageDevices,
    networkInterfaces,
    userAccounts,
    userGroups,
    storageFilter,
    networkFilter,
    userFilter,
    groupFilter,
}: UseHostInventoryFiltersArgs) => {
    // Helper function to assign priority to mount points (lower = higher priority)
    const getMountPointPriority = useCallback((mountPoint: string): number => {
        if (mountPoint === '/') return 1;                           // Root - highest priority
        if (mountPoint.includes('/System/Volumes')) return 3;      // System volumes - lower priority
        if (mountPoint.includes('/Library')) return 4;             // Library volumes - even lower
        return 2;                                                   // Other mounts - medium priority
    }, []);

    // Utility function to deduplicate storage devices by name, preferring root mounts
    const deduplicateStorageDevices = useCallback((devices: StorageDeviceType[]): StorageDeviceType[] => {
        const devicesByName = new Map<string, StorageDeviceType[]>();

        // Group devices by name
        devices.forEach(device => {
            const deviceName = device.name || 'Unknown Device';
            if (!devicesByName.has(deviceName)) {
                devicesByName.set(deviceName, []);
            }
            devicesByName.get(deviceName)!.push(device);
        });

        // For each name, select the best representative device
        const deduplicatedDevices: StorageDeviceType[] = [];
        devicesByName.forEach((deviceGroup) => {
            if (deviceGroup.length === 1) {
                // Only one device with this name, keep it
                deduplicatedDevices.push(deviceGroup[0]);
            } else {
                // Multiple devices with same name, prioritize by mount point
                // Priority: root (/), then system volumes, then others
                const prioritized = deviceGroup.toSorted((a, b) => {
                    const aMountPriority = getMountPointPriority(a.mount_point || '');
                    const bMountPriority = getMountPointPriority(b.mount_point || '');
                    return aMountPriority - bMountPriority;
                });

                deduplicatedDevices.push(prioritized[0]);
            }
        });

        return deduplicatedDevices;
    }, [getMountPointPriority]);

    // Filter storage devices based on physical/logical selection (memoized)
    const filteredStorageDevices = useMemo(() => {
        const deduplicatedDevices = deduplicateStorageDevices(storageDevices);

        switch (storageFilter) {
            case 'physical':
                return deduplicatedDevices.filter(device => device.is_physical === true);
            case 'logical':
                return deduplicatedDevices.filter(device => device.is_physical === false);
            case 'all':
            default:
                // Sort physical devices first, then logical
                return deduplicatedDevices.sort((a, b) => {
                    if (a.is_physical === b.is_physical) return 0;
                    return a.is_physical ? -1 : 1;
                });
        }
    }, [storageDevices, storageFilter, deduplicateStorageDevices]);

    // Filter user accounts based on system/regular selection (memoized)
    const filteredUsers = useMemo(() => {
        switch (userFilter) {
            case 'system':
                return userAccounts.filter(user => user.is_system_user === true);
            case 'regular':
                return userAccounts.filter(user => user.is_system_user === false);
            case 'all':
            default:
                // Sort regular users first, then system
                return userAccounts.sort((a, b) => {
                    if (a.is_system_user === b.is_system_user) return 0;
                    return a.is_system_user ? 1 : -1;
                });
        }
    }, [userAccounts, userFilter]);

    // Filter user groups based on system/regular selection (memoized)
    const filteredGroups = useMemo(() => {
        switch (groupFilter) {
            case 'system':
                return userGroups.filter(group => group.is_system_group === true);
            case 'regular':
                return userGroups.filter(group => group.is_system_group === false);
            case 'all':
            default:
                // Sort regular groups first, then system
                return userGroups.sort((a, b) => {
                    if (a.is_system_group === b.is_system_group) return 0;
                    return a.is_system_group ? 1 : -1;
                });
        }
    }, [userGroups, groupFilter]);

    // Filter network interfaces based on active/inactive selection (memoized)
    const filteredNetworkInterfaces = useMemo(() => {
        switch (networkFilter) {
            case 'active':
                return networkInterfaces.filter(iface => !!(iface.ipv4_address || iface.ipv6_address));
            case 'inactive':
                return networkInterfaces.filter(iface => !(iface.ipv4_address || iface.ipv6_address));
            case 'all':
            default:
                // Sort active interfaces first, then inactive
                return networkInterfaces.sort((a, b) => {
                    const aHasIP = !!(a.ipv4_address || a.ipv6_address);
                    const bHasIP = !!(b.ipv4_address || b.ipv6_address);
                    if (aHasIP === bHasIP) return 0;
                    return aHasIP ? -1 : 1;
                });
        }
    }, [networkInterfaces, networkFilter]);


    // Parse enabled shells (memoized to avoid JSON.parse on every render)
    const enabledShells = useMemo(() => {
        if (!host?.enabled_shells) return [];
        try {
            const shells = JSON.parse(host.enabled_shells);
            return Array.isArray(shells) ? shells : [];
        } catch {
            return [];
        }
    }, [host?.enabled_shells]);

    // Check if diagnostics are currently being processed based on persistent state
    const isDiagnosticsProcessing = host?.diagnostics_request_status === 'pending';
    return {
        filteredStorageDevices,
        filteredNetworkInterfaces,
        filteredUsers,
        filteredGroups,
        enabledShells,
        isDiagnosticsProcessing,
    };
};
