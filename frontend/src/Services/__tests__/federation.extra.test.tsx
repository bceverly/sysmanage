// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

import { vi, describe, beforeEach, afterEach, test, expect } from "vitest";
import { renderHook, waitFor, act } from "@testing-library/react";

// Mock the axios instance the federation service imports.  Matches the
// mocking style in ``src/__tests__/Services/federation.test.tsx`` (same
// module path, same set of HTTP verbs) with ``put`` added for the
// alert-config endpoint.
vi.mock("../api", () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
    delete: vi.fn(),
    patch: vi.fn(),
    put: vi.fn(),
  },
}));

import axiosInstance from "../api";
import {
  doListFederationSites,
  doGetFederationSite,
  doEnrollFederationSite,
  doSuspendFederationSite,
  doResumeFederationSite,
  doRemoveFederationSite,
  doGetFederationSiteSyncStatus,
  doGetFederationSiteSyncTimeline,
  doListFederationAuditLog,
  doListFederationPolicies,
  doGetFederationPolicy,
  doCreateFederationPolicy,
  doUpdateFederationPolicy,
  doDeactivateFederationPolicy,
  doAssignFederationPolicy,
  doPushFederationPolicy,
  doRepushSitePolicies,
  doGetFederationAlertConfig,
  doUpdateFederationAlertConfig,
  doGetFederationCrossSiteReport,
  doListFederationCommands,
  probeFederationLicensed,
  useFederationLicensed,
  _resetFederationLicensedCacheForTests,
} from "../federation";

const mockGet = axiosInstance.get as unknown as ReturnType<typeof vi.fn>;
const mockPost = axiosInstance.post as unknown as ReturnType<typeof vi.fn>;
const mockDelete = axiosInstance.delete as unknown as ReturnType<typeof vi.fn>;
const mockPatch = axiosInstance.patch as unknown as ReturnType<typeof vi.fn>;
const mockPut = (axiosInstance as unknown as { put: ReturnType<typeof vi.fn> })
  .put;

beforeEach(() => {
  vi.clearAllMocks();
  _resetFederationLicensedCacheForTests();
});

// ---------------------------------------------------------------------
// Site CRUD / lifecycle
// ---------------------------------------------------------------------

describe("doListFederationSites", () => {
  test("GETs the sites endpoint and returns the envelope", async () => {
    const data = { licensed: true, sites: [{ id: "s1" }] };
    mockGet.mockResolvedValue({ data });
    const res = await doListFederationSites();
    expect(mockGet.mock.calls[0][0]).toBe("/api/v1/federation/sites");
    expect(res).toEqual(data);
  });
});

describe("doGetFederationSite", () => {
  test("encodes the site id in the path and returns the site", async () => {
    const data = { licensed: true, site: { id: "s 1" } };
    mockGet.mockResolvedValue({ data });
    const res = await doGetFederationSite("s 1");
    expect(mockGet.mock.calls[0][0]).toBe("/api/v1/federation/sites/s%201");
    expect(res).toEqual(data);
  });
});

describe("doEnrollFederationSite", () => {
  test("POSTs the enrollment body to /sites", async () => {
    const body = { name: "West", url: "https://west.example" };
    const data = { licensed: true, enrollment_token: "tok" };
    mockPost.mockResolvedValue({ data });
    const res = await doEnrollFederationSite(body);
    expect(mockPost.mock.calls[0][0]).toBe("/api/v1/federation/sites");
    expect(mockPost.mock.calls[0][1]).toEqual(body);
    expect(res).toEqual(data);
  });
});

describe("doSuspendFederationSite", () => {
  test("POSTs to the suspend action endpoint", async () => {
    mockPost.mockResolvedValue({ data: { licensed: true } });
    await doSuspendFederationSite("s1");
    expect(mockPost.mock.calls[0][0]).toBe(
      "/api/v1/federation/sites/s1/suspend",
    );
  });
});

describe("doResumeFederationSite", () => {
  test("POSTs to the resume action endpoint", async () => {
    mockPost.mockResolvedValue({ data: { licensed: true } });
    await doResumeFederationSite("s1");
    expect(mockPost.mock.calls[0][0]).toBe(
      "/api/v1/federation/sites/s1/resume",
    );
  });
});

describe("doRemoveFederationSite", () => {
  test("DELETEs the site and returns the ack envelope", async () => {
    const data = { licensed: true };
    mockDelete.mockResolvedValue({ data });
    const res = await doRemoveFederationSite("s1");
    expect(mockDelete.mock.calls[0][0]).toBe("/api/v1/federation/sites/s1");
    expect(res).toEqual(data);
  });
});

describe("doGetFederationSiteSyncStatus", () => {
  test("GETs the sync-status endpoint", async () => {
    const data = { licensed: true, status: { pending_queue_depth: 3 } };
    mockGet.mockResolvedValue({ data });
    const res = await doGetFederationSiteSyncStatus("s1");
    expect(mockGet.mock.calls[0][0]).toBe(
      "/api/v1/federation/sites/s1/sync-status",
    );
    expect(res).toEqual(data);
  });
});

describe("doGetFederationSiteSyncTimeline", () => {
  test("GETs the timeline with the default limit param", async () => {
    mockGet.mockResolvedValue({ data: { licensed: true, events: [] } });
    await doGetFederationSiteSyncTimeline("s1");
    expect(mockGet.mock.calls[0][0]).toBe(
      "/api/v1/federation/sites/s1/sync-timeline",
    );
    expect(mockGet.mock.calls[0][1]).toEqual({ params: { limit: 100 } });
  });

  test("passes an explicit limit", async () => {
    mockGet.mockResolvedValue({ data: { licensed: true, events: [] } });
    await doGetFederationSiteSyncTimeline("s1", 5);
    expect(mockGet.mock.calls[0][1]).toEqual({ params: { limit: 5 } });
  });
});

// ---------------------------------------------------------------------
// Audit log
// ---------------------------------------------------------------------

describe("doListFederationAuditLog", () => {
  test("GETs the audit endpoint with the given params", async () => {
    const data = { licensed: true, entries: [], total: 0 };
    mockGet.mockResolvedValue({ data });
    const params = { site_id: "s1", operation: "enroll", limit: 10 };
    const res = await doListFederationAuditLog(params);
    expect(mockGet.mock.calls[0][0]).toBe("/api/v1/federation/audit");
    expect(mockGet.mock.calls[0][1]).toEqual({ params });
    expect(res).toEqual(data);
  });

  test("defaults to an empty params object", async () => {
    mockGet.mockResolvedValue({ data: { licensed: true } });
    await doListFederationAuditLog();
    expect(mockGet.mock.calls[0][1]).toEqual({ params: {} });
  });
});

// ---------------------------------------------------------------------
// Policies
// ---------------------------------------------------------------------

describe("doListFederationPolicies", () => {
  test("GETs policies with params (and defaults to {})", async () => {
    mockGet.mockResolvedValue({ data: { licensed: true, policies: [] } });
    await doListFederationPolicies({ policy_type: "firewall_role", active_only: true });
    expect(mockGet.mock.calls[0][0]).toBe("/api/v1/federation/policies");
    expect(mockGet.mock.calls[0][1]).toEqual({
      params: { policy_type: "firewall_role", active_only: true },
    });

    mockGet.mockResolvedValue({ data: { licensed: true } });
    await doListFederationPolicies();
    expect(mockGet.mock.calls[1][1]).toEqual({ params: {} });
  });
});

describe("doGetFederationPolicy", () => {
  test("encodes the policy id in the path", async () => {
    const data = { licensed: true, policy: { id: "p/1" } };
    mockGet.mockResolvedValue({ data });
    const res = await doGetFederationPolicy("p/1");
    expect(mockGet.mock.calls[0][0]).toBe("/api/v1/federation/policies/p%2F1");
    expect(res).toEqual(data);
  });
});

describe("doCreateFederationPolicy", () => {
  test("POSTs the create body to /policies", async () => {
    const body = {
      policy_type: "update_profile",
      name: "Nightly",
      definition: { schedule: "0 3 * * *" },
    };
    mockPost.mockResolvedValue({ data: { licensed: true, policy: { id: "p1" } } });
    const res = await doCreateFederationPolicy(body);
    expect(mockPost.mock.calls[0][0]).toBe("/api/v1/federation/policies");
    expect(mockPost.mock.calls[0][1]).toEqual(body);
    expect(res.policy?.id).toBe("p1");
  });
});

describe("doUpdateFederationPolicy", () => {
  test("PATCHes the policy by encoded id", async () => {
    const body = { name: "Renamed" };
    mockPatch.mockResolvedValue({ data: { licensed: true, policy: { id: "p 1" } } });
    const res = await doUpdateFederationPolicy("p 1", body);
    expect(mockPatch.mock.calls[0][0]).toBe(
      "/api/v1/federation/policies/p%201",
    );
    expect(mockPatch.mock.calls[0][1]).toEqual(body);
    expect(res.policy?.id).toBe("p 1");
  });
});

describe("doDeactivateFederationPolicy", () => {
  test("DELETEs the policy by encoded id", async () => {
    mockDelete.mockResolvedValue({ data: { licensed: true } });
    await doDeactivateFederationPolicy("p1");
    expect(mockDelete.mock.calls[0][0]).toBe("/api/v1/federation/policies/p1");
  });
});

describe("doAssignFederationPolicy", () => {
  test("POSTs site_ids to the assign endpoint", async () => {
    mockPost.mockResolvedValue({ data: { licensed: true } });
    await doAssignFederationPolicy("p1", ["s1", "s2"]);
    expect(mockPost.mock.calls[0][0]).toBe(
      "/api/v1/federation/policies/p1/assign",
    );
    expect(mockPost.mock.calls[0][1]).toEqual({ site_ids: ["s1", "s2"] });
  });
});

describe("doPushFederationPolicy", () => {
  test("POSTs to the push endpoint", async () => {
    mockPost.mockResolvedValue({ data: { licensed: true } });
    await doPushFederationPolicy("p1");
    expect(mockPost.mock.calls[0][0]).toBe(
      "/api/v1/federation/policies/p1/push",
    );
  });
});

describe("doRepushSitePolicies", () => {
  test("POSTs to the per-site repush endpoint", async () => {
    const data = { licensed: true, requeued_count: 4 };
    mockPost.mockResolvedValue({ data });
    const res = await doRepushSitePolicies("s1");
    expect(mockPost.mock.calls[0][0]).toBe(
      "/api/v1/federation/sites/s1/repush-policies",
    );
    expect(res.requeued_count).toBe(4);
  });
});

// ---------------------------------------------------------------------
// Alert config
// ---------------------------------------------------------------------

describe("doGetFederationAlertConfig", () => {
  test("GETs the alert-config endpoint", async () => {
    const data = { licensed: true, effective: {}, overrides: {} };
    mockGet.mockResolvedValue({ data });
    const res = await doGetFederationAlertConfig();
    expect(mockGet.mock.calls[0][0]).toBe("/api/v1/federation/alert-config");
    expect(res).toEqual(data);
  });
});

describe("doUpdateFederationAlertConfig", () => {
  test("PUTs the overrides to the alert-config endpoint", async () => {
    const overrides = { offline_multiplier: 3 };
    mockPut.mockResolvedValue({ data: { licensed: true } });
    await doUpdateFederationAlertConfig(overrides);
    expect(mockPut.mock.calls[0][0]).toBe("/api/v1/federation/alert-config");
    expect(mockPut.mock.calls[0][1]).toEqual(overrides);
  });
});

// ---------------------------------------------------------------------
// Cross-site report
// ---------------------------------------------------------------------

describe("doGetFederationCrossSiteReport", () => {
  test("joins siteIds into a site_ids param", async () => {
    mockGet.mockResolvedValue({ data: { licensed: true, sites: [], totals: {} } });
    await doGetFederationCrossSiteReport(["s1", "s2"]);
    expect(mockGet.mock.calls[0][0]).toBe("/api/v1/federation/reports/rollup");
    expect(mockGet.mock.calls[0][1]).toEqual({ params: { site_ids: "s1,s2" } });
  });

  test("omits params when siteIds is empty or undefined", async () => {
    mockGet.mockResolvedValue({ data: { licensed: true, sites: [], totals: {} } });
    await doGetFederationCrossSiteReport([]);
    expect(mockGet.mock.calls[0][1]).toEqual({ params: undefined });

    mockGet.mockResolvedValue({ data: { licensed: true, sites: [], totals: {} } });
    await doGetFederationCrossSiteReport();
    expect(mockGet.mock.calls[1][1]).toEqual({ params: undefined });
  });
});

// ---------------------------------------------------------------------
// Commands
// ---------------------------------------------------------------------

describe("doListFederationCommands", () => {
  test("builds a query string from the provided filters", async () => {
    mockGet.mockResolvedValue({ data: { licensed: true, commands: [] } });
    await doListFederationCommands({
      site_id: "s1",
      status: "in_progress",
      open_only: true,
      limit: 20,
      offset: 5,
    });
    const url = mockGet.mock.calls[0][0] as string;
    expect(url).toContain("/api/v1/federation/commands?");
    expect(url).toContain("site_id=s1");
    expect(url).toContain("status=in_progress");
    expect(url).toContain("open_only=true");
    expect(url).toContain("limit=20");
    expect(url).toContain("offset=5");
  });

  test("emits a bare endpoint when no filters are set", async () => {
    mockGet.mockResolvedValue({ data: { licensed: true, commands: [] } });
    await doListFederationCommands({});
    expect(mockGet.mock.calls[0][0]).toBe("/api/v1/federation/commands");
  });

  test("open_only=false is omitted from the query", async () => {
    mockGet.mockResolvedValue({ data: { licensed: true, commands: [] } });
    await doListFederationCommands({ open_only: false });
    expect(mockGet.mock.calls[0][0]).toBe("/api/v1/federation/commands");
  });
});

// ---------------------------------------------------------------------
// License probe + hook + cache reset
// ---------------------------------------------------------------------

describe("probeFederationLicensed", () => {
  afterEach(() => {
    localStorage.clear();
  });

  test("returns false without a bearer token (no network call)", async () => {
    localStorage.removeItem("bearer_token");
    const licensed = await probeFederationLicensed();
    expect(licensed).toBe(false);
    expect(mockGet).not.toHaveBeenCalled();
  });

  test("fetches, caches licensed=true, and reuses the cache", async () => {
    localStorage.setItem("bearer_token", "abc");
    mockGet.mockResolvedValue({ data: { licensed: true, sites: [] } });
    const first = await probeFederationLicensed();
    expect(first).toBe(true);
    expect(mockGet).toHaveBeenCalledTimes(1);
    // Second call hits the module-scope cache — no new request.
    const second = await probeFederationLicensed();
    expect(second).toBe(true);
    expect(mockGet).toHaveBeenCalledTimes(1);
  });

  test("treats a rejected probe as not-licensed", async () => {
    localStorage.setItem("bearer_token", "abc");
    mockGet.mockRejectedValue(new Error("boom"));
    const licensed = await probeFederationLicensed();
    expect(licensed).toBe(false);
  });

  test("coalesces concurrent probes into a single in-flight promise", async () => {
    localStorage.setItem("bearer_token", "abc");
    mockGet.mockResolvedValue({ data: { licensed: false } });
    const [a, b] = await Promise.all([
      probeFederationLicensed(),
      probeFederationLicensed(),
    ]);
    expect(a).toBe(false);
    expect(b).toBe(false);
    expect(mockGet).toHaveBeenCalledTimes(1);
  });
});

describe("useFederationLicensed", () => {
  afterEach(() => {
    localStorage.clear();
  });

  test("resolves loading→false with the probed licensed flag", async () => {
    localStorage.setItem("bearer_token", "abc");
    mockGet.mockResolvedValue({ data: { licensed: true } });
    const { result } = renderHook(() => useFederationLicensed());
    // First render before the probe resolves.
    expect(result.current.loading).toBe(true);
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.licensed).toBe(true);
  });

  test("skips the loading flash when the cache is already warm", async () => {
    localStorage.setItem("bearer_token", "abc");
    mockGet.mockResolvedValue({ data: { licensed: true } });
    // Warm the module-scope cache first.
    await probeFederationLicensed();
    const { result } = renderHook(() => useFederationLicensed());
    expect(result.current.loading).toBe(false);
    expect(result.current.licensed).toBe(true);
    // The effect still kicks off a background re-probe whose resolved
    // promise setState()s after this test body — flush it inside act() so
    // React doesn't warn about an update outside act().
    await act(async () => {
      await Promise.resolve();
    });
  });
});

describe("_resetFederationLicensedCacheForTests", () => {
  afterEach(() => {
    localStorage.clear();
  });

  test("clears the cache so the next probe re-fetches", async () => {
    localStorage.setItem("bearer_token", "abc");
    mockGet.mockResolvedValue({ data: { licensed: true } });
    await probeFederationLicensed();
    expect(mockGet).toHaveBeenCalledTimes(1);
    _resetFederationLicensedCacheForTests();
    await probeFederationLicensed();
    expect(mockGet).toHaveBeenCalledTimes(2);
  });
});
