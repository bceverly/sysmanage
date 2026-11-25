// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

// The off-site cloud copy card (27.3): set up and run with Professional+;
// restore and the key export in every edition; frozen, not gone, after a
// lapse; hidden on an air-gapped site.

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
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
vi.mock("../../Services/backupCloudCopy", () => ({
  getCloudCopies: vi.fn(), getCloudCopyRuns: vi.fn(), runCloudCopy: vi.fn(), checkCloudCopy: vi.fn(),
  rotateCloudCopyKey: vi.fn(), updateCloudCopy: vi.fn(), createCloudCopy: vi.fn(),
  getRestorePoints: vi.fn(), estimateRestore: vi.fn(), restoreCloudCopy: vi.fn(),
  exportCloudCopyKeys: vi.fn(), getSetupGuide: vi.fn(),
}));

import {
  checkCloudCopy, createCloudCopy, estimateRestore, getCloudCopies, getCloudCopyRuns,
  getRestorePoints, restoreCloudCopy, runCloudCopy,
} from "../../Services/backupCloudCopy";
import type { CloudCopy, CloudCopyOverview } from "../../Services/backupCloudCopy";
import BackupCloudCopy from "../../Components/Backups/BackupCloudCopy";

const DEFAULTS = {
  full_every_days: 30, run_hour_utc: 2, keep_monthly: 6, keep_yearly: 7, exclude: [], include: [],
  bandwidth: { rules: [{ days: [0, 1, 2, 3, 4], start: "08:00", end: "18:00", kbps: 20000 }], default_kbps: 0 },
  part_mib: 256,
};

const copy = (over: Partial<CloudCopy> = {}): CloudCopy => ({
  id: "c1", target_id: "t1", enabled: true, bucket: "acme-offsite", region: "us-east-2",
  endpoint: null, prefix: "nas", storage_class: "DEEP_ARCHIVE", object_lock: true,
  lock_verified: true, checked_at: null, access_key_hint: "MPLE", settings: DEFAULTS,
  next_run_at: "2026-11-26T02:00:00", last_ok_at: "2026-11-25T02:30:00", last_error: null,
  last_run_id: "r1", key_id: "abcd", bytes_stored: 2e12, licensed: true, overdue: false,
  datasets: [{ dataset: "tank/backups/web-1a2b3c4d", bytes_stored: 2e12, streams: 3,
               last_uploaded_at: "2026-11-25T02:30:00", last_full_at: "2026-11-01T02:30:00" }],
  cost: { monthly_usd: 1.98, usd_per_tb_month: 0.99, minimum_days: 180 },
  ...over,
});

const overview = (over: Partial<CloudCopyOverview> = {}): CloudCopyOverview => ({
  available: true, licensed: true, defaults: DEFAULTS, copies: [copy()],
  targets: [{ id: "t1", name: "nas", storage_path: "/srv/backups", has_storage_host: true }],
  ...over,
});

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(getCloudCopies).mockResolvedValue(overview());
  vi.mocked(getCloudCopyRuns).mockResolvedValue([]);
  vi.mocked(runCloudCopy).mockResolvedValue({} as never);
  vi.mocked(checkCloudCopy).mockResolvedValue({} as never);
});

test("shows what is stored, the lock and the cost, and runs on request", async () => {
  render(<BackupCloudCopy canManage canRestore />);
  expect(await screen.findByText("nas to s3://acme-offsite/nas (us-east-2, DEEP_ARCHIVE)")).toBeTruthy();
  expect(screen.getByText("Object Lock on")).toBeTruthy();
  expect(screen.getByText(/about \$1\.98 a month/)).toBeTruthy();
  expect(screen.getByText("tank/backups/web-1a2b3c4d")).toBeTruthy();
  fireEvent.click(screen.getByText("Run now"));
  await waitFor(() => expect(runCloudCopy).toHaveBeenCalledWith("c1"));
});

test("after a lapse the copy is frozen but restore and export stay", async () => {
  vi.mocked(getCloudCopies).mockResolvedValue(overview({ licensed: false, copies: [copy({ licensed: false })] }));
  render(<BackupCloudCopy canManage canRestore />);
  expect(await screen.findByText(/the copy is frozen/)).toBeTruthy();
  expect(screen.queryByText("Run now")).toBeNull();
  expect(screen.queryByText("Settings")).toBeNull();
  expect(screen.getByText("Restore")).toBeTruthy();
  expect(screen.getByText("Export keys")).toBeTruthy();
});

test("nothing shows on an air-gapped site, or unlicensed with no copy", async () => {
  vi.mocked(getCloudCopies).mockResolvedValue(overview({ available: false }));
  const { container, unmount } = render(<BackupCloudCopy canManage canRestore />);
  await waitFor(() => expect(getCloudCopies).toHaveBeenCalled());
  expect(container.textContent).toBe("");
  unmount();
  vi.mocked(getCloudCopies).mockResolvedValue(overview({ licensed: false, copies: [] }));
  const second = render(<BackupCloudCopy canManage canRestore />);
  await waitFor(() => expect(getCloudCopies).toHaveBeenCalledTimes(2));
  expect(second.container.textContent).toBe("");
});

test("setting up asks only for the bucket, region and keys", async () => {
  vi.mocked(getCloudCopies).mockResolvedValue(overview({ copies: [] }));
  vi.mocked(createCloudCopy).mockResolvedValue(copy());
  render(<BackupCloudCopy canManage canRestore />);
  fireEvent.click(await screen.findByText("Set up the cloud copy"));
  fireEvent.change(screen.getByLabelText("S3 bucket"), { target: { value: "acme-offsite" } });
  fireEvent.change(screen.getByLabelText("Access key ID"), { target: { value: "AKIAIOSFODNN7EXAMPLE" } });
  fireEvent.change(screen.getByLabelText("Secret access key"), { target: { value: "s3cret" } });
  fireEvent.click(screen.getByText("Save"));
  await waitFor(() => expect(createCloudCopy).toHaveBeenCalled());
  const body = vi.mocked(createCloudCopy).mock.calls[0][0];
  expect(body.target_id).toBe("t1");
  expect(body.settings?.full_every_days).toBe(30);
  expect(body.settings?.bandwidth?.rules[0].kbps).toBe(20000);
});

test("a restore shows its cost first and goes into a new dataset", async () => {
  vi.mocked(getRestorePoints).mockResolvedValue([
    { dataset: "tank/b", snapshot: "sysmanage-offsite-20261125T020000Z", uploaded_at: "2026-11-25T02:30:00",
      streams: 2, bytes: 4e9 },
  ]);
  vi.mocked(estimateRestore).mockResolvedValue({
    bytes: 4e9, parts: 16, streams: 2, storage_class: "DEEP_ARCHIVE", tier: "Bulk", thaw_hours: 48,
    usd_thaw: 0.01, usd_transfer: 0.36,
  });
  vi.mocked(restoreCloudCopy).mockResolvedValue({} as never);
  render(<BackupCloudCopy canManage={false} canRestore />);
  fireEvent.click(await screen.findByText("Restore"));
  expect(await screen.findByText(/About 48 hours to thaw/)).toBeTruthy();
  fireEvent.click(screen.getByText("Thaw and restore"));
  await waitFor(() => expect(restoreCloudCopy).toHaveBeenCalledWith(
    "c1", "tank/b", "sysmanage-offsite-20261125T020000Z", "Bulk", "tank/b-restored"));
});
