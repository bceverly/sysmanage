/**
 * Repository Mirroring API client (Phase 10.4).
 *
 * Wraps the ``/api/mirror-repositories/*`` and ``/api/settings/mirror``
 * endpoints.  Every call returns 402 when the Pro+
 * ``repository_mirroring_engine`` module isn't loaded; the caller is
 * expected to gate its UI on ``isModuleLicensed("repository_mirroring_engine")``
 * rather than rely on per-call error handling.
 */

import axiosInstance from './api';

export interface MirrorRepository {
  id: string;
  name: string;
  package_manager: 'apt' | 'dnf' | 'zypper' | 'pkg';
  upstream_url: string;
  suite?: string | null;
  components?: string | null;
  architectures?: string | null;
  repoid?: string | null;
  gpgkey_url?: string | null;
  repo_alias?: string | null;
  release?: string | null;
  signing_key_url?: string | null;
  bandwidth_cap_kbps: number;
  sync_cron: string;
  network_tier?: string | null;
  enabled: boolean;
  host_id: string;
  platform_config_id?: string | null;
  known_version_id?: string | null;
  last_sync_at?: string | null;
  last_sync_status?: string | null;
  last_sync_error?: string | null;
  last_sync_message_id?: string | null;
  next_sync_at?: string | null;
  last_snapshot_at?: string | null;
  last_snapshot_status?: string | null;
  last_snapshot_error?: string | null;
  last_snapshot_message_id?: string | null;
  last_restore_at?: string | null;
  last_restore_status?: string | null;
  last_restore_error?: string | null;
  last_restore_message_id?: string | null;
  last_integrity_at?: string | null;
  last_integrity_status?: string | null;
  last_integrity_error?: string | null;
  last_integrity_message_id?: string | null;
  last_gc_at?: string | null;
  last_gc_status?: string | null;
  last_gc_error?: string | null;
  last_gc_message_id?: string | null;
}

/** The plan ``action`` keys the OSS dispatch routes through. */
export type MirrorActionKey =
  | 'sync'
  | 'snapshot'
  | 'restore'
  | 'integrity'
  | 'gc';

export interface MirrorRepositoryCreate {
  name: string;
  package_manager: string;
  upstream_url: string;
  host_id: string;
  suite?: string;
  components?: string;
  architectures?: string;
  repoid?: string;
  gpgkey_url?: string;
  repo_alias?: string;
  release?: string;
  signing_key_url?: string;
  bandwidth_cap_kbps?: number;
  sync_cron?: string;
  network_tier?: string;
  enabled?: boolean;
  known_version_id?: string;
}

export interface MirrorSnapshot {
  id: string;
  repository_id: string;
  snapshot_id: string;
  taken_at?: string | null;
  size_bytes?: number | null;
  file_count?: number | null;
  retention_until?: string | null;
  notes?: string | null;
}

export interface MirrorSettings {
  mirror_root_path: string;
  integrity_check_cadence_hours: number;
  retention_window_days: number;
  default_bandwidth_cap_kbps: number;
  snapshot_count_to_keep: number;
  updated_at?: string | null;
}

export const listMirrors = async (): Promise<MirrorRepository[]> => {
  const r = await axiosInstance.get<MirrorRepository[]>('/api/mirror-repositories');
  return r.data;
};

export const createMirror = async (
  payload: MirrorRepositoryCreate,
): Promise<MirrorRepository> => {
  const r = await axiosInstance.post<MirrorRepository>(
    '/api/mirror-repositories',
    payload,
  );
  return r.data;
};

export const updateMirror = async (
  id: string,
  patch: Partial<MirrorRepositoryCreate>,
): Promise<MirrorRepository> => {
  const r = await axiosInstance.put<MirrorRepository>(
    `/api/mirror-repositories/${id}`,
    patch,
  );
  return r.data;
};

export const deleteMirror = async (id: string): Promise<void> => {
  await axiosInstance.delete(`/api/mirror-repositories/${id}`);
};

export const syncMirror = async (
  id: string,
): Promise<{ message: string; mirror_id: string; message_id: string }> => {
  const r = await axiosInstance.post(`/api/mirror-repositories/${id}/sync`);
  return r.data;
};

export const snapshotMirror = async (
  id: string,
): Promise<{ snapshot_id: string; message_id: string }> => {
  const r = await axiosInstance.post(`/api/mirror-repositories/${id}/snapshot`);
  return r.data;
};

export const restoreMirror = async (
  id: string,
  snapshotId: string,
): Promise<{ snapshot_id: string; message_id: string }> => {
  const r = await axiosInstance.post(
    `/api/mirror-repositories/${id}/restore/${snapshotId}`,
  );
  return r.data;
};

export const listSnapshots = async (
  id: string,
): Promise<MirrorSnapshot[]> => {
  const r = await axiosInstance.get<MirrorSnapshot[]>(
    `/api/mirror-repositories/${id}/snapshots`,
  );
  return r.data;
};

export const getMirrorSettings = async (): Promise<MirrorSettings> => {
  const r = await axiosInstance.get<MirrorSettings>('/api/settings/mirror');
  return r.data;
};

export const updateMirrorSettings = async (
  patch: Partial<MirrorSettings>,
): Promise<MirrorSettings> => {
  const r = await axiosInstance.put<MirrorSettings>('/api/settings/mirror', patch);
  return r.data;
};

// ---------------------------------------------------------------------
// Per-platform configs (Phase 10.4.2)
// ---------------------------------------------------------------------

// Phase 10.4.3: platform == package_manager.  Each tab is keyed to
// one PM so the Add Mirror dialog doesn't need a PM dropdown.
export type MirrorPlatform = 'apt' | 'dnf' | 'zypper' | 'pkg';

export interface MirrorPlatformConfig {
  id: string;
  platform: MirrorPlatform;
  host_id: string;
  mirror_root_path: string;
  integrity_check_cadence_hours: number;
  retention_window_days: number;
  default_bandwidth_cap_kbps: number;
  snapshot_count_to_keep: number;
  created_at: string | null;
  updated_at: string | null;
}

export interface MirrorPlatformConfigPayload {
  platform: MirrorPlatform;
  host_id: string;
  mirror_root_path?: string;
  integrity_check_cadence_hours?: number;
  retention_window_days?: number;
  default_bandwidth_cap_kbps?: number;
  snapshot_count_to_keep?: number;
}

export const listPlatformConfigs = async (): Promise<MirrorPlatformConfig[]> => {
  const r = await axiosInstance.get<MirrorPlatformConfig[]>(
    '/api/mirror-platform-configs',
  );
  return r.data;
};

export const createPlatformConfig = async (
  payload: MirrorPlatformConfigPayload,
): Promise<MirrorPlatformConfig> => {
  const r = await axiosInstance.post<MirrorPlatformConfig>(
    '/api/mirror-platform-configs',
    payload,
  );
  return r.data;
};

export const updatePlatformConfig = async (
  id: string,
  payload: MirrorPlatformConfigPayload,
): Promise<MirrorPlatformConfig> => {
  const r = await axiosInstance.put<MirrorPlatformConfig>(
    `/api/mirror-platform-configs/${id}`,
    payload,
  );
  return r.data;
};

export const deletePlatformConfig = async (id: string): Promise<void> => {
  await axiosInstance.delete(`/api/mirror-platform-configs/${id}`);
};

// ---------------------------------------------------------------------
// Known-version catalog + host default mirror assignments (10.4.4)
// ---------------------------------------------------------------------

export interface MirrorKnownVersion {
  id: string;
  platform: MirrorPlatform;
  version_key: string;
  label: string;
  os_family: string;
  match_regex: string;
  default_upstream_url: string;
  default_suite: string | null;
  default_repoid: string | null;
  default_repo_alias: string | null;
  default_release: string | null;
  is_active: boolean;
}

export const listKnownVersions = async (
  platform?: MirrorPlatform,
): Promise<MirrorKnownVersion[]> => {
  const r = await axiosInstance.get<MirrorKnownVersion[]>(
    '/api/mirror-known-versions',
    { params: platform ? { platform } : {} },
  );
  return r.data;
};

export interface HostDefaultMirrorRow {
  platform: MirrorPlatform;
  version_key: string;
  os_family: string;
  label: string;
  match_regex: string;
  eligible_mirrors: Array<{ id: string; name: string }>;
  current_mirror_id: string | null;
  assignment_id: string | null;
  updated_at: string | null;
}

export const listDefaultMirrorAssignments = async (): Promise<HostDefaultMirrorRow[]> => {
  const r = await axiosInstance.get<HostDefaultMirrorRow[]>(
    '/api/host-defaults/mirrors',
  );
  return r.data;
};

export const setDefaultMirrorAssignment = async (
  platform: MirrorPlatform,
  versionKey: string,
  osFamily: string,
  mirrorId: string | null,
): Promise<{
  platform: string;
  version_key: string;
  os_family: string;
  mirror_id: string | null;
  previous_mirror_id: string | null;
  dispatched: Array<{ host_id: string; message_id: string }>;
}> => {
  const r = await axiosInstance.put(
    `/api/host-defaults/mirrors/${platform}/${encodeURIComponent(versionKey)}/${osFamily}`,
    { mirror_id: mirrorId },
  );
  return r.data;
};

// ---------------------------------------------------------------------
// Setup-status card (Phase 10.4.1)
// ---------------------------------------------------------------------

export interface MirrorSetupStatus {
  host_id: string;
  tools: Record<string, 'present' | 'missing'>;
  platform: string | null;
  distro: string | null;
  last_check_at: string | null;
  last_check_message_id: string | null;
  last_check_error: string | null;
  install_status: 'idle' | 'dispatched' | 'succeeded' | 'failed';
  last_install_at: string | null;
  last_install_message_id: string | null;
  last_install_error: string | null;
  ready_apt: boolean;
  ready_dnf: boolean;
  ready_zypper: boolean;
  ready_pkg: boolean;
}

export const getMirrorSetupStatus = async (
  hostId: string,
): Promise<MirrorSetupStatus> => {
  const r = await axiosInstance.get<MirrorSetupStatus>(
    `/api/mirror-repositories/setup-status/${hostId}`,
  );
  return r.data;
};

export const refreshMirrorSetupStatus = async (
  hostId: string,
): Promise<{ host_id: string; message_id: string; status: string }> => {
  const r = await axiosInstance.post(
    `/api/mirror-repositories/setup-status/${hostId}/refresh`,
  );
  return r.data;
};

export const installMirrorTools = async (
  hostId: string,
  packageManager: 'apt' | 'dnf' | 'zypper' | 'pkg',
): Promise<{
  host_id: string;
  message_id: string;
  package_manager: string;
  status: string;
}> => {
  const r = await axiosInstance.post(
    `/api/mirror-repositories/setup-install/${hostId}`,
    { package_manager: packageManager },
  );
  return r.data;
};
