// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

/**
 * Host tag assignment.
 *
 * The rule that matters most: the "add" dropdown must offer only tags the
 * host does NOT already carry. Offering an assigned tag invites an operator
 * to add a duplicate, which the server rejects — an error for doing exactly
 * what the UI suggested.
 *
 * The second rule is that a FAILED add or remove says so. Every one of these
 * paths ends in a snackbar, including the ones where the request itself
 * succeeded at the transport level but the server said no.
 */

import { act, renderHook, waitFor } from "@testing-library/react";
import { vi, describe, test, expect, beforeEach } from "vitest";

vi.mock("../../../Services/api", () => ({
  default: { get: vi.fn() },
}));

import axiosInstance from "../../../Services/api";
import { useHostTags } from "../../../Components/HostDetail/useHostTags";

const t = ((_k: string, fallback?: string) => fallback ?? _k) as never;

const tag = (id: string, name = id) => ({ id, name, description: null });

const snack = () => ({
  setSnackbarMessage: vi.fn(),
  setSnackbarSeverity: vi.fn(),
  setSnackbarOpen: vi.fn(),
});

const get = () => axiosInstance.get as ReturnType<typeof vi.fn>;

const setup = (opts: { hostId?: string } = {}) => {
  // An options object, not a defaulted parameter: `setup({ hostId: undefined })` would
  // apply the default and silently test the opposite of what it claims.
  const hostId = "hostId" in opts ? opts.hostId : "h1";
  const s = snack();
  const hook = renderHook(() => useHostTags({ hostId, t, ...s } as never));
  return { ...hook, ...s };
};

/** Let the hook's mount-time effects settle without an act() warning. */
const settle = async () => {
  await act(async () => {
    await new Promise((resolve) => setTimeout(resolve, 10));
  });
};

/** Route the two GETs this hook makes. */
const routeGets = (hostTags: unknown[], allTags: unknown[]) => {
  get().mockImplementation(async (url: string) =>
    url.endsWith("/tags") && url.includes("/hosts/")
      ? { status: 200, data: hostTags }
      : { status: 200, data: allTags },
  );
};

beforeEach(() => {
  vi.clearAllMocks();
  globalThis.fetch = vi.fn();
  localStorage.setItem("bearer_token", "tok");
});

describe("loading", () => {
  test("no host id means no requests at all", async () => {
    routeGets([], []);
    setup({ hostId: undefined });
    await settle();
    // The available-tags load is not host-scoped, so it still runs; the
    // host-scoped one must not.
    const hostScoped = get().mock.calls.filter((c) =>
      String(c[0]).includes("/hosts/"),
    );
    expect(hostScoped).toHaveLength(0);
  });

  test("assigned tags are loaded for the host", async () => {
    routeGets([tag("a"), tag("b")], [tag("a"), tag("b"), tag("c")]);
    const { result } = setup();
    await waitFor(() => expect(result.current.hostTags).toHaveLength(2));
  });

  test("available excludes tags the host already has", async () => {
    routeGets([tag("a")], [tag("a"), tag("b"), tag("c")]);
    const { result } = setup();
    await waitFor(() =>
      expect(result.current.availableTags.map((x) => x.id)).toEqual(["b", "c"]),
    );
  });

  test("a host with every tag has nothing left to offer", async () => {
    routeGets([tag("a"), tag("b")], [tag("a"), tag("b")]);
    const { result } = setup();
    await waitFor(() => expect(result.current.hostTags).toHaveLength(2));
    expect(result.current.availableTags).toEqual([]);
  });

  test("a failed load leaves the lists empty rather than crashing the tab", async () => {
    get().mockRejectedValue(new Error("boom"));
    const { result } = setup();
    await settle();
    expect(result.current.hostTags).toEqual([]);
    expect(result.current.availableTags).toEqual([]);
  });

  test("a non-200 response is not treated as data", async () => {
    get().mockResolvedValue({ status: 204, data: null });
    const { result } = setup();
    await settle();
    expect(result.current.hostTags).toEqual([]);
  });
});

describe("adding", () => {
  test("does nothing when no tag is selected", async () => {
    routeGets([], [tag("b")]);
    const { result } = setup();
    await act(async () => {
      await result.current.handleAddTag();
    });
    expect(globalThis.fetch).not.toHaveBeenCalled();
  });

  test("a successful add reports success and clears the selection", async () => {
    routeGets([], [tag("b")]);
    (globalThis.fetch as ReturnType<typeof vi.fn>).mockResolvedValue({
      ok: true,
    });
    const { result, setSnackbarSeverity, setSnackbarOpen } = setup();
    act(() => result.current.setSelectedTagToAdd("b"));
    await act(async () => {
      await result.current.handleAddTag();
    });
    expect(setSnackbarSeverity).toHaveBeenCalledWith("success");
    expect(setSnackbarOpen).toHaveBeenCalledWith(true);
    await waitFor(() => expect(result.current.selectedTagToAdd).toBe(""));
  });

  test("a server refusal is reported as an error", async () => {
    // ok:false is a real outcome -- the request went through and the server
    // said no. Reporting it as success would be a lie the operator acts on.
    routeGets([], [tag("b")]);
    (globalThis.fetch as ReturnType<typeof vi.fn>).mockResolvedValue({
      ok: false,
    });
    const { result, setSnackbarSeverity } = setup();
    act(() => result.current.setSelectedTagToAdd("b"));
    await act(async () => {
      await result.current.handleAddTag();
    });
    expect(setSnackbarSeverity).toHaveBeenCalledWith("error");
  });

  test("a network failure is reported as an error, not swallowed", async () => {
    routeGets([], [tag("b")]);
    (globalThis.fetch as ReturnType<typeof vi.fn>).mockRejectedValue(
      new Error("offline"),
    );
    const { result, setSnackbarSeverity } = setup();
    act(() => result.current.setSelectedTagToAdd("b"));
    await act(async () => {
      await result.current.handleAddTag();
    });
    expect(setSnackbarSeverity).toHaveBeenCalledWith("error");
  });

  test("the add carries the bearer token", async () => {
    routeGets([], [tag("b")]);
    (globalThis.fetch as ReturnType<typeof vi.fn>).mockResolvedValue({
      ok: true,
    });
    const { result } = setup();
    act(() => result.current.setSelectedTagToAdd("b"));
    await act(async () => {
      await result.current.handleAddTag();
    });
    const [url, init] = (globalThis.fetch as ReturnType<typeof vi.fn>).mock
      .calls[0];
    expect(url).toBe("/api/v1/hosts/h1/tags/b");
    expect(init.method).toBe("POST");
    expect(init.headers.Authorization).toBe("Bearer tok");
  });
});

describe("removing", () => {
  test("does nothing without a host id", async () => {
    routeGets([], []);
    const { result } = setup({ hostId: undefined });
    await act(async () => {
      await result.current.handleRemoveTag("a");
    });
    expect(globalThis.fetch).not.toHaveBeenCalled();
  });

  test("a successful remove reports success", async () => {
    routeGets([tag("a")], [tag("a")]);
    (globalThis.fetch as ReturnType<typeof vi.fn>).mockResolvedValue({
      ok: true,
    });
    const { result, setSnackbarSeverity } = setup();
    await act(async () => {
      await result.current.handleRemoveTag("a");
    });
    expect(setSnackbarSeverity).toHaveBeenCalledWith("success");
  });

  test("a refused remove is reported as an error", async () => {
    routeGets([tag("a")], [tag("a")]);
    (globalThis.fetch as ReturnType<typeof vi.fn>).mockResolvedValue({
      ok: false,
    });
    const { result, setSnackbarSeverity } = setup();
    await act(async () => {
      await result.current.handleRemoveTag("a");
    });
    expect(setSnackbarSeverity).toHaveBeenCalledWith("error");
  });

  test("a network failure during remove is reported", async () => {
    routeGets([tag("a")], [tag("a")]);
    (globalThis.fetch as ReturnType<typeof vi.fn>).mockRejectedValue(
      new Error("offline"),
    );
    const { result, setSnackbarSeverity } = setup();
    await act(async () => {
      await result.current.handleRemoveTag("a");
    });
    expect(setSnackbarSeverity).toHaveBeenCalledWith("error");
  });

  test("remove issues a DELETE to the tag's own URL", async () => {
    routeGets([tag("a")], [tag("a")]);
    (globalThis.fetch as ReturnType<typeof vi.fn>).mockResolvedValue({
      ok: true,
    });
    const { result } = setup();
    await act(async () => {
      await result.current.handleRemoveTag("a");
    });
    const [url, init] = (globalThis.fetch as ReturnType<typeof vi.fn>).mock
      .calls[0];
    expect(url).toBe("/api/v1/hosts/h1/tags/a");
    expect(init.method).toBe("DELETE");
  });
});
