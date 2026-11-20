// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

// Legal hold (ROADMAP 27.2, Enterprise backup_ops_engine): a held snapshot
// is kept by every prune until it is released.  Placing and releasing answer
// 402 without the engine; a hold already placed keeps protecting.

import axiosInstance from './api';

const base = '/api/v1';

export interface LegalHold {
  id: string;
  host_id: string;
  fqdn: string | null;
  snapshot: string;
  owner: string;
  reason: string;
  placed_by: string;
  placed_at: string | null;
  released_by: string | null;
  released_at: string | null;
}

export const getLegalHolds = async (): Promise<LegalHold[]> =>
  (await axiosInstance.get<{ holds: LegalHold[] }>(`${base}/backups/legal-holds`)).data.holds;

export const placeLegalHold = async (hostId: string, snapshot: string, owner: string, reason: string) =>
  (await axiosInstance.post<LegalHold>(
    `${base}/host/${hostId}/backup-snapshots/${encodeURIComponent(snapshot)}/hold`, { owner, reason },
  )).data;

export const releaseLegalHold = async (id: string) =>
  (await axiosInstance.post<LegalHold>(`${base}/backups/legal-holds/${id}/release`)).data;
