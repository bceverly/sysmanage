// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

// Cloud backup (24.12): one "Enable iCloud backup" button on the storage
// host, "Needs sign-in" said plainly, the two-factor code relayed, the
// password sent once and never shown, and nothing at all when air-gapped.

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { vi, describe, test, expect, beforeEach } from "vitest";

vi.mock("react-i18next", async () => {
  const { t } = await import("../TimeSync/_i18nMock");
  return { useTranslation: () => ({ t, i18n: { language: "en" } }) };
});
vi.mock("../../../Services/permissions", () => ({
  hasPermission: vi.fn(() => Promise.resolve(true)),
  SecurityRoles: { MANAGE_CLOUD_BACKUPS: "Manage Cloud Backups" },
}));
vi.mock("../../../Services/cloudBackup", () => ({
  getCloudOverview: vi.fn(),
  enableCloudBackup: vi.fn(),
  createCloudAccount: vi.fn(),
  updateCloudAccount: vi.fn(),
  deleteCloudAccount: vi.fn(),
  connectCloudAccount: vi.fn(),
  listCloudLibraries: vi.fn(),
  runCloudAccountNow: vi.fn(),
  sendCloudCode: vi.fn(),
}));

import {
  createCloudAccount, enableCloudBackup, getCloudOverview, sendCloudCode,
} from "../../../Services/cloudBackup";
import CloudBackupSection from "../../../Components/CloudBackup/CloudBackupSection";
import { attentionCount, dashboardNote } from "../../../Components/CloudBackup/cloudBackupLabels";

const RUN = {
  id: "r1", account_id: "a1", action: "connect", status: "waiting_code", queued_at: null,
  started_at: null, finished_at: null, requested_by: null, progress: { phase: "waiting_code" },
  message: null, reason: null, detail: null, duration: null, exit_code: null, downloaded: null,
  present: null, failed: null, bytes: null, waiting_code: true,
};
const ACCOUNT = {
  id: "a1", provider: "icloud", apple_id: "family@example.com", display_name: "Family",
  library: "PrimarySync", libraries: [], password_set: true, password_set_at: null,
  dir_name: "icloud-0000abcd", enabled: true, interval_hours: 24, window_start_hour: null,
  until_found: 50, status: "needs_sign_in",
  state_message: "Apple did not accept", session_created_at: null, session_expires_at: null,
  session_expiring: false, last_good_at: null, last_full_at: null, photos_local: null,
  bytes_local: null, run_requested: false, retry_at: null, current_run: null,
  last_run: { ...RUN, action: "download", status: "needs_sign_in", reason: "auth_failed", waiting_code: false },
  created_at: null,
};
const OVERVIEW = {
  available: true, target: { id: "t", name: "nas", storage_path: "/srv/backups" },
  storage_host: { id: "h", fqdn: "nas.lab" }, support: { supported: true, reason: null },
  enable: null, enabled: false, accounts: [],
};

describe("CloudBackupSection", () => {
  beforeEach(() => vi.clearAllMocks());

  test("offers one Enable button that names the storage host", async () => {
    vi.mocked(getCloudOverview).mockResolvedValue(OVERVIEW as never);
    vi.mocked(enableCloudBackup).mockResolvedValue(OVERVIEW as never);
    render(<CloudBackupSection onError={vi.fn()} />);
    expect(await screen.findByText(/Runs on your backup storage host, nas.lab/)).toBeInTheDocument();
    fireEvent.click(screen.getByTestId("cloud-enable"));
    await waitFor(() => expect(enableCloudBackup).toHaveBeenCalledTimes(1));
    expect(screen.queryByTestId("cloud-add")).toBeNull();  // accounts come after Enable
  });

  test("shows Needs sign-in with the reason, never as no new photos", async () => {
    vi.mocked(getCloudOverview).mockResolvedValue({ ...OVERVIEW, enabled: true, accounts: [ACCOUNT] } as never);
    render(<CloudBackupSection onError={vi.fn()} />);
    expect(await screen.findByText("Needs sign-in")).toBeInTheDocument();
    expect(screen.getByText(/Apple did not accept the sign-in/)).toBeInTheDocument();
  });

  test("relays the two-factor code for a waiting sign-in", async () => {
    const waiting = { ...ACCOUNT, status: "waiting_code", current_run: RUN };
    vi.mocked(getCloudOverview).mockResolvedValue({ ...OVERVIEW, enabled: true, accounts: [waiting] } as never);
    vi.mocked(sendCloudCode).mockResolvedValue(RUN as never);
    render(<CloudBackupSection onError={vi.fn()} />);
    fireEvent.click(await screen.findByTestId("cloud-enter-code"));
    fireEvent.change(screen.getByTestId("cloud-code"), { target: { value: "123 456" } });
    fireEvent.click(screen.getByText("Send code"));
    await waitFor(() => expect(sendCloudCode).toHaveBeenCalledWith("r1", "123456"));
  });

  test("says what List libraries found", async () => {
    const listed = (libraries: string[]) => ({
      ...ACCOUNT, status: "ok", session_created_at: "2026-11-04T19:43:52Z", libraries,
      last_run: { ...RUN, action: "libraries", status: "ok", waiting_code: false },
    });
    vi.mocked(getCloudOverview).mockResolvedValue(
      { ...OVERVIEW, enabled: true, accounts: [listed(["PrimarySync"])] } as never);
    const { unmount } = render(<CloudBackupSection onError={vi.fn()} />);
    expect(await screen.findByText(/Only the personal library was found/)).toBeInTheDocument();
    unmount();
    vi.mocked(getCloudOverview).mockResolvedValue(
      { ...OVERVIEW, enabled: true, accounts: [listed(["PrimarySync", "SharedSync-AB12"])] } as never);
    render(<CloudBackupSection onError={vi.fn()} />);
    expect(await screen.findByText(/Libraries found: PrimarySync, SharedSync-AB12/)).toBeInTheDocument();
  });

  test("says when it tries again after Apple refuses, not that it failed", async () => {
    vi.mocked(getCloudOverview).mockResolvedValue({
      ...OVERVIEW, enabled: true, accounts: [{
        ...ACCOUNT, status: "cooling_down", session_created_at: "2026-11-04T19:43:52Z",
        retry_at: "2026-11-04T23:08:32",
        last_run: { ...RUN, action: "reconcile", status: "failed", reason: "apple_busy", waiting_code: false },
      }],
    } as never);
    render(<CloudBackupSection onError={vi.fn()} />);
    expect(await screen.findByText("Waiting for Apple")).toBeInTheDocument();
    expect(screen.getByText(/Apple is limiting downloads for this account/)).toBeInTheDocument();
    expect(screen.queryByText(/stopped trying/)).not.toBeInTheDocument();
  });

  test("sends the password once with a new account", async () => {
    vi.mocked(getCloudOverview).mockResolvedValue({ ...OVERVIEW, enabled: true } as never);
    vi.mocked(createCloudAccount).mockResolvedValue(ACCOUNT as never);
    render(<CloudBackupSection onError={vi.fn()} />);
    fireEvent.click(await screen.findByTestId("cloud-add"));
    fireEvent.change(screen.getByTestId("cloud-apple-id"), { target: { value: "a@example.com" } });
    fireEvent.change(screen.getByTestId("cloud-name"), { target: { value: "Mine" } });
    fireEvent.change(screen.getByTestId("cloud-password"), { target: { value: "secret-pw" } });
    fireEvent.click(screen.getByText("Save"));
    await waitFor(() => expect(createCloudAccount).toHaveBeenCalledTimes(1));
    const body = vi.mocked(createCloudAccount).mock.calls[0][0];
    expect(body.password).toBe("secret-pw");
    expect(body).not.toHaveProperty("auto_delete");  // one-way: no deletion setting
  });

  test("renders nothing on an air-gapped server", async () => {
    vi.mocked(getCloudOverview).mockResolvedValue({ available: false, reason: "airgapped", accounts: [] } as never);
    const { container } = render(<CloudBackupSection onError={vi.fn()} />);
    await waitFor(() => expect(getCloudOverview).toHaveBeenCalled());
    expect(container).toBeEmptyDOMElement();
  });

  test("the dashboard counts accounts needing sign-in", () => {
    const t = ((_k: string, d: string, o?: Record<string, unknown>) =>
      d.replace("{{n}}", String(o?.n ?? ""))) as never;
    const summary = { enabled: true, accounts: 2, ok: 0, running: 0, needs_sign_in: 1, failed: 1, expiring: 0 };
    expect(attentionCount(summary)).toBe(2);
    expect(dashboardNote(t, summary)).toBe("iCloud accounts that need sign-in: 1");
    expect(attentionCount({ ...summary, enabled: false })).toBe(0);
  });
});
