// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

import React, { useCallback, useEffect, useRef, useState } from "react";
import {
  Alert,
  Box,
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
import ErrorIcon from "@mui/icons-material/Error";
import HistoryIcon from "@mui/icons-material/History";
import { useTranslation } from "react-i18next";
import { formatUTCTimestamp } from "../utils/dateUtils";
import {
  ConfigProfileRun,
  getConfigProfileRuns,
} from "../Services/configManagementService";

interface ConfigProfileRunHistoryProps {
  hostId: string;
  refreshTrigger?: number;
  sx?: object;
}

const ConfigProfileRunHistory: React.FC<ConfigProfileRunHistoryProps> = ({
  hostId,
  refreshTrigger = 0,
  sx = {},
}) => {
  const { t } = useTranslation();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [runs, setRuns] = useState<ConfigProfileRun[]>([]);
  const isInitialLoad = useRef(true);

  const load = useCallback(async () => {
    if (isInitialLoad.current) {
      setLoading(true);
    }
    try {
      setRuns(await getConfigProfileRuns(hostId));
      setError(null);
      isInitialLoad.current = false;
    } catch (err) {
      console.error("Error fetching config profile runs:", err);
      setError(
        t(
          "configManagement.runsError",
          "Failed to load configuration run history",
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

  /**
   * The outcome chip.
   *
   * "Changed" and "No changes" are deliberately distinct rather than both
   * reading as a green tick: a run of a converged profile SHOULD change
   * nothing, and being able to see that streak is the whole point of
   * idempotency reporting. A failure outranks both.
   */
  const outcomeChip = (run: ConfigProfileRun) => {
    if (!run.success) {
      return (
        <Chip
          icon={<ErrorIcon />}
          label={t("configManagement.runFailed", "Failed")}
          color="error"
          size="small"
        />
      );
    }
    if (run.changed) {
      return (
        <Chip
          label={t("configManagement.runChanged", "Changed")}
          color="warning"
          size="small"
        />
      );
    }
    return (
      <Chip
        icon={<CheckCircleIcon />}
        label={t("configManagement.runNoChanges", "No changes")}
        color="success"
        size="small"
      />
    );
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
          <HistoryIcon sx={{ mr: 1 }} />
          {t("configManagement.runsTitle", "Configuration Run History")}
        </Typography>

        {error && (
          <Alert severity="error" sx={{ mb: 2 }}>
            {error}
          </Alert>
        )}

        {!error && runs.length === 0 && (
          <Typography variant="body2" color="text.secondary">
            {t(
              "configManagement.runsEmpty",
              "No configuration profiles have been applied to this host yet.",
            )}
          </Typography>
        )}

        {runs.length > 0 && (
          <TableContainer sx={{ overflowX: "auto" }}>
            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell>{t("configManagement.runWhen", "When")}</TableCell>
                  <TableCell>
                    {t("configManagement.runProfile", "Profile")}
                  </TableCell>
                  <TableCell>
                    {t("configManagement.runOutcome", "Outcome")}
                  </TableCell>
                  <TableCell>
                    {t("configManagement.runTasks", "Tasks")}
                  </TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {runs.map((run) => (
                  <TableRow key={run.id}>
                    <TableCell>
                      {run.completed_at
                        ? formatUTCTimestamp(run.completed_at)
                        : "-"}
                    </TableCell>
                    <TableCell>
                      <Stack direction="row" spacing={1} alignItems="center">
                        <span>
                          {run.profile_name ||
                            t("configManagement.runNoProfile", "No profile")}
                        </span>
                        {run.check_mode && (
                          <Chip
                            label={t(
                              "configManagement.runCheckMode",
                              "Dry run",
                            )}
                            size="small"
                            variant="outlined"
                          />
                        )}
                      </Stack>
                    </TableCell>
                    <TableCell>{outcomeChip(run)}</TableCell>
                    <TableCell>
                      {t(
                        "configManagement.runTaskCounts",
                        "{{ok}} ok, {{changed}} changed, {{failed}} failed",
                        {
                          ok: run.tasks_ok,
                          changed: run.tasks_changed,
                          failed: run.tasks_failed,
                        },
                      )}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </TableContainer>
        )}
      </CardContent>
    </Card>
  );
};

export default ConfigProfileRunHistory;
