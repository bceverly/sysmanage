// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

// Package-level restore (Pro+ 24.6): plan first, in place only, its own
// confirmation, and the script's summary shown before the real run.  The
// drift timeline (Pro+ 24.7): packages and files per pair, expected churn
// counted, and the "show everything" switch.

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { vi, describe, test, expect, beforeEach } from "vitest";

vi.mock("react-i18next", async () => {
  const { t } = await import("../TimeSync/_i18nMock");
  return { useTranslation: () => ({ t, i18n: { language: "en" } }) };
});
vi.mock("../../../Services/backups", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../../Services/backups")>();
  return {
    ...actual, getSnapshots: vi.fn(), restoreFiles: vi.fn(), getRun: vi.fn(),
    getDriftTimeline: vi.fn(), computeDrift: vi.fn(), setDriftIgnore: vi.fn(),
  };
});
vi.mock("../../../Services/permissions", () => ({
  hasPermission: vi.fn().mockResolvedValue(true),
  SecurityRoles: { MANAGE_BACKUPS: "Manage Backups" },
}));

import {
  computeDrift, getDriftTimeline, getSnapshots, restoreFiles, setDriftIgnore,
} from "../../../Services/backups";
import type { BackupRun, DriftTimeline } from "../../../Services/backups";
import RestoreFilesDialog from "../../../Components/Backups/RestoreFilesDialog";
import BackupDriftTimeline from "../../../Components/Backups/BackupDriftTimeline";

const button = (name: string | RegExp) => screen.getByRole("button", { name });

const PLAN = {
  id: "p1", status: "ok", action: "restore",
  result: { restore: { files: 1, bytes: 65, plan: ["/etc/proof"] },
            packages: { script: "#!/bin/sh\napt-get autoremove -y\n" } },
  package_summary: {
    lines: 2, apt: ["jq=1.8.1-1", "curl=8.18.0-1"], apt_count: 2, manual_count: 2,
    auto_count: 10, removes_unlisted: true, snaps: ["lxd"], flatpaks: [],
    repository_keys: 1, truncated: false,
  },
} as unknown as BackupRun;

describe("package restore", () => {
  beforeEach(() => {
    vi.mocked(getSnapshots).mockResolvedValue([
      { id: "s1", name: "20261102T181741Z", created_at: null, bytes: 1, new_bytes: null,
        unique_bytes: null, files: 1, signed: true, gone_at: null },
    ]);
    vi.mocked(restoreFiles).mockReset();
  });

  test("is offered only where it can run", async () => {
    render(<RestoreFilesDialog open hostId="h1" fqdn="t14" onClose={vi.fn()} />);
    await waitFor(() => expect(getSnapshots).toHaveBeenCalled());
    expect(screen.queryByLabelText(/Put the snapshot's packages back first/)).toBeNull();
  });

  test("goes in place, shows the script's summary, and needs its own confirmation", async () => {
    render(<RestoreFilesDialog open hostId="h1" fqdn="t14" canPackages onClose={vi.fn()} />);
    await waitFor(() => expect(getSnapshots).toHaveBeenCalled());
    fireEvent.click(screen.getByLabelText(/Put the snapshot's packages back first/));
    fireEvent.change(screen.getByLabelText(/Paths to put back/), { target: { value: "/etc/proof" } });
    vi.mocked(restoreFiles).mockResolvedValue(PLAN);
    fireEvent.click(button("Preview"));
    await waitFor(() => expect(restoreFiles).toHaveBeenCalledTimes(1));
    expect(vi.mocked(restoreFiles).mock.calls[0][1]).toMatchObject({
      dry_run: true, in_place: true, packages: true, acknowledge_packages: false,
    });
    expect(await screen.findByText(/apt packages installed by hand: 2/)).toBeInTheDocument();
    expect(screen.getByText(/removed by apt/)).toBeInTheDocument();
    fireEvent.click(screen.getByLabelText(/Replace the files at these paths/));
    expect(button("Restore into place")).toBeDisabled();
    fireEvent.click(screen.getByLabelText(/remove the packages the snapshot did not have/));
    expect(button("Restore into place")).toBeEnabled();
    vi.mocked(restoreFiles).mockResolvedValue({ ...PLAN, id: "r1" } as BackupRun);
    fireEvent.click(button("Restore into place"));
    await waitFor(() => expect(restoreFiles).toHaveBeenCalledTimes(2));
    expect(vi.mocked(restoreFiles).mock.calls[1][1]).toMatchObject({
      dry_run: false, in_place: true, packages: true, acknowledge_packages: true,
    });
  });
});

const TIMELINE: DriftTimeline = {
  entries: [{
    from: "20261102T171033Z", to: "20261102T181741Z", status: "ok", message: null,
    computed_at: null, added: 1, deleted: 0, modified: 2, packages_changed: 1,
    truncated: false, packages_truncated: false, hidden: 3,
    changes: [{ change: "M", path: "/etc/sysmanage-proof/restore-test.conf", what: "content" }],
    packages: [{ change: "U", manager: "apt", name: "jq", from: "1.7", to: "1.8" }],
  }],
  hide_expected: true, expected: ["/var/log"], path: null, ignore: ["/srv/x"],
  missing: [{ from: "20261102T181741Z", to: "20261102T190000Z" }], running: false,
};

describe("drift timeline", () => {
  beforeEach(() => {
    vi.mocked(getDriftTimeline).mockResolvedValue(TIMELINE);
    vi.mocked(computeDrift).mockResolvedValue({ id: "d1" } as BackupRun);
    vi.mocked(setDriftIgnore).mockResolvedValue({ ignore: ["/srv/x"] });
  });

  test("shows packages and files and counts the hidden churn", async () => {
    render(<BackupDriftTimeline hostId="h1" />);
    expect(await screen.findByText(/Hidden as expected churn: 3/)).toBeInTheDocument();
    fireEvent.click(screen.getByText(/20261102T171033Z -> 20261102T181741Z/));
    expect(screen.getByText(/upgraded: jq 1.7 -> 1.8 \(apt\)/)).toBeInTheDocument();
    expect(screen.getByText(/modified: \/etc\/sysmanage-proof\/restore-test.conf/)).toBeInTheDocument();
    expect(getDriftTimeline).toHaveBeenLastCalledWith("h1", true, null);
  });

  test("shows everything on request and compares a missed pair", async () => {
    render(<BackupDriftTimeline hostId="h1" />);
    await screen.findByText(/Hidden as expected churn/);
    fireEvent.click(screen.getByLabelText(/Show everything/));
    await waitFor(() => expect(getDriftTimeline).toHaveBeenLastCalledWith("h1", false, null));
    fireEvent.click(await screen.findByRole("button", { name: /Compare the newest backups/ }));
    await waitFor(() =>
      expect(computeDrift).toHaveBeenCalledWith("h1", "20261102T181741Z", "20261102T190000Z"));
  });

  test("saves the host's own patterns", async () => {
    render(<BackupDriftTimeline hostId="h1" />);
    const box = await screen.findByLabelText(/Also hide on this host/);
    fireEvent.change(box, { target: { value: "/srv/x\n/srv/y" } });
    fireEvent.click(button("Save"));
    await waitFor(() => expect(setDriftIgnore).toHaveBeenCalledWith("h1", ["/srv/x", "/srv/y"]));
  });
});
