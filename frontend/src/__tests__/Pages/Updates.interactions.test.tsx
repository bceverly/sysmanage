// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

/**
 * Interaction tests for Pages/Updates.tsx: sorting and row rendering,
 * selection, executing updates, result polling, search, filters and
 * pagination.  The 10s poll interval and the 3s selection-clear timeout are
 * captured (not waited on) so the tests stay deterministic.
 */

import { act, render, screen, fireEvent, waitFor, within } from "@testing-library/react";
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

const { searchParams, triggerRefresh } = vi.hoisted(() => ({
  searchParams: { get: (_k: string): string | null => null },
  triggerRefresh: vi.fn(),
}));
vi.mock("react-router", () => ({
  useSearchParams: () => [searchParams, vi.fn()],
}));

vi.mock("../../hooks/useNotificationRefresh", () => ({
  useNotificationRefresh: () => ({ triggerRefresh }),
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
      getUpdateResults: vi.fn(),
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

const anUpdate = (over: Record<string, unknown> = {}) => ({
  id: "u1",
  host_id: "h1",
  hostname: "alpha.example",
  package_name: "openssl",
  package_manager: "apt",
  current_version: "1.0",
  available_version: "1.1",
  is_security_update: true,
  is_system_update: false,
  ...over,
});

const listResponse = (updates: unknown[], total = updates.length) => ({
  updates,
  total_count: total,
  limit: 50,
  offset: 0,
});

// Capture the poll interval and the selection-clear timeout instead of
// waiting on them; every other timer (RTL's waitFor) runs for real.
let pollCallback: (() => Promise<void>) | null = null;
let clearCallback: (() => void) | null = null;

const realSetInterval = globalThis.setInterval;
const realSetTimeout = globalThis.setTimeout;

beforeEach(() => {
  vi.clearAllMocks();
  pollCallback = null;
  clearCallback = null;
  searchParams.get = () => null;
  vi.spyOn(globalThis, "setInterval").mockImplementation(((cb: () => Promise<void>, ms?: number) => {
    if (ms === 10000) {
      pollCallback = cb;
      return 4242 as unknown as ReturnType<typeof globalThis.setInterval>;
    }
    return realSetInterval(cb, ms);
  }) as typeof globalThis.setInterval);
  vi.spyOn(globalThis, "setTimeout").mockImplementation(((cb: () => void, ms?: number) => {
    if (ms === 3000) {
      clearCallback = cb;
      return 4343 as unknown as ReturnType<typeof globalThis.setTimeout>;
    }
    return realSetTimeout(cb, ms);
  }) as typeof globalThis.setTimeout);
  m(updatesService.getUpdatesSummary).mockResolvedValue({
    total_hosts: 3,
    hosts_with_updates: 2,
    total_updates: 7,
    security_updates: 2,
    system_updates: 3,
    application_updates: 2,
  });
  m(updatesService.getAllUpdates).mockResolvedValue(listResponse([anUpdate()]));
  m(updatesService.getHostUpdates).mockResolvedValue({
    host_id: "h1",
    updates: [anUpdate()],
    total_updates: 11,
    security_updates: 4,
    system_updates: 5,
    application_updates: 2,
  });
  m(updatesService.executeUpdates).mockResolvedValue({});
  m(updatesService.getUpdateResults).mockResolvedValue({ results: {} });
  m(hasPermission).mockResolvedValue(true);
});

afterEach(() => {
  vi.restoreAllMocks();
});

const packageOrder = () =>
  Array.from(document.querySelectorAll(".updates__item-package")).map((e) => e.textContent);

const rowFor = (name: string) =>
  screen.getByText(name, { selector: ".updates__item-package" }).closest(".updates__item") as HTMLElement;

const clickRowCheckbox = (name: string) => {
  const svg = rowFor(name).querySelector(".updates__item-select svg") as Element;
  fireEvent.click(svg);
};

const waitForPermission = async () => {
  await waitFor(() => expect(hasPermission).toHaveBeenCalled());
  await act(async () => {
    await Promise.resolve();
  });
};

describe("row rendering", () => {
  test("sorts security, then system, then application, then by name, and labels each", async () => {
    m(updatesService.getAllUpdates).mockResolvedValue(
      listResponse([
        anUpdate({ id: "a", package_name: "zlib", is_security_update: false, is_system_update: false }),
        anUpdate({ id: "b", package_name: "kernel", is_security_update: false, is_system_update: true, requires_reboot: true }),
        anUpdate({ id: "c", package_name: "openssl" }),
        anUpdate({ id: "d", package_name: "bash", is_security_update: false, is_system_update: false, current_version: null }),
        anUpdate({ id: "e", package_name: "curl", is_security_update: true }),
      ]),
    );
    render(<Updates />);
    await screen.findByText("zlib");
    expect(packageOrder()).toEqual(["curl", "openssl", "kernel", "bash", "zlib"]);
    expect(within(rowFor("kernel")).getByText("System")).toBeInTheDocument();
    expect(within(rowFor("kernel")).getByText("Requires reboot")).toBeInTheDocument();
    expect(within(rowFor("zlib")).getByText("Application")).toBeInTheDocument();
    expect(within(rowFor("curl")).getByText("Security")).toBeInTheDocument();
    expect(rowFor("bash").textContent).toContain("Unknown");
    expect(rowFor("curl").className).toContain("security");
    expect(within(rowFor("curl")).getByText("alpha.example")).toBeInTheDocument();
    // Global stats cards.
    expect(screen.getByText("Affected Hosts").previousSibling?.textContent).toBe("2");
  });

  test("shows backend status pills for updating, completed, success, failed and error", async () => {
    m(updatesService.getAllUpdates).mockResolvedValue(
      listResponse([
        anUpdate({ id: "1", package_name: "p-updating", status: "updating" }),
        anUpdate({ id: "2", package_name: "p-completed", status: "completed" }),
        anUpdate({ id: "3", package_name: "p-success", status: "success" }),
        anUpdate({ id: "4", package_name: "p-failed", status: "failed" }),
        anUpdate({ id: "5", package_name: "p-error", status: "error" }),
        anUpdate({ id: "6", package_name: "p-other", status: "something" }),
      ]),
    );
    render(<Updates />);
    await screen.findByText("p-updating");
    expect(within(rowFor("p-updating")).getByText("Update Requested")).toBeInTheDocument();
    expect(within(rowFor("p-completed")).getByText("Successfully Updated")).toBeInTheDocument();
    expect(within(rowFor("p-success")).getByText("Successfully Updated")).toBeInTheDocument();
    expect(within(rowFor("p-failed")).getByText("Update Failed")).toBeInTheDocument();
    expect(within(rowFor("p-error")).getByText("Update Failed")).toBeInTheDocument();
    expect(rowFor("p-other").querySelector(".updates__status-pill")).toBeNull();
  });
});

describe("selection and execution", () => {
  const twoHosts = () =>
    m(updatesService.getAllUpdates).mockResolvedValue(
      listResponse([
        anUpdate({ id: "1", package_name: "openssl", host_id: "h1" }),
        anUpdate({ id: "2", package_name: "curl", host_id: "h1", package_manager: "snap" }),
        anUpdate({ id: "3", package_name: "nginx", host_id: "h2", hostname: "beta.example" }),
      ]),
    );

  test("select-all toggles every row and back", async () => {
    twoHosts();
    render(<Updates />);
    await screen.findByText("nginx");
    await waitForPermission();
    expect(screen.getByText(/Select All/).textContent).toContain("(0/3)");
    fireEvent.click(document.querySelector(".updates__select-all svg") as Element);
    expect(screen.getByText(/Select All/).textContent).toContain("(3/3)");
    expect(screen.getByText(/Execute Selected Updates/).textContent).toContain("(3)");
    fireEvent.click(document.querySelector(".updates__select-all svg") as Element);
    expect(screen.getByText(/Select All/).textContent).toContain("(0/3)");
    expect(screen.queryByText(/Execute Selected Updates/)).toBeNull();
  });

  test("selecting and deselecting a single row", async () => {
    twoHosts();
    render(<Updates />);
    await screen.findByText("nginx");
    await waitForPermission();
    clickRowCheckbox("curl");
    expect(rowFor("curl").className).toContain("selected");
    clickRowCheckbox("curl");
    expect(rowFor("curl").className).not.toContain("selected");
  });

  test("executes per host, polls for results and clears completed selections", async () => {
    twoHosts();
    render(<Updates />);
    await screen.findByText("nginx");
    await waitForPermission();
    clickRowCheckbox("openssl");
    clickRowCheckbox("curl");
    clickRowCheckbox("nginx");
    await act(async () => {
      fireEvent.click(screen.getByText(/Execute Selected Updates/));
    });
    await waitFor(() => expect(updatesService.executeUpdates).toHaveBeenCalledTimes(2));
    expect(updatesService.executeUpdates).toHaveBeenCalledWith(["h1"], ["openssl", "curl"], ["apt", "snap"]);
    expect(updatesService.executeUpdates).toHaveBeenCalledWith(["h2"], ["nginx"], ["apt"]);
    expect(screen.getAllByText("Update Requested")).toHaveLength(3);

    // First poll returns nothing that matches: statuses stay pending.
    expect(pollCallback).not.toBeNull();
    m(updatesService.getUpdateResults).mockResolvedValueOnce({
      results: { h9: { updated_packages: [{ package_name: "x", package_manager: "apt" }] } },
    });
    await act(async () => {
      await pollCallback!();
    });
    expect(screen.getAllByText("Update Requested")).toHaveLength(3);

    m(updatesService.getUpdateResults).mockResolvedValueOnce({
      results: {
        h1: {
          updated_packages: [{ package_name: "openssl", package_manager: "apt", new_version: "1.1" }],
          failed_packages: [{ package_name: "curl", package_manager: "snap", error: "nope" }],
        },
        h2: {
          failed_packages: [{ package_name: "unrelated", package_manager: "apt" }],
        },
      },
    });
    await act(async () => {
      await pollCallback!();
    });
    expect(within(rowFor("openssl")).getByText("Successfully Updated")).toBeInTheDocument();
    expect(within(rowFor("curl")).getByText("Update Failed")).toBeInTheDocument();
    expect(within(rowFor("nginx")).getByText("Update Requested")).toBeInTheDocument();
    expect(triggerRefresh).toHaveBeenCalled();

    // Reselect a completed row; the deferred clear must drop it again.
    clickRowCheckbox("openssl");
    expect(rowFor("openssl").className).toContain("selected");
    expect(clearCallback).not.toBeNull();
    act(() => {
      clearCallback!();
    });
    expect(rowFor("openssl").className).not.toContain("selected");
  });

  test("a polling error is logged and does not change the rows", async () => {
    const errSpy = vi.spyOn(globalThis.console, "error").mockImplementation(() => {});
    render(<Updates />);
    await screen.findByText("openssl");
    await waitForPermission();
    clickRowCheckbox("openssl");
    await act(async () => {
      fireEvent.click(screen.getByText(/Execute Selected Updates/));
    });
    m(updatesService.getUpdateResults).mockRejectedValueOnce(new Error("poll down"));
    await act(async () => {
      await pollCallback!();
    });
    expect(errSpy).toHaveBeenCalledWith("Failed to poll for update results:", expect.any(Error));
    expect(screen.getByText("Update Requested")).toBeInTheDocument();
  });

  test("a failed submission marks the pending rows as failed", async () => {
    const errSpy = vi.spyOn(globalThis.console, "error").mockImplementation(() => {});
    m(updatesService.executeUpdates).mockRejectedValue(new Error("agent gone"));
    render(<Updates />);
    await screen.findByText("openssl");
    await waitForPermission();
    clickRowCheckbox("openssl");
    await act(async () => {
      fireEvent.click(screen.getByText(/Execute Selected Updates/));
    });
    await waitFor(() => expect(within(rowFor("openssl")).getByText("Update Failed")).toBeInTheDocument());
    expect(errSpy).toHaveBeenCalledWith("Failed to execute updates:", expect.any(Error));
  });

  test("an update with a null host_id is skipped, not submitted", async () => {
    const errSpy = vi.spyOn(globalThis.console, "error").mockImplementation(() => {});
    // Both the page query and the host dropdown query (limit 1000) carry the
    // malformed row: the dropdown used to crash the page on it.
    m(updatesService.getAllUpdates).mockResolvedValue(
      listResponse([anUpdate({ host_id: null, package_name: "ghost" })]),
    );
    render(<Updates />);
    await screen.findByText("ghost");
    expect(screen.getAllByRole("option").map((o) => o.textContent)).not.toContain(
      expect.stringContaining("(1 updates)"),
    );
    await waitForPermission();
    clickRowCheckbox("ghost");
    await act(async () => {
      fireEvent.click(screen.getByText(/Execute Selected Updates/));
    });
    expect(updatesService.executeUpdates).not.toHaveBeenCalled();
    expect(errSpy).toHaveBeenCalledWith("ERROR: Found null/undefined host_id in update:", expect.anything());
  });

  test("without the apply permission rows cannot be selected", async () => {
    m(hasPermission).mockResolvedValue(false);
    render(<Updates />);
    await screen.findByText("openssl");
    await waitForPermission();
    fireEvent.click(document.querySelector(".updates__select-all svg") as Element);
    clickRowCheckbox("openssl");
    expect(screen.getByText(/Select All/).textContent).toContain("(0/1)");
    expect(screen.queryByText(/Execute Selected Updates/)).toBeNull();
  });
});

describe("search, filters and pagination", () => {
  test("search filters by package name and can be cleared", async () => {
    m(updatesService.getAllUpdates).mockResolvedValue(
      listResponse([
        anUpdate({ id: "1", package_name: "OpenSSL" }),
        anUpdate({ id: "2", package_name: "curl" }),
      ]),
    );
    render(<Updates />);
    await screen.findByText("curl");
    fireEvent.change(screen.getByPlaceholderText("Search for package updates..."), {
      target: { value: "ssl" },
    });
    await waitFor(() => expect(screen.queryByText("curl")).toBeNull());
    expect(screen.getByText("OpenSSL")).toBeInTheDocument();
    fireEvent.click(screen.getByLabelText("Clear search"));
    await screen.findByText("curl");
  });

  test("system, application and package-manager filters are passed to the API", async () => {
    render(<Updates />);
    await screen.findByText("openssl");
    fireEvent.click(screen.getByLabelText("System Updates Only"));
    await waitFor(() =>
      expect(updatesService.getAllUpdates).toHaveBeenCalledWith(undefined, true, undefined, undefined, 50, 0),
    );
    fireEvent.click(screen.getByLabelText("Application Updates Only"));
    await waitFor(() =>
      expect(updatesService.getAllUpdates).toHaveBeenCalledWith(undefined, true, true, undefined, 50, 0),
    );
    fireEvent.change(screen.getByDisplayValue("All Package Managers"), { target: { value: "snap" } });
    await waitFor(() =>
      expect(updatesService.getAllUpdates).toHaveBeenCalledWith(undefined, true, true, "snap", 50, 0),
    );
  });

  test("filters with no results show the no-match message", async () => {
    render(<Updates />);
    await screen.findByText("openssl");
    m(updatesService.getAllUpdates).mockResolvedValue(listResponse([]));
    fireEvent.click(screen.getByLabelText("Security Updates Only"));
    expect(await screen.findByText("No updates match the current filters")).toBeInTheDocument();
  });

  test("the host dropdown lists hosts with counts and scopes to one host", async () => {
    m(updatesService.getAllUpdates).mockResolvedValue(
      listResponse([
        anUpdate({ id: "1", host_id: "h2", hostname: "beta.example", package_name: "a" }),
        anUpdate({ id: "2", host_id: "h1", hostname: "alpha.example", package_name: "b" }),
        anUpdate({ id: "3", host_id: "h2", hostname: "beta.example", package_name: "c" }),
      ]),
    );
    render(<Updates />);
    const alpha = await screen.findByRole("option", { name: "alpha.example (1 updates)" });
    const options = screen.getAllByRole("option").map((o) => o.textContent);
    expect(options.indexOf("alpha.example (1 updates)")).toBeLessThan(options.indexOf("beta.example (2 updates)"));
    fireEvent.change(alpha.closest("select") as HTMLSelectElement, { target: { value: "h1" } });
    await waitFor(() =>
      expect(updatesService.getHostUpdates).toHaveBeenCalledWith("h1", undefined, undefined, undefined, undefined),
    );
    // Host-scoped stats replace the fleet stats; hostnames are hidden.
    await waitFor(() => expect(screen.getByText("Total Updates").previousSibling?.textContent).toBe("11"));
    expect(screen.getByText("Affected Hosts").previousSibling?.textContent).toBe("1");
    expect(document.querySelector(".updates__item-host")).toBeNull();
  });

  test("a host-scoped fetch failure empties the list", async () => {
    const errSpy = vi.spyOn(globalThis.console, "error").mockImplementation(() => {});
    searchParams.get = (k: string) => (k === "host" ? "h1" : null);
    m(updatesService.getHostUpdates).mockRejectedValue(new Error("down"));
    render(<Updates />);
    expect(await screen.findByText("No updates match the current filters")).toBeInTheDocument();
    expect(errSpy).toHaveBeenCalledWith("Failed to fetch updates:", expect.any(Error));
  });

  test("a hosts-list failure leaves only the all-hosts option", async () => {
    const errSpy = vi.spyOn(globalThis.console, "error").mockImplementation(() => {});
    m(updatesService.getAllUpdates).mockImplementation((...args: unknown[]) =>
      args[4] === 1000 ? Promise.reject(new Error("x")) : Promise.resolve(listResponse([anUpdate()])),
    );
    render(<Updates />);
    await screen.findByText("openssl");
    await waitFor(() =>
      expect(errSpy).toHaveBeenCalledWith("Failed to fetch hosts with updates:", expect.any(Error)),
    );
    const hostSelect = screen.getByDisplayValue("All Affected Hosts") as HTMLSelectElement;
    expect(hostSelect.options).toHaveLength(1);
  });

  test("pagination moves between pages with the right offset", async () => {
    m(updatesService.getAllUpdates).mockResolvedValue(listResponse([anUpdate()], 120));
    render(<Updates />);
    expect(await screen.findByText("Page 1 of 3")).toBeInTheDocument();
    expect(screen.getByText("Previous")).toBeDisabled();
    fireEvent.click(screen.getByText("Next"));
    await waitFor(() =>
      expect(updatesService.getAllUpdates).toHaveBeenCalledWith(undefined, undefined, undefined, undefined, 50, 50),
    );
    expect(await screen.findByText("Page 2 of 3")).toBeInTheDocument();
    fireEvent.click(screen.getByText("Previous"));
    expect(await screen.findByText("Page 1 of 3")).toBeInTheDocument();
  });

  test("manual refresh refetches and pings the notification bell", async () => {
    render(<Updates />);
    await screen.findByText("openssl");
    const before = m(updatesService.getUpdatesSummary).mock.calls.length;
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: /Refresh/ }));
    });
    await waitFor(() => expect(triggerRefresh).toHaveBeenCalled());
    expect(m(updatesService.getUpdatesSummary).mock.calls.length).toBeGreaterThan(before);
  });
});
