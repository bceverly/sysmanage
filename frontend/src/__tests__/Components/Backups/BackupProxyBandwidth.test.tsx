// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

// Bandwidth by the hour through restate-proxy (ROADMAP 25.7, Professional+):
// shown only for a proxy target, edited by a manager with the license,
// and said plainly when not applied (no license, or a storage host whose
// restate is too old).

import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { vi, beforeEach, describe, test, expect } from "vitest";

vi.mock("react-i18next", async () => {
  const { t } = await import("../TimeSync/_i18nMock");
  return { useTranslation: () => ({ t, i18n: { language: "en" } }) };
});
vi.mock("../../../Services/backups", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../../Services/backups")>();
  return { ...actual, setProxyBandwidth: vi.fn() };
});

import { setProxyBandwidth } from "../../../Services/backups";
import type { BackupTarget, ProxyBandwidth } from "../../../Services/backups";
import BackupProxyBandwidth, { toForm, toRules } from "../../../Components/Backups/BackupProxyBandwidth";

const target = (bandwidth?: ProxyBandwidth, transport: "nfs" | "proxy" = "proxy"): BackupTarget => ({
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
  transport: { transport },
  proxy_bandwidth: bandwidth,
});

describe("BackupProxyBandwidth", () => {
  beforeEach(() => vi.clearAllMocks());

  test("rules go to the form and back as restate-proxy's lines", () => {
    const form = toForm(["08-18 2MiB/s", "22-06 512KiB/s", "20MiB/s"]);
    expect(form.rest).toBe("20MiB/s");
    expect(form.rows).toEqual([
      { from: "08", to: "18", rate: "2MiB/s" },
      { from: "22", to: "06", rate: "512KiB/s" },
    ]);
    expect(toRules(form.rows, form.rest)).toEqual(["08-18 2MiB/s", "22-06 512KiB/s", "20MiB/s"]);
    expect(toRules([{ from: "08", to: "18", rate: " " }], "")).toEqual([]);
  });

  test("nothing is shown for an NFS target", () => {
    const { container } = render(
      <BackupProxyBandwidth target={target(undefined, "nfs")} canManage onChanged={vi.fn()} />);
    expect(container.textContent).toBe("");
  });

  test("without the license it says so and offers no editing", () => {
    render(<BackupProxyBandwidth target={target({ rules: [], licensed: false, applied: false })}
      canManage onChanged={vi.fn()} />);
    expect(screen.getByText(/Professional\+ feature/)).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Change" })).toBeNull();
  });

  test("kept rules a lapsed license no longer applies can still be removed", () => {
    render(<BackupProxyBandwidth
      target={target({ rules: ["2MiB/s"], licensed: false, applied: false, reason: "unlicensed" })}
      canManage onChanged={vi.fn()} />);
    expect(screen.getByText(/run at full speed/)).toBeTruthy();
    expect(screen.getByRole("button", { name: "Remove every limit" })).toBeTruthy();
  });

  test("a storage host too old for limits is named", () => {
    render(<BackupProxyBandwidth
      target={target({ rules: ["2MiB/s"], licensed: true, applied: false, reason: "storage_too_old" })}
      canManage onChanged={vi.fn()} />);
    expect(screen.getByText(/too old to apply bandwidth limits/)).toBeTruthy();
  });

  test("a manager adds hours and saves them", async () => {
    vi.mocked(setProxyBandwidth).mockResolvedValue(target());
    const onChanged = vi.fn();
    render(<BackupProxyBandwidth target={target({ rules: ["20MiB/s"], licensed: true, applied: true })}
      canManage onChanged={onChanged} />);
    expect(screen.getByText("20MiB/s")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Change" }));
    fireEvent.click(screen.getByRole("button", { name: "Add hours" }));
    fireEvent.change(screen.getByLabelText("Rate"), { target: { value: "2MiB/s" } });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(setProxyBandwidth).toHaveBeenCalledWith("t1", ["08-18 2MiB/s", "20MiB/s"]));
    expect(onChanged).toHaveBeenCalled();
  });
});
