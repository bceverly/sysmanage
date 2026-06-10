/**
 * Phase 12.3: dispatch a federated command to a subordinate site.
 *
 * The coordinator only QUEUES the command (POST /federation/commands/dispatch).
 * The owning site's actuation worker then fans it out to local agents and
 * reports results back upstream — nothing runs synchronously from this
 * dialog.  Targets default to "all hosts at this site"; an operator can
 * narrow to specific host IDs (copyable from the cross-site Hosts page).
 */

import React, { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";

import Alert from "@mui/material/Alert";
import Button from "@mui/material/Button";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogContentText from "@mui/material/DialogContentText";
import DialogTitle from "@mui/material/DialogTitle";
import FormControl from "@mui/material/FormControl";
import FormControlLabel from "@mui/material/FormControlLabel";
import InputLabel from "@mui/material/InputLabel";
import MenuItem from "@mui/material/MenuItem";
import Radio from "@mui/material/Radio";
import RadioGroup from "@mui/material/RadioGroup";
import Select from "@mui/material/Select";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";

import { doDispatchFederationCommand } from "../Services/federation";

/** A selected host plus the site that owns it (multi-host mode). */
export interface DispatchHostTarget {
  host_id: string;
  site_id: string;
}

interface Props {
  open: boolean;
  onClose: () => void;
  /** Called after a successful dispatch so the caller can refresh its list. */
  onDispatched: () => void;
  /**
   * Single-site mode: dispatch to a whole site (optionally specific host
   * IDs typed by the operator).
   */
  siteId?: string;
  siteName?: string;
  /**
   * Multi-host mode: dispatch to a specific set of hosts that may span
   * MULTIPLE sites.  When provided (non-empty), the target UI is hidden
   * and dispatch fans out one command per distinct site_id.  Takes
   * precedence over ``siteId``.
   */
  hostTargets?: DispatchHostTarget[];
}

type CommandType =
  | "reboot"
  | "apply_updates"
  | "deploy_packages"
  | "run_script";

const COMMAND_TYPES: CommandType[] = [
  "reboot",
  "apply_updates",
  "deploy_packages",
  "run_script",
];

const FederationCommandDispatchDialog: React.FC<Props> = ({
  siteId,
  siteName,
  open,
  onClose,
  onDispatched,
  hostTargets,
}) => {
  const { t } = useTranslation();

  const multi = (hostTargets?.length ?? 0) > 0;
  // Distinct sites spanned by the selection (multi-host mode).
  const multiSiteIds = useMemo(
    () => Array.from(new Set((hostTargets ?? []).map((h) => h.site_id))),
    [hostTargets],
  );

  const [commandType, setCommandType] = useState<CommandType>("reboot");
  const [packages, setPackages] = useState("");
  const [script, setScript] = useState("");
  const [targetAll, setTargetAll] = useState(true);
  const [hostIds, setHostIds] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const commandLabel = useMemo(
    () => ({
      reboot: t("federationDispatch.types.reboot", "Reboot"),
      apply_updates: t("federationDispatch.types.applyUpdates", "Apply updates"),
      deploy_packages: t(
        "federationDispatch.types.deployPackages",
        "Install packages",
      ),
      run_script: t("federationDispatch.types.runScript", "Run script"),
    }),
    [t],
  );

  const reset = () => {
    setCommandType("reboot");
    setPackages("");
    setScript("");
    setTargetAll(true);
    setHostIds("");
    setError(null);
    setSubmitting(false);
  };

  const handleClose = () => {
    if (submitting) return;
    reset();
    onClose();
  };

  const buildParameters = (): Record<string, unknown> | null => {
    if (commandType === "deploy_packages" || commandType === "apply_updates") {
      const list = packages
        .split(/[\s,]+/)
        .map((p) => p.trim())
        .filter(Boolean);
      return list.length ? { package_names: list } : null;
    }
    if (commandType === "run_script") {
      return { script };
    }
    return null;
  };

  const validate = (): string | null => {
    if (commandType === "deploy_packages" && !packages.trim()) {
      return t(
        "federationDispatch.errors.packagesRequired",
        "Enter at least one package name.",
      );
    }
    if (commandType === "run_script" && !script.trim()) {
      return t(
        "federationDispatch.errors.scriptRequired",
        "Enter the script to run.",
      );
    }
    return null;
  };

  const handleDispatch = async () => {
    const validationError = validate();
    if (validationError) {
      setError(validationError);
      return;
    }
    setSubmitting(true);
    setError(null);
    const parameters = buildParameters();

    // Multi-host mode: fan out ONE command per distinct site, each with
    // that site's selected host IDs.  Dispatch is a per-site operation,
    // so a cross-site selection becomes N dispatches.
    if (multi) {
      const bySite = new Map<string, string[]>();
      for (const tgt of hostTargets ?? []) {
        const list = bySite.get(tgt.site_id) ?? [];
        list.push(tgt.host_id);
        bySite.set(tgt.site_id, list);
      }
      const results = await Promise.allSettled(
        Array.from(bySite.entries()).map(([sid, hosts]) =>
          doDispatchFederationCommand({
            command_type: commandType,
            target_site_id: sid,
            parameters,
            target_host_ids: hosts,
          }),
        ),
      );
      const failed = results.filter(
        (r) =>
          r.status === "rejected" ||
          (r.status === "fulfilled" && r.value.licensed === false),
      ).length;
      if (failed > 0) {
        setError(
          t(
            "federationDispatch.errors.partial",
            "{{failed}} of {{total}} site dispatches failed.",
            { failed, total: results.length },
          ),
        );
        setSubmitting(false);
        return;
      }
      reset();
      onDispatched();
      onClose();
      return;
    }

    if (!siteId) {
      setError(t("federationDispatch.errors.failed", "Failed to dispatch command."));
      setSubmitting(false);
      return;
    }
    const targetHostIds = targetAll
      ? null
      : hostIds
          .split(/[\s,]+/)
          .map((h) => h.trim())
          .filter(Boolean);
    try {
      const resp = await doDispatchFederationCommand({
        command_type: commandType,
        target_site_id: siteId,
        parameters,
        target_host_ids: targetHostIds,
      });
      if (resp.licensed === false) {
        setError(
          t(
            "federationDispatch.errors.unlicensed",
            "Federation requires an Enterprise license.",
          ),
        );
        setSubmitting(false);
        return;
      }
      reset();
      onDispatched();
      onClose();
    } catch (err) {
      setError(
        (err instanceof Error && err.message) ||
          t("federationDispatch.errors.failed", "Failed to dispatch command."),
      );
      setSubmitting(false);
    }
  };

  return (
    <Dialog open={open} onClose={handleClose} fullWidth maxWidth="sm">
      <DialogTitle>
        {t("federationDispatch.title", "Dispatch command")}
      </DialogTitle>
      <DialogContent>
        <DialogContentText sx={{ mb: 2 }}>
          {multi
            ? t(
                "federationDispatch.subtitleMulti",
                "Queue a command for {{hosts}} selected host(s) across {{sites}} site(s). Each site runs it and reports results back — nothing executes immediately.",
                {
                  hosts: hostTargets?.length ?? 0,
                  sites: multiSiteIds.length,
                },
              )
            : t(
                "federationDispatch.subtitle",
                "Queue a command for {{site}}. The site runs it on its hosts and reports results back — nothing executes immediately.",
                {
                  site: siteName || t("federationDispatch.thisSite", "this site"),
                },
              )}
        </DialogContentText>

        <Stack spacing={2}>
          <FormControl fullWidth size="small">
            <InputLabel id="fed-cmd-type-label">
              {t("federationDispatch.commandType", "Command")}
            </InputLabel>
            <Select
              labelId="fed-cmd-type-label"
              label={t("federationDispatch.commandType", "Command")}
              value={commandType}
              onChange={(e) => {
                setCommandType(e.target.value);
                setError(null);
              }}
            >
              {COMMAND_TYPES.map((c) => (
                <MenuItem key={c} value={c}>
                  {commandLabel[c]}
                </MenuItem>
              ))}
            </Select>
          </FormControl>

          {(commandType === "deploy_packages" ||
            commandType === "apply_updates") && (
            <TextField
              label={
                commandType === "deploy_packages"
                  ? t("federationDispatch.packages", "Package names")
                  : t(
                      "federationDispatch.packagesOptional",
                      "Package names (optional — blank = all updates)",
                    )
              }
              value={packages}
              onChange={(e) => setPackages(e.target.value)}
              placeholder="nginx, postgresql-16"
              fullWidth
              size="small"
            />
          )}

          {commandType === "run_script" && (
            <TextField
              label={t("federationDispatch.script", "Script")}
              value={script}
              onChange={(e) => setScript(e.target.value)}
              placeholder={"#!/bin/sh\n…"}
              fullWidth
              multiline
              minRows={4}
              size="small"
              slotProps={{ htmlInput: { style: { fontFamily: "monospace" } } }}
            />
          )}

          {!multi && (
            <FormControl>
              <RadioGroup
                value={targetAll ? "all" : "specific"}
                onChange={(e) => setTargetAll(e.target.value === "all")}
              >
                <FormControlLabel
                  value="all"
                  control={<Radio size="small" />}
                  label={t(
                    "federationDispatch.targetAll",
                    "All hosts at this site",
                  )}
                />
                <FormControlLabel
                  value="specific"
                  control={<Radio size="small" />}
                  label={t(
                    "federationDispatch.targetSpecific",
                    "Specific hosts (by ID)",
                  )}
                />
              </RadioGroup>
            </FormControl>
          )}

          {!multi && !targetAll && (
            <TextField
              label={t("federationDispatch.hostIds", "Host IDs")}
              value={hostIds}
              onChange={(e) => setHostIds(e.target.value)}
              placeholder={t(
                "federationDispatch.hostIdsHint",
                "Comma-separated host IDs (from the Hosts page)",
              )}
              fullWidth
              size="small"
            />
          )}

          {error && <Alert severity="error">{error}</Alert>}
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={handleClose} disabled={submitting}>
          {t("federationDispatch.cancel", "Cancel")}
        </Button>
        <Button
          variant="contained"
          onClick={handleDispatch}
          disabled={submitting}
        >
          {submitting
            ? t("federationDispatch.dispatching", "Dispatching…")
            : t("federationDispatch.dispatch", "Dispatch")}
        </Button>
      </DialogActions>
    </Dialog>
  );
};

export default FederationCommandDispatchDialog;
