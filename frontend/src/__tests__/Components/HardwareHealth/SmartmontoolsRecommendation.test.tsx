// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { vi, beforeEach, describe, test, expect } from "vitest";

vi.mock("react-i18next", async () => {
  const { t } = await import("../TimeSync/_i18nMock");
  return { useTranslation: () => ({ t, i18n: { language: "en" } }) };
});
vi.mock("../../../Services/permissions", () => ({
  hasPermission: vi.fn(),
  getUserPermissions: vi.fn(),
  SecurityRoles: {
    MANAGE_HARDWARE_HEALTH: "Manage Hardware Health",
    ADD_PACKAGE: "Add Package",
  },
}));
vi.mock("../../../Services/hardwareHealth", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../../Services/hardwareHealth")>();
  return {
    ...actual,
    getSmartmontools: vi.fn(),
    installSmartmontools: vi.fn(),
    setSmartmontoolsAuto: vi.fn(),
  };
});

import { getUserPermissions, hasPermission } from "../../../Services/permissions";
import type { UserPermissions } from "../../../Services/permissions";
import {
  getSmartmontools,
  installSmartmontools,
  setSmartmontoolsAuto,
} from "../../../Services/hardwareHealth";
import type { SmartmontoolsStatus, ToolInstall } from "../../../Services/hardwareHealth";
import {
  FleetSmartmontools,
  HostSmartmontools,
} from "../../../Components/HardwareHealth/SmartmontoolsRecommendation";

const failed: ToolInstall = {
  package: "smartmontools",
  status: "failed",
  attempts: 1,
  requested_by: "admin@example.com",
  requested_at: "2026-10-14T12:00:00",
  finished_at: "2026-10-14T12:01:00",
  last_error: "pkg: No packages available",
};

const fleet = (over: Partial<SmartmontoolsStatus> = {}): SmartmontoolsStatus => ({
  licensed: true,
  auto: false,
  hosts: [{ host_id: "h1", fqdn: "freebsd.lab", platform: "FreeBSD", install: null }],
  ...over,
});

const allowed = (yes: boolean, admin = false) => {
  vi.mocked(hasPermission).mockResolvedValue(yes);
  vi.mocked(getUserPermissions).mockResolvedValue({ is_admin: admin } as UserPermissions);
};

describe("HostSmartmontools", () => {
  beforeEach(() => vi.mocked(installSmartmontools).mockReset());

  test("nothing when not recommended", () => {
    allowed(true);
    const { container } = render(
      <HostSmartmontools hostId="h1" recommended={false} install={null} onChanged={vi.fn()} />,
    );
    expect(container).toBeEmptyDOMElement();
  });

  test("recommends, shows the last failure, installs", async () => {
    allowed(true);
    vi.mocked(installSmartmontools).mockResolvedValueOnce({ queued: 1, skipped: 0 });
    const changed = vi.fn();
    render(<HostSmartmontools hostId="h1" recommended install={failed} onChanged={changed} />);
    expect(screen.getByText(/can only be read with smartmontools/)).toBeInTheDocument();
    expect(screen.getByText("Install failed: pkg: No packages available")).toBeInTheDocument();
    fireEvent.click(await screen.findByText("Install smartmontools"));
    await waitFor(() => expect(changed).toHaveBeenCalled());
    expect(installSmartmontools).toHaveBeenCalledWith(["h1"]);
  });

  test("no button without both roles", async () => {
    allowed(false);
    render(<HostSmartmontools hostId="h1" recommended install={null} onChanged={vi.fn()} />);
    await waitFor(() => expect(hasPermission).toHaveBeenCalled());
    expect(screen.queryByText("Install smartmontools")).not.toBeInTheDocument();
  });
});

describe("FleetSmartmontools", () => {
  beforeEach(() => {
    vi.mocked(getSmartmontools).mockReset();
    vi.mocked(setSmartmontoolsAuto).mockReset();
  });

  test("lists the hosts and installs on them", async () => {
    allowed(true);
    vi.mocked(getSmartmontools).mockResolvedValue(fleet());
    vi.mocked(installSmartmontools).mockResolvedValueOnce({ queued: 1, skipped: 0 });
    render(<FleetSmartmontools onChanged={vi.fn()} />);
    expect(await screen.findByText("freebsd.lab")).toBeInTheDocument();
    fireEvent.click(await screen.findByText("Install smartmontools on these hosts"));
    expect(await screen.findByText("Hosts where the install was requested: 1")).toBeInTheDocument();
    expect(installSmartmontools).toHaveBeenCalledWith(["h1"]);
  });

  test("an administrator consents to the automatic install", async () => {
    allowed(true, true);
    vi.mocked(getSmartmontools).mockResolvedValue(fleet());
    vi.mocked(setSmartmontoolsAuto).mockResolvedValueOnce({ auto: true });
    render(<FleetSmartmontools onChanged={vi.fn()} />);
    const toggle = await screen.findByRole("switch");
    await waitFor(() => expect(toggle).not.toBeDisabled());
    fireEvent.click(toggle);
    await waitFor(() => expect(setSmartmontoolsAuto).toHaveBeenCalledWith(true));
  });

  test("unlicensed: the switch is off and says why", async () => {
    allowed(true, true);
    vi.mocked(getSmartmontools).mockResolvedValue(fleet({ licensed: false }));
    render(<FleetSmartmontools onChanged={vi.fn()} />);
    expect(
      await screen.findByText("Automatic installation requires a SysManage Enterprise license."),
    ).toBeInTheDocument();
    expect(screen.getByRole("switch")).toBeDisabled();
  });

  test("nothing when no host needs it", async () => {
    allowed(true);
    vi.mocked(getSmartmontools).mockResolvedValue(fleet({ hosts: [] }));
    const { container } = render(<FleetSmartmontools onChanged={vi.fn()} />);
    await waitFor(() => expect(getSmartmontools).toHaveBeenCalled());
    expect(container).toBeEmptyDOMElement();
  });
});
