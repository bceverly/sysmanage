// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

import { render, screen, fireEvent, waitFor, act } from "@testing-library/react";
import { vi, beforeEach, afterEach, test, expect } from "vitest";

// MUI emits a benign `anchorEl` console.error under jsdom when a Select
// popover opens (no real layout); silence it without hiding real errors.
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

vi.mock("../../Services/permissions", () => ({
  hasPermission: vi.fn(),
  SecurityRoles: {
    ADD_DEFAULT_REPOSITORY: "Add Default Repository",
    REMOVE_DEFAULT_REPOSITORY: "Remove Default Repository",
    VIEW_DEFAULT_REPOSITORIES: "View Default Repositories",
    ADD_ENABLED_PACKAGE_MANAGER: "Add Enabled Package Manager",
    REMOVE_ENABLED_PACKAGE_MANAGER: "Remove Enabled Package Manager",
    VIEW_ENABLED_PACKAGE_MANAGERS: "View Enabled Package Managers",
  },
}));

// The mirrors child card pulls in its own services + licensing hook; it's a
// separate component with its own tests, so stub it out here.
vi.mock("../../Components/DefaultPackageMirrorsCard", () => ({
  default: () => <div data-testid="mirrors-card" />,
}));

import axiosInstance from "../../Services/api";
import { hasPermission } from "../../Services/permissions";
import HostDefaultsSettings from "../../Components/HostDefaultsSettings";

const m = (fn: unknown) => fn as unknown as ReturnType<typeof vi.fn>;

const OS_OPTIONS_RESPONSE = {
  operating_systems: ["Ubuntu 22.04", "Fedora 40", "Windows 11"],
  package_managers: {
    "Ubuntu 22.04": ["apt"],
    "Fedora 40": ["dnf"],
    "Windows 11": ["chocolatey"],
  },
};

const PM_OS_OPTIONS_RESPONSE = {
  operating_systems: ["Ubuntu 22.04", "Fedora 40"],
  default_package_managers: { "Ubuntu 22.04": "apt", "Fedora 40": "dnf" },
  optional_package_managers: {
    "Ubuntu 22.04": ["snap", "flatpak"],
    "Fedora 40": [],
  },
};

const REPOSITORIES = [
  {
    id: "r1",
    os_name: "Ubuntu 22.04",
    package_manager: "apt",
    repository_url: "ppa:bceverly/sysmanage-agent",
    created_at: "2026-01-01T00:00:00Z",
    created_by: "admin",
  },
];

const ENABLED_PMS = [
  {
    id: "p1",
    os_name: "Ubuntu 22.04",
    package_manager: "snap",
    created_at: "2026-01-01T00:00:00Z",
    created_by: "admin",
  },
];

// Route axios GETs by URL to the right fixture.
function wireGet() {
  m(axiosInstance.get).mockImplementation((url: string) => {
    if (url === "/api/v1/default-repositories/os-options") {
      return Promise.resolve({ data: OS_OPTIONS_RESPONSE });
    }
    if (url === "/api/v1/default-repositories/") {
      return Promise.resolve({ data: REPOSITORIES });
    }
    if (url === "/api/v1/enabled-package-managers/os-options") {
      return Promise.resolve({ data: PM_OS_OPTIONS_RESPONSE });
    }
    if (url === "/api/v1/enabled-package-managers/") {
      return Promise.resolve({ data: ENABLED_PMS });
    }
    return Promise.resolve({ data: [] });
  });
}

beforeEach(() => {
  vi.clearAllMocks();
  errSpy = vi.spyOn(window.console, "error").mockImplementation(() => {});
  // Default: full permissions.
  m(hasPermission).mockResolvedValue(true);
  wireGet();
  m(axiosInstance.post).mockResolvedValue({ data: {} });
  m(axiosInstance.delete).mockResolvedValue({ data: {} });
});

afterEach(() => {
  errSpy.mockRestore();
});

test("renders configured repositories and enabled package managers", async () => {
  render(<HostDefaultsSettings />);

  // The list renders only after an async permission check + two GETs resolve;
  // give findByText real headroom so it doesn't flake under full-suite load
  // (the default 1000ms is too tight when many files run in parallel).
  expect(
    await screen.findByText("ppa:bceverly/sysmanage-agent", undefined, {
      timeout: 5000,
    }),
  ).toBeInTheDocument();
  // Enabled package manager entry from the second card.
  expect(
    await screen.findByText("snap", undefined, { timeout: 5000 }),
  ).toBeInTheDocument();
  // Mirrors child card is present.
  expect(screen.getByTestId("mirrors-card")).toBeInTheDocument();
});

test("shows the no-permission warning when the user cannot view anything", async () => {
  m(hasPermission).mockResolvedValue(false);
  render(<HostDefaultsSettings />);

  expect(
    await screen.findByText(
      /You do not have permission to view host default settings/,
    ),
  ).toBeInTheDocument();
});

test("adds a default repository through the form", async () => {
  render(<HostDefaultsSettings />);
  await screen.findByText("ppa:bceverly/sysmanage-agent", undefined, {
    timeout: 5000,
  });

  // The repo card is first: combobox[0] = OS, combobox[1] = Package Manager.
  const osSelect = screen.getAllByRole("combobox")[0];
  fireEvent.mouseDown(osSelect);
  const ubuntuOption = await screen.findByRole("option", {
    name: "Ubuntu 22.04",
  });
  fireEvent.click(ubuntuOption);

  // Select the package manager "apt".
  const pmSelect = screen.getAllByRole("combobox")[1];
  fireEvent.mouseDown(pmSelect);
  const aptOption = await screen.findByRole("option", { name: "apt" });
  fireEvent.click(aptOption);

  // Fill in the Ubuntu PPA fields so a repo identifier gets constructed.
  fireEvent.change(screen.getByLabelText(/PPA Owner/), {
    target: { value: "bceverly" },
  });
  fireEvent.change(screen.getByLabelText(/PPA Name/), {
    target: { value: "myppa" },
  });

  // The repo card's Add button is the first one; enabled once form is valid.
  const addButton = screen.getAllByRole("button", { name: /Add/ })[0];
  await waitFor(() => expect(addButton).not.toBeDisabled());

  await act(async () => {
    fireEvent.click(addButton);
  });

  await waitFor(() =>
    expect(axiosInstance.post).toHaveBeenCalledWith(
      "/api/v1/default-repositories/",
      expect.objectContaining({
        os_name: "Ubuntu 22.04",
        package_manager: "apt",
        repository_url: "ppa:bceverly/myppa",
      }),
    ),
  );
});

test("deletes a configured repository", async () => {
  render(<HostDefaultsSettings />);
  await screen.findByText("ppa:bceverly/sysmanage-agent", undefined, {
    timeout: 5000,
  });

  // Delete icon buttons carry the "Delete" title.
  const deleteButtons = screen.getAllByTitle("Delete");
  await act(async () => {
    fireEvent.click(deleteButtons[0]);
  });

  await waitFor(() =>
    expect(axiosInstance.delete).toHaveBeenCalledWith(
      "/api/v1/default-repositories/r1",
    ),
  );
});

test("adds an enabled package manager", async () => {
  render(<HostDefaultsSettings />);
  await screen.findByText("snap", undefined, { timeout: 5000 });

  // Comboboxes: repo card OS(0), repo PM(1), PM card OS(2), PM card PM(3).
  const pmOsSelect = screen.getAllByRole("combobox")[2];
  fireEvent.mouseDown(pmOsSelect);
  const ubuntuOption = await screen.findByRole("option", {
    name: "Ubuntu 22.04",
  });
  fireEvent.click(ubuntuOption);

  // Now pick an optional package manager (flatpak).
  const optionalPmSelect = screen.getAllByRole("combobox")[3];
  fireEvent.mouseDown(optionalPmSelect);
  const snapOption = await screen.findByRole("option", { name: "flatpak" });
  fireEvent.click(snapOption);

  const addButtons = screen.getAllByRole("button", { name: /Add/ });
  const pmAddButton = addButtons[addButtons.length - 1];
  await waitFor(() => expect(pmAddButton).not.toBeDisabled());

  await act(async () => {
    fireEvent.click(pmAddButton);
  });

  await waitFor(() =>
    expect(axiosInstance.post).toHaveBeenCalledWith(
      "/api/v1/enabled-package-managers/",
      expect.objectContaining({
        os_name: "Ubuntu 22.04",
        package_manager: "flatpak",
      }),
    ),
  );
});
