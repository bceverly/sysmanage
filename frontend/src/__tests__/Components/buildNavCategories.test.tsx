// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

// Focused unit tests for the pure ``buildNavCategories`` helper extracted from
// <Navbar/>.  The render-level Navbar test covers the common community case;
// this exercises the per-destination gating branches (air-gap server roles,
// plugin feature-flag gating, RBAC role hiding) directly and cheaply.

import { describe, it, expect, vi, beforeEach } from "vitest";

vi.mock("../../Services/permissions", () => ({
  hasPermissionSync: vi.fn(() => true),
  fetchUserPermissions: vi.fn(() => Promise.resolve()),
}));

import { buildNavCategories } from "../../Components/Navbar";
import { hasPermissionSync } from "../../Services/permissions";

// Identity translator (return the provided default, else the key).
const t = ((key: string, def?: string) => def || key) as unknown as Parameters<
  typeof buildNavCategories
>[0];

const baseOpts = {
  navItems: [] as { path: string; labelKey: string; featureFlag?: string }[],
  activeLicenseFeatures: [] as string[],
  activeLicenseModules: [] as string[],
  federationLicensed: false,
  serverRole: "standard",
};

const allPaths = (cats: ReturnType<typeof buildNavCategories>) =>
  cats.flatMap((c) => c.items.map((i) => i.path));

describe("buildNavCategories", () => {
  beforeEach(() => {
    vi.mocked(hasPermissionSync).mockReturnValue(true);
  });

  it("returns only community destinations by default and drops empty categories", () => {
    const cats = buildNavCategories(t, baseOpts);
    // security + insights are empty without their license → filtered out.
    expect(cats.map((c) => c.id)).toEqual(["fleet", "patching", "automation", "admin"]);
    expect(allPaths(cats)).toEqual([
      "/hosts",
      "/map",
      "/updates",
      "/os-upgrades",
      "/maintenance-windows",
      "/scripts",
      "/users",
      "/settings",
    ]);
    expect(allPaths(cats)).not.toContain("/sites");
    expect(allPaths(cats)).not.toContain("/secrets");
    expect(allPaths(cats)).not.toContain("/reports");
  });

  it("adds /sites only when federation is licensed", () => {
    expect(allPaths(buildNavCategories(t, baseOpts))).not.toContain("/sites");
    const fleet = buildNavCategories(t, { ...baseOpts, federationLicensed: true }).find(
      (c) => c.id === "fleet",
    )!;
    expect(fleet.items.map((i) => i.path)).toContain("/sites");
  });

  it("adds /secrets only with the secrets_engine module", () => {
    const cats = buildNavCategories(t, {
      ...baseOpts,
      activeLicenseModules: ["secrets_engine"],
    });
    expect(cats.find((c) => c.id === "security")!.items.map((i) => i.path)).toContain(
      "/secrets",
    );
  });

  it("adds /reports only with BOTH the reporting module and the reports feature", () => {
    expect(
      allPaths(
        buildNavCategories(t, { ...baseOpts, activeLicenseModules: ["reporting_engine"] }),
      ),
    ).not.toContain("/reports");
    expect(
      allPaths(
        buildNavCategories(t, { ...baseOpts, activeLicenseFeatures: ["reports"] }),
      ),
    ).not.toContain("/reports");
    expect(
      allPaths(
        buildNavCategories(t, {
          ...baseOpts,
          activeLicenseModules: ["reporting_engine"],
          activeLicenseFeatures: ["reports"],
        }),
      ),
    ).toContain("/reports");
  });

  it("shows air-gap repository/collector links only for the matching server role + engine", () => {
    expect(
      allPaths(buildNavCategories(t, { ...baseOpts, serverRole: "repository" })),
    ).not.toContain("/airgap/repositories");
    expect(
      allPaths(
        buildNavCategories(t, {
          ...baseOpts,
          serverRole: "repository",
          activeLicenseModules: ["airgap_repository_engine"],
        }),
      ),
    ).toContain("/airgap/repositories");
    expect(
      allPaths(
        buildNavCategories(t, {
          ...baseOpts,
          serverRole: "collector",
          activeLicenseModules: ["airgap_collector_engine"],
        }),
      ),
    ).toContain("/airgap/collections");
  });

  it("includes ungated plugin items and gates flagged ones by feature", () => {
    const navItems = [
      { path: "/plain-plugin", labelKey: "nav.plain" },
      { path: "/gated-plugin", labelKey: "nav.gated", featureFlag: "fancy" },
    ];
    const without = allPaths(buildNavCategories(t, { ...baseOpts, navItems }));
    expect(without).toContain("/plain-plugin");
    expect(without).not.toContain("/gated-plugin");

    const withFeature = allPaths(
      buildNavCategories(t, { ...baseOpts, navItems, activeLicenseFeatures: ["fancy"] }),
    );
    expect(withFeature).toContain("/gated-plugin");
  });

  it("hides a destination whose required security role is missing (RBAC)", () => {
    const navItems = [{ path: "/custom-metrics", labelKey: "nav.customMetrics" }];
    vi.mocked(hasPermissionSync).mockReturnValue(false);
    expect(allPaths(buildNavCategories(t, { ...baseOpts, navItems }))).not.toContain(
      "/custom-metrics",
    );
    vi.mocked(hasPermissionSync).mockReturnValue(true);
    expect(allPaths(buildNavCategories(t, { ...baseOpts, navItems }))).toContain(
      "/custom-metrics",
    );
  });
});
