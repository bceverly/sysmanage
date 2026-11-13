// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

// The SysManage server's own backup on the Backups page (ROADMAP 25.9): a
// warning while it has no good backup; Back up this SysManage server shows
// what is kept, left out and never backed up, and saves the server's policy
// with the preset's paths and the databases paused.

import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { vi, describe, test, expect, beforeEach } from "vitest";

vi.mock("react-i18next", async () => {
  const { t } = await import("../TimeSync/_i18nMock");
  return { useTranslation: () => ({ t, i18n: { language: "en" } }) };
});
vi.mock("../../../hooks/useModuleLicensed", () => ({ useModuleLicensed: () => false }));
vi.mock("../../../Services/backups", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../../Services/backups")>();
  return { ...actual, getServerBackup: vi.fn(), saveServerPolicy: vi.fn() };
});

import { getServerBackup, saveServerPolicy } from "../../../Services/backups";
import type { BackupHost, ServerBackup, ServerBackupStatus } from "../../../Services/backups";
import BackupServerCard from "../../../Components/Backups/BackupServerCard";

const PRESET = {
  quiesce: true,
  keep_paths: ["/etc/sysmanage/certs", "/var/lib/openbao"],
  skip_paths: ["/var/lib/sysmanage/modules"],
  never_paths: ["/var/lib/openbao/init.json", "/etc/sysmanage/openbao-token"],
};

const server = (over: Partial<ServerBackupStatus> = {}): ServerBackupStatus => ({
  status: "no_policy", host_id: "h-1", fqdn: "sysmanage.lab", host_status: "no_policy", warn: true,
  ...over,
});

const HOSTS = [
  { host_id: "h-1", fqdn: "sysmanage.lab" },
  { host_id: "h-2", fqdn: "web.lab" },
] as unknown as BackupHost[];

const show = (status: ServerBackupStatus | undefined, canManage = true) =>
  render(<BackupServerCard server={status} hosts={HOSTS} canManage={canManage} onChanged={() => undefined} />);

describe("BackupServerCard", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(getServerBackup).mockResolvedValue({ ...server(), candidates: [], preset: PRESET } as ServerBackup);
    vi.mocked(saveServerPolicy).mockResolvedValue({} as never);
  });

  test("shows nothing once the server is backed up, or when it is not warned on", () => {
    expect(show(server({ status: "ok", warn: false })).container.textContent).toBe("");
  });

  test("a server with no backup is named, and its policy saves the preset paused", async () => {
    show(server());
    expect(screen.getByText(/This SysManage server \(sysmanage\.lab\) is not backed up/)).toBeInTheDocument();
    fireEvent.click(screen.getByText("Back up this SysManage server"));
    expect(await screen.findByText("/var/lib/openbao/init.json")).toBeInTheDocument();
    expect(screen.getByText("Never backed up")).toBeInTheDocument();
    expect(screen.getByText(/This backup is not encrypted/)).toBeInTheDocument();
    fireEvent.click(screen.getByText("Save"));
    await waitFor(() => expect(saveServerPolicy).toHaveBeenCalled());
    const [hostId, input] = vi.mocked(saveServerPolicy).mock.calls[0];
    expect(hostId).toBe("h-1");
    expect(input.quiesce).toBe(true);
    expect(input.keep_paths).toEqual(PRESET.keep_paths);
    expect(input.skip_paths).toEqual(PRESET.skip_paths);
  });

  test("a server backed up as an ordinary host says so and offers the server's policy", () => {
    show(server({ status: "ordinary_policy", host_status: "ok" }));
    expect(screen.getByText(/is backed up as an ordinary host: its database is stopped/)).toBeInTheDocument();
    expect(screen.getByText("Back up this SysManage server")).toBeInTheDocument();
  });

  test("no good backup points at its row and offers no new policy", () => {
    show(server({ status: "no_good_backup", host_status: "failed" }));
    expect(screen.getByText(/has no recent good backup/)).toBeInTheDocument();
    expect(screen.queryByText("Back up this SysManage server")).toBeNull();
  });

  test("an unidentified server asks for its host; a viewer gets the warning only", () => {
    show(server({ status: "unknown", host_id: null, fqdn: null }), false);
    expect(screen.getByText(/cannot tell which host is this server/)).toBeInTheDocument();
    expect(screen.queryByText("Back up this SysManage server")).toBeNull();
  });

  test("Pro+ names the escrow key it encrypts to", async () => {
    vi.mocked(getServerBackup).mockResolvedValue({ ...server(), candidates: [], preset: PRESET,
      encryption: { available: true, escrow_fingerprint: "E".repeat(40), encrypted: false } } as ServerBackup);
    show(server());
    fireEvent.click(screen.getByText("Back up this SysManage server"));
    expect(await screen.findByText(/Encrypted to your break-glass escrow key/)).toBeInTheDocument();
    expect(screen.queryByText(/This backup is not encrypted/)).toBeNull();
  });

  test("Pro+ without an escrow key cannot save", async () => {
    vi.mocked(getServerBackup).mockResolvedValue({ ...server(), candidates: [], preset: PRESET,
      encryption: { available: true, escrow_fingerprint: null, encrypted: false } } as ServerBackup);
    show(server());
    fireEvent.click(screen.getByText("Back up this SysManage server"));
    expect(await screen.findByText(/Save a break-glass escrow key first/)).toBeInTheDocument();
    expect(screen.getByText("Save").closest("button")).toBeDisabled();
  });
});
