/**
 * Phase 12.3: federation sites map (geographic flavour).
 *
 * Plots every enrolled site at its operator-supplied
 * ``(geo_latitude, geo_longitude)`` on an OpenStreetMap base layer.
 * Marker colour reflects status (enrolled green, pending yellow,
 * suspended red, other grey).  Clicking a marker opens a popup with
 * name + status + last-sync + a link to the site detail page.
 *
 * Differs from ``MapView`` (the per-host map from Phase 12.7) in
 * scale and density: sites are O(10-100), not O(1M), so no
 * clustering is needed.  Same Leaflet + OSM stack though.
 *
 * Sites without geo coordinates are silently skipped — the operator
 * may not have supplied lat/lng at enrollment, in which case the
 * site still appears in the grid view but not the map.
 */

import React, { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";

import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Stack from "@mui/material/Stack";
import CircularProgress from "@mui/material/CircularProgress";
import Typography from "@mui/material/Typography";

import L from "leaflet";
import "leaflet/dist/leaflet.css";

import {
  doListFederationSites,
  FederationSiteSummary,
} from "../Services/federation";

const TILE_URL = "https://tile.openstreetmap.org/{z}/{x}/{y}.png";
const TILE_ATTRIBUTION =
  '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>';
const DEFAULT_CENTER: [number, number] = [20, 0];
const DEFAULT_ZOOM = 2;

function colorForSiteStatus(status: FederationSiteSummary["status"]): string {
  switch (status) {
    case "enrolled":
      return "#2e7d32"; // green
    case "pending":
      return "#ed6c02"; // amber
    case "suspended":
      return "#c62828"; // red
    default:
      return "#757575"; // grey
  }
}

function makeSiteIcon(status: FederationSiteSummary["status"]): L.DivIcon {
  const color = colorForSiteStatus(status);
  return L.divIcon({
    className: "sysmanage-site-marker",
    html: `<span style="
      display: inline-block;
      width: 18px;
      height: 18px;
      border-radius: 50%;
      background-color: ${color};
      border: 3px solid white;
      box-shadow: 0 0 3px rgba(0,0,0,0.5);
    "></span>`,
    iconSize: [18, 18],
    iconAnchor: [9, 9],
    popupAnchor: [0, -12],
  });
}

function escapeHtml(value: string): string {
  return value
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function popupHtml(site: FederationSiteSummary, openLabel: string): string {
  const lines: string[] = [
    `<div style="font-weight:600;margin-bottom:4px;">${escapeHtml(site.name)}</div>`,
    `<div><b>Status:</b> ${escapeHtml(site.status)}</div>`,
  ];
  if (site.location_label) {
    lines.push(`<div>${escapeHtml(site.location_label)}</div>`);
  }
  if (site.last_sync_at) {
    lines.push(
      `<div><b>Last sync:</b> ${escapeHtml(
        new Date(site.last_sync_at).toLocaleString(),
      )}</div>`,
    );
  }
  lines.push(
    `<div style="margin-top:6px;">` +
      `<a href="#" data-site-id="${escapeHtml(site.id)}" ` +
      `class="sysmanage-site-popup-link" ` +
      `style="color:#1976d2;text-decoration:underline;cursor:pointer;">` +
      `${escapeHtml(openLabel)}</a>` +
      `</div>`,
  );
  return `<div style="min-width:200px;">${lines.join("")}</div>`;
}

interface SitesMapState {
  loading: boolean;
  licensed: boolean | null;
  sites: FederationSiteSummary[];
  error: string | null;
}

const SitesMap: React.FC = () => {
  const { t } = useTranslation();
  const navigate = useNavigate();

  const [state, setState] = useState<SitesMapState>({
    loading: true,
    licensed: null,
    sites: [],
    error: null,
  });

  const containerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<L.Map | null>(null);
  const markerGroupRef = useRef<L.LayerGroup | null>(null);

  // ---- Fetch site data once on mount ----
  useEffect(() => {
    let cancelled = false;
    doListFederationSites()
      .then((data) => {
        if (cancelled) return;
        setState({
          loading: false,
          licensed: Boolean(data.licensed),
          sites: data.sites ?? [],
          error: null,
        });
      })
      .catch((err) => {
        if (cancelled) return;
        setState({
          loading: false,
          licensed: null,
          sites: [],
          error:
            (err instanceof Error && err.message) ||
            t("sitesMap.errorLoad", "Failed to load federation sites."),
        });
      });
    return () => {
      cancelled = true;
    };
  }, [t]);

  // ---- Initialise the Leaflet map once the container is mounted ----
  useEffect(() => {
    const container = containerRef.current;
    if (!container || mapRef.current) return;

    const map = L.map(container).setView(DEFAULT_CENTER, DEFAULT_ZOOM);
    L.tileLayer(TILE_URL, {
      attribution: TILE_ATTRIBUTION,
      maxZoom: 18,
    }).addTo(map);
    mapRef.current = map;

    // Same flex-layout-not-settled defence as MapView.
    const invalidate = () => {
      try {
        map.invalidateSize();
      } catch {
        // map already torn down — fine.
      }
    };
    const rafId = window.requestAnimationFrame(invalidate);
    window.addEventListener("resize", invalidate);

    // Click-delegate for "Open site detail" links in popups.
    const onContainerClick = (event: globalThis.Event) => {
      const target = event.target as HTMLElement | null;
      if (!target) return;
      const link = target.closest(".sysmanage-site-popup-link");
      if (link instanceof HTMLElement) {
        event.preventDefault();
        const siteId = link.dataset.siteId;
        if (siteId) {
          navigate(`/sites/${encodeURIComponent(siteId)}`);
        }
      }
    };
    container.addEventListener("click", onContainerClick);

    const group = L.layerGroup().addTo(map);
    markerGroupRef.current = group;

    return () => {
      container.removeEventListener("click", onContainerClick);
      window.cancelAnimationFrame(rafId);
      window.removeEventListener("resize", invalidate);
      map.remove();
      mapRef.current = null;
      markerGroupRef.current = null;
    };
  }, [navigate]);

  // ---- Plot markers when both the map and the data are ready ----
  const openLabel = useMemo(
    () => t("sitesMap.openSite", "Open site"),
    [t],
  );
  useEffect(() => {
    const map = mapRef.current;
    const group = markerGroupRef.current;
    if (!map || !group) return;
    group.clearLayers();

    const latLngs: L.LatLngExpression[] = [];
    for (const site of state.sites) {
      if (
        typeof site.geo_latitude !== "number" ||
        typeof site.geo_longitude !== "number"
      ) {
        continue;
      }
      const marker = L.marker([site.geo_latitude, site.geo_longitude], {
        icon: makeSiteIcon(site.status),
        title: site.name,
      });
      marker.bindPopup(popupHtml(site, openLabel));
      group.addLayer(marker);
      latLngs.push([site.geo_latitude, site.geo_longitude]);
    }
    if (latLngs.length > 0) {
      const bounds = L.latLngBounds(latLngs);
      map.fitBounds(bounds.pad(0.2), { maxZoom: 8 });
    } else {
      map.setView(DEFAULT_CENTER, DEFAULT_ZOOM);
    }
  }, [state.sites, openLabel]);

  return (
    <Box sx={{ display: "flex", flexDirection: "column", height: "calc(100vh - 64px)" }}>
      <Box sx={{ p: 2 }}>
        <Box
          sx={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            mb: 1,
            gap: 2,
            flexWrap: "wrap",
          }}
        >
          <Box>
            <Typography variant="h5" component="h1">
              {t("sitesMap.title", "Federation Sites Map")}
            </Typography>
            <Typography variant="body2" color="text.secondary">
              {t(
                "sitesMap.subtitle",
                "Geographic distribution of subordinate site servers.",
              )}
            </Typography>
          </Box>
          <Stack direction="row" spacing={1}>
            <Button variant="outlined" onClick={() => navigate("/sites")}>
              {t("sitesMap.gridView", "Grid view")}
            </Button>
            <Button variant="outlined" onClick={() => navigate("/sites/tiles")}>
              {t("sitesMap.tilesView", "Dashboard")}
            </Button>
          </Stack>
        </Box>
        {state.licensed === false && (
          <Alert severity="info" sx={{ mb: 1 }}>
            {t(
              "sites.enterpriseRequired.body",
              "Federation lets you manage many SysManage servers from one coordinator. " +
                "Upgrade to an Enterprise license to enroll subordinate sites here.",
            )}
          </Alert>
        )}
        {state.error && (
          <Alert severity="warning" sx={{ mb: 1 }}>
            {state.error}
          </Alert>
        )}
      </Box>

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
          data-testid="sysmanage-sites-map-container"
          sx={{
            position: "absolute",
            inset: 0,
            border: "1px solid",
            borderColor: "divider",
            borderRadius: 1,
            overflow: "hidden",
          }}
        />
        {state.loading && (
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

export default SitesMap;
