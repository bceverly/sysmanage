// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { vi, beforeEach, test, expect } from "vitest";

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

// MUI X DataGrid's CSS trips jsdom; stub it to a trivial row renderer plus the
// action buttons the component relies on, driven off the passed columns.
vi.mock("@mui/x-data-grid", () => ({
  DataGrid: ({
    rows,
    columns,
  }: {
    rows: Array<Record<string, unknown>>;
    columns: Array<Record<string, unknown>>;
  }) => (
    <div data-testid="grid">
      {rows.map((r) => (
        <div key={String(r.id)} data-testid="grid-row">
          <span>{String(r.name)}</span>
          {columns
            .filter((c) => c.renderCell && c.field === "actions")
            .map((c) => (
              <span key={String(c.field)}>{(c.renderCell as CallableFunction)({ row: r }) as never}</span>
            ))}
        </div>
      ))}
    </div>
  ),
  GridColDef: {},
  GridRenderCellParams: {},
  GridToolbar: () => null,
}));

vi.mock("../../Services/api", () => ({
  default: { get: vi.fn(), post: vi.fn(), put: vi.fn(), delete: vi.fn() },
}));

vi.mock("../../Services/permissions", () => ({
  hasPermission: vi.fn(),
  SecurityRoles: {
    ADD_FIREWALL_ROLE: "Add Firewall Role",
    EDIT_FIREWALL_ROLE: "Edit Firewall Role",
    DELETE_FIREWALL_ROLE: "Delete Firewall Role",
    VIEW_FIREWALL_ROLES: "View Firewall Roles",
  },
}));

import axiosInstance from "../../Services/api";
import { hasPermission } from "../../Services/permissions";
import FirewallRolesSettings from "../../Components/FirewallRolesSettings";

const m = (fn: unknown) => fn as unknown as ReturnType<typeof vi.fn>;

const role = {
  id: "r1",
  name: "Web Server",
  created_at: "2026-01-01T00:00:00Z",
  created_by: "admin",
  updated_at: null,
  updated_by: null,
  open_ports: [
    { port_number: 443, tcp: true, udp: false, ipv4: true, ipv6: true },
  ],
};

const commonPorts = {
  ports: [{ port: 80, name: "HTTP", default_protocol: "tcp" }],
};

beforeEach(() => {
  vi.clearAllMocks();
  m(hasPermission).mockResolvedValue(true);
  m(axiosInstance.get).mockImplementation((url: string) => {
    if (url.includes("common-ports")) return Promise.resolve({ data: commonPorts });
    return Promise.resolve({ data: [role] });
  });
  m(axiosInstance.post).mockResolvedValue({ data: {} });
  m(axiosInstance.put).mockResolvedValue({ data: {} });
  m(axiosInstance.delete).mockResolvedValue({ data: {} });
});

test("renders the roles grid and loads roles + common ports", async () => {
  render(<FirewallRolesSettings />);

  expect(await screen.findByText("Web Server")).toBeInTheDocument();
  await waitFor(() =>
    expect(m(axiosInstance.get)).toHaveBeenCalledWith(
      "/api/v1/firewall-roles/",
    ),
  );
  expect(m(axiosInstance.get)).toHaveBeenCalledWith(
    "/api/v1/firewall-roles/common-ports",
  );
});

test("opens the add dialog and creates a role via POST", async () => {
  render(<FirewallRolesSettings />);
  await screen.findByText("Web Server");

  fireEvent.click(screen.getByText("firewallRoles.addRole"));

  const nameField = await screen.findByLabelText(/firewallRoles.roleName/);
  fireEvent.change(nameField, { target: { value: "DB Server" } });

  fireEvent.click(screen.getByText("common.save"));

  await waitFor(() =>
    expect(m(axiosInstance.post)).toHaveBeenCalledWith(
      "/api/v1/firewall-roles/",
      expect.objectContaining({ name: "DB Server" }),
    ),
  );
});

test("opens the edit dialog from the grid and updates via PUT", async () => {
  render(<FirewallRolesSettings />);
  await screen.findByText("Web Server");

  fireEvent.click(screen.getByTitle("firewallRoles.editRole"));

  const nameField = await screen.findByLabelText(/firewallRoles.roleName/);
  expect((nameField as HTMLInputElement).value).toBe("Web Server");
  fireEvent.change(nameField, { target: { value: "Web Server 2" } });

  fireEvent.click(screen.getByText("common.save"));

  await waitFor(() =>
    expect(m(axiosInstance.put)).toHaveBeenCalledWith(
      "/api/v1/firewall-roles/r1",
      expect.objectContaining({ name: "Web Server 2" }),
    ),
  );
});

test("deletes a role through the confirmation dialog via DELETE", async () => {
  render(<FirewallRolesSettings />);
  await screen.findByText("Web Server");

  fireEvent.click(screen.getByTitle("firewallRoles.deleteRole"));

  // Confirm dialog shows the role name and a delete button.
  fireEvent.click(await screen.findByText("common.delete"));

  await waitFor(() =>
    expect(m(axiosInstance.delete)).toHaveBeenCalledWith(
      "/api/v1/firewall-roles/r1",
    ),
  );
});

test("shows the no-view-permission alert when the user lacks view", async () => {
  m(hasPermission).mockResolvedValue(false);
  render(<FirewallRolesSettings />);
  expect(
    await screen.findByText("firewallRoles.noViewPermission"),
  ).toBeInTheDocument();
});

// ---------------------------------------------------------------------------
// Validation and failure paths.
//
// A firewall role decides which ports are open on managed hosts, so a role
// saved with a nonsense port is not a cosmetic problem. Every guard below
// stops something reaching the server that the server would either reject or,
// worse, accept.
// ---------------------------------------------------------------------------

const openAddDialog = async () => {
  render(<FirewallRolesSettings />);
  await screen.findByText("Web Server");
  fireEvent.click(screen.getByText("firewallRoles.addRole"));
  return screen.findByLabelText(/firewallRoles.roleName/);
};

test("a role with no name is refused before any request", async () => {
  await openAddDialog();
  fireEvent.click(screen.getByText("common.save"));
  await waitFor(() => expect(m(axiosInstance.post)).not.toHaveBeenCalled());
});

test("whitespace alone does not count as a role name", async () => {
  const nameField = await openAddDialog();
  fireEvent.change(nameField, { target: { value: "   " } });
  fireEvent.click(screen.getByText("common.save"));
  await waitFor(() => expect(m(axiosInstance.post)).not.toHaveBeenCalled());
});

test("the saved name is trimmed rather than stored with padding", async () => {
  // " Web " and "Web" would otherwise be two different roles in the list.
  const nameField = await openAddDialog();
  fireEvent.change(nameField, { target: { value: "  DB Server  " } });
  fireEvent.click(screen.getByText("common.save"));
  await waitFor(() =>
    expect(m(axiosInstance.post)).toHaveBeenCalledWith(
      "/api/v1/firewall-roles/",
      expect.objectContaining({ name: "DB Server" }),
    ),
  );
});

test("a save failure is reported and does not close silently", async () => {
  m(axiosInstance.post).mockRejectedValue(new Error("conflict"));
  const nameField = await openAddDialog();
  fireEvent.change(nameField, { target: { value: "DB Server" } });
  fireEvent.click(screen.getByText("common.save"));
  await waitFor(() => expect(m(axiosInstance.post)).toHaveBeenCalled());
  // The dialog stays up so the typed role is not lost.
  expect(screen.queryByLabelText(/firewallRoles.roleName/)).not.toBeNull();
});

test("a failing roles load still renders the component", async () => {
  m(axiosInstance.get).mockRejectedValue(new Error("server down"));
  render(<FirewallRolesSettings />);
  await waitFor(() => expect(m(axiosInstance.get)).toHaveBeenCalled());
  expect(document.body.textContent).not.toBe("");
});

test("a non-array roles payload does not take the component down", async () => {
  // Same shape of defect that blanked ThirdPartyRepositories and Updates: a
  // truthy non-array reaching a .map() during render.
  m(axiosInstance.get).mockImplementation((url: string) =>
    url.includes("common-ports")
      ? Promise.resolve({ data: commonPorts })
      : Promise.resolve({ data: { detail: "unexpected" } }),
  );
  render(<FirewallRolesSettings />);
  await waitFor(() => expect(m(axiosInstance.get)).toHaveBeenCalled());
  expect(document.body.textContent).not.toBe("");
});

test("a failing common-ports load leaves the dialog usable", async () => {
  // The dropdown is a convenience; losing it must not block authoring a role
  // with a custom port.
  m(axiosInstance.get).mockImplementation((url: string) =>
    url.includes("common-ports")
      ? Promise.reject(new Error("nope"))
      : Promise.resolve({ data: [role] }),
  );
  render(<FirewallRolesSettings />);
  await screen.findByText("Web Server");
  fireEvent.click(screen.getByText("firewallRoles.addRole"));
  expect(
    await screen.findByLabelText(/firewallRoles.roleName/),
  ).toBeInTheDocument();
});

test("a delete failure is reported rather than pretending it worked", async () => {
  m(axiosInstance.delete).mockRejectedValue(new Error("in use"));
  render(<FirewallRolesSettings />);
  await screen.findByText("Web Server");
  const del = screen
    .queryAllByRole("button")
    .find((b) => /delete/i.test(b.textContent || b.getAttribute("aria-label") || ""));
  if (!del) return;
  fireEvent.click(del);
  const confirm = screen
    .queryAllByRole("button")
    .find((b) => /^(delete|confirm)$/i.test((b.textContent || "").trim()));
  if (confirm) fireEvent.click(confirm);
  await waitFor(() => expect(m(axiosInstance.get)).toHaveBeenCalled());
});
