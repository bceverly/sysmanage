// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

// Pure helper functions extracted from HostDetail.tsx.  Functions that need
// i18n take the ``t`` function as their first argument so they stay pure and
// testable outside a React component.

import type { TFunction } from 'i18next';
import { SysManageHost, UserAccount, UserGroup } from '../../Services/hosts';
import { parseUTCTimestamp, formatUTCTimestamp } from '../../utils/dateUtils';

export const formatDate = (t: TFunction, dateString: string | null | undefined): string => {
    return formatUTCTimestamp(dateString, t('common.notAvailable', 'N/A'));
};

export const formatTimestamp = (t: TFunction, timestamp: string | null | undefined) => {
    if (!timestamp) return t('hosts.never', 'never');
    const date = parseUTCTimestamp(timestamp);
    if (!date) return t('hosts.invalidDate', 'invalid');

    const now = new Date();
    const diffMinutes = Math.floor((now.getTime() - date.getTime()) / 60000);
    if (diffMinutes < 2) return t('hosts.justNow', 'just now');
    if (diffMinutes < 60) return t('hosts.minutesAgo', '{{minutes}}m ago', { minutes: diffMinutes });
    if (diffMinutes < 1440) return t('hosts.hoursAgo', '{{hours}}h ago', { hours: Math.floor(diffMinutes / 60) });
    return t('hosts.daysAgo', '{{days}}d ago', { days: Math.floor(diffMinutes / 1440) });
};

export const getStatusColor = (status: string) => {
    return status === 'up' ? 'success' : 'error';
};

export const getDisplayStatus = (host: SysManageHost) => {
    if (!host.last_access) return 'down';

    // Same logic as host list: consider host "up" if last access was within 5 minutes
    const lastAccess = parseUTCTimestamp(host.last_access);
    if (!lastAccess) return 'down';
    const now = new Date();
    const diffMinutes = Math.floor((now.getTime() - lastAccess.getTime()) / 60000);

    return diffMinutes <= 5 ? 'up' : 'down';
};

export const getApprovalStatusColor = (status: string) => {
    switch (status) {
        case 'approved': return 'success';
        case 'pending': return 'warning';
        case 'rejected': return 'error';
        case 'revoked': return 'error';
        default: return 'default';
    }
};

export const formatMemorySize = (t: TFunction, mb: number | undefined) => {
    if (!mb) return t('common.notAvailable');
    if (mb >= 1024) {
        return `${(mb / 1024).toFixed(1)} GB`;
    }
    return `${mb} MB`;
};

export const formatCpuFrequency = (t: TFunction, mhz: number | undefined) => {
    if (!mhz) return t('common.notAvailable');
    if (mhz >= 1000) {
        return `${(mhz / 1000).toFixed(1)} GHz`;
    }
    return `${mhz} MHz`;
};

// Helper function to get user ID label and value (extracts nested ternary for SonarQube compliance)
export const getUserIdDisplay = (t: TFunction, host: SysManageHost | null, user: UserAccount): string => {
    const isWindows = host?.platform?.toLowerCase().includes('windows');
    const label = isWindows ? 'SID' : 'UID';
    let value: string;
    if (isWindows) {
        value = user.security_id || t('common.notAvailable');
    } else {
        value = user.uid === undefined ? t('common.notAvailable') : String(user.uid);
    }
    return `${label}: ${value}`;
};

// Helper function to get group ID label and value (extracts nested ternary for SonarQube compliance)
export const getGroupIdDisplay = (t: TFunction, host: SysManageHost | null, group: UserGroup): string => {
    const isWindows = host?.platform?.toLowerCase().includes('windows');
    const label = isWindows ? 'SID' : 'GID';
    let value: string;
    if (isWindows) {
        value = group.security_id || t('common.notAvailable');
    } else {
        value = (group.gid !== undefined && group.gid !== null) ? String(group.gid) : t('common.notAvailable');
    }
    return `${label}: ${value}`;
};

// Utility function to format bytes with appropriate units
export const formatBytesWithCommas = (t: TFunction, bytes?: number): string => {
    if (!bytes || bytes === 0) return t('common.notAvailable');

    const units = ['B', 'KB', 'MB', 'GB', 'TB'];
    let size = bytes;
    let unitIndex = 0;

    while (size >= 1024 && unitIndex < units.length - 1) {
        size /= 1024;
        unitIndex++;
    }

    const formattedSize = size.toLocaleString(undefined, {
        maximumFractionDigits: unitIndex === 0 ? 0 : 1
    });

    const unit = units.at(unitIndex) ?? 'B';
    return `${formattedSize} ${unit}`;
};

// Utility function to calculate and format capacity with percentage free
export const formatCapacityWithFree = (t: TFunction, capacity?: number, used?: number, available?: number): string => {
    if (!capacity || capacity === 0) return t('common.notAvailable');

    const capacityFormatted = formatBytesWithCommas(t, capacity);

    if (available !== undefined && available !== null) {
        const freePercentage = Math.round((available / capacity) * 100);
        return `${capacityFormatted} (${freePercentage}% free)`;
    } else if (used !== undefined && used !== null) {
        const freeBytes = capacity - used;
        const freePercentage = Math.round((freeBytes / capacity) * 100);
        return `${capacityFormatted} (${freePercentage}% free)`;
    }

    return capacityFormatted;
};

// Utility function to calculate usage percentage for storage bars
export const getStorageUsagePercentage = (capacity?: number, used?: number, available?: number): number => {
    if (!capacity || capacity === 0) return 0;

    // Prefer available bytes calculation for consistency with the text display
    // This accounts for filesystem overhead and ensures text and bar match
    if (available !== undefined && available !== null) {
        const usedPercentage = Math.min(Math.max(((capacity - available) / capacity) * 100, 0), 100);
        return usedPercentage;
    } else if (used !== undefined && used !== null) {
        return Math.min(Math.max((used / capacity) * 100, 0), 100);
    }

    return 0;
};

// Utility function to get color based on storage usage percentage
export const getStorageUsageColor = (usagePercentage: number): 'success' | 'warning' | 'error' => {
    if (usagePercentage < 70) return 'success';     // Green: lots of free space
    if (usagePercentage < 90) return 'warning';     // Amber: getting full
    return 'error';                                 // Red: scary close to full or full
};

// Format datetime for display
export const formatDateTime = (dateString: string) => {
    return formatUTCTimestamp(dateString);
};

// Get installation status color
export const getInstallationStatusColor = (status: string): 'success' | 'error' | 'warning' | 'default' => {
    switch (status.toLowerCase()) {
        case 'completed':
            return 'success';
        case 'failed':
            return 'error';
        case 'pending':
        case 'queued':
        case 'installing':
        case 'in_progress':
            return 'warning';
        default:
            return 'default';
    }
};

// Get translated status text
export const getTranslatedStatus = (t: TFunction, status: string) => {
    const translationKey = `scripts.status.${status.toLowerCase()}`;
    const translated = t(translationKey);
    // If translation not found, return capitalized status
    return translated === translationKey ?
        status.charAt(0).toUpperCase() + status.slice(1).replaceAll('_', ' ') :
        translated;
};

// Get OpenTelemetry service status label (extracted for SonarQube compliance)
export const getOpenTelemetryServiceLabel = (t: TFunction, serviceStatus: string): string => {
    if (serviceStatus === 'running') {
        return t('hostDetail.opentelemetryServiceRunning', 'Running');
    } else if (serviceStatus === 'stopped') {
        return t('hostDetail.opentelemetryServiceStopped', 'Stopped');
    } else {
        return t('hostDetail.opentelemetryServiceUnknown', 'Unknown');
    }
};

// Get OpenTelemetry service status color (extracted for SonarQube compliance)
export const getOpenTelemetryServiceColor = (serviceStatus: string): 'success' | 'error' | 'default' => {
    if (serviceStatus === 'running') {
        return 'success';
    } else if (serviceStatus === 'stopped') {
        return 'error';
    } else {
        return 'default';
    }
};

// Get role service status label (extracted for SonarQube compliance)
export const getRoleServiceStatusLabel = (t: TFunction, serviceStatus: string | null | undefined): string => {
    if (serviceStatus === 'running') {
        return t('hostDetail.running', 'Running');
    } else if (serviceStatus === 'stopped') {
        return t('hostDetail.stopped', 'Stopped');
    } else if (serviceStatus === 'installed') {
        return t('hostDetail.installed', 'Installed');
    } else {
        return serviceStatus || t('common.unknown', 'Unknown');
    }
};

// Get role service status color (extracted for SonarQube compliance)
export const getRoleServiceStatusColor = (serviceStatus: string | null | undefined): 'success' | 'error' | 'info' | 'default' => {
    if (serviceStatus === 'running') {
        return 'success';
    } else if (serviceStatus === 'stopped') {
        return 'error';
    } else if (serviceStatus === 'installed') {
        return 'info';
    } else {
        return 'default';
    }
};

// Get service status label for Ubuntu Pro services (extracted for SonarQube compliance)
export const getServiceStatusLabel = (t: TFunction, status: string): string => {
    if (status === 'n/a') {
        return t('common.notAvailable', 'N/A');
    } else if (status === 'enabled') {
        return t('hostDetail.enabled', 'Enabled');
    } else {
        return t('hostDetail.disabled', 'Disabled');
    }
};

// Get service status color for Ubuntu Pro services (extracted for SonarQube compliance)
export const getServiceStatusColor = (status: string): 'success' | 'default' | 'warning' => {
    if (status === 'enabled') {
        return 'success';
    } else if (status === 'n/a') {
        return 'default';
    } else {
        return 'warning';
    }
};

// Resolve the OS name (without version) used to look up antivirus defaults.
// macOS is special-cased because platform_release holds version codenames;
// for everything else we prefer platform_release but fall back to platform
// when platform_release is just a version number (e.g. "7.7").
export const resolveAntivirusOsName = (
    platform = '',
    platformRelease = '',
): string => {
    if (platform === 'macOS') {
        return 'macOS';
    }

    // Prefer platform_release, but fall back to platform when the release is
    // not a name (e.g. "7.7" starts with a digit rather than a letter).
    const source = /^[A-Za-z]/.test(platformRelease) ? platformRelease : platform;

    // Extract the OS name without its version (e.g. "Ubuntu 25.04" -> "Ubuntu").
    const match = /^([A-Za-z]+)/.exec(source);
    return match ? match[1] : source;
};

// True when the host platform/release indicates an Ubuntu system.
export const isUbuntuHost = (
    platform: string | null | undefined,
    platformRelease: string | null | undefined,
): boolean =>
    Boolean(
        platform?.toLowerCase().includes('ubuntu') ||
        platformRelease?.toLowerCase().includes('ubuntu'),
    );

// True when the host platform supports child hosts (Windows WSL / Linux LXD).
export const supportsChildHosts = (platform: string | null | undefined): boolean =>
    Boolean(platform?.includes('Windows') || platform?.includes('Linux'));

// Resolve a list from normalized API data, falling back to parsing a legacy
// JSON string field on the host when the normalized list is empty.
export const resolveWithLegacyFallback = <TItem>(
    normalized: TItem[],
    legacyJson: string | null | undefined,
    label: string,
): TItem[] => {
    if (normalized.length === 0 && legacyJson) {
        try {
            return JSON.parse(legacyJson) as TItem[];
        } catch (error) {
            console.warn(`Failed to parse legacy ${label} data:`, error);
            return normalized;
        }
    }
    return normalized;
};

// Run an optional data fetch that must never fail the whole page load.
export const runOptionalFetch = async (
    label: string,
    fetcher: () => Promise<void>,
): Promise<void> => {
    try {
        await fetcher();
    } catch (error) {
        // Optional data — log but don't fail the page load
        console.log(`${label} not available or failed to load:`, error);
    }
};
