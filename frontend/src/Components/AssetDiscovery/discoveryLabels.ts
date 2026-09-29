// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

// Wording for asset discovery (Phase 21.6).  The server sends codes; literal
// t() keys here so the i18n tooling sees every one.

import type { TFunction } from 'i18next';
import type { DeviceType, ExclusionCategory } from '../../Services/assetDiscoveryService';

export const categoryLabel = (t: TFunction, category: ExclusionCategory | string): string => {
    const labels: Record<ExclusionCategory, string> = {
        printer: t('assetDiscovery.category.printer', 'Printer'),
        iot: t('assetDiscovery.category.iot', 'IoT device or sensor'),
        network_equipment: t('assetDiscovery.category.networkEquipment', 'Network equipment'),
        appliance: t('assetDiscovery.category.appliance', 'Appliance'),
        personal_device: t('assetDiscovery.category.personalDevice', 'Personal device'),
        virtual_machine: t('assetDiscovery.category.virtualMachine', 'Virtual machine'),
        virtual_address: t('assetDiscovery.category.virtualAddress', 'Virtual or shared address (VIP, load balancer)'),
        other: t('assetDiscovery.category.other', 'Other'),
    };
    return labels[category as ExclusionCategory] ?? category;
};

export const methodLabel = (t: TFunction, method: string): string => {
    const labels: Record<string, string> = {
        arp_listen: t('assetDiscovery.method.arpListen', 'ARP listening'),
        nd_listen: t('assetDiscovery.method.ndListen', 'IPv6 neighbor discovery'),
        cache: t('assetDiscovery.method.cache', 'Neighbor cache'),
        mdns: t('assetDiscovery.method.mdns', 'mDNS'),
        ssdp: t('assetDiscovery.method.ssdp', 'SSDP'),
        sweep: t('assetDiscovery.method.sweep', 'Active sweep'),
    };
    return labels[method] ?? method;
};

export const unavailableLabel = (t: TFunction, reason: string): string => {
    const labels: Record<string, string> = {
        not_root: t('assetDiscovery.unavailable.notRoot', 'the agent is not running as root'),
        unsupported_platform: t('assetDiscovery.unavailable.unsupportedPlatform', 'not supported on this platform'),
        port_in_use: t('assetDiscovery.unavailable.portInUse', 'the port is in use by another program'),
        unreadable: t('assetDiscovery.unavailable.unreadable', 'could not be read'),
        disabled: t('assetDiscovery.unavailable.disabled', 'not enabled'),
    };
    return labels[reason] ?? reason;
};

export const formatSeen = (iso: string | null): string => {
    if (!iso) return '-';
    const date = new Date(iso.endsWith('Z') || iso.includes('+') ? iso : `${iso}Z`);
    return Number.isNaN(date.getTime()) ? iso : date.toLocaleString();
};

export const deviceTypeLabel = (t: TFunction, kind: DeviceType | string | null | undefined): string => {
    const labels: Record<DeviceType, string> = {
        printer: t('assetDiscovery.type.printer', 'Printer'),
        media: t('assetDiscovery.type.media', 'TV, speaker or media player'),
        phone_or_tablet: t('assetDiscovery.type.phoneOrTablet', 'Phone or tablet'),
        computer: t('assetDiscovery.type.computer', 'Computer'),
        network_equipment: t('assetDiscovery.type.networkEquipment', 'Network equipment'),
        iot: t('assetDiscovery.type.iot', 'IoT device'),
        virtual_machine: t('assetDiscovery.type.virtualMachine', 'Virtual machine'),
        virtual_address: t('assetDiscovery.type.virtualAddress', 'Virtual router address'),
        unknown: t('assetDiscovery.type.unknown', 'Unknown'),
    };
    return labels[(kind ?? 'unknown') as DeviceType] ?? String(kind);
};

// The exclusion category a device's guessed type suggests, if any.
export const categoryForType = (kind: DeviceType | string | null | undefined): ExclusionCategory | null => {
    const map: Partial<Record<DeviceType, ExclusionCategory>> = {
        printer: 'printer',
        media: 'appliance',
        phone_or_tablet: 'personal_device',
        network_equipment: 'network_equipment',
        iot: 'iot',
        virtual_machine: 'virtual_machine',
        virtual_address: 'virtual_address',
    };
    return map[(kind ?? 'unknown') as DeviceType] ?? null;
};
