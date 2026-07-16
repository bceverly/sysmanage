// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

/**
 * API key management client (Phase 13.2 — API Completeness).
 *
 * Wraps ``/api/v1/api-keys`` — list/create/get/revoke of the current user's
 * programmatic-access keys.  The plaintext key is returned only by
 * ``createApiKey`` (once); it is never available afterwards.
 */

import axiosInstance from './api';

export interface ApiKey {
  id: string;
  user_id: string;
  name: string;
  key_prefix: string;
  scopes?: string | null;
  tenant_id?: string | null;
  is_active: boolean;
  created_at?: string | null;
  last_used_at?: string | null;
  expires_at?: string | null;
  revoked_at?: string | null;
}

export interface ApiKeyCreate {
  name: string;
  expires_at?: string | null;
  scopes?: string | null;
}

/** Creation response — extends ApiKey with the one-time plaintext ``key``. */
export interface ApiKeyCreated extends ApiKey {
  key: string;
}

export const listApiKeys = async (): Promise<ApiKey[]> => {
  const r = await axiosInstance.get<ApiKey[]>('/api/v1/api-keys');
  return r.data;
};

export const createApiKey = async (
  payload: ApiKeyCreate,
): Promise<ApiKeyCreated> => {
  const r = await axiosInstance.post<ApiKeyCreated>('/api/v1/api-keys', payload);
  return r.data;
};

export const getApiKey = async (id: string): Promise<ApiKey> => {
  const r = await axiosInstance.get<ApiKey>(`/api/v1/api-keys/${id}`);
  return r.data;
};

export const revokeApiKey = async (id: string): Promise<void> => {
  await axiosInstance.delete(`/api/v1/api-keys/${id}`);
};
