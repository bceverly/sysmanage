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

vi.mock("@mui/x-data-grid", () => ({
  DataGrid: ({
    rows,
    columns,
  }: { rows?: any[]; columns?: any[] }) => (
    <div data-testid="grid">
      {(rows ?? []).map((row, i) => (
        <div key={String(row.id ?? i)} data-testid="row">
          {(columns ?? []).map((c) => (
            <span key={c.field}>
              {(() => {
                if (c.renderCell) return c.renderCell({ row });
                if (c.valueGetter)
                  return String(c.valueGetter(row[c.field], row) ?? "");
                return String(row[c.field] ?? "");
              })()}
            </span>
          ))}
        </div>
      ))}
    </div>
  ),
  GridColDef: {},
  GridRenderCellParams: {},
}));


// SearchBox is a shared wrapper that does not pass its placeholder through to
// a plain input; stub it so this test exercises the panel's filtering rather
// than the search widget's internals.
vi.mock("../../Components/SearchBox", () => ({
  default: ({ searchTerm, setSearchTerm }: any) => (
    <input
      aria-label="search"
      value={searchTerm}
      onChange={(e) => setSearchTerm(e.target.value)}
    />
  ),
}));

vi.mock("../../Services/processes", () => ({
  doGetHostProcesses: vi.fn(),
  doRefreshHostProcesses: vi.fn(),
  doKillHostProcess: vi.fn(),
}));

vi.mock("../../Services/permissions", async (orig) => {
  const actual = await orig<typeof import("../../Services/permissions")>();
  return { ...actual, hasPermission: vi.fn() };
});

import {
  doGetHostProcesses,
  doRefreshHostProcesses,
  doKillHostProcess,
} from "../../Services/processes";
import { hasPermission } from "../../Services/permissions";
import ProcessesPanel from "../../Components/ProcessesPanel";

const proc = (over: Record<string, unknown> = {}) => ({
  id: "p1",
  pid: 4242,
  parent_pid: 1,
  process_name: "nginx",
  username: "www-data",
  status: "running",
  cpu_percent: 1.5,
  memory_percent: 2.5,
  memory_rss_bytes: 1024 * 1024,
  command_line: "nginx -g daemon off;",
  started_at: "2026-08-01T00:00:00Z",
  collected_at: "2026-08-01T00:05:00Z",
  ...over,
});

const props = (over: Record<string, unknown> = {}) => ({
  hostId: "h1",
  hostActive: true,
  isAgentPrivileged: true,
  ...over,
});

describe("ProcessesPanel", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(doGetHostProcesses).mockResolvedValue([
      proc(),
      proc({ id: "p2", pid: 99, process_name: "sshd", username: "root" }),
    ] as never);
    vi.mocked(doRefreshHostProcesses).mockResolvedValue({
      message: "Refresh queued",
    } as never);
    vi.mocked(doKillHostProcess).mockResolvedValue({
      message: "Kill queued",
    } as never);
    vi.mocked(hasPermission).mockResolvedValue(true);
  });

  afterEach(() => vi.restoreAllMocks());

  test("lists the host's processes", async () => {
    render(<ProcessesPanel {...props()} />);
    expect(await screen.findByText("nginx")).toBeInTheDocument();
    expect(screen.getByText("sshd")).toBeInTheDocument();
  });

  test("reports a load failure", async () => {
    vi.mocked(doGetHostProcesses).mockRejectedValue(new Error("down"));
    render(<ProcessesPanel {...props()} />);
    expect(
      await screen.findByText("Failed to load processes"),
    ).toBeInTheDocument();
  });

  test("refresh asks the agent for a new snapshot", async () => {
    render(<ProcessesPanel {...props()} />);
    await screen.findByText("nginx");
    fireEvent.click(screen.getByRole("button", { name: /Refresh/ }));
    await waitFor(() =>
      expect(doRefreshHostProcesses).toHaveBeenCalledWith("h1"),
    );
    expect(await screen.findByText("Refresh queued")).toBeInTheDocument();
  });

  test("reports a failed refresh request", async () => {
    vi.mocked(doRefreshHostProcesses).mockRejectedValue(new Error("offline"));
    render(<ProcessesPanel {...props()} />);
    await screen.findByText("nginx");
    fireEvent.click(screen.getByRole("button", { name: /Refresh/ }));
    expect(
      await screen.findByText("Failed to request refresh"),
    ).toBeInTheDocument();
  });

  test("searching narrows the listed processes", async () => {
    render(<ProcessesPanel {...props()} />);
    await screen.findByText("nginx");
    fireEvent.change(screen.getByLabelText("search"), {
      target: { value: "ssh" },
    });
    await waitFor(() =>
      expect(screen.queryByText("nginx")).not.toBeInTheDocument(),
    );
    expect(screen.getByText("sshd")).toBeInTheDocument();
  });

  test("the search is case-insensitive", async () => {
    render(<ProcessesPanel {...props()} />);
    await screen.findByText("nginx");
    fireEvent.change(screen.getByLabelText("search"), {
      target: { value: "NGINX" },
    });
    await waitFor(() =>
      expect(screen.queryByText("sshd")).not.toBeInTheDocument(),
    );
    expect(screen.getByText("nginx")).toBeInTheDocument();
  });

  test("killing a process confirms first, then sends the pid", async () => {
    render(<ProcessesPanel {...props()} />);
    await screen.findByText("nginx");
    fireEvent.click(screen.getAllByRole("button", { name: "Kill" })[0]);
    expect(await screen.findByText("Terminate Process")).toBeInTheDocument();
    // Opening the dialog must not itself terminate anything.
    expect(doKillHostProcess).not.toHaveBeenCalled();
    const buttons = screen.getAllByRole("button", { name: "Kill" });
    fireEvent.click(buttons[buttons.length - 1]);
    await waitFor(() =>
      expect(doKillHostProcess).toHaveBeenCalledWith(
        "h1",
        4242,
        expect.objectContaining({ expectedName: "nginx" }),
      ),
    );
    expect(await screen.findByText("Kill queued")).toBeInTheDocument();
  });

  test("reports a failed termination", async () => {
    vi.mocked(doKillHostProcess).mockRejectedValue(new Error("denied"));
    render(<ProcessesPanel {...props()} />);
    await screen.findByText("nginx");
    fireEvent.click(screen.getAllByRole("button", { name: "Kill" })[0]);
    await screen.findByText("Terminate Process");
    const buttons = screen.getAllByRole("button", { name: "Kill" });
    fireEvent.click(buttons[buttons.length - 1]);
    expect(
      await screen.findByText("Failed to request termination"),
    ).toBeInTheDocument();
  });

  test("without the kill permission no kill control is offered", async () => {
    vi.mocked(hasPermission).mockResolvedValue(false);
    render(<ProcessesPanel {...props()} />);
    await screen.findByText("nginx");
    expect(
      screen.queryByRole("button", { name: "Kill" }),
    ).not.toBeInTheDocument();
  });
});
