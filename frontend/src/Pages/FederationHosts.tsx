/**
 * Phase 12.3: federated cross-site host directory.
 *
 * Renders the coordinator's SYNCED, summary-tier view of every host
 * across every enrolled site — the data the sites push up, never a
 * live query fanned out to subordinates.  Filters compose with AND and
 * ride the URL so SiteDetail's "See hosts at this site" button can
 * deep-link a single-site view (``?site_id=<id>``).
 *
 * Drill-down is deliberately NAVIGATIONAL: the detail dialog shows the
 * synced summary plus the owning site's name and a deep-link into THAT
 * site's own web UI for live detail.  The coordinator never blocks on a
 * subordinate to answer a read — consistent with the queue-everything
 * architecture.
 *
 * When the federation controller engine isn't loaded the OSS stub
 * returns ``{licensed: false}`` and this page shows the same Enterprise
 * upsell as the rest of the federation surface.
 */

import React, { useCallback, useEffect, useMemo, useState } from "react";
import { useLocation, useNavigate, useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";

import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Checkbox from "@mui/material/Checkbox";
import Chip from "@mui/material/Chip";
import CircularProgress from "@mui/material/CircularProgress";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import Link from "@mui/material/Link";
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
  doGetFederationHostDetail,
  doSearchFederationHosts,
  FederationHostDetailResponse,
  FederationHostDirectoryEntry,
} from "../Services/federation";
import FederationCommandDispatchDialog from "../Components/FederationCommandDispatchDialog";

interface HostsState {
  loading: boolean;
  licensed: boolean | null;
  hosts: FederationHostDirectoryEntry[];
  total: number;
  error: string | null;
}

const DEFAULT_PAGE_SIZE = 25;

type StatusColor = "success" | "error" | "warning" | "default";

function statusColor(status?: string | null): StatusColor {
  const s = (status ?? "").toLowerCase();
  if (s === "up" || s === "online" || s === "active") return "success";
  if (s === "down" || s === "offline") return "error";
  if (s === "unknown" || s === "") return "default";
  return "warning";
}

function formatTimestamp(iso?: string | null): string {
  if (!iso) return "—";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toLocaleString();
}

const FederationHosts: React.FC = () => {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const location = useLocation();
  const [searchParams, setSearchParams] = useSearchParams();

  const [state, setState] = useState<HostsState>({
    loading: true,
    licensed: null,
    hosts: [],
    total: 0,
    error: null,
  });
  const [page, setPage] = useState(0);
  const [pageSize, setPageSize] = useState(DEFAULT_PAGE_SIZE);

  // Working filter inputs — committed to the URL on "Apply" so a fetch
  // doesn't fire per keystroke.
  const [filterText, setFilterText] = useState(
    searchParams.get("free_text") ?? "",
  );
  const [filterStatus, setFilterStatus] = useState(
    searchParams.get("status") ?? "",
  );
  const [filterOsFamily, setFilterOsFamily] = useState(
    searchParams.get("os_family") ?? "",
  );

  // Drill-down dialog state.
  const [detailOpen, setDetailOpen] = useState(false);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detail, setDetail] = useState<FederationHostDetailResponse | null>(
    null,
  );

  // Bulk-dispatch selection: host_id -> site_id.  A Map so a selection
  // survives pagination (we still know each picked host's owning site
  // even after it scrolls off the current page).
  const [selected, setSelected] = useState<Map<string, string>>(new Map());
  const [dispatchOpen, setDispatchOpen] = useState(false);

  const toggleHost = useCallback((host: FederationHostDirectoryEntry) => {
    setSelected((prev) => {
      const next = new Map(prev);
      if (next.has(host.host_id)) next.delete(host.host_id);
      else next.set(host.host_id, host.site_id);
      return next;
    });
  }, []);

  const siteId = searchParams.get("site_id") ?? "";

  const fetchData = useCallback(async () => {
    setState((prev) => ({ ...prev, loading: true, error: null }));
    try {
      const data = await doSearchFederationHosts({
        site_id: searchParams.get("site_id") ?? undefined,
        free_text: searchParams.get("free_text") ?? undefined,
        status: searchParams.get("status") ?? undefined,
        os_family: searchParams.get("os_family") ?? undefined,
        limit: pageSize,
        offset: page * pageSize,
      });
      setState({
        loading: false,
        licensed: Boolean(data.licensed),
        hosts: data.hosts ?? [],
        total: data.total ?? (data.hosts?.length ?? 0),
        error: null,
      });
    } catch (err) {
      setState({
        loading: false,
        licensed: null,
        hosts: [],
        total: 0,
        error:
          (err instanceof Error && err.message) ||
          t("federationHosts.errorLoad", "Failed to load cross-site hosts."),
      });
    }
  }, [searchParams, page, pageSize, t]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  // Reflect external URL filter changes (e.g. SiteDetail deep-link).
  useEffect(() => {
    setFilterText(searchParams.get("free_text") ?? "");
    setFilterStatus(searchParams.get("status") ?? "");
    setFilterOsFamily(searchParams.get("os_family") ?? "");
    setPage(0);
  }, [searchParams]);

  const applyFilters = () => {
    const next = new URLSearchParams(location.search);
    const setOrDelete = (key: string, value: string) => {
      if (value.trim()) next.set(key, value.trim());
      else next.delete(key);
    };
    setOrDelete("free_text", filterText);
    setOrDelete("status", filterStatus);
    setOrDelete("os_family", filterOsFamily);
    setSearchParams(next);
  };

  const clearFilters = () => {
    setFilterText("");
    setFilterStatus("");
    setFilterOsFamily("");
    // Preserve site_id scoping when clearing the free-form filters.
    const next = new URLSearchParams();
    if (siteId) next.set("site_id", siteId);
    setSearchParams(next);
  };

  const clearSiteScope = () => {
    const next = new URLSearchParams(location.search);
    next.delete("site_id");
    setSearchParams(next);
  };

  const hasActiveFilters = useMemo(
    () =>
      Boolean(
        searchParams.get("free_text") ||
          searchParams.get("status") ||
          searchParams.get("os_family"),
      ),
    [searchParams],
  );

  const openDetail = useCallback(async (hostId: string) => {
    setDetailOpen(true);
    setDetailLoading(true);
    setDetail(null);
    try {
      const data = await doGetFederationHostDetail(hostId);
      setDetail(data);
    } catch {
      setDetail(null);
    } finally {
      setDetailLoading(false);
    }
  }, []);

  // ----- Render branches -----

  if (state.loading && state.hosts.length === 0) {
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

  const detailHost = detail?.host ?? null;
  const detailSite = detail?.site ?? null;

  return (
    <Box sx={{ p: 3 }}>
      <Typography variant="h5" component="h1" gutterBottom>
        {t("federationHosts.title", "Cross-Site Hosts")}
      </Typography>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
        {t(
          "federationHosts.subtitle",
          "Every host across all enrolled sites, from the coordinator's synced directory.",
        )}
      </Typography>

      {siteId && (
        <Chip
          sx={{ mb: 2 }}
          color="primary"
          variant="outlined"
          label={t("federationHosts.scopedToSite", "Scoped to one site")}
          onDelete={clearSiteScope}
        />
      )}

      {/* Filter row -------------------------------------------------- */}
      <Paper variant="outlined" sx={{ p: 2, mb: 2 }}>
        <Stack direction={{ xs: "column", md: "row" }} spacing={2}>
          <TextField
            label={t("federationHosts.filters.search", "Search (name / IP)")}
            value={filterText}
            onChange={(e) => setFilterText(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") applyFilters();
            }}
            fullWidth
            size="small"
          />
          <TextField
            label={t("federationHosts.filters.status", "Status")}
            value={filterStatus}
            onChange={(e) => setFilterStatus(e.target.value)}
            fullWidth
            size="small"
          />
          <TextField
            label={t("federationHosts.filters.osFamily", "OS family")}
            value={filterOsFamily}
            onChange={(e) => setFilterOsFamily(e.target.value)}
            fullWidth
            size="small"
          />
          <Stack direction="row" spacing={1}>
            <Button variant="contained" onClick={applyFilters}>
              {t("federationHosts.filters.apply", "Apply")}
            </Button>
            <Button onClick={clearFilters} disabled={!hasActiveFilters}>
              {t("federationHosts.filters.clear", "Clear")}
            </Button>
          </Stack>
        </Stack>
      </Paper>

      {/* Bulk-dispatch toolbar (shown when ≥1 host selected) --------- */}
      {selected.size > 0 && (
        <Paper
          variant="outlined"
          sx={{
            p: 1.5,
            mb: 2,
            display: "flex",
            alignItems: "center",
            gap: 2,
            bgcolor: "action.hover",
          }}
        >
          <Typography variant="body2" sx={{ flexGrow: 1 }}>
            {t("federationHosts.bulk.selected", "{{n}} hosts selected", {
              n: selected.size,
            })}
          </Typography>
          <Button
            variant="contained"
            size="small"
            onClick={() => setDispatchOpen(true)}
            data-testid="bulk-dispatch-button"
          >
            {t("federationHosts.bulk.dispatch", "Dispatch command")}
          </Button>
          <Button size="small" onClick={() => setSelected(new Map())}>
            {t("federationHosts.bulk.clear", "Clear")}
          </Button>
        </Paper>
      )}

      {/* Table ------------------------------------------------------- */}
      {state.hosts.length === 0 ? (
        <Alert severity="info">
          {hasActiveFilters || siteId
            ? t(
                "federationHosts.emptyFiltered",
                "No hosts match the current filters.",
              )
            : t(
                "federationHosts.empty",
                "No hosts have been synced from any site yet.",
              )}
        </Alert>
      ) : (
        <TableContainer component={Paper} variant="outlined">
          <Table size="small" data-testid="federation-hosts-table">
            <TableHead>
              <TableRow>
                <TableCell padding="checkbox">
                  <Checkbox
                    size="small"
                    checked={
                      state.hosts.length > 0 &&
                      state.hosts.every((h) => selected.has(h.host_id))
                    }
                    indeterminate={
                      state.hosts.some((h) => selected.has(h.host_id)) &&
                      !state.hosts.every((h) => selected.has(h.host_id))
                    }
                    onChange={(e) => {
                      const checked = e.target.checked;
                      setSelected((prev) => {
                        const next = new Map(prev);
                        for (const h of state.hosts) {
                          if (checked) next.set(h.host_id, h.site_id);
                          else next.delete(h.host_id);
                        }
                        return next;
                      });
                    }}
                    slotProps={{
                      input: {
                        "aria-label": t(
                          "federationHosts.bulk.selectAll",
                          "Select all on this page",
                        ),
                      },
                    }}
                  />
                </TableCell>
                <TableCell>
                  {t("federationHosts.columns.fqdn", "Host")}
                </TableCell>
                <TableCell>{t("federationHosts.columns.ipv4", "IPv4")}</TableCell>
                <TableCell>{t("federationHosts.columns.os", "OS")}</TableCell>
                <TableCell>
                  {t("federationHosts.columns.platform", "Platform")}
                </TableCell>
                <TableCell>
                  {t("federationHosts.columns.status", "Status")}
                </TableCell>
                <TableCell>
                  {t("federationHosts.columns.lastSeen", "Last seen")}
                </TableCell>
                <TableCell />
              </TableRow>
            </TableHead>
            <TableBody>
              {state.hosts.map((host) => (
                <TableRow key={host.host_id} hover selected={selected.has(host.host_id)}>
                  <TableCell padding="checkbox">
                    <Checkbox
                      size="small"
                      checked={selected.has(host.host_id)}
                      onChange={() => toggleHost(host)}
                    />
                  </TableCell>
                  <TableCell>{host.fqdn || host.host_id}</TableCell>
                  <TableCell>{host.ipv4 || "—"}</TableCell>
                  <TableCell>
                    {[host.os_family, host.os_version]
                      .filter(Boolean)
                      .join(" ") || "—"}
                  </TableCell>
                  <TableCell>{host.platform || "—"}</TableCell>
                  <TableCell>
                    <Chip
                      label={host.status || "unknown"}
                      size="small"
                      color={statusColor(host.status)}
                      variant="outlined"
                    />
                  </TableCell>
                  <TableCell>{formatTimestamp(host.last_seen)}</TableCell>
                  <TableCell align="right">
                    <Stack
                      direction="row"
                      spacing={1}
                      justifyContent="flex-end"
                    >
                      <Button
                        size="small"
                        onClick={() => openDetail(host.host_id)}
                      >
                        {t("federationHosts.actions.detail", "Details")}
                      </Button>
                      {host.site_id && (
                        <Button
                          size="small"
                          onClick={() =>
                            navigate(
                              `/sites/${encodeURIComponent(host.site_id)}`,
                            )
                          }
                        >
                          {t("federationHosts.actions.openSite", "Site")}
                        </Button>
                      )}
                    </Stack>
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

      {/* Drill-down dialog ------------------------------------------- */}
      <Dialog
        open={detailOpen}
        onClose={() => setDetailOpen(false)}
        fullWidth
        maxWidth="sm"
      >
        <DialogTitle>
          {detailHost?.fqdn ||
            t("federationHosts.detail.title", "Host detail")}
        </DialogTitle>
        <DialogContent dividers>
          {detailLoading && (
            <Box sx={{ display: "flex", justifyContent: "center", py: 3 }}>
              <CircularProgress />
            </Box>
          )}
          {!detailLoading && !detailHost && (
            <Alert severity="warning">
              {t(
                "federationHosts.detail.notFound",
                "This host is no longer in the directory.",
              )}
            </Alert>
          )}
          {!detailLoading && detailHost && (
            <Stack spacing={1}>
              <DetailRow
                label={t("federationHosts.columns.fqdn", "Host")}
                value={detailHost.fqdn || detailHost.host_id}
              />
              <DetailRow
                label={t("federationHosts.columns.ipv4", "IPv4")}
                value={detailHost.ipv4 || "—"}
              />
              <DetailRow
                label={t("federationHosts.detail.ipv6", "IPv6")}
                value={detailHost.ipv6 || "—"}
              />
              <DetailRow
                label={t("federationHosts.columns.os", "OS")}
                value={
                  [detailHost.os_family, detailHost.os_version]
                    .filter(Boolean)
                    .join(" ") || "—"
                }
              />
              <DetailRow
                label={t("federationHosts.columns.status", "Status")}
                value={detailHost.status || "unknown"}
              />
              <DetailRow
                label={t("federationHosts.detail.site", "Owning site")}
                value={detailSite?.name || detailHost.site_id}
              />
              {detail?.site_detail_url ? (
                <Typography variant="body2" sx={{ mt: 1 }}>
                  <Link
                    href={detail.site_detail_url}
                    target="_blank"
                    rel="noopener noreferrer"
                  >
                    {t(
                      "federationHosts.detail.viewLive",
                      "View live detail on {{site}} →",
                      { site: detailSite?.name || t("federationHosts.detail.theSite", "the site") },
                    )}
                  </Link>
                </Typography>
              ) : (
                <Typography variant="caption" color="text.secondary">
                  {t(
                    "federationHosts.detail.noLiveLink",
                    "Live detail link unavailable (owning site has no URL).",
                  )}
                </Typography>
              )}
            </Stack>
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setDetailOpen(false)}>
            {t("federationHosts.detail.close", "Close")}
          </Button>
        </DialogActions>
      </Dialog>

      <FederationCommandDispatchDialog
        open={dispatchOpen}
        onClose={() => setDispatchOpen(false)}
        onDispatched={() => setSelected(new Map())}
        hostTargets={Array.from(selected.entries()).map(
          ([host_id, site_id]) => ({ host_id, site_id }),
        )}
      />
    </Box>
  );
};

const DetailRow: React.FC<{ label: string; value: string }> = ({
  label,
  value,
}) => (
  <Stack direction="row" spacing={2}>
    <Typography
      variant="body2"
      color="text.secondary"
      sx={{ minWidth: 120, fontWeight: 500 }}
    >
      {label}
    </Typography>
    <Typography variant="body2" sx={{ wordBreak: "break-all" }}>
      {value}
    </Typography>
  </Stack>
);

export default FederationHosts;
