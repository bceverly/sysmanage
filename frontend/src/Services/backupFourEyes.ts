// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

// Four-eyes restore approval (ROADMAP 27.2, Enterprise backup_ops_engine):
// with the setting on, a restore over a host's own files waits for a second
// person with the restore role.  The server answers 402 without the engine.

import axiosInstance from './api';

const base = '/api/v1';

export interface RestoreRequest {
  id: string;
  /** restore / rebuild / clone / wipe / migrate (2026-11-24); every request
   *  so far is a restore.  The card labels the others when they land. */
  kind?: string;
  /** where a rebuild or clone goes; null for a restore */
  target?: Record<string, unknown> | null;
  host_id: string;
  fqdn: string | null;
  /** pending / approved / rejected / withdrawn / expired */
  status: string;
  snapshot: string;
  include: string[];
  packages: boolean;
  requested_by: string;
  requested_at: string | null;
  decided_by: string | null;
  decided_at: string | null;
  reason: string | null;
  run_id: string | null;
}

export interface FourEyes {
  enabled: boolean;
  ttl_hours: number;
  requests: RestoreRequest[];
}

export const getFourEyes = async (): Promise<FourEyes> =>
  (await axiosInstance.get<FourEyes>(`${base}/backups/four-eyes`)).data;

export const setFourEyes = async (enabled: boolean) =>
  (await axiosInstance.put(`${base}/backups/four-eyes`, { enabled })).data;

export const approveRestore = async (id: string) =>
  (await axiosInstance.post(`${base}/backups/restore-requests/${id}/approve`)).data;

export const rejectRestore = async (id: string, reason: string | null) =>
  (await axiosInstance.post(`${base}/backups/restore-requests/${id}/reject`, { reason })).data;

export const withdrawRestore = async (id: string) =>
  (await axiosInstance.post(`${base}/backups/restore-requests/${id}/withdraw`)).data;
