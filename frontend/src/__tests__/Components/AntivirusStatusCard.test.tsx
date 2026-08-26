// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { vi, describe, beforeEach, afterEach, test, expect } from "vitest";

// One `t` per module, never per render.  This card's fetch effect lists `t`
// in its deps, so a per-render identity would loop forever.
vi.mock("react-i18next", () => {
  const t = (key: string, fallback?: string) =>
    typeof fallback === "string" ? fallback : key;
  return { useTranslation: () => ({ t, i18n: { language: "en" } }) };
});

vi.mock("../../Services/antivirusService", () => ({
  getAntivirusStatus: vi.fn(),
}));

import { getAntivirusStatus } from "../../Services/antivirusService";
import AntivirusStatusCard from "../../Components/AntivirusStatusCard";

const DEPLOYED = {
  id: "a1",
  host_id: "h1",
  software_name: "clamav",
  install_path: "/usr/bin/clamscan",
  version: "1.0.5",
  enabled: true,
  last_updated: "2026-08-01T00:00:00Z",
};

/** Everything permitted and the host healthy -- the happy baseline. */
const ready = {
  hostId: "h1",
  canDeployAntivirus: true,
  canRemoveAntivirus: true,
  canEnableAntivirus: true,
  canDisableAntivirus: true,
  isHostActive: true,
  isAgentPrivileged: true,
  hasOsDefault: true,
};

describe("AntivirusStatusCard", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(getAntivirusStatus).mockResolvedValue(DEPLOYED);
    vi.spyOn(globalThis.console, "error").mockImplementation(() => undefined);
  });

  afterEach(() => vi.restoreAllMocks());

  test("renders the detected antivirus details", async () => {
    render(<AntivirusStatusCard {...ready} onDeployAntivirus={vi.fn()} />);
    expect(await screen.findByText("clamav")).toBeInTheDocument();
    expect(screen.getByText("1.0.5")).toBeInTheDocument();
    expect(screen.getByText("/usr/bin/clamscan")).toBeInTheDocument();
    expect(screen.getByText("Enabled")).toBeInTheDocument();
  });

  test("shows the disabled chip when antivirus is present but off", async () => {
    vi.mocked(getAntivirusStatus).mockResolvedValue({
      ...DEPLOYED,
      enabled: false,
    });
    render(<AntivirusStatusCard {...ready} />);
    expect(await screen.findByText("Disabled")).toBeInTheDocument();
  });

  test("shows the unknown chip when the enabled flag is absent", async () => {
    vi.mocked(getAntivirusStatus).mockResolvedValue({
      ...DEPLOYED,
      enabled: null,
    });
    render(<AntivirusStatusCard {...ready} />);
    expect(await screen.findByText("Unknown")).toBeInTheDocument();
  });

  test("renders the empty state when nothing is installed", async () => {
    vi.mocked(getAntivirusStatus).mockResolvedValue(null);
    render(<AntivirusStatusCard {...ready} />);
    expect(
      await screen.findByText("No antivirus software detected"),
    ).toBeInTheDocument();
  });

  test("reports a fetch failure", async () => {
    vi.mocked(getAntivirusStatus).mockRejectedValue(new Error("down"));
    render(<AntivirusStatusCard {...ready} />);
    expect(
      await screen.findByText("Failed to load antivirus status"),
    ).toBeInTheDocument();
  });

  test("no hostId means no request at all", async () => {
    render(<AntivirusStatusCard {...ready} hostId="" />);
    await waitFor(() => expect(getAntivirusStatus).not.toHaveBeenCalled());
  });

  test("deploy is disabled while antivirus is already installed", async () => {
    render(<AntivirusStatusCard {...ready} onDeployAntivirus={vi.fn()} />);
    await screen.findByText("clamav");
    const deploy = screen.getByRole("button", { name: "Deploy Antivirus" });
    expect(deploy).toBeDisabled();
    expect(deploy).toHaveAttribute("title", "Antivirus already deployed");
  });

  test("deploy is offered when nothing is installed", async () => {
    vi.mocked(getAntivirusStatus).mockResolvedValue(null);
    const onDeploy = vi.fn();
    render(<AntivirusStatusCard {...ready} onDeployAntivirus={onDeploy} />);
    await screen.findByText("No antivirus software detected");
    const deploy = screen.getByRole("button", { name: "Deploy Antivirus" });
    expect(deploy).not.toBeDisabled();
    fireEvent.click(deploy);
    expect(onDeploy).toHaveBeenCalled();
  });

  test("an unprivileged agent blocks deploy and says why", async () => {
    vi.mocked(getAntivirusStatus).mockResolvedValue(null);
    render(
      <AntivirusStatusCard
        {...ready}
        isAgentPrivileged={false}
        onDeployAntivirus={vi.fn()}
      />,
    );
    await screen.findByText("No antivirus software detected");
    const deploy = screen.getByRole("button", { name: "Deploy Antivirus" });
    expect(deploy).toBeDisabled();
    expect(deploy).toHaveAttribute(
      "title",
      "Agent not running in privileged mode",
    );
  });

  test("an inactive host blocks deploy and says why", async () => {
    vi.mocked(getAntivirusStatus).mockResolvedValue(null);
    render(
      <AntivirusStatusCard
        {...ready}
        isHostActive={false}
        onDeployAntivirus={vi.fn()}
      />,
    );
    await screen.findByText("No antivirus software detected");
    expect(
      screen.getByRole("button", { name: "Deploy Antivirus" }),
    ).toHaveAttribute("title", "Host is not active");
  });

  test("no OS default blocks deploy and says why", async () => {
    vi.mocked(getAntivirusStatus).mockResolvedValue(null);
    render(
      <AntivirusStatusCard
        {...ready}
        hasOsDefault={false}
        onDeployAntivirus={vi.fn()}
      />,
    );
    await screen.findByText("No antivirus software detected");
    expect(
      screen.getByRole("button", { name: "Deploy Antivirus" }),
    ).toHaveAttribute(
      "title",
      "No antivirus default configured for this OS",
    );
  });

  test("remove is offered once something is installed", async () => {
    const onRemove = vi.fn();
    render(<AntivirusStatusCard {...ready} onRemoveAntivirus={onRemove} />);
    await screen.findByText("clamav");
    fireEvent.click(screen.getByRole("button", { name: "Remove Antivirus" }));
    expect(onRemove).toHaveBeenCalled();
  });

  test("enable is disabled while antivirus is already enabled", async () => {
    render(<AntivirusStatusCard {...ready} onEnableAntivirus={vi.fn()} />);
    await screen.findByText("clamav");
    expect(
      screen.getByRole("button", { name: "Enable Antivirus" }),
    ).toBeDisabled();
  });

  test("disable is disabled once antivirus is already off", async () => {
    vi.mocked(getAntivirusStatus).mockResolvedValue({
      ...DEPLOYED,
      enabled: false,
    });
    render(<AntivirusStatusCard {...ready} onDisableAntivirus={vi.fn()} />);
    await screen.findByText("Disabled");
    expect(
      screen.getByRole("button", { name: "Disable Antivirus" }),
    ).toBeDisabled();
  });

  test("buttons the caller has no permission for are not rendered", async () => {
    render(
      <AntivirusStatusCard
        hostId="h1"
        onDeployAntivirus={vi.fn()}
        onRemoveAntivirus={vi.fn()}
      />,
    );
    await screen.findByText("clamav");
    // Permission flags default to false, so nothing actionable appears.
    expect(
      screen.queryByRole("button", { name: "Deploy Antivirus" }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Remove Antivirus" }),
    ).not.toBeInTheDocument();
  });

  test("bumping refreshTrigger re-reads the status", async () => {
    const { rerender } = render(<AntivirusStatusCard {...ready} />);
    await screen.findByText("clamav");
    expect(getAntivirusStatus).toHaveBeenCalledTimes(1);
    rerender(<AntivirusStatusCard {...ready} refreshTrigger={1} />);
    await waitFor(() => expect(getAntivirusStatus).toHaveBeenCalledTimes(2));
  });
});
