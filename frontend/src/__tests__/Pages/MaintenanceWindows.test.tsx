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
