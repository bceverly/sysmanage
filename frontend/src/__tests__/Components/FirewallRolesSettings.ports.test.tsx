// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

/**
 * Port editing, grid rendering and error-path tests for
 * Components/FirewallRolesSettings.tsx.  A firewall role decides which ports
 * end up open on managed hosts, so the exact port entries sent to the server
 * are asserted, not just that a request happened.
 */

import { render, screen, fireEvent, waitFor, within } from "@testing-library/react";
import { vi, beforeEach, describe, test, expect } from "vitest";

vi.mock("react-i18next", () => {
  const t = (key: string, fallback?: string) => fallback || key;
  return { useTranslation: () => ({ t, i18n: { language: "en" } }) };
});

// Render every column's renderCell (or the raw field) and expose the
// selection callback through a test button.
vi.mock("@mui/x-data-grid", () => ({
  DataGrid: ({
    rows,
    columns,
    onRowSelectionModelChange,
  }: {
    rows: Array<Record<string, unknown>>;
    columns: Array<Record<string, unknown>>;
    onRowSelectionModelChange: (_ids: unknown[]) => void;
  }) => (
    <div data-testid="grid">
      <button type="button" onClick={() => onRowSelectionModelChange(rows.map((r) => r.id))}>
        select-all-rows
      </button>
      {rows.map((r) => (
        <div key={String(r.id)} data-testid={`row-${String(r.id)}`}>
          {columns.map((c) => (
            <div key={String(c.field)} data-testid={`cell-${String(c.field)}`}>
              {c.renderCell
                ? ((c.renderCell as CallableFunction)({ row: r }) as never)
                : String(r[c.field as string])}
            </div>
          ))}
        </div>
      ))}
    </div>
  ),
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

const port = (n: number, over: Record<string, boolean> = {}) => ({
  port_number: n,
  tcp: true,
  udp: false,
  ipv4: true,
  ipv6: true,
  ...over,
});

const webRole = {
  id: "r1",
  name: "Web Server",
  open_ports: [port(443), port(53, { udp: true, ipv6: false }), port(22, { ipv4: false })],
};

const bigRole = {
  id: "r2",
  name: "Big",
  open_ports: [1, 2, 3, 4, 5, 6].map((n) => port(n, { ipv6: false })),
};

let roles: unknown[] = [webRole];

beforeEach(() => {
  vi.clearAllMocks();
  roles = [webRole];
  m(hasPermission).mockResolvedValue(true);
  m(axiosInstance.get).mockImplementation((url: string) => {
    if (url.includes("common-ports")) {
      return Promise.resolve({ data: { ports: [{ port: 80, name: "HTTP", default_protocol: "tcp" }] } });
    }
    return Promise.resolve({ data: roles });
  });
  m(axiosInstance.post).mockResolvedValue({ data: {} });
  m(axiosInstance.put).mockResolvedValue({ data: {} });
  m(axiosInstance.delete).mockResolvedValue({ data: {} });
});

const ready = async () => {
  render(<FirewallRolesSettings />);
  await screen.findByTestId("grid");
};

const openAdd = async () => {
  await ready();
  fireEvent.click(screen.getByRole("button", { name: "firewallRoles.addRole" }));
  return screen.findByRole("dialog");
};

const combos = (dialog: HTMLElement) => within(dialog).getAllByRole("combobox");

const choose = (combo: HTMLElement, name: string) => {
  fireEvent.mouseDown(combo);
  fireEvent.click(within(screen.getByRole("listbox")).getByRole("option", { name }));
};

const addPort = (dialog: HTMLElement) =>
  fireEvent.click(within(dialog).getByRole("button", { name: "firewallRoles.addPort" }));

// The chip area that follows the "Open IPvN Ports (count)" heading.
const portList = (dialog: HTMLElement, version: "IPv4" | "IPv6") => {
  const heading = within(dialog).getByText(new RegExp(`^firewallRoles\\.open${version}Ports \\(\\d+\\)$`));
  return { heading, list: heading.nextElementSibling as HTMLElement };
};

const deleteChip = (list: HTMLElement, label: string) => {
  const chip = within(list).getByText(label).closest(".MuiChip-root") as HTMLElement;
  fireEvent.click(within(chip).getByTestId("CancelIcon"));
};

describe("grid rendering", () => {
  test("splits ports by IP version, formats protocols and collapses overflow", async () => {
    roles = [webRole, bigRole];
    await ready();
    const web = screen.getByTestId("row-r1");
    const v4 = within(web).getByTestId("cell-ipv4_ports");
    const v6 = within(web).getByTestId("cell-ipv6_ports");
    expect(within(v4).getByText("443-TCP")).toBeInTheDocument();
    expect(within(v4).getByText("53-TCP/UDP")).toBeInTheDocument();
    expect(within(v4).queryByText("22-TCP")).toBeNull();
    expect(within(v6).getByText("22-TCP")).toBeInTheDocument();
    expect(within(v6).queryByText("53-TCP/UDP")).toBeNull();

    const big = screen.getByTestId("row-r2");
    expect(within(big).getByText("+2")).toBeInTheDocument();
    expect(within(big).queryByText("5-TCP")).toBeNull();
    expect(within(big).getByText("firewallRoles.noIPv6Ports")).toBeInTheDocument();
  });

  test("a role with no IPv4 ports says so", async () => {
    roles = [{ id: "r3", name: "v6", open_ports: [port(1, { ipv4: false })] }];
    await ready();
    expect(within(screen.getByTestId("cell-ipv4_ports")).getByText("firewallRoles.noIPv4Ports")).toBeInTheDocument();
  });

  test("an empty role list shows the no-roles hint", async () => {
    roles = [];
    render(<FirewallRolesSettings />);
    expect(await screen.findByText("firewallRoles.noRoles")).toBeInTheDocument();
  });

  test("edit/delete actions are hidden without those permissions", async () => {
    m(hasPermission).mockImplementation((r: string) =>
      Promise.resolve(r === "View Firewall Roles"),
    );
    await ready();
    expect(screen.queryByTitle("firewallRoles.editRole")).toBeNull();
    expect(screen.queryByTitle("firewallRoles.deleteRole")).toBeNull();
    expect(screen.queryByRole("button", { name: "firewallRoles.addRole" })).toBeNull();
  });
});

describe("adding ports", () => {
  test("custom, range, any and common ports are added with protocol and IP version", async () => {
    const dialog = await openAdd();
    fireEvent.change(within(dialog).getByLabelText(/firewallRoles.roleName/), { target: { value: "Mixed" } });
    expect(within(dialog).getByText("firewallRoles.noIPv4Ports")).toBeInTheDocument();
    expect(within(dialog).getByText("firewallRoles.noIPv6Ports")).toBeInTheDocument();

    // Custom UDP port, IPv4 only.
    choose(combos(dialog)[0], "firewallRoles.customPort");
    fireEvent.change(within(dialog).getByLabelText("firewallRoles.customPort"), { target: { value: "8080" } });
    choose(combos(dialog)[1], "firewallRoles.udp");
    choose(combos(dialog)[2], "firewallRoles.ipv4Only");
    addPort(dialog);
    expect(within(portList(dialog, "IPv4").list).getByText("8080-UDP")).toBeInTheDocument();
    expect(portList(dialog, "IPv6").heading).toHaveTextContent("(0)");

    // Range 1000-1001, both protocols, IPv6 only.
    choose(combos(dialog)[0], "firewallRoles.portRange");
    fireEvent.change(within(dialog).getByLabelText("firewallRoles.startPort"), { target: { value: "1000" } });
    fireEvent.change(within(dialog).getByLabelText("firewallRoles.endPort"), { target: { value: "1001" } });
    choose(combos(dialog)[1], "firewallRoles.both");
    choose(combos(dialog)[2], "firewallRoles.ipv6Only");
    addPort(dialog);
    const v6 = portList(dialog, "IPv6").list;
    expect(within(v6).getByText("1000-TCP/UDP")).toBeInTheDocument();
    expect(within(v6).getByText("1001-TCP/UDP")).toBeInTheDocument();

    // Any port (0), defaults: TCP on both stacks.
    choose(combos(dialog)[0], "firewallRoles.anyPort");
    addPort(dialog);
    expect(within(portList(dialog, "IPv4").list).getByText("0-TCP")).toBeInTheDocument();

    // Common port 80 on IPv4, then again on IPv6: merged into one entry.
    choose(combos(dialog)[0], "80 - HTTP");
    choose(combos(dialog)[2], "firewallRoles.ipv4Only");
    addPort(dialog);
    choose(combos(dialog)[0], "80 - HTTP");
    choose(combos(dialog)[2], "firewallRoles.ipv6Only");
    addPort(dialog);
    expect(within(portList(dialog, "IPv6").list).getByText("80-TCP")).toBeInTheDocument();

    fireEvent.click(within(dialog).getByRole("button", { name: "common.save" }));
    await waitFor(() => expect(axiosInstance.post).toHaveBeenCalled());
    expect(m(axiosInstance.post).mock.calls[0]).toEqual([
      "/api/v1/firewall-roles/",
      {
        name: "Mixed",
        open_ports: [
          { port_number: 8080, tcp: false, udp: true, ipv4: true, ipv6: false },
          { port_number: 1000, tcp: true, udp: true, ipv4: false, ipv6: true },
          { port_number: 1001, tcp: true, udp: true, ipv4: false, ipv6: true },
          { port_number: 0, tcp: true, udp: false, ipv4: true, ipv6: true },
          { port_number: 80, tcp: true, udp: false, ipv4: true, ipv6: true },
        ],
      },
    ]);
    expect(await screen.findByText("firewallRoles.createSuccess")).toBeInTheDocument();
  });

  test("invalid custom ports and ranges are refused with a message", async () => {
    const dialog = await openAdd();
    choose(combos(dialog)[0], "firewallRoles.customPort");
    fireEvent.change(within(dialog).getByLabelText("firewallRoles.customPort"), { target: { value: "70000" } });
    addPort(dialog);
    expect(await screen.findByText("firewallRoles.invalidPortNumber")).toBeInTheDocument();

    choose(combos(dialog)[0], "firewallRoles.portRange");
    fireEvent.change(within(dialog).getByLabelText("firewallRoles.startPort"), { target: { value: "500" } });
    fireEvent.change(within(dialog).getByLabelText("firewallRoles.endPort"), { target: { value: "100" } });
    addPort(dialog);
    expect(portList(dialog, "IPv4").heading).toHaveTextContent("(0)");
    expect(portList(dialog, "IPv6").heading).toHaveTextContent("(0)");
  });

  test("cancel discards the dialog without saving", async () => {
    const dialog = await openAdd();
    fireEvent.click(within(dialog).getByRole("button", { name: "common.cancel" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    expect(axiosInstance.post).not.toHaveBeenCalled();
  });
});

describe("removing ports while editing", () => {
  test("removing from one stack keeps the other, removing the last stack drops the port", async () => {
    await ready();
    fireEvent.click(screen.getByTitle("firewallRoles.editRole"));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText("firewallRoles.editRole")).toBeInTheDocument();

    // 443 is on both stacks: drop IPv4, it stays on IPv6.
    deleteChip(portList(dialog, "IPv4").list, "443-TCP");
    expect(within(portList(dialog, "IPv4").list).queryByText("443-TCP")).toBeNull();
    expect(within(portList(dialog, "IPv6").list).getByText("443-TCP")).toBeInTheDocument();
    // Now IPv6-only: removing it from IPv6 deletes it.
    deleteChip(portList(dialog, "IPv6").list, "443-TCP");
    // 53 is IPv4-only: removing it deletes it.
    deleteChip(portList(dialog, "IPv4").list, "53-TCP/UDP");
    // 22 is IPv6-only; add it on IPv4 too, then drop the IPv6 side.
    choose(combos(dialog)[0], "firewallRoles.customPort");
    fireEvent.change(within(dialog).getByLabelText("firewallRoles.customPort"), { target: { value: "22" } });
    choose(combos(dialog)[2], "firewallRoles.ipv4Only");
    addPort(dialog);
    deleteChip(portList(dialog, "IPv6").list, "22-TCP");

    fireEvent.click(within(dialog).getByRole("button", { name: "common.save" }));
    await waitFor(() =>
      expect(axiosInstance.put).toHaveBeenCalledWith("/api/v1/firewall-roles/r1", {
        name: "Web Server",
        open_ports: [{ port_number: 22, tcp: true, udp: false, ipv4: true, ipv6: false }],
      }),
    );
    expect(await screen.findByText("firewallRoles.updateSuccess")).toBeInTheDocument();
  });
});

describe("error reporting", () => {
  const saveNew = async () => {
    const dialog = await openAdd();
    fireEvent.change(within(dialog).getByLabelText(/firewallRoles.roleName/), { target: { value: "X" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "common.save" }));
  };

  test("a string detail from the API is shown", async () => {
    vi.spyOn(globalThis.console, "error").mockImplementation(() => {});
    m(axiosInstance.post).mockRejectedValue({ response: { data: { detail: "Role name already exists" } } });
    await saveNew();
    expect(await screen.findByText("Role name already exists")).toBeInTheDocument();
  });

  test("the first validation message is shown for a detail array", async () => {
    vi.spyOn(globalThis.console, "error").mockImplementation(() => {});
    m(axiosInstance.post).mockRejectedValue({ response: { data: { detail: [{ msg: "port out of range" }] } } });
    await saveNew();
    expect(await screen.findByText("port out of range")).toBeInTheDocument();
  });

  test("an unusable detail falls back to the default message", async () => {
    vi.spyOn(globalThis.console, "error").mockImplementation(() => {});
    m(axiosInstance.post).mockRejectedValue({ response: { data: { detail: [{}] } } });
    await saveNew();
    expect(await screen.findByText("firewallRoles.errorCreating")).toBeInTheDocument();
  });

  test("an empty detail array or object falls back too, and edit uses the update message", async () => {
    vi.spyOn(globalThis.console, "error").mockImplementation(() => {});
    m(axiosInstance.put).mockRejectedValueOnce({ response: { data: { detail: [] } } });
    await ready();
    fireEvent.click(screen.getByTitle("firewallRoles.editRole"));
    const dialog = await screen.findByRole("dialog");
    fireEvent.click(within(dialog).getByRole("button", { name: "common.save" }));
    expect(await screen.findByText("firewallRoles.errorUpdating")).toBeInTheDocument();
  });

  test("a delete failure shows the API detail and closes the confirmation", async () => {
    vi.spyOn(globalThis.console, "error").mockImplementation(() => {});
    m(axiosInstance.delete).mockRejectedValue({ response: { data: { detail: "Role is assigned to hosts" } } });
    await ready();
    fireEvent.click(screen.getByTitle("firewallRoles.deleteRole"));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText("Web Server")).toBeInTheDocument();
    fireEvent.click(within(dialog).getByRole("button", { name: "common.delete" }));
    expect(await screen.findByText("Role is assigned to hosts")).toBeInTheDocument();
    await waitFor(() => expect(screen.queryByText("firewallRoles.confirmDelete")).toBeNull());
  });

  test("a delete failure without detail uses the default message", async () => {
    vi.spyOn(globalThis.console, "error").mockImplementation(() => {});
    m(axiosInstance.delete).mockRejectedValue(new Error("x"));
    await ready();
    fireEvent.click(screen.getByTitle("firewallRoles.deleteRole"));
    fireEvent.click(await screen.findByRole("button", { name: "common.delete" }));
    expect(await screen.findByText("firewallRoles.errorDeleting")).toBeInTheDocument();
  });

  test("the delete confirmation can be canceled", async () => {
    await ready();
    fireEvent.click(screen.getByTitle("firewallRoles.deleteRole"));
    fireEvent.click(await screen.findByRole("button", { name: "common.cancel" }));
    await waitFor(() => expect(screen.queryByText("firewallRoles.confirmDelete")).toBeNull());
    expect(axiosInstance.delete).not.toHaveBeenCalled();
  });

  test("a common-ports load failure is reported", async () => {
    vi.spyOn(globalThis.console, "error").mockImplementation(() => {});
    m(axiosInstance.get).mockImplementation((url: string) =>
      url.includes("common-ports") ? Promise.reject(new Error("x")) : Promise.resolve({ data: roles }),
    );
    render(<FirewallRolesSettings />);
    expect(await screen.findByText("firewallRoles.errorLoadingPorts")).toBeInTheDocument();
  });

  test("a roles load failure is reported", async () => {
    vi.spyOn(globalThis.console, "error").mockImplementation(() => {});
    m(axiosInstance.get).mockImplementation((url: string) =>
      url.includes("common-ports") ? Promise.resolve({ data: { ports: [] } }) : Promise.reject(new Error("x")),
    );
    render(<FirewallRolesSettings />);
    expect(await screen.findByText("firewallRoles.errorLoading")).toBeInTheDocument();
  });

  test("a permission lookup failure is logged and fails closed", async () => {
    const errSpy = vi.spyOn(globalThis.console, "error").mockImplementation(() => {});
    m(hasPermission).mockRejectedValue(new Error("expired"));
    render(<FirewallRolesSettings />);
    expect(await screen.findByText("firewallRoles.noViewPermission")).toBeInTheDocument();
    await waitFor(() =>
      expect(errSpy).toHaveBeenCalledWith("Failed to resolve permissions:", expect.any(Error)),
    );
  });
});

describe("bulk delete", () => {
  test("deletes every selected role and reloads", async () => {
    roles = [webRole, bigRole];
    await ready();
    const bulk = screen.getByRole("button", { name: "firewallRoles.deleteSelected" });
    expect(bulk).toBeDisabled();
    fireEvent.click(screen.getByText("select-all-rows"));
    expect(bulk).not.toBeDisabled();
    const loadsBefore = m(axiosInstance.get).mock.calls.length;
    fireEvent.click(bulk);
    await waitFor(() => expect(axiosInstance.delete).toHaveBeenCalledTimes(2));
    expect(axiosInstance.delete).toHaveBeenCalledWith("/api/v1/firewall-roles/r1");
    expect(axiosInstance.delete).toHaveBeenCalledWith("/api/v1/firewall-roles/r2");
    expect(await screen.findByText("firewallRoles.deleteSuccess")).toBeInTheDocument();
    await waitFor(() => expect(m(axiosInstance.get).mock.calls.length).toBeGreaterThan(loadsBefore));
  });

  test("a bulk delete failure reports the API detail", async () => {
    vi.spyOn(globalThis.console, "error").mockImplementation(() => {});
    m(axiosInstance.delete).mockRejectedValue({ response: { data: { detail: "nope" } } });
    await ready();
    fireEvent.click(screen.getByText("select-all-rows"));
    fireEvent.click(screen.getByRole("button", { name: "firewallRoles.deleteSelected" }));
    expect(await screen.findByText("nope")).toBeInTheDocument();
  });
});
