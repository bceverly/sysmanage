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

vi.mock("../../Services/openBAOService", () => ({
  openBAOService: {
    getStatus: vi.fn(),
    getConfig: vi.fn(),
    start: vi.fn(),
    stop: vi.fn(),
    seal: vi.fn(),
    unseal: vi.fn(),
  },
}));

import { openBAOService } from "../../Services/openBAOService";
import OpenBAOStatusCard from "../../Components/OpenBAOStatusCard";

const m = (fn: unknown) => fn as unknown as ReturnType<typeof vi.fn>;

const runningStatus = {
  running: true,
  status: "running",
  message: "ok",
  pid: 1234,
  server_url: "http://localhost:8200",
  health: { version: "2.5.4", cluster: "vault" },
  recent_logs: ["log line one", "log line two"],
  sealed: false,
};

const config = {
  enabled: true,
  url: "http://localhost:8200",
  mount_path: "secret",
  timeout: 30,
  verify_ssl: false,
  dev_mode: true,
  has_token: true,
};

beforeEach(() => {
  vi.clearAllMocks();
  errSpy = vi.spyOn(window.console, "error").mockImplementation(() => {});
  m(openBAOService.getStatus).mockResolvedValue(runningStatus);
  m(openBAOService.getConfig).mockResolvedValue(config);
  m(openBAOService.start).mockResolvedValue({
    success: true,
    message: "started",
    status: runningStatus,
  });
  m(openBAOService.stop).mockResolvedValue({
    success: true,
    message: "stopped",
    status: { ...runningStatus, running: false },
  });
  m(openBAOService.seal).mockResolvedValue({
    success: true,
    message: "sealed",
    status: { ...runningStatus, sealed: true },
  });
  m(openBAOService.unseal).mockResolvedValue({
    success: true,
    message: "unsealed",
    status: runningStatus,
  });
});

afterEach(() => {
  errSpy.mockRestore();
});

test("renders status, config details and running state", async () => {
  render(<OpenBAOStatusCard />);

  expect(await screen.findByText("OpenBAO Vault")).toBeInTheDocument();
  await waitFor(() =>
    expect(screen.getByText("http://localhost:8200")).toBeInTheDocument(),
  );
  expect(screen.getByText("Running")).toBeInTheDocument();
  expect(screen.getByText("1234")).toBeInTheDocument();
  expect(m(openBAOService.getStatus)).toHaveBeenCalled();
  expect(m(openBAOService.getConfig)).toHaveBeenCalled();
});

test("stops the vault via the Stop button", async () => {
  render(<OpenBAOStatusCard />);
  await screen.findByText("OpenBAO Vault");

  fireEvent.click(screen.getByText("Stop"));

  await waitFor(() => expect(m(openBAOService.stop)).toHaveBeenCalled());
});

test("seals the vault via the Seal button", async () => {
  render(<OpenBAOStatusCard />);
  await screen.findByText("OpenBAO Vault");

  fireEvent.click(screen.getByText("Seal"));

  await waitFor(() => expect(m(openBAOService.seal)).toHaveBeenCalled());
});

test("refresh button reloads data", async () => {
  render(<OpenBAOStatusCard />);
  // The header renders during loading; wait for the Refresh button (which only
  // appears once the async load resolves) rather than racing the spinner.
  const refreshButton = await screen.findByText("Refresh");

  m(openBAOService.getStatus).mockClear();
  fireEvent.click(refreshButton);

  await waitFor(() => expect(m(openBAOService.getStatus)).toHaveBeenCalled());
});

test("toggles the recent logs panel", async () => {
  render(<OpenBAOStatusCard />);
  await screen.findByText("OpenBAO Vault");

  fireEvent.click(screen.getByText("Show Logs"));

  await waitFor(() =>
    expect(screen.getByText("log line one")).toBeInTheDocument(),
  );
});

test("shows an error alert when loading fails", async () => {
  m(openBAOService.getStatus).mockRejectedValue(new Error("boom"));
  m(openBAOService.getConfig).mockRejectedValue(new Error("boom"));
  render(<OpenBAOStatusCard />);
  expect(
    await screen.findByText("Failed to load OpenBAO status"),
  ).toBeInTheDocument();
});
