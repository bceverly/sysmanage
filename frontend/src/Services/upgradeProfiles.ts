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
}

export type UpgradeProfileUpdate = Partial<UpgradeProfileCreate>;

export interface TriggerResult {
  profile_id: string;
  name: string;
  host_count: number;
  enqueued_count: number;
  host_ids: string[];
  next_run: string | null;
}

export const upgradeProfilesService = {
  async list(): Promise<UpgradeProfile[]> {
    const r = await axiosInstance.get('/api/upgrade-profiles');
    return r.data;
  },

  async create(payload: UpgradeProfileCreate): Promise<UpgradeProfile> {
    const r = await axiosInstance.post('/api/upgrade-profiles', payload);
    return r.data;
  },

  async update(id: string, payload: UpgradeProfileUpdate): Promise<UpgradeProfile> {
    const r = await axiosInstance.put(`/api/upgrade-profiles/${id}`, payload);
    return r.data;
  },

  async remove(id: string): Promise<void> {
    await axiosInstance.delete(`/api/upgrade-profiles/${id}`);
  },

  async trigger(id: string): Promise<TriggerResult> {
    const r = await axiosInstance.post(`/api/upgrade-profiles/${id}/trigger`);
    return r.data;
  },
};
