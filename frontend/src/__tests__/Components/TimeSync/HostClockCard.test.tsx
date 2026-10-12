// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

import { render, screen } from "@testing-library/react";
import { vi, describe, test, expect } from "vitest";

vi.mock("react-i18next", async () => {
  const { t } = await import("./_i18nMock");
  return { useTranslation: () => ({ t, i18n: { language: "en" } }) };
});

vi.mock("../../../Services/timeSync", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../../Services/timeSync")>();
  return { ...actual, getHostClock: vi.fn() };
});

vi.mock("@mui/x-charts/LineChart", () => ({
  LineChart: ({ children }: { children?: unknown }) => <div data-testid="chart">{children as never}</div>,
}));
vi.mock("@mui/x-charts/ChartsReferenceLine", () => ({
  ChartsReferenceLine: () => null,
}));

import { getHostClock } from "../../../Services/timeSync";
import type { HostClock } from "../../../Services/timeSync";
import HostClockCard from "../../../Components/TimeSync/HostClockCard";

const CLOCK: HostClock = {
  status: "warning",
  bounds: { warning_ms: 1000, critical_ms: 5000, source: "tag", ref: "t1" },
  server: { reference: "pool.ntp.org", offset_ms: 0.4, verified: true, reason: null, checked_at: 0 },
  service_ok: false,
  measured: { offset_ms: 1330, rtt_ms: 21.5, samples: 9, method: "exchange", measured_at: "2026-10-12T12:00:00" },
  time_service: {
    service: "w32time",
    running: false,
    synchronized: null,
    source: null,
    stratum: null,
    reported_offset_ms: null,
    reported_at: "2026-10-12T12:00:00",
  },
  history: [
    { at: "2026-10-12T11:45:00", offset_ms: 1300, rtt_ms: 20, method: "exchange" },
    { at: "2026-10-12T12:00:00", offset_ms: 1330, rtt_ms: 21, method: "exchange" },
  ],
};

describe("HostClockCard", () => {
  test("shows the measurement beside the service's claim", async () => {
    vi.mocked(getHostClock).mockResolvedValue(CLOCK);
    render(<HostClockCard hostId="h1" />);
    expect(await screen.findByText("Warning")).toBeInTheDocument();
    expect(screen.getByText("+1.33 s ahead of the server")).toBeInTheDocument();
    expect(screen.getByText("Bounds 1.00 s / 5.00 s (Tag)")).toBeInTheDocument();
    expect(screen.getByText(/not running or not synchronized, so its clock will drift/)).toBeInTheDocument();
    expect(screen.getByText("Windows Time")).toBeInTheDocument();
    expect(screen.getAllByText("Not reported").length).toBeGreaterThan(0);
    expect(screen.getByTestId("chart")).toBeInTheDocument();
  });

  test("an unmeasured host says so, with no chart", async () => {
    vi.mocked(getHostClock).mockResolvedValue({
      ...CLOCK,
      status: "unmeasured",
      service_ok: null,
      measured: null,
      time_service: null,
      history: [],
    });
    render(<HostClockCard hostId="h1" />);
    expect(await screen.findByText("Not measured")).toBeInTheDocument();
    expect(screen.queryByTestId("chart")).toBeNull();
    expect(screen.getByText(/fills in as the host stays connected/)).toBeInTheDocument();
  });

  test("a load failure says so", async () => {
    vi.mocked(getHostClock).mockRejectedValue(new Error("down"));
    render(<HostClockCard hostId="h1" />);
    expect(await screen.findByText("Could not load this host's clock.")).toBeInTheDocument();
  });
});
