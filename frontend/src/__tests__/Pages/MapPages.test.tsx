// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

/**
 * The two Leaflet map pages: host geolocation and federation sites.
 *
 * Leaflet touches real DOM measurement that jsdom does not implement, so the
 * library is replaced with a recording stub. That is not a cop-out: what
 * matters here is not that Leaflet draws, it is that the page asks for the
 * right data, survives a host with no coordinates, and does not blow up when
 * the fetch fails — all of which the stub lets us observe directly.
 *
 * A host without a fix is the normal case, not an edge case: geolocation is
 * best-effort and plenty of hosts never resolve. A page that throws on a null
 * latitude would be blank for most fleets.
 */

import { render, waitFor } from "@testing-library/react";
import { vi, describe, test, expect, beforeEach } from "vitest";

const t = (key: string, fallback?: string) =>
  typeof fallback === "string" ? fallback : key;
vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t, i18n: { language: "en" } }),
}));

const navigate = vi.fn();
vi.mock("react-router", () => ({ useNavigate: () => navigate }));

// A recording Leaflet stub. Every builder returns a chainable object so the
// pages' fluent calls work unchanged.
const chain = () => {
  const o: Record<string, unknown> = {};
  for (const k of [
    "addTo",
    "addLayer",
    "removeLayer",
    "clearLayers",
    "setView",
    "fitBounds",
    "bindPopup",
    "on",
    "off",
    "remove",
    "invalidateSize",
    "openPopup",
  ]) {
    o[k] = vi.fn(() => o);
  }
  return o;
};

const created = { markers: 0, maps: 0 };

vi.mock("leaflet", () => {
  const L = {
    map: vi.fn(() => {
      created.maps += 1;
      return chain();
    }),
    tileLayer: vi.fn(() => chain()),
    marker: vi.fn(() => {
      created.markers += 1;
      return chain();
    }),
    layerGroup: vi.fn(() => chain()),
    divIcon: vi.fn(() => ({})),
    latLngBounds: vi.fn(() => {
      const b: Record<string, unknown> = {
        isValid: () => true,
        extend: vi.fn(),
      };
      b.pad = vi.fn(() => b);
      return b;
    }),
    markerClusterGroup: vi.fn(() => chain()),
  };
  return { default: L, ...L };
});
vi.mock("leaflet/dist/leaflet.css", () => ({}));
vi.mock("leaflet.markercluster", () => ({}));
vi.mock("leaflet.markercluster/dist/MarkerCluster.css", () => ({}));
vi.mock("leaflet.markercluster/dist/MarkerCluster.Default.css", () => ({}));

vi.mock("../../Services/geolocations", () => ({
  doGetHostGeolocations: vi.fn(),
}));

vi.mock("../../Services/federation", () => ({
  doListFederationSites: vi.fn(),
}));

import { doGetHostGeolocations } from "../../Services/geolocations";
import { doListFederationSites } from "../../Services/federation";
import MapView from "../../Pages/MapView";
import SitesMap from "../../Pages/SitesMap";

const m = (fn: unknown) => fn as ReturnType<typeof vi.fn>;

const located = (over = {}) => ({
  host_id: "h1",
  fqdn: "host.invalid",
  status: "up",
  platform: "Linux",
  country_code: "GB",
  subdivision_code: null,
  city: "London",
  latitude: 51.5,
  longitude: -0.12,
  ...over,
});

beforeEach(() => {
  vi.clearAllMocks();
  created.markers = 0;
  created.maps = 0;
  m(doGetHostGeolocations).mockResolvedValue([located()]);
  m(doListFederationSites).mockResolvedValue({ licensed: true, sites: [] });
});

describe("MapView", () => {
  test("asks for host geolocations on mount", async () => {
    render(<MapView />);
    await waitFor(() => expect(m(doGetHostGeolocations)).toHaveBeenCalled());
  });

  test("a fetch failure leaves the page rendered rather than blank", async () => {
    m(doGetHostGeolocations).mockRejectedValue(new Error("no geo service"));
    render(<MapView />);
    await waitFor(() => expect(m(doGetHostGeolocations)).toHaveBeenCalled());
    expect(document.body.textContent).not.toBe("");
  });

  test("an empty fleet renders without attempting to fit empty bounds", async () => {
    m(doGetHostGeolocations).mockResolvedValue([]);
    render(<MapView />);
    await waitFor(() => expect(m(doGetHostGeolocations)).toHaveBeenCalled());
    expect(document.body.textContent).not.toBe("");
  });

  test("hosts without coordinates do not crash the page", async () => {
    // Geolocation is best-effort; most fleets have some hosts with no fix.
    m(doGetHostGeolocations).mockResolvedValue([
      located({ latitude: null, longitude: null }),
      located({ host_id: "h2", latitude: undefined, longitude: undefined }),
    ]);
    render(<MapView />);
    await waitFor(() => expect(m(doGetHostGeolocations)).toHaveBeenCalled());
    expect(document.body.textContent).not.toBe("");
  });

  test("a null city or status renders without a popup crash", async () => {
    // Every one of these is nullable in HostGeolocation, and the popup builds
    // raw HTML from them.
    m(doGetHostGeolocations).mockResolvedValue([
      located({ city: null, status: null, country_code: null }),
    ]);
    render(<MapView />);
    await waitFor(() => expect(m(doGetHostGeolocations)).toHaveBeenCalled());
    expect(document.body.textContent).not.toBe("");
  });

  test("an fqdn containing HTML is escaped, not injected", async () => {
    // The popup is built as a raw HTML string, so a hostile hostname is a
    // script-injection vector into the operator's own browser.
    m(doGetHostGeolocations).mockResolvedValue([
      located({ fqdn: '<img src=x onerror="alert(1)">' }),
    ]);
    render(<MapView />);
    await waitFor(() => expect(m(doGetHostGeolocations)).toHaveBeenCalled());
    expect(document.querySelector("img")).toBeNull();
  });
});

describe("SitesMap", () => {
  test("asks for the federation sites on mount", async () => {
    render(<SitesMap />);
    await waitFor(() => expect(m(doListFederationSites)).toHaveBeenCalled());
  });

  test("an unlicensed server is told so rather than shown an empty map", async () => {
    m(doListFederationSites).mockResolvedValue({ licensed: false, sites: [] });
    render(<SitesMap />);
    await waitFor(() => expect(m(doListFederationSites)).toHaveBeenCalled());
    expect(document.body.textContent).not.toBe("");
  });

  test("sites without coordinates are handled", async () => {
    m(doListFederationSites).mockResolvedValue({
      licensed: true,
      sites: [
        { id: "s1", name: "dc1", latitude: null, longitude: null },
        { id: "s2", name: "dc2", latitude: 40.7, longitude: -74 },
      ],
    });
    render(<SitesMap />);
    await waitFor(() => expect(m(doListFederationSites)).toHaveBeenCalled());
    expect(document.body.textContent).not.toBe("");
  });

  test("a fetch failure does not blank the page", async () => {
    m(doListFederationSites).mockRejectedValue(new Error("coordinator down"));
    render(<SitesMap />);
    await waitFor(() => expect(m(doListFederationSites)).toHaveBeenCalled());
    expect(document.body.textContent).not.toBe("");
  });

  test("a response with no sites key is treated as empty", async () => {
    m(doListFederationSites).mockResolvedValue({ licensed: true });
    render(<SitesMap />);
    await waitFor(() => expect(m(doListFederationSites)).toHaveBeenCalled());
    expect(document.body.textContent).not.toBe("");
  });
});
