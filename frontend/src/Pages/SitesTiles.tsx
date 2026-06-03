/**
 * Phase 12.3: federation tile dashboard (the "screen-of-glass" map flavor).
 *
 * Same per-site data as the Sites grid and the geographic map, rendered as
 * a hub-and-spoke board: the coordinator at top, every enrolled site below
 * as a status-coloured tile.  No geography — built to scan at a glance for
 * a war-room / wall display.  Like both other flavors it renders only at
 * SITE granularity, never individual agents.
 *
 * View toggles ("Grid view" / "Map view") round-trip to the other two
 * flavors.  OSS / unlicensed → the same Enterprise upsell.
 */

import React, { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";

import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Card from "@mui/material/Card";
import CardActionArea from "@mui/material/CardActionArea";
import CardContent from "@mui/material/CardContent";
import Chip from "@mui/material/Chip";
import CircularProgress from "@mui/material/CircularProgress";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";

import {
  doListFederationSites,
  FederationSiteSummary,
} from "../Services/federation";

type StatusColor = "success" | "warning" | "error" | "default";

function statusColor(status: FederationSiteSummary["status"]): StatusColor {
  switch (status) {
    case "enrolled":
      return "success";
    case "pending":
      return "warning";
    case "suspended":
      return "error";
    default:
      return "default";
  }
}

/** Map the chip color onto a theme palette key for the tile accent. */
const ACCENT: Record<StatusColor, string> = {
  success: "success.main",
  warning: "warning.main",
  error: "error.main",
  default: "text.disabled",
};

function relativeSync(iso: string | null | undefined, locale: string): string {
  if (!iso) return "—";
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return "—";
  const diffSec = Math.round((then - Date.now()) / 1000);
  const abs = Math.abs(diffSec);
  const rtf = new Intl.RelativeTimeFormat(locale, { numeric: "auto" });
  if (abs < 60) return rtf.format(Math.round(diffSec), "second");
  if (abs < 3600) return rtf.format(Math.round(diffSec / 60), "minute");
  if (abs < 86400) return rtf.format(Math.round(diffSec / 3600), "hour");
  return rtf.format(Math.round(diffSec / 86400), "day");
}

interface TilesState {
  loading: boolean;
  licensed: boolean | null;
  sites: FederationSiteSummary[];
  error: string | null;
}

const SitesTiles: React.FC = () => {
  const { t, i18n } = useTranslation();
  const navigate = useNavigate();

  const [state, setState] = useState<TilesState>({
    loading: true,
    licensed: null,
    sites: [],
    error: null,
  });

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
            t("sitesTiles.errorLoad", "Failed to load sites."),
        });
      });
    return () => {
      cancelled = true;
    };
  }, [t]);

  // Aggregate counts for the coordinator hub summary.
  const counts = useMemo(() => {
    const c = { enrolled: 0, pending: 0, suspended: 0, other: 0, hosts: 0 };
    for (const s of state.sites) {
      c.hosts += s.host_count ?? 0;
      if (s.status === "enrolled") c.enrolled += 1;
      else if (s.status === "pending") c.pending += 1;
      else if (s.status === "suspended") c.suspended += 1;
      else c.other += 1;
    }
    return c;
  }, [state.sites]);

  if (state.loading) {
    return (
      <Box sx={{ p: 3, display: "flex", justifyContent: "center" }}>
        <CircularProgress />
      </Box>
    );
  }

  if (state.error) {
    return (
      <Box sx={{ p: 3 }}>
        <Alert severity="error">{state.error}</Alert>
      </Box>
    );
  }

  if (state.licensed === false) {
    return (
      <Box sx={{ p: 3 }}>
        <Alert severity="info">
          <Typography variant="subtitle1" component="div">
            {t(
              "sites.enterpriseRequired.title",
              "Multi-site federation requires Enterprise",
            )}
          </Typography>
          <Typography variant="body2">
            {t(
              "sites.enterpriseRequired.body",
              "Federation lets you manage many SysManage servers from one coordinator. " +
                "Upgrade to an Enterprise license to enroll subordinate sites here.",
            )}
          </Typography>
        </Alert>
      </Box>
    );
  }

  return (
    <Box sx={{ p: 3 }}>
      <Stack
        direction="row"
        justifyContent="space-between"
        alignItems="center"
        sx={{ mb: 2, flexWrap: "wrap", gap: 1 }}
      >
        <Typography variant="h5" component="h1">
          {t("sitesTiles.title", "Federation Dashboard")}
        </Typography>
        <Stack direction="row" spacing={1}>
          <Button
            variant="outlined"
            onClick={() => navigate("/sites")}
            data-testid="tiles-grid-toggle"
          >
            {t("sitesTiles.gridView", "Grid view")}
          </Button>
          <Button
            variant="outlined"
            onClick={() => navigate("/sites/map")}
            data-testid="tiles-map-toggle"
          >
            {t("sitesTiles.mapView", "Map view")}
          </Button>
        </Stack>
      </Stack>

      {/* Coordinator hub --------------------------------------------- */}
      <Card
        variant="outlined"
        sx={{
          mb: 1,
          borderColor: "primary.main",
          borderWidth: 2,
          textAlign: "center",
        }}
      >
        <CardContent>
          <Typography variant="overline" color="primary">
            {t("sitesTiles.coordinator", "Coordinator")}
          </Typography>
          <Typography variant="h6">
            {t("sitesTiles.coordinatorThisServer", "This server")}
          </Typography>
          <Stack
            direction="row"
            spacing={1}
            justifyContent="center"
            sx={{ mt: 1, flexWrap: "wrap" }}
          >
            <Chip
              size="small"
              color="success"
              label={t("sitesTiles.countEnrolled", "{{n}} enrolled", {
                n: counts.enrolled,
              })}
            />
            {counts.pending > 0 && (
              <Chip
                size="small"
                color="warning"
                label={t("sitesTiles.countPending", "{{n}} pending", {
                  n: counts.pending,
                })}
              />
            )}
            {counts.suspended > 0 && (
              <Chip
                size="small"
                color="error"
                label={t("sitesTiles.countSuspended", "{{n}} suspended", {
                  n: counts.suspended,
                })}
              />
            )}
            <Chip
              size="small"
              variant="outlined"
              label={t("sitesTiles.countHosts", "{{n}} hosts", {
                n: counts.hosts,
              })}
            />
          </Stack>
        </CardContent>
      </Card>

      {/* Spoke connector ---------------------------------------------- */}
      <Box
        sx={{
          height: 16,
          width: 2,
          mx: "auto",
          bgcolor: "divider",
        }}
      />

      {/* Site tiles --------------------------------------------------- */}
      {state.sites.length === 0 ? (
        <Alert severity="info">
          {t("sitesTiles.empty", "No sites enrolled yet.")}
        </Alert>
      ) : (
        <Box
          sx={{
            display: "grid",
            gap: 2,
            gridTemplateColumns:
              "repeat(auto-fill, minmax(220px, 1fr))",
          }}
        >
          {state.sites.map((s) => {
            const color = statusColor(s.status);
            return (
              <Card
                key={s.id}
                variant="outlined"
                sx={{ borderTop: 4, borderTopColor: ACCENT[color] }}
              >
                <CardActionArea
                  onClick={() =>
                    navigate(`/sites/${encodeURIComponent(s.id)}`)
                  }
                  sx={{ height: "100%" }}
                >
                  <CardContent>
                    <Stack
                      direction="row"
                      justifyContent="space-between"
                      alignItems="flex-start"
                      spacing={1}
                    >
                      <Typography
                        variant="subtitle1"
                        sx={{ fontWeight: 600, wordBreak: "break-word" }}
                      >
                        {s.name}
                      </Typography>
                      <Chip label={s.status} size="small" color={color} />
                    </Stack>
                    {s.location_label && (
                      <Typography variant="caption" color="text.secondary">
                        {s.location_label}
                      </Typography>
                    )}
                    <Stack spacing={0.25} sx={{ mt: 1 }}>
                      <Typography variant="body2">
                        {t("sitesTiles.hostsLabel", "{{n}} hosts", {
                          n: s.host_count ?? 0,
                        })}
                      </Typography>
                      <Typography variant="caption" color="text.secondary">
                        {t("sitesTiles.lastSync", "Synced {{when}}", {
                          when: relativeSync(s.last_sync_at, i18n.language),
                        })}
                      </Typography>
                    </Stack>
                  </CardContent>
                </CardActionArea>
              </Card>
            );
          })}
        </Box>
      )}
    </Box>
  );
};

export default SitesTiles;
