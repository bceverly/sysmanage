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
): Promise<ConfigMgmtPrereqInstallResult> => {
  const response = await axiosInstance.post<ConfigMgmtPrereqInstallResult>(
    `/api/v1/hosts/${hostId}/config-management/prerequisite/install`,
  );
  return response.data;
};
