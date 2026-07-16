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

// MUI X DataGrid's CSS trips jsdom's cssstyle, so stub it to a trivial renderer.
vi.mock("@mui/x-data-grid", () => ({
  DataGrid: ({
    rows,
    columns,
  }: {
    rows: Array<Record<string, unknown>>;
    columns: Array<Record<string, unknown>>;
  }) => (
    <div data-testid="grid">
      {rows.map((r) => (
        <div key={String(r.id)}>
          <span>{String(r.name)}</span>
          {columns.map((c) =>
            c.renderCell ? (
              <span key={String(c.field)}>{(c.renderCell as CallableFunction)({ row: r }) as never}</span>
            ) : null,
          )}
        </div>
      ))}
    </div>
  ),
  GridColDef: {},
  GridRenderCellParams: {},
}));

vi.mock("../../Services/packageProfiles", () => ({
  CONSTRAINT_TYPES: ["REQUIRED", "BLOCKED"],
  VERSION_OPS: ["=", ">=", "<="],
  packageProfilesService: {
    list: vi.fn(),
    get: vi.fn(),
    create: vi.fn(),
    update: vi.fn(),
    remove: vi.fn(),
  },
}));

import { packageProfilesService } from "../../Services/packageProfiles";
import PackageProfilesSettings from "../../Components/PackageProfilesSettings";

const m = (fn: unknown) => fn as unknown as ReturnType<typeof vi.fn>;

const profile = {
  id: "p1",
  name: "Baseline",
  description: "core packages",
  enabled: true,
  constraints: [],
  created_at: null,
  updated_at: null,
};

beforeEach(() => {
  vi.clearAllMocks();
  errSpy = vi.spyOn(window.console, "error").mockImplementation(() => {});
  m(packageProfilesService.list).mockResolvedValue([profile]);
  m(packageProfilesService.get).mockResolvedValue(profile);
  m(packageProfilesService.create).mockResolvedValue(profile);
  m(packageProfilesService.update).mockResolvedValue(profile);
  m(packageProfilesService.remove).mockResolvedValue(undefined);
});

afterEach(() => {
  errSpy.mockRestore();
});

test("renders the profiles grid after load", async () => {
  render(<PackageProfilesSettings />);
  expect(await screen.findByText("Baseline")).toBeInTheDocument();
  expect(m(packageProfilesService.list)).toHaveBeenCalled();
});

test("opens the create dialog", async () => {
  render(<PackageProfilesSettings />);
  await screen.findByText("Baseline");

  fireEvent.click(screen.getByRole("button", { name: /Add Profile/ }));

  await waitFor(() =>
    expect(screen.getByText("Add Compliance Profile")).toBeInTheDocument(),
  );
});

test("creates a profile with a name and a constraint", async () => {
  render(<PackageProfilesSettings />);
  await screen.findByText("Baseline");

  fireEvent.click(screen.getByRole("button", { name: /Add Profile/ }));
  await screen.findByText("Add Compliance Profile");

  const nameField = screen.getByLabelText(/Name/) as HTMLInputElement;
  fireEvent.change(nameField, { target: { value: "New Profile" } });

  fireEvent.click(screen.getByRole("button", { name: /Add Constraint/ }));
  const pkgField = (await screen.findByLabelText(/Package/)) as HTMLInputElement;
  fireEvent.change(pkgField, { target: { value: "openssl" } });

  fireEvent.click(screen.getByRole("button", { name: /^Save$/ }));

  await waitFor(() =>
    expect(m(packageProfilesService.create)).toHaveBeenCalled(),
  );
});

test("blocks save when the name is empty", async () => {
  render(<PackageProfilesSettings />);
  await screen.findByText("Baseline");

  fireEvent.click(screen.getByRole("button", { name: /Add Profile/ }));
  await screen.findByText("Add Compliance Profile");

  fireEvent.click(screen.getByRole("button", { name: /^Save$/ }));

  await waitFor(() =>
    expect(screen.getByText("Name is required")).toBeInTheDocument(),
  );
  expect(m(packageProfilesService.create)).not.toHaveBeenCalled();
});

test("shows a load error when the list service fails", async () => {
  m(packageProfilesService.list).mockRejectedValue(new Error("boom"));
  render(<PackageProfilesSettings />);
  expect(
    await screen.findByText("Failed to load compliance profiles"),
  ).toBeInTheDocument();
});
