// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

import { describe, expect, test } from "vitest";
import type { TFunction } from "i18next";
import { t as mockT } from "../TimeSync/_i18nMock";
import {
  metricsText,
  reasonText,
  reasonsText,
  statusColor,
  statusHelp,
  statusLabel,
  transitionText,
} from "../../../Components/HardwareHealth/hardwareHealthLabels";
import { needingAttention, STATUS_ORDER } from "../../../Services/hardwareHealth";
import { event } from "./_fixtures";

const t = mockT as unknown as TFunction;

describe("hardware health labels", () => {
  test("reasons are worded from their codes and parameters", () => {
    // ``count`` is passed as ``n``: i18next would treat ``count`` as a plural
    expect(reasonText(t, { code: "media_errors", count: 19 })).toBe(
      "Media and data integrity errors: 19",
    );
    expect(reasonText(t, { code: "device_errors", read: 0, write: 0, cksum: 211 })).toBe(
      "Device errors: 0 read, 0 write, 211 checksum",
    );
    expect(reasonText(t, { code: "failed_members", members: ["loop11", "loop12"] })).toBe(
      "Failed members: loop11, loop12",
    );
    expect(reasonText(t, { code: "temperature_critical", value: 95, limit: 90 })).toBe(
      "95 C, at or above its critical limit of 90 C",
    );
    expect(
      reasonsText(t, [{ code: "smart_failed" }, { code: "reallocated_sectors", count: 48 }]),
    ).toBe("The SMART overall health check failed; Reallocated sectors: 48");
  });

  test("what the operating system announced", () => {
    expect(
      reasonText(t, { code: "os_storage_event", source: "kernel", text: "Buffer I/O error on dev dm-1" }),
    ).toBe("Storage error reported by the operating system: Buffer I/O error on dev dm-1");
    expect(reasonText(t, { code: "os_power_event", source: "eventlog", text: "Kernel-Power 41" })).toBe(
      "Unexpected loss of power reported by the operating system: Kernel-Power 41",
    );
  });

  test("btrfs, machine checks, vendor RAID and the BMC log are worded", () => {
    expect(
      reasonsText(t, [
        { code: "machine_checks_fatal", count: 2 },
        { code: "sel_events", count: 3, last: "Power Supply AC lost" },
        { code: "controller_status", status: "Needs Attention" },
      ]),
    ).toBe(
      "Uncorrected hardware errors (machine checks) in the last 24 hours: 2; "
        + "Hardware problems in the BMC event log in the last 24 hours: 3. Most recent: Power Supply AC lost; "
        + "RAID controller status: Needs Attention",
    );
    expect(
      reasonsText(t, [
        {
          code: "btrfs_device_errors", device: "/dev/loop11",
          write: 0, read: 0, flush: 0, corruption: 25600, generation: 0,
        },
      ]),
    ).toContain("/dev/loop11: errors since the counters were last reset");
  });

  test("an object parameter is shown as JSON, not [object Object]", () => {
    expect(
      reasonText(t, { code: "controller_status", status: { state: "degraded", slot: 2 } }),
    ).toBe('RAID controller status: {"state":"degraded","slot":2}');
    expect(reasonText(t, { code: "controller_status", status: true })).toBe(
      "RAID controller status: true",
    );
  });

  test("a code from a newer agent shows as itself", () => {
    expect(reasonText(t, { code: "quantum_flux" })).toBe("quantum_flux");
  });

  test("not reported is never healthy", () => {
    expect(statusLabel(t, "unmeasured")).toBe("Not reported");
    expect(statusColor("unmeasured")).toBe("default");
    expect(statusColor("ok")).toBe("success");
    expect(statusColor("gone")).toBe("error");
  });

  test("transitions and readings", () => {
    expect(transitionText(t, event())).toBe("New: Warning");
    expect(transitionText(t, event({ from_state: "warning", to_state: "ok" }))).toBe(
      "Warning -> Healthy",
    );
    expect(transitionText(t, event({ from_state: "ok", to_state: "gone" }))).toBe(
      "Healthy -> No longer reported",
    );
    expect(metricsText(t, { temperature_c: 39.85, percent_used: 5, power_on_hours: 16161 })).toBe(
      "39.85 C, 5% worn, Power-on hours: 16161",
    );
    expect(metricsText(t, {})).toBe("");
  });
});

describe("a host with no physical hardware (a VM)", () => {
  test("is neutral, ordered last, and says why", () => {
    expect(statusLabel(t, "none")).toBe("No physical hardware");
    expect(statusColor("none")).toBe("default");
    expect(statusHelp(t, "none")).toMatch(/virtual machine/);
    expect(STATUS_ORDER[STATUS_ORDER.length - 1]).toBe("none");
    expect(needingAttention({ none: 3, ok: 1 })).toBe(0);
  });
});
