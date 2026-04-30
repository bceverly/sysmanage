import axiosInstance from './api.js';

export const LEASE_KINDS = ['token', 'database', 'ssh'] as const;
export type LeaseKind = typeof LEASE_KINDS[number];

export const LEASE_STATUSES = ['ACTIVE', 'REVOKED', 'EXPIRED', 'FAILED'] as const;
export type LeaseStatus = typeof LEASE_STATUSES[number];

export interface DynamicSecretLease {
  id: string;
  name: string;
  kind: LeaseKind;
  backend_role: string;
  vault_lease_id: string | null;
  ttl_seconds: number | null;
  issued_at: string | null;
  expires_at: string | null;
  revoked_at: string | null;
  status: LeaseStatus;
  secret_metadata: Record<string, unknown>;
  note: string | null;
}

export interface IssueRequest {
  name: string;
  kind: LeaseKind;
  backend_role: string;
  ttl_seconds: number;
  note?: string | null;
}

export interface IssueResponse {
  lease: DynamicSecretLease;
  // Plaintext value — surfaced exactly once.
  secret: string;
}

export interface KindCatalog {
  kinds: Array<{ kind: LeaseKind; label: string }>;
  ttl: { min: number; max: number; default: number };
}

export const dynamicSecretsService = {
  async list(filter?: { status?: LeaseStatus; kind?: LeaseKind }): Promise<DynamicSecretLease[]> {
    const params: Record<string, string> = {};
    if (filter?.status) params.status = filter.status;
    if (filter?.kind) params.kind = filter.kind;
    const r = await axiosInstance.get('/api/dynamic-secrets/leases', { params });
    return r.data;
  },

  async get(id: string): Promise<DynamicSecretLease> {
    const r = await axiosInstance.get(`/api/dynamic-secrets/leases/${id}`);
    return r.data;
  },

  async issue(payload: IssueRequest): Promise<IssueResponse> {
    const r = await axiosInstance.post('/api/dynamic-secrets/issue', payload);
    return r.data;
  },

  async revoke(id: string): Promise<{ lease: DynamicSecretLease; vault_revoked: boolean }> {
    const r = await axiosInstance.post(`/api/dynamic-secrets/leases/${id}/revoke`);
    return r.data;
  },

  async reconcile(): Promise<{ transitioned_count: number }> {
    const r = await axiosInstance.post('/api/dynamic-secrets/reconcile');
    return r.data;
  },

  async kinds(): Promise<KindCatalog> {
    const r = await axiosInstance.get('/api/dynamic-secrets/kinds');
    return r.data;
  },
};
