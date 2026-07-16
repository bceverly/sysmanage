// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

import { render, screen, fireEvent, waitFor, within } from "@testing-library/react";
import { vi, beforeEach, afterEach, test, expect } from "vitest";

// MUI emits a benign `anchorEl` console.error under jsdom when a Select
// popover opens (no real layout); silence it without hiding real errors.
let errSpy: ReturnType<typeof vi.spyOn>;

vi.mock("react-i18next", () => {
  const t = (key: string, fallback?: string, opts?: Record<string, unknown>) => {
    let s = fallback || key;
    if (opts) {
      for (const [k, v] of Object.entries(opts)) {
        s = s.replace(new RegExp(`{{${k}}}`, "g"), String(v));
      }
    }
    return s;
  };
  return { useTranslation: () => ({ t, i18n: { language: "en" } }) };
});

// axiosInstance.get('/api/v1/hosts') is the only direct axios call the
// component makes; everything else routes through the service module.
vi.mock("../../Services/api", () => ({
  default: { get: vi.fn(), post: vi.fn(), put: vi.fn(), delete: vi.fn() },
}));

vi.mock("../../Services/repositoryMirroring", () => ({
  listPlatformConfigs: vi.fn(),
  listMirrors: vi.fn(),
  listKnownVersions: vi.fn(),
  listSnapshots: vi.fn(),
  createMirror: vi.fn(),
  updateMirror: vi.fn(),
  deleteMirror: vi.fn(),
  createPlatformConfig: vi.fn(),
  updatePlatformConfig: vi.fn(),
  deletePlatformConfig: vi.fn(),
  syncMirror: vi.fn(),
  snapshotMirror: vi.fn(),
  restoreMirror: vi.fn(),
  // Consumed by the MirrorSetupStatusCard child.
  getMirrorSetupStatus: vi.fn(),
  refreshMirrorSetupStatus: vi.fn(),
  installMirrorTools: vi.fn(),
}));

import axiosInstance from "../../Services/api";
import * as svc from "../../Services/repositoryMirroring";
import RepositoryMirroringSettings from "../../Components/RepositoryMirroringSettings";

const m = (fn: unknown) => fn as unknown as ReturnType<typeof vi.fn>;

const HOST = {
  id: "h1",
  fqdn: "mirror01.example.com",
  platform: "linux",
  platform_release: "Ubuntu 24.04",
};

const READY_STATUS = {
  host_id: "h1",
  tools: { "apt-mirror": "present", trickle: "present", rsync: "present", curl: "present" },
  platform: "linux",
  distro: "ubuntu",
  last_check_at: "2026-01-01T00:00:00Z",
  last_check_message_id: null,
  last_check_error: null,
  install_status: "succeeded",
  last_install_at: null,
  last_install_message_id: null,
  last_install_error: null,
  ready_apt: true,
  ready_dnf: true,
  ready_zypper: true,
  ready_pkg: true,
};

const APT_CONFIG = {
  id: "cfg-apt",
  platform: "apt",
  host_id: "h1",
  mirror_root_path: "/srv/mirror",
  integrity_check_cadence_hours: 24,
  retention_window_days: 30,
  default_bandwidth_cap_kbps: 0,
  snapshot_count_to_keep: 5,
  created_at: null,
  updated_at: null,
};

const APT_MIRROR = {
  id: "mir1",
  name: "ubuntu-noble",
  package_manager: "apt",
  upstream_url: "http://archive.ubuntu.com/ubuntu",
  suite: "noble",
  components: "main",
  bandwidth_cap_kbps: 0,
  sync_cron: "0 4 * * *",
  enabled: true,
  host_id: "h1",
  platform_config_id: "cfg-apt",
  known_version_id: null,
  last_sync_status: "SUCCESS",
  last_sync_at: "2026-01-01T00:00:00Z",
  last_sync_message_id: null,
  last_snapshot_status: null,
  last_snapshot_message_id: null,
  last_restore_status: null,
  last_restore_message_id: null,
  last_integrity_message_id: null,
  last_gc_message_id: null,
};

const KNOWN_VERSION = {
  id: "kv1",
  platform: "apt",
  version_key: "ubuntu-24.04",
  label: "Ubuntu 24.04 (Noble)",
  os_family: "ubuntu",
  match_regex: "",
  default_upstream_url: "http://archive.ubuntu.com/ubuntu",
  default_suite: "noble",
  default_repoid: null,
  default_repo_alias: null,
  default_release: null,
  is_active: true,
};

beforeEach(() => {
  vi.clearAllMocks();
  errSpy = vi.spyOn(window.console, "error").mockImplementation(() => {});
  m(axiosInstance.get).mockResolvedValue({ data: [HOST] });
  m(svc.listPlatformConfigs).mockResolvedValue([APT_CONFIG]);
  m(svc.listMirrors).mockResolvedValue([APT_MIRROR]);
  m(svc.listKnownVersions).mockResolvedValue([KNOWN_VERSION]);
  m(svc.listSnapshots).mockResolvedValue([]);
  m(svc.getMirrorSetupStatus).mockResolvedValue(READY_STATUS);
  m(svc.createMirror).mockResolvedValue({ ...APT_MIRROR, id: "new" });
  m(svc.updateMirror).mockResolvedValue(APT_MIRROR);
  m(svc.deleteMirror).mockResolvedValue(undefined);
  m(svc.createPlatformConfig).mockResolvedValue(APT_CONFIG);
  m(svc.updatePlatformConfig).mockResolvedValue(APT_CONFIG);
  m(svc.deletePlatformConfig).mockResolvedValue(undefined);
  m(svc.syncMirror).mockResolvedValue({ message: "ok", mirror_id: "mir1", message_id: "x" });
  m(svc.snapshotMirror).mockResolvedValue({ snapshot_id: "s1", message_id: "x" });
  m(svc.restoreMirror).mockResolvedValue({ snapshot_id: "s1", message_id: "x" });
});

afterEach(() => {
  errSpy.mockRestore();
});

test("renders the loaded mirror table for the active platform", async () => {
  render(<RepositoryMirroringSettings />);

  // Configured platform => the mirror table (gated behind the ready
  // setup probe) shows the loaded mirror row.
  expect(await screen.findByText("ubuntu-noble")).toBeInTheDocument();
  expect(screen.getByText("Mirror Repositories")).toBeInTheDocument();
  expect(svc.listPlatformConfigs).toHaveBeenCalled();
  expect(svc.listMirrors).toHaveBeenCalled();
});

test("switching to the FreeBSD tab shows the empty-state config form", async () => {
  render(<RepositoryMirroringSettings />);
  await screen.findByText("ubuntu-noble");

  // pkg has no config in fixtures => ConfigureEmptyState renders.
  fireEvent.click(screen.getByRole("tab", { name: /FreeBSD/ }));

  await waitFor(() =>
    expect(screen.getByText(/Configure FreeBSD mirroring/)).toBeInTheDocument(),
  );
});

test("opens the Add Mirror dialog and can save a new mirror", async () => {
  render(<RepositoryMirroringSettings />);
  await screen.findByText("ubuntu-noble");

  fireEvent.click(screen.getByRole("button", { name: /Add Mirror/ }));

  const dialog = await screen.findByRole("dialog");
  expect(within(dialog).getByText("Add Mirror")).toBeInTheDocument();

  // Fill the name so the draft is minimally valid; picking the version
  // auto-fills upstream_url + suite via applyVersionToDraft.
  const nameField = within(dialog).getByLabelText(/Name \(used as on-disk subdir\)/);
  fireEvent.change(nameField, { target: { value: "my-mirror" } });

  // Select the known version from the dropdown to fill upstream/suite.
  const versionSelect = within(dialog).getByLabelText(/Version/);
  fireEvent.mouseDown(versionSelect);
  const option = await screen.findByRole("option", { name: /Ubuntu 24.04/ });
  fireEvent.click(option);

  const saveBtn = within(dialog).getByRole("button", { name: /^Save$/ });
  await waitFor(() => expect(saveBtn).not.toBeDisabled());
  fireEvent.click(saveBtn);

  await waitFor(() => expect(svc.createMirror).toHaveBeenCalled());
});

test("triggers a sync on an existing mirror row", async () => {
  render(<RepositoryMirroringSettings />);
  await screen.findByText("ubuntu-noble");

  fireEvent.click(screen.getByRole("button", { name: /Sync now/ }));

  await waitFor(() => expect(svc.syncMirror).toHaveBeenCalledWith("mir1"));
});

test("expanding a mirror row loads its snapshots", async () => {
  render(<RepositoryMirroringSettings />);
  await screen.findByText("ubuntu-noble");

  fireEvent.click(screen.getByRole("button", { name: /Show snapshots/ }));

  await waitFor(() => expect(svc.listSnapshots).toHaveBeenCalledWith("mir1"));
});
