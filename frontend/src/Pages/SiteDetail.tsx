/**
 * Phase 12.3: federation site detail page.
 *
 * Drilled into from a card on /sites.  Renders:
 *
 *   - Metadata header (name, location, URL, status chip, enrolled-at)
 *   - Sync status card (last sync timestamp + status indicator)
 *   - Lifecycle action buttons (Suspend / Resume / Remove)
 *   - "See hosts" link → /hosts?site_id=<id>  (pre-filtering the
 *     Hosts page is the planned 12.3 Hosts-page facet; until that
 *     lands the link still routes correctly so the URL stays
 *     stable as new facets ship)
 *
 * On OSS / Community / unlicensed Enterprise installs the backend
 * returns ``{licensed: false}`` and this page renders the Enterprise
 * upsell, identical to the /sites grid behaviour.  Network failures
 * surface as a generic error alert; "no such site" (engine returned
 * ``site: undefined``) shows a NotFound state.
 */

import React, { useCallback, useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";

import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Card from "@mui/material/Card";
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
import Typography from "@mui/material/Typography";

import {
  doGetFederationSite,
  doListFederationCommands,
  doRemoveFederationSite,
  doResumeFederationSite,
  doSuspendFederationSite,
  FederationDispatchedCommand,
  FederationSiteDetail,
} from "../Services/federation";

function statusChipColor(
  status: FederationSiteDetail["status"],
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

function formatAbsolute(iso: string | null | undefined): string {
  if (!iso) return "—";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "—";
  return date.toLocaleString();
}

interface SiteDetailState {
  loading: boolean;
  licensed: boolean | null;
  site: FederationSiteDetail | null;
  notFound: boolean;
  error: string | null;
}

const initialState: SiteDetailState = {
  loading: true,
  licensed: null,
  site: null,
  notFound: false,
  error: null,
};

const SiteDetail: React.FC = () => {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { siteId } = useParams<{ siteId: string }>();

  const [state, setState] = useState<SiteDetailState>(initialState);
  const [confirmRemoveOpen, setConfirmRemoveOpen] = useState(false);
  const [actionInFlight, setActionInFlight] = useState(false);
  // Phase 12.10 visibility: open dispatched commands targeting this
  // site.  Loaded alongside the site detail; refreshed on resume +
  // suspend so the operator sees the FSM update without a page
  // reload.  ``null`` = not yet fetched.
  const [commands, setCommands] = useState<FederationDispatchedCommand[] | null>(
    null,
  );

  const refreshCommands = useCallback(async () => {
    if (!siteId) return;
    try {
      const resp = await doListFederationCommands({
        site_id: siteId,
        open_only: true,
        limit: 25,
      });
      if (resp.licensed) {
        setCommands(resp.commands ?? []);
      } else {
        setCommands([]);
      }
    } catch {
      // Non-fatal: just leave the panel empty.  The main page
      // already shows an error banner if the site itself fails to
      // load.
      setCommands([]);
    }
  }, [siteId]);

  const refresh = useCallback(async () => {
    if (!siteId) return;
    setState((prev) => ({ ...prev, loading: true, error: null }));
    try {
      const data = await doGetFederationSite(siteId);
      setState({
        loading: false,
        licensed: Boolean(data.licensed),
        site: data.site ?? null,
        notFound: Boolean(data.licensed) && !data.site,
        error: null,
      });
    } catch (err) {
      const message =
        err instanceof Error && err.message
          ? err.message
          : t("sites.detail.errorLoad", "Failed to load site.");
      setState({
        loading: false,
        licensed: null,
        site: null,
        notFound: false,
        error: message,
      });
    }
  }, [siteId, t]);

  useEffect(() => {
    let cancelled = false;
    if (!siteId) {
      setState({
        loading: false,
        licensed: null,
        site: null,
        notFound: true,
        error: null,
      });
      return;
    }
    doGetFederationSite(siteId)
      .then((data) => {
        if (cancelled) return;
        setState({
          loading: false,
          licensed: Boolean(data.licensed),
          site: data.site ?? null,
          notFound: Boolean(data.licensed) && !data.site,
          error: null,
        });
      })
      .catch((err) => {
        if (cancelled) return;
        setState({
          loading: false,
          licensed: null,
          site: null,
          notFound: false,
          error:
            (err instanceof Error && err.message) ||
            t("sites.detail.errorLoad", "Failed to load site."),
        });
      });
    refreshCommands();
    return () => {
      cancelled = true;
    };
  }, [siteId, t, refreshCommands]);

  const handleSuspend = async () => {
    if (!siteId || actionInFlight) return;
    setActionInFlight(true);
    try {
      await doSuspendFederationSite(siteId);
      await refresh();
      await refreshCommands();
    } finally {
      setActionInFlight(false);
    }
  };

  const handleResume = async () => {
    if (!siteId || actionInFlight) return;
    setActionInFlight(true);
    try {
      await doResumeFederationSite(siteId);
      await refresh();
      await refreshCommands();
    } finally {
      setActionInFlight(false);
    }
  };

  const handleRemoveConfirmed = async () => {
    if (!siteId || actionInFlight) return;
    setActionInFlight(true);
    try {
      await doRemoveFederationSite(siteId);
      setConfirmRemoveOpen(false);
      // After removal, fall back to the Sites grid — the row is
      // soft-removed at the backend but the operator's mental model
      // is "this site is gone now", so we navigate away.
      navigate("/sites");
    } finally {
      setActionInFlight(false);
    }
  };

  // ----- Render branches ----------------------------------------------

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
        <Button sx={{ mt: 2 }} onClick={() => navigate("/sites")}>
          {t("sites.detail.backToList", "Back to Sites")}
        </Button>
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

  if (state.notFound || !state.site) {
    return (
      <Box sx={{ p: 3 }}>
        <Alert severity="warning">
          {t("sites.detail.notFound", "Site not found.")}
        </Alert>
        <Button sx={{ mt: 2 }} onClick={() => navigate("/sites")}>
          {t("sites.detail.backToList", "Back to Sites")}
        </Button>
      </Box>
    );
  }

  const site = state.site;
  const canSuspend = site.status === "enrolled";
  const canResume = site.status === "suspended";
  // Pending sites are removed via cancel-enrollment (engine handles
  // the FSM check; from the UI both look like "remove this row").
  const canRemove = site.status !== "removed";

  return (
    <Box sx={{ p: 3 }}>
      {/* Header: name + status chip ------------------------------------ */}
      <Box
        sx={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          mb: 2,
          gap: 2,
          flexWrap: "wrap",
        }}
      >
        <Box>
          <Typography variant="h5" component="h1">
            {site.name}
          </Typography>
          {site.location_label && (
            <Typography variant="body2" color="text.secondary">
              {site.location_label}
            </Typography>
          )}
        </Box>
        <Chip
          label={site.status}
          color={statusChipColor(site.status)}
          data-testid="site-status-chip"
        />
      </Box>

      <Grid container spacing={2}>
        {/* Metadata card ----------------------------------------------- */}
        <Grid size={{ xs: 12, md: 6 }}>
          <Card variant="outlined">
            <CardContent>
              <Typography variant="h6" gutterBottom>
                {t("sites.detail.metadata", "Metadata")}
              </Typography>
              <Stack spacing={1}>
                <Box>
                  <Typography variant="caption" color="text.secondary">
                    {t("sites.detail.url", "URL")}
                  </Typography>
                  <Typography variant="body2" sx={{ wordBreak: "break-all" }}>
                    {site.url}
                  </Typography>
                </Box>
                <Box>
                  <Typography variant="caption" color="text.secondary">
                    {t("sites.detail.enrolledAt", "Enrolled at")}
                  </Typography>
                  <Typography variant="body2">
                    {formatAbsolute(site.enrolled_at)}
                  </Typography>
                </Box>
                <Box>
                  <Typography variant="caption" color="text.secondary">
                    {t("sites.detail.syncInterval", "Sync interval")}
                  </Typography>
                  <Typography variant="body2">
                    {site.sync_interval_seconds
                      ? t("sites.detail.syncIntervalValue", "{{seconds}}s", {
                          seconds: site.sync_interval_seconds,
                        })
                      : "—"}
                  </Typography>
                </Box>
                <Box>
                  <Typography variant="caption" color="text.secondary">
                    {t("sites.detail.hostCount", "Host count")}
                  </Typography>
                  <Typography variant="body2">{site.host_count}</Typography>
                </Box>
              </Stack>
            </CardContent>
          </Card>
        </Grid>

        {/* Sync status card -------------------------------------------- */}
        <Grid size={{ xs: 12, md: 6 }}>
          <Card variant="outlined">
            <CardContent>
              <Typography variant="h6" gutterBottom>
                {t("sites.detail.connection", "Connection")}
              </Typography>
              <Stack spacing={1}>
                <Box>
                  <Typography variant="caption" color="text.secondary">
                    {t("sites.detail.lastSyncAt", "Last sync at")}
                  </Typography>
                  <Typography variant="body2">
                    {formatAbsolute(site.last_sync_at)}
                  </Typography>
                </Box>
                <Box>
                  <Typography variant="caption" color="text.secondary">
                    {t("sites.detail.lastSyncStatus", "Last sync status")}
                  </Typography>
                  <Typography variant="body2">
                    {site.last_sync_status ?? "—"}
                  </Typography>
                </Box>
                {site.agent_version_min && (
                  <Box>
                    <Typography variant="caption" color="text.secondary">
                      {t(
                        "sites.detail.agentVersionMin",
                        "Minimum agent version",
                      )}
                    </Typography>
                    <Typography variant="body2">
                      {site.agent_version_min}
                    </Typography>
                  </Box>
                )}
              </Stack>
            </CardContent>
          </Card>
        </Grid>

        {/* Active commands card (Phase 12.10 visibility) ---------------
            Shows open dispatched commands targeting this site, with
            the FSM state, retry counter, and last push error.  An
            empty list renders a quiet "no active commands" line
            rather than hiding the card entirely — operators want to
            know the panel is up to date, not silently absent. */}
        <Grid size={{ xs: 12 }}>
          <Card variant="outlined">
            <CardContent>
              <Typography variant="h6" gutterBottom>
                {t("sites.detail.activeCommands", "Active commands")}
              </Typography>
              {commands === null ? (
                <Typography variant="body2" color="text.secondary">
                  {t("sites.detail.activeCommandsLoading", "Loading…")}
                </Typography>
              ) : commands.length === 0 ? (
                <Typography variant="body2" color="text.secondary">
                  {t(
                    "sites.detail.activeCommandsEmpty",
                    "No active commands.",
                  )}
                </Typography>
              ) : (
                <Stack spacing={1.5}>
                  {commands.map((cmd) => (
                    <Box
                      key={cmd.id}
                      sx={{
                        borderLeft: 2,
                        borderColor:
                          cmd.last_push_error || (cmd.push_attempts ?? 0) > 0
                            ? "warning.main"
                            : "divider",
                        pl: 1.5,
                        py: 0.5,
                      }}
                    >
                      <Stack
                        direction="row"
                        spacing={1}
                        alignItems="center"
                        sx={{ flexWrap: "wrap" }}
                      >
                        <Typography
                          variant="body2"
                          sx={{ fontFamily: "monospace" }}
                        >
                          {cmd.command_type}
                        </Typography>
                        <Chip
                          label={cmd.status}
                          size="small"
                          color={
                            cmd.status === "in_progress"
                              ? "info"
                              : cmd.status === "queued_at_site"
                                ? "default"
                                : "warning"
                          }
                        />
                        {(cmd.push_attempts ?? 0) > 0 && (
                          <Chip
                            label={t(
                              "sites.detail.commandAttempts",
                              "{{n}} push attempts",
                              { n: cmd.push_attempts },
                            )}
                            size="small"
                            variant="outlined"
                            color="warning"
                          />
                        )}
                      </Stack>
                      <Typography
                        variant="caption"
                        color="text.secondary"
                        component="div"
                      >
                        {cmd.dispatched_at
                          ? t(
                              "sites.detail.commandDispatchedAt",
                              "Dispatched {{when}}",
                              { when: formatAbsolute(cmd.dispatched_at) },
                            )
                          : null}
                      </Typography>
                      {cmd.last_push_error && (
                        <Typography
                          variant="caption"
                          color="error.main"
                          component="div"
                          sx={{ mt: 0.25, wordBreak: "break-word" }}
                        >
                          {cmd.last_push_error}
                        </Typography>
                      )}
                    </Box>
                  ))}
                </Stack>
              )}
            </CardContent>
          </Card>
        </Grid>
      </Grid>

      {/* Action surface ------------------------------------------------- */}
      <Box sx={{ mt: 3, display: "flex", gap: 1, flexWrap: "wrap" }}>
        <Button
          variant="outlined"
          onClick={() => navigate(`/hosts?site_id=${encodeURIComponent(site.id)}`)}
        >
          {t("sites.detail.seeHosts", "See hosts at this site")}
        </Button>
        <Button
          variant="outlined"
          onClick={() =>
            navigate(
              `/audit/federation?site_id=${encodeURIComponent(site.id)}`,
            )
          }
        >
          {t("sites.detail.viewAuditLog", "View audit log")}
        </Button>
        {canSuspend && (
          <Button
            variant="outlined"
            color="warning"
            disabled={actionInFlight}
            onClick={handleSuspend}
          >
            {t("sites.actions.suspend", "Suspend")}
          </Button>
        )}
        {canResume && (
          <Button
            variant="outlined"
            color="success"
            disabled={actionInFlight}
            onClick={handleResume}
          >
            {t("sites.actions.resume", "Resume")}
          </Button>
        )}
        {canRemove && (
          <Button
            variant="outlined"
            color="error"
            disabled={actionInFlight}
            onClick={() => setConfirmRemoveOpen(true)}
          >
            {t("sites.actions.remove", "Remove")}
          </Button>
        )}
        <Button onClick={() => navigate("/sites")}>
          {t("sites.detail.backToList", "Back to Sites")}
        </Button>
      </Box>

      {/* Confirm-remove dialog ------------------------------------------ */}
      <Dialog
        open={confirmRemoveOpen}
        onClose={() => !actionInFlight && setConfirmRemoveOpen(false)}
        data-testid="confirm-remove-dialog"
      >
        <DialogTitle>
          {t("sites.confirmRemove.title", "Remove federation site?")}
        </DialogTitle>
        <DialogContent>
          <DialogContentText>
            {t(
              "sites.confirmRemove.body",
              "The site row will be preserved for audit but the coordinator will stop accepting syncs from it. This action cannot be undone from the UI.",
            )}
          </DialogContentText>
        </DialogContent>
        <DialogActions>
          <Button
            onClick={() => setConfirmRemoveOpen(false)}
            disabled={actionInFlight}
          >
            {t("sites.confirmRemove.cancel", "Cancel")}
          </Button>
          <Button
            color="error"
            onClick={handleRemoveConfirmed}
            disabled={actionInFlight}
          >
            {t("sites.confirmRemove.confirm", "Remove site")}
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
};

export default SiteDetail;
