// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

/**
 * The per-engine config-management card (Phase 20.1).
 *
 * The design rule this defends: **an absent engine is not a deficiency.** A
 * host without Puppet is not broken, it simply does not use Puppet. If a
 * not-installed row rendered as an error, the card would become a checklist of
 * things the operator is "missing" and would pressure somebody who wants only
 * Salt into installing four engines. So not-installed is neutral, and licensed
 * adapters are labelled rather than hidden -- hiding them would tell a Puppet
 * shop that Puppet is unsupported when it is actually a paid adapter.
 */

import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { vi, describe, beforeEach, afterEach, test, expect } from "vitest";

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
  getConfigMgmtEngines: vi.fn(),
  installConfigMgmtPrereq: vi.fn(),
  applyConfigProfile: vi.fn(),
}));

import { hasPermission } from "../../Services/permissions";
import {
  getConfigMgmtEngines,
  installConfigMgmtPrereq,
} from "../../Services/configManagementService";
import ConfigManagementEnginesCard from "../../Components/ConfigManagementEnginesCard";

const engine = (over = {}) => ({
  engine: "ansible-core",
  status: "satisfied",
  installed_version: "2.20.1",
  minimum_version: "2.20",
  can_install: false,
  detail: null,
  package_name: "ansible-core",
  requires_license: false,
  ...over,
});

const ready = {
  hostId: "h1",
  canInstall: true,
  isHostActive: true,
  isAgentPrivileged: true,
};

const respond = (...engines: object[]) =>
  vi.mocked(getConfigMgmtEngines).mockResolvedValue({
    host_id: "h1",
    default_engine: "ansible-core",
    engines: engines as never,
  });

describe("ConfigManagementEnginesCard", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(hasPermission).mockResolvedValue(true);
    vi.spyOn(window.console, "error").mockImplementation(() => {});
  });
  afterEach(() => vi.restoreAllMocks());

  test("lists every applicable engine, not just the default", async () => {
    respond(
      engine(),
      engine({ engine: "puppet", status: "missing", requires_license: true }),
      engine({ engine: "chef", status: "missing", requires_license: true }),
    );
    render(<ConfigManagementEnginesCard {...ready} />);
    expect(await screen.findByText("ansible-core")).toBeInTheDocument();
    expect(screen.getByText("puppet")).toBeInTheDocument();
    expect(screen.getByText("chef")).toBeInTheDocument();
  });

  test("a not-installed engine is neutral, never an error", async () => {
    // The load-bearing rule. If this ever renders as an error the card starts
    // pressuring operators to install engines they do not want.
    respond(
      engine({ engine: "chef", status: "missing", installed_version: null }),
    );
    render(<ConfigManagementEnginesCard {...ready} />);
    const chip = await screen.findByText("Not installed");
    expect(chip).toBeInTheDocument();
    expect(chip.closest(".MuiChip-colorError")).toBeNull();
  });

  test("licensed adapters are labelled, not hidden", async () => {
    respond(
      engine({ engine: "puppet", status: "missing", requires_license: true }),
    );
    render(<ConfigManagementEnginesCard {...ready} />);
    expect(await screen.findByText("puppet")).toBeInTheDocument();
    expect(screen.getByText("Enterprise")).toBeInTheDocument();
  });

  test("a licensed engine offers no install button", async () => {
    // Pressing one would 403; the server already refuses to set can_install.
    respond(
      engine({
        engine: "puppet",
        status: "missing",
        can_install: false,
        requires_license: true,
      }),
    );
    render(<ConfigManagementEnginesCard {...ready} />);
    expect(await screen.findByText("puppet")).toBeInTheDocument();
    expect(screen.queryByText("Install")).not.toBeInTheDocument();
  });

  test("a free, installable engine offers an inline install", async () => {
    respond(
      engine({ status: "missing", can_install: true, installed_version: null }),
    );
    render(<ConfigManagementEnginesCard {...ready} />);
    fireEvent.click(await screen.findByText("Install"));
    await waitFor(() =>
      expect(installConfigMgmtPrereq).toHaveBeenCalledWith(
        "h1",
        "ansible-core",
      ),
    );
  });

  test("each row installs ITS OWN engine, not the platform default", async () => {
    // Without the engine argument the server installs the default, so every
    // row's button would silently install ansible-core.
    respond(
      engine({
        engine: "puppet",
        status: "missing",
        can_install: true,
        installed_version: null,
        requires_license: true,
      }),
    );
    render(<ConfigManagementEnginesCard {...ready} />);
    fireEvent.click(await screen.findByText("Install"));
    await waitFor(() =>
      expect(installConfigMgmtPrereq).toHaveBeenCalledWith("h1", "puppet"),
    );
  });

  test("a licensed adapter offers install once the server says it can", async () => {
    // can_install is the server's answer and already accounts for the licence;
    // the card must not second-guess it by keying off requires_license.
    respond(
      engine({
        engine: "chef",
        status: "missing",
        can_install: true,
        installed_version: null,
        requires_license: true,
      }),
    );
    render(<ConfigManagementEnginesCard {...ready} />);
    expect(await screen.findByText("Install")).toBeInTheDocument();
    expect(screen.getByText("Enterprise")).toBeInTheDocument();
  });

  test("the bundled Windows engine reads as included, not installed", async () => {
    respond(
      engine({
        engine: "dsc",
        status: "not_required",
        installed_version: null,
      }),
    );
    render(<ConfigManagementEnginesCard {...ready} />);
    expect(
      await screen.findByText("Included with the agent"),
    ).toBeInTheDocument();
  });

  test("apply is offered when at least one engine is ready", async () => {
    respond(engine());
    render(<ConfigManagementEnginesCard {...ready} />);
    expect(await screen.findByText("Apply profile")).toBeInTheDocument();
  });

  test("apply is NOT offered when nothing is ready", async () => {
    // It could only ever come back as executor_missing.
    respond(engine({ status: "missing", installed_version: null }));
    render(<ConfigManagementEnginesCard {...ready} />);
    expect(await screen.findByText("Not installed")).toBeInTheDocument();
    expect(screen.queryByText("Apply profile")).not.toBeInTheDocument();
  });

  test("apply is hidden without the run-script permission", async () => {
    vi.mocked(hasPermission).mockResolvedValue(false);
    respond(engine());
    render(<ConfigManagementEnginesCard {...ready} />);
    expect(await screen.findByText("Ready")).toBeInTheDocument();
    expect(screen.queryByText("Apply profile")).not.toBeInTheDocument();
  });

  test("install is disabled with a reason on an unprivileged agent", async () => {
    respond(
      engine({ status: "missing", can_install: true, installed_version: null }),
    );
    render(
      <ConfigManagementEnginesCard {...ready} isAgentPrivileged={false} />,
    );
    const button = (await screen.findByText("Install")).closest("button")!;
    expect(button).toBeDisabled();
    expect(button.getAttribute("title")).toBe(
      "Agent not running in privileged mode",
    );
  });

  test("a failed load surfaces an error rather than an empty card", async () => {
    vi.mocked(getConfigMgmtEngines).mockRejectedValue(new Error("boom"));
    render(<ConfigManagementEnginesCard {...ready} />);
    expect(
      await screen.findByText(
        "Failed to load configuration management engines",
      ),
    ).toBeInTheDocument();
  });

  test("a failed install re-enables the row instead of stranding it", async () => {
    respond(
      engine({ status: "missing", can_install: true, installed_version: null }),
    );
    vi.mocked(installConfigMgmtPrereq).mockRejectedValue(new Error("nope"));
    render(<ConfigManagementEnginesCard {...ready} />);
    fireEvent.click(await screen.findByText("Install"));
    expect(
      await screen.findByText(
        "Failed to request installation of the configuration management prerequisite",
      ),
    ).toBeInTheDocument();
    expect(screen.getByText("Install").closest("button")).not.toBeDisabled();
  });
});
