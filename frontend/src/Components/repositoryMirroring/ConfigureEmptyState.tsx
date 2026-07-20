// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

import React, { useMemo, useState } from 'react';
import {
  Alert,
  Autocomplete,
  Box,
  Button,
  Card,
  CardContent,
  Stack,
  TextField,
  Typography,
} from '@mui/material';
import { useTranslation } from 'react-i18next';
import {
  createPlatformConfig,
  MirrorPlatform,
} from '../../Services/repositoryMirroring';
import MirrorSetupStatusCard from '../MirrorSetupStatusCard';
import { HostSummary, hostMatchesPm, PLATFORM_FAMILY_LABEL } from './helpers';

// ---------------------------------------------------------------------
// Empty state — no platform config yet
// ---------------------------------------------------------------------

interface ConfigureEmptyStateProps {
  platform: MirrorPlatform;
  hosts: HostSummary[];
  onCreated: () => void;
}

const ConfigureEmptyState: React.FC<ConfigureEmptyStateProps> = ({
  platform,
  hosts,
  onCreated,
}) => {
  const { t } = useTranslation();
  const [hostId, setHostId] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // Track the chosen host's mirror-toolchain readiness so the Create
  // button is gated the same way the per-platform action buttons are.
  // ``undefined`` while the setup probe is still loading on the
  // newly-selected host — treated as "not ready" so the operator can't
  // commit to a host before its toolchain is confirmed green.
  const [setupReady, setSetupReady] = useState<boolean | undefined>(undefined);

  const eligible = useMemo(
    () => hosts.filter((h) => hostMatchesPm(h, platform)),
    [hosts, platform],
  );
  const selectedHost = hostId ? eligible.find((h) => h.id === hostId) ?? null : null;

  const submit = async () => {
    if (!hostId) return;
    setBusy(true);
    setError(null);
    try {
      await createPlatformConfig({ platform, host_id: hostId });
      onCreated();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card variant="outlined">
      <CardContent>
        <Typography variant="h6">
          {t('mirror.configureTitle', 'Configure {{platform}} mirroring', {
            platform: PLATFORM_FAMILY_LABEL[platform],
          })}
        </Typography>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
          {t(
            'mirror.configureSubtitle',
            'Pick the host that will run this platform\'s mirror plans. Only hosts whose platform matches the tab are listed.',
          )}
        </Typography>
        {error && (
          <Alert severity="error" sx={{ mb: 2 }}>
            {error}
          </Alert>
        )}
        <Stack direction="row" spacing={2} alignItems="center">
          <Autocomplete
            sx={{ minWidth: 360 }}
            options={eligible}
            getOptionLabel={(o) => o.fqdn}
            value={selectedHost}
            onChange={(_, v) => {
              setHostId(v?.id ?? null);
              // Reset readiness when the operator swaps hosts — the
              // new host's setup card will re-emit its own state.
              setSetupReady(undefined);
            }}
            renderInput={(params) => (
              <TextField {...params} label={t('mirror.field.host', 'Mirror host')} />
            )}
          />
          <Button
            variant="contained"
            onClick={submit}
            disabled={!hostId || busy || setupReady !== true}
          >
            {busy
              ? t('mirror.saving', 'Saving…')
              : t('mirror.create', 'Create')}
          </Button>
        </Stack>
        {hostId && selectedHost && (
          <Box sx={{ mt: 2 }}>
            <MirrorSetupStatusCard
              key={hostId}
              hostId={hostId}
              hostFqdn={selectedHost.fqdn}
              packageManager={platform}
              onReadyChange={setSetupReady}
            />
            {setupReady !== true && (
              <Alert severity="info" variant="outlined" sx={{ mt: 2 }}>
                {t(
                  'mirror.setupGate.preConfigure',
                  'Install the required mirror tooling on this host before configuring the platform. The Create button stays disabled until the setup probe reports all tools present.',
                )}
              </Alert>
            )}
          </Box>
        )}
        {eligible.length === 0 && (
          <Typography variant="caption" color="text.secondary" sx={{ mt: 1, display: 'block' }}>
            {t(
              'mirror.noEligibleHosts',
              'No registered {{family}} hosts available — register one and refresh.',
              {
                family: PLATFORM_FAMILY_LABEL[platform],
              },
            )}
          </Typography>
        )}
      </CardContent>
    </Card>
  );
};

export default ConfigureEmptyState;
