// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

// A host that cannot reach the backup storage is not offered backups, and
// says why; an unknown answer never blocks (Phase 24, 2026-10-30).

import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { vi, describe, test, expect, beforeEach } from "vitest";
import type { TFunction } from "i18next";

vi.mock("react-i18next", async () => {
  const { t } = await import("../TimeSync/_i18nMock");
  return { useTranslation: () => ({ t, i18n: { language: "en" } }) };
});
vi.mock("../../../Services/backups", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../../Services/backups")>();
  return { ...actual, checkBackupReach: vi.fn() };
});

import { t } from "../TimeSync/_i18nMock";
import { checkBackupReach } from "../../../Services/backups";
import type { BackupHost, BackupReach } from "../../../Services/backups";
import StorageReachNote from "../../../Components/Backups/StorageReachNote";
import { canBackUp, canEquip, canSetUp, pickBlocked } from "../../../Components/Backups/BackupHostsTable";
import { reasonLabel } from "../../../Components/Backups/backupLabels";

const NO_PATH: BackupReach = {
  reachable: false, address: "192.168.4.10", port: 2049, storage_fqdn: "nas",
  error: "timeout", checked_at: "2026-10-30T12:00:00",
};
const MESSAGE =
  "This host cannot reach the backup storage (nas, 192.168.4.10, NFS port 2049). Backups need a network path to it.";

const row = (over: Partial<BackupHost>): BackupHost => ({
  host_id: "h1", fqdn: "sysmanage.example", platform: "Linux", platform_release: "Ubuntu 26.04",
  equipped: true, reason: null, coverage: "full", policy: null, status: "no_policy",
  last_capture: null, last_good_capture: null, last_check: null, running: null,
  capture_requested: false, next_due: null, snapshot_count: 0, first_fit: null,
  equip_blocker: "equipped", ...over,
});

describe("storage reach", () => {
  beforeEach(() => vi.clearAllMocks());

  test("an unreachable host can be neither set up, backed up nor equipped, and says why", () => {
    const blocked = row({ reach: NO_PATH });
    expect(canSetUp(blocked)).toBe(false);
    expect(canBackUp(row({ reach: NO_PATH, policy: { configured: true } as BackupHost["policy"] })))
      .toBe(false);
    expect(canEquip(row({ equipped: false, equip_blocker: null, reach: NO_PATH }))).toBe(false);
    expect(pickBlocked(t as unknown as TFunction, blocked)).toBe(MESSAGE);
  });

  test("unknown or reachable never blocks", () => {
    expect(canSetUp(row({ reach: null }))).toBe(true);
    expect(canSetUp(row({ reach: { ...NO_PATH, reachable: true } }))).toBe(true);
  });

  test("the bulk skip reason reads plainly", () => {
    expect(reasonLabel(t as unknown as TFunction, "storage_unreachable"))
      .toBe("Cannot reach the backup storage");
  });

  test("the note says why and Check again asks the agent", async () => {
    vi.mocked(checkBackupReach).mockResolvedValue({ command_id: "c1" });
    render(<StorageReachNote hostId="h1" reach={NO_PATH} canManage onChanged={vi.fn()} />);
    expect(screen.getByText(MESSAGE)).toBeInTheDocument();
    fireEvent.click(screen.getByText("Check again"));
    await waitFor(() => expect(checkBackupReach).toHaveBeenCalledWith("h1"));
    expect(await screen.findByText("Asked the agent; the status updates in a few seconds."))
      .toBeInTheDocument();
  });

  test("nothing is shown when the storage is reachable or not known", () => {
    const { container, rerender } = render(
      <StorageReachNote hostId="h1" reach={null} canManage onChanged={vi.fn()} />);
    expect(container).toBeEmptyDOMElement();
    rerender(<StorageReachNote hostId="h1" reach={{ ...NO_PATH, reachable: true }} canManage
      onChanged={vi.fn()} />);
    expect(container).toBeEmptyDOMElement();
  });

  test("without the role there is no Check again", () => {
    render(<StorageReachNote hostId="h1" reach={NO_PATH} canManage={false} onChanged={vi.fn()} />);
    expect(screen.queryByText("Check again")).toBeNull();
  });
});
