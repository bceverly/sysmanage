// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

import axiosInstance from "./api";

/**
 * Readiness of a host to run Phase 20.1 config-management profiles.
 *
 * `status` is deliberately five-valued rather than a boolean, because the
 * reasons a host is not ready are not interchangeable:
 *
 *   satisfied     the executor is installed and new enough
 *   not_required  Windows -- dsc.exe ships with the agent, nothing to install
 *   missing       supported platform, executor absent, button will work
 *   too_old       present but below the minimum, button offers the upgrade
 *   unsupported   no measured install path here; offering a button would lie
 */
export type ConfigMgmtPrereqStatus =
  "satisfied" | "not_required" | "missing" | "too_old" | "unsupported";

export interface ConfigMgmtPrereq {
  host_id: string;
  executor: string;
  status: ConfigMgmtPrereqStatus;
  installed_version: string | null;
  minimum_version: string | null;
  can_install: boolean;
  detail: string | null;
  package_name: string | null;
}

export interface ConfigMgmtPrereqInstallResult {
  host_id: string;
  queued: boolean;
  message: string;
}

export const getConfigMgmtPrereq = async (
  hostId: string,
): Promise<ConfigMgmtPrereq> => {
  const response = await axiosInstance.get<ConfigMgmtPrereq>(
    `/api/v1/hosts/${hostId}/config-management/prerequisite`,
  );
  return response.data;
};

export const installConfigMgmtPrereq = async (
  hostId: string,
  engine?: string,
): Promise<ConfigMgmtPrereqInstallResult> => {
  // The engine is explicit: without it the server installs the platform
  // default, so every row's Install button would install ansible-core.
  const query = engine ? `?engine=${encodeURIComponent(engine)}` : "";
  const response = await axiosInstance.post<ConfigMgmtPrereqInstallResult>(
    `/api/v1/hosts/${hostId}/config-management/prerequisite/install${query}`,
  );
  return response.data;
};

/** One recorded application of a profile to a host. */
export interface ConfigProfileRun {
  id: string;
  host_id: string;
  profile_id: string | null;
  profile_name: string | null;
  executor: string | null;
  check_mode: boolean;
  success: boolean;
  changed: boolean;
  exit_code: number | null;
  tasks_ok: number;
  tasks_changed: number;
  tasks_failed: number;
  tasks_skipped: number;
  tasks_unreachable: number;
  reason: string | null;
  completed_at: string | null;
}

export interface ConfigProfileRunTask {
  host?: string | null;
  task?: string | null;
  status?: string | null;
  changed?: boolean;
  msg?: string | null;
}

export interface ConfigProfileRunDetail extends ConfigProfileRun {
  tasks: ConfigProfileRunTask[];
  error_output: string | null;
}

/**
 * Recent runs for a host, newest first.
 *
 * Unchanged runs are included deliberately: the thing an operator looks for is
 * the quiet streak that means the host has converged, and filtering no-ops out
 * as uninteresting would hide exactly that.
 */
export const getConfigProfileRuns = async (
  hostId: string,
  limit = 25,
): Promise<ConfigProfileRun[]> => {
  const response = await axiosInstance.get<ConfigProfileRun[]>(
    `/api/v1/hosts/${hostId}/config-management/runs?limit=${limit}`,
  );
  return response.data;
};

export const getConfigProfileRun = async (
  runId: string,
): Promise<ConfigProfileRunDetail> => {
  const response = await axiosInstance.get<ConfigProfileRunDetail>(
    `/api/v1/config-management/runs/${runId}`,
  );
  return response.data;
};

export interface ConfigProfileApplyRequest {
  engine?: string;
  playbook?: string;
  resources?: Record<string, unknown>[];
  profile_name?: string;
  check_mode?: boolean;
}

export interface ConfigProfileApplyResult {
  host_id: string;
  queued: boolean;
  check_mode: boolean;
  message: string;
}

/**
 * Queue an ad-hoc configuration profile for one host.
 *
 * The server decides which field a host's executor wants and rejects the wrong
 * one with a 400 naming the right field, so callers should surface the
 * server's detail rather than guessing.
 */
export const applyConfigProfile = async (
  hostId: string,
  request: ConfigProfileApplyRequest,
): Promise<ConfigProfileApplyResult> => {
  const response = await axiosInstance.post<ConfigProfileApplyResult>(
    `/api/v1/hosts/${hostId}/config-management/apply`,
    request,
  );
  return response.data;
};

/** Readiness of one engine on one host. */
export interface ConfigMgmtEngineStatus {
  engine: string;
  status: ConfigMgmtPrereqStatus;
  installed_version: string | null;
  minimum_version: string | null;
  can_install: boolean;
  detail: string | null;
  package_name: string | null;
  /** Puppet/Salt/Chef: supported, but only with an Enterprise licence. */
  requires_license: boolean;
}

export interface ConfigMgmtEngines {
  host_id: string;
  default_engine: string;
  engines: ConfigMgmtEngineStatus[];
}

/**
 * Every engine that could run on a host, readiest first.
 *
 * Returns a list rather than one executor because a host may have several
 * installed and the profile picks which applies. Licensed engines are included
 * with `requires_license` set rather than omitted: hiding them would tell a
 * Puppet shop that Puppet is unsupported when it is actually a paid adapter.
 */
export const getConfigMgmtEngines = async (
  hostId: string,
): Promise<ConfigMgmtEngines> => {
  const response = await axiosInstance.get<ConfigMgmtEngines>(
    `/api/v1/hosts/${hostId}/config-management/engines`,
  );
  return response.data;
};
