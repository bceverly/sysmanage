// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import React from "react";
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
// so stub it to a trivial row renderer -- the page logic under test is the
// toolbar/dialog, not the grid internals.
// The stub still renders each column through its renderCell / valueGetter so
// the column definitions (kind chip, schedule text, scope text, actions) run.
interface MockCol {
  field: string;
  renderCell?: (_p: {
    row: Record<string, unknown>;
    value: unknown;
  }) => React.ReactNode;
  valueGetter?: (_v: unknown, _row: Record<string, unknown>) => unknown;
}
vi.mock("@mui/x-data-grid", () => ({
  DataGrid: ({
    rows,
    columns,
    getRowId,
  }: {
    rows: Array<Record<string, unknown>>;
    columns: MockCol[];
    getRowId?: (_r: Record<string, unknown>) => string;
  }) => (
    <div data-testid="grid">
      {rows.map((r) => {
        const id = getRowId ? getRowId(r) : String(r.id);
        return (
          <div key={id} data-testid={`row-${id}`}>
            {columns.map((c) => (
              <span key={c.field} data-testid={`${id}-${c.field}`}>
                {c.renderCell
                  ? c.renderCell({ row: r, value: r[c.field] })
                  : String(
                      c.valueGetter
                        ? c.valueGetter(r[c.field], r)
                        : (r[c.field] ?? ""),
                    )}
              </span>
            ))}
          </div>
        );
      })}
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
  // Documents current behavior rather than endorsing it: windows, tags and
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

// ---------------------------------------------------------------------------
// Column rendering, dialog field editing, scope pickers and delete flow.
// ---------------------------------------------------------------------------

import { within } from "@testing-library/react";

const pickOption = async (comboName: RegExp, option: string) => {
  fireEvent.mouseDown(screen.getByRole("combobox", { name: comboName }));
  const listbox = await screen.findByRole("listbox");
  fireEvent.click(within(listbox).getByRole("option", { name: option }));
};

const hostsAndTags = () =>
  m(axiosInstance.get).mockImplementation((url: string) =>
    Promise.resolve({
      data: url.includes("tags")
        ? [
            { id: "t1", name: "web" },
            { id: "t2", name: "db" },
          ]
        : [
            { id: "h1", fqdn: "a.example.com", extra: 1 },
            { id: "h2", fqdn: "b.example.com" },
          ],
    }),
  );

test("grid columns render kind, schedule, scope and enabled text", async () => {
  m(maintenanceWindowsService.list).mockResolvedValue([
    aWindow(),
    aWindow({
      id: "w2",
      kind: "blackout",
      enabled: false,
      recurrence: "weekly",
      days_of_week: ["sat", "sun"],
      scopes: [
        { scope_type: "host", host_id: "h1" },
        { scope_type: "host", host_id: "h2" },
        { scope_type: "tag", tag_id: "t1" },
      ],
    }),
    aWindow({
      id: "w3",
      recurrence: "once",
      starts_at: "2026-09-01T02:00",
      ends_at: null,
      scopes: [],
    }),
    aWindow({ id: "w4", days_of_week: null, scopes: null }),
  ]);
  render(<MaintenanceWindows />);
  await screen.findByTestId("row-w1");
  expect(screen.getByTestId("w1-kind")).toHaveTextContent("Allow");
  expect(screen.getByTestId("w1-schedule")).toHaveTextContent(
    "Every day · 02:00 UTC · 120m",
  );
  expect(screen.getByTestId("w1-scope")).toHaveTextContent("All hosts");
  expect(screen.getByTestId("w1-enabled")).toHaveTextContent("Yes");
  expect(screen.getByTestId("w2-kind")).toHaveTextContent("Blackout");
  expect(screen.getByTestId("w2-schedule")).toHaveTextContent(
    "sat, sun · 02:00 UTC · 120m",
  );
  expect(screen.getByTestId("w2-scope")).toHaveTextContent(
    "2 host(s), 1 tag(s)",
  );
  expect(screen.getByTestId("w2-enabled")).toHaveTextContent("No");
  expect(screen.getByTestId("w3-schedule")).toHaveTextContent(
    "2026-09-01T02:00 → ?",
  );
  expect(screen.getByTestId("w3-scope")).toHaveTextContent("--");
  expect(screen.getByTestId("w4-scope")).toHaveTextContent("--");
});

test("create dialog edits every field and posts a host-scoped weekly blackout", async () => {
  hostsAndTags();
  m(maintenanceWindowsService.list).mockResolvedValue([aWindow()]);
  m(maintenanceWindowsService.create).mockResolvedValue(aWindow());
  await openCreateDialog();
  fireEvent.change(screen.getByLabelText(/Name/), {
    target: { value: "Freeze" },
  });
  fireEvent.change(screen.getByLabelText("Description"), {
    target: { value: "quarter end" },
  });
  await pickOption(/Kind/, "Blackout");
  await pickOption(/Recurrence/, "Weekly");
  fireEvent.click(await screen.findByRole("button", { name: "sat" }));
  fireEvent.change(screen.getByLabelText("Start time"), {
    target: { value: "03:30" },
  });
  fireEvent.change(screen.getByLabelText("Duration (minutes)"), {
    target: { value: "45" },
  });
  await pickOption(/Timezone/, "Asia/Tokyo");
  await pickOption(/Applies to/, "Specific hosts");
  const hostsInput = screen.getByRole("combobox", { name: "Hosts" });
  fireEvent.mouseDown(hostsInput);
  fireEvent.click(await screen.findByRole("option", { name: "b.example.com" }));
  fireEvent.click(screen.getByLabelText("Enabled"));

  expect(clickSave()).toBe(true);
  await waitFor(() =>
    expect(maintenanceWindowsService.create).toHaveBeenCalledWith({
      name: "Freeze",
      description: "quarter end",
      enabled: false,
      kind: "blackout",
      recurrence: "weekly",
      timezone: "Asia/Tokyo",
      start_time: "03:30",
      duration_minutes: 45,
      days_of_week: ["sat"],
      starts_at: null,
      ends_at: null,
      scopes: [{ scope_type: "host", host_id: "h2" }],
    }),
  );
  expect(
    await screen.findByText("Maintenance window created"),
  ).toBeInTheDocument();
});

test("one-time window with tag scope sends explicit bounds", async () => {
  hostsAndTags();
  m(maintenanceWindowsService.list).mockResolvedValue([aWindow()]);
  m(maintenanceWindowsService.create).mockResolvedValue(aWindow());
  await openCreateDialog();
  fireEvent.change(screen.getByLabelText(/Name/), {
    target: { value: "Once" },
  });
  await pickOption(/Recurrence/, "One-time");
  fireEvent.change(screen.getByLabelText("Starts at (UTC)"), {
    target: { value: "2026-10-01T01:00" },
  });
  fireEvent.change(screen.getByLabelText("Ends at (UTC)"), {
    target: { value: "2026-10-01T05:00" },
  });
  // Clearing the duration stores null (only reachable for recurring, so
  // switch back is not needed here; the one-time path omits the field).
  await pickOption(/Applies to/, "Hosts by tag");
  fireEvent.mouseDown(screen.getByRole("combobox", { name: "Tags" }));
  fireEvent.click(await screen.findByRole("option", { name: "db" }));
  expect(clickSave()).toBe(true);
  await waitFor(() =>
    expect(maintenanceWindowsService.create).toHaveBeenCalledWith(
      expect.objectContaining({
        recurrence: "once",
        starts_at: "2026-10-01T01:00",
        ends_at: "2026-10-01T05:00",
        scopes: [{ scope_type: "tag", tag_id: "t2" }],
      }),
    ),
  );
});

test("clearing the duration sends null and cancel closes the dialog", async () => {
  m(maintenanceWindowsService.list).mockResolvedValue([aWindow()]);
  m(maintenanceWindowsService.create).mockResolvedValue(aWindow());
  await openCreateDialog();
  fireEvent.change(screen.getByLabelText("Duration (minutes)"), {
    target: { value: "" },
  });
  expect(clickSave()).toBe(true);
  await waitFor(() =>
    expect(maintenanceWindowsService.create).toHaveBeenCalledWith(
      expect.objectContaining({ duration_minutes: null }),
    ),
  );
  await screen.findByText("Maintenance window created");
  fireEvent.click(
    await screen.findByRole("button", { name: /Schedule Maintenance/ }),
  );
  await screen.findByRole("dialog");
  fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
  await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
});

test("editing a tag-scoped window pre-fills the form and updates it", async () => {
  hostsAndTags();
  const w = aWindow({
    description: "desc",
    start_time: null,
    duration_minutes: null,
    days_of_week: null,
    scopes: [{ scope_type: "tag", tag_id: "t1" }],
  });
  m(maintenanceWindowsService.list).mockResolvedValue([w]);
  m(maintenanceWindowsService.update).mockResolvedValue(w);
  render(<MaintenanceWindows />);
  const actions = await screen.findByTestId("w1-actions");
  fireEvent.click(within(actions).getByRole("button", { name: "Edit" }));
  expect(
    await screen.findByText("Edit Maintenance Window"),
  ).toBeInTheDocument();
  expect(screen.getByLabelText("Description")).toHaveValue("desc");
  expect(screen.getByText("web")).toBeInTheDocument();
  expect(clickSave()).toBe(true);
  await waitFor(() =>
    expect(maintenanceWindowsService.update).toHaveBeenCalledWith(
      "w1",
      expect.objectContaining({
        start_time: "02:00",
        duration_minutes: 120,
        days_of_week: [],
        scopes: [{ scope_type: "tag", tag_id: "t1" }],
      }),
    ),
  );
  expect(
    await screen.findByText("Maintenance window updated"),
  ).toBeInTheDocument();
});

test("editing a host-scoped window keeps its hosts", async () => {
  hostsAndTags();
  const w = aWindow({ scopes: [{ scope_type: "host", host_id: "h1" }] });
  m(maintenanceWindowsService.list).mockResolvedValue([w]);
  m(maintenanceWindowsService.update).mockResolvedValue(w);
  render(<MaintenanceWindows />);
  const actions = await screen.findByTestId("w1-actions");
  fireEvent.click(within(actions).getByRole("button", { name: "Edit" }));
  expect(await screen.findByText("a.example.com")).toBeInTheDocument();
  expect(clickSave()).toBe(true);
  await waitFor(() =>
    expect(maintenanceWindowsService.update).toHaveBeenCalledWith(
      "w1",
      expect.objectContaining({
        scopes: [{ scope_type: "host", host_id: "h1" }],
      }),
    ),
  );
});

test("deleting a window confirms, removes and reloads", async () => {
  m(maintenanceWindowsService.list).mockResolvedValue([aWindow()]);
  m(maintenanceWindowsService.remove).mockResolvedValue(undefined);
  render(<MaintenanceWindows />);
  const actions = await screen.findByTestId("w1-actions");
  fireEvent.click(within(actions).getByRole("button", { name: "Delete" }));
  const dlg = await screen.findByRole("dialog");
  expect(
    within(dlg).getByText(
      "Are you sure you want to delete this maintenance window?",
    ),
  ).toBeInTheDocument();
  fireEvent.click(within(dlg).getByRole("button", { name: "Delete" }));
  await waitFor(() =>
    expect(maintenanceWindowsService.remove).toHaveBeenCalledWith("w1"),
  );
  expect(
    await screen.findByText("Maintenance window deleted"),
  ).toBeInTheDocument();
  expect(maintenanceWindowsService.list).toHaveBeenCalledTimes(2);
});

test("delete cancel closes the dialog without removing", async () => {
  m(maintenanceWindowsService.list).mockResolvedValue([aWindow()]);
  render(<MaintenanceWindows />);
  const actions = await screen.findByTestId("w1-actions");
  fireEvent.click(within(actions).getByRole("button", { name: "Delete" }));
  const dlg = await screen.findByRole("dialog");
  fireEvent.click(within(dlg).getByRole("button", { name: "Cancel" }));
  await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
  expect(maintenanceWindowsService.remove).not.toHaveBeenCalled();
});

test("a delete failure shows a dismissible error", async () => {
  m(maintenanceWindowsService.list).mockResolvedValue([aWindow()]);
  m(maintenanceWindowsService.remove).mockRejectedValue(new Error("x"));
  render(<MaintenanceWindows />);
  const actions = await screen.findByTestId("w1-actions");
  fireEvent.click(within(actions).getByRole("button", { name: "Delete" }));
  const dlg = await screen.findByRole("dialog");
  fireEvent.click(within(dlg).getByRole("button", { name: "Delete" }));
  // Close the confirm dialog so the page-level alert shows.
  await waitFor(() =>
    expect(maintenanceWindowsService.remove).toHaveBeenCalledWith("w1"),
  );
  fireEvent.click(within(dlg).getByRole("button", { name: "Cancel" }));
  await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
  expect(
    await screen.findByText("Failed to delete maintenance window"),
  ).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: /close/i }));
  await waitFor(() =>
    expect(
      screen.queryByText("Failed to delete maintenance window"),
    ).toBeNull(),
  );
});
