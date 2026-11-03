// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

// Backup policies by tag (Pro+ backup_engine, ROADMAP 24.6): a template that
// gives every host carrying a tag its backup settings.  The lowest priority
// wins where several cover a host; a host's own policy (Configure) beats
// them all.  The server answers 402 without the engine.

import axiosInstance from './api';
import type { PolicyInput } from './backups';

const base = '/api/v1';

export interface TagPolicy {
  id: string;
  name: string;
  tag_id: string;
  tag_name: string | null;
  priority: number;
  enabled: boolean;
  settings: PolicyInput;
  /** Hosts carrying the tag, and hosts whose policy comes from this one. */
  hosts_tagged: number;
  hosts_applied: number;
  created_at: string | null;
  created_by: string | null;
  updated_at: string | null;
}

export interface TagPolicyInput {
  name: string;
  tag_id: string;
  priority: number;
  enabled: boolean;
  settings: PolicyInput;
}

export interface TagPolicyOutcome {
  applied: { host_id: string; fqdn: string; tag_policy: string }[];
  unchanged: number;
  removed: { host_id: string; fqdn: string | null }[];
  skipped: { host_id: string; fqdn: string | null; reason: string }[];
}

export interface HostTag {
  id: string;
  name: string;
}

export const listTagPolicies = async (): Promise<TagPolicy[]> =>
  (await axiosInstance.get<{ tag_policies: TagPolicy[] }>(`${base}/backups/tag-policies`)).data
    .tag_policies;

export const createTagPolicy = async (
  input: TagPolicyInput,
): Promise<{ tag_policy: TagPolicy; applied: TagPolicyOutcome }> =>
  (await axiosInstance.post(`${base}/backups/tag-policies`, input)).data;

export const updateTagPolicy = async (
  id: string,
  input: TagPolicyInput,
): Promise<{ tag_policy: TagPolicy; applied: TagPolicyOutcome }> =>
  (await axiosInstance.put(`${base}/backups/tag-policies/${id}`, input)).data;

export const deleteTagPolicy = async (id: string): Promise<{ applied: TagPolicyOutcome }> =>
  (await axiosInstance.delete(`${base}/backups/tag-policies/${id}`)).data;

export const applyTagPolicies = async (): Promise<TagPolicyOutcome> =>
  (await axiosInstance.post<TagPolicyOutcome>(`${base}/backups/tag-policies/apply`)).data;

export const listHostTags = async (): Promise<HostTag[]> => {
  const data = (await axiosInstance.get(`${base}/tags`)).data;
  const rows: unknown[] = Array.isArray(data) ? data : (data?.tags ?? []);
  return rows
    .filter((row): row is HostTag => typeof row === 'object' && row !== null && 'id' in row && 'name' in row)
    .map(row => ({ id: String(row.id), name: String(row.name) }));
};
