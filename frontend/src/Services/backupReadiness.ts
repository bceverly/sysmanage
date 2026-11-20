// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

// Restore readiness (ROADMAP 27.1, Enterprise backup_ops_engine): per host,
// the recovery point objective, the expected restore time and whether the
// repository has been proven readable recently.  The server answers 402
// without the engine.

import axiosInstance from './api';

const base = '/api/v1';

export type ReadinessState = 'never_backed_up' | 'rpo_breached' | 'unproven' | 'ready';

export interface HostReadiness {
  host_id: string;
  fqdn: string;
  policy_id: string;
  enabled: boolean;
  state: ReadinessState;
  /** no_good_backup / rpo_breached / never_proven / proof_stale */
  reasons: string[];
  rpo: { target_hours: number; age_hours: number | null; met: boolean };
  /** basis: restore / verify / capture (capture = an estimate). */
  rto: { seconds: number | null; basis: string | null; mb_per_s: number | null };
  proof: { kind: string; at: string; fresh: boolean } | null;
}

export interface FleetReadiness {
  hosts: HostReadiness[];
  counts: Record<ReadinessState, number>;
}

export const READINESS_ORDER: ReadinessState[] = [
  'never_backed_up', 'rpo_breached', 'unproven', 'ready',
];

export const getReadiness = async (): Promise<FleetReadiness> =>
  (await axiosInstance.get<FleetReadiness>(`${base}/backups/readiness`)).data;

/** ``rpoHours`` null = the default, twice the policy's interval. */
export const setRpo = async (hostId: string, rpoHours: number | null) =>
  (await axiosInstance.put(`${base}/host/${hostId}/backup-readiness`, { rpo_hours: rpoHours })).data;
