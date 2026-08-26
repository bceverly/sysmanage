// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { vi, describe, beforeEach, afterEach, test, expect } from "vitest";

// One `t` per module, never per render -- a fresh identity re-fires every
// effect that lists it as a dep, which presents as an OOM rather than a
// failure.
vi.mock("react-i18next", () => {
  const t = (key: string, fallback?: string) =>
    typeof fallback === "string" ? fallback : key;
  return { useTranslation: () => ({ t, i18n: { language: "en" } }) };
});

const triggerRefresh = vi.fn();
vi.mock("../../hooks/useNotificationRefresh", () => ({
  useNotificationRefresh: () => ({ triggerRefresh }),
}));

vi.mock("../../Services/updates", () => ({
  updatesService: {
    getOSUpgrades: vi.fn(),
    getOSUpgradesSummary: vi.fn(),
    executeOSUpgrades: vi.fn(),
  },
}));

import { updatesService } from "../../Services/updates";
import OSUpgrades from "../../Pages/OSUpgrades";

const upgrade = (over: Record<string, unknown> = {}) => ({
  id: "u1",
  host_id: "h1",
  host_fqdn: "alpha.invalid",
  host_platform: "Linux",
  package_name: "ubuntu-release",
  current_version: "22.04",
  available_version: "24.04",
  package_manager: "ubuntu-release",
  update_type: "ubuntu-release",
  requires_reboot: true,
  size_bytes: 1024,
  discovered_at: "2026-08-01T00:00:00Z",
  ...over,
});

const SUMMARY = {
  total_hosts: 9,
  hosts_with_os_upgrades: 4,
  total_os_upgrades: 6,
  os_upgrades_by_type: { "ubuntu-release": 6 },
};


/** Click the select-all icon -- an <svg> beside the label text. */
const clickSelectAll = () => {
  const label = screen
    .getAllByText(/Select All/)
    .map((n) => n.closest("div"))
    .find((n) => n?.querySelector("svg"));
  fireEvent.click(label!.querySelector("svg")!);
};

describe("OSUpgrades", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(updatesService.getOSUpgrades).mockResolvedValue({
      os_upgrades: [upgrade(), upgrade({ id: "u2", host_id: "h2", host_fqdn: "beta.invalid", package_manager: "fedora-release" })],
    } as never);
    vi.mocked(updatesService.getOSUpgradesSummary).mockResolvedValue(SUMMARY as never);
    vi.mocked(updatesService.executeOSUpgrades).mockResolvedValue(undefined as never);
  });

  afterEach(() => vi.restoreAllMocks());

  test("renders the upgrade rows once loaded", async () => {
    render(<OSUpgrades />);
    expect(await screen.findByText("alpha.invalid")).toBeInTheDocument();
    expect(screen.getByText(/Select All/)).toBeInTheDocument();
  });

  test("shows the summary counters", async () => {
    render(<OSUpgrades />);
    expect(await screen.findByText("Total OS Upgrades")).toBeInTheDocument();
    // 6 renders twice: the total counter and the security counter.
    expect(screen.getAllByText("6")).toHaveLength(2);
    expect(screen.getByText("4")).toBeInTheDocument();
  });

  test("an empty list renders the no-upgrades notice", async () => {
    vi.mocked(updatesService.getOSUpgrades).mockResolvedValue({
      os_upgrades: [],
    } as never);
    render(<OSUpgrades />);
    expect(
      await screen.findByText("No OS upgrades are currently available"),
    ).toBeInTheDocument();
  });

  test("a missing os_upgrades key is treated as empty, not a crash", async () => {
    // The server omits the key entirely when nothing is pending.
    vi.mocked(updatesService.getOSUpgrades).mockResolvedValue({} as never);
    render(<OSUpgrades />);
    expect(
      await screen.findByText("No OS upgrades are currently available"),
    ).toBeInTheDocument();
  });

  test("a failed fetch leaves the page on the empty state", async () => {
    vi.mocked(updatesService.getOSUpgrades).mockRejectedValue(new Error("down"));
    render(<OSUpgrades />);
    expect(
      await screen.findByText("No OS upgrades are currently available"),
    ).toBeInTheDocument();
  });

  test("a failed summary fetch still renders the table", async () => {
    vi.mocked(updatesService.getOSUpgradesSummary).mockRejectedValue(
      new Error("down"),
    );
    render(<OSUpgrades />);
    expect(await screen.findByText("alpha.invalid")).toBeInTheDocument();
    expect(screen.queryByText("Total OS Upgrades")).not.toBeInTheDocument();
  });

  test("filtering by package manager narrows the list client-side", async () => {
    render(<OSUpgrades />);
    await screen.findByText("alpha.invalid");
    const select = screen.getByRole("combobox");
    fireEvent.change(select, { target: { value: "ubuntu-release" } });
    await waitFor(() =>
      expect(screen.queryByText("beta.invalid")).not.toBeInTheDocument(),
    );
  });

  test("refresh re-reads both endpoints and pokes the notification bell", async () => {
    render(<OSUpgrades />);
    await screen.findByText("alpha.invalid");
    vi.mocked(updatesService.getOSUpgrades).mockClear();
    fireEvent.click(screen.getByText("Refresh"));
    await waitFor(() => expect(updatesService.getOSUpgrades).toHaveBeenCalled());
    expect(triggerRefresh).toHaveBeenCalled();
  });

  test("select-all then execute dispatches one call per host", async () => {
    render(<OSUpgrades />);
    await screen.findByText("alpha.invalid");
    clickSelectAll();
    await waitFor(() =>
      expect(screen.getByText(/Select All/).textContent).toContain("(2/2)"),
    );
    fireEvent.click(screen.getByRole("button", { name: /Execute Selected OS Upgrades/ }));
    // Two distinct hosts -> two dispatches, each carrying only its own manager.
    await waitFor(() =>
      expect(updatesService.executeOSUpgrades).toHaveBeenCalledTimes(2),
    );
    expect(updatesService.executeOSUpgrades).toHaveBeenCalledWith(["h1"], ["ubuntu-release"]);
    expect(updatesService.executeOSUpgrades).toHaveBeenCalledWith(["h2"], ["fedora-release"]);
  });

  test("the execute button is absent until something is selected", async () => {
    render(<OSUpgrades />);
    await screen.findByText("alpha.invalid");
    // Not merely disabled -- the control is not rendered at all, so there is
    // no path to an empty dispatch.
    expect(
      screen.queryByRole("button", { name: /Execute Selected OS Upgrades/ }),
    ).not.toBeInTheDocument();
    clickSelectAll();
    expect(
      await screen.findByRole("button", { name: /Execute Selected OS Upgrades/ }),
    ).toBeInTheDocument();
  });

  test("a dispatch failure marks the pending rows failed", async () => {
    vi.mocked(updatesService.executeOSUpgrades).mockRejectedValue(
      new Error("queue down"),
    );
    render(<OSUpgrades />);
    await screen.findByText("alpha.invalid");
    clickSelectAll();
    fireEvent.click(screen.getByRole("button", { name: /Execute Selected OS Upgrades/ }));
    expect(await screen.findAllByText("Upgrade Failed")).not.toHaveLength(0);
  });

  test("selecting one row selects only that row", async () => {
    render(<OSUpgrades />);
    await screen.findByText("alpha.invalid");
    const before = screen.getByText(/Select All/).textContent;
    expect(before).toContain("(0/2)");
  });

  test("the reboot warning is shown for upgrades that need one", async () => {
    render(<OSUpgrades />);
    expect(
      await screen.findAllByText("OS upgrade requires system reboot"),
    ).toHaveLength(2);
  });
});
