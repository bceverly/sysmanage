// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import React from "react";
import { vi, beforeEach, test, expect } from "vitest";

// A stable `t` (one instance for every render): the component's refresh
// callback depends on it, so a fresh function per render would re-fire the
// mount effect forever.
vi.mock("react-i18next", () => {
  const t = (k: string, f?: string, opts?: Record<string, unknown>) => {
    let s = f || k;
    if (opts) {
      for (const [ok, ov] of Object.entries(opts)) {
        s = s.replace(new RegExp(`{{${ok}}}`, "g"), String(ov));
      }
    }
    return s;
  };
  const value = { t, i18n: { language: "en" } };
  return { useTranslation: () => value };
});

// Render every column through its renderCell / valueGetter so the column
// definitions (chips, formatted sizes, action buttons) are exercised.
interface MockCol {
  field: string;
  renderCell?: (_p: { row: Record<string, unknown> }) => React.ReactNode;
  valueGetter?: (_v: unknown, _row: Record<string, unknown>) => unknown;
}
vi.mock("@mui/x-data-grid", () => ({
  DataGrid: ({
    rows,
    columns,
    getRowId,
  }: {
    rows: Array<Record<string, unknown>>;
    columns: MockCol[];
    getRowId?: (_r: Record<string, unknown>) => string;
  }) => (
    <div data-testid="grid">
      {(rows || []).map((r) => {
        const id = getRowId ? getRowId(r) : String(r.id);
        return (
          <div key={id} data-testid={`row-${id}`}>
            {columns.map((c) => (
              <span key={c.field} data-testid={`${id}-${c.field}`}>
                {c.renderCell
                  ? c.renderCell({ row: r })
                  : String(
                      c.valueGetter
                        ? c.valueGetter(r[c.field], r)
                        : (r[c.field] ?? ""),
                    )}
              </span>
            ))}
          </div>
        );
      })}
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

import { copyToClipboard } from "../../utils/clipboard";
import { within, act } from "@testing-library/react";

const routeWith = (
  docker: Record<string, unknown> | Error,
  resources: Record<string, unknown> | Error,
  bundles: unknown[] | Error,
) => {
  const wrap = (v: unknown) =>
    v instanceof Error ? Promise.reject(v) : Promise.resolve({ data: v });
  m(axiosInstance.get).mockImplementation((url: string) => {
    if (url.includes("docker-status")) return wrap(docker);
    if (url.includes("resource-status")) return wrap(resources);
    return wrap(bundles);
  });
};

test("renders column cells for every bundle shape", async () => {
  routeWith(dockerReady, resourcesOk, [
    bundle,
    {
      ...bundle,
      id: "b2",
      product: "agent",
      status: "building",
      version: null,
      created_at: null,
      completed_at: null,
      size_bytes: null,
    },
    {
      ...bundle,
      id: "b3",
      product: "proplus",
      status: "queued",
      size_bytes: 5 * 1024 * 1024 * 1024,
    },
    { ...bundle, id: "b4", status: "failed", size_bytes: 10 },
  ]);
  render(<AirGapBundlesSettings />);
  await screen.findByTestId("row-b1");
  expect(screen.getByTestId("b1-size_bytes")).toHaveTextContent("1.0 KB");
  expect(screen.getByTestId("b1-version")).toHaveTextContent("1.0.0");
  expect(screen.getByTestId("b1-created_at")).toHaveTextContent(
    "2026-01-01T00:00:00Z",
  );
  expect(screen.getByTestId("b2-size_bytes")).toHaveTextContent("--");
  expect(screen.getByTestId("b2-version")).toHaveTextContent("--");
  expect(screen.getByTestId("b2-created_at")).toHaveTextContent("--");
  expect(screen.getByTestId("b2-completed_at")).toHaveTextContent("--");
  expect(screen.getByTestId("b3-size_bytes")).toHaveTextContent("5.0 GB");
  expect(screen.getByTestId("b4-size_bytes")).toHaveTextContent("10 B");
  expect(screen.getByTestId("b2-status")).toHaveTextContent("building");
  expect(screen.getByTestId("b3-product")).toHaveTextContent("proplus");
  // Only "ready" rows get a download button (2 buttons vs 1).
  expect(
    within(screen.getByTestId("b1-actions")).getAllByRole("button"),
  ).toHaveLength(2);
  expect(
    within(screen.getByTestId("b2-actions")).getAllByRole("button"),
  ).toHaveLength(1);
});

test("download mints a token and clicks a streaming anchor", async () => {
  const clickSpy = vi
    .spyOn(HTMLAnchorElement.prototype, "click")
    .mockImplementation(() => {});
  render(<AirGapBundlesSettings />);
  const actions = await screen.findByTestId("b1-actions");
  fireEvent.click(within(actions).getAllByRole("button")[0]);
  await waitFor(() => expect(clickSpy).toHaveBeenCalled());
  expect(axiosInstance.post).toHaveBeenCalledWith(
    "/api/v1/airgap-bundles/b1/download-token",
  );
  const anchor = clickSpy.mock.instances[0] as unknown as HTMLAnchorElement;
  expect(anchor.download).toBe("sysmanage-server-bundle-1.0.0.iso");
  expect(anchor.href).toContain(
    "/api/v1/airgap-bundles/b1/download-stream?token=tok",
  );
  clickSpy.mockRestore();
});

test("download failure surfaces an error snackbar", async () => {
  m(axiosInstance.post).mockRejectedValue(new Error("x"));
  render(<AirGapBundlesSettings />);
  const actions = await screen.findByTestId("b1-actions");
  fireEvent.click(within(actions).getAllByRole("button")[0]);
  expect(
    await screen.findByText("Failed to download bundle"),
  ).toBeInTheDocument();
});

test("delete confirms, deletes and reports success", async () => {
  vi.spyOn(globalThis, "confirm").mockReturnValue(true);
  render(<AirGapBundlesSettings />);
  const actions = await screen.findByTestId("b1-actions");
  fireEvent.click(within(actions).getAllByRole("button")[1]);
  await waitFor(() =>
    expect(axiosInstance.delete).toHaveBeenCalledWith(
      "/api/v1/airgap-bundles/b1",
    ),
  );
  expect(await screen.findByText("Bundle deleted")).toBeInTheDocument();
});

test("delete is skipped when the user cancels", async () => {
  vi.spyOn(globalThis, "confirm").mockReturnValue(false);
  render(<AirGapBundlesSettings />);
  const actions = await screen.findByTestId("b1-actions");
  fireEvent.click(within(actions).getAllByRole("button")[1]);
  expect(axiosInstance.delete).not.toHaveBeenCalled();
});

test("delete failure shows the server detail", async () => {
  vi.spyOn(globalThis, "confirm").mockReturnValue(true);
  m(axiosInstance.delete).mockRejectedValue({
    response: { data: { detail: "Bundle busy" } },
  });
  render(<AirGapBundlesSettings />);
  const actions = await screen.findByTestId("b1-actions");
  fireEvent.click(within(actions).getAllByRole("button")[1]);
  expect(await screen.findByText("Bundle busy")).toBeInTheDocument();
});

test("build failure falls back to the generic message", async () => {
  m(axiosInstance.post).mockRejectedValue(new Error("x"));
  render(<AirGapBundlesSettings />);
  const btn = await screen.findByRole("button", { name: /Build Pro\+ Bundle/ });
  fireEvent.click(btn);
  expect(await screen.findByText("Failed to queue build")).toBeInTheDocument();
});

test("build success queues the agent bundle and shows a snackbar", async () => {
  render(<AirGapBundlesSettings />);
  const btn = await screen.findByRole("button", { name: /Build Agent Bundle/ });
  await waitFor(() => expect(btn).not.toBeDisabled());
  fireEvent.click(btn);
  expect(
    await screen.findByText("Bundle build queued -- refreshing list"),
  ).toBeInTheDocument();
  expect(axiosInstance.post).toHaveBeenCalledWith("/api/v1/airgap-bundles", {
    product: "agent",
  });
  // Dismiss the snackbar.
  fireEvent.click(screen.getByRole("button", { name: /close/i }));
});

test("load failure shows an error and empty state", async () => {
  routeWith(new Error("d"), new Error("r"), new Error("b"));
  render(<AirGapBundlesSettings />);
  expect(await screen.findByText("Failed to load bundles")).toBeInTheDocument();
  // Docker probe failed -> neutral notice remains.
  expect(
    screen.getByText(/Bundle builds require Docker to be installed/),
  ).toBeInTheDocument();
  expect(screen.getByText(/No bundles yet/)).toBeInTheDocument();
});

test("recent failures list and insufficient-resource banner", async () => {
  routeWith(
    dockerReady,
    {
      ...resourcesOk,
      severity: "insufficient",
      sufficient: false,
      reason: "only 1 GB free",
      swap_free_mb: 0,
      disk_free_gb: 3,
    },
    [{ ...bundle, status: "failed", error_message: "pip exploded\nmore" }],
  );
  render(<AirGapBundlesSettings />);
  expect(await screen.findByText("Recent build failures:")).toBeInTheDocument();
  expect(screen.getByText("server: pip exploded")).toBeInTheDocument();
  expect(
    await screen.findByText(/does not have enough free memory/),
  ).toBeInTheDocument();
  expect(screen.getByText("only 1 GB free")).toBeInTheDocument();
  expect(screen.getByText(/disk free: 3 GB/)).toBeInTheDocument();
  expect(
    screen.getByRole("button", { name: /Build Server Bundle/ }),
  ).toBeDisabled();
  m(axiosInstance.get).mockClear();
  fireEvent.click(screen.getByRole("button", { name: /Re-check resources/ }));
  await waitFor(() =>
    expect(axiosInstance.get).toHaveBeenCalledWith(
      "/api/v1/airgap-bundles/resource-status",
    ),
  );
});

test("low-resource warning banner without optional stats", async () => {
  routeWith(
    dockerReady,
    {
      ...resourcesOk,
      severity: "warn",
      ram_available_mb: null,
      swap_free_mb: null,
      disk_free_gb: null,
    },
    [],
  );
  render(<AirGapBundlesSettings />);
  expect(await screen.findByText(/Low resources/)).toBeInTheDocument();
  expect(screen.getByText("RAM available: -- MB")).toBeInTheDocument();
});

test("permission-denied docker banner offers a copyable group fix", async () => {
  routeWith(
    {
      ...dockerReady,
      user_in_group: false,
      permission_denied: true,
      process_user: "bob",
      error: "permission denied on socket",
    },
    resourcesOk,
    [],
  );
  render(<AirGapBundlesSettings />);
  expect(
    await screen.findByText(/the bob user \(the one running/),
  ).toBeInTheDocument();
  expect(screen.getByText("permission denied on socket")).toBeInTheDocument();
  expect(screen.getByText(/sudo usermod -aG docker bob/)).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Copy to clipboard" }));
  await waitFor(() =>
    expect(copyToClipboard).toHaveBeenCalledWith(
      expect.stringContaining("sudo usermod -aG docker bob"),
    ),
  );
  expect(
    await screen.findByText("Command copied to clipboard"),
  ).toBeInTheDocument();
});

test("copy failure and not-in-group docker banner", async () => {
  m(copyToClipboard).mockResolvedValueOnce(false);
  routeWith({ ...dockerReady, user_in_group: false }, resourcesOk, []);
  render(<AirGapBundlesSettings />);
  expect(
    await screen.findByText(/is not in the docker group/),
  ).toBeInTheDocument();
  expect(
    screen.getByText(/sudo systemctl restart sysmanage/),
  ).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Copy to clipboard" }));
  expect(
    await screen.findByText("Could not access the clipboard"),
  ).toBeInTheDocument();
  m(axiosInstance.get).mockClear();
  fireEvent.click(screen.getByRole("button", { name: /Re-check Docker/ }));
  await waitFor(() =>
    expect(axiosInstance.get).toHaveBeenCalledWith(
      "/api/v1/airgap-bundles/docker-status",
    ),
  );
});

test("docker installed but daemon not running", async () => {
  routeWith({ ...dockerReady, running: false }, resourcesOk, []);
  render(<AirGapBundlesSettings />);
  expect(
    await screen.findByText(/the daemon is not reachable/),
  ).toBeInTheDocument();
  expect(
    screen.getByText("sudo systemctl enable --now docker"),
  ).toBeInTheDocument();
});

test("polls while a bundle is in flight", async () => {
  vi.useFakeTimers({ shouldAdvanceTime: true });
  try {
    routeWith(dockerReady, resourcesOk, [{ ...bundle, status: "queued" }]);
    render(<AirGapBundlesSettings />);
    await screen.findByTestId("row-b1");
    m(axiosInstance.get).mockClear();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(5000);
    });
    expect(axiosInstance.get).toHaveBeenCalledWith("/api/v1/airgap-bundles");
    expect(axiosInstance.get).toHaveBeenCalledWith(
      "/api/v1/airgap-bundles/resource-status",
    );
  } finally {
    vi.useRealTimers();
  }
});
