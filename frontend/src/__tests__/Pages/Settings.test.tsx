// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

import { render, screen, waitFor, within } from "@testing-library/react";
import { vi, describe, beforeEach, afterEach, test, expect } from "vitest";

vi.mock("react-i18next", () => {
  const t = (key: string, fallback?: string) =>
    typeof fallback === "string" ? fallback : key;
  return { useTranslation: () => ({ t, i18n: { language: "en" } }) };
});

// DataGrid's border shorthand with a CSS var trips jsdom's cssstyle; the page
// logic under test is the tab rail and license gating, not grid internals.
vi.mock("@mui/x-data-grid", () => ({
  DataGrid: ({ rows }: { rows?: Array<{ id: string }> }) => (
    <div data-testid="grid">{`rows:${rows?.length ?? 0}`}</div>
  ),
}));

vi.mock("../../Components/SearchBox", () => ({ default: () => <div data-testid="stub-SearchBox" /> }));
vi.mock("../../Components/ColumnVisibilityButton", () => ({ default: () => <div data-testid="stub-ColumnVisibilityButton" /> }));
vi.mock("../../Components/ConfigurationSettings", () => ({ default: () => <div data-testid="stub-ConfigurationSettings" /> }));
vi.mock("../../Components/AntivirusDefaultsSettings", () => ({ default: () => <div data-testid="stub-AntivirusDefaultsSettings" /> }));
vi.mock("../../Components/HostDefaultsSettings", () => ({ default: () => <div data-testid="stub-HostDefaultsSettings" /> }));
vi.mock("../../Components/FirewallRolesSettings", () => ({ default: () => <div data-testid="stub-FirewallRolesSettings" /> }));
vi.mock("../../Components/DistributionsSettings", () => ({ default: () => <div data-testid="stub-DistributionsSettings" /> }));
vi.mock("../../Components/UpgradeProfilesSettings", () => ({ default: () => <div data-testid="stub-UpgradeProfilesSettings" /> }));
vi.mock("../../Components/PackageProfilesSettings", () => ({ default: () => <div data-testid="stub-PackageProfilesSettings" /> }));
vi.mock("../../Components/ReportBrandingSettings", () => ({ default: () => <div data-testid="stub-ReportBrandingSettings" /> }));
vi.mock("../../Components/ReportTemplatesSettings", () => ({ default: () => <div data-testid="stub-ReportTemplatesSettings" /> }));
vi.mock("../../Components/AirGapBundlesSettings", () => ({ default: () => <div data-testid="stub-AirGapBundlesSettings" /> }));
vi.mock("../../Components/AgentMirrorsSettings", () => ({ default: () => <div data-testid="stub-AgentMirrorsSettings" /> }));
vi.mock("../../Components/RepositoryMirroringSettings", () => ({ default: () => <div data-testid="stub-RepositoryMirroringSettings" /> }));
vi.mock("../../Components/AuthenticationProvidersSettings", () => ({ default: () => <div data-testid="stub-AuthenticationProvidersSettings" /> }));
vi.mock("../../Components/ServerRoleSettings", () => ({ default: () => <div data-testid="stub-ServerRoleSettings" /> }));
vi.mock("../../Components/LoggingSettings", () => ({ default: () => <div data-testid="stub-LoggingSettings" /> }));
vi.mock("../../Components/settings/AvailablePackagesTab", () => ({ default: () => <div data-testid="stub-AvailablePackagesTab" /> }));
vi.mock("../../Components/settings/IntegrationsTab", () => ({ default: () => <div data-testid="stub-IntegrationsTab" /> }));
vi.mock("../../Components/settings/QueuesTab", () => ({ default: () => <div data-testid="stub-QueuesTab" /> }));
vi.mock("../../Components/settings/UbuntuProTab", () => ({ default: () => <div data-testid="stub-UbuntuProTab" /> }));
vi.mock("../../Components/settings/SettingsDialogs", () => ({ default: () => <div data-testid="stub-SettingsDialogs" /> }));
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

// The settings "tabs" are a ListItemButton rail inside a labelled <nav>, not
// MUI <Tabs>, so there is no role="tab" to query.
const rail = () => screen.getByRole("navigation", { name: "settings tabs" });
const railItems = () => within(rail()).getAllByRole("button");
const selectedItems = () =>
  railItems().filter((el) => el.className.includes("Mui-selected"));

const setHash = (h: string) => {
  globalThis.location.hash = h;
};

beforeEach(() => {
  vi.clearAllMocks();
  pluginTabs.length = 0;
  setHash("");
  m(axiosInstance.get).mockResolvedValue({ data: [] });
  m(hasPermission).mockResolvedValue(true);
  m(refreshLicenseCache).mockResolvedValue({ modules: [], features: [], active: false });
});

afterEach(() => {
  vi.restoreAllMocks();
  setHash("");
});

describe("initial render", () => {
  test("renders the tab rail and loads tags", async () => {
    render(<Settings />);
    await waitFor(() => expect(axiosInstance.get).toHaveBeenCalledWith("/api/v1/tags"));
    expect(railItems().length).toBeGreaterThan(0);
  });

  test("a failing tag load still renders the page", async () => {
    // Tags are one tab's data; losing them must not cost the whole Settings
    // screen, which is where an operator goes to fix things.
    m(axiosInstance.get).mockRejectedValue(new Error("boom"));
    render(<Settings />);
    await waitFor(() => expect(railItems().length).toBeGreaterThan(0));
  });

  test("a failing license lookup degrades to the unlicensed tab set", async () => {
    m(refreshLicenseCache).mockRejectedValue(new Error("offline"));
    render(<Settings />);
    await waitFor(() => expect(railItems().length).toBeGreaterThan(0));
  });
});

describe("license gating", () => {
  test("an unlicensed install sees fewer tabs than a licensed one", async () => {
    // The gate is the product boundary: a Community user must not be shown
    // Enterprise tabs they cannot open.
    const { unmount } = render(<Settings />);
    await waitFor(() => expect(railItems().length).toBeGreaterThan(0));
    const communityCount = railItems().length;
    unmount();

    // Real engine codes from settingsCategories' moduleRequired gates -- a
    // made-up module name unlocks nothing and the assertion would pass only by
    // accident.
    m(refreshLicenseCache).mockResolvedValue({
      modules: [
        "reporting_engine",
        "secrets_engine",
        "compliance_engine",
        "av_management_engine",
        "automation_engine",
      ],
      features: [],
      active: true,
    });
    render(<Settings />);
    await waitFor(() =>
      expect(railItems().length).toBeGreaterThan(communityCount),
    );
  });

  test("a plugin tab whose module is unlicensed is hidden", async () => {
    pluginTabs.push({
      id: "ghost",
      labelKey: "Ghost Tab",
      moduleRequired: "not-licensed",
    });
    render(<Settings />);
    await waitFor(() => expect(railItems().length).toBeGreaterThan(0));
    expect(screen.queryByText("Ghost Tab")).not.toBeInTheDocument();
  });

  test("a plugin tab whose feature flag is unlicensed is hidden", async () => {
    // Distinct from moduleRequired: this hides an Enterprise capability that
    // ships INSIDE a Professional module the customer does own.
    m(refreshLicenseCache).mockResolvedValue({
      modules: ["reporting"],
      features: [],
      active: true,
    });
    pluginTabs.push({
      id: "flagged",
      labelKey: "Flagged Tab",
      moduleRequired: "reporting",
      featureFlag: "enterprise-only",
    });
    render(<Settings />);
    await waitFor(() => expect(railItems().length).toBeGreaterThan(0));
    expect(screen.queryByText("Flagged Tab")).not.toBeInTheDocument();
  });

  test("a plugin tab with neither gate stays visible", async () => {
    pluginTabs.push({ id: "always", labelKey: "Always Tab" });
    render(<Settings />);
    await waitFor(() => expect(screen.getByText("Always Tab")).toBeInTheDocument());
  });
});

describe("hash navigation", () => {
  test("an unknown hash falls back to the first tab rather than nothing", async () => {
    setHash("#no-such-tab");
    render(<Settings />);
    await waitFor(() => expect(railItems().length).toBeGreaterThan(0));
    expect(selectedItems()).toHaveLength(1);
  });

  test("an empty hash selects the first tab", async () => {
    render(<Settings />);
    await waitFor(() => expect(railItems().length).toBeGreaterThan(0));
    expect(railItems()[0].className).toContain("Mui-selected");
  });
});
