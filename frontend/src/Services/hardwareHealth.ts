// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

// Hardware health (Phase 23.1).  Each host's agent judges its own drives,
// arrays, pools, sensors and memory from the operating system's sources; the
// server keeps the current picture and every state change.  Reasons travel
// as codes with parameters, which the UI words.

import axiosInstance from "./api";

export type ComponentKind = "drive" | "array" | "pool" | "sensor" | "memory";
export type ComponentState = "ok" | "warning" | "failed" | "unknown";

/** A host's standing: a component state, never reported / not recently, or
 * "none" -- it reported and has no physical hardware to watch (a VM). */
export type HardwareStatus = ComponentState | "unmeasured" | "stale" | "none";

/** Worst first -- the order the fleet view sorts by. */
export const STATUS_ORDER: HardwareStatus[] = [
  "failed",
  "warning",
  "stale",
  "unknown",
  "unmeasured",
  "ok",
  "none",
];

export interface Reason {
  code: string;
  [param: string]: unknown;
}

export interface HardwareComponent {
  kind: ComponentKind;
  id: string;
  name: string;
  state: ComponentState;
  reasons: Reason[];
  metrics: Record<string, string | number | boolean>;
  source: string | null;
  state_since: string | null;
  last_seen_at: string | null;
}

export interface HardwareSource {
  name: string;
  status: "ran" | "absent" | "failed";
  detail?: string;
}

export interface HardwareEvent {
  id: string;
  host_id: string;
  fqdn?: string | null;
  /** ``system``: the operating system announced it (kernel log, devd, the
   *  Windows System log); ``component_id`` is then the category. */
  kind: ComponentKind | "system";
  component_id: string;
  name: string | null;
  from_state: ComponentState | null;
  /** A component state, or ``gone``: no longer reported. */
  to_state: ComponentState | "gone";
  reasons: Reason[];
  occurred_at: string;
  acknowledged_at: string | null;
  acknowledged_by: string | null;
  resolved_at: string | null;
  resolved_by: string | null;
  note: string | null;
}

/** The last smartmontools install asked of a host (S6). */
export interface ToolInstall {
  package: string;
  status: "queued" | "succeeded" | "failed";
  attempts: number;
  requested_by: string | null;
  requested_at: string | null;
  finished_at: string | null;
  last_error: string | null;
}

export interface HostHardware {
  status: HardwareStatus;
  reported_at: string | null;
  sources: HardwareSource[];
  components: HardwareComponent[];
  events: HardwareEvent[];
  /** A drive can only be read with smartctl, which is not installed. */
  smartmontools?: { recommended: boolean; install: ToolInstall | null };
  /** The host's own temperature warning limit (C); null = each device's. */
  temperature_limit_c?: number | null;
}

export interface FleetHost {
  host_id: string;
  fqdn: string;
  platform: string | null;
  status: HardwareStatus;
  reported_at: string | null;
  component_counts: Partial<Record<ComponentState, number>>;
  problems: HardwareComponent[];
  site_id: string | null;
  site_name: string | null;
  tags: { id: string; name: string }[];
}

export interface FleetHardware {
  counts: Partial<Record<HardwareStatus, number>>;
  hosts: FleetHost[];
}

export interface HardwareSummary {
  total: number;
  counts: Partial<Record<HardwareStatus, number>>;
}

export const getFleetHardware = async (): Promise<FleetHardware> =>
  (await axiosInstance.get<FleetHardware>("/api/v1/hardware-health/hosts")).data;

export const getHardwareSummary = async (): Promise<HardwareSummary> =>
  (await axiosInstance.get<HardwareSummary>("/api/v1/hardware-health/summary"))
    .data;

export const getHostHardware = async (hostId: string): Promise<HostHardware> =>
  (
    await axiosInstance.get<HostHardware>(
      `/api/v1/host/${encodeURIComponent(hostId)}/hardware-health`,
    )
  ).data;

export const getHardwareEvents = async (
  openOnly = true,
  hostId?: string,
): Promise<HardwareEvent[]> =>
  (
    await axiosInstance.get<{ events: HardwareEvent[] }>(
      "/api/v1/hardware-health/events",
      { params: { open: openOnly, ...(hostId ? { host_id: hostId } : {}) } },
    )
  ).data.events;

/** The open events, plus how many there are beyond the page ("Select all N"). */
export const getHardwareEventsPage = async (
  hostId?: string,
): Promise<{ events: HardwareEvent[]; total: number }> => {
  const { data } = await axiosInstance.get<{ events: HardwareEvent[]; total?: number }>(
    "/api/v1/hardware-health/events",
    { params: { open: true, ...(hostId ? { host_id: hostId } : {}) } },
  );
  return { events: data.events, total: data.total ?? data.events.length };
};

export type BulkScope =
  | { eventIds: string[] }
  | { allOpen: true; hostId?: string };

/**
 * Acknowledge or resolve many events at once.  "All open" is changed by the
 * server in batches (at most 1000 a call); this repeats until none remain,
 * with a ceiling so a misbehaving server cannot loop it forever.
 */
export const bulkChangeHardwareEvents = async (
  action: "acknowledge" | "resolve",
  scope: BulkScope,
): Promise<{ changed: number; skipped: number }> => {
  const url = `/api/v1/hardware-health/events/${action}`;
  const body = "eventIds" in scope
    ? { event_ids: scope.eventIds }
    : { all_open: true, ...(scope.hostId ? { host_id: scope.hostId } : {}) };
  let changed = 0;
  let skipped = 0;
  for (let round = 0; round < 100; round += 1) {
    const { data } = await axiosInstance.post<Record<string, number>>(url, body);
    changed += data[`${action}d`] ?? 0;
    skipped += data.skipped ?? 0;
    if (!data.remaining || !("allOpen" in scope)) {
      break;
    }
  }
  return { changed, skipped };
};

export const changeHardwareEvent = async (
  eventId: string,
  action: "acknowledge" | "resolve",
  note?: string,
): Promise<HardwareEvent> =>
  (
    await axiosInstance.post<HardwareEvent>(
      `/api/v1/hardware-health/events/${encodeURIComponent(eventId)}/${action}`,
      { note: note || null },
    )
  ).data;

/** How many hosts need attention: failed or warning. */
export const needingAttention = (counts: HardwareSummary["counts"]): number =>
  (counts.failed ?? 0) + (counts.warning ?? 0);

export interface SmartmontoolsStatus {
  /** Automatic install is Enterprise. */
  licensed: boolean;
  /** An administrator consented to the automatic install. */
  auto: boolean;
  hosts: {
    host_id: string;
    fqdn: string;
    platform: string | null;
    install: ToolInstall | null;
  }[];
}

export const getSmartmontools = async (): Promise<SmartmontoolsStatus> =>
  (
    await axiosInstance.get<SmartmontoolsStatus>(
      "/api/v1/hardware-health/smartmontools",
    )
  ).data;

/** Only hosts it is recommended for are installed; the rest are skipped. */
export const installSmartmontools = async (
  hostIds: string[],
): Promise<{ queued: number; skipped: number }> =>
  (
    await axiosInstance.post<{ queued: number; skipped: number }>(
      "/api/v1/hardware-health/smartmontools/install",
      { host_ids: hostIds },
    )
  ).data;

export const setSmartmontoolsAuto = async (
  auto: boolean,
): Promise<{ auto: boolean }> =>
  (
    await axiosInstance.put<{ auto: boolean }>(
      "/api/v1/hardware-health/smartmontools",
      { auto },
    )
  ).data;

/** The host's own temperature warning limit (C); null clears it.  It takes
 * effect at the host's next report. */
export const setTemperatureLimit = async (
  hostId: string,
  limitC: number | null,
): Promise<{ temperature_limit_c: number | null }> =>
  (
    await axiosInstance.put<{ temperature_limit_c: number | null }>(
      `/api/v1/host/${encodeURIComponent(hostId)}/hardware-health/temperature-limit`,
      { limit_c: limitC },
    )
  ).data;
