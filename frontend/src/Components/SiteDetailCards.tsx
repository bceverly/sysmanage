// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

/**
 * Presentational cards for the SiteDetail page (Phase 12.x).  Each card
 * is a self-contained subtree that receives its data (and any callbacks)
 * via props; the owning page keeps all state and hooks.  Extracted from
 * SiteDetail.tsx to keep the page under the max-lines budget.
 */

import React from "react";
import { useTranslation } from "react-i18next";

import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Card from "@mui/material/Card";
import CardContent from "@mui/material/CardContent";
import Chip from "@mui/material/Chip";
import Grid from "@mui/material/Grid";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";

import {
  FederationAlert,
  FederationDashboardRollupResponse,
  FederationDispatchedCommand,
} from "../Services/federation";
import { formatAbsolute } from "./SiteDetailHelpers";

/** Open rollup alerts targeting this site (Phase 12.1). Renders nothing
 * when there are no alerts. */
export function SiteAlertsCard({
  alerts,
  onAcknowledge,
}: Readonly<{
  alerts: FederationAlert[];
  onAcknowledge: (alertId: string) => void;
}>) {
  const { t } = useTranslation();
  if (alerts.length === 0) return null;
  return (
    <Grid size={{ xs: 12 }}>
      <Card variant="outlined" sx={{ borderColor: "error.main" }}>
        <CardContent>
          <Typography variant="h6" gutterBottom>
            {t("sites.detail.alertsTitle", "Open alerts")}
          </Typography>
          <Stack spacing={1.5}>
            {alerts.map((a) => (
              <Box
                key={a.id}
                sx={{
                  borderLeft: 3,
                  borderColor:
                    a.severity === "critical" ? "error.main" : "warning.main",
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
                  <Chip
                    label={a.severity}
                    size="small"
                    color={a.severity === "critical" ? "error" : "warning"}
                  />
                  <Typography variant="body2" sx={{ fontWeight: 600 }}>
                    {a.title}
                  </Typography>
                  {a.acknowledged ? (
                    <Chip
                      label={t("sites.detail.alertAcked", "Acknowledged")}
                      size="small"
                      variant="outlined"
                    />
                  ) : (
                    <Button
                      size="small"
                      onClick={() => onAcknowledge(a.id)}
                      data-testid="ack-alert"
                    >
                      {t("sites.detail.alertAck", "Acknowledge")}
                    </Button>
                  )}
                </Stack>
                <Typography
                  variant="caption"
                  color="text.secondary"
                  component="div"
                >
                  {a.message}
                </Typography>
              </Box>
            ))}
          </Stack>
        </CardContent>
      </Card>
    </Grid>
  );
}

/** Compliance & vulnerability rollup card — the latest AGGREGATE snapshot
 * this site pushed up (per-host detail stays on the site). */
export function SiteRollupCard({
  rollup,
}: Readonly<{
  rollup: FederationDashboardRollupResponse | null;
}>) {
  const { t } = useTranslation();
  const compliance = rollup?.compliance_rollups ?? [];
  const vuln = rollup?.vulnerability_rollup ?? null;
  return (
    <Grid size={{ xs: 12 }}>
      <Card variant="outlined">
        <CardContent>
          <Typography variant="h6" gutterBottom>
            {t("sites.detail.rollupTitle", "Compliance & vulnerabilities")}
          </Typography>
          {compliance.length === 0 && !vuln ? (
            <Typography variant="body2" color="text.secondary">
              {t(
                "sites.detail.rollupEmpty",
                "No compliance or vulnerability data synced from this site yet.",
              )}
            </Typography>
          ) : (
            <Stack spacing={2}>
              {compliance.length > 0 && (
                <Box>
                  <Typography variant="caption" color="text.secondary">
                    {t("sites.detail.rollupCompliance", "Compliance")}
                  </Typography>
                  <Stack
                    direction="row"
                    spacing={1}
                    sx={{ flexWrap: "wrap", mt: 0.5 }}
                  >
                    {compliance.map((c) => {
                      const complianceColor = (() => {
                        if (c.score_percent >= 90) return "success";
                        if (c.score_percent >= 70) return "warning";
                        return "error";
                      })();
                      return (
                        <Chip
                          key={c.baseline}
                          size="small"
                          variant="outlined"
                          color={complianceColor}
                          label={`${c.baseline}: ${Math.round(
                            c.score_percent,
                          )}% (${c.hosts_compliant}/${c.hosts_in_scope})`}
                        />
                      );
                    })}
                  </Stack>
                </Box>
              )}
              {vuln && (
                <Box>
                  <Typography variant="caption" color="text.secondary">
                    {t(
                      "sites.detail.rollupVulnerabilities",
                      "Vulnerabilities ({{hosts}} hosts affected)",
                      { hosts: vuln.affected_host_count },
                    )}
                  </Typography>
                  <Stack
                    direction="row"
                    spacing={1}
                    sx={{ flexWrap: "wrap", mt: 0.5 }}
                  >
                    <Chip
                      size="small"
                      color="error"
                      label={t("sites.detail.vulnCritical", "{{n}} critical", {
                        n: vuln.critical_count,
                      })}
                    />
                    <Chip
                      size="small"
                      color="warning"
                      label={t("sites.detail.vulnHigh", "{{n}} high", {
                        n: vuln.high_count,
                      })}
                    />
                    <Chip
                      size="small"
                      variant="outlined"
                      label={t("sites.detail.vulnMedium", "{{n}} medium", {
                        n: vuln.medium_count,
                      })}
                    />
                    <Chip
                      size="small"
                      variant="outlined"
                      label={t("sites.detail.vulnLow", "{{n}} low", {
                        n: vuln.low_count,
                      })}
                    />
                  </Stack>
                </Box>
              )}
            </Stack>
          )}
        </CardContent>
      </Card>
    </Grid>
  );
}

/** Active commands card (Phase 12.10 visibility) — open dispatched commands
 * targeting this site with FSM state, retry counter, and last push error. */
export function SiteCommandsCard({
  commands,
  onDispatch,
}: Readonly<{
  commands: FederationDispatchedCommand[] | null;
  onDispatch: () => void;
}>) {
  const { t } = useTranslation();
  return (
    <Grid size={{ xs: 12 }}>
      <Card variant="outlined">
        <CardContent>
          <Stack
            direction="row"
            justifyContent="space-between"
            alignItems="center"
            sx={{ mb: 1 }}
          >
            <Typography variant="h6">
              {t("sites.detail.activeCommands", "Active commands")}
            </Typography>
            <Button
              size="small"
              variant="outlined"
              onClick={onDispatch}
              data-testid="dispatch-command-button"
            >
              {t("sites.detail.dispatchCommand", "Dispatch command")}
            </Button>
          </Stack>
          {commands === null && (
            <Typography variant="body2" color="text.secondary">
              {t("sites.detail.activeCommandsLoading", "Loading…")}
            </Typography>
          )}
          {commands !== null && commands.length === 0 && (
            <Typography variant="body2" color="text.secondary">
              {t("sites.detail.activeCommandsEmpty", "No active commands.")}
            </Typography>
          )}
          {commands !== null && commands.length > 0 && (
            <Stack spacing={1.5}>
              {commands.map((cmd) => {
                const statusColor = (() => {
                  if (cmd.status === "in_progress") return "info";
                  if (cmd.status === "queued_at_site") return "default";
                  return "warning";
                })();
                return (
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
                      <Chip label={cmd.status} size="small" color={statusColor} />
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
                );
              })}
            </Stack>
          )}
        </CardContent>
      </Card>
    </Grid>
  );
}
