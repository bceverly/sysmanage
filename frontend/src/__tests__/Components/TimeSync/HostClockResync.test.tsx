// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { vi, beforeEach, describe, test, expect } from "vitest";

vi.mock("react-i18next", async () => {
  const { t } = await import("./_i18nMock");
  return { useTranslation: () => ({ t, i18n: { language: "en" } }) };
});
vi.mock("../../../Services/permissions", () => ({
  hasPermission: vi.fn(),
  SecurityRoles: { RESYNC_HOST_CLOCK: "Resync Host Clock" },
}));
vi.mock("../../../Services/timeSync", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../../Services/timeSync")>();
  return { ...actual, getResyncs: vi.fn(), resyncHost: vi.fn() };
});

import { hasPermission } from "../../../Services/permissions";
import { getResyncs, resyncHost } from "../../../Services/timeSync";
import type { ClockResync } from "../../../Services/timeSync";
import HostClockResync from "../../../Components/TimeSync/HostClockResync";

const row = (over: Partial<ClockResync>): ClockResync => ({
  id: "r1",
  host_id: "h1",
  batch_id: null,
  status: "succeeded",
  requested_by: "admin",
  requested_at: "2026-10-12T12:00:00",
  sent_at: null,
  finished_at: null,
  offset_before_ms: 1330,
  reported_after_ms: 0.8,
  service: "w32time",
  method: "w32tm /resync",
  error: null,
  detail: null,
  ...over,
});

describe("HostClockResync", () => {
  beforeEach(() => {
    vi.mocked(hasPermission).mockResolvedValue(true);
    vi.mocked(getResyncs).mockResolvedValue([]);
  });

  test("resynchronizes on request and shows the outcome", async () => {
    vi.mocked(resyncHost).mockResolvedValue(row({ status: "sent" }));
    render(<HostClockResync hostId="h1" />);
    const button = await screen.findByText("Resynchronize now");
    await waitFor(() => expect(button.closest("button")).not.toBeDisabled());
    vi.mocked(getResyncs).mockResolvedValue([row({})]);
    fireEvent.click(button);
    await waitFor(() => expect(resyncHost).toHaveBeenCalledWith("h1"));
    expect(await screen.findByText("Resynchronized")).toBeInTheDocument();
    expect(screen.getByText("Service now reports +0.8 ms")).toBeInTheDocument();
  });

  test("a refusal says why in words", async () => {
    vi.mocked(getResyncs).mockResolvedValue([
      row({ status: "unsupported", error: "not_privileged", reported_after_ms: null }),
    ]);
    render(<HostClockResync hostId="h1" />);
    expect(await screen.findByText("Not possible")).toBeInTheDocument();
    expect(screen.getByText(/administrator rights/)).toBeInTheDocument();
  });

  test("the button is off without the role and while one is running", async () => {
    vi.mocked(hasPermission).mockResolvedValue(false);
    render(<HostClockResync hostId="h1" />);
    expect((await screen.findByText("Resynchronize now")).closest("button")).toBeDisabled();
  });

  test("an already running resync is explained", async () => {
    vi.mocked(resyncHost).mockRejectedValue({
      response: { data: { detail: { code: "already_running" } } },
    });
    render(<HostClockResync hostId="h1" />);
    const button = await screen.findByText("Resynchronize now");
    await waitFor(() => expect(button.closest("button")).not.toBeDisabled());
    fireEvent.click(button);
    expect(await screen.findByText(/already in progress/)).toBeInTheDocument();
  });
});
