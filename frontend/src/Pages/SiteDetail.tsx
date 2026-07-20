// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

/**
 * Phase 12.3: federation site detail page.
 *
 * Drilled into from a card on /sites.  Renders:
 *
 *   - Metadata header (name, location, URL, status chip, enrolled-at)
 *   - Sync status card (last sync timestamp + status indicator)
 *   - Lifecycle action buttons (Suspend / Resume / Remove)
 *   - "See hosts" link → /federation/hosts?site_id=<id>  (the
 *     cross-site federated Hosts page, scoped to this site)
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
import Snackbar from "@mui/material/Snackbar";
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
import Tooltip from "@mui/material/Tooltip";

import {
  doAcknowledgeFederationAlert,
  doGetFederationDashboardRollup,
  doGetFederationSite,
  doGetFederationSiteSyncStatus,
  doGetFederationSiteSyncTimeline,
  doListFederationAlerts,
  doListFederationCommands,
  doRemoveFederationSite,
  doRepushSitePolicies,
  doResumeFederationSite,
  doSuspendFederationSite,
  FederationAlert,
  FederationDashboardRollupResponse,
  FederationDispatchedCommand,
  FederationSiteSyncStatus,
  FederationSiteSyncTimeline,
} from "../Services/federation";
import FederationCommandDispatchDialog from "../Components/FederationCommandDispatchDialog";
import { Sparkline, SyncHealthHistogram } from "../Components/SiteDetailCharts";
import {
  SiteAlertsCard,
  SiteCommandsCard,
  SiteRollupCard,
} from "../Components/SiteDetailCards";
import {
  formatAbsolute,
  formatRelative,
  initialState,
  SiteDetailState,
  statusChipColor,
  syncHealth,
  SYNC_HEALTH_COLOR,
} from "../Components/SiteDetailHelpers";

const SiteDetail: React.FC = () => {
  const { t, i18n } = useTranslation();
  const navigate = useNavigate();
  const { siteId } = useParams<{ siteId: string }>();

  const [state, setState] = useState<SiteDetailState>(initialState);
  const [confirmRemoveOpen, setConfirmRemoveOpen] = useState(false);
  const [dispatchOpen, setDispatchOpen] = useState(false);
  const [actionInFlight, setActionInFlight] = useState(false);
  // Phase 12.10 visibility: open dispatched commands targeting this
  // site.  Loaded alongside the site detail; refreshed on resume +
  // suspend so the operator sees the FSM update without a page
  // reload.  ``null`` = not yet fetched.
  const [commands, setCommands] = useState<FederationDispatchedCommand[] | null>(
    null,
  );
  // Live connection-health metrics from the dedicated sync-status endpoint
  // (fresher than the site-detail snapshot; polled).
  const [syncStatus, setSyncStatus] = useState<FederationSiteSyncStatus | null>(
    null,
  );

  const refreshSyncStatus = useCallback(async () => {
    if (!siteId) return;
    try {
      const resp = await doGetFederationSiteSyncStatus(siteId);
      setSyncStatus(resp.licensed ? (resp.status ?? null) : null);
    } catch {
      // Non-fatal; the card falls back to the site-detail snapshot.
    }
  }, [siteId]);

  // Phase 12.2: per-site sync timeline + the site's self-reported uplink
  // state / version / capabilities (from its metadata reports).
  const [syncTimeline, setSyncTimeline] =
    useState<FederationSiteSyncTimeline | null>(null);

  const refreshSyncTimeline = useCallback(async () => {
    if (!siteId) return;
    try {
      const resp = await doGetFederationSiteSyncTimeline(siteId);
      setSyncTimeline(resp.licensed ? resp : null);
    } catch {
      // Non-fatal; the timeline card simply renders empty.
    }
  }, [siteId]);

  // Latest compliance + vulnerability rollup the site has pushed up.
  const [rollup, setRollup] = useState<FederationDashboardRollupResponse | null>(
    null,
  );

  const refreshRollup = useCallback(async () => {
    if (!siteId) return;
    try {
      const resp = await doGetFederationDashboardRollup(siteId);
      setRollup(resp.licensed ? resp : null);
    } catch {
      setRollup(null);
    }
  }, [siteId]);

  // Open rollup alerts targeting this site.
  const [alerts, setAlerts] = useState<FederationAlert[]>([]);

  const refreshAlerts = useCallback(async () => {
    if (!siteId) return;
    try {
      const resp = await doListFederationAlerts({ site_id: siteId });
      setAlerts(resp.licensed ? (resp.alerts ?? []) : []);
    } catch {
      setAlerts([]);
    }
  }, [siteId]);

  const acknowledge = useCallback(
    async (alertId: string) => {
      try {
        await doAcknowledgeFederationAlert(alertId);
        await refreshAlerts();
      } catch {
        // Non-fatal.
      }
    },
    [refreshAlerts],
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
    refreshSyncStatus();
    refreshSyncTimeline();
    refreshRollup();
    refreshAlerts();
    // Poll connection health + alerts so an operator watching the page
    // sees the site go stale/overdue (and new alerts) without a reload.
    const poll = setInterval(() => {
      refreshSyncStatus();
      refreshSyncTimeline();
      refreshAlerts();
    }, 15000);
    return () => {
      cancelled = true;
      clearInterval(poll);
    };
  }, [
    siteId,
    t,
    refreshCommands,
    refreshSyncStatus,
    refreshSyncTimeline,
    refreshRollup,
    refreshAlerts,
  ]);

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

  const [repushMsg, setRepushMsg] = useState<string | null>(null);

  const handleRepushPolicies = async () => {
    if (!siteId || actionInFlight) return;
    setActionInFlight(true);
    try {
      const resp = await doRepushSitePolicies(siteId);
      const n = resp.requeued_count ?? 0;
      setRepushMsg(
        t(
          "sites.detail.repushQueued",
          "Queued {{n}} policy push(es) for re-delivery.",
          { n },
        ),
      );
    } catch {
      setRepushMsg(
        t("sites.detail.repushFailed", "Failed to queue policy re-push."),
      );
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
        <Stack direction="row" spacing={1} alignItems="center">
          {/* Per-site action surface (Phase 12.3): a batch dispatch is
              the primary per-site action; disabled unless the site is
              actively enrolled (a suspended/removed site can't actuate). */}
          <Button
            variant="contained"
            size="small"
            disabled={site.status !== "enrolled"}
            onClick={() => setDispatchOpen(true)}
            data-testid="header-dispatch-button"
          >
            {t("sites.detail.dispatchCommand", "Dispatch command")}
          </Button>
          <Tooltip
            title={t(
              "sites.detail.pushPoliciesHint",
              "Re-queue every policy for this site — including any stuck or dead-lettered deliveries — for immediate re-push.",
            )}
          >
            <span>
              <Button
                variant="outlined"
                size="small"
                disabled={site.status !== "enrolled" || actionInFlight}
                onClick={handleRepushPolicies}
                data-testid="header-policies-button"
              >
                {t("sites.detail.pushPolicies", "Push policies")}
              </Button>
            </span>
          </Tooltip>
          <Chip
            label={site.status}
            color={statusChipColor(site.status)}
            data-testid="site-status-chip"
          />
        </Stack>
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

        {/* Connection-health card -------------------------------------- */}
        <Grid size={{ xs: 12, md: 6 }}>
          <Card variant="outlined">
            <CardContent>
              {(() => {
                // Prefer the live sync-status poll; fall back to the
                // site-detail snapshot when the endpoint hasn't answered yet.
                const lastSyncAt =
                  syncStatus?.last_sync_at ?? site.last_sync_at;
                const lastSyncStatus =
                  syncStatus?.last_sync_status ?? site.last_sync_status;
                const health = syncHealth(
                  lastSyncAt,
                  site.sync_interval_seconds,
                );
                const relative = formatRelative(lastSyncAt, i18n.language);
                const healthLabel = {
                  healthy: t("sites.detail.syncHealthy", "Healthy"),
                  stale: t("sites.detail.syncStale", "Stale"),
                  overdue: t("sites.detail.syncOverdue", "Overdue"),
                  unknown: t("sites.detail.syncNever", "Never synced"),
                }[health];
                return (
                  <>
                    <Stack
                      direction="row"
                      justifyContent="space-between"
                      alignItems="center"
                      sx={{ mb: 1 }}
                    >
                      <Stack direction="row" spacing={1} alignItems="center">
                        <Typography variant="h6">
                          {t("sites.detail.connection", "Connection health")}
                        </Typography>
                        <Chip
                          label={healthLabel}
                          size="small"
                          color={SYNC_HEALTH_COLOR[health]}
                        />
                      </Stack>
                      <Button
                        size="small"
                        onClick={refreshSyncStatus}
                        data-testid="refresh-sync-status"
                      >
                        {t("sites.detail.refresh", "Refresh")}
                      </Button>
                    </Stack>
                    <Stack spacing={1}>
                      <Box>
                        <Typography variant="caption" color="text.secondary">
                          {t("sites.detail.lastSyncAt", "Last sync at")}
                        </Typography>
                        <Typography variant="body2">
                          {formatAbsolute(lastSyncAt)}
                          {relative ? ` (${relative})` : ""}
                        </Typography>
                      </Box>
                      <Box>
                        <Typography variant="caption" color="text.secondary">
                          {t("sites.detail.lastSyncStatus", "Last sync status")}
                        </Typography>
                        <Typography variant="body2">
                          {lastSyncStatus ?? "—"}
                        </Typography>
                      </Box>
                      <Box>
                        <Typography variant="caption" color="text.secondary">
                          {t(
                            "sites.detail.backlogDepth",
                            "Pending upstream queue",
                          )}
                        </Typography>
                        <Typography variant="body2">
                          {syncStatus?.pending_queue_depth ??
                            t("sites.detail.backlogUnknown", "—")}
                        </Typography>
                      </Box>
                      {site.agent_version_min && (
                        <Box>
                          <Typography
                            variant="caption"
                            color="text.secondary"
                          >
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
                  </>
                );
              })()}
            </CardContent>
          </Card>
        </Grid>

        {/* Sync timeline + site-reported metadata (Phase 12.2) -------- */}
        <Grid size={{ xs: 12 }}>
          <Card variant="outlined" data-testid="sync-timeline-card">
            <CardContent>
              <Stack
                direction="row"
                justifyContent="space-between"
                alignItems="center"
                sx={{ mb: 1 }}
              >
                <Typography variant="h6">
                  {t("sites.detail.syncTimeline", "Sync timeline")}
                </Typography>
                {syncTimeline?.connection_state === "offline" && (
                  <Chip
                    size="small"
                    color="warning"
                    data-testid="autonomy-banner"
                    label={t(
                      "sites.detail.autonomous",
                      "Operating independently",
                    )}
                  />
                )}
              </Stack>
              {syncTimeline && syncTimeline.events.length > 0 ? (
                <Stack spacing={1}>
                  <Box>
                    <Typography variant="caption" color="text.secondary">
                      {t(
                        "sites.detail.syncLatency",
                        "Upstream sync latency (recent)",
                      )}
                    </Typography>
                    <Box>
                      <Sparkline
                        testId="sync-latency-sparkline"
                        values={syncTimeline.events.map((e) =>
                          e.latency_ms ?? e.queue_depth ?? null,
                        )}
                      />
                    </Box>
                  </Box>
                  <Box>
                    <Typography variant="caption" color="text.secondary">
                      {t(
                        "sites.detail.syncHealthHistogram",
                        "Sync success / failure (recent)",
                      )}
                    </Typography>
                    <Box>
                      <SyncHealthHistogram
                        testId="sync-health-histogram"
                        events={syncTimeline.events}
                      />
                    </Box>
                  </Box>
                  <Typography variant="body2" color="text.secondary">
                    {t("sites.detail.syncPoints", "{{n}} sync events", {
                      n: syncTimeline.events.length,
                    })}
                  </Typography>
                </Stack>
              ) : (
                <Typography variant="body2" color="text.secondary">
                  {t(
                    "sites.detail.syncTimelineEmpty",
                    "No sync events recorded yet.",
                  )}
                </Typography>
              )}
              {syncTimeline?.sysmanage_version && (
                <Box sx={{ mt: 1 }}>
                  <Typography variant="caption" color="text.secondary">
                    {t("sites.detail.siteVersion", "Reported version")}
                  </Typography>
                  <Typography variant="body2" data-testid="site-version">
                    {syncTimeline.sysmanage_version}
                  </Typography>
                </Box>
              )}
              {syncTimeline?.capabilities &&
                syncTimeline.capabilities.length > 0 && (
                  <Box sx={{ mt: 1 }}>
                    <Typography variant="caption" color="text.secondary">
                      {t("sites.detail.siteCapabilities", "Capabilities")}
                    </Typography>
                    <Stack
                      direction="row"
                      spacing={1}
                      sx={{ flexWrap: "wrap", mt: 0.5 }}
                    >
                      {syncTimeline.capabilities.map((cap) => (
                        <Chip key={cap} size="small" label={cap} />
                      ))}
                    </Stack>
                  </Box>
                )}
            </CardContent>
          </Card>
        </Grid>

        {/* Open alerts card (Phase 12.1 rollup alerting) -------------- */}
        <SiteAlertsCard alerts={alerts} onAcknowledge={acknowledge} />

        {/* Compliance & vulnerability rollup card ---------------------
            The federation-correct "cross-site compliance/vuln drill-down":
            the latest AGGREGATE snapshot this site pushed up (per-host
            detail stays on the site). */}
        <SiteRollupCard rollup={rollup} />

        {/* Active commands card (Phase 12.10 visibility) ---------------
            Shows open dispatched commands targeting this site, with
            the FSM state, retry counter, and last push error. */}
        <SiteCommandsCard
          commands={commands}
          onDispatch={() => setDispatchOpen(true)}
        />
      </Grid>

      {/* Action surface ------------------------------------------------- */}
      <Box sx={{ mt: 3, display: "flex", gap: 1, flexWrap: "wrap" }}>
        <Button
          variant="outlined"
          onClick={() =>
            navigate(`/federation/hosts?site_id=${encodeURIComponent(site.id)}`)
          }
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

      <FederationCommandDispatchDialog
        siteId={site.id}
        siteName={site.name}
        open={dispatchOpen}
        onClose={() => setDispatchOpen(false)}
        onDispatched={refreshCommands}
      />

      <Snackbar
        open={repushMsg !== null}
        autoHideDuration={5000}
        onClose={() => setRepushMsg(null)}
        message={repushMsg ?? ""}
        data-testid="repush-snackbar"
      />
    </Box>
  );
};

export default SiteDetail;
