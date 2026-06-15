/**
 * Tenant account switching (Phase 13.1).
 *
 * Backs the navbar tenant switcher: list the tenants the logged-in user is
 * granted to, and switch the active tenant (which re-mints the JWT to carry
 * the new ``tenant_id``).  Multi-tenancy only — the endpoints 400 when the
 * feature is disabled, so callers should gate on the control-plane status.
 */

import axiosInstance from './api';

export interface TenantAccount {
  tenant_id: string;
  name: string;
  slug: string;
  role: string;
  is_default: boolean;
}

interface AccountsResponse {
  accounts: TenantAccount[];
  total: number;
}

/** Decode the ``tenant_id`` claim from the stored bearer token, if any. */
export function getActiveTenantId(): string | null {
  const token = localStorage.getItem('bearer_token');
  if (!token) return null;
  const parts = token.split('.');
  if (parts.length !== 3) return null;
  try {
    const payload = JSON.parse(
      globalThis.atob(parts[1].replace(/-/g, '+').replace(/_/g, '/')),
    );
    return payload?.tenant_id ?? null;
  } catch {
    return null;
  }
}

export const accountsService = {
  async list(): Promise<TenantAccount[]> {
    const r = await axiosInstance.get<AccountsResponse>('/api/auth/accounts');
    return r.data.accounts;
  },

  /**
   * Switch the active tenant.  Stores the re-minted bearer token and returns
   * it; the caller typically reloads so all data refetches under the new
   * tenant scope.
   */
  async switch(tenantId: string | null): Promise<void> {
    const r = await axiosInstance.post<{ Authorization: string }>(
      '/api/auth/switch-account',
      { tenant_id: tenantId },
    );
    if (r.data?.Authorization) {
      localStorage.setItem('bearer_token', r.data.Authorization);
    }
  },
};
