// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

import { vi, describe, beforeEach, test, expect } from "vitest";

// Mock the axios instance the federation service imports.
vi.mock("../../Services/api", () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
    delete: vi.fn(),
    patch: vi.fn(),
  },
}));

import axiosInstance from "../../Services/api";
import {
  doSearchFederationHosts,
  doGetFederationHostDetail,
  doDispatchFederationCommand,
  doListFederationAlerts,
  doAcknowledgeFederationAlert,
  doGetFederationDashboardRollup,
} from "../../Services/federation";

const mockGet = axiosInstance.get as unknown as ReturnType<typeof vi.fn>;
const mockPost = axiosInstance.post as unknown as ReturnType<typeof vi.fn>;

beforeEach(() => {
  vi.clearAllMocks();
});

describe("doSearchFederationHosts", () => {
  test("builds query string from provided filters only", async () => {
    mockGet.mockResolvedValue({ data: { licensed: true, hosts: [], total: 0 } });
    await doSearchFederationHosts({
      site_id: "s1",
      free_text: "web",
      status: "up",
      limit: 25,
      offset: 0,
    });
    const url = mockGet.mock.calls[0][0] as string;
    expect(url).toContain("/api/v1/federation/hosts?");
    expect(url).toContain("site_id=s1");
    expect(url).toContain("free_text=web");
    expect(url).toContain("status=up");
    expect(url).toContain("limit=25");
    // Empty / undefined filters are omitted.
    expect(url).not.toContain("os_family=");
  });

  test("returns the payload", async () => {
    const payload = { licensed: true, hosts: [{ host_id: "h1" }], total: 1 };
    mockGet.mockResolvedValue({ data: payload });
    const res = await doSearchFederationHosts({ site_id: "s1" });
    expect(res).toEqual(payload);
  });

  test("no filters → bare endpoint with no query string", async () => {
    mockGet.mockResolvedValue({ data: { licensed: true } });
    await doSearchFederationHosts({});
    expect(mockGet.mock.calls[0][0]).toBe("/api/v1/federation/hosts");
  });
});

describe("doGetFederationHostDetail", () => {
  test("encodes the host id in the path", async () => {
    mockGet.mockResolvedValue({ data: { licensed: true, host: null } });
    await doGetFederationHostDetail("host/with space");
    expect(mockGet.mock.calls[0][0]).toBe(
      "/api/v1/federation/hosts/host%2Fwith%20space",
    );
  });
});

describe("doGetFederationDashboardRollup", () => {
  test("passes site_id and returns rollup", async () => {
    const data = { licensed: true, compliance_rollups: [], vulnerability_rollup: null };
    mockGet.mockResolvedValue({ data });
    const res = await doGetFederationDashboardRollup("s1");
    expect(mockGet.mock.calls[0][0]).toBe(
      "/api/v1/federation/rollups/dashboard?site_id=s1",
    );
    expect(res).toEqual(data);
  });
});

describe("doDispatchFederationCommand", () => {
  test("POSTs the dispatch body to the dispatch endpoint", async () => {
    mockPost.mockResolvedValue({ data: { licensed: true, command: { id: "c1" } } });
    const body = {
      command_type: "reboot",
      target_site_id: "s1",
      parameters: null,
      target_host_ids: ["h1", "h2"],
    };
    const res = await doDispatchFederationCommand(body);
    expect(mockPost.mock.calls[0][0]).toBe(
      "/api/v1/federation/commands/dispatch",
    );
    expect(mockPost.mock.calls[0][1]).toEqual(body);
    expect(res.command?.id).toBe("c1");
  });
});

describe("federation alerts", () => {
  test("doListFederationAlerts builds query + returns alerts", async () => {
    mockGet.mockResolvedValue({ data: { licensed: true, alerts: [{ id: "a1" }] } });
    const res = await doListFederationAlerts({
      site_id: "s1",
      include_resolved: true,
    });
    const url = mockGet.mock.calls[0][0] as string;
    expect(url).toContain("/api/v1/federation/alerts?");
    expect(url).toContain("site_id=s1");
    expect(url).toContain("include_resolved=true");
    expect(res.alerts?.[0].id).toBe("a1");
  });

  test("doAcknowledgeFederationAlert POSTs to the ack endpoint", async () => {
    mockPost.mockResolvedValue({ data: { licensed: true, alert: { id: "a1" } } });
    await doAcknowledgeFederationAlert("a1");
    expect(mockPost.mock.calls[0][0]).toBe(
      "/api/v1/federation/alerts/a1/acknowledge",
    );
  });
});
