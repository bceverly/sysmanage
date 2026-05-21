/**
 * Phase 12.3: federation Sites page.
 *
 * Lists every subordinate site server registered with this coordinator.
 * On OSS / Community / unlicensed Enterprise installs the backend
 * returns ``{licensed: false}`` and this page renders an Enterprise
 * upsell instead of the empty Sites grid (otherwise a fresh install
 * looks broken when the user clicks the nav link).
 *
 * When ``licensed: true`` and the sites array is populated, each site
 * renders as a card with name, location, host count, connection
 * status traffic-light, last-sync timestamp.  Detailed site drill-down
 * (sync history, audit log, push-policy action) is deferred to a
 * future slice once 12.1.B+ ships real CRUD handlers.
 */

import React, { useCallback, useEffect, useState } from "react";
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
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogContentText from "@mui/material/DialogContentText";
import DialogTitle from "@mui/material/DialogTitle";
import Grid from "@mui/material/Grid";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";

import {
  doEnrollFederationSite,
  doListFederationSites,
  FederationSiteSummary,
} from "../Services/federation";

/** MUI chip color for a federation site's status. */
function statusChipColor(
  status: FederationSiteSummary["status"],
): "success" | "warning" | "error" | "default" {
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

/** Format a UTC ISO timestamp as "5m ago" / "2h ago" / "yesterday". */
function formatRelative(iso: string | null | undefined): string | null {
  if (!iso) return null;
  const ts = new Date(iso).getTime();
  if (Number.isNaN(ts)) return null;
  const deltaSec = Math.max(0, (Date.now() - ts) / 1000);
  if (deltaSec < 60) return "just now";
  if (deltaSec < 3600) return `${Math.floor(deltaSec / 60)}m ago`;
  if (deltaSec < 86400) return `${Math.floor(deltaSec / 3600)}h ago`;
  return `${Math.floor(deltaSec / 86400)}d ago`;
}

interface SitesPageState {
  loading: boolean;
  licensed: boolean | null;
  sites: FederationSiteSummary[];
  fetchError: string | null;
}

interface EnrollDialogState {
  open: boolean;
  submitting: boolean;
  name: string;
  url: string;
  location_label: string;
  sync_interval_seconds: string;
  error: string | null;
  /** Plaintext token from the latest successful enrollment; shown
   * once to the operator and cleared when the dialog closes. */
  token: string | null;
}

const EMPTY_ENROLL: EnrollDialogState = {
  open: false,
  submitting: false,
  name: "",
  url: "",
  location_label: "",
  sync_interval_seconds: "300",
  error: null,
  token: null,
};

const Sites: React.FC = () => {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [state, setState] = useState<SitesPageState>({
    loading: true,
    licensed: null,
    sites: [],
    fetchError: null,
  });
  const [enroll, setEnroll] = useState<EnrollDialogState>(EMPTY_ENROLL);

  const fetchSites = useCallback(async () => {
    try {
      const data = await doListFederationSites();
      setState({
        loading: false,
        licensed: Boolean(data.licensed),
        sites: data.sites ?? [],
        fetchError: null,
      });
    } catch (err) {
      setState({
        loading: false,
        licensed: null,
        sites: [],
        fetchError:
          (err instanceof Error && err.message) ||
          t("sites.errorLoad", "Failed to load federation sites."),
      });
    }
  }, [t]);

  useEffect(() => {
    let cancelled = false;
    setState((prev) => ({ ...prev, loading: true }));
    doListFederationSites()
      .then((data) => {
        if (cancelled) return;
        setState({
          loading: false,
          licensed: Boolean(data.licensed),
          sites: data.sites ?? [],
          fetchError: null,
        });
      })
      .catch((err) => {
        if (cancelled) return;
        setState({
          loading: false,
          licensed: null,
          sites: [],
          fetchError:
            (err instanceof Error && err.message) ||
            t("sites.errorLoad", "Failed to load federation sites."),
        });
      });
    return () => {
      cancelled = true;
    };
  }, [t]);

  const handleSubmitEnroll = async () => {
    if (enroll.submitting) return;
    setEnroll((prev) => ({ ...prev, submitting: true, error: null }));
    try {
      const parsedInterval = Number.parseInt(
        enroll.sync_interval_seconds,
        10,
      );
      const response = await doEnrollFederationSite({
        name: enroll.name.trim(),
        url: enroll.url.trim(),
        location_label: enroll.location_label.trim() || null,
        sync_interval_seconds: Number.isFinite(parsedInterval)
          ? parsedInterval
          : undefined,
      });
      if (!response.licensed) {
        setEnroll((prev) => ({
          ...prev,
          submitting: false,
          error: t(
            "sites.enroll.engineUnavailable",
            "The federation controller engine is not loaded; cannot enroll a site.",
          ),
        }));
        return;
      }
      setEnroll((prev) => ({
        ...prev,
        submitting: false,
        token: response.enrollment_token ?? null,
      }));
      await fetchSites();
    } catch (err) {
      setEnroll((prev) => ({
        ...prev,
        submitting: false,
        error:
          (err instanceof Error && err.message) ||
          t("sites.enroll.error", "Failed to enroll site."),
      }));
    }
  };

  const closeEnrollDialog = () => {
    if (!enroll.submitting) {
      setEnroll(EMPTY_ENROLL);
    }
  };

  return (
    <Box sx={{ p: 3 }}>
      <Box
        sx={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          mb: 1,
          gap: 2,
          flexWrap: "wrap",
        }}
      >
        <Typography variant="h5" component="h1">
          {t("sites.title", "Federation Sites")}
        </Typography>
        <Box sx={{ display: "flex", gap: 1, flexWrap: "wrap" }}>
          {/* Federation action buttons are hidden entirely when the
              engine isn't loaded — same rule as the navbar Sites
              link.  The buttons would otherwise navigate to pages
              that all show the Enterprise upsell, which is the
              wrong UX for OSS users. */}
          {state.licensed === true && (
            <>
              <Button
                variant="outlined"
                onClick={() => navigate("/sites/map")}
                data-testid="sites-map-toggle"
              >
                {t("sites.mapView", "Map view")}
              </Button>
              <Button
                variant="outlined"
                onClick={() => navigate("/federation/policies")}
                data-testid="sites-policies-link"
              >
                {t("sites.policiesLink", "Policies")}
              </Button>
              <Button
                variant="contained"
                onClick={() => setEnroll({ ...EMPTY_ENROLL, open: true })}
                data-testid="add-site-button"
              >
                {t("sites.addSite", "Enroll Site")}
              </Button>
            </>
          )}
        </Box>
      </Box>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 3 }}>
        {t(
          "sites.subtitle",
          "Subordinate SysManage servers enrolled with this coordinator.",
        )}
      </Typography>

      {state.loading && (
        <Box sx={{ display: "flex", justifyContent: "center", p: 4 }}>
          <CircularProgress />
        </Box>
      )}

      {!state.loading && state.fetchError && (
        <Alert severity="error">{state.fetchError}</Alert>
      )}

      {!state.loading &&
        !state.fetchError &&
        state.licensed === false && (
          <Alert severity="info" sx={{ mb: 2 }}>
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
        )}

      {!state.loading &&
        !state.fetchError &&
        state.licensed === true &&
        state.sites.length === 0 && (
          <Alert severity="info">
            {t(
              "sites.empty",
              "No sites are enrolled yet. Enroll a subordinate SysManage server to get started.",
            )}
          </Alert>
        )}

      {!state.loading &&
        !state.fetchError &&
        state.licensed === true &&
        state.sites.length > 0 && (
          <Grid container spacing={2}>
            {state.sites.map((site) => (
              <Grid size={{ xs: 12, sm: 6, md: 4 }} key={site.id}>
                <Card variant="outlined" data-testid={`site-card-${site.id}`}>
                  <CardActionArea
                    onClick={() =>
                      navigate(`/sites/${encodeURIComponent(site.id)}`)
                    }
                  >
                    <CardContent>
                      <Box
                        sx={{
                          display: "flex",
                          justifyContent: "space-between",
                          alignItems: "flex-start",
                          gap: 1,
                        }}
                      >
                        <Typography variant="h6" component="div">
                          {site.name}
                        </Typography>
                        <Chip
                          label={site.status}
                          color={statusChipColor(site.status)}
                          size="small"
                        />
                      </Box>
                      {site.location_label && (
                        <Typography variant="body2" color="text.secondary">
                          {site.location_label}
                        </Typography>
                      )}
                      <Typography
                        variant="body2"
                        sx={{ mt: 1, wordBreak: "break-all" }}
                      >
                        {site.url}
                      </Typography>
                      <Box
                        sx={{
                          display: "flex",
                          justifyContent: "space-between",
                          mt: 2,
                        }}
                      >
                        <Typography variant="caption">
                          {t("sites.hostCount", "{{count}} hosts", {
                            count: site.host_count,
                          })}
                        </Typography>
                        {site.last_sync_at && (
                          <Typography variant="caption" color="text.secondary">
                            {t("sites.lastSync", "Synced {{when}}", {
                              when: formatRelative(site.last_sync_at) ?? "",
                            })}
                          </Typography>
                        )}
                      </Box>
                    </CardContent>
                  </CardActionArea>
                </Card>
              </Grid>
            ))}
          </Grid>
        )}

      {/* Enrollment dialog — modal form for "Add Site".  Renders the
          plaintext token EXACTLY ONCE on success; the operator copies
          it out-of-band to the new site server.  Closing the dialog
          clears the token from React state so it doesn't linger. */}
      <Dialog
        open={enroll.open}
        onClose={closeEnrollDialog}
        fullWidth
        maxWidth="sm"
        data-testid="enroll-site-dialog"
      >
        <DialogTitle>
          {enroll.token
            ? t("sites.enroll.successTitle", "Site enrolled")
            : t("sites.enroll.title", "Enroll a federation site")}
        </DialogTitle>
        <DialogContent>
          {enroll.token ? (
            <Stack spacing={2}>
              <DialogContentText>
                {t(
                  "sites.enroll.tokenInstructions",
                  "Copy the enrollment token below and deliver it to the new site server. " +
                    "This is the only time it will be displayed — there is no recovery if lost.",
                )}
              </DialogContentText>
              <TextField
                multiline
                fullWidth
                value={enroll.token}
                slotProps={{ input: { readOnly: true } }}
                data-testid="enrollment-token-value"
              />
            </Stack>
          ) : (
            <Stack spacing={2} sx={{ mt: 1 }}>
              {enroll.error && (
                <Alert severity="error">{enroll.error}</Alert>
              )}
              <TextField
                label={t("sites.enroll.name", "Site name")}
                value={enroll.name}
                onChange={(e) =>
                  setEnroll((prev) => ({ ...prev, name: e.target.value }))
                }
                fullWidth
                required
                disabled={enroll.submitting}
              />
              <TextField
                label={t("sites.enroll.url", "Site URL")}
                placeholder="https://sysmanage.site.example.com"
                value={enroll.url}
                onChange={(e) =>
                  setEnroll((prev) => ({ ...prev, url: e.target.value }))
                }
                fullWidth
                required
                disabled={enroll.submitting}
              />
              <TextField
                label={t("sites.enroll.location", "Location label (optional)")}
                value={enroll.location_label}
                onChange={(e) =>
                  setEnroll((prev) => ({
                    ...prev,
                    location_label: e.target.value,
                  }))
                }
                fullWidth
                disabled={enroll.submitting}
              />
              <TextField
                label={t(
                  "sites.enroll.syncIntervalSeconds",
                  "Sync interval (seconds)",
                )}
                type="number"
                value={enroll.sync_interval_seconds}
                onChange={(e) =>
                  setEnroll((prev) => ({
                    ...prev,
                    sync_interval_seconds: e.target.value,
                  }))
                }
                fullWidth
                disabled={enroll.submitting}
              />
            </Stack>
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={closeEnrollDialog} disabled={enroll.submitting}>
            {enroll.token
              ? t("sites.enroll.done", "Done")
              : t("sites.enroll.cancel", "Cancel")}
          </Button>
          {!enroll.token && (
            <Button
              variant="contained"
              onClick={handleSubmitEnroll}
              disabled={
                enroll.submitting ||
                !enroll.name.trim() ||
                !enroll.url.trim()
              }
            >
              {t("sites.enroll.submit", "Generate token")}
            </Button>
          )}
        </DialogActions>
      </Dialog>
    </Box>
  );
};

export default Sites;
