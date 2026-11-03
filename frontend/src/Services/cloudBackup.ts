// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

// iCloud Photos to local (ROADMAP 24.12, Community).  Runs on the backup
// target's storage host only.  An account's password goes to the server once,
// which puts it in OpenBAO; it never comes back.

import axiosInstance from "./api";

export type CloudAccountStatus =
  | "new"
  | "ok"
  | "running"
  | "waiting_code"
  | "needs_sign_in"
  | "failed";

export interface CloudRun {
  id: string;
  account_id: string | null;
  action: "enable" | "connect" | "download" | "reconcile" | "libraries" | "remove";
  status: "queued" | "running" | "waiting_code" | "ok" | "failed" | "needs_sign_in";
  queued_at: string | null;
  started_at: string | null;
  finished_at: string | null;
  requested_by: string | null;
  progress: { phase?: string; downloaded?: number | null; present?: number | null; failed?: number | null; line?: string | null } | null;
  message: string | null;
  reason: string | null;
  detail: string | null;
  duration: number | null;
  exit_code: number | null;
  downloaded: number | null;
  present: number | null;
  failed: number | null;
  bytes: number | null;
  waiting_code: boolean;
}

export interface CloudAccount {
  id: string;
  provider: string;
  apple_id: string;
  display_name: string;
  library: string;
  libraries: string[];
  password_set: boolean;
  password_set_at: string | null;
  dir_name: string;
  enabled: boolean;
  interval_hours: number;
  window_start_hour: number | null;
  until_found: number;
  auto_delete: boolean;
  status: CloudAccountStatus;
  state_message: string | null;
  session_created_at: string | null;
  session_expires_at: string | null;
  session_expiring: boolean;
  last_good_at: string | null;
  last_full_at: string | null;
  photos_local: number | null;
  bytes_local: number | null;
  run_requested: boolean;
  current_run: CloudRun | null;
  last_run: CloudRun | null;
  created_at: string | null;
}

export interface CloudEnable {
  status: "running" | "ok" | "failed";
  reason: string | null;
  detail: string | null;
  tool_version: string | null;
  install_method: string | null;
  cloud_root: string | null;
  requested_by: string | null;
  requested_at: string | null;
  finished_at: string | null;
}

export interface CloudOverview {
  available: boolean;
  reason?: string;
  target?: { id: string; name: string; storage_path: string | null } | null;
  storage_host?: { id: string; fqdn: string } | null;
  support?: { supported: boolean | null; reason: string | null };
  enable?: CloudEnable | null;
  enabled?: boolean;
  accounts: CloudAccount[];
}

export interface CloudSummary {
  enabled: boolean;
  accounts: number;
  ok: number;
  running: number;
  needs_sign_in: number;
  failed: number;
  expiring: number;
}

export interface CloudAccountSettings {
  display_name: string;
  library: string;
  enabled: boolean;
  interval_hours: number;
  window_start_hour: number | null;
  until_found: number;
  auto_delete: boolean;
  acknowledge_auto_delete: boolean;
}

export interface CloudAccountCreate extends CloudAccountSettings {
  apple_id: string;
  password: string;
}

export interface CloudAccountUpdate extends CloudAccountSettings {
  /** Only when it changes; omitted keeps the one in OpenBAO. */
  password?: string;
}

const base = "/api/v1/backups/cloud";

export const getCloudOverview = async (): Promise<CloudOverview> =>
  (await axiosInstance.get<CloudOverview>(base)).data;

export const getCloudSummary = async (): Promise<CloudSummary> =>
  (await axiosInstance.get<CloudSummary>(`${base}/summary`)).data;

export const getCloudRuns = async (accountId?: string): Promise<CloudRun[]> =>
  (await axiosInstance.get<{ runs: CloudRun[] }>(`${base}/runs`, {
    params: accountId ? { account_id: accountId } : {},
  })).data.runs;

export const enableCloudBackup = async (): Promise<CloudOverview> =>
  (await axiosInstance.post<CloudOverview>(`${base}/enable`)).data;

export const createCloudAccount = async (body: CloudAccountCreate): Promise<CloudAccount> =>
  (await axiosInstance.post<CloudAccount>(`${base}/accounts`, body)).data;

export const updateCloudAccount = async (id: string, body: CloudAccountUpdate): Promise<CloudAccount> =>
  (await axiosInstance.put<CloudAccount>(`${base}/accounts/${id}`, body)).data;

export const deleteCloudAccount = async (id: string): Promise<void> => {
  await axiosInstance.delete(`${base}/accounts/${id}`);
};

export const connectCloudAccount = async (id: string): Promise<CloudRun> =>
  (await axiosInstance.post<CloudRun>(`${base}/accounts/${id}/connect`)).data;

export const listCloudLibraries = async (id: string): Promise<CloudRun> =>
  (await axiosInstance.post<CloudRun>(`${base}/accounts/${id}/libraries`)).data;

export const runCloudAccountNow = async (id: string): Promise<CloudAccount> =>
  (await axiosInstance.post<CloudAccount>(`${base}/accounts/${id}/run-now`)).data;

export const sendCloudCode = async (runId: string, code: string): Promise<CloudRun> =>
  (await axiosInstance.post<CloudRun>(`${base}/runs/${runId}/code`, { code })).data;
