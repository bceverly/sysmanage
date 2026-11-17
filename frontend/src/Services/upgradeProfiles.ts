// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

import axiosInstance from './api.js';

export interface UpgradeProfile {
  id: string;
  name: string;
  description: string | null;
  cron: string;
  enabled: boolean;
  security_only: boolean;
  package_managers: string[];
  staggered_window_min: number;
  tag_id: string | null;
  last_run: string | null;
  last_status: string | null;
  next_run: string | null;
  created_at: string | null;
  updated_at: string | null;
  // 26.1 automatic application (Enterprise)
  auto_apply: boolean;
  reboot_mode: RebootMode;
  excluded_packages: string;
  require_backup_hours: number | null;
  held: boolean;
  hold_reason: string | null;
  hold_by: string | null;
  hold_at: string | null;
  host_ids: string[];
  // 26.3 waiting periods (Enterprise)
  wait_days_regular: number;
  wait_days_critical: number;
  critical_source: CriticalSource;
  // 26.4 fleet-by-fleet rollout (Enterprise)
  rollout_enabled: boolean;
  rollout_max_failure_pct: number;
  rollout_stages: RolloutStageConfig[];
}

// 26.4: one fleet of a policy's rollout, as stored.
export interface RolloutStageConfig {
  id?: string;
  position?: number;
  name: string;
  tag_id: string | null;
  soak_minutes: number;
}

// 26.4: one fleet as the form sends it.
export interface RolloutStageInput {
  name: string;
  tag_id: string;
  soak_hours: number;
}

// 26.2: in_window reboots only inside a maintenance window.
export type RebootMode = 'never' | 'when_needed' | 'in_window';
export type CriticalSource = 'vulnerability' | 'advisory' | 'either';

export interface UpgradeProfileCreate {
  name: string;
  description?: string | null;
  cron?: string;
  enabled?: boolean;
  security_only?: boolean;
  package_managers?: string[] | null;
  staggered_window_min?: number;
  tag_id?: string | null;
  auto_apply?: boolean;
  reboot_mode?: RebootMode;
  excluded_packages?: string | null;
  require_backup_hours?: number | null;
  host_ids?: string[];
  wait_days_regular?: number;
  wait_days_critical?: number;
  critical_source?: CriticalSource;
  rollout_enabled?: boolean;
  rollout_max_failure_pct?: number;
  rollout_stages?: RolloutStageInput[];
}

export type UpgradeProfileUpdate = Partial<UpgradeProfileCreate>;

export interface TriggerResult {
  profile_id: string;
  name: string;
  queued: number;
  skipped: number;
  nothing: number;
  other_policy: number;
  waiting?: number;
  next_run: string | null;
}

export const upgradeProfilesService = {
  async list(): Promise<UpgradeProfile[]> {
    const r = await axiosInstance.get('/api/v1/upgrade-profiles');
    return r.data;
  },

  async create(payload: UpgradeProfileCreate): Promise<UpgradeProfile> {
    const r = await axiosInstance.post('/api/v1/upgrade-profiles', payload);
    return r.data;
  },

  async update(id: string, payload: UpgradeProfileUpdate): Promise<UpgradeProfile> {
    const r = await axiosInstance.put(`/api/v1/upgrade-profiles/${id}`, payload);
    return r.data;
  },

  async remove(id: string): Promise<void> {
    await axiosInstance.delete(`/api/v1/upgrade-profiles/${id}`);
  },

  async trigger(id: string): Promise<TriggerResult> {
    const r = await axiosInstance.post(`/api/v1/upgrade-profiles/${id}/trigger`);
    return r.data;
  },
};
