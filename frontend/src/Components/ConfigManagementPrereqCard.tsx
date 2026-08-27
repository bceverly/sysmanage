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
  Typography,
} from "@mui/material";
import CheckCircleIcon from "@mui/icons-material/CheckCircle";
import TuneIcon from "@mui/icons-material/Tune";
import WarningIcon from "@mui/icons-material/Warning";
import InfoOutlinedIcon from "@mui/icons-material/InfoOutlined";
import DownloadIcon from "@mui/icons-material/Download";
import PlayArrowIcon from "@mui/icons-material/PlayArrow";
import { useTranslation } from "react-i18next";
import {
  ConfigMgmtPrereq,
  getConfigMgmtPrereq,
  installConfigMgmtPrereq,
} from "../Services/configManagementService";
import ApplyConfigProfileDialog from "./ApplyConfigProfileDialog";
import { hasPermission, SecurityRoles } from "../Services/permissions";

interface ConfigManagementPrereqCardProps {
  hostId: string;
  canInstall?: boolean;
  /** Called after a profile is queued so the run history can refresh. */
  onProfileApplied?: () => void;
  isHostActive?: boolean;
  isAgentPrivileged?: boolean;
  refreshTrigger?: number;
  sx?: object;
}

/**
 * How quickly the card re-checks after the install is requested.
 *
 * Faster than the idle poll because there is a specific thing to wait for: the
 * install runs, then the inventory refresh the server queued behind it lands.
 * The card cannot know when that happens, so it asks.
 */
const ACTIVE_POLL_MS = 10000;
const IDLE_POLL_MS = 60000;

const ConfigManagementPrereqCard: React.FC<ConfigManagementPrereqCardProps> = ({
  hostId,
  canInstall = false,
  onProfileApplied,
  isHostActive = false,
  isAgentPrivileged = false,
  refreshTrigger = 0,
  sx = {},
}) => {
  const { t } = useTranslation();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [prereq, setPrereq] = useState<ConfigMgmtPrereq | null>(null);
  const [installing, setInstalling] = useState(false);
  const [applyOpen, setApplyOpen] = useState(false);
  // Checked here rather than threaded down from the page. Applying a profile
  // is arbitrary code execution, so the UI gate must be the SAME role the API
  // enforces (RUN_SCRIPT) -- a looser one would only render a button that
  // 403s. Owning the check locally also keeps four unrelated files (the page,
  // the tab, the tab-content switch and the shared permissions hook) from
  // having to know this card exists.
  const [canApply, setCanApply] = useState(false);

  useEffect(() => {
    let cancelled = false;
    hasPermission(SecurityRoles.RUN_SCRIPT)
      .then((allowed) => {
        if (!cancelled) setCanApply(allowed);
      })
      .catch(() => {
        // Fail CLOSED: if the permission cannot be determined, do not offer
        // the action.
        if (!cancelled) setCanApply(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);
  const isInitialLoad = useRef(true);

  const load = useCallback(async () => {
    if (isInitialLoad.current) {
      setLoading(true);
    }
    try {
      const status = await getConfigMgmtPrereq(hostId);
      setPrereq(status);
      setError(null);
      // Once the executor is actually there, stop showing the pending state
      // even if this component never saw the request complete.
      if (status.status === "satisfied") {
        setInstalling(false);
      }
      isInitialLoad.current = false;
    } catch (err) {
      console.error("Error fetching config-management prerequisite:", err);
      setError(
        t(
          "configManagement.prereqError",
          "Failed to load configuration management prerequisite status",
        ),
      );
    } finally {
      setLoading(false);
    }
  }, [hostId, t]);

  useEffect(() => {
    if (hostId) {
      load();
    }
  }, [hostId, refreshTrigger, load]);

  useEffect(() => {
    if (!hostId) return undefined;
    const intervalId = setInterval(
      load,
      installing ? ACTIVE_POLL_MS : IDLE_POLL_MS,
    );
    return () => clearInterval(intervalId);
  }, [hostId, installing, load]);

  const handleInstall = async () => {
    setInstalling(true);
    setError(null);
    try {
      await installConfigMgmtPrereq(hostId);
    } catch (err) {
      console.error(
        "Error requesting config-management prerequisite install:",
        err,
      );
      // Leaving the button in the pending state after a failed request would
      // strand the operator with no way to retry.
      setInstalling(false);
      setError(
        t(
          "configManagement.prereqInstallError",
          "Failed to request installation of the configuration management prerequisite",
        ),
      );
    }
  };

  const statusChip = () => {
    if (!prereq) return null;
    switch (prereq.status) {
      case "satisfied":
        return (
          <Chip
            icon={<CheckCircleIcon />}
            label={t("configManagement.prereqReady", "Ready")}
            color="success"
            size="small"
          />
        );
      case "not_required":
        return (
          <Chip
            icon={<CheckCircleIcon />}
            label={t(
              "configManagement.prereqBundled",
              "Included with the agent",
            )}
            color="success"
            size="small"
          />
        );
      case "unsupported":
        return (
          <Chip
            icon={<InfoOutlinedIcon />}
            label={t(
              "configManagement.prereqUnsupported",
              "Not available on this platform",
            )}
            size="small"
          />
        );
      case "too_old":
        return (
          <Chip
            icon={<WarningIcon />}
            label={t("configManagement.prereqTooOld", "Version too old")}
            color="warning"
            size="small"
          />
        );
      default:
        return (
          <Chip
            icon={<WarningIcon />}
            label={t("configManagement.prereqMissing", "Not installed")}
            color="warning"
            size="small"
          />
        );
    }
  };

  const explanation = () => {
    if (!prereq) return "";
    switch (prereq.status) {
      case "satisfied":
        return t(
          "configManagement.prereqReadyDetail",
          "This host has the software it needs to apply configuration profiles.",
        );
      case "not_required":
        return t(
          "configManagement.prereqBundledDetail",
          "Windows hosts use DSC, which ships with the SysManage agent. Nothing to install.",
        );
      case "unsupported":
        return t(
          "configManagement.prereqUnsupportedDetail",
          "SysManage does not have a verified way to install the configuration management engine on this operating system.",
        );
      case "too_old":
        return t(
          "configManagement.prereqTooOldDetail",
          "The installed version is older than configuration management requires. Installing will upgrade it.",
        );
      default:
        return t(
          "configManagement.prereqMissingDetail",
          "Configuration profiles cannot be applied to this host until the engine is installed.",
        );
    }
  };

  /** Why the install button is disabled, shown on hover. Empty when enabled. */
  const installButtonTitle = (): string => {
    if (installing) {
      return t(
        "configManagement.prereqInstallPending",
        "Installation already requested",
      );
    }
    if (!isAgentPrivileged) {
      return t(
        "hostDetail.notPrivileged",
        "Agent not running in privileged mode",
      );
    }
    if (!isHostActive) {
      return t("hostDetail.hostInactive", "Host is not active");
    }
    return "";
  };

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
          {t("configManagement.prereqTitle", "Configuration Management")}
        </Typography>

        {error && (
          <Alert severity="error" sx={{ mb: 2 }}>
            {error}
          </Alert>
        )}

        {prereq && (
          <Stack spacing={2}>
            <Box>
              <Typography variant="body2" color="text.secondary" gutterBottom>
                {t("configManagement.prereqEngine", "Engine")}
              </Typography>
              <Typography variant="body1" fontWeight="medium">
                {prereq.executor}
              </Typography>
            </Box>

            <Box>
              <Typography variant="body2" color="text.secondary" gutterBottom>
                {t("configManagement.prereqStatus", "Status")}
              </Typography>
              {statusChip()}
            </Box>

            {prereq.installed_version && (
              <Box>
                <Typography variant="body2" color="text.secondary" gutterBottom>
                  {t(
                    "configManagement.prereqInstalledVersion",
                    "Installed version",
                  )}
                </Typography>
                <Typography variant="body1">
                  {prereq.installed_version}
                </Typography>
              </Box>
            )}

            {prereq.minimum_version && prereq.status !== "satisfied" && (
              <Box>
                <Typography variant="body2" color="text.secondary" gutterBottom>
                  {t(
                    "configManagement.prereqMinimumVersion",
                    "Minimum version",
                  )}
                </Typography>
                <Typography variant="body1">
                  {prereq.minimum_version}
                </Typography>
              </Box>
            )}

            <Typography variant="body2" color="text.secondary">
              {explanation()}
            </Typography>

            {installing && (
              <Alert severity="info">
                {t(
                  "configManagement.prereqInstallRequested",
                  "Installation requested. This card updates once the host reports back.",
                )}
              </Alert>
            )}
          </Stack>
        )}

        {/* Applying is only meaningful once an executor is actually present:
            "satisfied" (installed) or "not_required" (bundled, e.g. DSC).
            Offering it on a host with no engine would queue work that can only
            come back as executor_missing. */}
        {canApply &&
          prereq &&
          (prereq.status === "satisfied" ||
            prereq.status === "not_required") && (
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

        {prereq && (
          <ApplyConfigProfileDialog
            open={applyOpen}
            hostId={hostId}
            executor={prereq.executor}
            onClose={() => setApplyOpen(false)}
            onApplied={onProfileApplied}
          />
        )}

        {prereq?.can_install && canInstall && (
          <Box sx={{ mt: 3, display: "flex", gap: 1, flexWrap: "wrap" }}>
            <Button
              variant="contained"
              color="primary"
              startIcon={
                installing ? (
                  <CircularProgress size={16} color="inherit" />
                ) : (
                  <DownloadIcon />
                )
              }
              onClick={handleInstall}
              disabled={installing || !isHostActive || !isAgentPrivileged}
              title={installButtonTitle()}
            >
              {t("configManagement.prereqInstall", "Install prerequisite")}
            </Button>
          </Box>
        )}
      </CardContent>
    </Card>
  );
};

export default ConfigManagementPrereqCard;
