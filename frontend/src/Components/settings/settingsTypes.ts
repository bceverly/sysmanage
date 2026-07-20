// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

export interface Tag {
  id: string;
  name: string;
  description: string | null;
  created_at: string;
  updated_at: string;
  host_count: number;
}

export interface TagWithHosts extends Tag {
  hosts: Array<{
    id: string;
    fqdn: string;
    ipv4: string;
    ipv6: string;
    active: boolean;
    status: string;
  }>;
}

export interface PackageInfo {
  name: string;
  version: string;
  description?: string;
  package_manager: string;
}

export interface PackageManagerSummary {
  package_manager: string;
  package_count: number;
}

export interface OSPackageSummary {
  os_name: string;
  os_version: string;
  package_managers: PackageManagerSummary[];
  total_packages: number;
}

export interface Host {
  id: string;
  fqdn: string;
  ipv4: string;
  ipv6: string;
  active: boolean;
  approval_status: string;
  platform?: string;
  platform_version?: string;
}

export interface QueueMessage {
  id: string;
  type: string;
  direction: string;
  timestamp: string;
  created_at: string;
  host_id: string | null;
  priority: string;
  data: Record<string, unknown>;
}
