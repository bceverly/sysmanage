// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { vi, beforeEach, describe, test, expect } from "vitest";

vi.mock("react-i18next", async () => {
  const { t } = await import("./_i18nMock");
  return { useTranslation: () => ({ t, i18n: { language: "en" } }) };
});

vi.mock("../../../Services/timeSync", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../../Services/timeSync")>();
  return { ...actual, getFleetClocks: vi.fn() };
});

import { getFleetClocks } from "../../../Services/timeSync";
import type { FleetClock, FleetClocks } from "../../../Services/timeSync";
import TimeSync from "../../../Pages/TimeSync";

const bounds = { warning_ms: 1000, critical_ms: 5000, source: "default" as const, ref: "" };
const host = (fqdn: string, over: Partial<FleetClock>): FleetClock => ({
  host_id: fqdn,
  fqdn,
  status: "ok",
  bounds,
  measured: { offset_ms: 1, rtt_ms: 20, samples: 9, method: "exchange", measured_at: null },
  service_ok: true,
  time_service: "chrony",
  time_source: "ntp.lab",
  site_id: null,
  site_name: null,
  tags: [],
  policy_compliant: null,
  policy_findings: [],
  ...over,
});

const FLEET: FleetClocks = {
  server: { reference: "pool.ntp.org", offset_ms: -1.7, verified: true, reason: null, checked_at: 0 },
  counts: { critical: 1, warning: 1, ok: 1 },
  hosts: [
    host("x13s.lab", {
      status: "critical",
      measured: { offset_ms: 7200000, rtt_ms: null, samples: 1, method: "timestamp", measured_at: null },
      time_service: "w32time",
      service_ok: false,
    }),
    host("mac.lab", { status: "warning", tags: [{ id: "t1", name: "laptops" }] }),
    host("beast.lab", {}),
  ],
};

const renderPage = () =>
  render(
    <MemoryRouter>
      <TimeSync />
    </MemoryRouter>,
  );

describe("Time Sync page", () => {
  beforeEach(() => {
    vi.mocked(getFleetClocks).mockResolvedValue(FLEET);
  });

  test("shows the server's clock first and every host, worst first", async () => {
    renderPage();
    expect(await screen.findByTestId("server-clock")).toHaveTextContent("-1.7 ms from pool.ntp.org");
    const links = screen.getAllByRole("link").map((a) => a.textContent);
    expect(links).toEqual(["x13s.lab", "mac.lab", "beast.lab"]);
    expect(screen.getByText("+2.0 h")).toBeInTheDocument();
    expect(screen.getByText("Windows Time (not running or not synchronized)")).toBeInTheDocument();
  });

  test("a status chip filters the list, and a second click clears it", async () => {
    renderPage();
    const chip = await screen.findByText("Critical: 1");
    fireEvent.click(chip);
    await waitFor(() => expect(screen.getAllByRole("link")).toHaveLength(1));
    fireEvent.click(chip);
    await waitFor(() => expect(screen.getAllByRole("link")).toHaveLength(3));
  });

  test("the host search filters by name", async () => {
    renderPage();
    await screen.findByTestId("server-clock");
    fireEvent.change(screen.getByLabelText("Host"), { target: { value: "MAC" } });
    await waitFor(() => expect(screen.getAllByRole("link").map((a) => a.textContent)).toEqual(["mac.lab"]));
  });

  test("a load failure says so", async () => {
    vi.mocked(getFleetClocks).mockRejectedValue(new Error("down"));
    renderPage();
    expect(await screen.findByText("Could not load the fleet clocks.")).toBeInTheDocument();
  });

  test("an empty fleet says so", async () => {
    vi.mocked(getFleetClocks).mockResolvedValue({ ...FLEET, counts: {}, hosts: [] });
    renderPage();
    expect(await screen.findByText("There are no approved hosts yet.")).toBeInTheDocument();
  });
});
