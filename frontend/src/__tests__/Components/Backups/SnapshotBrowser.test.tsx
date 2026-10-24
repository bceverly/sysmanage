// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

// Browsing a snapshot: each folder is a listing run polled to the end;
// folders open, files and folders are added to the restore list, a name that
// is not valid text cannot be picked, and a truncated folder says so.

import { render, screen, fireEvent } from "@testing-library/react";
import { vi, describe, test, expect, beforeEach } from "vitest";

vi.mock("react-i18next", async () => {
  const { t } = await import("../TimeSync/_i18nMock");
  return { useTranslation: () => ({ t, i18n: { language: "en" } }) };
});
vi.mock("../../../Services/backups", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../../Services/backups")>();
  return { ...actual, browseSnapshot: vi.fn(), getRun: vi.fn() };
});

import { browseSnapshot, getRun } from "../../../Services/backups";
import type { BackupRun } from "../../../Services/backups";
import SnapshotBrowser from "../../../Components/Backups/SnapshotBrowser";

const listing = (path: string, entries: object[], truncated = false): BackupRun =>
  ({ id: `run-${path}`, action: "list", status: "ok", result: { list: { path, entries, truncated } } }) as unknown as BackupRun;

describe("SnapshotBrowser", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(browseSnapshot).mockImplementation(async (_h, _s, path) =>
      ({ id: `run-${path}`, status: "queued" }) as unknown as BackupRun);
    vi.mocked(getRun).mockImplementation(async (id) => {
      if (id === "run-/") {
        return listing("/", [
          { name: "etc", type: "dir" },
          { name: "notes.txt", type: "file", size: 120 },
          { name: "bad", type: "file", name_base64: "/w==" },
        ], true);
      }
      return listing("/etc", [{ name: "hosts", type: "file", size: 40 }]);
    });
  });

  test("opens folders and adds paths to the restore list", async () => {
    const onPick = vi.fn();
    render(<SnapshotBrowser hostId="h1" snapshot="s1" picked={[]} onPick={onPick} />);
    expect(await screen.findByText("etc/")).toBeInTheDocument();
    expect(screen.getByText(/more entries than can be shown/)).toBeInTheDocument();
    const badRow = screen.getByText("bad").closest("tr") as HTMLElement;
    expect(badRow.querySelector("button")).toBeDisabled(); // "bad" is not valid text
    fireEvent.click(screen.getByText("etc/"));
    expect(await screen.findByText("hosts")).toBeInTheDocument();
    expect(browseSnapshot).toHaveBeenLastCalledWith("h1", "s1", "/etc");
    fireEvent.click(screen.getByText("Add"));
    expect(onPick).toHaveBeenCalledWith("/etc/hosts");
  });

  test("a path already picked shows as added", async () => {
    render(<SnapshotBrowser hostId="h1" snapshot="s1" picked={["/notes.txt"]} onPick={vi.fn()} />);
    expect(await screen.findByText("Added")).toBeInTheDocument();
  });

  test("a failed listing says so", async () => {
    vi.mocked(getRun).mockResolvedValue({ id: "run-/", status: "failed", message: "not in the snapshot",
      result: {} } as unknown as BackupRun);
    render(<SnapshotBrowser hostId="h1" snapshot="s1" picked={[]} onPick={vi.fn()} />);
    expect(await screen.findByText("not in the snapshot")).toBeInTheDocument();
  });
});
