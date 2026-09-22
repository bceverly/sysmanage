// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

import axiosInstance from "./api";

/**
 * Query packs over the Phase 21.1 endpoint fact substrate.
 *
 * The substrate is open-source; this management plane is Professional, so
 * every call here 403s on a server without `query_pack_engine`.
 */

export interface QueryPackQuery {
  id?: string;
  name: string;
  sql: string;
  description?: string | null;
  required_tables?: string[];
  interval_minutes?: number | null;
  platforms?: string[];
}

export interface QueryPack {
  id: string;
  name: string;
  description: string | null;
  version: number;
  enabled?: boolean;
  /** Curated packs come from the shared catalog and cannot be edited here. */
  curated: boolean;
  slug?: string;
  category?: string | null;
  deprecated?: boolean;
  query_count: number;
  created_by?: string | null;
  created_at?: string | null;
  queries?: QueryPackQuery[];
}

export interface QueryPackAssignment {
  id: string;
  pack_id: string | null;
  shared_pack_id: string | null;
  host_id: string | null;
  tag_id: string | null;
  site_id: string | null;
  enabled: boolean;
  interval_minutes: number;
  last_dispatched_at: string | null;
}

/**
 * `partial` is not a lesser success — it means some queries could not be
 * answered on that host, and the UI must never render it as a clean pass.
 * That distinction is the whole point of the fact substrate.
 */
export type QueryPackRunStatus = "pending" | "success" | "partial" | "failed";

export interface QueryPackResultRow {
  query_name: string;
  status: "ok" | "not_covered" | "error";
  reason: string | null;
  columns: Record<string, unknown> | null;
}

export interface QueryPackRun {
  id: string;
  host_id: string;
  pack_name: string | null;
  status: QueryPackRunStatus;
  contract_version: number | null;
  queries_total: number;
  queries_ok: number;
  queries_not_covered: number;
  queries_failed: number;
  error: string | null;
  started_at: string | null;
  completed_at: string | null;
  results?: QueryPackResultRow[];
}

export interface PackValidation {
  valid: boolean;
  problems: string[];
}

const BASE = "/api/v1/query-packs";

export const getCatalog = async (): Promise<QueryPack[]> => {
  const response = await axiosInstance.get<QueryPack[]>(`${BASE}/catalog`);
  return response.data;
};

export const getPacks = async (): Promise<QueryPack[]> => {
  const response = await axiosInstance.get<QueryPack[]>(BASE);
  return response.data;
};

export const getPack = async (packId: string): Promise<QueryPack> => {
  const response = await axiosInstance.get<QueryPack>(`${BASE}/${packId}`);
  return response.data;
};

export const createPack = async (pack: {
  name: string;
  description?: string;
  queries: QueryPackQuery[];
}): Promise<QueryPack> => {
  const response = await axiosInstance.post<QueryPack>(BASE, pack);
  return response.data;
};

export const updatePack = async (
  packId: string,
  changes: Partial<{
    name: string;
    description: string;
    enabled: boolean;
    queries: QueryPackQuery[];
  }>,
): Promise<QueryPack> => {
  const response = await axiosInstance.put<QueryPack>(
    `${BASE}/${packId}`,
    changes,
  );
  return response.data;
};

export const deletePack = async (packId: string): Promise<void> => {
  await axiosInstance.delete(`${BASE}/${packId}`);
};

/**
 * Check a pack without storing it.
 *
 * Its own call rather than inferring from a failed create: an author wants to
 * know the SQL is acceptable before committing a name, and a rejected create
 * leaves no draft behind to fix.
 */
export const validatePack = async (pack: {
  name: string;
  queries: QueryPackQuery[];
}): Promise<PackValidation> => {
  const response = await axiosInstance.post<PackValidation>(
    `${BASE}/validate`,
    pack,
  );
  return response.data;
};

export const getAssignments = async (): Promise<QueryPackAssignment[]> => {
  const response = await axiosInstance.get<QueryPackAssignment[]>(
    `${BASE}/assignments/all`,
  );
  return response.data;
};

export const createAssignment = async (assignment: {
  pack_id?: string;
  shared_pack_id?: string;
  host_id?: string;
  tag_id?: string;
  site_id?: string;
  interval_minutes?: number;
}): Promise<QueryPackAssignment> => {
  const response = await axiosInstance.post<QueryPackAssignment>(
    `${BASE}/assignments`,
    assignment,
  );
  return response.data;
};

export const deleteAssignment = async (assignmentId: string): Promise<void> => {
  await axiosInstance.delete(`${BASE}/assignments/${assignmentId}`);
};

export const getRuns = async (hostId?: string): Promise<QueryPackRun[]> => {
  const query = hostId ? `?host_id=${encodeURIComponent(hostId)}` : "";
  const response = await axiosInstance.get<QueryPackRun[]>(
    `${BASE}/runs/recent${query}`,
  );
  return response.data;
};

export const getRun = async (runId: string): Promise<QueryPackRun> => {
  const response = await axiosInstance.get<QueryPackRun>(
    `${BASE}/runs/${runId}`,
  );
  return response.data;
};

/**
 * A live query: one ad-hoc statement fanned out across a fleet, bounded.
 *
 * `concurrency` and `timeout_seconds` are not cosmetic. An ad-hoc query is
 * one keystroke against every host you own, which is exactly the unbounded
 * fan-out fleet jobs exist to prevent — so the server clamps both and records
 * what it actually used.
 */
export type LiveQueryStatus = "pending" | "running" | "completed" | "canceled";

export interface LiveQueryTarget {
  run_id: string;
  host_id: string;
  /** `waiting` = not yet dispatched; `pending` = dispatched, awaiting answer. */
  status: "waiting" | "pending" | "success" | "partial" | "failed";
  queries_ok: number;
  queries_not_covered: number;
  error: string | null;
  rows: {
    status: "ok" | "not_covered" | "error";
    reason: string | null;
    columns: Record<string, unknown> | null;
  }[];
}

export interface LiveQuery {
  id: string;
  name: string | null;
  sql: string;
  required_tables: string[];
  status: LiveQueryStatus;
  concurrency: number;
  timeout_seconds: number;
  total_targets: number;
  completed_count: number;
  failed_count: number;
  /** Counted apart from failures: a host that cannot answer has not failed. */
  not_covered_count: number;
  requested_by: string | null;
  created_at: string | null;
  completed_at: string | null;
  targets?: LiveQueryTarget[];
}

export const createLiveQuery = async (request: {
  sql: string;
  name?: string;
  required_tables?: string[];
  host_ids?: string[];
  tag_id?: string;
  site_id?: string;
  concurrency?: number;
  timeout_seconds?: number;
}): Promise<LiveQuery> => {
  const response = await axiosInstance.post<LiveQuery>(`${BASE}/live`, request);
  return response.data;
};

export const getLiveQueries = async (): Promise<LiveQuery[]> => {
  const response = await axiosInstance.get<LiveQuery[]>(`${BASE}/live`);
  return response.data;
};

/** One live query with its per-host results. Also sweeps timed-out hosts. */
export const getLiveQuery = async (liveId: string): Promise<LiveQuery> => {
  const response = await axiosInstance.get<LiveQuery>(`${BASE}/live/${liveId}`);
  return response.data;
};

export const cancelLiveQuery = async (
  liveId: string,
): Promise<{ status: string; targets_not_dispatched: number }> => {
  const response = await axiosInstance.post<{
    status: string;
    targets_not_dispatched: number;
  }>(`${BASE}/live/${liveId}/cancel`);
  return response.data;
};
