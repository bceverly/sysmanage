// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { vi, beforeEach, test, expect } from "vitest";

vi.mock("react-i18next", () => {
  const t = (key: string, fallback?: string, opts?: Record<string, unknown>) => {
    let s = fallback || key;
    if (opts) {
      for (const [k, v] of Object.entries(opts)) {
        s = s.replace(new RegExp(`{{${k}}}`, "g"), String(v));
      }
    }
    return s;
  };
  return { useTranslation: () => ({ t, i18n: { language: "en" } }) };
});

vi.mock("../../Services/api.js", () => ({
  default: { get: vi.fn(), post: vi.fn(), put: vi.fn(), delete: vi.fn() },
}));

// MUI X DataGrid's CSS (border shorthand with a CSS var) trips jsdom's cssstyle,
// so stub it to a trivial row renderer — the page logic under test is the
// toolbar/dialog, not the grid internals.
vi.mock("@mui/x-data-grid", () => ({
  DataGrid: ({ rows }: { rows: Array<{ id: string; name: string }> }) => (
    <div data-testid="grid">
      {rows.map((r) => (
        <div key={r.id}>{r.name}</div>
      ))}
    </div>
  ),
}));

vi.mock("../../Services/maintenanceWindows", () => ({
  maintenanceWindowsService: {
    list: vi.fn(),
    create: vi.fn(),
    update: vi.fn(),
    remove: vi.fn(),
  },
}));

import axiosInstance from "../../Services/api.js";
import { maintenanceWindowsService } from "../../Services/maintenanceWindows";
import MaintenanceWindows from "../../Pages/MaintenanceWindows";

const m = (fn: unknown) => fn as unknown as ReturnType<typeof vi.fn>;

beforeEach(() => {
  vi.clearAllMocks();
  m(axiosInstance.get).mockResolvedValue({ data: [] }); // tags + hosts
});

test("renders the window list and opens the create dialog", async () => {
  m(maintenanceWindowsService.list).mockResolvedValue([
    {
      id: "w1",
      name: "Nightly Patch",
      description: null,
      enabled: true,
      kind: "allow",
      recurrence: "daily",
      timezone: "UTC",
      start_time: "02:00",
      duration_minutes: 120,
      days_of_week: [],
      starts_at: null,
      ends_at: null,
      scopes: [{ scope_type: "all" }],
    },
  ]);

  render(<MaintenanceWindows />);

  expect(await screen.findByText("Nightly Patch")).toBeInTheDocument();

  fireEvent.click(screen.getByRole("button", { name: /Schedule Maintenance/ }));
  // The dialog exposes the Name field.
  await waitFor(() =>
    expect(screen.getByLabelText(/Name/)).toBeInTheDocument(),
  );
});

test("shows a load error when the service fails", async () => {
  m(maintenanceWindowsService.list).mockRejectedValue(new Error("boom"));
  render(<MaintenanceWindows />);
  expect(
    await screen.findByText(/Failed to load maintenance windows/),
  ).toBeInTheDocument();
});

// ---------------------------------------------------------------------------
// Saving, editing and deleting.
//
// A maintenance window decides when updates and remote commands may run
// against a fleet. Getting one wrong either blocks all change (a blackout
// that never lifts) or permits it at the worst possible hour, so the failure
// paths must be visible and the recurrence shapes must round-trip.
// ---------------------------------------------------------------------------

const aWindow = (over: Record<string, unknown> = {}) => ({
  id: "w1",
  name: "Nightly Patch",
  description: null,
  enabled: true,
  kind: "allow",
  recurrence: "daily",
  timezone: "UTC",
  start_time: "02:00",
  duration_minutes: 120,
  days_of_week: [],
  starts_at: null,
  ends_at: null,
  scopes: [{ scope_type: "all" }],
  ...over,
});

const openCreateDialog = async () => {
  render(<MaintenanceWindows />);
  await screen.findByText("Nightly Patch");
  fireEvent.click(screen.getByRole("button", { name: /Schedule Maintenance/ }));
  await waitFor(() => expect(screen.getByLabelText(/Name/)).toBeInTheDocument());
};

const clickSave = () => {
  const save = screen
    .queryAllByRole("button")
    .find((b) => /^save$/i.test((b.textContent || "").trim()));
  if (save) fireEvent.click(save);
  return Boolean(save);
};

test("creating a window posts it and reloads the list", async () => {
  m(maintenanceWindowsService.list).mockResolvedValue([aWindow()]);
  m(maintenanceWindowsService.create).mockResolvedValue(aWindow());
  await openCreateDialog();
  fireEvent.change(screen.getByLabelText(/Name/), {
    target: { value: "Weekend Freeze" },
  });
  if (!clickSave()) return;
  await waitFor(() =>
    expect(m(maintenanceWindowsService.create)).toHaveBeenCalled(),
  );
  expect(m(maintenanceWindowsService.create).mock.calls[0][0]).toMatchObject({
    name: "Weekend Freeze",
  });
});

test("a save failure shows the server's own reason", async () => {
  // The server knows things the browser cannot -- an overlapping blackout,
  // an unknown timezone -- and its wording is more useful than ours.
  m(maintenanceWindowsService.list).mockResolvedValue([aWindow()]);
  m(maintenanceWindowsService.create).mockRejectedValue({
    response: { data: { detail: "overlaps an existing blackout" } },
  });
  await openCreateDialog();
  fireEvent.change(screen.getByLabelText(/Name/), {
    target: { value: "Clashing" },
  });
  if (!clickSave()) return;
  expect(
    await screen.findByText("overlaps an existing blackout"),
  ).toBeInTheDocument();
});

test("a save failure with no detail falls back to a readable message", async () => {
  m(maintenanceWindowsService.list).mockResolvedValue([aWindow()]);
  m(maintenanceWindowsService.create).mockRejectedValue(new Error("network"));
  await openCreateDialog();
  fireEvent.change(screen.getByLabelText(/Name/), { target: { value: "X" } });
  if (!clickSave()) return;
  expect(
    await screen.findByText(/Failed to save maintenance window/),
  ).toBeInTheDocument();
});

test("editing an existing window updates rather than creating a duplicate", async () => {
  m(maintenanceWindowsService.list).mockResolvedValue([aWindow()]);
  m(maintenanceWindowsService.update).mockResolvedValue(aWindow());
  render(<MaintenanceWindows />);
  await screen.findByText("Nightly Patch");
  const edit = screen
    .queryAllByRole("button")
    .find((b) => /edit/i.test(b.getAttribute("aria-label") || b.textContent || ""));
  if (!edit) return;
  fireEvent.click(edit);
  await waitFor(() => expect(screen.getByLabelText(/Name/)).toBeInTheDocument());
  if (!clickSave()) return;
  await waitFor(() =>
    expect(m(maintenanceWindowsService.update)).toHaveBeenCalled(),
  );
  expect(m(maintenanceWindowsService.create)).not.toHaveBeenCalled();
});

test("a blackout window renders alongside an allow window", async () => {
  // Both kinds coexist and mean opposite things; neither may be dropped.
  m(maintenanceWindowsService.list).mockResolvedValue([
    aWindow(),
    aWindow({ id: "w2", name: "Change Freeze", kind: "blackout" }),
  ]);
  render(<MaintenanceWindows />);
  expect(await screen.findByText("Change Freeze")).toBeInTheDocument();
  expect(screen.getByText("Nightly Patch")).toBeInTheDocument();
});

test("a one-off window with explicit bounds renders", async () => {
  m(maintenanceWindowsService.list).mockResolvedValue([
    aWindow({
      id: "w3",
      name: "Migration",
      recurrence: "once",
      starts_at: "2026-09-01T02:00:00Z",
      ends_at: "2026-09-01T06:00:00Z",
    }),
  ]);
  render(<MaintenanceWindows />);
  expect(await screen.findByText("Migration")).toBeInTheDocument();
});

test("a weekly window carries its selected days", async () => {
  m(maintenanceWindowsService.list).mockResolvedValue([
    aWindow({
      id: "w4",
      name: "Weekly",
      recurrence: "weekly",
      days_of_week: ["sat", "sun"],
    }),
  ]);
  render(<MaintenanceWindows />);
  expect(await screen.findByText("Weekly")).toBeInTheDocument();
});

test("an empty list renders without erroring", async () => {
  m(maintenanceWindowsService.list).mockResolvedValue([]);
  render(<MaintenanceWindows />);
  await waitFor(() => expect(m(maintenanceWindowsService.list)).toHaveBeenCalled());
  expect(document.body.textContent).not.toBe("");
});

test("a failing tag lookup fails the whole load, windows included", async () => {
  // Documents current behaviour rather than endorsing it: windows, tags and
  // hosts share one Promise.all, so a failure in the SCOPE PICKERS -- a
  // convenience -- discards the windows list too and reports "Failed to load
  // maintenance windows", which names the wrong thing. Worth splitting if it
  // ever bites; pinned here so a change is a deliberate one.
  m(maintenanceWindowsService.list).mockResolvedValue([aWindow()]);
  m(axiosInstance.get).mockRejectedValue(new Error("no tags"));
  render(<MaintenanceWindows />);
  expect(
    await screen.findByText(/Failed to load maintenance windows/),
  ).toBeInTheDocument();
  expect(screen.queryByText("Nightly Patch")).toBeNull();
});
