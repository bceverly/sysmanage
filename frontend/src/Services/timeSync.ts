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
