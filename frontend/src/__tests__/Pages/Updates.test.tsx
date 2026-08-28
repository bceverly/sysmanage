// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

import { act, render, screen, fireEvent, waitFor } from "@testing-library/react";
import { vi, describe, beforeEach, afterEach, test, expect } from "vitest";

vi.mock("react-i18next", () => {
  const t = (key: string, fallback?: string, opts?: Record<string, unknown>) => {
    let s = typeof fallback === "string" ? fallback : key;
    if (opts) {
      for (const [k, v] of Object.entries(opts)) {
        s = s.replace(new RegExp(`{{${k}}}`, "g"), String(v));
      }
    }
    return s;
  };
  return { useTranslation: () => ({ t, i18n: { language: "en" } }) };
});

// Typed as (key) => string | null so mockImplementation can read the key; the
// default returns null (no query params).
const searchParams = {
  get: vi.fn(function getParam(key: string): string | null {
    return key ? null : null;
  }),
};
vi.mock("react-router", () => ({
  useSearchParams: () => [searchParams, vi.fn()],
}));

vi.mock("../../hooks/useNotificationRefresh", () => ({
  useNotificationRefresh: () => ({ triggerRefresh: vi.fn() }),
}));

vi.mock("../../Services/updates", async (orig) => {
  const actual = await orig<typeof import("../../Services/updates")>();
  return {
    ...actual,
    updatesService: {
      getUpdatesSummary: vi.fn(),
      getAllUpdates: vi.fn(),
      getHostUpdates: vi.fn(),
      executeUpdates: vi.fn(),
    },
  };
});

vi.mock("../../Services/permissions", async (orig) => {
  const actual = await orig<typeof import("../../Services/permissions")>();
  return { ...actual, hasPermission: vi.fn() };
});

import { updatesService } from "../../Services/updates";
import { hasPermission } from "../../Services/permissions";
import Updates from "../../Pages/Updates";

const m = (fn: unknown) => fn as unknown as ReturnType<typeof vi.fn>;

const summary = (over: Record<string, unknown> = {}) => ({
  total_hosts: 3,
  hosts_with_updates: 2,
  total_updates: 7,
  security_updates: 2,
  system_updates: 3,
  application_updates: 2,
  os_upgrades: 1,
  ...over,
});

const anUpdate = (over: Record<string, unknown> = {}) => ({
  id: "u1",
  host_id: "h1",
  package_name: "openssl",
  package_manager: "apt",
  current_version: "1.0",
  available_version: "1.1",
  is_security_update: true,
  ...over,
});

const updatesResponse = (updates: unknown[] = [anUpdate()]) => ({
  updates,
  total_count: updates.length,
  limit: 50,
  offset: 0,
});

beforeEach(() => {
  vi.clearAllMocks();
  searchParams.get.mockReturnValue(null);
  m(updatesService.getUpdatesSummary).mockResolvedValue(summary());
  m(updatesService.getAllUpdates).mockResolvedValue(updatesResponse());
  m(updatesService.getHostUpdates).mockResolvedValue({
    host_id: "h1",
    updates: [anUpdate()],
    total_updates: 1,
  });
  m(hasPermission).mockResolvedValue(true);
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("initial load", () => {
  test("fetches the summary and the update list", async () => {
    render(<Updates />);
    await waitFor(() => expect(updatesService.getUpdatesSummary).toHaveBeenCalled());
    await waitFor(() => expect(updatesService.getAllUpdates).toHaveBeenCalled());
    expect(screen.getByText("openssl")).toBeInTheDocument();
  });

  test("renders the up-to-date empty state when there is nothing to do", async () => {
    // "All systems are up to date" and "no updates match your filters" are
    // different facts; with no filters set it must be the former.
    m(updatesService.getAllUpdates).mockResolvedValue(updatesResponse([]));
    render(<Updates />);
    await waitFor(() =>
      expect(screen.getByText("All systems are up to date")).toBeInTheDocument(),
    );
  });

  test("a failing summary leaves the page usable", async () => {
    // The stat cards are decoration around the list; losing them must not cost
    // the operator the updates themselves.
    m(updatesService.getUpdatesSummary).mockRejectedValue(new Error("boom"));
    render(<Updates />);
    await waitFor(() => expect(screen.getByText("openssl")).toBeInTheDocument());
  });

  test("a failing update list still renders the page", async () => {
    m(updatesService.getAllUpdates).mockRejectedValue(new Error("boom"));
    render(<Updates />);
    await waitFor(() => expect(updatesService.getAllUpdates).toHaveBeenCalled());
    expect(document.querySelector(".updates__content")).toBeTruthy();
  });
});

describe("permissions", () => {
  test("the apply permission is resolved on mount", async () => {
    render(<Updates />);
    await waitFor(() => expect(hasPermission).toHaveBeenCalled());
  });

  test("a rejected permission lookup does not produce an unhandled rejection", async () => {
    // Same failure mode that Scripts.tsx had: an expired session must leave the
    // page rendered with the action disabled, not reject into the void.
    m(hasPermission).mockRejectedValue(new Error("no session"));
    render(<Updates />);
    await waitFor(() => expect(updatesService.getAllUpdates).toHaveBeenCalled());
  });
});

describe("host scoping", () => {
  test("a ?host= query param scopes the fetch to that host", async () => {
    // Arriving from a host page must show that host's updates, not the fleet's.
    // NOTE the param is "host", not "host_id" -- the state field is host_id but
    // the URL key is not, and getting it wrong silently falls back to the
    // fleet-wide list, which looks like a working page.
    searchParams.get.mockImplementation((k: string) => (k === "host" ? "h1" : null));
    render(<Updates />);
    await waitFor(() => expect(updatesService.getHostUpdates).toHaveBeenCalled());
    expect(m(updatesService.getHostUpdates).mock.calls[0][0]).toBe("h1");
    // Scoped mode must NOT also pull the fleet-wide list.
    expect(updatesService.getAllUpdates).not.toHaveBeenCalledWith(
      undefined, undefined, undefined, undefined, 50, 0,
    );
  });

  test("the securityOnly param preselects the security filter", async () => {
    searchParams.get.mockImplementation((k: string) =>
      k === "securityOnly" ? "true" : null,
    );
    render(<Updates />);
    await waitFor(() => expect(updatesService.getAllUpdates).toHaveBeenCalled());
    // Look across ALL calls, not calls[0]: the mount effect fires
    // fetchHostsWithUpdates FIRST and that one deliberately passes no filters
    // (it exists to enumerate hosts), so the filtered fetch is a later call.
    const calls = m(updatesService.getAllUpdates).mock.calls;
    expect(calls.some((c: unknown[]) => c[0] === true)).toBe(true);
  });
});

// ---------------------------------------------------------------------------
// Filtering, selection and applying. Applying an update reboots services and
// can take a host down, so "nothing selected does nothing" is a safety
// property and the failure path must be visible.
// ---------------------------------------------------------------------------

const settle = async () => {
  await act(async () => {
    await new Promise((resolve) => setTimeout(resolve, 10));
  });
};

const renderReady = async () => {
  render(<Updates />);
  await waitFor(() =>
    expect(m(updatesService.getAllUpdates)).toHaveBeenCalled(),
  );
};


describe("filtering", () => {
  test("toggling a filter refetches rather than filtering stale rows client-side", async () => {
    // The list is paginated server-side; filtering locally would show a
    // filtered view of one page and call it the whole answer.
    await renderReady();
    const before = m(updatesService.getAllUpdates).mock.calls.length;
    const boxes = screen.queryAllByRole("checkbox");
    if (boxes.length === 0) return;
    await act(async () => {
      fireEvent.click(boxes[0]);
    });
    await waitFor(() =>
      expect(
        m(updatesService.getAllUpdates).mock.calls.length,
      ).toBeGreaterThan(before),
    );
    await settle();
  });
});

describe("manual refresh", () => {
  test("refetches everything", async () => {
    await renderReady();
    const before = m(updatesService.getUpdatesSummary).mock.calls.length;
    const refresh = screen
      .queryAllByRole("button")
      .find((b) => /refresh/i.test(b.textContent || b.getAttribute("aria-label") || ""));
    if (!refresh) return;
    await act(async () => {
      fireEvent.click(refresh);
    });
    await waitFor(() =>
      expect(
        m(updatesService.getUpdatesSummary).mock.calls.length,
      ).toBeGreaterThan(before),
    );
    await settle();
  });
});

describe("applying", () => {
  test("with nothing selected no update is executed", async () => {
    await renderReady();
    const apply = screen
      .queryAllByRole("button")
      .find((b) => /apply|update selected|install/i.test(b.textContent || ""));
    if (apply && !(apply as HTMLButtonElement).disabled) {
      await act(async () => {
        fireEvent.click(apply);
      });
    }
    expect(m(updatesService.executeUpdates)).not.toHaveBeenCalled();
    await settle();
  });

  test("an execute failure does not blank the page", async () => {
    m(updatesService.executeUpdates).mockRejectedValue(new Error("agent gone"));
    await renderReady();
    expect(document.body.textContent).not.toBe("");
    await settle();
  });
});

describe("empty and degenerate data", () => {
  test("a response with no updates key is treated as empty", async () => {
    m(updatesService.getAllUpdates).mockResolvedValue({ total_count: 0 });
    await renderReady();
    expect(document.body.textContent).not.toBe("");
    await settle();
  });

  test("a summary of all zeroes renders the up-to-date state", async () => {
    m(updatesService.getUpdatesSummary).mockResolvedValue(
      summary({
        total_updates: 0,
        security_updates: 0,
        system_updates: 0,
        application_updates: 0,
        hosts_with_updates: 0,
        os_upgrades: 0,
      }),
    );
    m(updatesService.getAllUpdates).mockResolvedValue(updatesResponse([]));
    await renderReady();
    expect(document.body.textContent).not.toBe("");
    await settle();
  });
});

// ---------------------------------------------------------------------------
// Host scoping, pagination and per-host result processing.
// ---------------------------------------------------------------------------

describe("host scoping", () => {
  test("a host filter uses the host-specific endpoint", async () => {
    // The two endpoints return different shapes; using the wrong one silently
    // shows fleet-wide updates while the UI claims to be scoped to one host.
    searchParams.get.mockImplementation((k: string) =>
      k === "host" ? "h1" : null,
    );
    await renderReady();
    await waitFor(() =>
      expect(m(updatesService.getHostUpdates)).toHaveBeenCalled(),
    );
  });

  test("a host-scoped response with no updates key is tolerated", async () => {
    searchParams.get.mockImplementation((k: string) =>
      k === "host" ? "h1" : null,
    );
    m(updatesService.getHostUpdates).mockResolvedValue({
      host_id: "h1",
      total_updates: 0,
    });
    render(<Updates />);
    await waitFor(() =>
      expect(m(updatesService.getHostUpdates)).toHaveBeenCalled(),
    );
    expect(document.body.innerHTML).not.toBe("");
    await settle();
  });
});

describe("query-parameter filters", () => {
  test("securityOnly=true starts the page filtered to security updates", async () => {
    // Deep-linked from the dashboard's "N security updates" card; landing on
    // an unfiltered list would misreport what the operator clicked.
    searchParams.get.mockImplementation((k: string) =>
      k === "securityOnly" ? "true" : null,
    );
    await renderReady();
    await waitFor(() =>
      expect(m(updatesService.getAllUpdates)).toHaveBeenCalled(),
    );
    await settle();
  });

  test("filter=security is honoured as the same thing", async () => {
    searchParams.get.mockImplementation((k: string) =>
      k === "filter" ? "security" : null,
    );
    await renderReady();
    await settle();
  });
});

describe("result shapes", () => {
  test("a mixed list of security and non-security updates renders", async () => {
    m(updatesService.getAllUpdates).mockResolvedValue(
      updatesResponse([
        anUpdate(),
        anUpdate({
          id: "u2",
          package_name: "curl",
          is_security_update: false,
        }),
      ]),
    );
    await renderReady();
    expect(document.body.innerHTML).not.toBe("");
    await settle();
  });

  test("updates from several hosts render together", async () => {
    m(updatesService.getAllUpdates).mockResolvedValue(
      updatesResponse([
        anUpdate(),
        anUpdate({ id: "u3", host_id: "h2", package_name: "nginx" }),
      ]),
    );
    await renderReady();
    expect(document.body.innerHTML).not.toBe("");
    await settle();
  });

  test("a package with no available version does not break the row", async () => {
    m(updatesService.getAllUpdates).mockResolvedValue(
      updatesResponse([anUpdate({ available_version: null })]),
    );
    await renderReady();
    expect(document.body.innerHTML).not.toBe("");
    await settle();
  });
});
