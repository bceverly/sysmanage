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
  };
});

import {
  backupNow,
  getBackupOverview,
  getRuns,
  getSnapshots,
  restoreFiles,
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
  last_check: null,
  running: null,
  next_due: null,
  snapshot_count: 3,
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
    warnings: ["not_sealed"],
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
