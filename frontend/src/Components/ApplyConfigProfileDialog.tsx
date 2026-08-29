// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

import React, { useEffect, useState } from "react";
import {
  Alert,
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  FormControlLabel,
  Stack,
  Switch,
  TextField,
  Typography,
} from "@mui/material";
import { useTranslation } from "react-i18next";
import {
  applyConfigProfile,
  getConfigProfiles,
  ConfigProfile,
} from "../Services/configManagementService";

interface ApplyConfigProfileDialogProps {
  open: boolean;
  hostId: string;
  /**
   * Engines that are actually ready on this host, readiest first.
   *
   * A list, not one executor: a host may have several installed and the
   * operator picks. The chosen engine decides which field the server expects
   * (DSC takes `resources`, everything else takes a playbook/manifest).
   */
  engines: string[];
  onClose: () => void;
  /** Called after the profile is queued, so the run history can refresh. */
  onApplied?: () => void;
}

const ApplyConfigProfileDialog: React.FC<ApplyConfigProfileDialogProps> = ({
  open,
  hostId,
  engines,
  onClose,
  onApplied,
}) => {
  const { t } = useTranslation();
  // Stored profiles, if this server has the Enterprise module. An empty list
  // (including the 402 case) simply means the picker is not offered -- the
  // ad-hoc path below is open source and must stay usable either way.
  const [stored, setStored] = useState<ConfigProfile[]>([]);
  const [profileId, setProfileId] = useState("");
  const [engine, setEngine] = useState(engines[0] || "ansible-core");
  const isDsc = engine === "dsc";
  const [body, setBody] = useState("");
  const [profileName, setProfileName] = useState("");
  // Defaults to a DRY RUN on purpose. This dialog runs arbitrary code as root
  // on a managed host; the safe option should be the one you get by not
  // thinking about it, and the destructive one should take a deliberate act.
  const [checkMode, setCheckMode] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    const loadStored = async () => {
      try {
        const all = await getConfigProfiles();
        setStored(all.filter((p) => p.is_active));
      } catch {
        // Unlicensed (402) or unreachable: fall back to ad-hoc only. This is
        // an expected state on an open-source server, not an error worth
        // showing an operator who never asked for stored profiles.
        //
        // The functional form matters: writing a fresh [] over an already
        // empty list is a real re-render for no change, which on the common
        // unlicensed path is pure noise.
        setStored((prev) => (prev.length ? [] : prev));
      }
    };
    loadStored();
  }, [open]);

  const reset = () => {
    setProfileId("");
    setEngine(engines[0] || "ansible-core");
    setBody("");
    setProfileName("");
    setCheckMode(true);
    setError(null);
  };

  const handleClose = () => {
    if (submitting) return;
    reset();
    onClose();
  };

  const handleApply = async () => {
    setSubmitting(true);
    setError(null);
    try {
      let resources: Record<string, unknown>[] | undefined;
      if (isDsc && !profileId) {
        // Parse locally so a typo is caught here, with a message about JSON,
        // rather than becoming an opaque 422 from the request body.
        const parsed = JSON.parse(body) as unknown;
        if (!Array.isArray(parsed)) {
          throw new SyntaxError("not an array");
        }
        resources = parsed as Record<string, unknown>[];
      }
      await applyConfigProfile(
        hostId,
        profileId
          ? // The server reads the stored profile's engine and body; sending
            // ours too would let a stale copy in this tab overwrite what was
            // saved.
            { profile_id: profileId, check_mode: checkMode }
          : {
              engine,
              ...(isDsc ? { resources } : { playbook: body }),
              ...(profileName.trim()
                ? { profile_name: profileName.trim() }
                : {}),
              check_mode: checkMode,
            },
      );
      reset();
      onClose();
      onApplied?.();
    } catch (err) {
      if (err instanceof SyntaxError) {
        setError(
          t(
            "configManagement.applyInvalidJson",
            "The resources must be a JSON array of DSC resource objects.",
          ),
        );
      } else {
        // Prefer the server's own detail: it names the field a mismatched
        // host actually wants, which a generic message would throw away.
        const detail = (err as { response?: { data?: { detail?: string } } })
          ?.response?.data?.detail;
        setError(
          detail ||
            t(
              "configManagement.applyError",
              "Failed to queue the configuration profile",
            ),
        );
      }
    } finally {
      setSubmitting(false);
    }
  };

  // Three mutually exclusive states, named rather than nested inline: a
  // stored profile, a DSC host, or everything else. Chained ternaries in JSX
  // read as one condition until you count the colons.
  let helpText: string;
  if (profileId) {
    helpText = t(
      "configManagement.applyStoredChosen",
      "This runs the saved profile as stored. The run is recorded against it.",
    );
  } else if (isDsc) {
    helpText = t(
      "configManagement.applyHelpDsc",
      "This host applies configuration with DSC. Paste a JSON array of DSC resources.",
    );
  } else {
    helpText = t(
      "configManagement.applyHelpAnsible",
      "This host applies configuration with ansible-core. Paste a playbook; it runs locally against this host only.",
    );
  }

  return (
    <Dialog open={open} onClose={handleClose} maxWidth="md" fullWidth>
      <DialogTitle>
        {t("configManagement.applyTitle", "Apply a configuration profile")}
      </DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ mt: 1 }}>
          <Typography variant="body2" color="text.secondary">
            {helpText}
          </Typography>

          {stored.length > 0 && (
            <TextField
              select
              label={t(
                "configManagement.applyStoredProfile",
                "Stored profile",
              )}
              value={profileId}
              onChange={(event) => setProfileId(event.target.value)}
              size="small"
              fullWidth
              disabled={submitting}
              helperText={t(
                "configManagement.applyStoredHelp",
                "Pick a saved profile, or leave this blank to paste one below.",
              )}
              slotProps={{ select: { native: true } }}
            >
              <option value="">
                {t("configManagement.applyNoStored", "None — paste below")}
              </option>
              {stored.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name} ({p.engine})
                </option>
              ))}
            </TextField>
          )}

          {!profileId && engines.length > 1 && (
            <TextField
              select
              label={t("configManagement.applyEngine", "Engine")}
              value={engine}
              onChange={(event) => setEngine(event.target.value)}
              size="small"
              fullWidth
              disabled={submitting}
              slotProps={{ select: { native: true } }}
            >
              {engines.map((name) => (
                <option key={name} value={name}>
                  {name}
                </option>
              ))}
            </TextField>
          )}

          {!profileId && (
          <TextField
            label={t(
              "configManagement.applyProfileName",
              "Profile name (optional)",
            )}
            value={profileName}
            onChange={(event) => setProfileName(event.target.value)}
            size="small"
            fullWidth
            disabled={submitting}
          />
          )}

          {!profileId && (
            <TextField
              label={
                isDsc
                  ? t("configManagement.applyResources", "DSC resources (JSON)")
                  : t(
                      "configManagement.applyPlaybook",
                      "Playbook content (YAML)",
                    )
              }
              value={body}
              onChange={(event) => setBody(event.target.value)}
              multiline
              minRows={10}
              fullWidth
              disabled={submitting}
              slotProps={{
                input: { sx: { fontFamily: "monospace", fontSize: "0.85rem" } },
              }}
            />
          )}

          <FormControlLabel
            control={
              <Switch
                checked={checkMode}
                onChange={(event) => setCheckMode(event.target.checked)}
                disabled={submitting}
              />
            }
            label={t(
              "configManagement.applyDryRun",
              "Dry run (report changes without making them)",
            )}
          />

          {!checkMode && (
            <Alert severity="warning">
              {t(
                "configManagement.applyLiveWarning",
                "This will make real changes to this host.",
              )}
            </Alert>
          )}

          {error && <Alert severity="error">{error}</Alert>}
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={handleClose} disabled={submitting}>
          {t("common.cancel", "Cancel")}
        </Button>
        <Button
          variant="contained"
          onClick={handleApply}
          // A stored profile has no pasted body -- the server reads it -- so
          // requiring one here would leave the button permanently disabled.
          disabled={submitting || (!profileId && !body.trim())}
        >
          {checkMode
            ? t("configManagement.applyDryRunAction", "Preview changes")
            : t("configManagement.applyAction", "Apply")}
        </Button>
      </DialogActions>
    </Dialog>
  );
};

export default ApplyConfigProfileDialog;
