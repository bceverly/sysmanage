// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

import React, { useCallback, useEffect, useRef, useState } from "react";
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  CircularProgress,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Typography,
} from "@mui/material";
import CheckCircleIcon from "@mui/icons-material/CheckCircle";
import DownloadIcon from "@mui/icons-material/Download";
import PlayArrowIcon from "@mui/icons-material/PlayArrow";
import TuneIcon from "@mui/icons-material/Tune";
import WarningIcon from "@mui/icons-material/Warning";
import { useTranslation } from "react-i18next";
import {
  ConfigMgmtEngineStatus,
  getConfigMgmtEngines,
  installConfigMgmtPrereq,
} from "../Services/configManagementService";
import { hasPermission, SecurityRoles } from "../Services/permissions";
import ApplyConfigProfileDialog from "./ApplyConfigProfileDialog";

interface ConfigManagementEnginesCardProps {
  hostId: string;
  canInstall?: boolean;
  isHostActive?: boolean;
  isAgentPrivileged?: boolean;
  refreshTrigger?: number;
  onProfileApplied?: () => void;
  sx?: object;
}

/** Statuses that mean the engine can actually run a profile right now. */
const READY = new Set(["satisfied", "not_required"]);

const ConfigManagementEnginesCard: React.FC<
  ConfigManagementEnginesCardProps
> = ({
  hostId,
  canInstall = false,
  isHostActive = false,
  isAgentPrivileged = false,
  refreshTrigger = 0,
  onProfileApplied,
  sx = {},
}) => {
  const { t } = useTranslation();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [engines, setEngines] = useState<ConfigMgmtEngineStatus[]>([]);
  const [installing, setInstalling] = useState<string | null>(null);
  const [applyOpen, setApplyOpen] = useState(false);
  const [canApply, setCanApply] = useState(false);
  const isInitialLoad = useRef(true);

  useEffect(() => {
    let cancelled = false;
    hasPermission(SecurityRoles.RUN_SCRIPT)
      .then((allowed) => {
        if (!cancelled) setCanApply(allowed);
      })
      // Fail CLOSED: if the permission cannot be determined, offer nothing.
      .catch(() => {
        if (!cancelled) setCanApply(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const load = useCallback(async () => {
    if (isInitialLoad.current) setLoading(true);
    try {
      const data = await getConfigMgmtEngines(hostId);
      setEngines(data.engines);
      setError(null);
      isInitialLoad.current = false;
    } catch (err) {
      console.error("Error fetching config-management engines:", err);
      setError(
        t(
          "configManagement.enginesError",
          "Failed to load configuration management engines",
        ),
      );
    } finally {
      setLoading(false);
    }
  }, [hostId, t]);

  useEffect(() => {
    if (hostId) load();
  }, [hostId, refreshTrigger, load]);

  const handleInstall = async (engine: string) => {
    setInstalling(engine);
    setError(null);
    try {
      await installConfigMgmtPrereq(hostId, engine);
    } catch (err) {
      console.error("Error requesting engine install:", err);
      // Do not strand the row in a pending state with no way to retry.
      setInstalling(null);
      setError(
        t(
          "configManagement.prereqInstallError",
          "Failed to request installation of the configuration management prerequisite",
        ),
      );
    }
  };

  /**
   * The status chip.
   *
   * An engine that is not installed reads as NEUTRAL, never as an error. A
   * host without Puppet is not broken -- it simply does not use Puppet, and
   * painting that red turns the card into a checklist of things the operator
   * is "missing" and pressures them into installing four engines when they
   * wanted one. A missing engine only becomes a problem when a profile
   * actually targets it, which is a different screen.
   */
  // Why the install button is disabled, in priority order. Named rather than
  // nested inline: the button's own `disabled` already encodes the same two
  // conditions, and two copies of that logic would drift into a button that
  // is disabled with no tooltip saying why.
  let blockedReason = "";
  if (!isAgentPrivileged) {
    blockedReason = t(
      "hostDetail.notPrivileged",
      "Agent not running in privileged mode",
    );
  } else if (!isHostActive) {
    blockedReason = t("hostDetail.hostInactive", "Host is not active");
  }

  const statusChip = (row: ConfigMgmtEngineStatus) => {
    if (row.status === "satisfied") {
      return (
        <Chip
          icon={<CheckCircleIcon />}
          label={t("configManagement.engineReady", "Ready")}
          color="success"
          size="small"
        />
      );
    }
    if (row.status === "not_required") {
      return (
        <Chip
          icon={<CheckCircleIcon />}
          label={t("configManagement.engineBundled", "Included with the agent")}
          color="success"
          size="small"
        />
      );
    }
    if (row.status === "too_old") {
      return (
        <Chip
          icon={<WarningIcon />}
          label={t("configManagement.engineTooOld", "Version too old")}
          color="warning"
          size="small"
        />
      );
    }
    if (row.status === "missing") {
      return (
        <Chip
          label={t("configManagement.engineNotInstalled", "Not installed")}
          size="small"
          variant="outlined"
        />
      );
    }
    return (
      <Chip
        label={t("configManagement.engineUnavailable", "Not available here")}
        size="small"
        variant="outlined"
      />
    );
  };

  const readyEngines = engines
    .filter((e) => READY.has(e.status))
    .map((e) => e.engine);

  if (loading) {
    return (
      <Card sx={sx}>
        <CardContent>
          <Box
            display="flex"
            justifyContent="center"
            alignItems="center"
            minHeight="150px"
          >
            <CircularProgress />
          </Box>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card sx={sx}>
      <CardContent>
        <Typography
          variant="subtitle1"
          sx={{
            display: "flex",
            alignItems: "center",
            fontWeight: "bold",
            fontSize: "1.1rem",
            mb: 2,
          }}
        >
          <TuneIcon sx={{ mr: 1 }} />
          {t("configManagement.enginesTitle", "Configuration Management")}
        </Typography>

        {error && (
          <Alert severity="error" sx={{ mb: 2 }}>
            {error}
          </Alert>
        )}

        {installing && (
          <Alert severity="info" sx={{ mb: 2 }}>
            {t(
              "configManagement.prereqInstallRequested",
              "Installation requested. This card updates once the host reports back.",
            )}
          </Alert>
        )}

        <TableContainer sx={{ overflowX: "auto" }}>
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>
                  {t("configManagement.engineName", "Engine")}
                </TableCell>
                <TableCell>
                  {t("configManagement.engineStatus", "Status")}
                </TableCell>
                <TableCell align="right" />
              </TableRow>
            </TableHead>
            <TableBody>
              {engines.map((row) => (
                <TableRow key={row.engine}>
                  <TableCell>
                    <Stack direction="row" spacing={1} alignItems="center">
                      <span>{row.engine}</span>
                      {row.requires_license && (
                        <Chip
                          label={t(
                            "configManagement.engineEnterprise",
                            "Enterprise",
                          )}
                          size="small"
                          color="info"
                          variant="outlined"
                        />
                      )}
                    </Stack>
                  </TableCell>
                  <TableCell>
                    <Stack direction="row" spacing={1} alignItems="center">
                      {statusChip(row)}
                      {row.installed_version && (
                        <Typography variant="body2" color="text.secondary">
                          {row.installed_version}
                        </Typography>
                      )}
                    </Stack>
                  </TableCell>
                  <TableCell align="right">
                    {/* An inline action only where one exists -- four engines
                        with a button each would be a wall, and most rows need
                        no action at all. */}
                    {row.can_install && canInstall && (
                      <Button
                        size="small"
                        startIcon={<DownloadIcon />}
                        onClick={() => handleInstall(row.engine)}
                        disabled={
                          Boolean(installing) ||
                          !isHostActive ||
                          !isAgentPrivileged
                        }
                        title={blockedReason}
                      >
                        {t("configManagement.engineInstall", "Install")}
                      </Button>
                    )}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </TableContainer>

        {canApply && readyEngines.length > 0 && (
          <Box sx={{ mt: 3, display: "flex", gap: 1, flexWrap: "wrap" }}>
            <Button
              variant="outlined"
              startIcon={<PlayArrowIcon />}
              onClick={() => setApplyOpen(true)}
              disabled={!isHostActive}
              title={
                isHostActive
                  ? ""
                  : t("hostDetail.hostInactive", "Host is not active")
              }
            >
              {t("configManagement.applyProfile", "Apply profile")}
            </Button>
          </Box>
        )}

        <ApplyConfigProfileDialog
          open={applyOpen}
          hostId={hostId}
          engines={readyEngines}
          onClose={() => setApplyOpen(false)}
          onApplied={onProfileApplied}
        />
      </CardContent>
    </Card>
  );
};

export default ConfigManagementEnginesCard;
