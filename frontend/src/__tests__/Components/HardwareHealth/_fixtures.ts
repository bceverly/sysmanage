// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

// Hardware health shaped as the server returns it; the drive is the lab
// FreeBSD box's Crucial P1 with its 19 media errors.

import type {
  HardwareComponent,
  HardwareEvent,
  HostHardware,
} from "../../../Services/hardwareHealth";

export const drive = (over: Partial<HardwareComponent> = {}): HardwareComponent => ({
  kind: "drive",
  id: "nvme0",
  name: "CT1000P1SSD8",
  state: "warning",
  reasons: [{ code: "media_errors", count: 19 }],
  metrics: { temperature_c: 39.85, percent_used: 5, power_on_hours: 16161 },
  source: "nvmecontrol",
  state_since: "2026-10-13T20:00:00",
  last_seen_at: "2026-10-13T21:00:00",
  ...over,
});

export const sensor = (id: string, over: Partial<HardwareComponent> = {}): HardwareComponent => ({
  kind: "sensor",
  id,
  name: `ACPI ${id}`,
  state: "ok",
  reasons: [],
  metrics: { temperature_c: 40.1 },
  source: "sysctl",
  state_since: null,
  last_seen_at: null,
  ...over,
});

export const event = (over: Partial<HardwareEvent> = {}): HardwareEvent => ({
  id: "e1",
  host_id: "h1",
  fqdn: "freebsd.lab",
  kind: "drive",
  component_id: "nvme0",
  name: "CT1000P1SSD8",
  from_state: null,
  to_state: "warning",
  reasons: [{ code: "media_errors", count: 19 }],
  occurred_at: "2026-10-13T20:00:00",
  acknowledged_at: null,
  acknowledged_by: null,
  resolved_at: null,
  resolved_by: null,
  note: null,
  ...over,
});

export const hostHardware = (over: Partial<HostHardware> = {}): HostHardware => ({
  status: "warning",
  reported_at: "2026-10-13T21:00:00",
  sources: [
    { name: "nvmecontrol", status: "ran" },
    { name: "gmirror", status: "absent", detail: "class not loaded" },
  ],
  components: [drive(), sensor("tz0"), sensor("tz1"), sensor("tz2")],
  events: [event()],
  ...over,
});
