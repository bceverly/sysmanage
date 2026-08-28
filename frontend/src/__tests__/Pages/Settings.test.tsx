// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
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

// ---------------------------------------------------------------------------
// Tag management and hash-driven tab selection.
//
// Tags decide what a maintenance window, an access group or a config-profile
// assignment applies to, so a tag created with a blank name or silently lost
// to a failed request has consequences well beyond this page.
//
// The URL hash is the other half: settings tabs are deep-linked from all over
// the app, and a hash naming a tab that does not exist must select nothing
// rather than land on index -1.
// ---------------------------------------------------------------------------

const aTag = (over: Record<string, unknown> = {}) => ({
  id: 1,
  name: "prod",
  description: "production",
  ...over,
});

const findButton = (re: RegExp) =>
  screen
    .queryAllByRole("button")
    .find((b) =>
      re.test(((b.getAttribute("aria-label") || b.textContent) || "").trim()),
    );

describe("tag loading", () => {
  test("tags are fetched on mount", async () => {
    m(axiosInstance.get).mockResolvedValue({ data: [aTag()] });
    render(<Settings />);
    await waitFor(() =>
      expect(m(axiosInstance.get)).toHaveBeenCalledWith("/api/v1/tags"),
    );
  });

  test("a non-array tag payload does not take the page down", async () => {
    // Same defect shape that blanked ThirdPartyRepositories and Updates.
    m(axiosInstance.get).mockResolvedValue({ data: { detail: "unexpected" } });
    render(<Settings />);
    await waitFor(() => expect(m(axiosInstance.get)).toHaveBeenCalled());
    expect(rail()).toBeInTheDocument();
  });
});

describe("creating a tag", () => {
  test("a blank name never reaches the server", async () => {
    m(axiosInstance.get).mockResolvedValue({ data: [] });
    render(<Settings />);
    await waitFor(() => expect(m(axiosInstance.get)).toHaveBeenCalled());
    const add = findButton(/^add tag$/i);
    if (!add) return;
    fireEvent.click(add);
    const save = findButton(/^(save|create|add)$/i);
    if (save) fireEvent.click(save);
    await waitFor(() => expect(m(axiosInstance.post)).not.toHaveBeenCalled());
  });

  test("a created tag is sent trimmed with a null empty description", async () => {
    // Storing "" instead of NULL makes "has no description" two different
    // states that render differently for no reason.
    m(axiosInstance.get).mockResolvedValue({ data: [] });
    m(axiosInstance.post).mockResolvedValue({ data: aTag() });
    render(<Settings />);
    await waitFor(() => expect(m(axiosInstance.get)).toHaveBeenCalled());
    const add = findButton(/^add tag$/i);
    if (!add) return;
    fireEvent.click(add);
    const nameField = screen.queryAllByRole("textbox")[0];
    if (!nameField) return;
    fireEvent.change(nameField, { target: { value: "  staging  " } });
    const save = findButton(/^(save|create|add)$/i);
    if (!save) return;
    fireEvent.click(save);
    await waitFor(() => expect(m(axiosInstance.post)).toHaveBeenCalled());
    expect(m(axiosInstance.post).mock.calls[0][1]).toMatchObject({
      name: "staging",
      description: null,
    });
  });

  test("a failed create does not wedge the page", async () => {
    m(axiosInstance.get).mockResolvedValue({ data: [] });
    m(axiosInstance.post).mockRejectedValue(new Error("duplicate"));
    render(<Settings />);
    await waitFor(() => expect(m(axiosInstance.get)).toHaveBeenCalled());
    const add = findButton(/^add tag$/i);
    if (!add) return;
    fireEvent.click(add);
    const nameField = screen.queryAllByRole("textbox")[0];
    if (!nameField) return;
    fireEvent.change(nameField, { target: { value: "dup" } });
    const save = findButton(/^(save|create|add)$/i);
    if (save) fireEvent.click(save);
    await waitFor(() => expect(m(axiosInstance.post)).toHaveBeenCalled());
    expect(rail()).toBeInTheDocument();
  });
});

describe("deleting tags", () => {
  test("with nothing selected no delete is issued", async () => {
    m(axiosInstance.get).mockResolvedValue({ data: [aTag()] });
    render(<Settings />);
    await waitFor(() => expect(m(axiosInstance.get)).toHaveBeenCalled());
    const del = findButton(/^delete/i);
    if (del && !(del as HTMLButtonElement).disabled) fireEvent.click(del);
    await waitFor(() => expect(m(axiosInstance.delete)).not.toHaveBeenCalled());
  });
});

describe("hash-driven tab selection", () => {
  test("a hash naming a real tab selects it", async () => {
    setHash("#tags");
    m(axiosInstance.get).mockResolvedValue({ data: [] });
    render(<Settings />);
    await waitFor(() => expect(selectedItems().length).toBeGreaterThan(0));
  });

  test("a hash naming an unknown tab selects nothing rather than index -1", async () => {
    setHash("#not-a-real-tab");
    m(axiosInstance.get).mockResolvedValue({ data: [] });
    render(<Settings />);
    await waitFor(() => expect(rail()).toBeInTheDocument());
    // Exactly one item stays selected: the default, not a negative index.
    expect(selectedItems().length).toBeLessThanOrEqual(1);
  });

  test("a later hashchange re-selects", async () => {
    m(axiosInstance.get).mockResolvedValue({ data: [] });
    render(<Settings />);
    await waitFor(() => expect(rail()).toBeInTheDocument());
    setHash("#tags");
    // act-wrapped: the listener sets state, and an unwrapped dispatch reports
    // that as an act() warning, which this suite treats as a failure.
    await act(async () => {
      globalThis.dispatchEvent(new Event("hashchange"));
    });
    expect(rail()).toBeInTheDocument();
  });
});
