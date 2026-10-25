// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

// What changed since the last backup: the check is started, polled, and its
// counts and first changes shown.

import { render, screen } from "@testing-library/react";
import { vi, describe, test, expect } from "vitest";

vi.mock("react-i18next", async () => {
  const { t } = await import("../TimeSync/_i18nMock");
  return { useTranslation: () => ({ t, i18n: { language: "en" } }) };
});
vi.mock("../../../Services/backups", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../../Services/backups")>();
  return { ...actual, backupChanges: vi.fn(), getRun: vi.fn() };
});

import { backupChanges, getRun } from "../../../Services/backups";
import type { BackupRun } from "../../../Services/backups";
import BackupChangesDialog from "../../../Components/Backups/BackupChangesDialog";

describe("BackupChangesDialog", () => {
  test("shows the counts and each change", async () => {
    vi.mocked(backupChanges).mockResolvedValue({ id: "r1", status: "queued" } as unknown as BackupRun);
    vi.mocked(getRun).mockResolvedValue({
      id: "r1", status: "different",
      result: { diff: { added: 1, deleted: 0, modified: 1, truncated: false, changes: [
        { change: "A", path: "/etc/new.conf", what: "" },
        { change: "M", path: "/etc/hosts", what: "content" },
      ] } },
    } as unknown as BackupRun);
    render(<BackupChangesDialog hostId="h1" fqdn="t14" onClose={vi.fn()} />);
    expect(await screen.findByText("Added: 1, deleted: 0, modified: 1")).toBeInTheDocument();
    expect(screen.getByText("/etc/hosts")).toBeInTheDocument();
    expect(screen.getByText("content")).toBeInTheDocument();
    expect(screen.getByText("Modified")).toBeInTheDocument();
  });

  test("a snapshot from before restate 2.2.0.2 is called out", async () => {
    vi.mocked(backupChanges).mockResolvedValue({ id: "r2", status: "queued" } as unknown as BackupRun);
    vi.mocked(getRun).mockResolvedValue({
      id: "r2", status: "different",
      result: { capture_rules: false, diff: { added: 1, deleted: 0, modified: 0, changes: [
        { change: "A", path: "/home/u/Nextcloud/a.txt" },
      ] } },
    } as unknown as BackupRun);
    render(<BackupChangesDialog hostId="h1" fqdn="t14" onClose={vi.fn()} />);
    expect(await screen.findByText(/taken before restate 2.2.0.2/)).toBeInTheDocument();
  });

  test("no note when restate used the capture's rules", async () => {
    vi.mocked(backupChanges).mockResolvedValue({ id: "r3", status: "queued" } as unknown as BackupRun);
    vi.mocked(getRun).mockResolvedValue({
      id: "r3", status: "ok",
      result: { capture_rules: true, diff: { added: 0, deleted: 0, modified: 0, changes: [] } },
    } as unknown as BackupRun);
    render(<BackupChangesDialog hostId="h1" fqdn="t14" onClose={vi.fn()} />);
    expect(await screen.findByText("Added: 0, deleted: 0, modified: 0")).toBeInTheDocument();
    expect(screen.queryByText(/taken before restate 2.2.0.2/)).not.toBeInTheDocument();
  });

  test("a refusal is shown", async () => {
    vi.mocked(backupChanges).mockRejectedValue({ response: { data: { detail: "This host's restate cannot do this yet; upgrade restate" } } });
    render(<BackupChangesDialog hostId="h1" fqdn="t14" onClose={vi.fn()} />);
    expect(await screen.findByText(/upgrade restate/)).toBeInTheDocument();
  });
});
