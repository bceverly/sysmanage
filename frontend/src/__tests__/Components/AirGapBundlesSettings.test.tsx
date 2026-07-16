// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { vi, beforeEach, test, expect } from "vitest";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (k: string, f?: string, opts?: Record<string, unknown>) => {
      let s = f || k;
      if (opts) {
        for (const [ok, ov] of Object.entries(opts)) {
          s = s.replace(new RegExp(`{{${ok}}}`, "g"), String(ov));
        }
      }
      return s;
    },
    i18n: { language: "en" },
  }),
}));

vi.mock("@mui/x-data-grid", () => ({
  DataGrid: ({ rows }: { rows: Array<{ id: string; product: string }> }) => (
    <div data-testid="grid">
      {(rows || []).map((r) => (
        <div key={r.id}>{r.product}</div>
      ))}
    </div>
  ),
}));

vi.mock("../../Services/api", () => ({
  default: { get: vi.fn(), post: vi.fn(), put: vi.fn(), delete: vi.fn() },
}));

vi.mock("../../utils/clipboard", () => ({
  copyToClipboard: vi.fn().mockResolvedValue(true),
}));

vi.mock("../../utils/dateUtils", () => ({
  formatUTCTimestamp: (v: string) => v,
}));

import axiosInstance from "../../Services/api";
import AirGapBundlesSettings from "../../Components/AirGapBundlesSettings";

const m = (fn: unknown) => fn as unknown as ReturnType<typeof vi.fn>;

const dockerReady = {
  installed: true,
  running: true,
  version: "24.0.0",
  user_in_group: true,
  process_user: "sysmanage",
  error: null,
  permission_denied: false,
};

const resourcesOk = {
  ram_total_mb: 16000,
  ram_available_mb: 12000,
  swap_total_mb: 2000,
  swap_free_mb: 2000,
  available_mb: 12000,
  disk_free_gb: 100,
  disk_total_gb: 200,
  min_available_mb: 2000,
  min_disk_gb: 20,
  severity: "ok" as const,
  sufficient: true,
  reason: null,
};

const bundle = {
  id: "b1",
  product: "server" as const,
  status: "ready" as const,
  created_at: "2026-01-01T00:00:00Z",
  started_at: null,
  completed_at: "2026-01-01T01:00:00Z",
  size_bytes: 1024,
  error_message: null,
  version: "1.0.0",
};

// The component fires three GETs on mount (bundles / docker-status /
// resource-status).  Route the resolved value by URL.
const routedGet = (url: string) => {
  if (url.includes("docker-status")) return Promise.resolve({ data: dockerReady });
  if (url.includes("resource-status"))
    return Promise.resolve({ data: resourcesOk });
  return Promise.resolve({ data: [bundle] });
};

beforeEach(() => {
  vi.clearAllMocks();
  m(axiosInstance.get).mockImplementation(routedGet);
  m(axiosInstance.post).mockResolvedValue({ data: { token: "tok" } });
  m(axiosInstance.delete).mockResolvedValue({ data: {} });
});

test("renders the bundle list and docker-ready banner", async () => {
  render(<AirGapBundlesSettings />);
  expect(await screen.findByText("Air-Gap Install Bundles")).toBeInTheDocument();
  await waitFor(() => expect(screen.getByTestId("grid")).toBeInTheDocument());
  expect(screen.getByText(/Docker is ready/)).toBeInTheDocument();
  expect(axiosInstance.get).toHaveBeenCalledWith("/api/v1/airgap-bundles");
});

test("queues a server bundle build", async () => {
  render(<AirGapBundlesSettings />);
  await screen.findByText("Air-Gap Install Bundles");

  const buildBtn = await screen.findByRole("button", {
    name: /Build Server Bundle/,
  });
  await waitFor(() => expect(buildBtn).not.toBeDisabled());
  fireEvent.click(buildBtn);

  await waitFor(() =>
    expect(axiosInstance.post).toHaveBeenCalledWith("/api/v1/airgap-bundles", {
      product: "server",
    }),
  );
});

test("refresh button re-fetches bundles", async () => {
  render(<AirGapBundlesSettings />);
  await screen.findByText("Air-Gap Install Bundles");
  m(axiosInstance.get).mockClear();

  const refreshBtn = screen.getByRole("button", { name: /Refresh/ });
  fireEvent.click(refreshBtn);
  await waitFor(() =>
    expect(axiosInstance.get).toHaveBeenCalledWith("/api/v1/airgap-bundles"),
  );
});

test("build buttons disabled when docker is not ready", async () => {
  m(axiosInstance.get).mockImplementation((url: string) => {
    if (url.includes("docker-status"))
      return Promise.resolve({
        data: { ...dockerReady, installed: false, running: false },
      });
    if (url.includes("resource-status"))
      return Promise.resolve({ data: resourcesOk });
    return Promise.resolve({ data: [] });
  });
  render(<AirGapBundlesSettings />);
  await screen.findByText("Air-Gap Install Bundles");
  await waitFor(() =>
    expect(screen.getByText(/Docker is not installed/)).toBeInTheDocument(),
  );
  expect(
    screen.getByRole("button", { name: /Build Server Bundle/ }),
  ).toBeDisabled();
});
