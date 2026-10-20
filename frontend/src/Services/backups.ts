// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

// Fleet backup with restate (Phase 24, Community).  Hosts capture into their
// own repository on the target and NEVER prune; the target's storage host
// seals each capture (a ZFS snapshot) and only then prunes; it also checks
// the repository.  Restores always land in the agent's staging directory.

import axiosInstance from "./api";

export type BackupStatus =
  | "ok"
  | "incomplete"
  | "overdue"
  | "failed"
  | "never"
  | "not_equipped"
  | "disabled"
  | "no_policy";

/** Worst first -- the order the hosts table sorts by. */
export const BACKUP_STATUS_ORDER: BackupStatus[] = [
  "failed",
  "overdue",
  "incomplete",
  "not_equipped",
  "never",
  "disabled",
  "ok",
  "no_policy",
];

export type Coverage = "full" | "files_only" | "unsupported";
export type SealMode = "none" | "zfs_snapshot";
export type TargetWarning = "not_sealed" | "no_storage_host" | "storage_not_equipped";

export interface BackupTarget {
  id: string;
  name: string;
  host_mount_point: string;
  storage_host_id: string | null;
  storage_hostname: string | null;
  storage_path: string | null;
  storage_reason: string | null;
  max_concurrent: number;
  seal_mode: SealMode;
  zfs_dataset: string | null;
  warnings: TargetWarning[];
}

export interface TargetInput {
  name: string;
  host_mount_point: string;
  storage_host_id: string | null;
  storage_path: string | null;
  max_concurrent: number;
  seal_mode: SealMode;
  zfs_dataset: string | null;
}

export interface BackupPolicy {
  id: string;
  host_id: string;
  enabled: boolean;
  interval_hours: number;
  window_start_hour: number | null;
  keep_last: number;
  check_interval_days: number;
  quiesce: boolean;
  quiesce_with: string[];
  estimate_bytes: number | null;
  repository_bytes: number | null;
  configured: boolean;
  storage_configured: boolean;
  restate_version: string | null;
  storage_restate_version: string | null;
}

export type PolicyInput = Pick<
  BackupPolicy,
  | "enabled"
  | "interval_hours"
  | "window_start_hour"
  | "keep_last"
  | "check_interval_days"
  | "quiesce"
  | "quiesce_with"
>;

export interface BackupProgress {
  phase?: string | null;
  paths?: number | null;
  read_bytes?: number | null;
  new_bytes?: number | null;
  total_bytes?: number | null;
  hook?: string | null;
  at?: string | null;
}

export interface BackupRun {
  id: string;
  policy_id: string;
  host_id: string;
  action: string;
  status: string;
  exit_code: number | null;
  queued_at: string | null;
  started_at: string | null;
  finished_at: string | null;
  snapshot: string | null;
  message: string | null;
  restate_version: string | null;
  requested_by: string | null;
  progress: BackupProgress | null;
  result: Record<string, unknown> | null;
  /** For a check: ``verified`` only after a full read; a keyless check is
   *  ``metadata_check_passed`` and must never read as verified. */
  check_label: "verified" | "changed" | "metadata_check_passed" | "metadata_changed" | null;
  staging_path?: string;
}

export interface BackupHost {
  host_id: string;
  fqdn: string;
  platform: string | null;
  platform_release: string | null;
  equipped: boolean;
  reason: string | null;
  coverage: Coverage;
  policy: BackupPolicy | null;
  status: BackupStatus;
  last_capture: BackupRun | null;
  last_check: BackupRun | null;
  running: BackupRun | null;
  next_due: string | null;
  snapshot_count: number;
}

export interface BackupOverview {
  target: BackupTarget | null;
  hosts: BackupHost[];
  counts: Partial<Record<BackupStatus, number>>;
  restate_versions: string[];
}

export interface BackupSummary {
  configured: boolean;
  counts: Partial<Record<BackupStatus, number>>;
  attention: number;
  total: number;
}

export interface BackupSnapshot {
  id: string;
  name: string;
  created_at: string | null;
  bytes: number | null;
  new_bytes: number | null;
  unique_bytes: number | null;
  files: number | null;
  signed: boolean;
  gone_at: string | null;
}

export interface HostBackup extends BackupHost {
  target: BackupTarget | null;
}

export interface RestoreInput {
  snapshot: string;
  include: string[];
  exclude: string[];
  dry_run: boolean;
  acknowledge_unsigned: boolean;
}

const base = "/api/v1";

export const getBackupOverview = async (): Promise<BackupOverview> =>
  (await axiosInstance.get<BackupOverview>(`${base}/backups/overview`)).data;

export const getBackupSummary = async (): Promise<BackupSummary> =>
  (await axiosInstance.get<BackupSummary>(`${base}/backups/summary`)).data;

export const saveTarget = async (
  input: TargetInput,
  id?: string,
): Promise<BackupTarget> =>
  id
    ? (await axiosInstance.put<BackupTarget>(`${base}/backups/targets/${id}`, input)).data
    : (await axiosInstance.post<BackupTarget>(`${base}/backups/targets`, input)).data;

export const getHostBackup = async (hostId: string): Promise<HostBackup> =>
  (await axiosInstance.get<HostBackup>(`${base}/host/${hostId}/backup`)).data;

export const savePolicy = async (hostId: string, input: PolicyInput): Promise<BackupPolicy> =>
  (await axiosInstance.put<BackupPolicy>(`${base}/host/${hostId}/backup-policy`, input)).data;

export const deletePolicy = async (hostId: string): Promise<void> => {
  await axiosInstance.delete(`${base}/host/${hostId}/backup-policy`);
};

export const backupNow = async (hostId: string, action = "capture"): Promise<BackupRun> =>
  (await axiosInstance.post<BackupRun>(`${base}/host/${hostId}/backup-now`, { action })).data;

export const getRuns = async (
  params: { host_id?: string; action?: string; limit?: number; offset?: number } = {},
): Promise<{ total: number; runs: BackupRun[] }> =>
  (await axiosInstance.get<{ total: number; runs: BackupRun[] }>(`${base}/backups/runs`, { params }))
    .data;

export const getRun = async (runId: string): Promise<BackupRun> =>
  (await axiosInstance.get<BackupRun>(`${base}/backups/runs/${runId}`)).data;

export const getSnapshots = async (hostId: string): Promise<BackupSnapshot[]> =>
  (await axiosInstance.get<BackupSnapshot[]>(`${base}/host/${hostId}/backup-snapshots`)).data;

export const restoreFiles = async (hostId: string, input: RestoreInput): Promise<BackupRun> =>
  (await axiosInstance.post<BackupRun>(`${base}/host/${hostId}/backup-restore`, input)).data;
