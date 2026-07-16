// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { vi, beforeEach, afterEach, test, expect } from "vitest";

// Error-path tests intentionally log to console.error; silence the expected
// noise without hiding real errors (restored after each test).
let errSpy: ReturnType<typeof vi.spyOn>;

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (k: string, f?: string) => f || k,
    i18n: { language: "en" },
  }),
}));

vi.mock("@mui/x-data-grid", () => ({
  DataGrid: ({
    rows,
  }: {
    rows: Array<{ id: string; display_name: string }>;
  }) => (
    <div data-testid="grid">
      {(rows || []).map((r) => (
        <div key={r.id}>{r.display_name}</div>
      ))}
    </div>
  ),
}));

vi.mock("../../Services/childHostDistributions", () => ({
  distributionService: {
    getAll: vi.fn(),
    get: vi.fn(),
    create: vi.fn(),
    update: vi.fn(),
    delete: vi.fn(),
    toggleActive: vi.fn(),
  },
}));

vi.mock("../../Services/permissions", () => ({
  hasPermission: vi.fn(),
  SecurityRoles: { CONFIGURE_CHILD_HOST: "Configure Child Host" },
}));

vi.mock("../../Services/license", () => ({
  refreshLicenseCache: vi.fn(),
  isModuleLicensed: vi.fn(),
}));

// The grid's useColumnVisibility hook fires a real column-preferences GET
// on mount; stub the service so nothing escapes to MSW.
vi.mock("../../Services/columnPreferencesService", () => ({
  getColumnPreferences: vi.fn().mockResolvedValue(null),
  updateColumnPreferences: vi.fn().mockResolvedValue(undefined),
  deleteColumnPreferences: vi.fn().mockResolvedValue(undefined),
}));

import { distributionService } from "../../Services/childHostDistributions";
import { hasPermission } from "../../Services/permissions";
import { refreshLicenseCache, isModuleLicensed } from "../../Services/license";
import DistributionsSettings from "../../Components/DistributionsSettings";

const m = (fn: unknown) => fn as unknown as ReturnType<typeof vi.fn>;

const dist = {
  id: "d1",
  child_type: "wsl",
  distribution_name: "Ubuntu",
  distribution_version: "24.04",
  display_name: "Ubuntu 24.04 LTS",
  install_identifier: "Ubuntu-24.04",
  executable_name: "ubuntu2404.exe",
  agent_install_method: "manual",
  agent_install_commands: "[]",
  is_active: true,
  min_agent_version: "",
  notes: "",
  created_at: null,
  updated_at: null,
};

beforeEach(() => {
  vi.clearAllMocks();
  errSpy = vi.spyOn(window.console, "error").mockImplementation(() => {});
  m(distributionService.getAll).mockResolvedValue([dist]);
  m(distributionService.create).mockResolvedValue(dist);
  m(distributionService.update).mockResolvedValue(dist);
  m(distributionService.delete).mockResolvedValue(undefined);
  m(hasPermission).mockResolvedValue(true);
  m(refreshLicenseCache).mockResolvedValue(null);
  m(isModuleLicensed).mockReturnValue(true);
});

afterEach(() => {
  errSpy.mockRestore();
});

test("renders the distribution list after load", async () => {
  render(<DistributionsSettings />);
  expect(
    await screen.findByText("Child Host Distributions"),
  ).toBeInTheDocument();
  await waitFor(() => expect(distributionService.getAll).toHaveBeenCalled());
  expect(await screen.findByText("Ubuntu 24.04 LTS")).toBeInTheDocument();
});

test("opens the add dialog and creates a distribution", async () => {
  render(<DistributionsSettings />);
  await screen.findByText("Ubuntu 24.04 LTS");

  const addBtn = await screen.findByRole("button", {
    name: /Add Distribution/,
  });
  fireEvent.click(addBtn);

  const displayName = await screen.findByLabelText(/Display Name/);
  fireEvent.change(displayName, { target: { value: "Debian 12" } });

  fireEvent.click(screen.getByRole("button", { name: /^Save$/ }));
  await waitFor(() => expect(distributionService.create).toHaveBeenCalled());
});

test("cancel closes the add dialog without creating", async () => {
  render(<DistributionsSettings />);
  await screen.findByText("Ubuntu 24.04 LTS");

  fireEvent.click(
    await screen.findByRole("button", { name: /Add Distribution/ }),
  );
  await screen.findByText("Add Distribution", { selector: "h2" });
  fireEvent.click(screen.getByRole("button", { name: /Cancel/ }));

  await waitFor(() =>
    expect(distributionService.create).not.toHaveBeenCalled(),
  );
});

test("respects an unlicensed virtualization engine", async () => {
  m(isModuleLicensed).mockReturnValue(false);
  m(distributionService.getAll).mockResolvedValue([
    dist,
    { ...dist, id: "d2", child_type: "kvm", display_name: "KVM VM" },
  ]);
  render(<DistributionsSettings />);
  await screen.findByText("Ubuntu 24.04 LTS");
  // The KVM (VM) distribution must be filtered out of the grid.
  await waitFor(() =>
    expect(screen.queryByText("KVM VM")).not.toBeInTheDocument(),
  );
});

test("shows an error snackbar when loading fails", async () => {
  m(distributionService.getAll).mockRejectedValue(new Error("boom"));
  render(<DistributionsSettings />);
  expect(
    await screen.findByText(/Error loading distributions/),
  ).toBeInTheDocument();
});
