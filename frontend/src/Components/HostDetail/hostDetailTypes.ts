// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

// Shared types and constants extracted from HostDetail.tsx.

// Inventory filter mode (user / group / storage / network list filters).
export type HostFilterMode = 'all' | 'system' | 'regular';

// Certificate interface
export interface Certificate {
    id: string;
    certificate_name: string;
    subject: string;
    issuer: string;
    not_before: string | null;
    not_after: string | null;
    serial_number: string;
    fingerprint_sha256: string;
    is_ca: boolean;
    key_usage: string | null;
    file_path: string;
    collected_at: string | null;
    is_expired: boolean;
    days_until_expiry: number | null;
    common_name: string | null;
}

export interface HostRole {
    id: string;
    role: string;
    package_name: string;
    package_version: string | null;
    service_name: string | null;
    service_status: string | null;
    is_active: boolean;
    detected_at: string;
    updated_at: string;
}

// Child host interface
export interface ChildHost {
    id: string;
    parent_host_id: string;
    child_host_id: string | null;
    child_name: string;
    child_type: string;
    distribution: string | null;
    distribution_version: string | null;
    hostname: string | null;
    status: string;
    installation_step: string | null;
    error_message: string | null;
    created_at: string | null;
    installed_at: string | null;
    reboot_required?: boolean;
    agent_version?: string | null;
}

// Virtualization status state
export interface VirtualizationStatus {
    supported_types: string[];
    capabilities: {
        wsl?: {
            available: boolean;
            enabled: boolean;
            needs_enable: boolean;
            needs_bios_virtualization?: boolean;
            version?: string;
            default_version?: number;
        };
        lxd?: {
            available: boolean;
            installed: boolean;
            initialized: boolean;
            user_in_group: boolean;
            needs_install: boolean;
            needs_init: boolean;
            snap_available: boolean;
        };
        vmm?: {
            available: boolean;
            enabled: boolean;
            running: boolean;
            initialized: boolean;
            kernel_supported: boolean;
            needs_enable: boolean;
        };
        kvm?: {
            available: boolean;
            installed: boolean;
            enabled: boolean;
            running: boolean;
            initialized: boolean;
            needs_install: boolean;
            needs_enable: boolean;
        };
        bhyve?: {
            available: boolean;
            enabled: boolean;
            running: boolean;
            initialized: boolean;
            kernel_supported: boolean;
            needs_enable: boolean;
        };
        [key: string]: unknown;
    };
    reboot_required: boolean;
}

export interface InstallationHistoryItem {
    request_id: string;  // UUID that groups packages
    requested_by: string;
    status: string;
    operation_type: string;  // install or uninstall
    requested_at: string;
    completed_at?: string;
    result_log?: string;
    package_names: string;  // Comma-separated list of package names
    installed_version?: string;
    error_message?: string;
    installation_log?: string;
}

export interface ChildHostFormData {
    childType: string;
    distribution: string;
    containerName: string;
    vmName: string;
    hostname: string;
    username: string;
    password: string;
    confirmPassword: string;
    rootPassword: string;
    confirmRootPassword: string;
    autoApprove: boolean;
}

export interface AvailableDistribution {
    id: string;
    display_name: string;
    install_identifier: string;
    child_type: string;
}

export type OpenTelemetryStatus = {
    deployed: boolean;
    service_status: string;
    grafana_url: string | null;
    grafana_configured: boolean;
} | null;

// Two-pane Host Detail: the (~15) tabs are grouped into a categorized left rail
// instead of one long horizontal strip.  Unmapped tab ids fall into "Overview".
export const HOST_CATEGORY_ORDER = [
  'overview', 'software', 'security', 'operations', 'access', 'virtualization',
] as const;
export const HOST_CAT_LABEL = new Map<string, { key: string; def: string }>([
  ['overview', { key: 'hostDetail.cat.overview', def: 'Overview' }],
  ['software', { key: 'hostDetail.cat.software', def: 'Software' }],
  ['security', { key: 'hostDetail.cat.security', def: 'Security' }],
  ['operations', { key: 'hostDetail.cat.operations', def: 'Operations' }],
  ['access', { key: 'hostDetail.cat.access', def: 'Access' }],
  ['virtualization', { key: 'hostDetail.cat.virtualization', def: 'Virtualization' }],
]);
export const HOST_TAB_CATEGORY = new Map<string, string>([
  ['info', 'overview'], ['hardware', 'overview'],
  ['software', 'software'], ['software-changes', 'software'], ['third-party-repos', 'software'],
  ['ubuntu-pro', 'software'], ['proplus-advisory', 'software'], ['proplus-lifecycle', 'software'],
  ['security', 'security'], ['compliance', 'security'], ['proplus-compliance', 'security'],
  ['fips-compliance', 'security'], ['certificates', 'security'], ['proplus-vuln', 'security'],
  ['processes', 'operations'], ['server-roles', 'operations'], ['diagnostics', 'operations'],
  ['proplus-health', 'operations'], ['proplus-alerting', 'operations'], ['proplus-audit', 'operations'],
  ['access', 'access'], ['proplus-secrets', 'access'],
  ['child-hosts', 'virtualization'], ['proplus-containers', 'virtualization'],
]);
