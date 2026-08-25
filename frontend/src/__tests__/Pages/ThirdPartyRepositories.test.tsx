// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

import { render, screen, waitFor } from "@testing-library/react";
import { vi, describe, beforeEach, afterEach, test, expect } from "vitest";

vi.mock("react-i18next", () => {
  const t = (key: string, fallback?: string) =>
    typeof fallback === "string" ? fallback : key;
  return { useTranslation: () => ({ t, i18n: { language: "en" } }) };
});

vi.mock("@mui/x-data-grid", () => ({
  DataGrid: ({ rows }: { rows?: Array<{ id: string; name?: string }> }) => (
    <div data-testid="grid">
      {(rows ?? []).map((r) => (
        <div key={r.id}>{r.name}</div>
      ))}
    </div>
  ),
}));

vi.mock("../../Components/ThirdPartyReposActionBar", () => ({
  default: ({ selectionCount }: { selectionCount: number }) => (
    <div data-testid="actionbar">{`selected:${selectionCount}`}</div>
  ),
}));
vi.mock("../../Components/ColumnVisibilityButton", () => ({ default: () => null }));

vi.mock("../../Services/api", () => ({
  default: { get: vi.fn(), post: vi.fn(), delete: vi.fn() },
}));

vi.mock("../../Services/permissions", async (orig) => {
  const actual = await orig<typeof import("../../Services/permissions")>();
  return { ...actual, hasPermission: vi.fn() };
});

import axiosInstance from "../../Services/api";
import { hasPermission } from "../../Services/permissions";
import ThirdPartyRepositories from "../../Pages/ThirdPartyRepositories";

const m = (fn: unknown) => fn as unknown as ReturnType<typeof vi.fn>;

const renderPage = (over: Record<string, unknown> = {}) =>
  render(
    <ThirdPartyRepositories
      hostId="h1"
      privilegedMode
      osName="Ubuntu"
      {...(over as { hostId?: string; privilegedMode?: boolean; osName?: string })}
    />,
  );

beforeEach(() => {
  vi.clearAllMocks();
  vi.spyOn(globalThis.console, "error").mockImplementation(() => undefined);
  m(hasPermission).mockResolvedValue(true);
  m(axiosInstance.get).mockResolvedValue({
    data: { repositories: [{ name: "ppa:deadsnakes/ppa", type: "ppa", enabled: true }] },
  });
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("privileged-mode gate", () => {
  test("an unprivileged host shows the requirement and fetches NOTHING", async () => {
    // The gate has to be enforced before the request, not just in the UI: an
    // unprivileged agent cannot act on repositories, so asking is pointless and
    // would surface a confusing server error.
    renderPage({ privilegedMode: false });
    await waitFor(() =>
      expect(screen.getByText("thirdPartyRepos.privilegedModeRequired")).toBeInTheDocument(),
    );
    expect(axiosInstance.get).not.toHaveBeenCalledWith(
      expect.stringContaining("/third-party-repos"),
    );
  });

  test("a privileged host loads its repositories", async () => {
    renderPage();
    await waitFor(() =>
      expect(axiosInstance.get).toHaveBeenCalledWith("/api/v1/hosts/h1/third-party-repos"),
    );
    expect(await screen.findByText("ppa:deadsnakes/ppa")).toBeInTheDocument();
  });
});

describe("load failures", () => {
  test("a failed load surfaces the server's detail rather than a blank grid", async () => {
    m(axiosInstance.get).mockRejectedValue({
      response: { data: { detail: "agent offline" } },
    });
    renderPage();
    await waitFor(() => expect(screen.getByText("agent offline")).toBeInTheDocument());
  });

  test("a missing repositories key yields an empty grid, not a crash", async () => {
    m(axiosInstance.get).mockResolvedValue({ data: {} });
    renderPage();
    await waitFor(() => expect(screen.getByTestId("grid")).toBeInTheDocument());
  });

  test("a non-array defaults payload does not take the page down", async () => {
    // Regression: the defaults endpoint result went into state behind a
    // `|| []` guard, which passes a truthy non-array straight through -- and
    // the very next render did defaultRepositories.map(), throwing and blanking
    // the page.  Found by this suite, 2026-08-25.
    m(axiosInstance.get).mockResolvedValue({ data: { detail: "unexpected" } });
    renderPage();
    await waitFor(() => expect(screen.getByTestId("grid")).toBeInTheDocument());
  });
});

describe("permissions", () => {
  test("all five repository permissions are resolved", async () => {
    renderPage();
    await waitFor(() => expect(hasPermission).toHaveBeenCalled());
    expect(m(hasPermission).mock.calls.length).toBeGreaterThanOrEqual(5);
  });

  test("a rejected permission lookup does not reject into the void", async () => {
    // Third instance of the fire-and-forget checkPermission pattern; this pins
    // the fix so it cannot regress here.
    m(hasPermission).mockRejectedValue(new Error("no session"));
    renderPage();
    await waitFor(() => expect(screen.getByTestId("grid")).toBeInTheDocument());
  });
});
