/**
 * Phase 12.7: world map of geo-located hosts.
 *
 * Renders an OpenStreetMap base layer (via Leaflet) with one marker
 * per host that has a resolved (latitude, longitude).  Markers are
 * grouped via ``leaflet.markercluster`` so the view stays usable at
 * thousand-host scale.  Click a marker -> popup with hostname /
 * status / location + a link to the host detail page.
 *
 * Notable design choices:
 *   * No third-party tile provider — uses tile.openstreetmap.org
 *     directly, matching the project's no-third-party-tracker stance.
 *   * Cluster plugin loaded via dynamic import inside useEffect so
 *     it stays out of the initial JS bundle for users who never
 *     visit /map.
 *   * Self-bounding: on first load, the map zooms to fit all hosts'
 *     bounding box.  Empty fleet -> world view (0,0 zoom=2).
 *   * Marker color reflects host.status: green for "up", red for
 *     "down", grey for unknown.  Custom DivIcon avoids the default
 *     "broken-image" sprite that Leaflet ships with (its bundled
 *     marker sprite paths don't resolve under Vite without extra
 *     plumbing).
 */

import React, { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";

import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import Alert from "@mui/material/Alert";
import CircularProgress from "@mui/material/CircularProgress";

import L from "leaflet";
import "leaflet/dist/leaflet.css";
import "leaflet.markercluster";
import "leaflet.markercluster/dist/MarkerCluster.css";
import "leaflet.markercluster/dist/MarkerCluster.Default.css";

import { doGetHostGeolocations, HostGeolocation } from "../Services/geolocations";

// Leaflet + leaflet.markercluster are both bundled by Vite from
// node_modules — no runtime CDN, no third-party trackers, no
// external font requests.  Tile imagery still comes from
// tile.openstreetmap.org per the no-tracker compromise (OSM's tile
// servers are donation-funded and don't log identifiers).

const TILE_URL = "https://tile.openstreetmap.org/{z}/{x}/{y}.png";
const TILE_ATTRIBUTION =
  '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>';
const DEFAULT_CENTER: [number, number] = [20, 0]; // roughly center-of-mass for an empty fleet
const DEFAULT_ZOOM = 2;

/** Map a host status to a CSS color for the marker dot. */
function colorForStatus(status: string | null): string {
  switch ((status || "").toLowerCase()) {
    case "up":
      return "#2e7d32"; // MUI green 800
    case "down":
      return "#c62828"; // MUI red 800
    default:
      return "#757575"; // MUI grey 600
  }
}

/** Build a DivIcon for a host marker.  Pure HTML/CSS — no sprite. */
function makeHostIcon(status: string | null): L.DivIcon {
  const color = colorForStatus(status);
  return L.divIcon({
    className: "sysmanage-host-marker",
    html: `<span style="
      display: inline-block;
      width: 14px;
      height: 14px;
      border-radius: 50%;
      background-color: ${color};
      border: 2px solid white;
      box-shadow: 0 0 2px rgba(0,0,0,0.5);
    "></span>`,
    iconSize: [14, 14],
    iconAnchor: [7, 7],
    popupAnchor: [0, -8],
  });
}

/**
 * Build a popup body for a host marker.  HTML string — Leaflet's
 * default popup renderer takes that, and we keep this simple
 * rather than rendering a React component into the popup (which
 * react-leaflet supports but adds complexity we don't need here).
 */
function popupHtml(host: HostGeolocation, openLabel: string): string {
  const safeFqdn = escapeHtml(host.fqdn);
  const cityLine = (() => {
    if (host.city) {
      const subdivisionPart = host.subdivision_code
        ? `, ${escapeHtml(host.subdivision_code)}`
        : "";
      const countryPart = host.country_code
        ? ` (${escapeHtml(host.country_code)})`
        : "";
      return `<div>${escapeHtml(host.city)}${subdivisionPart}${countryPart}</div>`;
    }
    if (host.country_code) {
      return `<div>${escapeHtml(host.country_code)}</div>`;
    }
    return "";
  })();
  const statusLine = host.status
    ? `<div><b>Status:</b> ${escapeHtml(host.status)}</div>`
    : "";
  return `
    <div style="min-width: 200px;">
      <div style="font-weight: 600; margin-bottom: 4px;">${safeFqdn}</div>
      ${statusLine}
      ${cityLine}
      <div style="margin-top: 6px;">
        <a href="#" data-host-id="${escapeHtml(host.host_id)}"
           class="sysmanage-host-popup-link"
           style="color: #1976d2; text-decoration: underline; cursor: pointer;">
          ${escapeHtml(openLabel)}
        </a>
      </div>
    </div>
  `;
}

function escapeHtml(value: string): string {
  return value
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

const MapView: React.FC = () => {
  const { t } = useTranslation();
  const navigate = useNavigate();

  const [hosts, setHosts] = useState<HostGeolocation[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  // The map + cluster-group refs persist across re-renders so we
  // mutate the existing instance rather than rebuilding it on every
  // hosts-data fetch.
  const containerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<L.Map | null>(null);
  const clusterGroupRef = useRef<L.LayerGroup | null>(null);

  // --- Fetch host data once on mount.  Future enhancement: poll or
  // subscribe to a websocket for live updates as hosts come online.
  useEffect(() => {
    let cancelled = false;
    doGetHostGeolocations()
      .then((data) => {
        if (!cancelled) {
          setHosts(data);
        }
      })
      .catch((err) => {
        if (!cancelled) {
          setError(
            err?.message ||
              t(
                "map.errorLoadHosts",
                "Failed to load host locations.",
              ),
          );
          setHosts([]);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [t]);

  // --- Initialize the Leaflet map once we have the container DOM
  // node.  Dynamic-import the markercluster plugin so it stays out
  // of the bundle for users who don't visit /map.
  useEffect(() => {
    // Capture the container at effect start so the cleanup doesn't
    // chase containerRef.current after React has detached it.
    const container = containerRef.current;
    if (!container || mapRef.current) {
      return;
    }
    const map = L.map(container).setView(DEFAULT_CENTER, DEFAULT_ZOOM);
    L.tileLayer(TILE_URL, {
      attribution: TILE_ATTRIBUTION,
      maxZoom: 18,
    }).addTo(map);
    mapRef.current = map;

    // Leaflet measures container size at construction time.  If the
    // surrounding flex layout hasn't fully settled (e.g. when the
    // page mounts inside a still-laying-out parent) the map renders
    // a blank gray/white square because its internal panes are sized
    // to 0x0.  Force a remeasure on the next animation frame and on
    // window resize.
    const invalidate = () => {
      try {
        map.invalidateSize();
      } catch {
        // map already torn down — fine.
      }
    };
    const rafId = globalThis.requestAnimationFrame(invalidate);
    globalThis.addEventListener("resize", invalidate);

    // Click-delegate for "Open host" links inside marker popups.
    // Leaflet popups render into the map container; capturing clicks
    // here lets us route to /hosts/<id> via react-router without
    // putting an event listener on every popup string.
    const onContainerClick = (event: globalThis.Event) => {
      const target = event.target as HTMLElement | null;
      if (!target) return;
      const link = target.closest(".sysmanage-host-popup-link");
      if (link instanceof HTMLElement) {
        event.preventDefault();
        const hostId = link.dataset.hostId;
        if (hostId) {
          navigate(`/hosts/${hostId}`);
        }
      }
    };
    container.addEventListener("click", onContainerClick);

    // leaflet.markercluster is statically imported at the top of this
    // file, so ``L.markerClusterGroup`` is available synchronously.
    // Fall back to a plain layer group if the plugin isn't present
    // (defensive — shouldn't happen in a normal build).
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const clusterFactory = (L as any).markerClusterGroup;
    const group: L.LayerGroup = clusterFactory
      ? clusterFactory()
      : L.layerGroup();
    group.addTo(map);
    clusterGroupRef.current = group;

    return () => {
      container.removeEventListener("click", onContainerClick);
      globalThis.cancelAnimationFrame(rafId);
      globalThis.removeEventListener("resize", invalidate);
      map.remove();
      mapRef.current = null;
      clusterGroupRef.current = null;
    };
  }, [navigate]);

  // --- Plot markers once both the map AND the host data are ready.
  // Re-runs if hosts change (e.g. after a future live-update hook).
  const openHostLabel = useMemo(
    () => t("map.openHost", "Open host"),
    [t],
  );
  useEffect(() => {
    const map = mapRef.current;
    const group = clusterGroupRef.current;
    if (!map || !group || !hosts) {
      return;
    }
    // Clear any markers from a previous render.
    group.clearLayers();

    if (hosts.length === 0) {
      map.setView(DEFAULT_CENTER, DEFAULT_ZOOM);
      return;
    }

    const latLngs: L.LatLngExpression[] = [];
    for (const host of hosts) {
      if (
        typeof host.latitude !== "number" ||
        typeof host.longitude !== "number"
      ) {
        continue;
      }
      const marker = L.marker([host.latitude, host.longitude], {
        icon: makeHostIcon(host.status),
        title: host.fqdn,
      });
      marker.bindPopup(popupHtml(host, openHostLabel));
      group.addLayer(marker);
      latLngs.push([host.latitude, host.longitude]);
    }

    if (latLngs.length > 0) {
      const bounds = L.latLngBounds(latLngs);
      map.fitBounds(bounds.pad(0.2), { maxZoom: 10 });
    }
  }, [hosts, openHostLabel]);

  return (
    <Box sx={{ display: "flex", flexDirection: "column", height: "calc(100vh - 64px)" }}>
      <Box sx={{ p: 2 }}>
        <Typography variant="h5" component="h1">
          {t("map.title", "Host Map")}
        </Typography>
        <Typography variant="body2" color="text.secondary">
          {t(
            "map.subtitle",
            "Geographic distribution of agents that have reported a public IP.",
          )}
        </Typography>
      </Box>
      {error && (
        <Alert severity="warning" sx={{ mx: 2, mb: 1 }}>
          {error}
        </Alert>
      )}
      {/* Map container is mounted unconditionally so the init effect's
          containerRef is non-null on the first commit.  Spinner is
          overlaid while hosts are still loading. */}
      <Box
        sx={{
          position: "relative",
          flex: 1,
          mx: 2,
          mb: 2,
          minHeight: 400,
        }}
      >
        <Box
          ref={containerRef}
          data-testid="sysmanage-map-container"
          sx={{
            position: "absolute",
            inset: 0,
            border: "1px solid",
            borderColor: "divider",
            borderRadius: 1,
            overflow: "hidden",
          }}
        />
        {hosts === null && (
          <Box
            sx={{
              position: "absolute",
              inset: 0,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              backgroundColor: "rgba(255,255,255,0.6)",
              zIndex: 1000,
              pointerEvents: "none",
            }}
          >
            <CircularProgress />
          </Box>
        )}
      </Box>
    </Box>
  );
};

export default MapView;
