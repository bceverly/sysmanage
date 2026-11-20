// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

/**
 * A federated site's backup STATUS, as the coordinator holds it (Phase
 * 27.1).  Each site server owns its backup target and all backup data;
 * only these counts, sizes and times reach the coordinator.  Kept apart
 * from ``federation.ts``, which is at its line budget.
 */

import type { FederationDashboardRollupResponse } from './federation';

export interface FederationBackupAttentionHost {
  host_id: string;
  fqdn: string;
  status: string;
  last_good_at?: string | null;
}

export interface FederationBackupRollup {
  configured: boolean;
  target_problem: boolean;
  hosts_with_policy: number;
  attention_count: number;
  never_backed_up: number;
  repository_bytes: number;
  oldest_last_good_at?: string | null;
  status_counts: Record<string, number>;
  verification_counts: Record<string, number>;
  attention_hosts: FederationBackupAttentionHost[];
  /** Hosts by restore readiness (27.1); absent where the site has no
   *  Enterprise backup operations engine. */
  readiness_counts?: Record<string, number> | null;
  snapshot_at?: string | null;
}

/** The dashboard rollup with the site's backup status. */
export type FederationDashboardWithBackup = FederationDashboardRollupResponse & {
  backup_rollup?: FederationBackupRollup | null;
};
