// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

import { describe, expect, test } from "vitest";
import type { TFunction } from "i18next";
import {
  boundsErrorText,
  formatOffset,
  offsetDirection,
  serverClockSeverity,
  serverClockText,
  serviceName,
  statusColor,
  statusLabel,
} from "../../../Components/TimeSync/timeSyncLabels";
import type { ServerClock } from "../../../Services/timeSync";
import { t as mockT } from "./_i18nMock";

const t = mockT as unknown as TFunction;

describe("formatOffset", () => {
  test.each([
    [null, "-"],
    [0, "0.0 ms"],
    [0.43, "+0.4 ms"],
    [-224.2, "-224 ms"],
    [1330, "+1.33 s"],
    [-59_999, "-60.00 s"],
    [720_000, "+12 min"],
    [-7_200_000, "-2.0 h"],
  ])("%s ms reads %s", (ms, text) => {
    expect(formatOffset(t, ms)).toBe(text);
  });
});

test("the direction is said in words", () => {
  expect(offsetDirection(t, 5)).toBe("ahead of the server");
  expect(offsetDirection(t, -5)).toBe("behind the server");
  expect(offsetDirection(t, 0)).toBe("");
});

test("not measured never looks like in sync", () => {
  expect(statusLabel(t, "unmeasured")).toBe("Not measured");
  expect(statusColor("unmeasured")).toBe("default");
  expect(statusColor("stale")).toBe("default");
  expect(statusColor("ok")).toBe("success");
  expect(statusColor("critical")).toBe("error");
});

const server = (over: Partial<ServerClock>): ServerClock => ({
  reference: "pool.ntp.org",
  offset_ms: -1.7,
  verified: true,
  reason: null,
  checked_at: 0,
  ...over,
});

test("the server's own clock, in each state", () => {
  expect(serverClockText(t, server({}))).toContain("-1.7 ms from pool.ntp.org");
  expect(serverClockSeverity(server({}))).toBe("success");
  const off = server({ reason: "server_off", verified: false, offset_ms: 2000 });
  expect(serverClockText(t, off)).toContain("not judged");
  expect(serverClockSeverity(off)).toBe("error");
  const gone = server({ reason: "unreachable", verified: false });
  expect(serverClockText(t, gone)).toContain("could not reach");
  expect(serverClockSeverity(gone)).toBe("warning");
  expect(serverClockText(t, server({ reason: "no_reference", verified: false }))).toContain(
    "No time reference",
  );
});

test("codes and service names are worded", () => {
  expect(boundsErrorText(t, "warning_not_below_critical")).toContain("smaller");
  expect(boundsErrorText(t, null)).toBe("The bounds could not be saved.");
  expect(serviceName(t, "w32time")).toBe("Windows Time");
  expect(serviceName(t, null)).toBe("Not reported");
  expect(serviceName(t, "none")).toBe("No time service");
});
