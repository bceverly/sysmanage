// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

/**
 * Backup status card for the SiteDetail page (Phase 27.1): the latest
 * status snapshot the site pushed up.  The site keeps its own backup
 * target and every byte of its backups; this shows only counts, sizes,
 * times and the few hosts that need a look at the site.
 */

import React from "react";
import { useTranslation } from "react-i18next";
import type { TFunction } from "i18next";

import Box from "@mui/material/Box";
import Card from "@mui/material/Card";
import CardContent from "@mui/material/CardContent";
import Chip from "@mui/material/Chip";
import Grid from "@mui/material/Grid";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";

import type { BackupStatus } from "../Services/backups";
import type { FederationBackupRollup } from "../Services/federationBackup";
import {
  formatBytes,
  formatTime,
  statusColor,
  statusLabel,
} from "./Backups/backupLabels";

const VERIFICATION_ORDER = ["verified", "unverified", "failed", "running", "off"];

function verificationLabel(
  t: TFunction,
  state: string,
  n: number,
): string {
  switch (state) {
    case "verified":
      return t("sites.detail.backupVerified", "Verified: {{n}}", { n });
    case "unverified":
      return t("sites.detail.backupUnverified", "Not verified: {{n}}", { n });
    case "failed":
      return t("sites.detail.backupVerifyFailed", "Verification failed: {{n}}", {
        n,
      });
    case "running":
      return t("sites.detail.backupVerifying", "Verifying now: {{n}}", { n });
    default:
      return t("sites.detail.backupVerifyOff", "Verification off: {{n}}", { n });
  }
}

function BackupSummary({ backup }: Readonly<{ backup: FederationBackupRollup }>) {
  const { t } = useTranslation();
  const verification = VERIFICATION_ORDER.filter(
    (state) => (backup.verification_counts[state] ?? 0) > 0,
  );
  return (
    <Stack spacing={2}>
      <Stack direction="row" spacing={1} sx={{ flexWrap: "wrap" }}>
        <Chip
          size="small"
          variant="outlined"
          label={t("sites.detail.backupCovered", "Hosts covered: {{n}}", {
            n: backup.hosts_with_policy,
          })}
        />
        <Chip
          size="small"
          color={backup.attention_count > 0 ? "error" : "success"}
          label={t("sites.detail.backupAttention", "Need attention: {{n}}", {
            n: backup.attention_count,
          })}
        />
        {backup.never_backed_up > 0 && (
          <Chip
            size="small"
            color="warning"
            label={t("sites.detail.backupNever", "Never backed up: {{n}}", {
              n: backup.never_backed_up,
            })}
          />
        )}
        {backup.target_problem && (
          <Chip
            size="small"
            color="error"
            label={t(
              "sites.detail.backupStorageProblem",
              "The site's backup storage needs attention",
            )}
          />
        )}
      </Stack>
      <Box>
        <Typography variant="body2">
          {t("sites.detail.backupOldest", "Oldest last good backup: {{when}}", {
            when: backup.oldest_last_good_at
              ? formatTime(backup.oldest_last_good_at)
              : t("sites.detail.backupNone", "none yet"),
          })}
        </Typography>
        <Typography variant="body2">
          {t("sites.detail.backupSize", "Stored at the site: {{size}}", {
            size: formatBytes(backup.repository_bytes),
          })}
        </Typography>
      </Box>
      <Stack direction="row" spacing={1} sx={{ flexWrap: "wrap" }}>
        {Object.entries(backup.status_counts).map(([status, n]) => (
          <Chip
            key={status}
            size="small"
            variant="outlined"
            color={statusColor(status as BackupStatus)}
            label={`${statusLabel(t, status as BackupStatus)}: ${n}`}
          />
        ))}
        {verification.map((state) => (
          <Chip
            key={`verify-${state}`}
            size="small"
            variant="outlined"
            color={state === "failed" ? "error" : "default"}
            label={verificationLabel(t, state, backup.verification_counts[state])}
          />
        ))}
      </Stack>
      {backup.attention_hosts.length > 0 && (
        <Box>
          <Typography variant="caption" color="text.secondary">
            {t(
              "sites.detail.backupAttentionHosts",
              "Hosts to look at on the site",
            )}
          </Typography>
          {backup.attention_hosts.map((host) => (
            <Typography key={host.host_id} variant="body2">
              {host.fqdn}: {statusLabel(t, host.status as BackupStatus)} (
              {host.last_good_at
                ? t("sites.detail.backupLastGood", "last good {{when}}", {
                    when: formatTime(host.last_good_at),
                  })
                : t("sites.detail.backupNeverShort", "never backed up")}
              )
            </Typography>
          ))}
        </Box>
      )}
    </Stack>
  );
}

/** The site's backup status, or why there is none. */
export function SiteBackupCard({
  backup,
}: Readonly<{ backup: FederationBackupRollup | null | undefined }>) {
  const { t } = useTranslation();
  let body: React.ReactNode;
  if (!backup) {
    body = (
      <Typography variant="body2" color="text.secondary">
        {t(
          "sites.detail.backupEmpty",
          "No backup status synced from this site yet.",
        )}
      </Typography>
    );
  } else if (!backup.configured) {
    body = (
      <Typography variant="body2" color="text.secondary">
        {t(
          "sites.detail.backupNotSetUp",
          "Backups are not set up on this site's server.",
        )}
      </Typography>
    );
  } else {
    body = <BackupSummary backup={backup} />;
  }
  return (
    <Grid size={{ xs: 12 }}>
      <Card variant="outlined">
        <CardContent>
          <Typography variant="h6" gutterBottom>
            {t("sites.detail.backupTitle", "Backups")}
          </Typography>
          {body}
          <Typography
            variant="caption"
            color="text.secondary"
            sx={{ display: "block", mt: 2 }}
          >
            {t(
              "sites.detail.backupStaysAtSite",
              "Each site keeps its own backup storage; only this status comes here.",
            )}
          </Typography>
        </CardContent>
      </Card>
    </Grid>
  );
}
