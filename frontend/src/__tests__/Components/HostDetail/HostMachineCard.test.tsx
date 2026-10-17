// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

import { render, screen, fireEvent, waitFor, act } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { vi, describe, beforeEach, test, expect } from "vitest";

vi.mock("react-i18next", () => {
  const t = (key: string, fallback?: string, opts?: Record<string, unknown>) => {
    let out = typeof fallback === "string" ? fallback : key;
    if (opts) {
      for (const [k, v] of Object.entries(opts)) {
        out = out.replace(`{{${k}}}`, String(v));
      }
    }
    return out;
  };
  return { useTranslation: () => ({ t, i18n: { language: "en" } }) };
});

vi.mock("../../../Services/permissions", () => ({
  hasPermission: vi.fn(),
  SecurityRoles: {
    MANAGE_ASSET_TAGS: "Manage Asset Tags",
    APPROVE_HOST_REGISTRATION: "Approve Host Registration",
  },
}));

vi.mock("../../../Services/machines", () => ({
  getHostMachine: vi.fn(),
  checkAssetTag: vi.fn(),
  setMachineAssetTag: vi.fn(),
  resolveMachineConflict: vi.fn(),
  errorCode: (err: unknown) =>
    (err as { response?: { data?: { detail?: { code?: string } } } })?.response?.data?.detail
      ?.code ?? null,
}));

import { hasPermission } from "../../../Services/permissions";
import {
  getHostMachine,
  checkAssetTag,
  setMachineAssetTag,
  resolveMachineConflict,
} from "../../../Services/machines";
import type { HostMachine, MachineSummary } from "../../../Services/machines";
import HostMachineCard, {
  noMachineReason,
  tagReasonText,
} from "../../../Components/HostDetail/HostMachineCard";

const mockPerm = vi.mocked(hasPermission);
const mockGet = vi.mocked(getHostMachine);
const mockCheck = vi.mocked(checkAssetTag);
const mockSet = vi.mocked(setMachineAssetTag);
const mockResolve = vi.mocked(resolveMachineConflict);

const MACHINE: MachineSummary = {
  id: "m1",
  system_uuid: "4c4c4544-0042-3510-8051-b4c04f4e3732",
  system_serial: "SN-123",
  board_serial: "BRD-9",
  vendor: "Lenovo",
  model: "ThinkPad T480",
  is_virtual: false,
  asset_tag: "IT-0042",
};

const makeData = (over: Partial<HostMachine> = {}): HostMachine => ({
  identity: {
    system_uuid: MACHINE.system_uuid,
    system_serial: MACHINE.system_serial,
    board_serial: MACHINE.board_serial,
    status: { system_uuid: "ran", system_serial: "ran", board_serial: "ran" },
    reported_at: "2026-10-01T00:00:00Z",
  },
  machine: MACHINE,
  other_hosts: [],
  conflict: null,
  ...over,
});

const grant = (...roles: string[]) =>
  mockPerm.mockImplementation(async (role: string) => roles.includes(role));

const renderCard = async () => {
  render(
    <MemoryRouter>
      <HostMachineCard hostId="h1" />
    </MemoryRouter>,
  );
  await screen.findByText("Machine");
  await waitFor(() => expect(screen.queryByRole("progressbar")).not.toBeInTheDocument());
};

const refusal = (code: string) => ({ response: { data: { detail: { code } } } });

describe("HostMachineCard", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    grant();
    mockCheck.mockResolvedValue({ ok: true, reason: null });
  });

  test("shows the machine, its tag and the other operating systems with links", async () => {
    mockGet.mockResolvedValue(
      makeData({
        other_hosts: [
          { id: "h2", fqdn: "win.example.com", platform: "Windows", active: true },
          { id: "h3", fqdn: "obsd.example.com", platform: "OpenBSD", active: false },
        ],
      }),
    );
    await renderCard();
    expect(mockGet).toHaveBeenCalledWith("h1");
    expect(screen.getByTestId("machine-asset-tag")).toHaveTextContent("IT-0042");
    expect(screen.getByText("Lenovo")).toBeInTheDocument();
    expect(screen.getByText("ThinkPad T480")).toBeInTheDocument();
    expect(screen.getByText(MACHINE.system_uuid as string)).toBeInTheDocument();
    expect(screen.getByText("SN-123")).toBeInTheDocument();
    expect(screen.getByText("BRD-9")).toBeInTheDocument();
    expect(screen.getByText("Other operating systems on this machine")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "win.example.com" })).toHaveAttribute("href", "/hosts/h2");
    expect(screen.getByRole("link", { name: "obsd.example.com" })).toHaveAttribute("href", "/hosts/h3");
    expect(screen.getByText("Inactive")).toBeInTheDocument();
    expect(screen.queryByText("Virtual machine")).not.toBeInTheDocument();
  });

  test("says when no other operating system shares the machine", async () => {
    mockGet.mockResolvedValue(makeData({ machine: { ...MACHINE, asset_tag: null } }));
    await renderCard();
    expect(screen.getByText("No asset tag")).toBeInTheDocument();
    expect(
      screen.getByText("No other operating system on this machine has reported in."),
    ).toBeInTheDocument();
  });

  test("shows the virtual machine chip", async () => {
    mockGet.mockResolvedValue(makeData({ machine: { ...MACHINE, is_virtual: true } }));
    await renderCard();
    expect(screen.getByText("Virtual machine")).toBeInTheDocument();
  });

  test.each([
    [{ system_uuid: "unprivileged" as const }, "2026-10-01T00:00:00Z", /cannot use sudo/],
    // A sudo-privileged packaged agent whose sudo rules predate the identity
    // reads: say what to do, not "needs privileged mode" (2026-10-17).
    [{ system_uuid: "needs_sudo_rule" as const }, "2026-10-01T00:00:00Z", /Upgrade the agent package/],
    [{ system_uuid: "placeholder" as const }, "2026-10-01T00:00:00Z", /placeholder UUID/],
    [{ system_uuid: "failed" as const }, "2026-10-01T00:00:00Z", /read failed/],
    [
      { system_uuid: "absent" as const, system_serial: "absent" as const },
      "2026-10-01T00:00:00Z",
      /does not expose/,
    ],
    [{}, null, /has not reported/],
    [{ system_uuid: "ran" as const }, "2026-10-01T00:00:00Z", /not linked to a machine yet/],
  ])("explains a missing machine (%o)", async (status, reportedAt, text) => {
    mockGet.mockResolvedValue(
      makeData({
        machine: null,
        identity: {
          system_uuid: null,
          system_serial: null,
          board_serial: null,
          status,
          reported_at: reportedAt,
        },
      }),
    );
    await renderCard();
    expect(screen.getByText("No machine identified")).toBeInTheDocument();
    expect(screen.getByText(text)).toBeInTheDocument();
    expect(screen.queryByTestId("machine-asset-tag")).not.toBeInTheDocument();
  });

  test("noMachineReason prefers placeholder over unprivileged", () => {
    expect(
      noMachineReason({
        system_uuid: null,
        system_serial: null,
        board_serial: null,
        status: { system_uuid: "placeholder", system_serial: "unprivileged" },
        reported_at: "x",
      }),
    ).toBe("placeholder");
  });

  test("tagReasonText covers every reason and unknown codes", () => {
    const t = ((_k: string, f: string, o?: { code?: string }) =>
      o?.code ? f.replace("{{code}}", o.code) : f) as never;
    expect(tagReasonText(t, "empty")).toMatch(/Enter an asset tag/);
    expect(tagReasonText(t, "too_long")).toMatch(/too long/);
    expect(tagReasonText(t, "bad_characters")).toMatch(/not allowed/);
    expect(tagReasonText(t, "does_not_match_scheme")).toMatch(/scheme/);
    expect(tagReasonText(t, "scheme_timeout")).toMatch(/too long to check/);
    expect(tagReasonText(t, "duplicate")).toMatch(/Another machine/);
    expect(tagReasonText(t, "weird")).toMatch(/\(weird\)/);
  });

  test("shows a load failure", async () => {
    mockGet.mockRejectedValue(new Error("boom"));
    await renderCard();
    expect(screen.getByText("The machine could not be loaded.")).toBeInTheDocument();
  });

  test("is read-only without the roles", async () => {
    mockGet.mockResolvedValue(
      makeData({ conflict: { reason: "virtual_clone", machine: MACHINE } }),
    );
    await renderCard();
    await waitFor(() => expect(mockPerm).toHaveBeenCalledTimes(2));
    expect(screen.getByText(/usually a clone that kept its UUID/)).toBeInTheDocument();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  test("edits the tag with an entry-time check, then saves", async () => {
    grant("Manage Asset Tags");
    mockGet.mockResolvedValue(makeData());
    mockCheck.mockImplementation(async (tag: string) =>
      tag === "IT-1" ? { ok: false, reason: "duplicate" } : { ok: true, reason: null },
    );
    mockSet.mockResolvedValue({ machine_id: "m1", asset_tag: "IT-0099" });
    await renderCard();

    await act(async () => {
      fireEvent.click(await screen.findByRole("button", { name: "Change" }));
    });
    const input = screen.getByLabelText("Asset tag", { selector: "input" });
    await waitFor(() => expect(mockCheck).toHaveBeenCalledWith("IT-0042", "m1"));

    await act(async () => {
      fireEvent.change(input, { target: { value: "IT-1" } });
    });
    expect(await screen.findByText("Another machine already has this asset tag.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Save" })).toBeDisabled();

    await act(async () => {
      fireEvent.change(input, { target: { value: "IT-0099" } });
    });
    await waitFor(() =>
      expect(screen.queryByText("Another machine already has this asset tag.")).not.toBeInTheDocument(),
    );
    await waitFor(() => expect(screen.getByRole("button", { name: "Save" })).toBeEnabled());

    mockGet.mockResolvedValue(makeData({ machine: { ...MACHINE, asset_tag: "IT-0099" } }));
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Save" }));
    });
    expect(mockSet).toHaveBeenCalledWith("m1", "IT-0099");
    await waitFor(() =>
      expect(screen.getByTestId("machine-asset-tag")).toHaveTextContent("IT-0099"),
    );
    expect(screen.queryByRole("button", { name: "Save" })).not.toBeInTheDocument();
  });

  test("shows the server's refusal code on save", async () => {
    grant("Manage Asset Tags");
    mockGet.mockResolvedValue(makeData({ machine: { ...MACHINE, asset_tag: null } }));
    mockSet.mockRejectedValue(refusal("does_not_match_scheme"));
    await renderCard();

    await act(async () => {
      fireEvent.click(await screen.findByRole("button", { name: "Set asset tag" }));
    });
    const input = screen.getByLabelText("Asset tag", { selector: "input" });
    await act(async () => {
      fireEvent.change(input, { target: { value: "X1" } });
    });
    await waitFor(() => expect(screen.getByRole("button", { name: "Save" })).toBeEnabled());
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Save" }));
    });
    expect(
      await screen.findByText("The asset tag does not match the asset tag scheme."),
    ).toBeInTheDocument();
  });

  test("shows a generic error when the save fails without a code, and cancels", async () => {
    grant("Manage Asset Tags");
    mockGet.mockResolvedValue(makeData());
    mockSet.mockRejectedValue(new Error("network"));
    await renderCard();
    await act(async () => {
      fireEvent.click(await screen.findByRole("button", { name: "Change" }));
    });
    await waitFor(() => expect(screen.getByRole("button", { name: "Save" })).toBeEnabled());
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Save" }));
    });
    expect(await screen.findByText("The asset tag could not be saved.")).toBeInTheDocument();
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    });
    expect(screen.getByRole("button", { name: "Change" })).toBeInTheDocument();
  });

  test("clears the tag", async () => {
    grant("Manage Asset Tags");
    mockGet.mockResolvedValue(makeData());
    mockSet.mockResolvedValue({ machine_id: "m1", asset_tag: null });
    await renderCard();
    const clear = await screen.findByRole("button", { name: "Clear" });
    mockGet.mockResolvedValue(makeData({ machine: { ...MACHINE, asset_tag: null } }));
    await act(async () => {
      fireEvent.click(clear);
    });
    expect(mockSet).toHaveBeenCalledWith("m1", null);
    expect(await screen.findByText("No asset tag")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Clear" })).not.toBeInTheDocument();
  });

  test("shows a refusal when clearing fails", async () => {
    grant("Manage Asset Tags");
    mockGet.mockResolvedValue(makeData());
    mockSet.mockRejectedValue(refusal("empty"));
    await renderCard();
    await act(async () => {
      fireEvent.click(await screen.findByRole("button", { name: "Clear" }));
    });
    expect(await screen.findByText("Enter an asset tag.")).toBeInTheDocument();
  });

  test.each([
    ["Same machine", "same"],
    ["Different machine", "different"],
  ])("resolves a conflict as %s and reloads", async (label, decision) => {
    grant("Approve Host Registration");
    mockGet.mockResolvedValue(
      makeData({ conflict: { reason: "serial_mismatch", machine: MACHINE } }),
    );
    mockResolve.mockResolvedValue(MACHINE);
    await renderCard();
    expect(screen.getByText(/same system UUID but a different serial/)).toBeInTheDocument();
    const button = await screen.findByRole("button", { name: label });
    mockGet.mockResolvedValue(makeData());
    await act(async () => {
      fireEvent.click(button);
    });
    expect(mockResolve).toHaveBeenCalledWith("h1", decision);
    await waitFor(() =>
      expect(screen.queryByText("Machine identity conflict")).not.toBeInTheDocument(),
    );
    expect(mockGet).toHaveBeenCalledTimes(2);
    expect(screen.queryByRole("button", { name: "Change" })).not.toBeInTheDocument();
  });

  test("shows an error when resolving fails", async () => {
    grant("Approve Host Registration");
    mockGet.mockResolvedValue(
      makeData({ conflict: { reason: "virtual_clone", machine: MACHINE } }),
    );
    mockResolve.mockRejectedValueOnce(refusal("not_in_conflict"));
    mockResolve.mockRejectedValueOnce(new Error("x"));
    await renderCard();
    await act(async () => {
      fireEvent.click(await screen.findByRole("button", { name: "Same machine" }));
    });
    expect(
      await screen.findByText("The conflict could not be resolved (not_in_conflict)."),
    ).toBeInTheDocument();
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Different machine" }));
    });
    expect(await screen.findByText("The conflict could not be resolved.")).toBeInTheDocument();
  });
});
