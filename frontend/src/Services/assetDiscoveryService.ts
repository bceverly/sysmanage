// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

import axiosInstance from "./api";

/**
 * Unenrolled asset discovery (Phase 21.6): the devices agents see on their
 * own segments, matched against the managed fleet. Enterprise -- every call
 * here fails on a server without `asset_discovery_engine`.
 *
 * THE LIST IS NEVER THE WHOLE ANSWER
 * Passive listening cannot reliably see a silent device, some agents cannot
 * listen for ARP, and an agent that stops reporting sees nothing. The summary
 * carries those blind spots; the page must show them beside the list.
 */

export type DeviceStatus = "unmanaged" | "managed" | "excluded" | "all";

export type DeviceType =
  | "printer"
  | "media"
  | "phone_or_tablet"
  | "computer"
  | "network_equipment"
  | "iot"
  | "virtual_machine"
  | "virtual_address"
  | "unknown";

export const RETENTION_CHOICES = [7, 30, 90, 365] as const;

export const EXCLUSION_CATEGORIES = [
  "printer",
  "iot",
  "network_equipment",
  "appliance",
  "personal_device",
  "virtual_machine",
  "virtual_address",
  "other",
] as const;
export type ExclusionCategory = (typeof EXCLUSION_CATEGORIES)[number];

export interface Exclusion {
  id: string;
  identity: string;
  category: ExclusionCategory;
  reason: string;
  created_by: string;
  created_at: string | null;
  revoked_by: string | null;
  revoked_at: string | null;
  revoke_reason: string | null;
  last_ip?: string | null;
  last_seen_at?: string | null;
}

export interface DiscoveredDevice {
  id: string;
  identity: string;
  identity_kind: "mac" | "ip";
  mac: string | null;
  mac_locally_administered: boolean;
  last_ip: string | null;
  ips: string[];
  hostnames: string[];
  evidence: { mdns_services?: string[]; ssdp?: string[] };
  methods: string[];
  vendor?: string | null;
  device_type?: DeviceType | null;
  classification?: { confidence?: "high" | "low" | "none"; reasons?: string[] };
  managed_host_id: string | null;
  managed_host_fqdn: string | null;
  managed_reason: string | null;
  first_seen_at: string | null;
  last_seen_at: string | null;
  status: Exclude<DeviceStatus, "all">;
  networks: string[];
  observers: string[];
  exclusion: Exclusion | null;
}

export interface DiscoveryPolicy {
  enabled: boolean;
  report_interval_seconds: number;
  sweep_enabled: boolean;
  retention_days?: number;
  updated_by: string | null;
  updated_at: string | null;
}

export interface DiscoveryObserver {
  host_id: string;
  fqdn: string;
  networks: { interface: string; network: string }[];
  last_report_at: string;
  stale: boolean;
  unavailable: Record<string, string>;
}

export interface DiscoverySummary {
  policy: DiscoveryPolicy;
  counts: { unmanaged: number; managed: number; excluded: number };
  types?: Record<string, number>;
  networks: { network: string; unmanaged: number; observers: number; swept_at?: string | null }[];
  observers: DiscoveryObserver[];
  coverage: { equipped: number; not_equipped: number; unknown: number };
  blind_spots: {
    silent_devices_unseen: boolean;
    unswept_networks?: string[];
    stale_observers: number;
    observers_without_arp: number;
  };
}

export type SweepStatus = "queued" | "completed" | "refused" | "failed" | "timed_out";

export interface SweepRun {
  id: string;
  cidr: string;
  rate: number;
  addresses: number;
  status: SweepStatus;
  reason: string | null;
  requested_by: string;
  requested_at: string | null;
  agent_host_id: string | null;
  agent_fqdn?: string | null;
  finished_at: string | null;
  probed: number | null;
  devices_found: number | null;
}

export const SWEEP_RATES = [10, 50, 100, 200] as const;

export interface ExcludeResult {
  excluded: number;
  already_excluded: number;
  skipped_managed: number;
  not_found: number;
  exclusions: Exclusion[];
}

const BASE = "/api/v1/asset-discovery";

export const assetDiscoveryService = {
  async getSummary(): Promise<DiscoverySummary> {
    return (await axiosInstance.get(`${BASE}/summary`)).data;
  },

  async listDevices(params: {
    status: DeviceStatus;
    network?: string;
    search?: string;
    limit?: number;
    offset?: number;
  }): Promise<{ total: number; devices: DiscoveredDevice[] }> {
    return (await axiosInstance.get(`${BASE}/devices`, { params })).data;
  },

  async listExclusions(includeRevoked = false): Promise<Exclusion[]> {
    const response = await axiosInstance.get(`${BASE}/exclusions`, {
      params: { include_revoked: includeRevoked },
    });
    return response.data.exclusions;
  },

  async exclude(
    assetIds: string[],
    category: ExclusionCategory,
    reason: string,
  ): Promise<ExcludeResult> {
    return (
      await axiosInstance.post(`${BASE}/exclusions`, {
        asset_ids: assetIds,
        category,
        reason,
      })
    ).data;
  },

  async revoke(exclusionId: string, reason: string): Promise<Exclusion> {
    return (
      await axiosInstance.post(`${BASE}/exclusions/${exclusionId}/revoke`, { reason })
    ).data;
  },

  async setPolicy(
    enabled: boolean,
    reportIntervalSeconds?: number,
    sweepEnabled?: boolean,
    retentionDays?: number,
  ): Promise<DiscoveryPolicy> {
    return (
      await axiosInstance.put(`${BASE}/policy`, {
        enabled,
        report_interval_seconds: reportIntervalSeconds,
        sweep_enabled: sweepEnabled,
        retention_days: retentionDays,
      })
    ).data;
  },

  async excludeAddress(
    address: string,
    category: ExclusionCategory,
    reason: string,
  ): Promise<Exclusion> {
    return (
      await axiosInstance.post(`${BASE}/exclusions/address`, { address, category, reason })
    ).data;
  },

  async listSweeps(): Promise<SweepRun[]> {
    return (await axiosInstance.get(`${BASE}/sweeps`)).data.sweeps;
  },

  async requestSweep(cidr: string, rate: number): Promise<SweepRun> {
    return (await axiosInstance.post(`${BASE}/sweeps`, { cidr, rate })).data;
  },
};
