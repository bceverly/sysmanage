// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

/**
 * Settings page: the tag CRUD round trips, tag search, the Available Packages
 * wiring (summary, host scoping, search params, refresh), every licensed tab's
 * content dispatch, and plugin-tab ordering. The child components are stubs
 * that expose the callbacks the page hands them, so what is asserted is the
 * page's own request shaping, not the children's UI.
 */

import React from "react";
import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { vi, describe, beforeEach, afterEach, test, expect } from "vitest";

const t = (key: string, fallback?: string) =>
  typeof fallback === "string" ? fallback : key;
vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t, i18n: { language: "en" } }),
}));

vi.mock("@mui/x-data-grid", () => ({
  DataGrid: ({
    rows,
    columns,
    onRowSelectionModelChange,
  }: {
    rows?: any[];
    columns?: any[];
    onRowSelectionModelChange?: (_ids: unknown[]) => void;
  }) => (
    <div data-testid="grid">
      <button
        onClick={() => onRowSelectionModelChange?.((rows ?? []).map((r) => r.id))}
      >
        select-all
      </button>
      {(rows ?? []).map((row) => (
        <div key={String(row.id)} data-testid={`row-${row.id}`}>
          {(columns ?? []).map((col: any) => (
            <div key={col.field}>
              {col.renderCell
                ? col.renderCell({ row, value: row[col.field] })
                : String(row[col.field] ?? "")}
            </div>
          ))}
        </div>
      ))}
    </div>
  ),
}));

vi.mock("../../Components/SearchBox", () => ({
  default: (p: any) => (
    <div>
      <input
        aria-label="tag-search"
        value={p.searchTerm}
        onChange={(e) => p.setSearchTerm(e.target.value)}
      />
      <button onClick={() => p.setSearchColumn("description")}>
        search-description
      </button>
    </div>
  ),
}));

const { stub } = vi.hoisted(() => ({
  stub: (name: string) => ({
    default: () => <div data-testid={`stub-${name}`} />,
  }),
}));
vi.mock("../../Components/ColumnVisibilityButton", () => stub("ColumnVisibilityButton"));
vi.mock("../../Components/ConfigurationSettings", () => stub("ConfigurationSettings"));
vi.mock("../../Components/AntivirusDefaultsSettings", () => stub("AntivirusDefaultsSettings"));
vi.mock("../../Components/HostDefaultsSettings", () => stub("HostDefaultsSettings"));
vi.mock("../../Components/FirewallRolesSettings", () => stub("FirewallRolesSettings"));
vi.mock("../../Components/DistributionsSettings", () => stub("DistributionsSettings"));
vi.mock("../../Components/UpgradeProfilesSettings", () => stub("UpgradeProfilesSettings"));
vi.mock("../../Components/PackageProfilesSettings", () => stub("PackageProfilesSettings"));
vi.mock("../../Components/ReportBrandingSettings", () => stub("ReportBrandingSettings"));
vi.mock("../../Components/ReportTemplatesSettings", () => stub("ReportTemplatesSettings"));
vi.mock("../../Components/AirGapBundlesSettings", () => stub("AirGapBundlesSettings"));
vi.mock("../../Components/AgentMirrorsSettings", () => stub("AgentMirrorsSettings"));
vi.mock("../../Components/RepositoryMirroringSettings", () => stub("RepositoryMirroringSettings"));
vi.mock("../../Components/AuthenticationProvidersSettings", () => stub("AuthenticationProvidersSettings"));
vi.mock("../../Components/ServerRoleSettings", () => stub("ServerRoleSettings"));
vi.mock("../../Components/LoggingSettings", () => stub("LoggingSettings"));
vi.mock("../../Components/settings/IntegrationsTab", () => stub("IntegrationsTab"));
vi.mock("../../Components/settings/QueuesTab", () => stub("QueuesTab"));
vi.mock("../../Components/settings/UbuntuProTab", () => stub("UbuntuProTab"));

vi.mock("../../Components/settings/AvailablePackagesTab", () => ({
  default: (p: any) => (
    <div data-testid="stub-AvailablePackagesTab">
      <span data-testid="pkg-state">
        {`summary:${p.packageSummary?.length ?? "x"} packages:${p.packages.length} total:${p.packageTotalCount} searched:${String(p.hasSearched)} hosts:${p.packageHosts.map((h: any) => h.fqdn).join(",")}`}
      </span>
      <button onClick={() => p.setPackageSearchTerm("nginx")}>set-term</button>
      <button onClick={() => p.setSelectedOS("Ubuntu:24.04")}>set-os</button>
      <button onClick={() => p.setSelectedPackageHost("h1")}>set-host</button>
      <button onClick={() => p.setSelectedManager("apt")}>set-mgr</button>
      <button onClick={() => p.onSearch(1, 10)}>search</button>
      <button onClick={() => p.onSearch()}>search-default</button>
      <button onClick={() => p.onRefreshAll()}>refresh-all</button>
      <button onClick={() => p.onRefreshOS("Ubuntu", "24.04")}>refresh-os</button>
    </div>
  ),
}));

vi.mock("../../Components/settings/SettingsDialogs", () => ({
  default: (p: any) => (
    <div data-testid="dialogs">
      <span data-testid="dlg-state">
        {`add:${String(p.addDialogOpen)} edit:${String(p.editDialogOpen)} hosts:${String(p.viewHostsDialogOpen)} tag:${p.viewingTag?.name ?? ""} name:${p.tagName} desc:${p.tagDescription}`}
      </span>
      <input
        aria-label="dlg-name"
        value={p.tagName}
        onChange={(e) => p.setTagName(e.target.value)}
      />
      <input
        aria-label="dlg-desc"
        value={p.tagDescription}
        onChange={(e) => p.setTagDescription(e.target.value)}
      />
      <button onClick={() => p.onCreateTag()}>dlg-create</button>
      <button onClick={() => p.onUpdateTag()}>dlg-update</button>
      <button onClick={() => p.onAddDialogClose()}>dlg-add-close</button>
      <button onClick={() => p.onEditDialogClose()}>dlg-edit-close</button>
      <button onClick={() => p.onViewHostsClose()}>dlg-hosts-close</button>
    </div>
  ),
}));

vi.mock("../../Services/api", () => ({
  default: { get: vi.fn(), post: vi.fn(), put: vi.fn(), delete: vi.fn() },
}));
vi.mock("../../Services/license", () => ({ refreshLicenseCache: vi.fn() }));
vi.mock("../../Services/permissions", async (orig) => {
  const actual = await orig<typeof import("../../Services/permissions")>();
  return { ...actual, hasPermission: vi.fn() };
});

const pluginTabs: Array<Record<string, unknown>> = [];
vi.mock("../../plugins", () => ({
  usePlugins: () => ({ settingsTabs: pluginTabs }),
}));

import axiosInstance from "../../Services/api";
import { refreshLicenseCache } from "../../Services/license";
import { hasPermission } from "../../Services/permissions";
import Settings from "../../Pages/Settings";

const m = (fn: unknown) => fn as unknown as ReturnType<typeof vi.fn>;

const TAGS = [
  { id: 1, name: "prod", description: "production", host_count: 3, updated_at: "2026-08-01T00:00:00Z" },
  { id: 2, name: "dev", description: null, host_count: 0, updated_at: "2026-08-02T00:00:00Z" },
];

const HOSTS = [
  { id: "h2", fqdn: "zeta.example", active: true, approval_status: "approved", platform: "Ubuntu", platform_version: "24.04" },
  { id: "h1", fqdn: "alpha.example", active: true, approval_status: "approved", platform: "Ubuntu", platform_version: "24.04" },
  { id: "h3", fqdn: "", active: true, approval_status: "approved", platform: "Debian", platform_version: "13" },
  { id: "h4", fqdn: "off.example", active: false, approval_status: "approved", platform: "Fedora", platform_version: "42" },
  { id: "h5", fqdn: "pending.example", active: true, approval_status: "pending" },
];

const ALL_MODULES = [
  "observability_engine",
  "av_management_engine",
  "firewall_orchestration_engine",
  "automation_engine",
  "compliance_engine",
  "reporting_engine",
  "airgap_collector_engine",
  "provisioning_engine",
  "repository_mirroring_engine",
  "external_idp_engine",
];

let routes: Record<string, unknown>;
const setHash = (h: string) => {
  globalThis.location.hash = h;
};

beforeEach(() => {
  vi.clearAllMocks();
  pluginTabs.length = 0;
  setHash("");
  routes = {
    "/api/v1/tags": TAGS,
    "/api/v1/tags/1/hosts": { id: 1, name: "prod", hosts: [] },
    "/api/v1/packages/summary": [{ os_name: "Ubuntu", os_version: "24.04" }],
    "/api/v1/hosts": HOSTS,
    "/api/v1/packages/search/count": { total_count: 42 },
    "/api/v1/packages/search": [{ name: "nginx" }, { name: "nginx-core" }],
  };
  m(axiosInstance.get).mockImplementation(async (url: string) => {
    const v = routes[url];
    if (v instanceof Error) throw v;
    if (v === undefined) throw new Error(`unrouted ${url}`);
    return { data: v };
  });
  m(axiosInstance.post).mockResolvedValue({ data: { success: true, message: "ok" } });
  m(axiosInstance.put).mockResolvedValue({ data: {} });
  m(axiosInstance.delete).mockResolvedValue({ data: {} });
  m(hasPermission).mockResolvedValue(true);
  m(refreshLicenseCache).mockResolvedValue({ modules: [], features: [], active: false });
  vi.spyOn(globalThis.console, "error").mockImplementation(() => {});
  vi.spyOn(globalThis.console, "log").mockImplementation(() => {});
});

afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
  setHash("");
});

const rail = () => screen.getByRole("navigation", { name: "settings tabs" });
const clickTab = (label: string) =>
  fireEvent.click(within(rail()).getByText(label));
const dlgState = () => screen.getByTestId("dlg-state").textContent ?? "";
const pkgState = () => screen.getByTestId("pkg-state").textContent ?? "";

const renderTags = async () => {
  setHash("#tags");
  render(<Settings />);
  await screen.findByTestId("row-1");
  await screen.findByRole("button", { name: /Add Tag/ });
};

describe("tags tab", () => {
  test("rows render with actions and the search narrows by column", async () => {
    await renderTags();
    expect(screen.getByTestId("row-2")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("tag-search"), {
      target: { value: "PRO" },
    });
    await waitFor(() => expect(screen.queryByTestId("row-2")).toBeNull());
    expect(screen.getByTestId("row-1")).toBeInTheDocument();
    // dev has a null description, so a description search skips it.
    fireEvent.click(screen.getByText("search-description"));
    fireEvent.change(screen.getByLabelText("tag-search"), {
      target: { value: "duct" },
    });
    await waitFor(() => expect(screen.queryByTestId("row-2")).toBeNull());
    expect(screen.getByTestId("row-1")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("tag-search"), {
      target: { value: "" },
    });
    await screen.findByTestId("row-2");
  });

  test("create sends a trimmed tag, reloads and closes", async () => {
    await renderTags();
    fireEvent.click(screen.getByRole("button", { name: /Add Tag/ }));
    expect(dlgState()).toContain("add:true");
    fireEvent.click(screen.getByText("dlg-create"));
    expect(axiosInstance.post).not.toHaveBeenCalled();
    fireEvent.change(screen.getByLabelText("dlg-name"), {
      target: { value: " qa " },
    });
    fireEvent.change(screen.getByLabelText("dlg-desc"), {
      target: { value: " quality " },
    });
    fireEvent.click(screen.getByText("dlg-create"));
    await waitFor(() =>
      expect(axiosInstance.post).toHaveBeenCalledWith("/api/v1/tags", {
        name: "qa",
        description: "quality",
      }),
    );
    await waitFor(() => expect(dlgState()).toContain("add:false"));
    expect(dlgState()).toContain("name: desc:");
    fireEvent.click(screen.getByRole("button", { name: /Add Tag/ }));
    fireEvent.click(screen.getByText("dlg-add-close"));
    expect(dlgState()).toContain("add:false");
  });

  test("edit prefills, puts the change, and a failed put keeps the dialog", async () => {
    await renderTags();
    fireEvent.click(within(screen.getByTestId("row-2")).getByTitle("Edit"));
    expect(dlgState()).toContain("edit:true");
    expect(dlgState()).toContain("name:dev desc:");
    fireEvent.change(screen.getByLabelText("dlg-name"), {
      target: { value: "develop" },
    });
    m(axiosInstance.put).mockRejectedValueOnce(new Error("conflict"));
    fireEvent.click(screen.getByText("dlg-update"));
    await waitFor(() => expect(axiosInstance.put).toHaveBeenCalledTimes(1));
    expect(dlgState()).toContain("edit:true");
    fireEvent.click(screen.getByText("dlg-update"));
    await waitFor(() =>
      expect(axiosInstance.put).toHaveBeenLastCalledWith("/api/v1/tags/2", {
        name: "develop",
        description: null,
      }),
    );
    await waitFor(() => expect(dlgState()).toContain("edit:false"));
    // Update without an editing tag is a no-op.
    fireEvent.click(screen.getByText("dlg-update"));
    expect(axiosInstance.put).toHaveBeenCalledTimes(2);
    fireEvent.click(within(screen.getByTestId("row-1")).getByTitle("Edit"));
    expect(dlgState()).toContain("desc:production");
    fireEvent.click(screen.getByText("dlg-edit-close"));
    expect(dlgState()).toContain("edit:false");
  });

  test("view hosts loads the tag's hosts; a failure leaves it closed", async () => {
    await renderTags();
    fireEvent.click(within(screen.getByTestId("row-1")).getByTitle("View Hosts"));
    await waitFor(() => expect(dlgState()).toContain("hosts:true tag:prod"));
    expect(axiosInstance.get).toHaveBeenCalledWith("/api/v1/tags/1/hosts");
    fireEvent.click(screen.getByText("dlg-hosts-close"));
    expect(dlgState()).toContain("hosts:false");
    fireEvent.click(within(screen.getByTestId("row-2")).getByTitle("View Hosts"));
    await waitFor(() =>
      expect(axiosInstance.get).toHaveBeenCalledWith("/api/v1/tags/2/hosts"),
    );
    expect(dlgState()).toContain("hosts:false");
  });

  test("delete removes every selected tag, then clears the selection", async () => {
    await renderTags();
    fireEvent.click(screen.getByText("select-all"));
    const del = screen.getByRole("button", { name: /Delete \(2\)/ });
    fireEvent.click(del);
    await waitFor(() => expect(axiosInstance.delete).toHaveBeenCalledTimes(2));
    expect(axiosInstance.delete).toHaveBeenCalledWith("/api/v1/tags/1");
    expect(axiosInstance.delete).toHaveBeenCalledWith("/api/v1/tags/2");
    await screen.findByRole("button", { name: /Delete \(0\)/ });
  });

  test("a failed delete keeps the selection", async () => {
    m(axiosInstance.delete).mockRejectedValue(new Error("in use"));
    await renderTags();
    fireEvent.click(screen.getByText("select-all"));
    fireEvent.click(screen.getByRole("button", { name: /Delete \(2\)/ }));
    await waitFor(() => expect(globalThis.console.error).toHaveBeenCalled());
    expect(screen.getByRole("button", { name: /Delete \(2\)/ })).toBeInTheDocument();
  });

  test("a failed create is logged and the dialog stays open", async () => {
    m(axiosInstance.post).mockRejectedValue(new Error("dup"));
    await renderTags();
    fireEvent.click(screen.getByRole("button", { name: /Add Tag/ }));
    fireEvent.change(screen.getByLabelText("dlg-name"), {
      target: { value: "prod" },
    });
    fireEvent.click(screen.getByText("dlg-create"));
    await waitFor(() =>
      expect(globalThis.console.error).toHaveBeenCalledWith(
        "Error creating tag:",
        expect.any(Error),
      ),
    );
    expect(dlgState()).toContain("add:true");
  });

  test("a rejected permission check hides the tag controls", async () => {
    m(hasPermission).mockRejectedValue(new Error("expired"));
    setHash("#tags");
    render(<Settings />);
    await screen.findByTestId("row-1");
    await waitFor(() =>
      expect(globalThis.console.error).toHaveBeenCalledWith(
        "Failed to resolve permissions:",
        expect.any(Error),
      ),
    );
    expect(screen.queryByRole("button", { name: /Add Tag/ })).toBeNull();
  });
});

describe("available packages", () => {
  test("loading on mount sorts and filters scoping hosts", async () => {
    setHash("#available-packages");
    render(<Settings />);
    await waitFor(() =>
      expect(pkgState()).toContain("hosts:,alpha.example,zeta.example"),
    );
    expect(pkgState()).toContain("summary:1");
  });

  test("a failed host list keeps the summary", async () => {
    routes["/api/v1/hosts"] = new Error("down");
    setHash("#available-packages");
    render(<Settings />);
    await waitFor(() => expect(pkgState()).toContain("summary:1"));
    await waitFor(() =>
      expect(globalThis.console.error).toHaveBeenCalledWith(
        "Error fetching hosts for package scoping:",
        expect.any(Error),
      ),
    );
    expect(pkgState()).toContain("hosts:");
  });

  test("a failed summary is logged", async () => {
    routes["/api/v1/packages/summary"] = new Error("down");
    setHash("#available-packages");
    render(<Settings />);
    await waitFor(() =>
      expect(globalThis.console.error).toHaveBeenCalledWith(
        "Error fetching package summary:",
        expect.any(Error),
      ),
    );
  });

  test("search sends every filter and pages correctly", async () => {
    setHash("#available-packages");
    render(<Settings />);
    await screen.findByTestId("stub-AvailablePackagesTab");
    // An empty term resets rather than searching.
    fireEvent.click(screen.getByText("search"));
    expect(pkgState()).toContain("searched:false");
    fireEvent.click(screen.getByText("set-term"));
    fireEvent.click(screen.getByText("set-os"));
    fireEvent.click(screen.getByText("set-host"));
    fireEvent.click(screen.getByText("set-mgr"));
    fireEvent.click(screen.getByText("search"));
    const expected = {
      query: "nginx",
      os_name: "Ubuntu",
      os_version: "24.04",
      host_id: "h1",
      package_manager: "apt",
    };
    await waitFor(() => expect(pkgState()).toContain("packages:2 total:42"));
    expect(axiosInstance.get).toHaveBeenCalledWith(
      "/api/v1/packages/search/count",
      { params: expected },
    );
    expect(axiosInstance.get).toHaveBeenCalledWith("/api/v1/packages/search", {
      params: { ...expected, limit: 10, offset: 10 },
    });
    expect(pkgState()).toContain("searched:true");
  });

  test("a failed search clears results", async () => {
    setHash("#available-packages");
    render(<Settings />);
    await screen.findByTestId("stub-AvailablePackagesTab");
    fireEvent.click(screen.getByText("set-term"));
    fireEvent.click(screen.getByText("search-default"));
    await waitFor(() => expect(pkgState()).toContain("packages:2"));
    expect(axiosInstance.get).toHaveBeenCalledWith("/api/v1/packages/search", {
      params: { query: "nginx", limit: 25, offset: 0 },
    });
    routes["/api/v1/packages/search/count"] = new Error("bad");
    fireEvent.click(screen.getByText("search-default"));
    await waitFor(() => expect(pkgState()).toContain("packages:0 total:0"));
  });

  test("refreshing one OS posts and reloads the summary later", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    setHash("#available-packages");
    render(<Settings />);
    await screen.findByTestId("stub-AvailablePackagesTab");
    await waitFor(() => expect(pkgState()).toContain("summary:1"));
    const before = m(axiosInstance.get).mock.calls.filter(
      (c) => c[0] === "/api/v1/packages/summary",
    ).length;
    fireEvent.click(screen.getByText("refresh-os"));
    await waitFor(() =>
      expect(axiosInstance.post).toHaveBeenCalledWith(
        "/api/v1/packages/refresh/Ubuntu/24.04",
      ),
    );
    await act(async () => {
      vi.advanceTimersByTime(2500);
    });
    await waitFor(() =>
      expect(
        m(axiosInstance.get).mock.calls.filter(
          (c) => c[0] === "/api/v1/packages/summary",
        ).length,
      ).toBeGreaterThan(before),
    );
  });

  test("a failed or unsuccessful single refresh does not reload", async () => {
    setHash("#available-packages");
    render(<Settings />);
    await screen.findByTestId("stub-AvailablePackagesTab");
    m(axiosInstance.post).mockResolvedValueOnce({ data: { success: false } });
    fireEvent.click(screen.getByText("refresh-os"));
    await waitFor(() => expect(axiosInstance.post).toHaveBeenCalledTimes(1));
    m(axiosInstance.post).mockRejectedValueOnce(new Error("x"));
    fireEvent.click(screen.getByText("refresh-os"));
    await waitFor(() =>
      expect(globalThis.console.error).toHaveBeenCalledWith(
        "Error refreshing packages:",
        expect.any(Error),
      ),
    );
  });

  test("refresh all uses known summaries and tolerates per-OS failures", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    routes["/api/v1/packages/summary"] = [
      { os_name: "Ubuntu", os_version: "24.04" },
      { os_name: "Debian", os_version: "13" },
    ];
    m(axiosInstance.post).mockImplementation(async (url: string) => {
      if (url.includes("Debian")) throw new Error("x");
      return { data: { success: true } };
    });
    setHash("#available-packages");
    render(<Settings />);
    await waitFor(() => expect(pkgState()).toContain("summary:2"));
    fireEvent.click(screen.getByText("refresh-all"));
    await waitFor(() => expect(axiosInstance.post).toHaveBeenCalledTimes(2));
    expect(axiosInstance.post).toHaveBeenCalledWith(
      "/api/v1/packages/refresh/Debian/13",
    );
    await act(async () => {
      vi.advanceTimersByTime(3500);
    });
  });

  test("refresh all with no summaries discovers OSes from active hosts", async () => {
    routes["/api/v1/packages/summary"] = [];
    m(axiosInstance.post).mockImplementation(async (url: string) => {
      if (url.includes("Debian")) throw new Error("x");
      return { data: { success: true } };
    });
    setHash("#available-packages");
    render(<Settings />);
    await waitFor(() => expect(pkgState()).toContain("summary:0"));
    fireEvent.click(screen.getByText("refresh-all"));
    await waitFor(() => expect(axiosInstance.post).toHaveBeenCalledTimes(2));
    expect(axiosInstance.post).toHaveBeenCalledWith(
      "/api/v1/packages/refresh/Ubuntu/24.04",
    );
    expect(axiosInstance.post).toHaveBeenCalledWith(
      "/api/v1/packages/refresh/Debian/13",
    );
    // Inactive Fedora host is not refreshed.
    expect(axiosInstance.post).not.toHaveBeenCalledWith(
      "/api/v1/packages/refresh/Fedora/42",
    );
  });

  test("refresh all logs when host discovery fails", async () => {
    routes["/api/v1/packages/summary"] = [];
    setHash("#available-packages");
    render(<Settings />);
    await waitFor(() => expect(pkgState()).toContain("summary:0"));
    routes["/api/v1/hosts"] = new Error("down");
    fireEvent.click(screen.getByText("refresh-all"));
    await waitFor(() =>
      expect(globalThis.console.error).toHaveBeenCalledWith(
        "Error fetching hosts for package refresh:",
        expect.any(Error),
      ),
    );
  });
});

describe("tab switching", () => {
  test("every licensed tab dispatches to its content", async () => {
    m(refreshLicenseCache).mockResolvedValue({
      modules: ALL_MODULES,
      features: [],
      active: true,
    });
    render(<Settings />);
    await within(rail()).findByText("Authentication");
    const cases: Array<[string, string]> = [
      ["Server Role", "stub-ServerRoleSettings"],
      ["Logging", "stub-LoggingSettings"],
      ["Host Defaults", "stub-HostDefaultsSettings"],
      ["Queues", "stub-QueuesTab"],
      ["Integrations", "stub-IntegrationsTab"],
      ["Ubuntu Pro", "stub-UbuntuProTab"],
      ["Antivirus", "stub-AntivirusDefaultsSettings"],
      ["Firewall Roles", "stub-FirewallRolesSettings"],
      ["Distributions", "stub-DistributionsSettings"],
      ["Update Profiles", "stub-UpgradeProfilesSettings"],
      ["Compliance Profiles", "stub-PackageProfilesSettings"],
      ["Report Branding", "stub-ReportBrandingSettings"],
      ["Report Templates", "stub-ReportTemplatesSettings"],
      ["Air-Gap Bundles", "stub-AirGapBundlesSettings"],
      ["Agent Install Mirrors", "stub-AgentMirrorsSettings"],
      ["Repository Mirroring", "stub-RepositoryMirroringSettings"],
      ["Authentication", "stub-AuthenticationProvidersSettings"],
      ["Configuration", "stub-ConfigurationSettings"],
    ];
    for (const [label, testId] of cases) {
      clickTab(label);
      expect(await screen.findByTestId(testId)).toBeInTheDocument();
    }
    expect(globalThis.location.hash).toBe("#configuration");
  });

  test("entering Available Packages starts a refresh timer that leaving clears", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const clear = vi.spyOn(globalThis, "clearInterval");
    render(<Settings />);
    await within(rail()).findByText("Available Packages");
    clickTab("Available Packages");
    await screen.findByTestId("stub-AvailablePackagesTab");
    // Re-entering replaces the running interval.
    clickTab("Available Packages");
    expect(clear).toHaveBeenCalled();
    const summaryCalls = () =>
      m(axiosInstance.get).mock.calls.filter(
        (c) => c[0] === "/api/v1/packages/summary",
      ).length;
    const before = summaryCalls();
    await act(async () => {
      vi.advanceTimersByTime(30000);
    });
    await waitFor(() => expect(summaryCalls()).toBeGreaterThan(before));
    const clearsBefore = clear.mock.calls.length;
    clickTab("Tags");
    expect(clear.mock.calls.length).toBeGreaterThan(clearsBefore);
    expect(await screen.findByTestId("row-1")).toBeInTheDocument();
  });

  test("the proplus plugin tab is placed after Configuration and renders", async () => {
    const Lic = () => <div data-testid="plugin-proplus">license body</div>;
    const Other = () => <div data-testid="plugin-other">other body</div>;
    pluginTabs.push(
      { id: "other", labelKey: "Other Plugin", component: Other },
      { id: "proplus", labelKey: "SysManage License", component: Lic },
    );
    setHash("#proplus");
    render(<Settings />);
    expect(await screen.findByTestId("plugin-proplus")).toBeInTheDocument();
    const labels = within(rail())
      .getAllByRole("button")
      .map((b) => b.textContent);
    // Rail is grouped by category: proplus lands in System, and because it
    // is spliced in right after Configuration it precedes every other System
    // tab, while ordinary plugin tabs trail at the end.
    expect(labels.indexOf("SysManage License")).toBeLessThan(
      labels.indexOf("Server Role"),
    );
    expect(labels.at(-1)).toBe("Other Plugin");
    clickTab("Other Plugin");
    expect(await screen.findByTestId("plugin-other")).toBeInTheDocument();
    expect(globalThis.location.hash).toBe("#other");
  });

  test("a hashchange to a real tab switches content", async () => {
    render(<Settings />);
    await screen.findByTestId("stub-ConfigurationSettings");
    setHash("#queues");
    await act(async () => {
      globalThis.dispatchEvent(new Event("hashchange"));
    });
    expect(await screen.findByTestId("stub-QueuesTab")).toBeInTheDocument();
  });
});
