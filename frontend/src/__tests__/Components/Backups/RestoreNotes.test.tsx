// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

// A restore's unmatched paths, symlinks followed and hooks (restate after
// 2.2.0.14), in the dialog and the job list.

import { render, screen } from "@testing-library/react";
import { vi, describe, test, expect } from "vitest";

vi.mock("react-i18next", async () => {
  const { t } = await import("../TimeSync/_i18nMock");
  return { useTranslation: () => ({ t, i18n: { language: "en" } }) };
});

import { t } from "../TimeSync/_i18nMock";
import type { TFunction } from "i18next";
import type { BackupRun } from "../../../Services/backups";
import { RestoreNotes, restoreNotes } from "../../../Components/Backups/RestoreNotes";

const run = (restore: Record<string, unknown>, status = "ok") =>
  ({ id: "r", action: "restore", status, result: { restore } } as unknown as BackupRun);
const notes = (r: BackupRun) => restoreNotes(t as unknown as TFunction, r);
const hook = (status: string) => ({
  dump_dir: "/var/lib/restate/dumps/nextcloud-nextcloud", kind: "nextcloud", name: "nextcloud", status,
});

describe("restoreNotes", () => {
  test("an older restate reports none of it, and nothing is said", () => {
    expect(notes(run({ files: 3 }))).toEqual([]);
    expect(notes({ id: "x", status: "ok", result: null } as unknown as BackupRun)).toEqual([]);
  });

  test("each hook status says how it went; failures are warnings, first", () => {
    const all = notes(run({ hooks: ["junk", hook("ran"), hook("unknown"), hook("failed"),
      hook("no_hook"), { dump_dir: "/d/x", status: "unreadable" }, hook("odd")] }, "incomplete"));
    expect(all.map(n => n.warning)).toEqual([true, true, true, false, false]);
    expect(all[0].text).toBe(
      "The nextcloud hook failed after the restore, so the restore is incomplete. The restate log on the host says why.");
    expect(all[1].text).toMatch(/^This host has no nextcloud hook/);
    expect(all[2].text).toBe("restate could not tell which hook /d/x is for, so no hook was run.");
    expect(all[3].text).toBe("The nextcloud hook put right what pausing it left in the restored files.");
    expect(all[4].text).toBe("The nextcloud hook had nothing to put right.");
  });

  test("a hook's kind and a different name are both named", () => {
    const [note] = notes(run({ hooks: [{ ...hook("ran"), kind: "postgresql", name: "18-main" }] }));
    expect(note.text).toMatch(/^The postgresql 18-main hook/);
  });

  test("a preview reads no marker: the dump directory names the service", () => {
    const named = (dir: string) => notes(run({ hooks: [{ dump_dir: dir, status: "would_run" }] }))[0].text;
    expect(named("/var/lib/restate/dumps/nextcloud-nextcloud")).toMatch(/run the nextcloud hook to/);
    expect(named("/var/lib/restate/dumps/postgresql-18-main")).toMatch(/run the postgresql-18-main hook/);
  });

  test("unmatched paths and symlinks followed", () => {
    const all = notes(run({
      unmatched: ["/a", "/b", 7],
      resolved: [{ include: "/s/current/x", path: "/s/9/x", through: ["/s/current"] }, { include: "/n" }],
    }, "incomplete"));
    expect(all.map(n => n.text)).toEqual([
      "2 of your paths matched nothing in the snapshot: /a, /b",
      "/s/current/x was followed to /s/9/x through the snapshot's symbolic links.",
    ]);
  });

  test("the job list shows only why a restore is incomplete", () => {
    render(<RestoreNotes warningsOnly run={run({ unmatched: ["/a"], hooks: [hook("ran")] }, "incomplete")} />);
    expect(screen.getByText("1 of your paths matched nothing in the snapshot: /a")).toBeInTheDocument();
    expect(screen.queryByText(/put right what pausing/)).not.toBeInTheDocument();
  });
});
