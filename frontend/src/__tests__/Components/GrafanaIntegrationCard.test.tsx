// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { vi, describe, beforeEach, afterEach, test, expect } from "vitest";

// One `t` per module, never per render -- see UserDetail.test.tsx.
vi.mock("react-i18next", () => {
  const t = (key: string, fallback?: string) =>
    typeof fallback === "string" ? fallback : key;
  return { useTranslation: () => ({ t, i18n: { language: "en" } }) };
});

vi.mock("../../Services/api", () => ({
  default: { get: vi.fn(), post: vi.fn() },
}));

vi.mock("../../Services/permissions", async (orig) => {
  const actual = await orig<typeof import("../../Services/permissions")>();
  return { ...actual, hasPermission: vi.fn() };
});

import axiosInstance from "../../Services/api";
import { hasPermission } from "../../Services/permissions";
import GrafanaIntegrationCard from "../../Components/GrafanaIntegrationCard";

const SERVER = {
  id: "h1",
  fqdn: "grafana.invalid",
  role: "grafana",
  package_name: "grafana",
  package_version: "11.0.0",
  is_active: true,
};

const settings = (over: Record<string, unknown> = {}) => ({
  enabled: true,
  use_managed_server: true,
  host_id: "h1",
  ...over,
});

/** Route the two GETs the card issues on mount. */
const routeGets = (
  servers: unknown[] = [SERVER],
  s: Record<string, unknown> = settings(),
) =>
  vi.mocked(axiosInstance.get).mockImplementation(async (url: string) => {
    if (url.includes("grafana-servers")) return { data: { grafana_servers: servers } };
    if (url.includes("/settings")) return { data: s };
    if (url.includes("/health")) return { data: { healthy: true, version: "11.0.0" } };
    return { data: {} };
  });

describe("GrafanaIntegrationCard", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    routeGets();
    vi.mocked(axiosInstance.post).mockResolvedValue({ data: {} });
    vi.mocked(hasPermission).mockResolvedValue(true);
  });

  afterEach(() => vi.restoreAllMocks());

  test("renders the card once loaded", async () => {
    render(<GrafanaIntegrationCard />);
    expect(await screen.findByText("Grafana Integration")).toBeInTheDocument();
  });

  test("reports a load failure with the server's detail", async () => {
    vi.mocked(axiosInstance.get).mockRejectedValue({
      isAxiosError: true,
      response: { data: { detail: "grafana module not licensed" } },
    });
    render(<GrafanaIntegrationCard />);
    expect(
      await screen.findByText("grafana module not licensed"),
    ).toBeInTheDocument();
  });

  test("falls back to a generic load message without a detail", async () => {
    vi.mocked(axiosInstance.get).mockRejectedValue(new Error("offline"));
    render(<GrafanaIntegrationCard />);
    expect(
      await screen.findByText("Failed to load Grafana configuration"),
    ).toBeInTheDocument();
  });

  test("shows Disabled while the integration is off", async () => {
    routeGets([SERVER], settings({ enabled: false }));
    render(<GrafanaIntegrationCard />);
    expect(await screen.findByText("Disabled")).toBeInTheDocument();
  });

  test("shows Unknown when enabled but not yet health-checked", async () => {
    render(<GrafanaIntegrationCard />);
    await screen.findByText("Grafana Integration");
    // The card does not auto-probe, so status stays Unknown until asked.
    expect(screen.getByText("Unknown")).toBeInTheDocument();
  });

  test("a health check reports a healthy server and its version", async () => {
    render(<GrafanaIntegrationCard />);
    await screen.findByText("Grafana Integration");
    fireEvent.click(screen.getByRole("button", { name: "Check Health" }));
    expect(await screen.findByText("Healthy")).toBeInTheDocument();
    // Rendered twice: the health chip and the server list entry.
    expect(screen.getAllByText("v11.0.0").length).toBeGreaterThan(0);
  });

  test("a failed health check reports unhealthy with the reason", async () => {
    render(<GrafanaIntegrationCard />);
    await screen.findByText("Grafana Integration");
    vi.mocked(axiosInstance.get).mockRejectedValue({
      isAxiosError: true,
      response: { data: { detail: "connection refused" } },
    });
    fireEvent.click(screen.getByRole("button", { name: "Check Health" }));
    expect(await screen.findByText("Unhealthy")).toBeInTheDocument();
    expect(await screen.findByText(/connection refused/)).toBeInTheDocument();
  });

  test("health check is unavailable while the integration is off", async () => {
    routeGets([SERVER], settings({ enabled: false }));
    render(<GrafanaIntegrationCard />);
    await screen.findByText("Disabled");
    expect(
      screen.getByRole("button", { name: "Check Health" }),
    ).toBeDisabled();
  });

  test("saving posts the current settings", async () => {
    render(<GrafanaIntegrationCard />);
    await screen.findByText("Grafana Integration");
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() =>
      expect(axiosInstance.post).toHaveBeenCalledWith(
        "/api/v1/grafana/settings",
        expect.objectContaining({ enabled: true }),
      ),
    );
  });

  test("surfaces the server's detail when a save is refused", async () => {
    vi.mocked(axiosInstance.post).mockRejectedValue({
      isAxiosError: true,
      response: { data: { detail: "api key rejected" } },
    });
    render(<GrafanaIntegrationCard />);
    await screen.findByText("Grafana Integration");
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(await screen.findByText("api key rejected")).toBeInTheDocument();
  });

  test("without the enable permission the save control is hidden", async () => {
    vi.mocked(hasPermission).mockResolvedValue(false);
    render(<GrafanaIntegrationCard />);
    await screen.findByText("Grafana Integration");
    expect(
      screen.queryByRole("button", { name: "Save" }),
    ).not.toBeInTheDocument();
  });

  test("an empty server list says so", async () => {
    routeGets([], settings({ host_id: undefined }));
    render(<GrafanaIntegrationCard />);
    await screen.findByText("Grafana Integration");
    // The placeholder lives in a MenuItem, which only mounts once the Select
    // is opened.
    // The MUI Select label is not associated with a form control, so go
    // via the combobox role.
    fireEvent.mouseDown(screen.getAllByRole("combobox")[0]);
    expect(
      await screen.findByText("No Grafana servers found"),
    ).toBeInTheDocument();
  });

  test("toggling the integration off flips the status text", async () => {
    render(<GrafanaIntegrationCard />);
    await screen.findByText("Grafana Integration");
    fireEvent.click(screen.getByLabelText("Enable Grafana Integration"));
    expect(await screen.findByText("Disabled")).toBeInTheDocument();
  });

  test("refresh re-reads servers and settings", async () => {
    render(<GrafanaIntegrationCard />);
    await screen.findByText("Grafana Integration");
    vi.mocked(axiosInstance.get).mockClear();
    routeGets();
    fireEvent.click(screen.getByRole("button", { name: /Refresh/ }));
    await waitFor(() =>
      expect(axiosInstance.get).toHaveBeenCalledWith(
        "/api/v1/grafana/settings",
      ),
    );
  });
});
