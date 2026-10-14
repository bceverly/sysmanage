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

/** A host's standing: a component state, or never reported / not recently. */
export type HardwareStatus = ComponentState | "unmeasured" | "stale";

/** Worst first -- the order the fleet view sorts by. */
export const STATUS_ORDER: HardwareStatus[] = [
  "failed",
  "warning",
  "stale",
  "unknown",
  "unmeasured",
  "ok",
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
