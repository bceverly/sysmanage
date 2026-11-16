// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

// Automatic updates (ROADMAP 26.1, Enterprise): holds, opt-outs, runs.

import axiosInstance from './api.js';

export interface SkippedPackage {
  package_name: string;
  package_manager: string;
  reason: string;
}

export interface AutoUpdateRun {
  id: string;
  profile_id: string | null;
  profile_name: string;
  host_id: string;
  hostname?: string | null;
  status: string;
  reason: string | null;
  triggered_by: string | null;
  packages: { package_name: string; package_manager: string; available_version?: string }[];
  skipped: SkippedPackage[];
  applied_count: number;
  failed_count: number;
  failures: { package_name: string; package_manager: string; error: string }[];
  reboot_needed: boolean;
  reboot_status: string;
  queued_at: string | null;
  release_at: string | null;
  completed_at: string | null;
  acknowledged_by: string | null;
  acknowledged_at: string | null;
}

export interface AutoUpdateSettings {
  hold_all: boolean;
  hold_reason: string | null;
  hold_by: string | null;
  hold_at: string | null;
  retry_after_hours: number;
  reboot_timeout_minutes: number;
  counts?: {
    failed_recent: number;
    queued: number;
    reboot_not_back: number;
    opted_out_hosts: number;
  };
}

export interface HostAutoUpdates {
  host_id: string;
  opt_out: boolean;
  opt_out_reason: string | null;
  hold_all: boolean;
  policy: { id: string; name: string; rule: string; candidates: string[] } | null;
  runs: AutoUpdateRun[];
}

const BASE = '/api/v1/auto-updates';

export const autoUpdatesService = {
  async settings(): Promise<AutoUpdateSettings> {
    return (await axiosInstance.get(`${BASE}/settings`)).data;
  },
  async holdAll(hold: boolean, reason?: string): Promise<AutoUpdateSettings> {
    return (await axiosInstance.put(`${BASE}/hold-all`, { hold, reason })).data;
  },
  async holdProfile(id: string, hold: boolean, reason?: string) {
    return (await axiosInstance.put(`${BASE}/profiles/${id}/hold`, { hold, reason })).data;
  },
  async optOut(hostId: string, optOut: boolean, reason?: string) {
    return (await axiosInstance.put(`${BASE}/hosts/${hostId}/opt-out`, { opt_out: optOut, reason })).data;
  },
  async host(hostId: string): Promise<HostAutoUpdates> {
    return (await axiosInstance.get(`${BASE}/hosts/${hostId}`)).data;
  },
  async runs(params: { status?: string; limit?: number } = {}): Promise<AutoUpdateRun[]> {
    return (await axiosInstance.get(`${BASE}/runs`, { params })).data;
  },
  async acknowledge(runId: string): Promise<AutoUpdateRun> {
    return (await axiosInstance.post(`${BASE}/runs/${runId}/acknowledge`)).data;
  },
};
