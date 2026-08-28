// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

/**
 * Antivirus actions on a single host.
 *
 * Every one of these dispatches a real change to a managed machine, so the
 * property that matters is that the operator is never told something worked
 * when it did not. Deploy is the subtle one: the request can return 200 while
 * the body reports the host in `failed_hosts`, and reading only the HTTP
 * status would show a success snackbar for a deployment that never happened.
 */

import { act, renderHook, waitFor } from "@testing-library/react";
import { vi, describe, test, expect, beforeEach, afterEach } from "vitest";

vi.mock("../../../Services/api", () => ({
  default: { post: vi.fn() },
}));

import axiosInstance from "../../../Services/api";
import { useHostAntivirus } from "../../../Components/HostDetail/useHostAntivirus";

const t = ((_k: string, fallback?: string) => fallback ?? _k) as never;
const post = () => axiosInstance.post as ReturnType<typeof vi.fn>;

const setup = (opts: { host?: unknown } = {}) => {
  const host = "host" in opts ? opts.host : { id: "h1", fqdn: "a.invalid" };
  const s = {
    setSnackbarMessage: vi.fn(),
    setSnackbarSeverity: vi.fn(),
    setSnackbarOpen: vi.fn(),
  };
  const hook = renderHook(() => useHostAntivirus({ host, t, ...s } as never));
  return { ...hook, ...s };
};

beforeEach(() => {
  vi.clearAllMocks();
  vi.useFakeTimers({ shouldAdvanceTime: true });
  post().mockResolvedValue({ data: {} });
});

afterEach(() => {
  vi.useRealTimers();
});

describe("guarding on a host", () => {
  test.each([
    ["handleDeployAntivirus"],
    ["handleEnableAntivirus"],
    ["handleDisableAntivirus"],
    ["handleRemoveAntivirus"],
  ])("%s does nothing without a host", async (name) => {
    const { result } = setup({ host: null });
    await act(async () => {
      await (result.current as unknown as Record<string, () => Promise<void>>)[name]();
    });
    expect(post()).not.toHaveBeenCalled();
  });
});

describe("deploy", () => {
  test("a clean response reports success", async () => {
    const { result, setSnackbarSeverity } = setup();
    await act(async () => {
      await result.current.handleDeployAntivirus();
    });
    expect(post()).toHaveBeenCalledWith("/api/v1/deploy", { host_ids: ["h1"] });
    expect(setSnackbarSeverity).toHaveBeenCalledWith("success");
  });

  test("a 200 carrying failed_hosts is reported as a FAILURE", async () => {
    // The request succeeded; the deployment did not. Reading only the status
    // would show a green snackbar for a host that got nothing.
    post().mockResolvedValue({
      data: { failed_hosts: [{ reason: "no package for this OS" }] },
    });
    const { result, setSnackbarSeverity } = setup();
    await act(async () => {
      await result.current.handleDeployAntivirus();
    });
    expect(setSnackbarSeverity).toHaveBeenCalledWith("error");
  });

  test("an empty failed_hosts array is still a success", async () => {
    post().mockResolvedValue({ data: { failed_hosts: [] } });
    const { result, setSnackbarSeverity } = setup();
    await act(async () => {
      await result.current.handleDeployAntivirus();
    });
    expect(setSnackbarSeverity).toHaveBeenCalledWith("success");
  });

  test("a transport failure is reported, not swallowed", async () => {
    post().mockRejectedValue(new Error("offline"));
    const { result, setSnackbarSeverity, setSnackbarOpen } = setup();
    await act(async () => {
      await result.current.handleDeployAntivirus();
    });
    expect(setSnackbarSeverity).toHaveBeenCalledWith("error");
    expect(setSnackbarOpen).toHaveBeenCalledWith(true);
  });

  test("a success schedules a refresh so the panel catches up", async () => {
    // The agent needs time to act; without the delayed refresh the panel
    // shows the pre-deploy state and looks like nothing happened.
    const { result } = setup();
    const before = result.current.antivirusRefreshTrigger;
    await act(async () => {
      await result.current.handleDeployAntivirus();
    });
    await act(async () => {
      vi.advanceTimersByTime(10_000);
    });
    await waitFor(() =>
      expect(result.current.antivirusRefreshTrigger).toBeGreaterThan(before),
    );
  });

  test("a failure does NOT schedule a refresh", async () => {
    post().mockRejectedValue(new Error("offline"));
    const { result } = setup();
    const before = result.current.antivirusRefreshTrigger;
    await act(async () => {
      await result.current.handleDeployAntivirus();
    });
    await act(async () => {
      vi.advanceTimersByTime(10_000);
    });
    expect(result.current.antivirusRefreshTrigger).toBe(before);
  });
});

describe("enable, disable and remove", () => {
  test.each([
    ["handleEnableAntivirus", "/api/v1/hosts/h1/antivirus/enable"],
    ["handleDisableAntivirus", "/api/v1/hosts/h1/antivirus/disable"],
  ])("%s posts to %s", async (name, url) => {
    const { result, setSnackbarSeverity } = setup();
    await act(async () => {
      await (result.current as unknown as Record<string, () => Promise<void>>)[name]();
    });
    expect(post()).toHaveBeenCalledWith(url);
    expect(setSnackbarSeverity).toHaveBeenCalledWith("success");
  });

  test.each([
    ["handleEnableAntivirus"],
    ["handleDisableAntivirus"],
    ["handleRemoveAntivirus"],
  ])("%s reports a failure rather than claiming success", async (name) => {
    post().mockRejectedValue(new Error("agent gone"));
    const { result, setSnackbarSeverity } = setup();
    await act(async () => {
      await (result.current as unknown as Record<string, () => Promise<void>>)[name]();
    });
    expect(setSnackbarSeverity).toHaveBeenCalledWith("error");
  });

  test("remove targets this host's own endpoint", async () => {
    const { result } = setup();
    await act(async () => {
      await result.current.handleRemoveAntivirus();
    });
    expect(String(post().mock.calls[0][0])).toContain("h1");
  });
});
