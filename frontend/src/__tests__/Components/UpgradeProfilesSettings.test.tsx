// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { vi, beforeEach, afterEach, test, expect } from "vitest";

// Error-path tests intentionally log to console.error; silence the expected
// noise without hiding real errors (restored after each test).
let errSpy: ReturnType<typeof vi.spyOn>;

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

vi.mock("../../Services/api", () => ({
  default: { get: vi.fn(), post: vi.fn(), put: vi.fn(), delete: vi.fn() },
}));

vi.mock("../../Services/upgradeProfiles", () => ({
  upgradeProfilesService: {
    list: vi.fn(),
    create: vi.fn(),
    update: vi.fn(),
    remove: vi.fn(),
    trigger: vi.fn(),
  },
}));

vi.mock("@mui/x-data-grid", () => ({
  DataGrid: ({
    rows,
  }: {
    rows: Array<{ id: string; name: string }>;
  }) => (
    <div data-testid="grid">
      {rows.map((r) => (
        <div key={r.id}>{r.name}</div>
      ))}
    </div>
  ),
}));

import axiosInstance from "../../Services/api";
import { upgradeProfilesService } from "../../Services/upgradeProfiles";
import UpgradeProfilesSettings from "../../Components/UpgradeProfilesSettings";

const m = (fn: unknown) => fn as unknown as ReturnType<typeof vi.fn>;

const profile = {
  id: "p1",
  name: "Nightly Fleet Update",
  description: "desc",
  cron: "0 3 * * *",
  enabled: true,
  security_only: false,
  package_managers: ["apt"],
  staggered_window_min: 30,
  tag_id: null,
  last_run: null,
  last_status: null,
  next_run: null,
  created_at: null,
  updated_at: null,
};

beforeEach(() => {
  vi.clearAllMocks();
  errSpy = vi.spyOn(window.console, "error").mockImplementation(() => {});
  m(upgradeProfilesService.list).mockResolvedValue([profile]);
  m(upgradeProfilesService.create).mockResolvedValue(profile);
  m(upgradeProfilesService.update).mockResolvedValue(profile);
  m(upgradeProfilesService.remove).mockResolvedValue(undefined);
  m(upgradeProfilesService.trigger).mockResolvedValue({
    profile_id: "p1",
    name: "Nightly Fleet Update",
    host_count: 3,
    enqueued_count: 3,
    host_ids: [],
    next_run: null,
  });
  m(axiosInstance.get).mockResolvedValue({
    data: [{ id: "t1", name: "prod" }],
  });
});

afterEach(() => {
  errSpy.mockRestore();
});

test("renders the profile list from the service", async () => {
  render(<UpgradeProfilesSettings />);

  expect(await screen.findByText("Nightly Fleet Update")).toBeInTheDocument();
  expect(screen.getByText("Update Profiles")).toBeInTheDocument();
  expect(m(upgradeProfilesService.list)).toHaveBeenCalled();
  expect(m(axiosInstance.get)).toHaveBeenCalledWith("/api/v1/tags");
});

test("opens the create dialog and creates a profile", async () => {
  render(<UpgradeProfilesSettings />);
  await screen.findByText("Nightly Fleet Update");

  fireEvent.click(screen.getByText("Add Profile"));
  await screen.findByText("Add Update Profile");

  const nameInput = screen.getByLabelText(/Name/);
  fireEvent.change(nameInput, { target: { value: "New Profile" } });

  fireEvent.click(screen.getByText("Save"));

  await waitFor(() =>
    expect(m(upgradeProfilesService.create)).toHaveBeenCalled(),
  );
});

test("shows validation error when saving without a name", async () => {
  render(<UpgradeProfilesSettings />);
  await screen.findByText("Nightly Fleet Update");

  fireEvent.click(screen.getByText("Add Profile"));
  await screen.findByText("Add Update Profile");

  fireEvent.click(screen.getByText("Save"));

  expect(await screen.findByText("Name is required")).toBeInTheDocument();
  expect(m(upgradeProfilesService.create)).not.toHaveBeenCalled();
});

test("shows a load error when the list service fails", async () => {
  m(upgradeProfilesService.list).mockRejectedValue(new Error("boom"));
  render(<UpgradeProfilesSettings />);
  expect(
    await screen.findByText("Failed to load update profiles"),
  ).toBeInTheDocument();
});
