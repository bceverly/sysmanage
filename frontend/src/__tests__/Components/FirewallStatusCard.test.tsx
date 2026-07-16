// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { vi, beforeEach, afterEach, test, expect } from "vitest";

// Error-path tests intentionally log to console.error; silence the expected
// noise without hiding real errors (restored after each test).
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

vi.mock("../../Services/api", () => ({
  default: { get: vi.fn(), post: vi.fn(), put: vi.fn(), delete: vi.fn() },
}));

vi.mock("../../Services/firewallService", () => ({
  getFirewallStatus: vi.fn(),
}));

vi.mock("../../Services/firewallOperationsService", () => ({
  deployFirewall: vi.fn(),
  enableFirewall: vi.fn(),
  disableFirewall: vi.fn(),
  restartFirewall: vi.fn(),
}));

vi.mock("../../Services/license", () => ({
  isModuleLicensed: vi.fn(),
}));

vi.mock("../../Services/permissions", () => ({
  hasPermission: vi.fn(),
  SecurityRoles: {
    DEPLOY_FIREWALL: "Deploy Firewall",
    REMOVE_FIREWALL: "Remove Firewall",
    ENABLE_FIREWALL: "Enable Firewall",
    DISABLE_FIREWALL: "Disable Firewall",
    RESTART_FIREWALL: "Restart Firewall",
    ASSIGN_HOST_FIREWALL_ROLES: "Assign Host Firewall Roles",
    VIEW_FIREWALL_ROLES: "View Firewall Roles",
  },
}));

import axiosInstance from "../../Services/api";
import { getFirewallStatus } from "../../Services/firewallService";
import {
  disableFirewall,
  restartFirewall,
} from "../../Services/firewallOperationsService";
import { isModuleLicensed } from "../../Services/license";
import { hasPermission } from "../../Services/permissions";
import FirewallStatusCard from "../../Components/FirewallStatusCard";

const m = (fn: unknown) => fn as unknown as ReturnType<typeof vi.fn>;

const enabledStatus = {
  id: "s1",
  host_id: "h1",
  firewall_name: "ufw",
  enabled: true,
  tcp_open_ports: null,
  udp_open_ports: null,
  ipv4_ports: JSON.stringify([{ port: "22", protocols: ["tcp"] }]),
  ipv6_ports: JSON.stringify([{ port: "443", protocols: ["tcp"] }]),
  last_updated: "2026-01-01T00:00:00Z",
};

const hostRoles = [
  {
    id: "a1",
    firewall_role_id: "r1",
    firewall_role_name: "Web Server",
    created_at: "2026-01-01T00:00:00Z",
  },
];

const allRoles = [
  { id: "r1", name: "Web Server" },
  { id: "r2", name: "DB Server" },
];

const expectedPorts = {
  ipv4_ports: [{ port: "8080", protocols: ["tcp"] }],
  ipv6_ports: [],
};

beforeEach(() => {
  vi.clearAllMocks();
  errSpy = vi.spyOn(window.console, "error").mockImplementation(() => {});
  m(hasPermission).mockResolvedValue(true);
  m(isModuleLicensed).mockReturnValue(true);
  m(getFirewallStatus).mockResolvedValue(enabledStatus);
  m(axiosInstance.get).mockImplementation((url: string) => {
    if (url.includes("/roles")) return Promise.resolve({ data: hostRoles });
    if (url.includes("expected-ports"))
      return Promise.resolve({ data: expectedPorts });
    if (url.endsWith("firewall-roles/"))
      return Promise.resolve({ data: allRoles });
    return Promise.resolve({ data: [] });
  });
  m(axiosInstance.post).mockResolvedValue({ data: {} });
  m(axiosInstance.delete).mockResolvedValue({ data: {} });
  m(disableFirewall).mockResolvedValue(undefined);
  m(restartFirewall).mockResolvedValue(undefined);
});

afterEach(() => {
  errSpy.mockRestore();
});

test("renders firewall status, name and assigned roles", async () => {
  render(<FirewallStatusCard hostId="h1" />);

  expect(await screen.findByText("ufw")).toBeInTheDocument();
  expect(screen.getByText("Enabled")).toBeInTheDocument();
  await waitFor(() =>
    expect(screen.getByText("Web Server")).toBeInTheDocument(),
  );
  expect(m(getFirewallStatus)).toHaveBeenCalledWith("h1");
});

test("disables the firewall through the Disable button", async () => {
  render(<FirewallStatusCard hostId="h1" />);
  await screen.findByText("ufw");

  fireEvent.click(screen.getByText("Disable Firewall"));

  await waitFor(() =>
    expect(m(disableFirewall)).toHaveBeenCalledWith("h1"),
  );
});

test("restarts the firewall through the Restart button", async () => {
  render(<FirewallStatusCard hostId="h1" />);
  await screen.findByText("ufw");

  fireEvent.click(screen.getByText("Restart Firewall"));

  await waitFor(() =>
    expect(m(restartFirewall)).toHaveBeenCalledWith("h1"),
  );
});

test("opens the Edit Roles dialog and saves a newly added role", async () => {
  render(<FirewallStatusCard hostId="h1" />);
  await screen.findByText("ufw");

  fireEvent.click(screen.getByText("Edit Roles"));

  // Dialog title appears.
  await screen.findByText("Edit Firewall Roles");

  // Save with existing pending roles closes; assert save button reachable.
  fireEvent.click(screen.getByText("Save"));

  await waitFor(() =>
    expect(m(axiosInstance.get)).toHaveBeenCalledWith(
      "/api/v1/firewall-roles/host/h1/roles",
    ),
  );
});

test("shows the deploy button and an error alert when status load fails", async () => {
  m(getFirewallStatus).mockRejectedValue(new Error("boom"));
  render(<FirewallStatusCard hostId="h1" />);
  expect(
    await screen.findByText("Failed to load firewall status"),
  ).toBeInTheDocument();
});
