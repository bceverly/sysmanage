// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

import { render, screen, fireEvent } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { vi, beforeEach, describe, test, expect } from "vitest";

vi.mock("react-i18next", async () => {
  const { t } = await import("../TimeSync/_i18nMock");
  return { useTranslation: () => ({ t, i18n: { language: "en" } }) };
});
vi.mock("../../../Services/permissions", () => ({
  hasPermission: vi.fn().mockResolvedValue(false),
  SecurityRoles: { MANAGE_HARDWARE_HEALTH: "Manage Hardware Health" },
}));
vi.mock("../../../Services/hardwareHealth", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../../Services/hardwareHealth")>();
  return { ...actual, getHostHardware: vi.fn() };
});

import { getHostHardware } from "../../../Services/hardwareHealth";
import HostHardwareCard from "../../../Components/HardwareHealth/HostHardwareCard";
import { hostHardware } from "./_fixtures";

const renderCard = () =>
  render(
    <MemoryRouter>
      <HostHardwareCard hostId="h1" />
    </MemoryRouter>,
  );

describe("HostHardwareCard", () => {
  beforeEach(() => vi.mocked(getHostHardware).mockClear());

  test("shows the drive and why, folds the healthy sensors away", async () => {
    vi.mocked(getHostHardware).mockResolvedValue(hostHardware());
    renderCard();
    expect(await screen.findByText("CT1000P1SSD8")).toBeInTheDocument();
    expect(screen.getAllByText("Media and data integrity errors: 19").length).toBeGreaterThan(0);
    expect(screen.getByText("39.85 C, 5% worn, Power-on hours: 16161")).toBeInTheDocument();
    expect(screen.queryByText("ACPI tz0")).not.toBeInTheDocument();
    fireEvent.click(screen.getByText("Show 3 healthy sensors"));
    expect(screen.getByText("ACPI tz0")).toBeInTheDocument();
    expect(screen.getByText("gmirror: not present")).toBeInTheDocument();
    expect(screen.getByText("New: Warning")).toBeInTheDocument();
  });

  test("a host that never reported says so -- not healthy", async () => {
    vi.mocked(getHostHardware).mockResolvedValue(
      hostHardware({ status: "unmeasured", reported_at: null, sources: [], components: [], events: [] }),
    );
    renderCard();
    expect(await screen.findByText("Not reported")).toBeInTheDocument();
    expect(screen.getByText(/has never reported its hardware/)).toBeInTheDocument();
  });

  test("a load failure is shown", async () => {
    vi.mocked(getHostHardware).mockRejectedValueOnce(new Error("boom"));
    renderCard();
    expect(await screen.findByText("Could not load the hardware health.")).toBeInTheDocument();
  });
});
