// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

import React, { useEffect, useState } from 'react';
import {
  Alert,
  Autocomplete,
  Button,
  Card,
  CardContent,
  Stack,
  TextField,
  Typography,
} from '@mui/material';
import { useTranslation } from 'react-i18next';
import {
  deletePlatformConfig,
  MirrorPlatformConfig,
  updatePlatformConfig,
} from '../../Services/repositoryMirroring';
import { HostSummary, hostMatchesPm } from './helpers';

// ---------------------------------------------------------------------
// Platform config card (host + filesystem defaults for this platform)
// ---------------------------------------------------------------------

interface PlatformConfigCardProps {
  config: MirrorPlatformConfig;
  hosts: HostSummary[];
  onSaved: () => void;
  onRemoved: () => void;
  mirrorCount: number;
}

const PlatformConfigCard: React.FC<PlatformConfigCardProps> = ({
  config,
  hosts,
  onSaved,
  onRemoved,
  mirrorCount,
}) => {
  const { t } = useTranslation();
  const [draft, setDraft] = useState({ ...config });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => setDraft({ ...config }), [config]);

  const save = async () => {
    setBusy(true);
    setError(null);
    try {
      await updatePlatformConfig(config.id, {
        platform: draft.platform,
        host_id: draft.host_id,
        mirror_root_path: draft.mirror_root_path,
        integrity_check_cadence_hours: draft.integrity_check_cadence_hours,
        retention_window_days: draft.retention_window_days,
        default_bandwidth_cap_kbps: draft.default_bandwidth_cap_kbps,
        snapshot_count_to_keep: draft.snapshot_count_to_keep,
      });
      onSaved();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const removeConfig = async () => {
    if (mirrorCount > 0) {
      setError(
        t(
          'mirror.deleteConfigInUse',
          'Delete the {{n}} mirror(s) under this platform first.',
          { n: mirrorCount },
        ),
      );
      return;
    }
    if (
      !globalThis.confirm(
        t('mirror.deleteConfigConfirm', 'Remove this platform configuration?'),
      )
    )
      return;
    try {
      await deletePlatformConfig(config.id);
      onRemoved();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  const eligibleHosts = hosts.filter((h) => hostMatchesPm(h, config.platform));

  return (
    <Card variant="outlined">
      <CardContent>
        <Typography variant="h6" sx={{ mb: 1 }}>
          {t('mirror.platformSettings.title', 'Platform Settings')}
        </Typography>
        {error && (
          <Alert severity="error" sx={{ mb: 2 }}>
            {error}
          </Alert>
        )}
        <Stack spacing={2}>
          <Autocomplete
            options={eligibleHosts}
            getOptionLabel={(o) => o.fqdn}
            value={eligibleHosts.find((h) => h.id === draft.host_id) ?? null}
            onChange={(_, v) => setDraft({ ...draft, host_id: v?.id ?? '' })}
            renderInput={(params) => (
              <TextField {...params} label={t('mirror.field.host', 'Mirror host')} />
            )}
          />
          <TextField
            label={t('mirror.field.mirrorRootPath', 'Mirror root path')}
            value={draft.mirror_root_path}
            onChange={(e) => setDraft({ ...draft, mirror_root_path: e.target.value })}
            fullWidth
          />
          <Stack direction="row" spacing={2}>
            <TextField
              type="number"
              label={t('mirror.field.retention', 'Retention (days)')}
              value={draft.retention_window_days}
              onChange={(e) =>
                setDraft({
                  ...draft,
                  retention_window_days: Number(e.target.value || 0),
                })
              }
              sx={{ flex: 1 }}
            />
            <TextField
              type="number"
              label={t('mirror.field.integrityCadence', 'Integrity check (hrs)')}
              value={draft.integrity_check_cadence_hours}
              onChange={(e) =>
                setDraft({
                  ...draft,
                  integrity_check_cadence_hours: Number(e.target.value || 0),
                })
              }
              sx={{ flex: 1 }}
            />
            <TextField
              type="number"
              label={t('mirror.field.bandwidthCap', 'Default cap (kbps, 0=off)')}
              value={draft.default_bandwidth_cap_kbps}
              onChange={(e) =>
                setDraft({
                  ...draft,
                  default_bandwidth_cap_kbps: Number(e.target.value || 0),
                })
              }
              sx={{ flex: 1 }}
            />
            <TextField
              type="number"
              label={t('mirror.field.snapshotKeep', 'Snapshots to keep')}
              value={draft.snapshot_count_to_keep}
              onChange={(e) =>
                setDraft({
                  ...draft,
                  snapshot_count_to_keep: Number(e.target.value || 0),
                })
              }
              sx={{ flex: 1 }}
            />
          </Stack>
          <Stack direction="row" spacing={1} justifyContent="flex-end">
            <Button color="error" onClick={removeConfig} disabled={busy}>
              {t('mirror.deletePlatform', 'Remove platform')}
            </Button>
            <Button variant="contained" onClick={save} disabled={busy}>
              {busy
                ? t('mirror.saving', 'Saving…')
                : t('mirror.save', 'Save')}
            </Button>
          </Stack>
        </Stack>
      </CardContent>
    </Card>
  );
};

export default PlatformConfigCard;
