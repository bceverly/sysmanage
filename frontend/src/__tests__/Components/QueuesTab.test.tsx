// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

/**
 * The Queues tab was lifted out of Settings.tsx, which had no test at all.
 *
 * The one behaviour that genuinely CHANGED in the move is pinned first: the
 * page used to fetch the failed-message list from its tab-change handler, so
 * arriving at #queues by URL rendered an empty grid that never populated.  The
 * component now fetches on mount, which is the only way the deep link works.
 */

import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { vi, beforeEach, test, expect } from "vitest";

vi.mock("react-i18next", () => {
  const t = (key: string, fallback?: string) => fallback || key;
  return { useTranslation: () => ({ t, i18n: { language: "en" } }) };
});

vi.mock("../../Services/api", () => ({
  default: { get: vi.fn(), post: vi.fn(), put: vi.fn(), delete: vi.fn() },
}));

vi.mock("../../Services/permissions", () => ({
  hasPermission: vi.fn(),
  SecurityRoles: { DELETE_QUEUE_MESSAGE: "DELETE_QUEUE_MESSAGE" },
}));

vi.mock("../../hooks/useTablePageSize", () => ({
  useTablePageSize: () => ({ pageSize: 25, pageSizeOptions: [10, 25, 50] }),
}));

vi.mock("../../hooks/useColumnVisibility", () => ({
  useColumnVisibility: () => ({
    hiddenColumns: [],
    setHiddenColumns: vi.fn(),
    resetPreferences: vi.fn(),
    getColumnVisibilityModel: () => ({}),
  }),
}));

// MUI X DataGrid's CSS (border shorthand with a CSS var) trips jsdom's cssstyle,
// so stub it to a trivial renderer -- what is under test is the fetching and
// the delete/detail wiring, not the grid internals.
vi.mock("@mui/x-data-grid", () => ({
  DataGrid: ({
    rows,
    columns,
  }: {
    rows: Array<{ id: string; type: string }>;
    columns: Array<{ field: string; renderCell?: (p: unknown) => unknown }>;
  }) => (
    <div data-testid="grid">
      {rows.map((r) => (
        <div key={r.id}>
          <span>{r.type}</span>
          {columns
            .filter((c) => c.field === "actions")
            .map((c) => (
              <span key={c.field}>{c.renderCell?.({ row: r })}</span>
            ))}
        </div>
      ))}
    </div>
  ),
}));

import axiosInstance from "../../Services/api";
import { hasPermission } from "../../Services/permissions";
import QueuesTab from "../../Components/settings/QueuesTab";

const MESSAGES = [
  { id: "m1", type: "command", direction: "outbound", priority: "high" },
  { id: "m2", type: "heartbeat", direction: "inbound", priority: "low" },
];

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(hasPermission).mockResolvedValue(true);
  vi.mocked(axiosInstance.get).mockResolvedValue({ data: MESSAGES });
  vi.mocked(axiosInstance.delete).mockResolvedValue({ data: {} });
});

test("fetches the failed-message list on mount", async () => {
  // The regression this replaces: loading was driven by the parent's tab-change
  // handler, so a deep link to the tab never triggered a fetch.
  render(<QueuesTab />);

  await waitFor(() =>
    expect(axiosInstance.get).toHaveBeenCalledWith("/api/v1/queue/failed"),
  );
  expect(await screen.findByText("command")).toBeInTheDocument();
  expect(screen.getByText("heartbeat")).toBeInTheDocument();
});

test("an API failure leaves the tab usable rather than blank", async () => {
  vi.mocked(axiosInstance.get).mockRejectedValue(new Error("boom"));
  const spy = vi.spyOn(console, "error").mockImplementation(() => {});

  render(<QueuesTab />);

  expect(await screen.findByText("Queue Management")).toBeInTheDocument();
  await waitFor(() => expect(spy).toHaveBeenCalled());
  spy.mockRestore();
});

test("delete is hidden without the DELETE_QUEUE_MESSAGE role", async () => {
  vi.mocked(hasPermission).mockResolvedValue(false);
  render(<QueuesTab />);

  await screen.findByText("command");
  expect(screen.queryByRole("button", { name: /Delete/ })).toBeNull();
});

test("delete is shown, but disabled until rows are selected", async () => {
  render(<QueuesTab />);

  const button = await screen.findByRole("button", { name: /Delete/ });
  // Nothing is selected on first render, so deleting would be a no-op request.
  expect(button).toBeDisabled();
  expect(axiosInstance.delete).not.toHaveBeenCalled();
});

test("viewing a message fetches its detail and shows the payload", async () => {
  vi.mocked(axiosInstance.get).mockImplementation((url: string) =>
    url === "/api/v1/queue/failed"
      ? Promise.resolve({ data: MESSAGES })
      : Promise.resolve({
          data: { ...MESSAGES[0], data: { command_type: "collect_packages" } },
        }),
  );

  render(<QueuesTab />);
  await screen.findByText("command");

  fireEvent.click(screen.getAllByTitle("View Details")[0]);

  await waitFor(() =>
    expect(axiosInstance.get).toHaveBeenCalledWith("/api/v1/queue/failed/m1"),
  );
  expect(await screen.findByText("Message Details")).toBeInTheDocument();
  // The dialog renders the raw payload, which is the whole point of opening it.
  expect(screen.getByText(/collect_packages/)).toBeInTheDocument();
});
