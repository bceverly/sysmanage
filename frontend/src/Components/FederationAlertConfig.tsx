/**
 * FederationAlertConfig — operator-configurable rollup-alert thresholds
 * (Phase 12.1).  A self-contained card that loads the effective thresholds
 * (operator overrides merged over built-in defaults) and lets the operator
 * override any subset.  A blank field clears that override (reverts to the
 * built-in default).
 *
 * Renders nothing when the federation controller engine isn't licensed —
 * the host page already shows the Enterprise upsell, so this just stays out
 * of the way.
 */
import React, { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Card from "@mui/material/Card";
import CardContent from "@mui/material/CardContent";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";

import {
  doGetFederationAlertConfig,
  doUpdateFederationAlertConfig,
  FederationAlertThresholds,
} from "../Services/federation";

type FieldKey = keyof FederationAlertThresholds;

interface FieldDef {
  key: FieldKey;
  labelKey: string;
  labelFallback: string;
  helpKey: string;
  helpFallback: string;
  isFloat?: boolean;
}

const FIELDS: FieldDef[] = [
  {
    key: "offline_multiplier",
    labelKey: "federationAlertConfig.offlineMultiplier",
    labelFallback: "Offline multiplier",
    helpKey: "federationAlertConfig.offlineMultiplierHelp",
    helpFallback: "× the site's sync interval before it's flagged offline",
  },
  {
    key: "min_offline_seconds",
    labelKey: "federationAlertConfig.minOfflineSeconds",
    labelFallback: "Minimum offline seconds",
    helpKey: "federationAlertConfig.minOfflineSecondsHelp",
    helpFallback: "Floor so fast sync intervals don't flap",
  },
  {
    key: "compliance_threshold",
    labelKey: "federationAlertConfig.complianceThreshold",
    labelFallback: "Compliance threshold (%)",
    helpKey: "federationAlertConfig.complianceThresholdHelp",
    helpFallback: "Alert when a baseline score drops below this percent",
    isFloat: true,
  },
  {
    key: "critical_cve_threshold",
    labelKey: "federationAlertConfig.criticalCveThreshold",
    labelFallback: "Critical CVE threshold",
    helpKey: "federationAlertConfig.criticalCveThresholdHelp",
    helpFallback: "Alert when critical-CVE count strictly exceeds this",
  },
];

/** A blank input → null (clear override); otherwise the parsed number. */
function parseField(raw: string, isFloat: boolean): number | null {
  const trimmed = raw.trim();
  if (trimmed === "") return null;
  return isFloat ? Number.parseFloat(trimmed) : Number.parseInt(trimmed, 10);
}

const FederationAlertConfig: React.FC = () => {
  const { t } = useTranslation();
  const [licensed, setLicensed] = useState<boolean | null>(null);
  const [effective, setEffective] = useState<FederationAlertThresholds | null>(
    null,
  );
  // Per-field text inputs; empty string means "no override".
  const [inputs, setInputs] = useState<Record<FieldKey, string>>({
    offline_multiplier: "",
    min_offline_seconds: "",
    compliance_threshold: "",
    critical_cve_threshold: "",
  });
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const applyOverrides = useCallback((overrides: FederationAlertThresholds) => {
    setInputs({
      offline_multiplier:
        overrides.offline_multiplier == null
          ? ""
          : String(overrides.offline_multiplier),
      min_offline_seconds:
        overrides.min_offline_seconds == null
          ? ""
          : String(overrides.min_offline_seconds),
      compliance_threshold:
        overrides.compliance_threshold == null
          ? ""
          : String(overrides.compliance_threshold),
      critical_cve_threshold:
        overrides.critical_cve_threshold == null
          ? ""
          : String(overrides.critical_cve_threshold),
    });
  }, []);

  const load = useCallback(async () => {
    try {
      const resp = await doGetFederationAlertConfig();
      setLicensed(resp.licensed);
      if (resp.licensed) {
        setEffective(resp.effective ?? null);
        if (resp.overrides) applyOverrides(resp.overrides);
      }
    } catch {
      setLicensed(false);
    }
  }, [applyOverrides]);

  useEffect(() => {
    load();
  }, [load]);

  const handleSave = async () => {
    setSaving(true);
    setMessage(null);
    setError(null);
    try {
      const overrides: Partial<FederationAlertThresholds> = {};
      for (const f of FIELDS) {
        overrides[f.key] = parseField(inputs[f.key], Boolean(f.isFloat));
      }
      const resp = await doUpdateFederationAlertConfig(overrides);
      if (resp.effective) setEffective(resp.effective);
      setMessage(
        t("federationAlertConfig.saved", "Alert thresholds saved."),
      );
    } catch (err) {
      setError(
        (err instanceof Error && err.message) ||
          t("federationAlertConfig.saveFailed", "Failed to save thresholds."),
      );
    } finally {
      setSaving(false);
    }
  };

  // Unlicensed (or not yet known) → render nothing; host page shows upsell.
  if (licensed !== true) return null;

  return (
    <Card variant="outlined" sx={{ mb: 2 }} data-testid="alert-config-card">
      <CardContent>
        <Typography variant="h6" gutterBottom>
          {t("federationAlertConfig.title", "Alert thresholds")}
        </Typography>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
          {t(
            "federationAlertConfig.subtitle",
            "Leave a field blank to use the built-in default.",
          )}
        </Typography>
        <Stack spacing={2}>
          {FIELDS.map((f) => (
            <TextField
              key={f.key}
              type="number"
              size="small"
              label={t(f.labelKey, f.labelFallback)}
              value={inputs[f.key]}
              onChange={(e) =>
                setInputs((prev) => ({ ...prev, [f.key]: e.target.value }))
              }
              helperText={
                effective
                  ? `${t(f.helpKey, f.helpFallback)} — ${t(
                      "federationAlertConfig.effective",
                      "effective",
                    )}: ${String(effective[f.key])}`
                  : t(f.helpKey, f.helpFallback)
              }
              slotProps={{
                htmlInput: { "data-testid": `alert-config-${f.key}` },
              }}
            />
          ))}
        </Stack>
        <Box sx={{ mt: 2 }}>
          <Button
            variant="contained"
            onClick={handleSave}
            disabled={saving}
            data-testid="alert-config-save"
          >
            {t("federationAlertConfig.save", "Save thresholds")}
          </Button>
        </Box>
        {message && (
          <Alert severity="success" sx={{ mt: 2 }} data-testid="alert-config-msg">
            {message}
          </Alert>
        )}
        {error && (
          <Alert severity="error" sx={{ mt: 2 }} data-testid="alert-config-err">
            {error}
          </Alert>
        )}
      </CardContent>
    </Card>
  );
};

export default FederationAlertConfig;
