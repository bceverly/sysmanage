/**
 * FederationReportPanel — the federated facet of the Reports page
 * (Phase 12.3).  Lets an operator pick one or more enrolled sites (or
 * "all") and renders a cross-site rollup report: per-site host counts,
 * worst compliance baseline, and CVE-severity counts, plus
 * enterprise-wide totals.  Data is the coordinator's cached rollups, so
 * the report is a screen-of-glass aggregate — no per-host drill-down.
 *
 * Self-gating: when the federation controller engine isn't licensed it
 * renders the Enterprise upsell rather than an empty table.
 */
import React, { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Checkbox from "@mui/material/Checkbox";
import Chip from "@mui/material/Chip";
import FormControl from "@mui/material/FormControl";
import InputLabel from "@mui/material/InputLabel";
import ListItemText from "@mui/material/ListItemText";
import MenuItem from "@mui/material/MenuItem";
import OutlinedInput from "@mui/material/OutlinedInput";
import Select, { SelectChangeEvent } from "@mui/material/Select";
import Table from "@mui/material/Table";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableHead from "@mui/material/TableHead";
import TableRow from "@mui/material/TableRow";
import Typography from "@mui/material/Typography";

import {
  doGetFederationCrossSiteReport,
  doListFederationSites,
  FederationCrossSiteReport,
  FederationSiteSummary,
} from "../Services/federation";

const FederationReportPanel: React.FC = () => {
  const { t } = useTranslation();
  const [licensed, setLicensed] = useState<boolean | null>(null);
  const [sites, setSites] = useState<FederationSiteSummary[]>([]);
  const [selected, setSelected] = useState<string[]>([]);
  const [report, setReport] = useState<FederationCrossSiteReport | null>(null);
  const [loading, setLoading] = useState(false);

  // Load the enrolled-site list for the multi-select on mount.
  useEffect(() => {
    let cancelled = false;
    doListFederationSites()
      .then((resp) => {
        if (cancelled) return;
        setLicensed(resp.licensed);
        if (resp.licensed) {
          setSites(
            (resp.sites ?? []).filter((s) => s.status === "enrolled"),
          );
        }
      })
      .catch(() => {
        if (!cancelled) setLicensed(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const generate = useCallback(async () => {
    setLoading(true);
    try {
      // Empty selection → all sites.
      const resp = await doGetFederationCrossSiteReport(selected);
      setReport(resp.licensed ? resp : null);
    } catch {
      setReport(null);
    } finally {
      setLoading(false);
    }
  }, [selected]);

  const handleSelect = (e: SelectChangeEvent<string[]>) => {
    const value = e.target.value;
    setSelected(typeof value === "string" ? value.split(",") : value);
  };

  if (licensed === false) {
    return (
      <Alert severity="info" data-testid="federation-report-upsell">
        {t(
          "federationReport.upsell",
          "Multi-site federation requires Enterprise.",
        )}
      </Alert>
    );
  }

  return (
    <Box data-testid="federation-report-panel">
      <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
        {t(
          "federationReport.subtitle",
          "Aggregate host, compliance, and vulnerability rollups across sites.",
        )}
      </Typography>
      <Box sx={{ display: "flex", gap: 2, alignItems: "center", mb: 2, flexWrap: "wrap" }}>
        <FormControl sx={{ minWidth: 260 }} size="small">
          <InputLabel id="fed-report-sites-label">
            {t("federationReport.sites", "Sites (all if none selected)")}
          </InputLabel>
          <Select
            labelId="fed-report-sites-label"
            multiple
            value={selected}
            onChange={handleSelect}
            input={
              <OutlinedInput
                label={t("federationReport.sites", "Sites (all if none selected)")}
              />
            }
            renderValue={(vals) =>
              vals
                .map((id) => sites.find((s) => s.id === id)?.name ?? id)
                .join(", ")
            }
            data-testid="federation-report-site-select"
          >
            {sites.map((s) => (
              <MenuItem key={s.id} value={s.id}>
                <Checkbox checked={selected.includes(s.id)} />
                <ListItemText primary={s.name} />
              </MenuItem>
            ))}
          </Select>
        </FormControl>
        <Button
          variant="contained"
          onClick={generate}
          disabled={loading}
          data-testid="federation-report-generate"
        >
          {t("federationReport.generate", "Generate report")}
        </Button>
      </Box>

      {report && (
        <Table size="small" data-testid="federation-report-table">
          <TableHead>
            <TableRow>
              <TableCell>{t("federationReport.col.site", "Site")}</TableCell>
              <TableCell align="right">
                {t("federationReport.col.hosts", "Hosts")}
              </TableCell>
              <TableCell align="right">
                {t("federationReport.col.active", "Active")}
              </TableCell>
              <TableCell>
                {t("federationReport.col.compliance", "Worst compliance")}
              </TableCell>
              <TableCell align="right">
                {t("federationReport.col.critical", "Critical CVEs")}
              </TableCell>
              <TableCell align="right">
                {t("federationReport.col.high", "High CVEs")}
              </TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {report.sites.map((row) => (
              <TableRow key={row.site_id} data-testid="federation-report-row">
                <TableCell>{row.site_name}</TableCell>
                <TableCell align="right">{row.host_count}</TableCell>
                <TableCell align="right">{row.active_count}</TableCell>
                <TableCell>
                  {row.worst_compliance ? (
                    <Chip
                      size="small"
                      color={
                        row.worst_compliance.score_percent < 70
                          ? "error"
                          : "default"
                      }
                      label={`${row.worst_compliance.baseline} ${row.worst_compliance.score_percent.toFixed(
                        0,
                      )}%`}
                    />
                  ) : (
                    "—"
                  )}
                </TableCell>
                <TableCell align="right">{row.critical_count}</TableCell>
                <TableCell align="right">{row.high_count}</TableCell>
              </TableRow>
            ))}
            <TableRow data-testid="federation-report-totals">
              <TableCell>
                <strong>
                  {t("federationReport.totals", "Totals ({{n}} sites)", {
                    n: report.totals.site_count ?? 0,
                  })}
                </strong>
              </TableCell>
              <TableCell align="right">
                <strong>{report.totals.host_count ?? 0}</strong>
              </TableCell>
              <TableCell align="right">
                <strong>{report.totals.active_count ?? 0}</strong>
              </TableCell>
              <TableCell />
              <TableCell align="right">
                <strong>{report.totals.critical_count ?? 0}</strong>
              </TableCell>
              <TableCell align="right">
                <strong>{report.totals.high_count ?? 0}</strong>
              </TableCell>
            </TableRow>
          </TableBody>
        </Table>
      )}
    </Box>
  );
};

export default FederationReportPanel;
