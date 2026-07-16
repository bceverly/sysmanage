// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

/**
 * Phase 12.3: federation audit log viewer.
 *
 * Lists every cross-site operation the coordinator has recorded —
 * enrollment, suspend / resume / remove, policy assignments and
 * pushes, command dispatches, and ad-hoc engine events.  Filters
 * compose with AND (site, operation type, actor, time window) and
 * the URL carries them so the operator can deep-link a filtered
 * view (e.g. SiteDetail's "View audit log" button pre-filters by
 * ``?site_id=<id>``).
 *
 * When the federation controller engine isn't loaded, the OSS stub
 * returns ``{licensed: false, entries: []}`` and this page renders
 * the same Enterprise upsell every other federation page uses.
 */

import React, { useCallback, useEffect, useMemo, useState } from "react";
import { useLocation, useNavigate, useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";

import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import CircularProgress from "@mui/material/CircularProgress";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import Table from "@mui/material/Table";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableContainer from "@mui/material/TableContainer";
import TableHead from "@mui/material/TableHead";
import TablePagination from "@mui/material/TablePagination";
import TableRow from "@mui/material/TableRow";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";

import {
  doListFederationAuditLog,
  FederationAuditEntry,
  FederationAuditListParams,
} from "../Services/federation";

interface AuditLogState {
  loading: boolean;
  licensed: boolean | null;
  entries: FederationAuditEntry[];
  total: number;
  error: string | null;
}

const DEFAULT_PAGE_SIZE = 25;

/** Parse the filter inputs into the typed params object the service expects. */
function buildParams(
  searchParams: URLSearchParams,
  page: number,
  pageSize: number,
): FederationAuditListParams {
  const params: FederationAuditListParams = {
    limit: pageSize,
    offset: page * pageSize,
  };
  const siteId = searchParams.get("site_id");
  const operation = searchParams.get("operation");
  const actor = searchParams.get("actor_userid");
  if (siteId) params.site_id = siteId;
  if (operation) params.operation = operation;
  if (actor) params.actor_userid = actor;
  return params;
}

function formatTimestamp(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toLocaleString();
}

const FederationAuditLog: React.FC = () => {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const location = useLocation();
  const [searchParams, setSearchParams] = useSearchParams();

  const [state, setState] = useState<AuditLogState>({
    loading: true,
    licensed: null,
    entries: [],
    total: 0,
    error: null,
  });
  const [page, setPage] = useState(0);
  const [pageSize, setPageSize] = useState(DEFAULT_PAGE_SIZE);

  // Working copies of filters so typing in the boxes doesn't fire a
  // fetch per keystroke.  Committed to the URL on "Apply".
  const [filterSiteId, setFilterSiteId] = useState(
    searchParams.get("site_id") ?? "",
  );
  const [filterOperation, setFilterOperation] = useState(
    searchParams.get("operation") ?? "",
  );
  const [filterActor, setFilterActor] = useState(
    searchParams.get("actor_userid") ?? "",
  );

  const fetchData = useCallback(async () => {
    setState((prev) => ({ ...prev, loading: true, error: null }));
    try {
      const data = await doListFederationAuditLog(
        buildParams(searchParams, page, pageSize),
      );
      setState({
        loading: false,
        licensed: Boolean(data.licensed),
        entries: data.entries ?? [],
        total: data.total ?? (data.entries?.length ?? 0),
        error: null,
      });
    } catch (err) {
      setState({
        loading: false,
        licensed: null,
        entries: [],
        total: 0,
        error:
          (err instanceof Error && err.message) ||
          t("audit.errorLoad", "Failed to load federation audit log."),
      });
    }
  }, [searchParams, page, pageSize, t]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  // Whenever the URL filter params change externally (e.g. SiteDetail's
  // deep-link), reflect them into the working filter inputs.
  useEffect(() => {
    setFilterSiteId(searchParams.get("site_id") ?? "");
    setFilterOperation(searchParams.get("operation") ?? "");
    setFilterActor(searchParams.get("actor_userid") ?? "");
    // Reset to first page on a filter-driven navigation.
    setPage(0);
  }, [searchParams]);

  const applyFilters = () => {
    const next = new URLSearchParams(location.search);
    if (filterSiteId.trim()) {
      next.set("site_id", filterSiteId.trim());
    } else {
      next.delete("site_id");
    }
    if (filterOperation.trim()) {
      next.set("operation", filterOperation.trim());
    } else {
      next.delete("operation");
    }
    if (filterActor.trim()) {
      next.set("actor_userid", filterActor.trim());
    } else {
      next.delete("actor_userid");
    }
    setSearchParams(next);
  };

  const clearFilters = () => {
    setFilterSiteId("");
    setFilterOperation("");
    setFilterActor("");
    setSearchParams(new URLSearchParams());
  };

  const hasActiveFilters = useMemo(
    () =>
      Boolean(
        searchParams.get("site_id") ||
          searchParams.get("operation") ||
          searchParams.get("actor_userid"),
      ),
    [searchParams],
  );

  // ----- Render branches -----

  if (state.loading && state.entries.length === 0) {
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
      <Typography variant="h5" component="h1" gutterBottom>
        {t("audit.title", "Federation Audit Log")}
      </Typography>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 3 }}>
        {t(
          "audit.subtitle",
          "Every cross-site operation logged centrally by the coordinator.",
        )}
      </Typography>

      {/* Filter row -------------------------------------------------- */}
      <Paper variant="outlined" sx={{ p: 2, mb: 2 }}>
        <Stack direction={{ xs: "column", md: "row" }} spacing={2}>
          <TextField
            label={t("audit.filters.siteId", "Site ID")}
            value={filterSiteId}
            onChange={(e) => setFilterSiteId(e.target.value)}
            fullWidth
            size="small"
          />
          <TextField
            label={t("audit.filters.operation", "Operation")}
            value={filterOperation}
            onChange={(e) => setFilterOperation(e.target.value)}
            fullWidth
            size="small"
          />
          <TextField
            label={t("audit.filters.actor", "Actor")}
            value={filterActor}
            onChange={(e) => setFilterActor(e.target.value)}
            fullWidth
            size="small"
          />
          <Stack direction="row" spacing={1}>
            <Button variant="contained" onClick={applyFilters}>
              {t("audit.filters.apply", "Apply")}
            </Button>
            <Button
              onClick={clearFilters}
              disabled={!hasActiveFilters}
            >
              {t("audit.filters.clear", "Clear")}
            </Button>
          </Stack>
        </Stack>
      </Paper>

      {/* Table ------------------------------------------------------- */}
      {state.entries.length === 0 ? (
        <Alert severity="info">
          {hasActiveFilters
            ? t("audit.emptyFiltered", "No audit entries match the filters.")
            : t("audit.empty", "No federation audit entries yet.")}
        </Alert>
      ) : (
        <TableContainer component={Paper} variant="outlined">
          <Table size="small" data-testid="audit-table">
            <TableHead>
              <TableRow>
                <TableCell>{t("audit.columns.timestamp", "Timestamp")}</TableCell>
                <TableCell>{t("audit.columns.operation", "Operation")}</TableCell>
                <TableCell>{t("audit.columns.actor", "Actor")}</TableCell>
                <TableCell>{t("audit.columns.site", "Site")}</TableCell>
                <TableCell>{t("audit.columns.details", "Details")}</TableCell>
                <TableCell />
              </TableRow>
            </TableHead>
            <TableBody>
              {state.entries.map((entry) => (
                <TableRow key={entry.id} hover>
                  <TableCell>{formatTimestamp(entry.created_at)}</TableCell>
                  <TableCell>
                    <Chip
                      label={entry.operation}
                      size="small"
                      variant="outlined"
                    />
                  </TableCell>
                  <TableCell>{entry.actor_userid ?? "—"}</TableCell>
                  <TableCell>
                    {entry.target_site_name || entry.target_site_id || "—"}
                  </TableCell>
                  <TableCell
                    sx={{
                      maxWidth: 360,
                      whiteSpace: "nowrap",
                      overflow: "hidden",
                      textOverflow: "ellipsis",
                      fontFamily: "monospace",
                      fontSize: "0.8rem",
                    }}
                    title={
                      entry.details
                        ? JSON.stringify(entry.details, null, 2)
                        : ""
                    }
                  >
                    {entry.details
                      ? JSON.stringify(entry.details)
                      : "—"}
                  </TableCell>
                  <TableCell>
                    {entry.target_site_id && (
                      <Button
                        size="small"
                        onClick={() =>
                          navigate(
                            `/sites/${encodeURIComponent(
                              entry.target_site_id ?? "",
                            )}`,
                          )
                        }
                      >
                        {t("audit.columns.openSite", "Open")}
                      </Button>
                    )}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
          <TablePagination
            component="div"
            count={state.total}
            page={page}
            onPageChange={(_, p) => setPage(p)}
            rowsPerPage={pageSize}
            onRowsPerPageChange={(e) => {
              setPageSize(Number.parseInt(e.target.value, 10));
              setPage(0);
            }}
            rowsPerPageOptions={[10, 25, 50, 100]}
          />
        </TableContainer>
      )}
    </Box>
  );
};

export default FederationAuditLog;
