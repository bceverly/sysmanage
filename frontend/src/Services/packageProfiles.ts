import axiosInstance from './api.js';

export const CONSTRAINT_TYPES = ['REQUIRED', 'BLOCKED'] as const;
export type ConstraintType = typeof CONSTRAINT_TYPES[number];

export const VERSION_OPS = ['=', '==', '>=', '<=', '>', '<', '!=', '~='] as const;
export type VersionOp = typeof VERSION_OPS[number];

export const COMPLIANCE_STATUSES = ['COMPLIANT', 'NON_COMPLIANT', 'PENDING'] as const;
export type ComplianceStatus = typeof COMPLIANCE_STATUSES[number];

export interface PackageConstraint {
  id?: string;
  package_name: string;
  package_manager: string | null;
  constraint_type: ConstraintType;
  version_op: VersionOp | null;
  version: string | null;
}

export interface PackageProfile {
  id: string;
  name: string;
  description: string | null;
  enabled: boolean;
  constraints?: PackageConstraint[];
  created_at: string | null;
  updated_at: string | null;
}

export interface PackageProfileCreate {
  name: string;
  description?: string | null;
  enabled?: boolean;
  constraints?: PackageConstraint[];
}

export type PackageProfileUpdate = Partial<PackageProfileCreate>;

export interface ComplianceViolation {
  package_name: string;
  reason: string;
  // Whatever extra fields the evaluator returns in the JSON blob.
  [key: string]: unknown;
}

export interface HostComplianceStatus {
  id: string;
  host_id: string;
  profile_id: string;
  status: ComplianceStatus;
  violations: ComplianceViolation[];
  last_scan_at: string | null;
}

export const packageProfilesService = {
  async list(): Promise<PackageProfile[]> {
    const r = await axiosInstance.get('/api/package-profiles');
    return r.data;
  },

  async get(id: string): Promise<PackageProfile> {
    const r = await axiosInstance.get(`/api/package-profiles/${id}`);
    return r.data;
  },

  async create(payload: PackageProfileCreate): Promise<PackageProfile> {
    const r = await axiosInstance.post('/api/package-profiles', payload);
    return r.data;
  },

  async update(id: string, payload: PackageProfileUpdate): Promise<PackageProfile> {
    const r = await axiosInstance.put(`/api/package-profiles/${id}`, payload);
    return r.data;
  },

  async remove(id: string): Promise<void> {
    await axiosInstance.delete(`/api/package-profiles/${id}`);
  },

  async scanHost(profileId: string, hostId: string): Promise<HostComplianceStatus> {
    const r = await axiosInstance.post(
      `/api/package-profiles/${profileId}/scan/${hostId}`,
    );
    return r.data;
  },

  async dispatchToAgent(profileId: string, hostId: string): Promise<{ status: string }> {
    const r = await axiosInstance.post(
      `/api/package-profiles/${profileId}/dispatch/${hostId}`,
    );
    return r.data;
  },

  async statusForHost(hostId: string): Promise<HostComplianceStatus[]> {
    const r = await axiosInstance.get(`/api/package-profiles/status/host/${hostId}`);
    return r.data;
  },
};
