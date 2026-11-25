// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

// The off-site cloud copy: S3 Glacier Deep Archive (ROADMAP 27.3).  Setting
// it up and running it is Professional+ (402 without backup_engine); reading
// it, checking it, turning it off, restoring and the key export work in
// every edition, also after a lapse.

import axiosInstance from './api';

const base = '/api/v1/backups/offsite';

export interface BandwidthRule {
  days: number[];
  start: string;
  end: string;
  kbps: number;
}

export interface CloudCopySettings {
  full_every_days: number;
  run_hour_utc: number;
  keep_monthly: number;
  keep_yearly: number;
  exclude: string[];
  include: string[];
  bandwidth: { rules: BandwidthRule[]; default_kbps: number };
  part_mib: number;
}

export interface CloudCopyDataset {
  dataset: string;
  bytes_stored: number;
  streams: number;
  last_snapshot?: string;
  last_uploaded_at?: string;
  last_full_at: string | null;
  key_id?: string;
}

export interface CloudCopy {
  id: string;
  target_id: string;
  enabled: boolean;
  bucket: string;
  region: string;
  endpoint: string | null;
  prefix: string;
  storage_class: string;
  object_lock: boolean;
  lock_verified: boolean | null;
  checked_at: string | null;
  access_key_hint: string | null;
  settings: Partial<CloudCopySettings>;
  next_run_at: string | null;
  last_ok_at: string | null;
  last_error: string | null;
  last_run_id: string | null;
  key_id: string | null;
  datasets: CloudCopyDataset[];
  bytes_stored: number;
  licensed: boolean;
  overdue: boolean;
  cost?: { monthly_usd: number; usd_per_tb_month: number; minimum_days: number };
  retention_days?: { incremental: number; monthly: number; yearly: number; minimum: number };
}

export interface CloudCopyOverview {
  available: boolean;
  licensed: boolean;
  defaults: CloudCopySettings | null;
  copies: CloudCopy[];
  targets: { id: string; name: string; storage_path: string | null; has_storage_host: boolean }[];
}

export interface CloudCopyRun {
  id: string;
  action: 'check' | 'upload' | 'restore';
  status: 'queued' | 'running' | 'ok' | 'partial' | 'failed' | 'interrupted';
  queued_at: string;
  finished_at: string | null;
  requested_by: string | null;
  snapshot: string | null;
  target_dataset: string | null;
  bytes_moved: number | null;
  message: string | null;
  progress: Record<string, unknown> | null;
}

export interface RestorePoint {
  dataset: string;
  snapshot: string;
  uploaded_at: string;
  streams: number;
  bytes: number;
}

export interface RestoreEstimate {
  bytes: number;
  parts: number;
  streams: number;
  storage_class: string;
  tier: string;
  thaw_hours: number;
  usd_thaw: number;
  usd_transfer: number;
}

export interface SetupGuide {
  lifecycle: Record<string, unknown>;
  iam_policy: Record<string, unknown>;
  commands: string[];
}

export type CopyChanges = Partial<Omit<CloudCopy, 'settings'>> & {
  target_id?: string;
  access_key?: string;
  secret_key?: string;
  settings?: Partial<CloudCopySettings>;
};

export const getCloudCopies = async () => (await axiosInstance.get<CloudCopyOverview>(base)).data;
export const createCloudCopy = async (body: CopyChanges) => (await axiosInstance.post<CloudCopy>(base, body)).data;
export const updateCloudCopy = async (id: string, body: CopyChanges) =>
  (await axiosInstance.put<CloudCopy>(`${base}/${id}`, body)).data;
export const checkCloudCopy = async (id: string) => (await axiosInstance.post<CloudCopyRun>(`${base}/${id}/check`)).data;
export const runCloudCopy = async (id: string) => (await axiosInstance.post<CloudCopyRun>(`${base}/${id}/run`)).data;
export const rotateCloudCopyKey = async (id: string) =>
  (await axiosInstance.post<CloudCopy>(`${base}/${id}/rotate-key`)).data;
export const getSetupGuide = async (id: string) => (await axiosInstance.get<SetupGuide>(`${base}/${id}/setup`)).data;
export const getCloudCopyRuns = async (id: string) =>
  (await axiosInstance.get<CloudCopyRun[]>(`${base}/${id}/runs`)).data;
export const getRestorePoints = async (id: string) =>
  (await axiosInstance.get<RestorePoint[]>(`${base}/${id}/restore-points`)).data;
export const estimateRestore = async (id: string, dataset: string, snapshot: string, tier: string) =>
  (await axiosInstance.post<RestoreEstimate>(`${base}/${id}/restore/estimate`, { dataset, snapshot, tier })).data;
export const restoreCloudCopy = async (
  id: string, dataset: string, snapshot: string, tier: string, targetDataset: string,
) => (await axiosInstance.post<CloudCopyRun>(`${base}/${id}/restore`, {
  dataset, snapshot, tier, target_dataset: targetDataset,
})).data;
export const exportCloudCopyKeys = async (id: string, reason: string, recipientKey?: string) => {
  const answer = await axiosInstance.post<string>(`${base}/${id}/export`, {
    reason, recipient_key: recipientKey || undefined,
  }, { responseType: 'text' });
  const disposition = String(answer.headers['content-disposition'] ?? '');
  const name = /filename="([^"]+)"/.exec(disposition)?.[1] ?? 'sysmanage-offsite-keys.tar.asc';
  return { name, content: answer.data };
};
