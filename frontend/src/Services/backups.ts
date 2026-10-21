// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

// Fleet backup with restate (Phase 24, Community).  Hosts capture into their
// own repository on the target and NEVER prune; the target's storage host
// seals each capture (a ZFS snapshot or a read-only btrfs snapshot) and only
// then prunes; it also checks the repository.  Restores always land in the agent's staging directory.

import axiosInstance from "./api";

export type BackupStatus =
  | "ok"
  | "incomplete"
  | "overdue"
  | "failed"
  | "running"
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
  "running",
  "disabled",
  "ok",
  "no_policy",
];

export type Coverage = "full" | "files_only" | "unsupported";
export type SealMode = "none" | "zfs_snapshot" | "btrfs_snapshot";
/** Worst first, as the server orders them. */
export type TargetWarning =
  | "no_storage_host"
  | "storage_not_equipped"
  | "seal_fs_mismatch"
  | "btrfs_not_subvolume"
  | "seal_stale"
  | "prune_stale"
  | "check_stale"
  | "not_sealed"
  | "fs_cannot_snapshot"
  | "fs_unchecked";

/** What the storage host last reported about the filesystem under the
 *  storage path; every field null until it has. */
export interface StorageFilesystem {
  type: string | null;
  mount_point: string | null;
  btrfs_subvolume: boolean | null;
  checked_at: string | null;
}

export interface StorageRunBrief {
  status: string;
  finished_at: string | null;
  message: string | null;
}

/** The storage side, when the storage host can run restate. */
export interface StorageStatus {
  policies: number;
  confirmed: number;
  last_seal: StorageRunBrief | null;
  last_prune: StorageRunBrief | null;
  last_check: StorageRunBrief | null;
  /** Host ids whose repository is behind on each storage job. */
  stale: Record<"seal_stale" | "prune_stale" | "check_stale", string[]>;
}

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
  btrfs_snapshot_dir: string | null;
  storage_fs: StorageFilesystem;
  storage_status: StorageStatus | null;
  warnings: TargetWarning[];
  /** The target counts once on the dashboard's overdue-or-failed card. */
  problem: boolean;
}

export interface TargetInput {
  name: string;
  host_mount_point: string;
  storage_host_id: string | null;
  storage_path: string | null;
  max_concurrent: number;
  seal_mode: SealMode;
  zfs_dataset: string | null;
  btrfs_snapshot_dir: string | null;
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
  /** restate path patterns kept although the built-in rules leave them out. */
  keep_paths: string[];
  /** restate path patterns left out of the backup (they win over keeps). */
  skip_paths: string[];
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
  | "keep_paths"
  | "skip_paths"
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
  /** The newest capture that produced a snapshot (ok, different, incomplete). */
  last_good_capture: BackupRun | null;
  last_check: BackupRun | null;
  running: BackupRun | null;
  /** A bulk "Back up now" waiting for a free slot under the target's cap. */
  capture_requested: boolean;
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

export interface BulkBackupResult {
  requested: number;
  started: number;
  waiting: number;
  skipped: { host_id: string; fqdn: string | null; reason: string }[];
}

/** "Back up now" for many hosts: started as the target's cap allows. */
export const bulkBackupNow = async (hostIds: string[]): Promise<BulkBackupResult> =>
  (await axiosInstance.post<BulkBackupResult>(`${base}/backups/backup-now`, { host_ids: hostIds })).data;

/** Clear the Recent jobs list: finished jobs leave it (none are deleted). */
export const clearRuns = async (): Promise<{ cleared: number }> =>
  (await axiosInstance.post<{ cleared: number }>(`${base}/backups/runs/clear`)).data;

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
