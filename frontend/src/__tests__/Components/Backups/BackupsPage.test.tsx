// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { vi, beforeEach, describe, test, expect } from "vitest";

vi.mock("react-i18next", async () => {
  const { t } = await import("../TimeSync/_i18nMock");
  return { useTranslation: () => ({ t, i18n: { language: "en" } }) };
});
vi.mock("../../../hooks/useVisiblePolling", () => ({ useVisiblePolling: vi.fn() }));
vi.mock("../../../Services/permissions", () => ({
  hasPermission: vi.fn().mockResolvedValue(true),
  SecurityRoles: { MANAGE_BACKUPS: "Manage Backups", RESTORE_FILES: "Restore Files" },
}));
vi.mock("../../../Services/backups", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../../Services/backups")>();
  return {
    ...actual,
    getBackupOverview: vi.fn(),
    getRuns: vi.fn(),
    backupNow: vi.fn(),
    getSnapshots: vi.fn(),
    restoreFiles: vi.fn(),
    getRun: vi.fn(),
    savePolicy: vi.fn(),
    bulkBackupNow: vi.fn(),
    clearRuns: vi.fn(),
    equipBackup: vi.fn(),
    bulkEquipBackup: vi.fn(),
    bulkSetupBackups: vi.fn(),
    recheckBackup: vi.fn(),
  };
});

import {
  backupNow,
  getBackupOverview,
  getRuns,
  getSnapshots,
  restoreFiles,
  savePolicy,
  bulkBackupNow,
  clearRuns,
  equipBackup,
  bulkEquipBackup,
  bulkSetupBackups,
  recheckBackup,
} from "../../../Services/backups";
import type { BackupHost, BackupOverview, BackupRun } from "../../../Services/backups";
import Backups from "../../../Pages/Backups";
import { runStatusLabel, sortHostsForTest } from "./_helpers";

const policy = {
  id: "p1",
  host_id: "h1",
  enabled: true,
  interval_hours: 24,
  window_start_hour: null,
  keep_last: 14,
  check_interval_days: 7,
  quiesce: false,
  quiesce_with: [],
  keep_paths: [],
  skip_paths: [],
  estimate_bytes: null,
  repository_bytes: 2048,
  configured: true,
  storage_configured: true,
  restate_version: "2.0.0.0",
  storage_restate_version: null,
};

const host = (over: Partial<BackupHost>): BackupHost => ({
  host_id: "h1",
  fqdn: "web.lab",
  platform: "Linux",
  platform_release: "Ubuntu 26.04",
  equipped: true,
  reason: null,
  coverage: "full",
  policy,
  status: "ok",
  last_capture: null,
  last_good_capture: null,
  last_check: null,
  running: null,
  capture_requested: false,
  next_due: null,
  snapshot_count: 3,
  first_fit: null,
  ...over,
});

const overview = (over: Partial<BackupOverview> = {}): BackupOverview => ({
  target: {
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
    warnings: ["not_sealed"],
    problem: false,
  },
  hosts: [
    host({}),
    host({
      host_id: "h2",
      fqdn: "old.lab",
      equipped: false,
      reason: "tool_outdated",
      status: "not_equipped",
      snapshot_count: 0,
    }),
    host({
      host_id: "h3",
      fqdn: "bare.lab",
      equipped: false,
      reason: "missing_tool",
      status: "not_equipped",
      policy: null,
      snapshot_count: 0,
    }),
  ],
  counts: { ok: 1, not_equipped: 2 },
  restate_versions: ["2.0.0.0"],
  ...over,
});

const run = (over: Partial<BackupRun>): BackupRun => ({
  id: "r1",
  policy_id: "p1",
  host_id: "h1",
  action: "check",
  status: "ok",
  exit_code: 0,
  queued_at: "2026-10-20T01:00:00",
  started_at: null,
  finished_at: "2026-10-20T01:05:00",
  snapshot: null,
  message: null,
  restate_version: "2.0.0.0",
  requested_by: "system",
  progress: null,
  result: null,
  check_label: null,
  ...over,
});

describe("Backups page", () => {
  beforeEach(() => {
    vi.mocked(getBackupOverview).mockResolvedValue(overview());
    vi.mocked(getRuns).mockResolvedValue({
      total: 1,
      runs: [run({ check_label: "metadata_check_passed" })],
    });
  });

  test("shows the target, the seal warning, versions and the not-equipped reasons", async () => {
    render(<MemoryRouter><Backups /></MemoryRouter>);
    expect(await screen.findByText("Not sealed (no immutable copies)")).toBeInTheDocument();
    expect(screen.getByText(/restate versions in use/)).toHaveTextContent("2.0.0.0");
    expect(screen.getByText("Upgrade restate")).toBeInTheDocument();
    expect(screen.getByText("Install restate")).toBeInTheDocument();
    expect(await screen.findByText("Metadata check passed")).toBeInTheDocument();
    expect(screen.queryByText("Verified")).not.toBeInTheDocument();
  });

  test("a running capture shows Backing up, not the earlier failure", async () => {
    const failed = run({ id: "r0", action: "capture", status: "failed", finished_at: "2026-10-20T09:32:33" });
    const good = run({ id: "r9", action: "capture", status: "ok", finished_at: "2026-10-19T03:00:00" });
    vi.mocked(getBackupOverview).mockResolvedValue(overview({
      hosts: [host({
        status: "running",
        last_capture: failed,
        last_good_capture: good,
        running: run({ id: "r1", action: "capture", status: "running", finished_at: null }),
      })],
      counts: { running: 1 },
    }));
    render(<MemoryRouter><Backups /></MemoryRouter>);
    expect((await screen.findAllByText("Backing up")).length).toBeGreaterThan(0);
    expect(screen.queryByText("Failed")).not.toBeInTheDocument();
  });

  test("the policy dialog saves leave-out and keep path patterns, one per line", async () => {
    vi.mocked(savePolicy).mockResolvedValue(policy);
    render(<MemoryRouter><Backups /></MemoryRouter>);
    fireEvent.click((await screen.findAllByText("Configure"))[0]);
    fireEvent.change(screen.getByLabelText("Leave out (one path pattern per line)"), {
      target: { value: "**/previews\n\n  /var/tmp  \n" },
    });
    fireEvent.change(screen.getByLabelText("Also back up (one path pattern per line)"), {
      target: { value: "/home/*/Downloads" },
    });
    fireEvent.click(screen.getByText("Save"));
    await waitFor(() =>
      expect(savePolicy).toHaveBeenCalledWith("h3", expect.objectContaining({
        skip_paths: ["**/previews", "/var/tmp"],
        keep_paths: ["/home/*/Downloads"],
      })),
    );
  });

  test("Back up selected sends the picked hosts and reports started, waiting and skipped", async () => {
    vi.mocked(getBackupOverview).mockResolvedValue(overview({
      hosts: [
        host({}),
        host({ host_id: "h4", fqdn: "db.lab" }),
        host({ host_id: "h5", fqdn: "busy.lab", status: "running",
               running: run({ id: "r5", action: "capture", status: "running" }) }),
      ],
    }));
    vi.mocked(bulkBackupNow).mockResolvedValue({
      requested: 2, started: 1, waiting: 1,
      skipped: [{ host_id: "h4", fqdn: "db.lab", reason: "running" }],
    });
    render(<MemoryRouter><Backups /></MemoryRouter>);
    const all = await screen.findByLabelText("Select every host that can be backed up or equipped now");
    // busy.lab is already backing up: it cannot be picked
    expect(screen.getByLabelText("Select busy.lab")).toBeDisabled();
    fireEvent.click(all);
    expect(screen.getByText("Hosts selected: 2")).toBeInTheDocument();
    fireEvent.click(screen.getByText("Back up selected"));
    await waitFor(() => expect(bulkBackupNow).toHaveBeenCalledWith(["h1", "h4"]));
    expect(await screen.findByText("Started: 1. Waiting for a free slot: 1. Skipped: 1.")).toBeInTheDocument();
    expect(screen.getByText("db.lab: Already backing up")).toBeInTheDocument();
  });

  test("a host without restate offers Equip for backup, which asks its agent", async () => {
    vi.mocked(getBackupOverview).mockResolvedValue(overview({
      hosts: [host({ equipped: false, reason: "missing_tool", status: "not_equipped",
                     policy: null, equip: null, equip_blocker: null })],
    }));
    vi.mocked(equipBackup).mockResolvedValue({ command_id: "c1", equip: null });
    render(<MemoryRouter><Backups /></MemoryRouter>);
    fireEvent.click(await screen.findByText("Equip for backup"));
    await waitFor(() => expect(equipBackup).toHaveBeenCalledWith("h1"));
    expect(await screen.findByText("Installing restate; this can take a few minutes.")).toBeInTheDocument();
  });

  test("Check again asks the agent for a fresh report", async () => {
    vi.mocked(getBackupOverview).mockResolvedValue(overview({
      hosts: [host({ equipped: false, reason: "missing_tool", status: "not_equipped",
                     policy: null, equip_blocker: "not_applicable" })],
    }));
    vi.mocked(recheckBackup).mockResolvedValue({ command_id: "c2" });
    render(<MemoryRouter><Backups /></MemoryRouter>);
    // no package for this system: no Equip button, but a way forward
    expect(await screen.findByText("Install restate by hand on this system (build it from source)")).toBeInTheDocument();
    expect(screen.queryByText("Equip for backup")).not.toBeInTheDocument();
    fireEvent.click(screen.getByText("Check again"));
    await waitFor(() => expect(recheckBackup).toHaveBeenCalledWith("h1"));
  });

  test("an equip in progress or failed says so", async () => {
    vi.mocked(getBackupOverview).mockResolvedValue(overview({
      hosts: [
        host({ equipped: false, reason: "missing_tool", status: "not_equipped", policy: null,
               equip_blocker: "in_progress",
               equip: { status: "running", reason: null, detail: null, installed: null,
                        requested_at: "2026-10-27T10:00:00", finished_at: null } }),
        host({ host_id: "h2", fqdn: "db.lab", equipped: false, reason: "missing_tool",
               status: "not_equipped", policy: null, equip_blocker: null,
               equip: { status: "failed", reason: "checksum_mismatch", detail: "x.pkg", installed: null,
                        requested_at: "2026-10-27T10:00:00", finished_at: "2026-10-27T10:01:00" } }),
      ],
    }));
    render(<MemoryRouter><Backups /></MemoryRouter>);
    expect(await screen.findByText("Equipping: installing restate...")).toBeInTheDocument();
    expect(screen.getByText(
      "Equip for backup failed: The downloaded package did not match its published checksum, so it was not installed",
    )).toBeInTheDocument();
  });

  test("a capture held by a maintenance window reads waiting, and an overdue one says why", async () => {
    vi.mocked(getBackupOverview).mockResolvedValue(overview({
      hosts: [
        host({ status: "waiting_window", capture_held: true }),
        host({ host_id: "h2", fqdn: "db.lab", status: "overdue", capture_held: true }),
      ],
    }));
    render(<MemoryRouter><Backups /></MemoryRouter>);
    expect((await screen.findAllByText("Waiting for window")).length).toBeGreaterThan(0);
    expect(screen.getAllByText("The next backup waits for this host's maintenance window")).toHaveLength(1);
  });

  test("an equip held by a maintenance window says it is waiting", async () => {
    vi.mocked(getBackupOverview).mockResolvedValue(overview({
      hosts: [
        host({ equipped: false, reason: "missing_tool", status: "not_equipped", policy: null,
               equip_blocker: "in_progress",
               equip: { status: "running", reason: null, held: true, detail: null, installed: null,
                        requested_at: "2026-10-27T10:00:00", finished_at: null } }),
      ],
    }));
    render(<MemoryRouter><Backups /></MemoryRouter>);
    expect(await screen.findByText(
      "Waiting for this host's maintenance window to install restate",
    )).toBeInTheDocument();
    expect(screen.queryByText("Equipping: installing restate...")).not.toBeInTheDocument();
  });

  test("Equip selected sends only the picked hosts that are not equipped", async () => {
    vi.mocked(getBackupOverview).mockResolvedValue(overview({
      hosts: [
        host({}),
        host({ host_id: "h6", fqdn: "new.lab", equipped: false, reason: "missing_tool",
               status: "not_equipped", policy: null, equip_blocker: null }),
      ],
    }));
    vi.mocked(bulkEquipBackup).mockResolvedValue({ requested: 1, started: 1, skipped: [] });
    render(<MemoryRouter><Backups /></MemoryRouter>);
    fireEvent.click(await screen.findByLabelText("Select every host that can be backed up or equipped now"));
    fireEvent.click(screen.getByText("Equip selected for backup (1)"));
    await waitFor(() => expect(bulkEquipBackup).toHaveBeenCalledWith(["h6"]));
    expect(await screen.findByText("Equipping: 1. Skipped: 0.")).toBeInTheDocument();
  });

  test("Set up backups sends the picked equipped hosts that have no policy", async () => {
    vi.mocked(getBackupOverview).mockResolvedValue(overview({
      hosts: [
        host({}),
        host({ host_id: "h7", fqdn: "nopolicy.lab", policy: null, status: "no_policy" }),
      ],
    }));
    vi.mocked(bulkSetupBackups).mockResolvedValue({ requested: 1, created: 1, skipped: [] });
    render(<MemoryRouter><Backups /></MemoryRouter>);
    fireEvent.click(await screen.findByLabelText("Select nopolicy.lab"));
    fireEvent.click(screen.getByText("Set up backups for selected (1)"));
    await waitFor(() => expect(bulkSetupBackups).toHaveBeenCalledWith(["h7"]));
    expect(await screen.findByText(/Set up with the default policy: 1\. Skipped: 0\./)).toBeInTheDocument();
  });

  test("a host that cannot be picked says why on hover", async () => {
    vi.mocked(getBackupOverview).mockResolvedValue(overview({
      hosts: [host({ running: run({ action: "capture", status: "running" }) })],
    }));
    render(<MemoryRouter><Backups /></MemoryRouter>);
    const box = await screen.findByLabelText(`Select ${host({}).fqdn}`);
    expect(box).toBeDisabled();
    fireEvent.mouseOver(box.closest("span") as HTMLElement);
    expect(await screen.findByText("Already backing up")).toBeInTheDocument();
  });

  test("a host waiting for a free slot says so", async () => {
    vi.mocked(getBackupOverview).mockResolvedValue(overview({
      hosts: [host({ capture_requested: true })],
    }));
    render(<MemoryRouter><Backups /></MemoryRouter>);
    expect(await screen.findByText("Waiting for a free slot")).toBeInTheDocument();
  });

  test("Clear asks first, then clears the job list and reloads it", async () => {
    vi.mocked(clearRuns).mockResolvedValue({ cleared: 1 });
    render(<MemoryRouter><Backups /></MemoryRouter>);
    fireEvent.click(await screen.findByText("Clear list"));
    expect(screen.getByText("Clear the job list?")).toBeInTheDocument();
    expect(clearRuns).not.toHaveBeenCalled();
    const before = vi.mocked(getRuns).mock.calls.length;
    const buttons = screen.getAllByText("Clear list");
    fireEvent.click(buttons[buttons.length - 1]);
    await waitFor(() => expect(clearRuns).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(vi.mocked(getRuns).mock.calls.length).toBeGreaterThan(before));
  });

  test("a preview planned from the index says the data was not read", async () => {
    vi.mocked(getSnapshots).mockResolvedValue([{
      id: "s1", name: "20261021T153126Z", created_at: "2026-10-21T15:31:26", bytes: 10,
      new_bytes: 1, unique_bytes: null, files: 2, signed: false, gone_at: null,
    }]);
    vi.mocked(restoreFiles).mockResolvedValue(run({
      action: "restore", status: "ok",
      result: { files: 1, bytes: 8, plan: ["/home/a/contract.txt"], content_read: false },
    }));
    render(<MemoryRouter><Backups /></MemoryRouter>);
    fireEvent.click(await screen.findByText("Restore files"));
    fireEvent.click(await screen.findByLabelText("This snapshot is not signed. Restore it anyway."));
    fireEvent.click(screen.getByText("Preview"));
    expect(await screen.findByText(/Planned from the snapshot index/)).toBeInTheDocument();
  });

  test("Back up now queues a capture", async () => {
    vi.mocked(backupNow).mockResolvedValue(run({ action: "capture", status: "queued" }));
    render(<MemoryRouter><Backups /></MemoryRouter>);
    const buttons = (await screen.findAllByText("Back up now")).map(b => b.closest("button"));
    // old.lab cannot run restate yet: its button is disabled.
    expect(buttons.filter(b => b?.disabled)).toHaveLength(1);
    fireEvent.click(buttons.find(b => !b?.disabled) as HTMLButtonElement);
    await waitFor(() => expect(backupNow).toHaveBeenCalledWith("h1"));
  });

  test("a restore needs the unsigned acknowledgment and previews first", async () => {
    vi.mocked(getSnapshots).mockResolvedValue([
      {
        id: "s1",
        name: "2026-10-20T010000Z",
        created_at: "2026-10-20T01:00:00",
        bytes: 10,
        new_bytes: 1,
        unique_bytes: null,
        files: 2,
        signed: false,
        gone_at: null,
      },
    ]);
    vi.mocked(restoreFiles).mockResolvedValue(
      run({ action: "restore", status: "ok", result: { files: 2, bytes: 10, plan: ["/etc/a"] } }),
    );
    render(<MemoryRouter><Backups /></MemoryRouter>);
    fireEvent.click(await screen.findByText("Restore files"));
    const preview = await screen.findByText("Preview");
    expect(preview.closest("button")).toBeDisabled();
    fireEvent.click(screen.getByLabelText("This snapshot is not signed. Restore it anyway."));
    fireEvent.click(preview);
    await waitFor(() =>
      expect(restoreFiles).toHaveBeenCalledWith("h1", expect.objectContaining({
        dry_run: true,
        acknowledge_unsigned: true,
      })),
    );
    expect(await screen.findByText("/etc/a")).toBeInTheDocument();
    expect(screen.getByText("Restore to staging").closest("button")).not.toBeDisabled();
  });

  test("a status chip filters the hosts, and clicking it again shows all", async () => {
    render(<MemoryRouter><Backups /></MemoryRouter>);
    expect(await screen.findByText("old.lab")).toBeInTheDocument();
    fireEvent.click(screen.getByText("Backed up: 1"));
    expect(screen.queryByText("old.lab")).not.toBeInTheDocument();
    expect(screen.queryByText("bare.lab")).not.toBeInTheDocument();
    fireEvent.click(screen.getByText("Backed up: 1"));
    expect(await screen.findByText("old.lab")).toBeInTheDocument();
    fireEvent.click(screen.getByText("Not equipped: 2"));
    expect(screen.getByText("old.lab")).toBeInTheDocument();
    expect(screen.getByText("bare.lab")).toBeInTheDocument();
    fireEvent.click(screen.getByText("Show all hosts"));
    expect(screen.queryByText("Show all hosts")).not.toBeInTheDocument();
  });

  test("a backup that skipped files says how many, with the first ones", async () => {
    const incomplete = run({ id: "r5", action: "capture", status: "incomplete",
      result: {
        unreadable: { count: 3, first: [{ path: "/var/lib/secret", reason: "Permission denied" }] },
        quiesce: [
          { kind: "postgresql", name: "16-main", paused_at: "2026-10-23T02:00:00Z",
            resumed_at: "2026-10-23T02:00:12Z", status: "ok", message: "" },
          { kind: "nextcloud", name: "", paused_at: "2026-10-23T02:00:00Z",
            resumed_at: "", status: "failed", message: "occ exited 1" },
        ],
      } });
    vi.mocked(getBackupOverview).mockResolvedValue(overview({
      hosts: [host({ status: "incomplete", last_capture: incomplete, last_good_capture: incomplete })],
      counts: { incomplete: 1 },
    }));
    render(<MemoryRouter><Backups /></MemoryRouter>);
    expect(await screen.findByText("Files not read: 3")).toBeInTheDocument();
  });

  test("a capture's job shows each paused service and a failed pause", async () => {
    const paused = run({ id: "r6", action: "capture", status: "incomplete",
      result: { quiesce: [
        { kind: "postgresql", name: "16-main", paused_at: "2026-10-23T02:00:00Z",
          resumed_at: "2026-10-23T02:00:12Z", status: "ok", message: "" },
        { kind: "nextcloud", name: "", paused_at: "2026-10-23T02:00:00Z",
          resumed_at: "", status: "failed", message: "occ exited 1" },
      ] } });
    vi.mocked(getRuns).mockResolvedValue({ total: 1, runs: [paused] });
    render(<MemoryRouter><Backups /></MemoryRouter>);
    expect(await screen.findByText("Paused postgresql 16-main for 12 s")).toBeInTheDocument();
    expect(screen.getByText("Could not pause or resume nextcloud: occ exited 1")).toBeInTheDocument();
  });

  test("a load failure is shown", async () => {
    vi.mocked(getBackupOverview).mockRejectedValue(new Error("boom"));
    render(<MemoryRouter><Backups /></MemoryRouter>);
    expect(await screen.findByText("Could not load the backups.")).toBeInTheDocument();
  });
});

describe("backup labels", () => {
  test("a keyless check never reads as verified", () => {
    expect(runStatusLabel(run({ check_label: "metadata_check_passed" }))).toBe("Metadata check passed");
    expect(runStatusLabel(run({ check_label: "verified" }))).toBe("Verified");
    expect(runStatusLabel(run({ status: "busy" }))).toBe("Busy, will retry");
  });

  test("hosts sort worst first", () => {
    const rows = sortHostsForTest([
      host({ host_id: "a", fqdn: "a", status: "ok" }),
      host({ host_id: "b", fqdn: "b", status: "failed" }),
    ]);
    expect(rows.map(r => r.fqdn)).toEqual(["b", "a"]);
  });
});
