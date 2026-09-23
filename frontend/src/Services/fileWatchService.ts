// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

/**
 * File watch lists and collected watched-file state (Phase 21.1 S7).
 *
 * A watch list names the paths a host should hash every interval; the
 * golden-host differ then compares those hashes between hosts.
 *
 * NO FILE CONTENT CROSSES THIS API, because none is collected. A path, a
 * sha256 and stat metadata are the whole vocabulary -- which is what makes it
 * safe to watch /etc/shadow or a private key.
 */

import axiosInstance from './api';

/** The outcomes a watched path can report. Never inferred from a missing row. */
export type FileWatchState =
  | 'present'
  | 'absent'
  | 'unreadable'
  | 'not_a_file'
  | 'too_large';

/** States in which the host did NOT manage to measure the path. */
export const NOT_MEASURED_STATES: FileWatchState[] = ['unreadable', 'too_large'];

export interface FileWatchPath {
  id?: string;
  path: string;
  description?: string | null;
  /** Empty or absent means every platform. */
  platforms?: string[] | null;
}

export interface FileWatch {
  id: string;
  name: string;
  description: string | null;
  version: number;
  enabled: boolean;
  created_by: string | null;
  created_at: string | null;
  path_count: number;
  paths?: FileWatchPath[];
}

export interface SharedFileWatch {
  id: string;
  slug: string;
  name: string;
  description: string | null;
  version: number;
  category: string | null;
  deprecated: boolean;
  path_count: number;
}

export interface FileWatchAssignment {
  id: string;
  watch_id: string | null;
  shared_watch_id: string | null;
  host_id: string | null;
  tag_id: string | null;
  site_id: string | null;
  enabled: boolean;
  interval_minutes: number;
  last_dispatched_at: string | null;
}

export interface HostFileStateRow {
  path: string;
  state: FileWatchState;
  sha256: string | null;
  size: number | null;
  mode: string | null;
  owner: string | null;
  group_name: string | null;
  mtime: number | null;
  type: string | null;
  target: string | null;
  collected_at: string | null;
}

export interface HostFileStateResponse {
  host_id: string;
  paths: HostFileStateRow[];
  /** How many paths landed in each state, so blind spots need no hunting. */
  counts: Record<string, number>;
}

export const listFileWatches = async (): Promise<FileWatch[]> => {
  const response = await axiosInstance.get<FileWatch[]>('/api/v1/file-watches');
  return response.data;
};

export const getFileWatch = async (watchId: string): Promise<FileWatch> => {
  const response = await axiosInstance.get<FileWatch>(
    `/api/v1/file-watches/${watchId}`,
  );
  return response.data;
};

export const listSharedFileWatches = async (): Promise<SharedFileWatch[]> => {
  const response = await axiosInstance.get<SharedFileWatch[]>(
    '/api/v1/file-watches/catalog',
  );
  return response.data;
};

export const createFileWatch = async (payload: {
  name: string;
  paths: FileWatchPath[];
  description?: string;
  enabled?: boolean;
}): Promise<FileWatch> => {
  const response = await axiosInstance.post<FileWatch>(
    '/api/v1/file-watches',
    payload,
  );
  return response.data;
};

export const updateFileWatch = async (
  watchId: string,
  payload: Partial<{
    name: string;
    paths: FileWatchPath[];
    description: string;
    enabled: boolean;
  }>,
): Promise<FileWatch> => {
  const response = await axiosInstance.put<FileWatch>(
    `/api/v1/file-watches/${watchId}`,
    payload,
  );
  return response.data;
};

export const deleteFileWatch = async (watchId: string): Promise<void> => {
  await axiosInstance.delete(`/api/v1/file-watches/${watchId}`);
};

export const listFileWatchAssignments = async (): Promise<
  FileWatchAssignment[]
> => {
  const response = await axiosInstance.get<FileWatchAssignment[]>(
    '/api/v1/file-watches/assignments/all',
  );
  return response.data;
};

export const createFileWatchAssignment = async (payload: {
  watch_id?: string;
  shared_watch_id?: string;
  host_id?: string;
  tag_id?: string;
  site_id?: string;
  interval_minutes?: number;
  enabled?: boolean;
}): Promise<FileWatchAssignment> => {
  const response = await axiosInstance.post<FileWatchAssignment>(
    '/api/v1/file-watches/assignments',
    payload,
  );
  return response.data;
};

export const deleteFileWatchAssignment = async (
  assignmentId: string,
): Promise<void> => {
  await axiosInstance.delete(`/api/v1/file-watches/assignments/${assignmentId}`);
};

/** Every watched path on one host, including the absent and unreadable ones. */
export const getHostFileState = async (
  hostId: string,
): Promise<HostFileStateResponse> => {
  const response = await axiosInstance.get<HostFileStateResponse>(
    `/api/v1/file-watches/hosts/${hostId}/state`,
  );
  return response.data;
};
