// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

// Automatic updates (ROADMAP 26.1, Enterprise): holds, opt-outs, runs.

import axiosInstance from './api.js';

export interface SkippedPackage {
  package_name: string;
  package_manager: string;
  reason: string;
  kind?: 'critical' | 'regular';
  fix_id?: string | null;
  eligible_at?: string | null;
}

// 26.3: one pending update under the host's policy -- applied on the next
// run (reason null), left out and why, or waiting until eligible_at.
export interface PendingUpdate extends SkippedPackage {
  reason: string;
  available_version?: string | null;
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
  packages: {
    package_name: string;
    package_manager: string;
    available_version?: string;
    kind?: 'critical' | 'regular' | null;
    fix_id?: string | null;
  }[];
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
  critical_threshold: 'critical' | 'high';
  counts?: {
    failed_recent: number;
    queued: number;
    waiting?: number;
    reboot_not_back: number;
    opted_out_hosts: number;
    // 26.5: reboots waiting for a window; 26.4 rollouts.
    reboot_waiting?: number;
    rollouts_running?: number;
    rollouts_halted?: number;
  };
}

// 26.4: one host of a rollout's fleet and its latest run there.
export interface RolloutHost {
  host_id: string;
  hostname: string | null;
  run_id: string | null;
  status: string | null;
  reason: string | null;
  reboot_status: string | null;
  release_at: string | null;
}

export interface RolloutStage {
  name: string;
  tag_id: string | null;
  soak_minutes: number;
  host_ids: string[];
  remaining?: boolean;
  status: 'pending' | 'running' | 'done' | 'halted';
  started_at: string | null;
  finished_at: string | null;
  soak_until?: string | null;
  forced?: boolean;
  resumed_by?: string;
  counts?: { hosts: number; in_flight?: number; applied?: number; failed?: number; other?: number };
  hosts: RolloutHost[];
}

export interface Rollout {
  id: string;
  profile_id: string | null;
  profile_name: string;
  status: 'running' | 'halted' | 'completed' | 'canceled';
  stage_index: number;
  stages: RolloutStage[];
  triggered_by: string | null;
  started_at: string | null;
  completed_at: string | null;
  halt_reason: string | null;
  halt_detail: { stage?: number; culprits?: string[]; failure_pct?: number;
    max_failure_pct?: number; alerts?: string[] };
  halted_at: string | null;
  ended_by: string | null;
  end_reason: string | null;
}

export interface HostAutoUpdates {
  host_id: string;
  opt_out: boolean;
  opt_out_reason: string | null;
  hold_all: boolean;
  policy: {
    id: string;
    name: string;
    rule: string;
    candidates: string[];
    wait_days_regular?: number;
    wait_days_critical?: number;
    critical_source?: string;
    reboot_mode?: string;
  } | null;
  runs: AutoUpdateRun[];
  // 26.3: null with an engine older than 26.3, or no policy.
  pending?: {
    updates: PendingUpdate[];
    sources: { vulnerability: boolean; advisory: boolean };
    critical_threshold: string;
  } | null;
  // 26.2: the host's maintenance-window state.
  window?: {
    state: 'unrestricted' | 'in_window' | 'blocked' | 'override';
    active_blackout: string | null;
    next_window: { id: string; name: string; starts_at: string | null } | null;
  } | null;
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
  async updateSettings(changes: {
    retry_after_hours?: number;
    reboot_timeout_minutes?: number;
    critical_threshold?: 'critical' | 'high';
  }): Promise<AutoUpdateSettings> {
    return (await axiosInstance.put(`${BASE}/settings`, changes)).data;
  },
  async acknowledge(runId: string): Promise<AutoUpdateRun> {
    return (await axiosInstance.post(`${BASE}/runs/${runId}/acknowledge`)).data;
  },
  async rollouts(params: { status?: string; limit?: number } = {}): Promise<Rollout[]> {
    return (await axiosInstance.get(`${BASE}/rollouts`, { params })).data;
  },
  async resumeRollout(id: string, reason: string): Promise<Rollout> {
    return (await axiosInstance.post(`${BASE}/rollouts/${id}/resume`, { reason })).data;
  },
  async cancelRollout(id: string, reason: string): Promise<Rollout> {
    return (await axiosInstance.post(`${BASE}/rollouts/${id}/cancel`, { reason })).data;
  },
};
