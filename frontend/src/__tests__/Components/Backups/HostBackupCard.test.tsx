// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

// The host's Backup card re-reads itself while a job runs, so "Backing up"
// turns into the result without a page reload, and stops once nothing runs.

import { act, render, waitFor } from "@testing-library/react";
import { vi, describe, test, expect, afterEach } from "vitest";

vi.mock("react-i18next", async () => {
  const { t } = await import("../TimeSync/_i18nMock");
  return { useTranslation: () => ({ t, i18n: { language: "en" } }) };
});
vi.mock("react-router", () => ({ useNavigate: () => vi.fn() }));
vi.mock("../../../Services/permissions", () => ({
  hasPermission: vi.fn().mockResolvedValue(false),
  SecurityRoles: { MANAGE_BACKUPS: "m", RESTORE_FILES: "r" },
}));
vi.mock("../../../Services/backups", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../../Services/backups")>();
  return { ...actual, getHostBackup: vi.fn() };
});

import { getHostBackup } from "../../../Services/backups";
import type { HostBackup } from "../../../Services/backups";
import HostBackupCard from "../../../Components/Backups/HostBackupCard";

const policy = {
  id: "p1", host_id: "h1", enabled: true, interval_hours: 24, window_start_hour: null,
  keep_last: 14, check_interval_days: 7, quiesce: false, quiesce_with: [], keep_paths: [],
  skip_paths: [], estimate_bytes: null, repository_bytes: 2048, configured: true,
  storage_configured: true, restate_version: "2.2.0.2", storage_restate_version: null,
};

const card = (running: unknown): HostBackup => ({
  host_id: "h1", fqdn: "t14", platform: "Linux", platform_release: "Ubuntu 26.04",
  equipped: true, reason: null, coverage: "full", policy, status: "ok",
  last_capture: null, last_good_capture: null, last_check: null, running,
  capture_requested: false, next_due: null, snapshot_count: 3, target: null,
} as unknown as HostBackup);

afterEach(() => {
  vi.useRealTimers();
  vi.mocked(getHostBackup).mockReset();
});

describe("HostBackupCard", () => {
  test("polls while a backup runs and stops once it has finished", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const running = { id: "r1", action: "capture", status: "running" };
    vi.mocked(getHostBackup)
      .mockResolvedValueOnce(card(running))
      .mockResolvedValue(card(null));
    render(<HostBackupCard hostId="h1" />);
    await waitFor(() => expect(getHostBackup).toHaveBeenCalledTimes(1));
    await act(async () => { await vi.advanceTimersByTimeAsync(5000); });
    await waitFor(() => expect(getHostBackup).toHaveBeenCalledTimes(2));
    // Finished: no more polls.
    await act(async () => { await vi.advanceTimersByTimeAsync(20000); });
    expect(getHostBackup).toHaveBeenCalledTimes(2);
  });

  test("does not poll when nothing is running", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    vi.mocked(getHostBackup).mockResolvedValue(card(null));
    render(<HostBackupCard hostId="h1" />);
    await waitFor(() => expect(getHostBackup).toHaveBeenCalledTimes(1));
    await act(async () => { await vi.advanceTimersByTimeAsync(20000); });
    expect(getHostBackup).toHaveBeenCalledTimes(1);
  });
});
