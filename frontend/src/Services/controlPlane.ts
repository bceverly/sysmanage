/**
 * Client for the multi-tenancy control-plane API (Phase 13.1).
 *
 * Backs the Tenant Management page.  Every route lives under
 * ``/api/control-plane`` and requires a bearer token (attached by the shared
 * axios interceptor).  The control plane is only meaningful when
 * ``multitenancy.enabled`` is true on the server — callers gate the UI on
 * ``getStatus().multitenancy_enabled``.
 */

import axiosInstance from './api';

export interface ControlPlaneStatus {
  multitenancy_enabled: boolean;
  tenant_count: number;
  self_service_provisioning?: boolean;
  provisioner_configured?: boolean;
}

export interface EnrollmentTokenSummary {
  id: string;
  tenant_id: string;
  label?: string | null;
  created_at?: string | null;
  expires_at?: string | null;
  max_uses?: number | null;
  use_count: number;
  last_used_at?: string | null;
  revoked: boolean;
}

export interface CreateEnrollmentTokenResponse {
  token: string;
  summary: EnrollmentTokenSummary;
}

export interface AutoProvisionResponse {
  tenant_id: string;
  dbname: string;
  openbao_role: string;
  revision?: string | null;
  status: string;
}

export interface TenantSummary {
  id: string;
  name: string;
  slug: string;
  status: string;
}

export interface UserSummary {
  id: string;
  email: string;
  is_active: boolean;
}

export interface GrantSummary {
  id: string;
  user_id: string;
  tenant_id: string;
  role: string;
  is_default: boolean;
  expires_at?: string | null;
}

export interface EmailDomainSummary {
  id: string;
  tenant_id: string;
  domain: string;
}

export interface PlacementSummary {
  tenant_id: string;
  host?: string | null;
  port?: number | null;
  dbname?: string | null;
  region?: string | null;
  tier: string;
  openbao_role?: string | null;
}

export interface ProvisionResponse {
  tenant_id: string;
  revision?: string | null;
  status: string;
}

export const controlPlaneService = {
  // --- Status -------------------------------------------------------------
  async getStatus(): Promise<ControlPlaneStatus> {
    const r = await axiosInstance.get<ControlPlaneStatus>(
      '/api/control-plane/status',
    );
    return r.data;
  },

  // --- Tenants ------------------------------------------------------------
  async listTenants(status?: string): Promise<TenantSummary[]> {
    const r = await axiosInstance.get<{ tenants: TenantSummary[]; total: number }>(
      '/api/control-plane/tenants',
      { params: status ? { status } : undefined },
    );
    return r.data.tenants;
  },

  async createTenant(name: string, slug: string): Promise<TenantSummary> {
    const r = await axiosInstance.post<TenantSummary>(
      '/api/control-plane/tenants',
      { name, slug },
    );
    return r.data;
  },

  // --- Users --------------------------------------------------------------
  async listUsers(email?: string): Promise<UserSummary[]> {
    const r = await axiosInstance.get<UserSummary[]>('/api/control-plane/users', {
      params: email ? { email } : undefined,
    });
    return r.data;
  },

  async createUser(email: string): Promise<UserSummary> {
    const r = await axiosInstance.post<UserSummary>('/api/control-plane/users', {
      email,
    });
    return r.data;
  },

  /**
   * Resolve a user id by email, creating the global identity if it doesn't
   * exist yet.  Backs the "add member by email" flow.
   */
  async ensureUser(email: string): Promise<UserSummary> {
    const existing = await this.listUsers(email);
    if (existing.length > 0) {
      return existing[0];
    }
    return this.createUser(email);
  },

  // --- Grants -------------------------------------------------------------
  async listGrants(params?: {
    user_id?: string;
    tenant_id?: string;
  }): Promise<GrantSummary[]> {
    const r = await axiosInstance.get<GrantSummary[]>(
      '/api/control-plane/grants',
      { params },
    );
    return r.data;
  },

  async createGrant(payload: {
    user_id: string;
    tenant_id: string;
    role?: string;
    is_default?: boolean;
    expires_at?: string | null;
  }): Promise<GrantSummary> {
    const r = await axiosInstance.post<GrantSummary>(
      '/api/control-plane/grants',
      payload,
    );
    return r.data;
  },

  async deleteGrant(grantId: string): Promise<void> {
    await axiosInstance.delete(`/api/control-plane/grants/${grantId}`);
  },

  // --- Email-domain allowlist --------------------------------------------
  async listEmailDomains(tenantId: string): Promise<EmailDomainSummary[]> {
    const r = await axiosInstance.get<EmailDomainSummary[]>(
      `/api/control-plane/tenants/${tenantId}/email-domains`,
    );
    return r.data;
  },

  async addEmailDomain(
    tenantId: string,
    domain: string,
  ): Promise<EmailDomainSummary> {
    const r = await axiosInstance.post<EmailDomainSummary>(
      `/api/control-plane/tenants/${tenantId}/email-domains`,
      { domain },
    );
    return r.data;
  },

  async deleteEmailDomain(tenantId: string, domainId: string): Promise<void> {
    await axiosInstance.delete(
      `/api/control-plane/tenants/${tenantId}/email-domains/${domainId}`,
    );
  },

  // --- Placement + provisioning ------------------------------------------
  async getPlacement(tenantId: string): Promise<PlacementSummary | null> {
    try {
      const r = await axiosInstance.get<PlacementSummary>(
        `/api/control-plane/tenants/${tenantId}/placement`,
      );
      return r.data;
    } catch (err: unknown) {
      // 404 = no placement set yet; surface as null rather than throwing.
      if (
        typeof err === 'object' &&
        err !== null &&
        'response' in err &&
        (err as { response?: { status?: number } }).response?.status === 404
      ) {
        return null;
      }
      throw err;
    }
  },

  async upsertPlacement(
    tenantId: string,
    payload: {
      host?: string | null;
      port?: number | null;
      dbname?: string | null;
      region?: string | null;
      tier: string;
      openbao_role?: string | null;
    },
  ): Promise<PlacementSummary> {
    const r = await axiosInstance.put<PlacementSummary>(
      `/api/control-plane/tenants/${tenantId}/placement`,
      payload,
    );
    return r.data;
  },

  async provisionTenant(tenantId: string): Promise<ProvisionResponse> {
    const r = await axiosInstance.post<ProvisionResponse>(
      `/api/control-plane/tenants/${tenantId}/provision`,
      {},
    );
    return r.data;
  },

  // Destructive: tears down OpenBAO role/config + registry rows, optionally
  // drops the database.  Requires the tenant slug as confirmation.
  async deleteTenant(
    tenantId: string,
    opts: { confirm: string; dropDatabase: boolean },
  ): Promise<Record<string, unknown>> {
    const r = await axiosInstance.delete<Record<string, unknown>>(
      `/api/control-plane/tenants/${tenantId}`,
      { data: { confirm: opts.confirm, drop_database: opts.dropDatabase } },
    );
    return r.data;
  },

  // --- Enrollment tokens (agent→tenant binding) --------------------------
  async listEnrollmentTokens(
    tenantId: string,
  ): Promise<EnrollmentTokenSummary[]> {
    const r = await axiosInstance.get<EnrollmentTokenSummary[]>(
      `/api/control-plane/tenants/${tenantId}/enrollment-tokens`,
    );
    return r.data;
  },

  async createEnrollmentToken(
    tenantId: string,
    opts: { label?: string; expiresInDays?: number | null; maxUses?: number | null },
  ): Promise<CreateEnrollmentTokenResponse> {
    const r = await axiosInstance.post<CreateEnrollmentTokenResponse>(
      `/api/control-plane/tenants/${tenantId}/enrollment-tokens`,
      {
        label: opts.label || null,
        expires_in_days: opts.expiresInDays ?? null,
        max_uses: opts.maxUses ?? null,
      },
    );
    return r.data;
  },

  async revokeEnrollmentToken(tenantId: string, tokenId: string): Promise<void> {
    await axiosInstance.delete(
      `/api/control-plane/tenants/${tenantId}/enrollment-tokens/${tokenId}`,
    );
  },

  // Self-service: server creates the DB + OpenBAO role + placement + migrates.
  async autoProvision(
    tenantId: string,
    opts?: {
      host?: string | null;
      port?: number | null;
      region?: string | null;
      tier?: string;
    },
  ): Promise<AutoProvisionResponse> {
    const r = await axiosInstance.post<AutoProvisionResponse>(
      `/api/control-plane/tenants/${tenantId}/auto-provision`,
      opts ?? {},
    );
    return r.data;
  },
};
