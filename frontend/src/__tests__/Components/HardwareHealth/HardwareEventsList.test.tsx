// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { vi, beforeEach, describe, test, expect } from "vitest";

vi.mock("react-i18next", async () => {
  const { t } = await import("../TimeSync/_i18nMock");
  return { useTranslation: () => ({ t, i18n: { language: "en" } }) };
});
vi.mock("../../../Services/permissions", () => ({
  hasPermission: vi.fn(),
  SecurityRoles: { MANAGE_HARDWARE_HEALTH: "Manage Hardware Health" },
}));
vi.mock("../../../Services/hardwareHealth", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../../Services/hardwareHealth")>();
  return { ...actual, changeHardwareEvent: vi.fn() };
});

import { hasPermission } from "../../../Services/permissions";
import { changeHardwareEvent } from "../../../Services/hardwareHealth";
import { ThemeProvider, createTheme } from "@mui/material/styles";
import HardwareEventsList from "../../../Components/HardwareHealth/HardwareEventsList";
import { event } from "./_fixtures";

const renderList = (events = [event()], onChanged = vi.fn()) =>
  render(
    <MemoryRouter>
      <HardwareEventsList events={events} showHost onChanged={onChanged} />
    </MemoryRouter>,
  );

describe("HardwareEventsList", () => {
  beforeEach(() => vi.mocked(changeHardwareEvent).mockReset());

  test("acknowledges with a note", async () => {
    vi.mocked(hasPermission).mockResolvedValue(true);
    vi.mocked(changeHardwareEvent).mockResolvedValue(event());
    const onChanged = vi.fn();
    renderList([event()], onChanged);
    expect(screen.getByText("freebsd.lab")).toBeInTheDocument();
    fireEvent.click(await screen.findByText("Acknowledge"));
    fireEvent.change(screen.getByLabelText("Note (optional)"), {
      target: { value: "replacement ordered" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Acknowledge this event" }));
    await waitFor(() =>
      expect(changeHardwareEvent).toHaveBeenCalledWith("e1", "acknowledge", "replacement ordered"),
    );
    await waitFor(() => expect(onChanged).toHaveBeenCalled());
  });

  test("the action buttons never wrap, whatever the theme says", async () => {
    // The app theme lets every Button wrap anywhere (long translations); on
    // the host card that broke "Acknowledge" into "ACKNOWL / EDGE".
    vi.mocked(hasPermission).mockResolvedValue(true);
    const wrapAnywhere = createTheme({
      components: {
        MuiButton: { styleOverrides: { root: { whiteSpace: "normal", overflowWrap: "anywhere" } } },
      },
    });
    render(
      <ThemeProvider theme={wrapAnywhere}>
        <MemoryRouter>
          <HardwareEventsList events={[event()]} onChanged={vi.fn()} />
        </MemoryRouter>
      </ThemeProvider>,
    );
    for (const label of ["Acknowledge", "Resolve"]) {
      const button = (await screen.findByText(label)).closest("button");
      expect(button).toHaveStyle({ whiteSpace: "nowrap", overflowWrap: "normal" });
    }
  });

  test("without the role there are no buttons; who acted is shown", async () => {
    vi.mocked(hasPermission).mockResolvedValue(false);
    renderList([event({ acknowledged_at: "2026-10-13T21:00:00", acknowledged_by: "ops@lab" })]);
    expect(await screen.findByText("Acknowledged by ops@lab")).toBeInTheDocument();
    expect(screen.queryByText("Acknowledge")).not.toBeInTheDocument();
    expect(screen.queryByText("Resolve")).not.toBeInTheDocument();
  });

  test("an operating-system event names no component", async () => {
    vi.mocked(hasPermission).mockResolvedValue(false);
    renderList([
      event({
        kind: "system",
        component_id: "storage",
        name: "storage",
        reasons: [{ code: "os_storage_event", source: "kernel", text: "Buffer I/O error on dev dm-1" }],
      }),
    ]);
    expect(await screen.findByText("Operating system")).toBeInTheDocument();
    expect(
      screen.getByText("Storage error reported by the operating system: Buffer I/O error on dev dm-1"),
    ).toBeInTheDocument();
  });

  test("an empty list says so", () => {
    vi.mocked(hasPermission).mockResolvedValue(false);
    renderList([]);
    expect(screen.getByText("No hardware events.")).toBeInTheDocument();
  });
});
