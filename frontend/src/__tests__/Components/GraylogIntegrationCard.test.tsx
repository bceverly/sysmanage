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

vi.mock("../../Services/permissions", () => ({
  hasPermission: vi.fn(),
  SecurityRoles: {
    ENABLE_GRAYLOG_INTEGRATION: "Enable Graylog Integration",
  },
}));

import axiosInstance from "../../Services/api";
import { hasPermission } from "../../Services/permissions";
import GraylogIntegrationCard from "../../Components/GraylogIntegrationCard";

const m = (fn: unknown) => fn as unknown as ReturnType<typeof vi.fn>;

const servers = [
  {
    id: "g1",
    fqdn: "graylog.local",
    role: "graylog_server",
    package_name: "graylog",
    package_version: "5.2",
    is_active: true,
  },
];

const disabledSettings = {
  enabled: false,
  use_managed_server: true,
  host_id: undefined,
  manual_url: undefined,
  api_token: undefined,
};

beforeEach(() => {
  vi.clearAllMocks();
  errSpy = vi.spyOn(window.console, "error").mockImplementation(() => {});
  m(hasPermission).mockResolvedValue(true);
  m(axiosInstance.get).mockImplementation((url: string) => {
    if (url.includes("graylog-servers"))
      return Promise.resolve({ data: { graylog_servers: servers } });
    if (url.includes("/settings"))
      return Promise.resolve({ data: disabledSettings });
    if (url.includes("/health"))
      return Promise.resolve({ data: { healthy: true, version: "5.2" } });
    return Promise.resolve({ data: {} });
  });
  m(axiosInstance.post).mockResolvedValue({ data: {} });
});

afterEach(() => {
  errSpy.mockRestore();
});

test("renders the card with disabled status after load", async () => {
  render(<GraylogIntegrationCard />);
  expect(await screen.findByText("Graylog Integration")).toBeInTheDocument();
  await waitFor(() =>
    expect(screen.getByText("Disabled")).toBeInTheDocument(),
  );
  expect(m(axiosInstance.get)).toHaveBeenCalledWith(
    "/api/v1/graylog/graylog-servers",
  );
});

test("enabling the integration reveals the managed-server controls", async () => {
  render(<GraylogIntegrationCard />);
  await screen.findByText("Graylog Integration");

  const enableSwitch = screen.getByLabelText(
    "Enable Graylog Integration",
  ) as HTMLInputElement;
  fireEvent.click(enableSwitch);

  await waitFor(() =>
    expect(screen.getByText("Use Managed Server")).toBeInTheDocument(),
  );
});

test("saves settings via the save button", async () => {
  render(<GraylogIntegrationCard />);
  await screen.findByText("Graylog Integration");

  fireEvent.click(screen.getByRole("button", { name: /^Save$/ }));

  await waitFor(() =>
    expect(m(axiosInstance.post)).toHaveBeenCalledWith(
      "/api/v1/graylog/settings",
      expect.any(Object),
    ),
  );
});

test("reloads data when Refresh is clicked", async () => {
  render(<GraylogIntegrationCard />);
  await screen.findByText("Graylog Integration");
  m(axiosInstance.get).mockClear();

  fireEvent.click(screen.getByRole("button", { name: /Refresh/ }));

  await waitFor(() =>
    expect(m(axiosInstance.get)).toHaveBeenCalledWith(
      "/api/v1/graylog/settings",
    ),
  );
});

test("shows an error alert when loading fails", async () => {
  m(axiosInstance.get).mockRejectedValue(new Error("boom"));
  render(<GraylogIntegrationCard />);
  expect(
    await screen.findByText("Failed to load Graylog configuration"),
  ).toBeInTheDocument();
});
