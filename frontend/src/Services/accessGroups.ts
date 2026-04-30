import axiosInstance from './api.js';

export interface AccessGroup {
  id: string;
  name: string;
  description: string | null;
  parent_id: string | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface AccessGroupCreate {
  name: string;
  description?: string | null;
  parent_id?: string | null;
}

export interface AccessGroupUpdate {
  name?: string | null;
  description?: string | null;
  parent_id?: string | null;
}

export interface RegistrationKey {
  id: string;
  name: string;
  access_group_id: string | null;
  auto_approve: boolean;
  revoked: boolean;
  max_uses: number | null;
  use_count: number;
  expires_at: string | null;
  created_at: string | null;
  last_used_at: string | null;
  // Only populated on the create response.
  key?: string | null;
}

export interface RegistrationKeyCreate {
  name: string;
  access_group_id?: string | null;
  auto_approve?: boolean;
  max_uses?: number | null;
  expires_at?: string | null;
}

export const accessGroupsService = {
  async list(): Promise<AccessGroup[]> {
    const r = await axiosInstance.get('/api/access-groups');
    return r.data;
  },

  async create(payload: AccessGroupCreate): Promise<AccessGroup> {
    const r = await axiosInstance.post('/api/access-groups', payload);
    return r.data;
  },

  async update(id: string, payload: AccessGroupUpdate): Promise<AccessGroup> {
    const r = await axiosInstance.put(`/api/access-groups/${id}`, payload);
    return r.data;
  },

  async remove(id: string): Promise<void> {
    await axiosInstance.delete(`/api/access-groups/${id}`);
  },
};

export const registrationKeysService = {
  async list(): Promise<RegistrationKey[]> {
    const r = await axiosInstance.get('/api/registration-keys');
    return r.data;
  },

  async create(payload: RegistrationKeyCreate): Promise<RegistrationKey> {
    const r = await axiosInstance.post('/api/registration-keys', payload);
    return r.data;
  },

  async revoke(id: string): Promise<void> {
    await axiosInstance.post(`/api/registration-keys/${id}/revoke`);
  },

  async remove(id: string): Promise<void> {
    await axiosInstance.delete(`/api/registration-keys/${id}`);
  },
};
