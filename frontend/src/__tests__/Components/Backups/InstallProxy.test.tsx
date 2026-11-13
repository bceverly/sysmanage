// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

// restate-proxy missing on the storage host: the target card offers to
// install it through Equip (ROADMAP 25.5).

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { vi, describe, test, expect, beforeEach } from "vitest";

vi.mock("react-i18next", async () => {
  const { t } = await import("../TimeSync/_i18nMock");
  return { useTranslation: () => ({ t, i18n: { language: "en" } }) };
});

const equipBackup = vi.fn();
vi.mock("../../../Services/backups", () => ({
  equipBackup: (id: string) => equipBackup(id),
}));

import BackupStorageStatus from "../../../Components/Backups/BackupStorageStatus";
import type { BackupTarget } from "../../../Services/backups";

const target = (problem: string) =>
  ({
    storage_host_id: "nas-1",
    storage_status: null,
    storage_fs: { type: null, mount_point: null },
    warnings: ["audit_proxy_running"],
    storage_audit: { proxy_running: { level: "error", hosts: [], params: { problem } } },
  }) as unknown as BackupTarget;

describe("Install restate-proxy", () => {
  beforeEach(() => equipBackup.mockReset().mockResolvedValue({ command_id: "c", equip: null }));

  test("offered when it is not installed, and asks the storage host's agent", async () => {
    render(<BackupStorageStatus target={target("not_installed")} hosts={[]} canManage />);
    fireEvent.click(screen.getByTestId("backup-install-proxy"));
    await waitFor(() => expect(equipBackup).toHaveBeenCalledWith("nas-1"));
    expect(await screen.findByText(/Installing restate-proxy on the storage host/)).toBeInTheDocument();
  });

  test("not offered when it is only stopped, or to a viewer", () => {
    const { rerender } = render(<BackupStorageStatus target={target("stopped")} hosts={[]} canManage />);
    expect(screen.queryByTestId("backup-install-proxy")).toBeNull();
    rerender(<BackupStorageStatus target={target("not_installed")} hosts={[]} />);
    expect(screen.queryByTestId("backup-install-proxy")).toBeNull();
  });
});
