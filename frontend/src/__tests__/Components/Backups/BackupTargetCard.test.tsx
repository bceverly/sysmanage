// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

// The backup target card's storage side (Phase 24.4, 24.5, 24.8): one test
// per state -- no storage host, one that cannot run restate, a seal the
// filesystem cannot take, storage jobs behind, a filesystem that cannot
// snapshot, not checked yet -- plus the btrfs seal in the dialog.

import { act, render, screen, fireEvent, waitFor, within } from "@testing-library/react";
import { vi, beforeEach, describe, test, expect } from "vitest";

vi.mock("react-i18next", async () => {
  const { t } = await import("../TimeSync/_i18nMock");
  return { useTranslation: () => ({ t, i18n: { language: "en" } }) };
});
vi.mock("../../../Services/backups", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../../Services/backups")>();
  return { ...actual, saveTarget: vi.fn() };
});

import { saveTarget } from "../../../Services/backups";
import type { BackupHost, BackupTarget, StorageStatus } from "../../../Services/backups";
import BackupTargetCard from "../../../Components/Backups/BackupTargetCard";

const target = (over: Partial<BackupTarget> = {}): BackupTarget => ({
  id: "t1",
  name: "nas",
  host_mount_point: "/mnt/backups",
  storage_host_id: "h9",
  storage_hostname: "nas.lab",
  storage_path: "/srv/backups/restate",
  storage_reason: null,
  max_concurrent: 2,
  seal_mode: "none",
  zfs_dataset: null,
  btrfs_snapshot_dir: null,
  storage_fs: { type: null, mount_point: null, btrfs_subvolume: null, checked_at: null },
  storage_status: null,
  warnings: [],
  problem: false,
  ...over,
});

const status = (over: Partial<StorageStatus> = {}): StorageStatus => ({
  policies: 2,
  confirmed: 1,
  last_seal: { status: "ok", finished_at: "2026-10-20T01:00:00", message: null },
  last_prune: null,
  last_check: { status: "failed", finished_at: "2026-10-19T01:00:00", message: "x" },
  stale: { seal_stale: [], prune_stale: [], check_stale: [] },
  ...over,
});

const hosts = [{ host_id: "h1", fqdn: "web.lab" } as BackupHost];

const show = (t: BackupTarget, canManage = false) =>
  render(
    <BackupTargetCard target={t} hosts={hosts} versions={[]} canManage={canManage} onChanged={vi.fn()} />,
  );

const alertWith = (text: RegExp) => screen.getAllByRole("alert").find((a) => text.test(a.textContent ?? ""));

describe("BackupTargetCard storage side", () => {
  beforeEach(() => vi.clearAllMocks());

  test("no storage host is a prominent error", () => {
    show(target({ storage_host_id: null, storage_hostname: null, warnings: ["no_storage_host", "not_sealed"] }));
    const alert = alertWith(/No storage host: backups are never sealed, pruned or checked/);
    expect(alert).toBeTruthy();
    expect(alert!.className).toMatch(/Error/);
    expect(alertWith(/Not sealed/)!.className).toMatch(/Warning/);
  });

  test.each([
    ["missing_tool", "Install restate"],
    ["tool_outdated", "Upgrade restate"],
    ["wrong_platform", "Not supported on this OS"],
  ])("a storage host that cannot run restate (%s) says why", (reason, words) => {
    show(target({ storage_reason: reason, warnings: ["storage_not_equipped"] }));
    const alert = alertWith(/storage jobs cannot run/);
    expect(alert!.textContent).toContain(words);
    expect(alert!.className).toMatch(/Error/);
  });

  test("the storage status shows confirmed job files and the last runs", () => {
    show(target({ storage_status: status(), storage_fs: { type: "zfs", mount_point: "/srv", btrfs_subvolume: null, checked_at: null } }));
    const box = screen.getByTestId("backup-storage-status");
    expect(within(box).getByText("Storage job files confirmed: 1 of 2")).toBeInTheDocument();
    expect(within(box).getByText(/Last seal: .*\(Succeeded\)/)).toBeInTheDocument();
    expect(within(box).getByText("Last prune: Never")).toBeInTheDocument();
    expect(within(box).getByText(/Last check: .*\(Failed\)/)).toBeInTheDocument();
    expect(within(box).getByText(/Storage filesystem: zfs/)).toBeInTheDocument();
  });

  test("storage jobs that fell behind name the hosts", () => {
    show(target({
      storage_status: status({ stale: { seal_stale: ["h1"], prune_stale: ["h1"], check_stale: ["h7"] } }),
      warnings: ["seal_stale", "prune_stale", "check_stale"],
    }));
    expect(alertWith(/Not sealed since the last backup: web.lab/)).toBeTruthy();
    expect(alertWith(/Not pruned for more than twice the backup interval: web.lab/)).toBeTruthy();
    expect(alertWith(/Not checked for more than twice the check interval: h7/)).toBeTruthy();
  });

  test("a seal the filesystem cannot take is an error", () => {
    show(target({
      seal_mode: "zfs_snapshot", zfs_dataset: "tank/b",
      storage_fs: { type: "ext4", mount_point: "/", btrfs_subvolume: null, checked_at: null },
      warnings: ["seal_fs_mismatch", "fs_cannot_snapshot"],
    }));
    const alert = alertWith(/The seal mode needs ZFS, but the storage path is on ext4/);
    expect(alert!.className).toMatch(/Error/);
  });

  test("a btrfs seal on a plain directory says how to make the subvolume", () => {
    show(target({
      seal_mode: "btrfs_snapshot", btrfs_snapshot_dir: "/srv/backups/.snapshots",
      storage_fs: { type: "btrfs", mount_point: "/srv", btrfs_subvolume: false, checked_at: null },
      warnings: ["btrfs_not_subvolume"],
    }));
    const alert = alertWith(/need the repository directory to be a subvolume/);
    expect(alert!.textContent).toContain("btrfs subvolume create /srv/backups/restate");
    expect(screen.getByText(/btrfs snapshot \(read-only\) \(\/srv\/backups\/.snapshots\)/)).toBeInTheDocument();
  });

  test("a filesystem that cannot snapshot is a caution, even unsealed", () => {
    show(target({
      storage_fs: { type: "xfs", mount_point: "/srv", btrfs_subvolume: null, checked_at: null },
      warnings: ["not_sealed", "fs_cannot_snapshot"],
    }));
    const alert = alertWith(/The storage path is on xfs, which cannot take snapshots/);
    expect(alert!.className).toMatch(/Info/);
  });

  test("an unchecked filesystem is neutral", () => {
    show(target({ warnings: ["fs_unchecked"] }));
    expect(alertWith(/Filesystem not checked yet/)!.className).toMatch(/Info/);
  });

  test("a failed drive on the storage host is an error naming it; space is shown", () => {
    show(target({
      storage_status: status(),
      storage_health: {
        drives: { failed: ["ada1"], warning: [] },
        space: { mount_point: "/srv", total_bytes: 1000 * 1024 ** 3, available_bytes: 30 * 1024 ** 3, used_percent: 97 },
      },
      warnings: ["storage_drive_failed", "storage_space_critical"],
      problem: true,
    }));
    const drive = alertWith(/failed drive or array \(ada1\)/);
    expect(drive?.className).toMatch(/Error/);
    const space = alertWith(/97% full/);
    expect(space?.className).toMatch(/Error/);
    expect(screen.getByText(/Storage space: 97% used/)).toBeInTheDocument();
  });

  test("a filling disk below the critical line is a warning", () => {
    show(target({
      storage_health: {
        drives: { failed: [], warning: [] },
        space: { mount_point: "/srv", total_bytes: 1000, available_bytes: 120, used_percent: 88 },
      },
      warnings: ["storage_space_low"],
    }));
    expect(alertWith(/88% full/)?.className).toMatch(/Warning/);
  });

  test("audit findings name the hosts and take their level from the audit", () => {
    show(target({
      storage_audit: {
        export_shared: { level: "error", hosts: ["h1"], params: { exports: ["/srv/backups/restate"] } },
        append_only_layout: { level: "warning", hosts: ["h1"], params: { unprotected_files: 9 } },
        nfs_local_locks: { level: "error", hosts: [], params: {} },
      },
      warnings: ["audit_export_shared", "audit_nfs_local_locks", "audit_append_only_layout"],
      problem: true,
    }));
    expect(alertWith(/Reachable through a shared export: web.lab/)?.className).toMatch(/Error/);
    expect(alertWith(/Not append-only: web.lab/)?.className).toMatch(/Warning/);
    expect(alertWith(/enable_locallocks=1/)?.className).toMatch(/Error/);
  });

  test("the dialog offers the btrfs seal and sends its snapshot directory", async () => {
    vi.mocked(saveTarget).mockResolvedValue(target());
    show(target(), true);
    fireEvent.click(screen.getByText("Edit target"));
    fireEvent.mouseDown(screen.getAllByRole("combobox")[1]);
    fireEvent.click(await screen.findByText("btrfs snapshot (read-only)"));
    expect(screen.getByText(/must sit on a btrfs subvolume/)).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText(/Snapshot directory on the storage host/), {
      target: { value: "/srv/backups/.snapshots" },
    });
    await act(async () => {
      fireEvent.click(screen.getByText("Save"));
    });
    await waitFor(() => expect(saveTarget).toHaveBeenCalled());
    expect(vi.mocked(saveTarget).mock.calls[0][0]).toMatchObject({
      seal_mode: "btrfs_snapshot",
      btrfs_snapshot_dir: "/srv/backups/.snapshots",
    });
  });
});
