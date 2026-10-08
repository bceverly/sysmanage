// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

import { render, screen, fireEvent, within } from "@testing-library/react";
import { vi, describe, beforeEach, test, expect } from "vitest";

vi.mock("react-i18next", () => {
  const t = (key: string, fallback?: string) =>
    typeof fallback === "string" ? fallback : key;
  return { useTranslation: () => ({ t, i18n: { language: "en" } }) };
});

vi.mock("../../../Services/permissions", () => ({
  hasPermissionSync: vi.fn(),
  SecurityRoles: {
    CREATE_CHILD_HOST: "Create Child Host",
    UPDATE_AGENT: "Update Agent",
  },
}));

// The hypervisor card is its own tested component; stub it to expose which
// card rendered and to forward its create callback.
vi.mock("../../../Components/HypervisorStatusCard", () => ({
  default: ({
    type,
    onCreate,
    canCreate,
    rebootRequired,
  }: {
    type: string;
    onCreate: () => void;
    canCreate: boolean;
    rebootRequired?: boolean;
  }) => (
    <div data-testid={`hv-${type}`}>
      <span>{`can-create:${String(canCreate)}`}</span>
      {rebootRequired && <span>reboot-pending</span>}
      <button onClick={onCreate}>{`create-${type}`}</button>
    </div>
  ),
}));

vi.mock("../../../Components/HostDetail/ChildHostProgress", () => ({
  default: () => null,
}));

import { hasPermissionSync } from "../../../Services/permissions";
import HostChildHostsTab from "../../../Components/HostDetail/HostChildHostsTab";
import type { ChildHost } from "../../../Components/HostDetail/hostDetailTypes";

const mockPerm = vi.mocked(hasPermissionSync);

const child = (over: Partial<ChildHost>): ChildHost => ({
  id: "c1",
  parent_host_id: "p1",
  child_host_id: "h-c1",
  child_name: "vm-one",
  child_type: "kvm",
  distribution: "Ubuntu",
  distribution_version: "24.04",
  hostname: "vm-one.local",
  status: "running",
  installation_step: null,
  error_message: null,
  created_at: null,
  installed_at: null,
  agent_version: "1.2.3",
  ...over,
});

const VSTATUS = {
  supported_types: ["wsl", "lxd", "kvm", "vmm", "bhyve"],
  capabilities: {},
  reboot_required: true,
} as any;

const ALL_ENGINES = ["container_engine", "virtualization_engine"];

const makeProps = (over: Record<string, unknown> = {}) => ({
  host: { id: "p1", platform: "Linux", is_agent_privileged: true } as any,
  licenseModules: ALL_ENGINES,
  virtualizationStatus: VSTATUS,
  virtualizationLoading: false,
  childHosts: [] as ChildHost[],
  childHostsLoading: false,
  childHostsRefreshRequested: false,
  childHostOperationLoading: {} as Record<string, string | null>,
  enableWslLoading: false,
  initializeLxdLoading: false,
  initializeKvmLoading: false,
  initializeVmmLoading: false,
  initializeBhyveLoading: false,
  disableBhyveLoading: false,
  kvmModulesLoading: false,
  canEnableWsl: true,
  canEnableLxd: true,
  canEnableKvm: true,
  canEnableVmm: true,
  canEnableBhyve: true,
  handleEnableWsl: vi.fn(),
  handleInitializeLxd: vi.fn(),
  handleInitializeKvm: vi.fn(),
  handleInitializeVmm: vi.fn(),
  handleInitializeBhyve: vi.fn(),
  handleDisableBhyve: vi.fn(),
  handleEnableKvmModules: vi.fn(),
  handleDisableKvmModules: vi.fn(),
  openCreateDialogWithType: vi.fn(),
  requestChildHostsRefresh: vi.fn(),
  handleChildHostStart: vi.fn(),
  handleChildHostStop: vi.fn(),
  handleChildHostRestart: vi.fn(),
  handleChildHostUpdateAgent: vi.fn(),
  handleChildHostDeleteConfirm: vi.fn(),
  getWslEmptyMessage: () => "wsl-empty",
  getLxdEmptyMessage: () => "lxd-empty",
  getVmmEmptyMessage: () => "vmm-empty",
  getBhyveEmptyMessage: () => "bhyve-empty",
  ...over,
});

const rowFor = (name: string) => screen.getByText(name).closest("tr") as HTMLElement;

describe("HostChildHostsTab", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockPerm.mockReturnValue(true);
  });

  test("shows the unavailable message, then loading spinners", () => {
    const { rerender } = render(
      <HostChildHostsTab {...makeProps({ virtualizationStatus: null })} />,
    );
    expect(
      screen.getByText("Virtualization status not available"),
    ).toBeInTheDocument();
    rerender(
      <HostChildHostsTab
        {...makeProps({ virtualizationStatus: null, virtualizationLoading: true, childHostsLoading: true })}
      />,
    );
    expect(screen.queryByText("Virtualization status not available")).toBeNull();
    expect(screen.getAllByRole("progressbar").length).toBeGreaterThanOrEqual(2);
    expect(screen.queryByText("No child hosts found")).toBeNull();
  });

  test.each([
    ["Linux", ["lxd", "kvm"], "lxd-empty"],
    ["Windows 11", ["wsl"], "wsl-empty"],
    ["OpenBSD", ["vmm"], "vmm-empty"],
    ["FreeBSD", ["bhyve"], "bhyve-empty"],
  ])("%s shows the matching hypervisor cards and empty message", (platform, cards, empty) => {
    const props = makeProps({ host: { id: "p1", platform, is_agent_privileged: false } });
    render(<HostChildHostsTab {...props} />);
    for (const type of ["wsl", "lxd", "kvm", "vmm", "bhyve"]) {
      if (cards.includes(type)) {
        expect(screen.getByTestId(`hv-${type}`)).toBeInTheDocument();
        fireEvent.click(screen.getByText(`create-${type}`));
        expect(props.openCreateDialogWithType).toHaveBeenCalledWith(type);
      } else {
        expect(screen.queryByTestId(`hv-${type}`)).toBeNull();
      }
    }
    expect(screen.getByText("No child hosts found")).toBeInTheDocument();
    expect(screen.getByText(empty)).toBeInTheDocument();
  });

  test("windows card receives the reboot flag", () => {
    render(
      <HostChildHostsTab
        {...makeProps({ host: { id: "p1", platform: "Windows", is_agent_privileged: true } })}
      />,
    );
    expect(screen.getByText("reboot-pending")).toBeInTheDocument();
  });

  test("hides hypervisor cards without the engines", () => {
    render(<HostChildHostsTab {...makeProps({ licenseModules: [] })} />);
    expect(screen.queryByTestId("hv-lxd")).toBeNull();
    expect(screen.queryByTestId("hv-kvm")).toBeNull();
  });

  test("refresh button requests a refresh and disables while pending", () => {
    const props = makeProps();
    const { rerender } = render(<HostChildHostsTab {...props} />);
    fireEvent.click(screen.getByRole("button", { name: "Refresh" }));
    expect(props.requestChildHostsRefresh).toHaveBeenCalled();
    rerender(<HostChildHostsTab {...props} childHostsRefreshRequested />);
    expect(screen.getByRole("button", { name: "Refresh" })).toBeDisabled();
  });

  test("renders rows with status labels, details and action buttons", () => {
    const children = [
      child({ id: "r", child_name: "run-linked" }),
      child({ id: "rp", child_name: "run-pending", child_host_id: null, hostname: null, agent_version: null, reboot_required: true }),
      child({ id: "s", child_name: "stopped-one", status: "stopped", hostname: null, distribution_version: null }),
      child({ id: "e", child_name: "errored", status: "error", error_message: "disk full", child_host_id: null }),
      child({ id: "c", child_name: "making", status: "creating", child_type: "wsl", child_host_id: null }),
      child({ id: "p", child_name: "queued", status: "pending", child_type: "lxd", child_host_id: null }),
    ];
    const props = makeProps({ childHosts: children });
    render(<HostChildHostsTab {...props} />);

    // Running + linked: stop, restart, update agent, delete.
    const linked = within(rowFor("run-linked"));
    expect(linked.getByText("Running")).toBeInTheDocument();
    expect(linked.getByText("Ubuntu 24.04")).toBeInTheDocument();
    expect(linked.getByText("vm-one.local")).toBeInTheDocument();
    expect(linked.getByText("1.2.3")).toBeInTheDocument();
    expect(linked.getByText("KVM")).toBeInTheDocument();
    fireEvent.click(linked.getByTitle("Stop"));
    expect(props.handleChildHostStop).toHaveBeenCalledWith(children[0]);
    fireEvent.click(linked.getByTitle("Restart"));
    expect(props.handleChildHostRestart).toHaveBeenCalledWith(children[0]);
    fireEvent.click(linked.getByTitle("Update Agent"));
    expect(props.handleChildHostUpdateAgent).toHaveBeenCalledWith(children[0]);
    fireEvent.click(linked.getByTitle("Delete"));
    expect(props.handleChildHostDeleteConfirm).toHaveBeenCalledWith(children[0]);

    // Running but unlinked: pending approval, reboot chip, dash placeholders.
    const pending = within(rowFor("run-pending"));
    expect(pending.getByText("Pending Approval")).toBeInTheDocument();
    expect(pending.getByText("hosts.rebootRequired")).toBeInTheDocument();
    expect(pending.getAllByText("-").length).toBe(2);
    expect(pending.queryByTitle("Update Agent")).toBeNull();

    // Stopped: start + restart, "Not running" hostname.
    const stopped = within(rowFor("stopped-one"));
    expect(stopped.getByText("Stopped")).toBeInTheDocument();
    expect(stopped.getByText("Not running")).toBeInTheDocument();
    expect(stopped.getByText("Ubuntu")).toBeInTheDocument();
    fireEvent.click(stopped.getByTitle("Start"));
    expect(props.handleChildHostStart).toHaveBeenCalledWith(children[2]);
    expect(stopped.queryByTitle("Stop")).toBeNull();

    // Error shows its message.
    const errored = within(rowFor("errored"));
    expect(errored.getByText("Error")).toBeInTheDocument();
    expect(errored.getByText("disk full")).toBeInTheDocument();

    // Creating / pending: cancel instead of delete; unknown status shown raw.
    const making = within(rowFor("making"));
    expect(making.getByText("Creating...")).toBeInTheDocument();
    expect(making.getByTitle("Cancel")).toBeInTheDocument();
    const queued = within(rowFor("queued"));
    expect(queued.getByText("pending")).toBeInTheDocument();
    expect(queued.getByTitle("Cancel")).toBeInTheDocument();
  });

  test("in-flight operations show spinners and disable the row's buttons", () => {
    const children = [
      child({ id: "a", child_name: "starting", status: "stopped" }),
      child({ id: "b", child_name: "stopping", status: "running" }),
      child({ id: "c", child_name: "restarting", status: "running" }),
      child({ id: "d", child_name: "updating", status: "running" }),
      child({ id: "e", child_name: "deleting", status: "running" }),
    ];
    render(
      <HostChildHostsTab
        {...makeProps({
          childHosts: children,
          childHostOperationLoading: {
            a: "start",
            b: "stop",
            c: "restart",
            d: "update-agent",
            e: "delete",
          },
        })}
      />,
    );
    for (const name of ["starting", "stopping", "restarting", "updating", "deleting"]) {
      const row = within(rowFor(name));
      expect(row.getByRole("progressbar")).toBeInTheDocument();
      expect(row.getByTitle("Delete")).toBeDisabled();
    }
  });

  test("hides row actions without the required engine or update permission", () => {
    mockPerm.mockReturnValue(false);
    const children = [
      child({ id: "w", child_name: "wsl-box", child_type: "wsl" }),
      child({ id: "k", child_name: "kvm-box", child_type: "kvm" }),
    ];
    render(
      <HostChildHostsTab
        {...makeProps({ childHosts: children, licenseModules: ["virtualization_engine"] })}
      />,
    );
    expect(within(rowFor("wsl-box")).queryByTitle("Delete")).toBeNull();
    const kvm = within(rowFor("kvm-box"));
    expect(kvm.getByTitle("Delete")).toBeInTheDocument();
    expect(kvm.queryByTitle("Update Agent")).toBeNull();
  });
});
