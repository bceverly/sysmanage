// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

/**
 * The config-management prerequisite card (Phase 20.1).
 *
 * The interesting behaviour is not "does it render" -- it is that the card
 * must NOT offer an install button in the three cases where pressing it would
 * be a lie: Windows (the engine ships with the agent), an unsupported
 * platform, and a host that is already ready.  Each of those is asserted
 * separately, because they arrive as different statuses from the server and
 * collapsing them into "no button" in one test would let a regression in any
 * one of them hide behind the other two.
 */

import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { vi, describe, beforeEach, afterEach, test, expect } from "vitest";

// One `t` per module, never per render: the fetch callback lists `t` in its
// deps, so a fresh identity each render is an infinite loop.
vi.mock("react-i18next", () => {
  const t = (key: string, fallback?: string) =>
    typeof fallback === "string" ? fallback : key;
  return { useTranslation: () => ({ t, i18n: { language: "en" } }) };
});

vi.mock("../../Services/permissions", async (orig) => {
  const actual = await orig<typeof import("../../Services/permissions")>();
  return { ...actual, hasPermission: vi.fn() };
});

vi.mock("../../Services/configManagementService", () => ({
  getConfigMgmtPrereq: vi.fn(),
  installConfigMgmtPrereq: vi.fn(),
  // The card renders the apply dialog, which imports from this module.
  applyConfigProfile: vi.fn(),
}));

import { hasPermission } from "../../Services/permissions";
import {
  getConfigMgmtPrereq,
  installConfigMgmtPrereq,
} from "../../Services/configManagementService";
import ConfigManagementPrereqCard from "../../Components/ConfigManagementPrereqCard";

const base = {
  host_id: "h1",
  executor: "ansible-core",
  installed_version: null as string | null,
  minimum_version: "2.20",
  can_install: false,
  detail: null as string | null,
  package_name: null as string | null,
};

const ready = {
  hostId: "h1",
  canInstall: true,
  isHostActive: true,
  isAgentPrivileged: true,
};

const INSTALL_BUTTON = "Install prerequisite";

describe("ConfigManagementPrereqCard", () => {
  // Error-path tests intentionally log to console.error; silence the expected
  // noise without hiding real errors (restored after each test).
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(hasPermission).mockResolvedValue(true);
    vi.spyOn(window.console, "error").mockImplementation(() => {});
  });
  afterEach(() => vi.restoreAllMocks());

  test("a satisfied host shows its version and no install button", async () => {
    vi.mocked(getConfigMgmtPrereq).mockResolvedValue({
      ...base,
      status: "satisfied",
      installed_version: "2.20.1",
      can_install: false,
    });
    render(<ConfigManagementPrereqCard {...ready} />);
    expect(await screen.findByText("Ready")).toBeInTheDocument();
    expect(screen.getByText("2.20.1")).toBeInTheDocument();
    expect(screen.queryByText(INSTALL_BUTTON)).not.toBeInTheDocument();
  });

  test("a bare host offers the install button", async () => {
    vi.mocked(getConfigMgmtPrereq).mockResolvedValue({
      ...base,
      status: "missing",
      can_install: true,
    });
    render(<ConfigManagementPrereqCard {...ready} />);
    expect(await screen.findByText("Not installed")).toBeInTheDocument();
    expect(screen.getByText(INSTALL_BUTTON)).toBeInTheDocument();
  });

  test("Windows says the engine is bundled and offers nothing to press", async () => {
    vi.mocked(getConfigMgmtPrereq).mockResolvedValue({
      ...base,
      executor: "dsc",
      status: "not_required",
      minimum_version: null,
      can_install: false,
    });
    render(<ConfigManagementPrereqCard {...ready} />);
    expect(
      await screen.findByText("Included with the agent"),
    ).toBeInTheDocument();
    expect(screen.queryByText(INSTALL_BUTTON)).not.toBeInTheDocument();
  });

  test("an unsupported platform offers nothing to press", async () => {
    vi.mocked(getConfigMgmtPrereq).mockResolvedValue({
      ...base,
      status: "unsupported",
      can_install: false,
    });
    render(<ConfigManagementPrereqCard {...ready} />);
    expect(
      await screen.findByText("Not available on this platform"),
    ).toBeInTheDocument();
    expect(screen.queryByText(INSTALL_BUTTON)).not.toBeInTheDocument();
  });

  test("a too-old version is distinguished from a missing one", async () => {
    vi.mocked(getConfigMgmtPrereq).mockResolvedValue({
      ...base,
      status: "too_old",
      installed_version: "2.14.2",
      can_install: true,
    });
    render(<ConfigManagementPrereqCard {...ready} />);
    expect(await screen.findByText("Version too old")).toBeInTheDocument();
    expect(screen.getByText("2.14.2")).toBeInTheDocument();
    expect(screen.getByText("2.20")).toBeInTheDocument();
    expect(screen.getByText(INSTALL_BUTTON)).toBeInTheDocument();
  });

  test("without the package permission the button is not rendered at all", async () => {
    vi.mocked(getConfigMgmtPrereq).mockResolvedValue({
      ...base,
      status: "missing",
      can_install: true,
    });
    render(<ConfigManagementPrereqCard {...ready} canInstall={false} />);
    expect(await screen.findByText("Not installed")).toBeInTheDocument();
    expect(screen.queryByText(INSTALL_BUTTON)).not.toBeInTheDocument();
  });

  test("an inactive host renders the button disabled, with the reason", async () => {
    vi.mocked(getConfigMgmtPrereq).mockResolvedValue({
      ...base,
      status: "missing",
      can_install: true,
    });
    render(<ConfigManagementPrereqCard {...ready} isHostActive={false} />);
    const button = (await screen.findByText(INSTALL_BUTTON)).closest("button")!;
    expect(button).toBeDisabled();
    expect(button.getAttribute("title")).toBe("Host is not active");
  });

  test("an unprivileged agent renders the button disabled, with the reason", async () => {
    vi.mocked(getConfigMgmtPrereq).mockResolvedValue({
      ...base,
      status: "missing",
      can_install: true,
    });
    render(<ConfigManagementPrereqCard {...ready} isAgentPrivileged={false} />);
    const button = (await screen.findByText(INSTALL_BUTTON)).closest("button")!;
    expect(button).toBeDisabled();
    expect(button.getAttribute("title")).toBe(
      "Agent not running in privileged mode",
    );
  });

  test("pressing install requests it and reports that it is pending", async () => {
    vi.mocked(getConfigMgmtPrereq).mockResolvedValue({
      ...base,
      status: "missing",
      can_install: true,
    });
    vi.mocked(installConfigMgmtPrereq).mockResolvedValue({
      host_id: "h1",
      queued: true,
      message: "ok",
    });
    render(<ConfigManagementPrereqCard {...ready} />);
    fireEvent.click(await screen.findByText(INSTALL_BUTTON));
    await waitFor(() =>
      expect(installConfigMgmtPrereq).toHaveBeenCalledWith("h1"),
    );
    expect(
      await screen.findByText(
        "Installation requested. This card updates once the host reports back.",
      ),
    ).toBeInTheDocument();
    // Double-pressing would queue a second install for no reason.
    expect(screen.getByText(INSTALL_BUTTON).closest("button")).toBeDisabled();
  });

  test("a failed install request re-enables the button instead of stranding it", async () => {
    vi.mocked(getConfigMgmtPrereq).mockResolvedValue({
      ...base,
      status: "missing",
      can_install: true,
    });
    vi.mocked(installConfigMgmtPrereq).mockRejectedValue(new Error("nope"));
    render(<ConfigManagementPrereqCard {...ready} />);
    fireEvent.click(await screen.findByText(INSTALL_BUTTON));
    expect(
      await screen.findByText(
        "Failed to request installation of the configuration management prerequisite",
      ),
    ).toBeInTheDocument();
    expect(
      screen.getByText(INSTALL_BUTTON).closest("button"),
    ).not.toBeDisabled();
  });

  test("a failed status fetch surfaces an error rather than an empty card", async () => {
    vi.mocked(getConfigMgmtPrereq).mockRejectedValue(new Error("boom"));
    render(<ConfigManagementPrereqCard {...ready} />);
    expect(
      await screen.findByText(
        "Failed to load configuration management prerequisite status",
      ),
    ).toBeInTheDocument();
  });

  describe("the apply-profile affordance", () => {
    const APPLY = "Apply profile";

    test("is offered when the executor is installed", async () => {
      vi.mocked(getConfigMgmtPrereq).mockResolvedValue({
        ...base,
        status: "satisfied",
        installed_version: "2.20.1",
      });
      render(<ConfigManagementPrereqCard {...ready} />);
      expect(await screen.findByText(APPLY)).toBeInTheDocument();
    });

    test("is offered on Windows, where the executor is bundled", async () => {
      // not_required is still a usable host -- dsc.exe ships with the agent.
      vi.mocked(getConfigMgmtPrereq).mockResolvedValue({
        ...base,
        executor: "dsc",
        status: "not_required",
      });
      render(<ConfigManagementPrereqCard {...ready} />);
      expect(await screen.findByText(APPLY)).toBeInTheDocument();
    });

    test("is NOT offered when no executor is installed", async () => {
      // Queuing here could only ever come back as executor_missing, so the
      // button would be an invitation to a guaranteed failure.
      vi.mocked(getConfigMgmtPrereq).mockResolvedValue({
        ...base,
        status: "missing",
        can_install: true,
      });
      render(<ConfigManagementPrereqCard {...ready} />);
      expect(await screen.findByText("Not installed")).toBeInTheDocument();
      expect(screen.queryByText(APPLY)).not.toBeInTheDocument();
    });

    test("is NOT offered on an unsupported platform", async () => {
      vi.mocked(getConfigMgmtPrereq).mockResolvedValue({
        ...base,
        status: "unsupported",
      });
      render(<ConfigManagementPrereqCard {...ready} />);
      expect(
        await screen.findByText("Not available on this platform"),
      ).toBeInTheDocument();
      expect(screen.queryByText(APPLY)).not.toBeInTheDocument();
    });

    test("is hidden without the run-script permission", async () => {
      // The UI gate must match the API's RUN_SCRIPT gate exactly; a looser one
      // here would just render a button that 403s.
      vi.mocked(getConfigMgmtPrereq).mockResolvedValue({
        ...base,
        status: "satisfied",
      });
      vi.mocked(hasPermission).mockResolvedValue(false);
      render(<ConfigManagementPrereqCard {...ready} />);
      expect(await screen.findByText("Ready")).toBeInTheDocument();
      expect(screen.queryByText(APPLY)).not.toBeInTheDocument();
    });

    test("is disabled with a reason on an inactive host", async () => {
      vi.mocked(getConfigMgmtPrereq).mockResolvedValue({
        ...base,
        status: "satisfied",
      });
      render(<ConfigManagementPrereqCard {...ready} isHostActive={false} />);
      const button = (await screen.findByText(APPLY)).closest("button")!;
      expect(button).toBeDisabled();
      expect(button.getAttribute("title")).toBe("Host is not active");
    });
  });
});
