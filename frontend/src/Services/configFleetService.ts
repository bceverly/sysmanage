// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

/**
 * Fleet-scale configuration management and remediation playbooks (Phase 20.1).
 *
 * Its own module rather than more of `configManagementService`, which is
 * already near this project's 1000-line file ceiling. The seam is real: that
 * file is about one host at a time, this one is about thousands.
 */

import axiosInstance from "./api";

const BASE = "/api/v1/config-management";

// --- inventories -------------------------------------------------------------

/**
 * A named, reusable set of hosts.
 *
 * `host_count` is resolved by the server on every read rather than stored, so
 * it is right after a host is tagged, retired or added. A cached count on a
 * launch screen is wrong in the way people only notice afterwards.
 */
export interface ConfigInventory {
  id: string;
  name: string;
  description: string | null;
  all_hosts: boolean;
  host_count: number | null;
  created_by: string | null;
  updated_by: string | null;
  created_at: string | null;
  updated_at: string | null;
}

/** One selector in an inventory. Exactly one of the three ids is set. */
export interface ConfigInventoryMember {
  id: string;
  inventory_id: string;
  host_id: string | null;
  tag_id: string | null;
  site_id: string | null;
  created_at: string | null;
}

export const getInventories = async (): Promise<ConfigInventory[]> => {
  const response = await axiosInstance.get<ConfigInventory[]>(`${BASE}/inventories`);
  return response.data;
};

export const createInventory = async (payload: {
  name: string;
  description?: string | null;
  all_hosts?: boolean;
}): Promise<ConfigInventory> => {
  const response = await axiosInstance.post<ConfigInventory>(
    `${BASE}/inventories`,
    payload,
  );
  return response.data;
};

export const updateInventory = async (
  inventoryId: string,
  payload: { name?: string; description?: string | null; all_hosts?: boolean },
): Promise<ConfigInventory> => {
  const response = await axiosInstance.put<ConfigInventory>(
    `${BASE}/inventories/${inventoryId}`,
    payload,
  );
  return response.data;
};

export const deleteInventory = async (inventoryId: string): Promise<void> => {
  await axiosInstance.delete(`${BASE}/inventories/${inventoryId}`);
};

export const getInventoryMembers = async (
  inventoryId: string,
): Promise<ConfigInventoryMember[]> => {
  const response = await axiosInstance.get<ConfigInventoryMember[]>(
    `${BASE}/inventories/${inventoryId}/members`,
  );
  return response.data;
};

export const addInventoryMember = async (
  inventoryId: string,
  payload: { host_id?: string; tag_id?: string; site_id?: string },
): Promise<ConfigInventoryMember> => {
  const response = await axiosInstance.post<ConfigInventoryMember>(
    `${BASE}/inventories/${inventoryId}/members`,
    payload,
  );
  return response.data;
};

export const deleteInventoryMember = async (memberId: string): Promise<void> => {
  await axiosInstance.delete(`${BASE}/inventory-members/${memberId}`);
};

/**
 * The hostnames an inventory resolves to right now.
 *
 * The question an operator needs answered before launching against four
 * thousand machines, which is why resolution is never cached.
 */
export const previewInventory = async (
  inventoryId: string,
): Promise<string[]> => {
  const response = await axiosInstance.get<string[]>(
    `${BASE}/inventories/${inventoryId}/hosts`,
  );
  return response.data;
};

// --- job templates -----------------------------------------------------------

/**
 * A profile plus an inventory plus how hard to run it.
 *
 * `concurrency` is what the server STORED, not what was typed: the engine
 * clamps it, so a request for 10,000 comes back as the ceiling. Rendering the
 * returned value is what tells an operator what they actually got.
 */
export interface ConfigJobTemplate {
  id: string;
  name: string;
  description: string | null;
  profile_id: string;
  inventory_id: string;
  check_mode: boolean;
  concurrency: number;
  timeout_seconds: number | null;
  schedule: string | null;
  enabled: boolean;
  created_by: string | null;
  updated_by: string | null;
  created_at: string | null;
  updated_at: string | null;
  last_launched_at: string | null;
}

export interface ConfigJobTemplateRequest {
  name: string;
  profile_id: string;
  inventory_id: string;
  description?: string | null;
  check_mode?: boolean;
  concurrency?: number | null;
  timeout_seconds?: number | null;
  schedule?: string | null;
  enabled?: boolean;
}

export const getJobTemplates = async (): Promise<ConfigJobTemplate[]> => {
  const response = await axiosInstance.get<ConfigJobTemplate[]>(
    `${BASE}/job-templates`,
  );
  return response.data;
};

export const createJobTemplate = async (
  payload: ConfigJobTemplateRequest,
): Promise<ConfigJobTemplate> => {
  const response = await axiosInstance.post<ConfigJobTemplate>(
    `${BASE}/job-templates`,
    payload,
  );
  return response.data;
};

export const updateJobTemplate = async (
  templateId: string,
  payload: Partial<ConfigJobTemplateRequest>,
): Promise<ConfigJobTemplate> => {
  const response = await axiosInstance.put<ConfigJobTemplate>(
    `${BASE}/job-templates/${templateId}`,
    payload,
  );
  return response.data;
};

export const deleteJobTemplate = async (templateId: string): Promise<void> => {
  await axiosInstance.delete(`${BASE}/job-templates/${templateId}`);
};

export const launchJobTemplate = async (
  templateId: string,
): Promise<ConfigJob> => {
  const response = await axiosInstance.post<ConfigJob>(
    `${BASE}/job-templates/${templateId}/launch`,
    {},
  );
  return response.data;
};

// --- jobs --------------------------------------------------------------------

/**
 * One fan-out of a profile across an inventory.
 *
 * `status` answers "did this job do its work", NOT "is every host happy" --
 * the counts answer that. A job with a handful of failures on a fleet of
 * thousands is `completed`, deliberately: a status that goes red every time is
 * ignored within a week.
 */
export interface ConfigJob {
  id: string;
  template_id: string | null;
  template_name: string | null;
  profile_id: string | null;
  profile_name: string | null;
  inventory_name: string | null;
  status: string;
  check_mode: boolean;
  concurrency: number;
  total_targets: number;
  succeeded_count: number;
  failed_count: number;
  skipped_count: number;
  outstanding_count: number;
  requested_by: string | null;
  detail: string | null;
  created_at: string | null;
  started_at: string | null;
  finished_at: string | null;
}

/** One host within a job, and what became of it. */
export interface ConfigJobTarget {
  id: string;
  job_id: string;
  host_id: string | null;
  host_fqdn: string | null;
  status: string;
  command_id: string | null;
  run_id: string | null;
  detail: string | null;
  queued_at: string | null;
  finished_at: string | null;
}

export const getJobs = async (limit = 25): Promise<ConfigJob[]> => {
  const response = await axiosInstance.get<ConfigJob[]>(`${BASE}/jobs`, {
    params: { limit },
  });
  return response.data;
};

export const getJob = async (jobId: string): Promise<ConfigJob> => {
  const response = await axiosInstance.get<ConfigJob>(`${BASE}/jobs/${jobId}`);
  return response.data;
};

export const getJobTargets = async (
  jobId: string,
  limit = 100,
): Promise<ConfigJobTarget[]> => {
  const response = await axiosInstance.get<ConfigJobTarget[]>(
    `${BASE}/jobs/${jobId}/targets`,
    { params: { limit } },
  );
  return response.data;
};

export const cancelJob = async (
  jobId: string,
  reason?: string,
): Promise<ConfigJob> => {
  const response = await axiosInstance.post<ConfigJob>(
    `${BASE}/jobs/${jobId}/cancel`,
    { reason: reason ?? null },
  );
  return response.data;
};

// --- remediation playbooks ---------------------------------------------------

/**
 * A binding from a drift finding to the profile that repairs it.
 *
 * The playbook itself is an ordinary `ConfigProfile` -- only the binding is
 * new, which is why there is no separate authoring surface for one.
 */
export interface ConfigRemediationRule {
  id: string;
  name: string;
  description: string | null;
  /** Narrows the rule to drift from one profile. Null means any. */
  profile_id: string | null;
  profile_name: string | null;
  /** A glob matched against the finding's task name, case-insensitively. */
  task_pattern: string;
  remediation_profile_id: string;
  remediation_profile_name: string | null;
  enabled: boolean;
  /** Lowest number wins. Ties break toward the profile-scoped rule. */
  priority: number;
  /** Whether the drift reconciler may fire this without an operator. */
  auto_apply: boolean;
  created_by: string | null;
  updated_by: string | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface ConfigRemediationRuleRequest {
  name: string;
  task_pattern: string;
  remediation_profile_id: string;
  description?: string | null;
  profile_id?: string | null;
  enabled?: boolean;
  priority?: number;
  auto_apply?: boolean;
}

/**
 * What would repair one finding.
 *
 * Three distinguishable answers, because they send an operator to three
 * different places: nothing matched (write a rule), a rule matched but its
 * profile is retired (turn it back on), or here is what will run.
 */
export interface ConfigRemediationMatch {
  finding_id: string;
  matched: boolean;
  unavailable: boolean;
  rule_id: string | null;
  rule_name: string | null;
  remediation_profile_id: string | null;
  remediation_profile_name: string | null;
  preview: Record<string, unknown> | null;
}

export interface ConfigRepairResult {
  finding_id: string;
  host_id: string;
  profile_id: string;
  profile_name: string | null;
  queued: boolean;
  message: string;
}

export const getRemediationRules = async (): Promise<ConfigRemediationRule[]> => {
  const response = await axiosInstance.get<ConfigRemediationRule[]>(
    `${BASE}/remediation-rules`,
  );
  return response.data;
};

export const createRemediationRule = async (
  payload: ConfigRemediationRuleRequest,
): Promise<ConfigRemediationRule> => {
  const response = await axiosInstance.post<ConfigRemediationRule>(
    `${BASE}/remediation-rules`,
    payload,
  );
  return response.data;
};

export const updateRemediationRule = async (
  ruleId: string,
  payload: Partial<ConfigRemediationRuleRequest>,
): Promise<ConfigRemediationRule> => {
  const response = await axiosInstance.put<ConfigRemediationRule>(
    `${BASE}/remediation-rules/${ruleId}`,
    payload,
  );
  return response.data;
};

export const deleteRemediationRule = async (ruleId: string): Promise<void> => {
  await axiosInstance.delete(`${BASE}/remediation-rules/${ruleId}`);
};

/** What would repair this finding, without doing it. */
export const getFindingRemediation = async (
  findingId: string,
): Promise<ConfigRemediationMatch> => {
  const response = await axiosInstance.get<ConfigRemediationMatch>(
    `${BASE}/drift/findings/${findingId}/remediation`,
  );
  return response.data;
};

/** Apply the matched playbook to the host this finding is on. */
export const repairFinding = async (
  findingId: string,
): Promise<ConfigRepairResult> => {
  const response = await axiosInstance.post<ConfigRepairResult>(
    `${BASE}/drift/findings/${findingId}/remediate`,
    {},
  );
  return response.data;
};
