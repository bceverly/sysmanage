// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

/**
 * The small Host Detail hooks: snackbar, tab navigation, certificate grid.
 *
 * Tab navigation is the one with teeth. It maps a URL hash to a tab index in
 * three separate places (initial load, browser back/forward, and a
 * recalculation when dynamic tabs appear), and every one of them indexes an
 * array by a value taken from the address bar. A hash naming a tab that does
 * not exist must select nothing rather than land on index -1.
 */

import { act, renderHook } from "@testing-library/react";
import { vi, describe, test, expect, beforeEach } from "vitest";

import { useHostSnackbar } from "../../../Components/HostDetail/useHostSnackbar";
import { useHostTabNavigation } from "../../../Components/HostDetail/useHostTabNavigation";
import { useCertificateGrid } from "../../../Components/HostDetail/useCertificateGrid";

const t = ((_key: string, fallback?: string) =>
  fallback ?? _key) as unknown as Parameters<
  typeof useHostTabNavigation
>[0]["t"];

describe("useHostSnackbar", () => {
  test("starts closed with a success severity", () => {
    const { result } = renderHook(() => useHostSnackbar());
    expect(result.current.snackbarOpen).toBe(false);
    expect(result.current.snackbarMessage).toBe("");
    expect(result.current.snackbarSeverity).toBe("success");
  });

  test("a normal close dismisses it", () => {
    const { result } = renderHook(() => useHostSnackbar());
    act(() => result.current.setSnackbarOpen(true));
    act(() =>
      result.current.handleCloseSnackbar({} as never, "timeout"),
    );
    expect(result.current.snackbarOpen).toBe(false);
  });

  test("a clickaway does NOT dismiss it", () => {
    // Clicking elsewhere while an error is showing must not wipe the message
    // before it has been read -- that is the whole reason for the exception.
    const { result } = renderHook(() => useHostSnackbar());
    act(() => result.current.setSnackbarOpen(true));
    act(() =>
      result.current.handleCloseSnackbar({} as never, "clickaway"),
    );
    expect(result.current.snackbarOpen).toBe(true);
  });

  test("severity and message are settable for the action hooks to share", () => {
    const { result } = renderHook(() => useHostSnackbar());
    act(() => {
      result.current.setSnackbarMessage("it broke");
      result.current.setSnackbarSeverity("error");
    });
    expect(result.current.snackbarMessage).toBe("it broke");
    expect(result.current.snackbarSeverity).toBe("error");
  });
});

describe("useHostTabNavigation", () => {
  const tabs = [
    { id: "info", label: "Info" },
    { id: "hardware", label: "Hardware" },
    { id: "security", label: "Security" },
    { id: "child-hosts", label: "Child Hosts" },
  ];

  const setup = (over: Record<string, unknown> = {}) => {
    const setCurrentTab = vi.fn();
    const hook = renderHook(() =>
      useHostTabNavigation({
        tabDefinitions: tabs,
        currentTab: 0,
        setCurrentTab,
        host: null,
        ubuntuProInfo: null,
        t,
        ...over,
      } as never),
    );
    return { ...hook, setCurrentTab };
  };

  beforeEach(() => {
    globalThis.location.hash = "";
  });

  test("tabs are grouped into their left-rail categories", () => {
    const { result } = setup();
    const groups = result.current.hostTabGroups;
    expect(groups.map((g) => g.id)).toEqual([
      "overview",
      "security",
      "virtualization",
    ]);
    expect(groups[0].tabs.map((x) => x.id)).toEqual(["info", "hardware"]);
  });

  test("categories with no tabs drop out entirely", () => {
    // A host shows only the categories it actually has tabs in; an empty
    // "Software" heading with nothing under it is just noise.
    const { result } = setup({ tabDefinitions: [{ id: "info", label: "I" }] });
    expect(result.current.hostTabGroups.map((g) => g.id)).toEqual(["overview"]);
  });

  test("an unknown tab id falls back to overview rather than vanishing", () => {
    const { result } = setup({
      tabDefinitions: [{ id: "not-a-real-tab", label: "X" }],
    });
    expect(result.current.hostTabGroups.map((g) => g.id)).toEqual(["overview"]);
  });

  test("groups follow the declared category order, not tab order", () => {
    const { result } = setup({
      tabDefinitions: [
        { id: "child-hosts", label: "C" },
        { id: "info", label: "I" },
      ],
    });
    expect(result.current.hostTabGroups.map((g) => g.id)).toEqual([
      "overview",
      "virtualization",
    ]);
  });

  test("changing tab writes the tab id to the URL hash", () => {
    const { result, setCurrentTab } = setup();
    act(() => result.current.handleTabChange({} as never, 2));
    expect(setCurrentTab).toHaveBeenCalledWith(2);
    expect(globalThis.location.hash).toBe("#security");
  });

  test("an out-of-range index changes the tab but writes no hash", () => {
    // The bounds check is what keeps `tabs[newValue]` from writing
    // "#undefined" into the address bar.
    const { result } = setup();
    act(() => result.current.handleTabChange({} as never, 99));
    expect(globalThis.location.hash).toBe("");
  });

  test("a hashchange to a known tab selects it", () => {
    const { setCurrentTab } = setup();
    globalThis.location.hash = "#security";
    act(() => {
      globalThis.dispatchEvent(new Event("hashchange"));
    });
    expect(setCurrentTab).toHaveBeenCalledWith(2);
  });

  test("a hashchange naming an unknown tab selects nothing", () => {
    // indexOf returns -1; acting on it would blank the page.
    const { setCurrentTab } = setup();
    setCurrentTab.mockClear();
    globalThis.location.hash = "#does-not-exist";
    act(() => {
      globalThis.dispatchEvent(new Event("hashchange"));
    });
    expect(setCurrentTab).not.toHaveBeenCalled();
  });

  test("an empty hash is ignored rather than resetting the tab", () => {
    const { setCurrentTab } = setup();
    setCurrentTab.mockClear();
    globalThis.location.hash = "";
    act(() => {
      globalThis.dispatchEvent(new Event("hashchange"));
    });
    expect(setCurrentTab).not.toHaveBeenCalled();
  });

  test("the listener is removed on unmount", () => {
    const remove = vi.spyOn(globalThis, "removeEventListener");
    const { unmount } = setup();
    unmount();
    expect(remove).toHaveBeenCalledWith("hashchange", expect.any(Function));
    remove.mockRestore();
  });
});

describe("useCertificateGrid", () => {
  test("defaults to server certificates", () => {
    // Server certs are what an operator came to look at; CA and client certs
    // are the long tail.
    const { result } = renderHook(() => useCertificateGrid());
    expect(result.current.certificateFilter).toBe("server");
    expect(result.current.certificateSearchTerm).toBe("");
  });

  test("filter and search are settable", () => {
    const { result } = renderHook(() => useCertificateGrid());
    act(() => {
      result.current.setCertificateFilter("ca");
      result.current.setCertificateSearchTerm("acme");
    });
    expect(result.current.certificateFilter).toBe("ca");
    expect(result.current.certificateSearchTerm).toBe("acme");
  });

  test("the active page size is always among the options", () => {
    // MUI warns loudly when paginationModel.pageSize is not in
    // pageSizeOptions, and the dynamic sizing can land off the fixed list.
    const { result } = renderHook(() => useCertificateGrid());
    expect(result.current.safePageSizeOptions).toContain(
      result.current.certificatePaginationModel.pageSize,
    );
  });

  test("an off-list page size is merged in, in sorted order", () => {
    const { result } = renderHook(() => useCertificateGrid());
    act(() =>
      result.current.setCertificatePaginationModel({ page: 0, pageSize: 37 }),
    );
    const options = result.current.safePageSizeOptions;
    expect(options).toContain(37);
    expect([...options]).toEqual([...options].sort((a, b) => a - b));
  });
});
