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
  reboot_mode: 'never' | 'when_needed';
  excluded_packages: string;
  require_backup_hours: number | null;
  held: boolean;
  hold_reason: string | null;
  hold_by: string | null;
  hold_at: string | null;
  host_ids: string[];
}

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
  reboot_mode?: 'never' | 'when_needed';
  excluded_packages?: string | null;
  require_backup_hours?: number | null;
  host_ids?: string[];
}

export type UpgradeProfileUpdate = Partial<UpgradeProfileCreate>;

export interface TriggerResult {
  profile_id: string;
  name: string;
  queued: number;
  skipped: number;
  nothing: number;
  other_policy: number;
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
