// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

// Commands a maintenance window is holding must be visible: a banner on the
// host page, a "pending" toast for the action that queued one, and a list on
// the Maintenance Windows page.  Production, 2026-10-16: Ubuntu Pro "Attach"
// said "requested" and then nothing happened, so it looked broken.

import React from "react";
import { act, fireEvent, render, renderHook, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { beforeEach, expect, test, vi } from "vitest";

vi.mock("react-i18next", () => {
  const t = (key: string, fallback?: string, opts?: Record<string, unknown>) => {
    let s = fallback || key;
    for (const [k, v] of Object.entries(opts ?? {})) {
      s = s.replace(new RegExp(`{{${k}}}`, "g"), String(v));
    }
    return s;
  };
  return { useTranslation: () => ({ t, i18n: { language: "en" } }) };
});

vi.mock("../../Services/maintenanceWindows", () => ({
  maintenanceWindowsService: {
    hostStatus: vi.fn(),
    createOverride: vi.fn(),
    listHeld: vi.fn(),
    cancelHeld: vi.fn(),
  },
}));

import { maintenanceWindowsService } from "../../Services/maintenanceWindows";
import type { HeldCommand, HostWindowStatus } from "../../Services/maintenanceWindows";
import HeldCommandsBanner from "../../Components/HostDetail/HeldCommandsBanner";
import { pendingNotice, useHeldAwareNotices } from "../../Components/HostDetail/useHeldCommands";
import HeldCommandsPanel from "../../Components/MaintenanceWindows/HeldCommandsPanel";
import { heldCommandText } from "../../Components/MaintenanceWindows/heldCommandText";

const svc = vi.mocked(maintenanceWindowsService);
const t = ((key: string, fallback?: string, opts?: Record<string, unknown>) => {
  let s = fallback || key;
  for (const [k, v] of Object.entries(opts ?? {})) s = s.replace(`{{${k}}}`, String(v));
  return s;
}) as never;

const blocked = (count: number): HostWindowStatus => ({
  state: "blocked",
  override: null,
  active_blackout: null,
  next_window: { id: "w1", name: "Server Updates", starts_at: "2026-10-17T02:00:00" },
  held_commands: { count, oldest_at: null },
});

beforeEach(() => vi.clearAllMocks());

test("the pending notice exists only while a window is holding changes", () => {
  expect(pendingNotice(blocked(0), t)).toMatch(/Pending the next maintenance window \('Server Updates'/);
  expect(pendingNotice({ ...blocked(0), state: "in_window" }, t)).toBeNull();
  expect(pendingNotice({ ...blocked(0), state: "override" }, t)).toBeNull();
  expect(pendingNotice(null, t)).toBeNull();
});

test("the banner shows the count and offers the override", () => {
  render(<HeldCommandsBanner hostId="h1" status={blocked(5)} onReleased={vi.fn()} />);
  expect(screen.getByTestId("held-commands-banner")).toHaveTextContent(
    "5 commands are waiting for the 'Server Updates' maintenance window",
  );
  fireEvent.click(screen.getByText("Emergency override"));
  expect(screen.getByText("Override")).toBeInTheDocument();
});

test("no held commands, no banner", () => {
  const { container } = render(
    <HeldCommandsBanner hostId="h1" status={blocked(0)} onReleased={vi.fn()} />,
  );
  expect(container).toBeEmptyDOMElement();
});

const notices = (status: HostWindowStatus | null) => {
  const setters = {
    setSnackbarMessage: vi.fn(),
    setSnackbarSeverity: vi.fn(),
    setSnackbarOpen: vi.fn(),
    refresh: vi.fn().mockResolvedValue(status),
  };
  const { result } = renderHook(() => useHeldAwareNotices({ t, ...setters }));
  return { held: result.current, ...setters };
};

test("a success toast becomes 'pending' while the host is held", async () => {
  const s = notices(blocked(1));
  act(() => {
    s.held.setSnackbarMessage("Ubuntu Pro attach requested");
    s.held.setSnackbarSeverity("success");
    s.held.setSnackbarOpen(true);
  });
  await waitFor(() => expect(s.setSnackbarOpen).toHaveBeenCalledWith(true));
  expect(s.setSnackbarMessage).toHaveBeenLastCalledWith(
    expect.stringMatching(/^Pending the next maintenance window \('Server Updates'/),
  );
  expect(s.setSnackbarSeverity).toHaveBeenLastCalledWith("warning");
});

test("an unrestricted host keeps today's toast", async () => {
  const s = notices({ ...blocked(0), state: "unrestricted", next_window: null });
  act(() => {
    s.held.setSnackbarMessage("Ubuntu Pro attach requested");
    s.held.setSnackbarSeverity("success");
    s.held.setSnackbarOpen(true);
  });
  await waitFor(() => expect(s.setSnackbarOpen).toHaveBeenCalledWith(true));
  expect(s.setSnackbarMessage).toHaveBeenLastCalledWith("Ubuntu Pro attach requested");
});

test("an unreadable status keeps today's toast; errors pass straight through", async () => {
  const s = notices(null);
  act(() => {
    s.held.setSnackbarMessage("Failed to attach");
    s.held.setSnackbarSeverity("error");
    s.held.setSnackbarOpen(true);
  });
  expect(s.refresh).not.toHaveBeenCalled();
  expect(s.setSnackbarOpen).toHaveBeenCalledWith(true);
});

const item = (over: Partial<HeldCommand> = {}): HeldCommand => ({
  id: "m1",
  host_id: "h1",
  fqdn: "milsurpmonitor",
  command_type: "apply_updates",
  details: { packages: { names: ["cups", "snapd"], count: 4 } },
  queued_at: "2026-10-16T19:41:54",
  rechecks_at: null,
  expires_at: "2026-10-23T19:41:54",
  retry_count: 0,
  max_retries: 3,
  release: { state: "blocked", blackout: null, window: { id: "w1", name: "Server Updates", starts_at: "2026-10-17T02:00:00" } },
  ...over,
});

test("commands read as words, packages summarized", () => {
  expect(heldCommandText(t, item())).toBe("Apply updates: cups, snapd (+2)");
  expect(heldCommandText(t, item({ command_type: "ubuntu_pro_attach", details: {} }))).toBe("Ubuntu Pro attach");
  expect(heldCommandText(t, item({ command_type: "brand_new_thing", details: {} }))).toBe("brand_new_thing");
});

test("the held list links the host and cancels a command", async () => {
  svc.listHeld.mockResolvedValue({ total: 1, items: [item()] });
  svc.cancelHeld.mockResolvedValue(undefined);
  render(<MemoryRouter><HeldCommandsPanel /></MemoryRouter>);
  expect(await screen.findByText("milsurpmonitor")).toHaveAttribute("href", "/hosts/h1");
  expect(screen.getByText("Apply updates: cups, snapd (+2)")).toBeInTheDocument();
  fireEvent.click(screen.getAllByText("Cancel command")[0]);
  await act(async () => {
    fireEvent.click(screen.getAllByText("Cancel command").at(-1) as HTMLElement);
  });
  expect(svc.cancelHeld).toHaveBeenCalledWith("m1");
});

test("an empty queue says so", async () => {
  svc.listHeld.mockResolvedValue({ total: 0, items: [] });
  render(<MemoryRouter><HeldCommandsPanel /></MemoryRouter>);
  expect(await screen.findByText("No commands are waiting for a window.")).toBeInTheDocument();
});
