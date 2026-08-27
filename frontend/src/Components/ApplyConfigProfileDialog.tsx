// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

import React, { useState } from "react";
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
import { applyConfigProfile } from "../Services/configManagementService";

interface ApplyConfigProfileDialogProps {
  open: boolean;
  hostId: string;
  /** "ansible-core" or "dsc" -- decides which field the server expects. */
  executor: string;
  onClose: () => void;
  /** Called after the profile is queued, so the run history can refresh. */
  onApplied?: () => void;
}

const ApplyConfigProfileDialog: React.FC<ApplyConfigProfileDialogProps> = ({
  open,
  hostId,
  executor,
  onClose,
  onApplied,
}) => {
  const { t } = useTranslation();
  const isDsc = executor === "dsc";
  const [body, setBody] = useState("");
  const [profileName, setProfileName] = useState("");
  // Defaults to a DRY RUN on purpose. This dialog runs arbitrary code as root
  // on a managed host; the safe option should be the one you get by not
  // thinking about it, and the destructive one should take a deliberate act.
  const [checkMode, setCheckMode] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const reset = () => {
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
      if (isDsc) {
        // Parse locally so a typo is caught here, with a message about JSON,
        // rather than becoming an opaque 422 from the request body.
        const parsed = JSON.parse(body) as unknown;
        if (!Array.isArray(parsed)) {
          throw new SyntaxError("not an array");
        }
        resources = parsed as Record<string, unknown>[];
      }
      await applyConfigProfile(hostId, {
        ...(isDsc ? { resources } : { playbook: body }),
        ...(profileName.trim() ? { profile_name: profileName.trim() } : {}),
        check_mode: checkMode,
      });
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

  return (
    <Dialog open={open} onClose={handleClose} maxWidth="md" fullWidth>
      <DialogTitle>
        {t("configManagement.applyTitle", "Apply a configuration profile")}
      </DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ mt: 1 }}>
          <Typography variant="body2" color="text.secondary">
            {isDsc
              ? t(
                  "configManagement.applyHelpDsc",
                  "This host applies configuration with DSC. Paste a JSON array of DSC resources.",
                )
              : t(
                  "configManagement.applyHelpAnsible",
                  "This host applies configuration with ansible-core. Paste a playbook; it runs locally against this host only.",
                )}
          </Typography>

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

          <TextField
            label={
              isDsc
                ? t("configManagement.applyResources", "DSC resources (JSON)")
                : t("configManagement.applyPlaybook", "Playbook content (YAML)")
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
          disabled={submitting || !body.trim()}
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
