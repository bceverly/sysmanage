// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

/**
 * Host Detail's initial data load.
 *
 * The order of the guards is the whole point. No bearer token means redirect
 * to login BEFORE anything is fetched — issuing a dozen requests that will
 * all 401 is both noisy and slow. A missing host id is a bad URL, not a
 * server failure, and must say so rather than spinning forever.
 *
 * The optional subsystems (Ubuntu Pro, antivirus defaults, certificates,
 * child hosts) are each allowed to fail without taking the page down: a host
 * that is not an Ubuntu Pro subscriber is not a broken host.
 */

import { act, renderHook, waitFor } from "@testing-library/react";
import { vi, describe, test, expect, beforeEach } from "vitest";

vi.mock("../../../Services/api", () => ({
  default: { get: vi.fn() },
}));

vi.mock("../../../Services/hosts", () => ({
  doGetHostByID: vi.fn(),
  doGetHostStorage: vi.fn(),
  doGetHostNetwork: vi.fn(),
  doGetHostUsers: vi.fn(),
  doGetHostGroups: vi.fn(),
  doGetHostDiagnostics: vi.fn(),
  doGetHostUbuntuPro: vi.fn(),
}));

vi.mock("../../../Services/users", () => ({ doGetMe: vi.fn() }));
vi.mock("../../../Services/license", () => ({ getLicenseInfo: vi.fn() }));

import axiosInstance from "../../../Services/api";
import {
  doGetHostByID,
  doGetHostStorage,
  doGetHostNetwork,
  doGetHostUsers,
  doGetHostGroups,
  doGetHostDiagnostics,
  doGetHostUbuntuPro,
} from "../../../Services/hosts";
import { doGetMe } from "../../../Services/users";
import { getLicenseInfo } from "../../../Services/license";
import { useHostData } from "../../../Components/HostDetail/useHostData";

const m = (fn: unknown) => fn as ReturnType<typeof vi.fn>;
const t = ((_k: string, fallback?: string) => fallback ?? _k) as never;

const host = (over = {}) => ({
  id: "h1",
  fqdn: "host.invalid",
  platform: "Linux",
  active: true,
  ...over,
});

const setters = () => ({
  setHost: vi.fn(),
  setStorageDevices: vi.fn(),
  setNetworkInterfaces: vi.fn(),
  setUserAccounts: vi.fn(),
  setUserGroups: vi.fn(),
  setDiagnosticsData: vi.fn(),
  setCurrentUser: vi.fn(),
  setUbuntuProInfo: vi.fn(),
  setHasAntivirusOsDefault: vi.fn(),
  setLoading: vi.fn(),
  setError: vi.fn(),
  setLicenseModules: vi.fn(),
  setLicenseFeatures: vi.fn(),
});

const fetchers = () => ({
  fetchCertificates: vi.fn().mockResolvedValue(undefined),
  fetchRoles: vi.fn().mockResolvedValue(undefined),
  fetchChildHosts: vi.fn().mockResolvedValue(undefined),
  fetchVirtualizationStatus: vi.fn().mockResolvedValue(undefined),
});

const setup = (opts: { hostId?: string } = {}) => {
  const hostId = "hostId" in opts ? opts.hostId : "h1";
  const navigate = vi.fn();
  const s = setters();
  const f = fetchers();
  const hook = renderHook(() =>
    useHostData({ hostId, navigate, t, ...s, ...f } as never),
  );
  return { ...hook, navigate, ...s, ...f };
};

const settle = async () => {
  await act(async () => {
    await new Promise((resolve) => setTimeout(resolve, 20));
  });
};

beforeEach(() => {
  vi.clearAllMocks();
  localStorage.setItem("bearer_token", "tok");
  m(getLicenseInfo).mockResolvedValue({ modules: [], features: [] });
  m(doGetHostByID).mockResolvedValue(host());
  m(doGetHostStorage).mockResolvedValue([]);
  m(doGetHostNetwork).mockResolvedValue([]);
  m(doGetHostUsers).mockResolvedValue([]);
  m(doGetHostGroups).mockResolvedValue([]);
  m(doGetHostDiagnostics).mockResolvedValue([]);
  m(doGetHostUbuntuPro).mockResolvedValue(null);
  m(doGetMe).mockResolvedValue({ userid: "op@invalid" });
  m(axiosInstance.get).mockResolvedValue({ data: {} });
});

describe("guards", () => {
  test("no bearer token redirects to login and fetches nothing", async () => {
    // A dozen requests that will all 401 is noise on the way to the same
    // outcome.
    localStorage.removeItem("bearer_token");
    const { navigate } = setup();
    await settle();
    expect(navigate).toHaveBeenCalledWith("/login");
    expect(m(doGetHostByID)).not.toHaveBeenCalled();
  });

  test("a missing host id is a bad URL, reported as such", async () => {
    const { setError, setLoading } = setup({ hostId: undefined });
    await settle();
    expect(setError).toHaveBeenCalledWith("Invalid host ID");
    // And loading must stop, or the page spins forever on a typo.
    expect(setLoading).toHaveBeenCalledWith(false);
    expect(m(doGetHostByID)).not.toHaveBeenCalled();
  });
});

describe("the happy path", () => {
  test("the host and its inventory are loaded", async () => {
    const { setHost } = setup();
    await waitFor(() => expect(m(doGetHostByID)).toHaveBeenCalledWith("h1"));
    await settle();
    expect(setHost).toHaveBeenCalled();
    expect(m(doGetHostStorage)).toHaveBeenCalledWith("h1");
    expect(m(doGetHostNetwork)).toHaveBeenCalledWith("h1");
    expect(m(doGetHostUsers)).toHaveBeenCalledWith("h1");
    expect(m(doGetHostGroups)).toHaveBeenCalledWith("h1");
  });

  test("the optional subsystem fetchers are invoked", async () => {
    const { fetchCertificates, fetchRoles } = setup();
    await settle();
    expect(fetchCertificates).toHaveBeenCalled();
    expect(fetchRoles).toHaveBeenCalled();
  });

  test("loading is cleared when the load finishes", async () => {
    const { setLoading } = setup();
    await settle();
    expect(setLoading).toHaveBeenCalledWith(false);
  });

  test("licence modules are resolved for the tab set", async () => {
    m(getLicenseInfo).mockResolvedValue({
      modules: ["config_management_engine"],
      features: ["reports"],
    });
    const { setLicenseModules } = setup();
    await waitFor(() => expect(setLicenseModules).toHaveBeenCalled());
  });
});

describe("degradation", () => {
  test("a failing host fetch reports an error rather than a blank page", async () => {
    m(doGetHostByID).mockRejectedValue(new Error("404"));
    const { setError, setLoading } = setup();
    await settle();
    expect(setError).toHaveBeenCalledWith("Failed to load host details");
    expect(setLoading).toHaveBeenCalledWith(false);
  });

  test("a failing licence lookup does not stop the host loading", async () => {
    // The licence decides which TABS appear; losing it must not lose the host.
    m(getLicenseInfo).mockRejectedValue(new Error("no licence service"));
    setup();
    await waitFor(() => expect(m(doGetHostByID)).toHaveBeenCalled());
  });

  test("a failing antivirus-defaults probe is not fatal", async () => {
    // It only decides whether a Deploy button is offered.
    m(axiosInstance.get).mockRejectedValue(new Error("404"));
    const { setError } = setup();
    await settle();
    expect(setError).not.toHaveBeenCalledWith("Failed to load host details");
  });

  test("a failing inventory fetch still clears loading", async () => {
    // Otherwise the page spins forever behind a partial failure.
    m(doGetHostStorage).mockRejectedValue(new Error("agent offline"));
    const { setLoading } = setup();
    await settle();
    expect(setLoading).toHaveBeenCalledWith(false);
  });
});
