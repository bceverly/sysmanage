// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

import { render, screen, fireEvent, within } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { vi, beforeEach, describe, test, expect } from "vitest";

vi.mock("react-i18next", async () => {
  const { t } = await import("../TimeSync/_i18nMock");
  return { useTranslation: () => ({ t, i18n: { language: "en" } }) };
});
vi.mock("../../../hooks/useVisiblePolling", () => ({ useVisiblePolling: vi.fn() }));
vi.mock("../../../Services/permissions", () => ({
  hasPermission: vi.fn().mockResolvedValue(false),
  SecurityRoles: { MANAGE_HARDWARE_HEALTH: "Manage Hardware Health" },
}));
vi.mock("../../../Services/hardwareHealth", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../../Services/hardwareHealth")>();
  return {
    ...actual,
    getFleetHardware: vi.fn(),
    getHardwareEvents: vi.fn(),
    getSmartmontools: vi.fn().mockResolvedValue({ licensed: false, auto: false, hosts: [] }),
  };
});

import { getFleetHardware, getHardwareEvents } from "../../../Services/hardwareHealth";
import type { FleetHost } from "../../../Services/hardwareHealth";
import HardwareHealth from "../../../Pages/HardwareHealth";
import { drive, event } from "./_fixtures";

const host = (over: Partial<FleetHost>): FleetHost => ({
  host_id: "h1",
  fqdn: "freebsd.lab",
  platform: "FreeBSD",
  status: "warning",
  reported_at: "2026-10-13T21:00:00",
  component_counts: { warning: 1, ok: 4 },
  problems: [drive()],
  site_id: null,
  site_name: null,
  tags: [],
  ...over,
});

describe("Hardware Health page", () => {
  beforeEach(() => {
    vi.mocked(getFleetHardware).mockResolvedValue({
      counts: { warning: 1, unmeasured: 1, ok: 1 },
      hosts: [
        host({}),
        host({ host_id: "h2", fqdn: "never.lab", status: "unmeasured", problems: [], component_counts: {} }),
        host({ host_id: "h3", fqdn: "beast.lab", status: "ok", problems: [], component_counts: { ok: 9 } }),
      ],
    });
    vi.mocked(getHardwareEvents).mockResolvedValue([event()]);
  });

  test("lists the fleet worst first with why, and the open events", async () => {
    render(<MemoryRouter><HardwareHealth /></MemoryRouter>);
    expect(await screen.findByText("Hardware Health")).toBeInTheDocument();
    expect(screen.getByText("Warning: 1")).toBeInTheDocument();
    expect(screen.getByText("Not reported: 1")).toBeInTheDocument();
    expect(screen.getAllByText("freebsd.lab").length).toBeGreaterThan(0);
    expect(screen.getAllByText(/Media and data integrity errors: 19/).length).toBeGreaterThan(0);
    expect(screen.getByText("Unresolved events")).toBeInTheDocument();
    expect(getHardwareEvents).toHaveBeenCalledWith(true);
  });

  test("a status chip filters the hosts", async () => {
    render(<MemoryRouter><HardwareHealth /></MemoryRouter>);
    fireEvent.click(await screen.findByText("Not reported: 1"));
    const grid = screen.getByRole("grid");
    expect(within(grid).getByText("never.lab")).toBeInTheDocument();
    expect(within(grid).queryByText("beast.lab")).not.toBeInTheDocument();
  });

  test("a load failure is shown", async () => {
    vi.mocked(getFleetHardware).mockRejectedValue(new Error("boom"));
    render(<MemoryRouter><HardwareHealth /></MemoryRouter>);
    expect(await screen.findByText("Could not load the fleet hardware.")).toBeInTheDocument();
  });
});
