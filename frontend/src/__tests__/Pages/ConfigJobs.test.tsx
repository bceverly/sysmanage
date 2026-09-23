// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

/**
 * The fleet jobs page.
 *
 * Jobs is the first tab deliberately: it is the one people come back to, while
 * templates and inventories are authored once and then rarely touched.
 *
 * Launching jumps to Jobs. A launch that leaves the operator staring at the
 * Templates tab looks exactly like nothing happened, and the first thing they
 * do is press it again -- which on a fleet means two jobs.
 */

import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { vi, describe, test, expect, beforeEach } from "vitest";

const t = (key: string, fallback?: string) =>
  typeof fallback === "string" ? fallback : key;
vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t, i18n: { language: "en" } }),
}));

vi.mock("../../Services/permissions", async (orig) => {
  const actual = await orig<typeof import("../../Services/permissions")>();
  return { ...actual, hasPermission: vi.fn() };
});

vi.mock("../../Components/ConfigJobsPanel", () => ({
  default: ({ canCancel }: { canCancel: boolean }) => (
    <div data-testid="jobs-panel">{String(canCancel)}</div>
  ),
}));
vi.mock("../../Components/ConfigJobTemplatesPanel", () => ({
  default: ({
    canEdit,
    canLaunch,
    onLaunched,
  }: {
    canEdit: boolean;
    canLaunch: boolean;
    onLaunched?: () => void;
  }) => (
    <div data-testid="templates-panel">
      {String(canEdit)}/{String(canLaunch)}
      <button onClick={() => onLaunched?.()}>fire-launch</button>
    </div>
  ),
}));
vi.mock("../../Components/ConfigInventoriesPanel", () => ({
  default: ({ canEdit }: { canEdit: boolean }) => (
    <div data-testid="inventories-panel">{String(canEdit)}</div>
  ),
}));

import { hasPermission } from "../../Services/permissions";
import ConfigJobs from "../../Pages/ConfigJobs";

const m = (fn: unknown) => fn as ReturnType<typeof vi.fn>;

beforeEach(() => {
  vi.clearAllMocks();
  m(hasPermission).mockResolvedValue(true);
});

describe("ConfigJobs", () => {
  test("jobs is the tab that opens first", async () => {
    render(<ConfigJobs />);
    expect(await screen.findByTestId("jobs-panel")).toBeInTheDocument();
  });

  test("the intro says a job works in waves, not all at once", async () => {
    // The distinction between this page and an assignment; if it is not said
    // here it is not said anywhere the operator will read.
    render(<ConfigJobs />);
    expect(await screen.findByText(/in waves rather than all at once/i)).toBeInTheDocument();
  });

  test("each tab shows its own panel", async () => {
    render(<ConfigJobs />);
    fireEvent.click(screen.getByText("Templates"));
    expect(await screen.findByTestId("templates-panel")).toBeInTheDocument();
    fireEvent.click(screen.getByText("Inventories"));
    expect(await screen.findByTestId("inventories-panel")).toBeInTheDocument();
  });

  test("launching returns the operator to the jobs tab", async () => {
    render(<ConfigJobs />);
    fireEvent.click(screen.getByText("Templates"));
    fireEvent.click(await screen.findByText("fire-launch"));
    expect(await screen.findByTestId("jobs-panel")).toBeInTheDocument();
  });

  test("permissions reach the panels", async () => {
    render(<ConfigJobs />);
    await waitFor(() =>
      expect(screen.getByTestId("jobs-panel")).toHaveTextContent("true"),
    );
    fireEvent.click(screen.getByText("Templates"));
    expect(await screen.findByTestId("templates-panel")).toHaveTextContent(
      "true/true",
    );
  });

  test("a permission lookup that fails leaves the page read-only, not broken", async () => {
    // Fail closed: a page of dead buttons with no explanation is bad, but a
    // page that grants everything because a check errored is worse.
    // The test-file lint block does not list `console` among its globals, so
    // the directive has to sit on the line itself -- wrapped onto two lines it
    // would apply to the comment rather than to the code.
    // eslint-disable-next-line no-undef
    const spy = vi.spyOn(console, "error").mockImplementation(() => {});
    m(hasPermission).mockRejectedValue(new Error("no session"));
    render(<ConfigJobs />);
    fireEvent.click(screen.getByText("Templates"));
    expect(await screen.findByTestId("templates-panel")).toHaveTextContent(
      "false/false",
    );
    spy.mockRestore();
  });
});
