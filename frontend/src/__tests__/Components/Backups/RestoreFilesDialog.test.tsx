// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

// Restore files: into staging by default; into place only with specific
// paths, a preview, and its own confirmation.

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { vi, describe, test, expect, beforeEach } from "vitest";

vi.mock("react-i18next", async () => {
  const { t } = await import("../TimeSync/_i18nMock");
  return { useTranslation: () => ({ t, i18n: { language: "en" } }) };
});
vi.mock("../../../Services/backups", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../../Services/backups")>();
  return { ...actual, getSnapshots: vi.fn(), restoreFiles: vi.fn(), getRun: vi.fn() };
});

import { getSnapshots, restoreFiles } from "../../../Services/backups";
import type { BackupRun } from "../../../Services/backups";
import RestoreFilesDialog from "../../../Components/Backups/RestoreFilesDialog";

const done = (id: string) =>
  ({ id, status: "ok", result: { files: 2, bytes: 10 } } as unknown as BackupRun);

beforeEach(() => {
  vi.mocked(getSnapshots).mockResolvedValue([
    { id: "s1", name: "20261025T103120Z", created_at: null, bytes: 1, new_bytes: null,
      unique_bytes: null, files: 1, signed: false, gone_at: null },
  ]);
  vi.mocked(restoreFiles).mockReset();
});

const open = async () => {
  render(<RestoreFilesDialog open hostId="h1" fqdn="t14" onClose={vi.fn()} />);
  await waitFor(() => expect(getSnapshots).toHaveBeenCalled());
  fireEvent.click(screen.getByLabelText("This snapshot is not signed. Restore it anyway."));
};

const button = (name: string) => screen.getByRole("button", { name });

describe("RestoreFilesDialog", () => {
  test("restores to staging by default", async () => {
    await open();
    vi.mocked(restoreFiles).mockResolvedValue(done("p1"));
    fireEvent.click(button("Preview"));
    await waitFor(() => expect(restoreFiles).toHaveBeenCalledTimes(1));
    expect(vi.mocked(restoreFiles).mock.calls[0][1]).toMatchObject({ dry_run: true, in_place: false });
    expect(button("Restore to staging")).toBeEnabled();
  });

  test("a preview that matches nothing says so (restate 2.2 nests the counts)", async () => {
    await open();
    vi.mocked(restoreFiles).mockResolvedValue({
      id: "p2", status: "ok",
      result: { restore: { files: 0, bytes: 0, plan_count: 0, plan: [] } },
    } as unknown as BackupRun);
    fireEvent.click(button("Preview"));
    expect(await screen.findByText(/Nothing in the snapshot matches these paths/)).toBeInTheDocument();
  });

  test("nested counts are shown", async () => {
    await open();
    vi.mocked(restoreFiles).mockResolvedValue({
      id: "p3", status: "ok",
      result: { restore: { files: 3, bytes: 2048, plan_count: 3, plan: ["/etc/a", "/etc/b", "/etc/c"] } },
    } as unknown as BackupRun);
    fireEvent.click(button("Preview"));
    expect(await screen.findByText(/Files: 3/)).toBeInTheDocument();
    expect(screen.getByText(/\/etc\/a/)).toBeInTheDocument();
  });

  test("into place needs paths, a preview and its own confirmation", async () => {
    await open();
    fireEvent.click(screen.getByLabelText("Into place, replacing the host's files"));
    expect(button("Preview")).toBeDisabled(); // no paths yet
    fireEvent.change(screen.getByLabelText("Paths to put back (one per line)"), {
      target: { value: "/etc/nginx" },
    });
    vi.mocked(restoreFiles).mockResolvedValueOnce(done("p1"));
    fireEvent.click(button("Preview"));
    await waitFor(() => expect(restoreFiles).toHaveBeenCalledTimes(1));
    expect(vi.mocked(restoreFiles).mock.calls[0][1]).toMatchObject({
      dry_run: true, in_place: true, include: ["/etc/nginx"], acknowledge_in_place: false,
    });
    await waitFor(() => expect(screen.getByText(/Files: 2/)).toBeInTheDocument());
    expect(button("Restore into place")).toBeDisabled(); // not confirmed
    fireEvent.click(screen.getByLabelText("Replace the files at these paths on t14."));
    vi.mocked(restoreFiles).mockResolvedValueOnce(done("r1"));
    fireEvent.click(button("Restore into place"));
    await waitFor(() => expect(restoreFiles).toHaveBeenCalledTimes(2));
    expect(vi.mocked(restoreFiles).mock.calls[1][1]).toMatchObject({
      dry_run: false, in_place: true, acknowledge_in_place: true,
    });
  });
});
