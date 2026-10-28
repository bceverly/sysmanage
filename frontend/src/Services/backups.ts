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
  | "waiting_window"
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
  "waiting_window",
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
  | "fs_unchecked"
  | "storage_drive_failed"
  | "storage_drive_warning"
  | "storage_space_critical"
  | "storage_space_low"
  | `audit_${string}`;

/** One storage-audit finding summarized over the target's repositories. */
export interface StorageAuditEntry {
  level: "error" | "warning" | "ok";
  /** Affected hosts; empty for host-wide findings (the NFS baseline). */
  hosts: string[];
  params: Record<string, unknown>;
}

/** The storage host's own health: its drives and the space under the path. */
export interface StorageHealth {
  drives: { failed: string[]; warning: string[] };
  space: {
    mount_point: string;
    total_bytes: number;
    available_bytes: number;
    used_percent: number;
  } | null;
}

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
  /** Days the storage host keeps its seal snapshots (the newest always stays). */
  seal_keep_days?: number | null;
  /** Percent used at which the target warns, and warns critically (85 / 95). */
  space_low_percent?: number | null;
  space_critical_percent?: number | null;
  /** GB of restate write cache per host before it is flagged (20). */
  cache_budget_gb?: number | null;
  storage_fs: StorageFilesystem;
  storage_status: StorageStatus | null;
  storage_health?: StorageHealth | null;
  storage_audit?: Record<string, StorageAuditEntry>;
  service_account?: string;
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
  /** Days the storage host keeps its seal snapshots (the newest always stays). */
  seal_keep_days?: number | null;
  /** Percent used at which the target warns, and warns critically (85 / 95). */
  space_low_percent?: number | null;
  space_critical_percent?: number | null;
  service_account?: string | null;
  cache_budget_gb?: number | null;
}

export interface BackupPolicy {
  id: string;
  host_id: string;
  enabled: boolean;
  interval_hours: number;
  window_start_hour: number | null;
  keep_last: number;
  /** Grandfather-father-son (Pro+ to set, always honored): the newest
   *  snapshot of each of the last N days / ISO weeks / months; 0 = unused. */
  keep_daily?: number;
  keep_weekly?: number;
  keep_monthly?: number;
  check_interval_days: number;
  quiesce: boolean;
  quiesce_with: string[];
  /** What the host's restate offers: "list" (browse), "status" (what changed), "cache". */
  abilities?: string[];
  /** Quiesce hooks the host's restate reports present (2.1+); null until reported. */
  available_hooks?: string[] | null;
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
  /** Pro+ backup_engine: the current repository's key (never the secret
   *  key) and the plain repository it replaced; null when not encrypted. */
  encryption?: { fingerprint: string | null; since: string | null; previous_repository: string | null } | null;
}

export type PolicyInput = Pick<
  BackupPolicy,
  | "enabled"
  | "interval_hours"
  | "window_start_hour"
  | "keep_last"
  | "keep_daily"
  | "keep_weekly"
  | "keep_monthly"
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
  /** A restore's staging directory; null for one into place. */
  staging_path?: string | null;
  /** A restore over the host's own files (24.9). */
  in_place?: boolean;
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
  /** The pending capture is held by the host's maintenance window; shown
   *  as a note when the host is overdue or failed (otherwise the status is
   *  ``waiting_window``). */
  capture_held?: boolean;
  next_due: string | null;
  snapshot_count: number;
  /** Before a host's first good backup: does restate's estimate fit the
   *  target's free space?  Null when there is nothing to compare. */
  first_fit: FirstFit | null;
  /** The latest "Equip for backup" (the agent installing restate). */
  equip?: BackupEquipState | null;
  /** Why Equip for backup is not offered now -- equipped, agent_outdated,
   *  not_applicable, in_progress, or another not-equipped reason -- or null
   *  when it is. */
  equip_blocker?: string | null;
}

export interface BackupEquipState {
  status: "running" | "ok" | "failed";
  /** On failure: unsupported, no_release, download_failed,
   *  checksum_mismatch, install_failed, no_answer. */
  reason: string | null;
  /** Running, but the command is queued behind the host's maintenance
   *  window; the hour to answer starts when it is sent. */
  held?: boolean;
  detail: string | null;
  installed: string | null;
  requested_at: string | null;
  finished_at: string | null;
}

export interface FirstFit {
  estimate_bytes: number;
  available_bytes: number;
  fits: boolean;
  largest: { path: string; bytes: number }[];
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
  target_problem: boolean;
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
  /** Over the host's own files rather than into staging. */
  in_place?: boolean;
  acknowledge_in_place?: boolean;
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

/** Have the host's agent install restate ("Equip for backup"). */
export const equipBackup = async (hostId: string): Promise<{ command_id: string; equip: BackupEquipState | null }> =>
  (await axiosInstance.post<{ command_id: string; equip: BackupEquipState | null }>(
    `${base}/host/${hostId}/backup-equip`,
  )).data;

export interface BulkEquipResult {
  requested: number;
  started: number;
  skipped: { host_id: string; fqdn: string | null; reason: string }[];
}

/** Equip for backup on many hosts; the rest come back with why. */
export const bulkEquipBackup = async (hostIds: string[]): Promise<BulkEquipResult> =>
  (await axiosInstance.post<BulkEquipResult>(`${base}/backups/equip`, { host_ids: hostIds })).data;

/** Ask the host's agent whether it can run restate now ("Check again"). */
export const recheckBackup = async (hostId: string): Promise<{ command_id: string }> =>
  (await axiosInstance.post<{ command_id: string }>(`${base}/host/${hostId}/backup-recheck`)).data;

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

/** List one folder of a snapshot (restate 2.1.0.4 ``list``); poll the run. */
export const browseSnapshot = async (hostId: string, snapshot: string, path: string): Promise<BackupRun> =>
  (await axiosInstance.post<BackupRun>(`${base}/host/${hostId}/backup-browse`, { snapshot, path })).data;

/** What changed on the host since its newest snapshot (restate ``status``). */
export const backupChanges = async (hostId: string): Promise<BackupRun> =>
  (await axiosInstance.post<BackupRun>(`${base}/host/${hostId}/backup-changes`, {})).data;

export const restoreFiles = async (hostId: string, input: RestoreInput): Promise<BackupRun> =>
  (await axiosInstance.post<BackupRun>(`${base}/host/${hostId}/backup-restore`, input)).data;

/** What the next prune would keep and remove (Pro+ backup_engine; the
 *  server ports restate's own choice).  HTTP 402 without the engine. */
export interface RetentionPreview {
  kept: string[];
  removed: string[];
}

export const previewRetention = async (
  hostId: string,
  values: Pick<PolicyInput, "keep_last" | "keep_daily" | "keep_weekly" | "keep_monthly">,
): Promise<RetentionPreview> => {
  const params = new URLSearchParams({
    keep_last: String(values.keep_last),
    keep_daily: String(values.keep_daily ?? 0),
    keep_weekly: String(values.keep_weekly ?? 0),
    keep_monthly: String(values.keep_monthly ?? 0),
  });
  const response = await axiosInstance.get(
    `${base}/host/${hostId}/backup-retention-preview?${params.toString()}`,
  );
  return response.data;
};
