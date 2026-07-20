// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

/**
 * Types, constants, formatting helpers, and the self-ticking status cell
 * for the Air-Gap Collection Runs page.  Extracted from
 * AirgapCollections.tsx to keep the page under the max-lines budget.
 */

import React, { useEffect, useState } from 'react';
import { Box, Chip, Typography } from '@mui/material';

export type RunStatus =
  | 'QUEUED'
  | 'MIRRORING'
  | 'STAGING_COMPLETE'
  | 'BUILDING_ISO'
  | 'ISO_BUILT'
  | 'BURNING'
  | 'COMPLETE'
  | 'FAILED';

export const IN_FLIGHT_STATUSES = new Set<RunStatus>([
  'QUEUED',
  'MIRRORING',
  'STAGING_COMPLETE',
  'BUILDING_ISO',
  'ISO_BUILT',
  'BURNING',
]);

export interface RunTarget {
  // Option-B: operator picks a mirror; backend derives distro/version.
  mirror_id: string;
  distro?: string | null;
  version?: string | null;
  repos: string[];
  mirror_name?: string | null;
  source_snapshot_id?: string | null;
}

// Trimmed projection of a MirrorRepository row — just what the
// run-create dialog needs to render its picker.
export interface MirrorPickItem {
  id: string;
  name: string;
  package_manager: string;
  host_id: string;
  enabled: boolean;
  known_version_id: string | null;
}

export interface CollectionRun {
  id: string;
  iso_label: string;
  media_size_bytes: number;
  // Actual on-disk ISO size (sum across discs); null until built.  The
  // Size column shows this, falling back to media_size_bytes when absent.
  iso_size_bytes?: number | null;
  include_cve: boolean;
  include_compliance: boolean;
  status: string;
  started_at: string | null;
  completed_at: string | null;
  error_message: string | null;
  cron_schedule: string | null;
  parent_run_id: string | null;
  created_at: string | null;
  worker_message_id?: string | null;
  burn_device?: string | null;
  targets?: RunTarget[];
}

export interface Manifest {
  id: string;
  disc_index: number;
  disc_count: number;
  iso_path: string;
  iso_sha256: string;
  iso_size_bytes: number;
  signer_fingerprint: string;
  signature_algorithm: string;
  format_version: number;
  created_at: string | null;
}

export interface DiscInfo {
  disc_index: number;
  filename: string;
  size_bytes: number;
}

export interface ServerInfo {
  role?: string;
}

export const RUNS_URL = '/api/v1/airgap/collector/runs';

export const statusColor = (
  s: string,
): 'default' | 'info' | 'success' | 'error' => {
  switch (s) {
    case 'QUEUED':
      return 'default';
    case 'MIRRORING':
    case 'STAGING_COMPLETE':
    case 'BUILDING_ISO':
    case 'ISO_BUILT':
    case 'BURNING':
      return 'info';
    case 'COMPLETE':
      return 'success';
    case 'FAILED':
      return 'error';
    default:
      return 'default';
  }
};

export const formatBytes = (n: number | null | undefined): string => {
  if (n === null || n === undefined) return '—';
  const units = ['B', 'KB', 'MB', 'GB'];
  let v = n;
  let u = 0;
  while (v >= 1024 && u < units.length - 1) {
    v /= 1024;
    u += 1;
  }
  return `${v.toFixed(u === 0 ? 0 : 1)} ${units[u]}`;
};

export const formatElapsed = (since: Date): string => {
  const ms = Date.now() - since.getTime();
  if (ms < 60_000) return `${Math.max(1, Math.round(ms / 1000))}s`;
  if (ms < 3_600_000) return `${Math.round(ms / 60_000)}m`;
  return `${Math.round(ms / 3_600_000)}h`;
};

/**
 * Status cell for a collection run.  For in-flight runs (QUEUED →
 * BURNING) it shows the status chip plus a live elapsed-time that
 * ticks every second — same UX as the mirror ActionStatusChip — so the
 * operator can see at a glance that a run is progressing (or how long
 * it's been wedged at QUEUED, which is the symptom that says the
 * orchestrator isn't advancing it).  Self-tickers per in-flight row
 * avoid rebuilding the whole DataGrid column array every second.
 */
export const RunStatusCell: React.FC<{ row: CollectionRun }> = ({ row }) => {
  const inFlight = IN_FLIGHT_STATUSES.has(row.status as RunStatus);
  // Throwaway tick state forces a 1s re-render while in-flight; the
  // interval is torn down the moment the run settles.  Only the setter
  // is needed (the value is meaningless), hence the unused first slot.
  const [, setTick] = useState(0); // NOSONAR S6754 - re-render tick; value intentionally unused
  useEffect(() => {
    if (!inFlight) return undefined;
    const h = setInterval(() => setTick((n) => n + 1), 1000);
    return () => clearInterval(h);
  }, [inFlight]);

  // Anchor elapsed on started_at (set when the orchestrator dispatches
  // the first plan) and fall back to created_at for runs still sitting
  // at QUEUED before the orchestrator has touched them.
  const anchorRaw = row.started_at || row.created_at;
  const anchor = anchorRaw ? new Date(anchorRaw) : null;
  const elapsed = inFlight && anchor ? formatElapsed(anchor) : '';

  return (
    <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.75 }}>
      <Chip size="small" label={row.status} color={statusColor(row.status)} />
      {elapsed && (
        <Typography variant="caption" color="text.secondary">
          {elapsed}
        </Typography>
      )}
    </Box>
  );
};
