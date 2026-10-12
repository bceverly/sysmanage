// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

// Time synchronization (Phase 23.3).  The server MEASURES every host's clock
// (offset = host minus server; positive means the host is ahead) and judges
// it against the host's bounds.  Refusals come back as codes
// (``detail.code``), which the UI translates.

import axiosInstance from "./api";

export type ClockStatus =
  | "ok"
  | "warning"
  | "critical"
  | "unmeasured"
  | "stale"
  | "server_clock_off";

/** Worst first -- the order the fleet view sorts by. */
export const STATUS_ORDER: ClockStatus[] = [
  "critical",
  "warning",
  "server_clock_off",
  "stale",
  "unmeasured",
  "ok",
];

/** Where a host's bounds come from. */
export type BoundsSource = "default" | "server" | "tenant" | "site" | "tag";

export interface Bounds {
  warning_ms: number;
  critical_ms: number;
  source: BoundsSource;
  ref: string;
}

/** The server's own clock against its reference. */
export interface ServerClock {
  reference: string | null;
  offset_ms: number | null;
  verified: boolean;
  /** ``no_reference`` | ``unreachable`` | ``server_off`` | null */
  reason: string | null;
  checked_at: number;
}

export interface Measured {
  offset_ms: number;
  rtt_ms: number | null;
  samples: number | null;
  /** ``exchange`` (to the millisecond) or ``timestamp`` (to the second). */
  method: string | null;
  measured_at: string | null;
}

export interface TimeService {
  service: string | null;
  running: boolean | null;
  synchronized: boolean | null;
  source: string | null;
  stratum: number | null;
  reported_offset_ms: number | null;
  reported_at: string | null;
}

export interface HostClock {
  status: ClockStatus;
  /** Null without the policy engine (Pro+). */
  ntp_policy: HostNtpPolicy | null;
  bounds: Bounds;
  server: ServerClock;
  service_ok: boolean | null;
  measured: Measured | null;
  time_service: TimeService | null;
  history: { at: string; offset_ms: number; rtt_ms: number | null; method: string }[];
}

export interface FleetClock {
  host_id: string;
  fqdn: string;
  status: ClockStatus;
  bounds: Bounds;
  measured: Measured | null;
  service_ok: boolean | null;
  time_service: string | null;
  time_source: string | null;
  site_id: string | null;
  site_name: string | null;
  tags: { id: string; name: string }[];
  /** Null without the policy engine, or with no policy for the host. */
  policy_compliant: boolean | null;
  policy_findings: string[];
}

export interface FleetClocks {
  server: ServerClock;
  counts: Partial<Record<ClockStatus, number>>;
  hosts: FleetClock[];
}

export interface FleetSummary {
  server: ServerClock;
  total: number;
  counts: Partial<Record<ClockStatus, number>>;
}

export type OverrideScope = "tenant" | "site" | "tag";

export interface BoundOverride {
  scope_kind: OverrideScope;
  scope_ref: string;
  warning_ms: number;
  critical_ms: number;
  updated_at: string | null;
  updated_by: string | null;
}

export interface BoundsConfig {
  server: Bounds;
  overrides: BoundOverride[];
  limits: { min_ms: number; max_ms: number };
  /** The tenant level is offered only under multi-tenancy. */
  multitenancy: boolean;
}

export const getHostClock = async (hostId: string): Promise<HostClock> =>
  (await axiosInstance.get(`/api/v1/host/${hostId}/clock`)).data;

export const getFleetClocks = async (): Promise<FleetClocks> =>
  (await axiosInstance.get("/api/v1/time-sync/hosts")).data;

export const getFleetSummary = async (): Promise<FleetSummary> =>
  (await axiosInstance.get("/api/v1/time-sync/summary")).data;

export const getBounds = async (): Promise<BoundsConfig> =>
  (await axiosInstance.get("/api/v1/time-sync/bounds")).data;

export const setServerBounds = async (
  warningMs: number,
  criticalMs: number,
): Promise<Bounds> =>
  (
    await axiosInstance.put("/api/v1/time-sync/bounds/server", {
      warning_ms: warningMs,
      critical_ms: criticalMs,
    })
  ).data;

export const setOverride = async (
  scopeKind: OverrideScope,
  scopeRef: string,
  warningMs: number,
  criticalMs: number,
): Promise<BoundOverride[]> =>
  (
    await axiosInstance.put("/api/v1/time-sync/bounds/override", {
      scope_kind: scopeKind,
      scope_ref: scopeRef,
      warning_ms: warningMs,
      critical_ms: criticalMs,
    })
  ).data.overrides;

export const clearOverride = async (
  scopeKind: OverrideScope,
  scopeRef: string,
): Promise<BoundOverride[]> =>
  (
    await axiosInstance.delete("/api/v1/time-sync/bounds/override", {
      params: { scope_kind: scopeKind, scope_ref: scopeRef },
    })
  ).data.overrides;

// --- spot resync (Phase 23.3 S5) -------------------------------------------

export type ResyncStatus =
  | "queued"
  | "sent"
  | "succeeded"
  | "failed"
  | "unsupported"
  | "timed_out";

export interface ClockResync {
  id: string;
  host_id: string;
  batch_id: string | null;
  status: ResyncStatus;
  requested_by: string | null;
  requested_at: string | null;
  sent_at: string | null;
  finished_at: string | null;
  offset_before_ms: number | null;
  reported_after_ms: number | null;
  service: string | null;
  method: string | null;
  /** A code: not_privileged, command_failed, no_tool, agent_too_old, ... */
  error: string | null;
  detail: string | null;
}

export interface FleetResync {
  batch_id: string;
  requested: number;
  already_running: number;
  counts: Partial<Record<ResyncStatus, number>>;
}

export const resyncHost = async (hostId: string): Promise<ClockResync> =>
  (await axiosInstance.post(`/api/v1/host/${hostId}/clock/resync`)).data;

export const resyncFleet = async (statuses: ClockStatus[]): Promise<FleetResync> =>
  (await axiosInstance.post("/api/v1/time-sync/resync", { statuses })).data;

export const getResyncs = async (params: {
  hostId?: string;
  batchId?: string;
  limit?: number;
}): Promise<ClockResync[]> =>
  (
    await axiosInstance.get("/api/v1/time-sync/resyncs", {
      params: { host_id: params.hostId, batch_id: params.batchId, limit: params.limit },
    })
  ).data.resyncs;

// --- fleet NTP policy (Phase 23.3 S5b, Pro+) --------------------------------

export type PolicyScope = "fleet" | "site" | "tag";

export interface NtpPolicy {
  id: string;
  scope_kind: PolicyScope;
  scope_ref: string;
  servers: string[];
  enforce: boolean;
  auto_resync: boolean;
  updated_at: string | null;
  updated_by: string | null;
}

export interface PolicyFinding {
  /** servers_differ | not_enabled | not_running | not_reported | ... */
  code: string;
  expected?: string[];
  actual?: string[];
}

export interface HostNtpPolicy {
  policy: NtpPolicy | null;
  conflict: boolean;
  findings: PolicyFinding[];
  compliant: boolean | null;
  apply_status: string | null;
  apply_error: string | null;
  configured_servers: string[] | null;
  enabled: boolean | null;
}

export const getNtpPolicies = async (): Promise<{ policies: NtpPolicy[]; max_servers: number }> =>
  (await axiosInstance.get("/api/v1/time-sync/ntp-policies")).data;

export const setNtpPolicy = async (policy: {
  scope_kind: PolicyScope;
  scope_ref: string;
  servers: string[];
  enforce: boolean;
  auto_resync: boolean;
}): Promise<NtpPolicy> =>
  (await axiosInstance.put("/api/v1/time-sync/ntp-policies", policy)).data;

export const clearNtpPolicy = async (scopeKind: PolicyScope, scopeRef: string): Promise<void> => {
  await axiosInstance.delete("/api/v1/time-sync/ntp-policies", {
    params: { scope_kind: scopeKind, scope_ref: scopeRef },
  });
};
