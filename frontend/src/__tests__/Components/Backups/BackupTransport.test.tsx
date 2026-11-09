// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

// How hosts reach the storage (ROADMAP 25.5): NFS or restate-proxy, shown on
// the target card and changed in its own dialog; a saved CA is kept unless
// the operator removes it.

import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { vi, beforeEach, describe, test, expect } from "vitest";

vi.mock("react-i18next", async () => {
  const { t } = await import("../TimeSync/_i18nMock");
  return { useTranslation: () => ({ t, i18n: { language: "en" } }) };
});
vi.mock("../../../Services/backups", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../../Services/backups")>();
  return { ...actual, setTransport: vi.fn() };
});

import { setTransport } from "../../../Services/backups";
import type { BackupTarget } from "../../../Services/backups";
import BackupTransport from "../../../Components/Backups/BackupTransport";

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

const proxyTarget = (ca = false) =>
  target({
    transport: {
      transport: "proxy", proxy_host: "nas.example.lan", proxy_port: 8443,
      proxy_pin_sha256: null, proxy_ca: ca, url: "https://nas.example.lan:8443",
    },
  });

describe("BackupTransport", () => {
  beforeEach(() => vi.clearAllMocks());

  test("an NFS target says so, and only a manager can change it", () => {
    const { rerender } = render(<BackupTransport target={target()} canManage={false} onChanged={vi.fn()} />);
    expect(screen.getByText(/How hosts reach the storage/).textContent).toContain("NFS");
    expect(screen.queryByRole("button", { name: "Change" })).toBeNull();
    rerender(<BackupTransport target={target()} canManage onChanged={vi.fn()} />);
    expect(screen.getByRole("button", { name: "Change" })).toBeTruthy();
  });

  test("a proxy target shows where hosts reach it", () => {
    render(<BackupTransport target={proxyTarget()} canManage={false} onChanged={vi.fn()} />);
    expect(screen.getByText("https://nas.example.lan:8443")).toBeTruthy();
  });

  test("saving the proxy sends its address and keeps a saved CA", async () => {
    vi.mocked(setTransport).mockResolvedValue(proxyTarget(true));
    const changed = vi.fn();
    render(<BackupTransport target={proxyTarget(true)} canManage onChanged={changed} />);
    fireEvent.click(screen.getByRole("button", { name: "Change" }));
    fireEvent.change(screen.getByLabelText("Port"), { target: { value: "9443" } });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(changed).toHaveBeenCalled());
    expect(setTransport).toHaveBeenCalledWith("t1", {
      transport: "proxy", proxy_host: "nas.example.lan", proxy_port: 9443,
      proxy_pin_sha256: null, proxy_ca_pem: null, remove_proxy_ca: false,
    });
  });

  test("a saved CA is removed only when asked", async () => {
    vi.mocked(setTransport).mockResolvedValue(proxyTarget());
    render(<BackupTransport target={proxyTarget(true)} canManage onChanged={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: "Change" }));
    fireEvent.click(screen.getByLabelText("Remove the saved CA and trust the system store"));
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(setTransport).toHaveBeenCalled());
    expect(vi.mocked(setTransport).mock.calls[0][1].remove_proxy_ca).toBe(true);
  });

  test("a refusal is shown in the dialog", async () => {
    vi.mocked(setTransport).mockRejectedValue({ response: { data: { detail: "The proxy port must be between 1 and 65535" } } });
    render(<BackupTransport target={proxyTarget()} canManage onChanged={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: "Change" }));
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(await screen.findByText("The proxy port must be between 1 and 65535")).toBeTruthy();
  });
});
