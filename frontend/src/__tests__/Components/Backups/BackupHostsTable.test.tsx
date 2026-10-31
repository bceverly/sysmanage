// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

// The Backups table's layout (2026-10-31): one primary action per row and
// the rest in a "More" menu, the storage host listed as such, coverage only
// when it is not full, and compact dates with the full time on hover.

import { render, screen, fireEvent, within } from "@testing-library/react";
import { vi, describe, test, expect } from "vitest";

vi.mock("react-i18next", async () => {
  const { t } = await import("../TimeSync/_i18nMock");
  return { useTranslation: () => ({ t, i18n: { language: "en" } }) };
});
vi.mock("../../../Services/backups", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../../Services/backups")>();
  return { ...actual, backupNow: vi.fn(), equipBackup: vi.fn(), recheckBackup: vi.fn(), checkBackupReach: vi.fn() };
});

import type { BackupHost, BackupPolicy } from "../../../Services/backups";
import BackupHostsTable from "../../../Components/Backups/BackupHostsTable";
import { hostActions } from "../../../Components/Backups/BackupRowActions";
import { formatShortTime } from "../../../Components/Backups/backupLabels";

const policy = { id: "p1", host_id: "h1", enabled: true, interval_hours: 24, window_start_hour: null,
  keep_last: 7, check_interval_days: 7, quiesce: false, quiesce_with: [], keep_paths: [], skip_paths: [],
  estimate_bytes: null, repository_bytes: 2048, configured: true, storage_configured: true,
  restate_version: "2.2.0.14", storage_restate_version: null } as BackupPolicy;

const host = (over: Partial<BackupHost> = {}): BackupHost => ({
  host_id: "h1", fqdn: "web.lab", platform: "Linux", platform_release: "Ubuntu 26.04", equipped: true,
  reason: null, coverage: "full", policy, status: "ok", last_capture: null, last_good_capture: null,
  last_check: null, running: null, capture_requested: false, next_due: null, snapshot_count: 2,
  first_fit: null, equip_blocker: "equipped", ...over,
});

const all = { canManage: true, canRestore: true, hasTarget: true, storageHost: false };

describe("the primary action follows the host's state", () => {
  test.each([
    ["backed up", host(), "backupNow"],
    ["equipped, no policy", host({ policy: null, snapshot_count: 0 }), "configure"],
    ["not equipped, Equip offered", host({ equipped: false, policy: null, equip_blocker: null }), "equip"],
    ["not equipped, nothing to install", host({ equipped: false, policy: null, equip_blocker: "not_applicable" }), "recheck"],
    ["cannot reach the storage", host({ reach: { reachable: false, address: "10.0.0.9", port: 2049,
      storage_fqdn: "nas", error: null, checked_at: null } }), "reach"],
  ])("%s", (_name, row, primary) => {
    expect(hostActions(row, all)[0]).toBe(primary);
  });

  test("a viewer who may only restore gets Restore files, and the storage host nothing", () => {
    expect(hostActions(host(), { ...all, canManage: false })).toEqual(["restore"]);
    expect(hostActions(host({ policy: null }), { ...all, storageHost: true })).toEqual([]);
  });
});

const show = (rows: BackupHost[], storageHostId: string | null = null) =>
  render(<BackupHostsTable rows={rows} hasTarget storageHostId={storageHostId} canManage canRestore
    onChanged={vi.fn()} onError={vi.fn()} />);

describe("BackupHostsTable", () => {
  test("the secondary actions are in the row's More menu", () => {
    show([host()]);
    expect(screen.getByRole("button", { name: "Back up now" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Configure" })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "More: web.lab" }));
    const menu = screen.getByRole("menu");
    expect(within(menu).getAllByRole("menuitem").map(i => i.textContent)).toEqual(["Configure", "Restore files"]);
  });

  test("the storage host is listed last, as such, with no actions or checkbox", () => {
    show([host({ host_id: "nas", fqdn: "nas.lab", policy: null, status: "no_policy", snapshot_count: 0 }),
          host({ host_id: "h2", fqdn: "zzz.lab" })], "nas");
    const rows = screen.getAllByRole("row");
    expect(within(rows[rows.length - 1]).getByText("Storage host")).toBeInTheDocument();
    expect(within(rows[rows.length - 1]).queryByRole("button")).not.toBeInTheDocument();
    expect(screen.getByLabelText("Select nas.lab")).toBeDisabled();
    expect(screen.queryByText("Not configured")).not.toBeInTheDocument();
  });

  test("coverage shows only when it is not full", () => {
    show([host(), host({ host_id: "h2", fqdn: "files.lab", coverage: "files_only" })]);
    expect(screen.getAllByRole("img", { name: "Files only" })).toHaveLength(1);
    expect(screen.queryByText("Full (files and packages)")).not.toBeInTheDocument();
  });

  test("dates are short, with the full time on hover; a running backup's next due says Running", async () => {
    show([host({ last_good_capture: { finished_at: "2026-10-29T15:45:26" } as BackupHost["last_good_capture"] }),
          host({ host_id: "h2", fqdn: "busy.lab", status: "running",
                 running: { action: "capture", status: "running", progress: null } as unknown as BackupHost["running"] })]);
    const short = formatShortTime("2026-10-29T15:45:26");
    expect(short).not.toContain("26 ");
    fireEvent.mouseOver(screen.getByText(short));
    expect(await screen.findByRole("tooltip")).toHaveTextContent(new Date("2026-10-29T15:45:26Z").toLocaleString());
    expect(screen.getByText("Running")).toBeInTheDocument();
  });

  test("the short date names the year only when it is not this year", () => {
    const now = new Date("2026-10-31T12:00:00Z");
    expect(formatShortTime("2026-10-29T15:45:26Z", now)).not.toMatch(/2026/);
    expect(formatShortTime("2025-10-29T15:45:26Z", now)).toMatch(/2025/);
  });
});
