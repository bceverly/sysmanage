// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

// The backup window's UTC start hour, shown on the viewer's own clock.

import { describe, test, expect } from "vitest";
import { localWindow } from "../../../Components/Backups/windowLocalTime";

const winter = new Date(Date.UTC(2026, 10, 2, 12));
const summer = new Date(Date.UTC(2026, 6, 1, 12));

describe("localWindow", () => {
  test("7 UTC is 2 AM to 8 AM in New York in winter", () => {
    expect(localWindow(7, "en-US", winter, "America/New_York")).toEqual({ start: "2:00 AM", end: "8:00 AM" });
  });

  test("uses the offset of the day it is shown (daylight saving time)", () => {
    expect(localWindow(7, "en-US", summer, "America/New_York")).toEqual({ start: "3:00 AM", end: "9:00 AM" });
  });

  test("a window that crosses midnight wraps the end hour", () => {
    expect(localWindow(22, "en-US", winter, "UTC")).toEqual({ start: "10:00 PM", end: "4:00 AM" });
  });

  test("no hint without a valid hour", () => {
    for (const hour of [null, undefined, -1, 24, 1.5, Number.NaN]) {
      expect(localWindow(hour, "en-US", winter, "UTC")).toBeNull();
    }
  });
});
