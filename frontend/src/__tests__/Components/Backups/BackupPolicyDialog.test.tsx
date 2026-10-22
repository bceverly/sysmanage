// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

// The services to pause are offered from what restate found on the host
// (2.1+), and saved as the policy's quiesce_with.

import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { vi, describe, test, expect, beforeEach } from "vitest";

vi.mock("react-i18next", async () => {
  const { t } = await import("../TimeSync/_i18nMock");
  return { useTranslation: () => ({ t, i18n: { language: "en" } }) };
});
vi.mock("../../../Services/backups", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../../Services/backups")>();
  return { ...actual, savePolicy: vi.fn() };
});

import { savePolicy } from "../../../Services/backups";
import type { BackupPolicy } from "../../../Services/backups";
import BackupPolicyDialog from "../../../Components/Backups/BackupPolicyDialog";

const policy = (over: Partial<BackupPolicy> = {}): BackupPolicy => ({
  id: "p1", host_id: "h1", enabled: true, interval_hours: 24, window_start_hour: null,
  keep_last: 14, check_interval_days: 7, quiesce: true, quiesce_with: ["lxd"],
  available_hooks: ["docker", "libvirt", "lxd"], keep_paths: [], skip_paths: [],
  estimate_bytes: null, repository_bytes: null, configured: true,
  storage_configured: true, restate_version: "2.1.0.1", storage_restate_version: "2.1.0.1",
  ...over,
});

const open = (p: BackupPolicy) =>
  render(<BackupPolicyDialog open hostId="h1" fqdn="t14" policy={p} onClose={vi.fn()} onSaved={vi.fn()} />);

describe("BackupPolicyDialog services to pause", () => {
  beforeEach(() => vi.clearAllMocks());

  test("names what restate found on the host and keeps the current choice", () => {
    open(policy());
    expect(screen.getByText("Found on this host: docker, libvirt, lxd")).toBeInTheDocument();
    expect(screen.getByText("lxd")).toBeInTheDocument();
  });

  test("falls back to an example when the host reported none", () => {
    open(policy({ available_hooks: null, quiesce_with: [] }));
    expect(screen.getByText("For example: postgres, nextcloud")).toBeInTheDocument();
  });

  test("saves the chosen services as quiesce_with", async () => {
    vi.mocked(savePolicy).mockResolvedValue({} as never);
    open(policy());
    fireEvent.click(screen.getByText("Save"));
    await waitFor(() => expect(savePolicy).toHaveBeenCalled());
    expect(vi.mocked(savePolicy).mock.calls[0][1].quiesce_with).toEqual(["lxd"]);
  });
});
