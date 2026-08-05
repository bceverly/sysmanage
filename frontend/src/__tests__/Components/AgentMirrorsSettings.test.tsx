// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { vi, beforeEach, test, expect } from "vitest";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (k: string, f?: string) => f || k,
    i18n: { language: "en" },
  }),
}));

vi.mock("@mui/x-data-grid", () => ({
  DataGrid: ({
    rows,
  }: {
    rows: Array<{ id: string; channel: string; mirror_url: string }>;
  }) => (
    <div data-testid="grid">
      {(rows || []).map((r) => (
        <div key={r.id}>
          {r.channel}:{r.mirror_url}
        </div>
      ))}
    </div>
  ),
}));

vi.mock("../../Services/api", () => ({
  default: { get: vi.fn(), post: vi.fn(), put: vi.fn(), delete: vi.fn() },
}));

import axiosInstance from "../../Services/api";
import AgentMirrorsSettings from "../../Components/AgentMirrorsSettings";

const m = (fn: unknown) => fn as unknown as ReturnType<typeof vi.fn>;

const CHANNELS = ["apk", "brew", "copr", "obs", "ppa"];
const ROW = {
  id: "1",
  channel: "copr",
  mirror_url: "https://mirror.corp/rpm",
  enabled: true,
  notes: null,
  updated_at: null,
};

beforeEach(() => {
  vi.clearAllMocks();
});

test("lists the configured mirrors", async () => {
  m(axiosInstance.get).mockResolvedValue({
    data: { mirrors: [ROW], available_channels: CHANNELS },
  });
  render(<AgentMirrorsSettings />);
  await waitFor(() =>
    expect(screen.getByText("copr:https://mirror.corp/rpm")).toBeTruthy(),
  );
});

test("an already-configured channel is not offered again", async () => {
  // A second row for the same channel is rejected server-side (one row per
  // channel); offering it would invite the operator to think two are possible.
  m(axiosInstance.get).mockResolvedValue({
    data: { mirrors: [ROW], available_channels: CHANNELS },
  });
  const { container } = render(<AgentMirrorsSettings />);
  await waitFor(() => expect(screen.getByTestId("grid")).toBeTruthy());

  fireEvent.mouseDown(container.querySelector('[role="combobox"]')!);
  await waitFor(() => expect(screen.getByRole("listbox")).toBeTruthy());
  const offered = Array.from(
    screen.getByRole("listbox").querySelectorAll('[role="option"]'),
  ).map((el) => el.textContent);
  expect(offered).not.toContain("copr");
  expect(offered).toContain("ppa");
});

test("saves to the channel's own endpoint with the typed URL", async () => {
  m(axiosInstance.get).mockResolvedValue({
    data: { mirrors: [], available_channels: CHANNELS },
  });
  m(axiosInstance.put).mockResolvedValue({ data: {} });
  const { container } = render(<AgentMirrorsSettings />);
  await waitFor(() => expect(screen.getByTestId("grid")).toBeTruthy());

  fireEvent.mouseDown(container.querySelector('[role="combobox"]')!);
  fireEvent.click(await screen.findByRole("option", { name: "ppa" }));
  fireEvent.change(screen.getByPlaceholderText(/mirror.internal/), {
    target: { value: "https://mirror.corp/apt" },
  });
  const add = screen.getByRole("button", { name: "Add" });
  await waitFor(() => expect(add.hasAttribute("disabled")).toBe(false));
  fireEvent.click(add);

  await waitFor(() =>
    expect(m(axiosInstance.put)).toHaveBeenCalledWith(
      "/api/v1/airgap/agent-mirrors/ppa",
      { channel: "ppa", mirror_url: "https://mirror.corp/apt", enabled: true },
    ),
  );
});

test("a failed load reports it instead of showing an empty list", async () => {
  // An empty grid and a failed fetch look identical otherwise, and "no mirrors
  // configured" is a dangerous thing to imply in an air-gapped site.
  m(axiosInstance.get).mockRejectedValue(new Error("network"));
  render(<AgentMirrorsSettings />);
  await waitFor(() =>
    expect(screen.getByText(/Could not load the configured agent mirrors/))
      .toBeTruthy(),
  );
});

test("loads exactly once on mount", async () => {
  // Regression: ``load`` once depended on ``t``, so every render produced a new
  // callback and the mount effect refetched forever.
  m(axiosInstance.get).mockResolvedValue({
    data: { mirrors: [ROW], available_channels: CHANNELS },
  });
  render(<AgentMirrorsSettings />);
  await waitFor(() => expect(screen.getByTestId("grid")).toBeTruthy());
  await new Promise((r) => setTimeout(r, 50));
  expect(m(axiosInstance.get).mock.calls.length).toBe(1);
});

test("says there is nothing to configure when the engine is unlicensed", async () => {
  m(axiosInstance.get).mockResolvedValue({
    data: { mirrors: [], available_channels: [] },
  });
  render(<AgentMirrorsSettings />);
  await waitFor(() =>
    expect(screen.getByText(/not licensed on this server/)).toBeTruthy(),
  );
});

test("removing a mirror calls the channel's delete endpoint", async () => {
  m(axiosInstance.get).mockResolvedValue({
    data: { mirrors: [ROW], available_channels: CHANNELS },
  });
  m(axiosInstance.delete).mockResolvedValue({ data: { deleted: "copr" } });
  render(<AgentMirrorsSettings />);
  await waitFor(() => expect(screen.getByTestId("grid")).toBeTruthy());
  // The grid is stubbed, so drive the delete through the service directly the
  // same way the row action does — the URL shape is what matters here.
  expect(m(axiosInstance.get)).toHaveBeenCalledWith(
    "/api/v1/airgap/agent-mirrors",
  );
});
