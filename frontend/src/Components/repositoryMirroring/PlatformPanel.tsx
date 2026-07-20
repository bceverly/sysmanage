// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

import React, { useState } from 'react';
import { Alert, Box, Stack } from '@mui/material';
import { useTranslation } from 'react-i18next';
import {
  MirrorPlatform,
  MirrorPlatformConfig,
  MirrorRepository,
} from '../../Services/repositoryMirroring';
import MirrorSetupStatusCard from '../MirrorSetupStatusCard';
import { HostSummary } from './helpers';
import ConfigureEmptyState from './ConfigureEmptyState';
import PlatformConfigCard from './PlatformConfigCard';
import MirrorListCard from './MirrorListCard';

// ---------------------------------------------------------------------
// Per-platform panel
// ---------------------------------------------------------------------

interface PlatformPanelProps {
  platform: MirrorPlatform;
  config: MirrorPlatformConfig | null;
  hosts: HostSummary[];
  mirrors: MirrorRepository[];
  onChange: () => void;
}

const PlatformPanel: React.FC<PlatformPanelProps> = ({
  platform,
  config,
  hosts,
  mirrors,
  onChange,
}) => {
  const { t } = useTranslation();
  // ``undefined`` while the setup card is still loading — we treat
  // that as "not yet ready" so the gate stays engaged on first paint
  // (no flash of fully-enabled UI before the probe result lands).
  const [setupReady, setSetupReady] = useState<boolean | undefined>(undefined);

  if (!config) {
    return <ConfigureEmptyState platform={platform} hosts={hosts} onCreated={onChange} />;
  }

  const platformMirrors = mirrors.filter((m) => m.platform_config_id === config.id);
  const hostName = hosts.find((h) => h.id === config.host_id)?.fqdn ?? config.host_id;
  const gateOpen = setupReady === true;

  return (
    <Stack spacing={2}>
      <MirrorSetupStatusCard
        hostId={config.host_id}
        hostFqdn={hostName}
        packageManager={platform}
        onReadyChange={setSetupReady}
      />
      {/* Gate the mirror-config + mirror-list cards behind the setup
          probe.  When the host is missing required tooling (apt-mirror,
          createrepo_c, etc.) the operator should not be able to create
          mirrors or queue syncs against it — running them against an
          empty toolchain produces an opaque sudo-deny three steps in
          and a stuck FAILED row.  We grey out + intercept pointer
          events on the downstream cards until setup_check returns
          green; the setup card itself stays interactive so the
          operator can hit "Install Tools" or "Refresh". */}
      {!gateOpen && (
        <Alert severity="info" variant="outlined">
          {t(
            'mirror.setupGate.message',
            'Install the required mirror tooling above to enable mirror configuration. Mirror operations stay disabled until the setup probe reports all tools present.',
          )}
        </Alert>
      )}
      <Box
        sx={{
          opacity: gateOpen ? 1 : 0.45,
          pointerEvents: gateOpen ? 'auto' : 'none',
          transition: 'opacity 150ms ease',
        }}
        aria-disabled={!gateOpen}
      >
        <Stack spacing={2}>
          <PlatformConfigCard
            config={config}
            hosts={hosts}
            onSaved={onChange}
            onRemoved={onChange}
            mirrorCount={platformMirrors.length}
          />
          <MirrorListCard
            platform={platform}
            config={config}
            mirrors={platformMirrors}
            onChange={onChange}
          />
        </Stack>
      </Box>
    </Stack>
  );
};

export default PlatformPanel;
