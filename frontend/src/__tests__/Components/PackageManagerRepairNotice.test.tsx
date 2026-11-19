// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

// Hosts whose package manager needs repair, and those not safe to reboot
// (2026-11-19): shown with the repair one click away.

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactElement } from "react";
import { MemoryRouter } from "react-router";
import { vi, beforeEach, test, expect } from "vitest";

vi.mock("react-i18next", () => {
  const fill = (text: string, opts?: Record<string, unknown>) =>
    text.replace(/\{\{(\w+)\}\}/g, (_m, key) => String(opts?.[key] ?? ""));
  const value = {
    t: (k: string, f?: string | Record<string, unknown>, o?: Record<string, unknown>) =>
      typeof f === "string" ? fill(f, o) : k,
    i18n: { language: "en" },
  };
  return { useTranslation: () => value };
});
vi.mock("../../Services/hosts", () => ({ doGetHostsSummary: vi.fn(), doRepairPackageManagers: vi.fn() }));
vi.mock("../../Services/permissions", () => ({
  hasPermissionSync: vi.fn(() => true),
  SecurityRoles: { APPLY_SOFTWARE_UPDATE: "Apply Software Update" },
}));

import { doGetHostsSummary, doRepairPackageManagers } from "../../Services/hosts";
import type { SysManageHost } from "../../Services/hosts";
import PackageManagerRepairNotice from "../../Components/PackageManagerRepairNotice";

const host = (over: Partial<SysManageHost>): SysManageHost =>
  ({ id: "h1", fqdn: "beast", active: true, ...over }) as SysManageHost;

const UNSAFE = host({
  package_manager_needs_repair: true, package_manager_repairable: true,
  package_manager_repair_reason: "Packages not fully installed: linux-image-7.0.0-44-generic",
  reboot_unsafe: true,
  reboot_unsafe_reason: "Not safe to reboot: linux-image-7.0.0-44-generic is only partly installed",
});

beforeEach(() => {
  vi.mocked(doGetHostsSummary).mockReset();
  vi.mocked(doRepairPackageManagers).mockReset();
});

const summary = (repair: SysManageHost[]) => ({
  total: 2, approved: 2, approved_up: 2, approved_down: 0, reboot_required: 0,
  package_manager_repair: repair.length, reboot_unsafe: repair.filter((h) => h.reboot_unsafe).length,
  repair_hosts: repair,
});

const shown = (ui: ReactElement) => render(<MemoryRouter>{ui}</MemoryRouter>);

test("a healthy fleet shows nothing", async () => {
  vi.mocked(doGetHostsSummary).mockResolvedValue(summary([]));
  const { container } = shown(<PackageManagerRepairNotice />);
  await waitFor(() => expect(doGetHostsSummary).toHaveBeenCalled());
  expect(container).toBeEmptyDOMElement();
});

test("a host that may not boot is an error naming the host and why", async () => {
  vi.mocked(doGetHostsSummary).mockResolvedValue(summary([UNSAFE]));
  shown(<PackageManagerRepairNotice />);
  expect(await screen.findByText("Do not reboot until the package manager is repaired")).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "beast" })).toHaveAttribute("href", "/hosts/h1");
  expect(screen.getByText(/only partly installed/)).toBeInTheDocument();
});

test("a repair is one click away", async () => {
  vi.mocked(doGetHostsSummary).mockResolvedValue(summary([UNSAFE]));
  vi.mocked(doRepairPackageManagers).mockResolvedValue({ requested: 1, started: 1, skipped: [] });
  const started = vi.fn();
  shown(<PackageManagerRepairNotice onRepairStarted={started} />);
  fireEvent.click(await screen.findByRole("button", { name: "Repair Package Manager" }));
  await waitFor(() => expect(doRepairPackageManagers).toHaveBeenCalledWith(["h1"]));
  expect(await screen.findByText("Package manager repair started on 1 host(s).")).toBeInTheDocument();
  expect(started).toHaveBeenCalled();
});

test("on a host's own page it uses that host and fetches nothing", () => {
  shown(<PackageManagerRepairNotice host={host({ package_manager_needs_repair: true,
    package_manager_repair_reason: "dpkg was interrupted" })} />);
  expect(screen.getByText("Package manager needs repair")).toBeInTheDocument();
  expect(screen.getByText("dpkg was interrupted")).toBeInTheDocument();
  expect(doGetHostsSummary).not.toHaveBeenCalled();
});

test("more hosts than are named are counted", async () => {
  const many = Array.from({ length: 7 }, (_v, i) =>
    host({ id: `h${i}`, fqdn: `host${i}`, package_manager_needs_repair: true }));
  vi.mocked(doGetHostsSummary).mockResolvedValue({ ...summary(many), package_manager_repair: 30 });
  shown(<PackageManagerRepairNotice />);
  expect(await screen.findByText("and 25 more on the Hosts page")).toBeInTheDocument();
});
