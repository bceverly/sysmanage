/**
 * Mirror Setup Status Card (Phase 10.4.1).
 *
 * Sits above the mirror-repository table on the Repository Mirroring
 * settings tab.  For each host that has a mirror configured (or an
 * arbitrary host the operator picks via the host dropdown), shows
 * which mirror-tooling binaries are present + an Install button
 * that queues a sudo-install plan via the agent.
 *
 * All agent communication goes through the existing message queue:
 *   - Refresh button POSTs /setup-status/{host_id}/refresh which
 *     dispatches a probe plan asynchronously.  The component then
 *     polls the GET endpoint while ``last_check_message_id`` is
 *     non-NULL.
 *   - Install button POSTs /setup-install/{host_id}.  Same polling
 *     loop watches ``last_install_message_id``.  Server auto-chains
 *     a follow-up probe on success so tool presence refreshes
 *     without a manual click.
 */

import React, { useCallback, useEffect, useState } from 'react';
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  CircularProgress,
  Stack,
  Typography,
} from '@mui/material';
import { useTranslation } from 'react-i18next';
import {
  MirrorSetupStatus,
  getMirrorSetupStatus,
  refreshMirrorSetupStatus,
  installMirrorTools,
} from '../Services/repositoryMirroring';

interface Props {
  hostId: string;
  hostFqdn?: string;
  /** apt | dnf | zypper | pkg — which install plan to fire when the
   *  user clicks Install.  Driven by the package_manager field on the
   *  mirror_repository row this host owns. */
  packageManager: 'apt' | 'dnf' | 'zypper' | 'pkg';
}

const POLL_MS = 2000;

const MirrorSetupStatusCard: React.FC<Props> = ({ hostId, hostFqdn, packageManager }) => {
  const { t } = useTranslation();
  const [status, setStatus] = useState<MirrorSetupStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const fetchStatus = useCallback(async () => {
    try {
      const s = await getMirrorSetupStatus(hostId);
      setStatus(s);
      setError(null);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }, [hostId]);

  useEffect(() => {
    fetchStatus();
  }, [fetchStatus]);

  // Poll while a probe or install is in flight.
  useEffect(() => {
    if (!status) return;
    const inFlight =
      status.last_check_message_id || status.last_install_message_id;
    if (!inFlight) return;
    const handle = setInterval(fetchStatus, POLL_MS);
    return () => clearInterval(handle);
  }, [status, fetchStatus]);

  const handleRefresh = async () => {
    setBusy(true);
    try {
      await refreshMirrorSetupStatus(hostId);
      await fetchStatus();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const handleInstall = async () => {
    setBusy(true);
    try {
      await installMirrorTools(hostId, packageManager);
      await fetchStatus();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  // Tools we render in the status grid — only those relevant to this
  // host's package manager.  The probe enumerates EVERY tool regardless
  // of PM (so the engine can give a complete picture for an audit log),
  // but the card only shows what's actually required + the shared
  // helpers, so an APT host doesn't display ``reposync`` /
  // ``createrepo_c`` as "missing" when those are DNF-side tools the
  // operator will never need.
  const toolsByPm: Record<typeof packageManager, Array<{ key: string; label: string }>> = {
    apt: [
      { key: 'apt-mirror', label: 'apt-mirror' },
      { key: 'trickle', label: 'trickle' },
      { key: 'rsync', label: 'rsync' },
      { key: 'curl', label: 'curl' },
    ],
    dnf: [
      { key: 'reposync', label: 'reposync' },
      { key: 'createrepo_c', label: 'createrepo_c' },
      { key: 'trickle', label: 'trickle' },
      { key: 'rsync', label: 'rsync' },
      { key: 'curl', label: 'curl' },
    ],
    zypper: [
      { key: 'createrepo_c', label: 'createrepo_c' },
      { key: 'trickle', label: 'trickle' },
      { key: 'rsync', label: 'rsync' },
      { key: 'curl', label: 'curl' },
    ],
    pkg: [
      { key: 'rsync', label: 'rsync' },
      { key: 'curl', label: 'curl' },
    ],
  };
  const toolsToShow = toolsByPm[packageManager];

  const ready = status && {
    apt: status.ready_apt,
    dnf: status.ready_dnf,
    zypper: status.ready_zypper,
    pkg: status.ready_pkg,
  }[packageManager];

  const probeInFlight = !!status?.last_check_message_id;
  const installInFlight = !!status?.last_install_message_id;
  const neverProbed = status && !status.last_check_at;

  return (
    <Card sx={{ mb: 2 }}>
      <CardContent>
        <Stack
          direction={{ xs: 'column', md: 'row' }}
          justifyContent="space-between"
          alignItems={{ xs: 'flex-start', md: 'center' }}
          spacing={1}
        >
          <Box>
            <Typography variant="h6">
              {t('mirror.setupStatus.title', 'Mirror Setup Status')}
              {hostFqdn ? `: ${hostFqdn}` : ''}
            </Typography>
            <Typography variant="body2" color="text.secondary">
              {t(
                'mirror.setupStatus.subtitle',
                'Tooling required to run {{pm}} mirror plans on this host',
                { pm: packageManager },
              )}
            </Typography>
          </Box>
          <Stack direction="row" spacing={1}>
            <Button
              variant="outlined"
              size="small"
              onClick={handleRefresh}
              disabled={busy || probeInFlight}
              startIcon={
                probeInFlight ? <CircularProgress size={16} /> : undefined
              }
            >
              {probeInFlight
                ? t('mirror.setupStatus.checking', 'Checking…')
                : t('mirror.setupStatus.refresh', 'Refresh')}
            </Button>
            {(neverProbed || ready === false) && (
              <Button
                variant="contained"
                size="small"
                color="primary"
                onClick={handleInstall}
                disabled={busy || installInFlight}
                startIcon={
                  installInFlight ? <CircularProgress size={16} /> : undefined
                }
              >
                {installInFlight
                  ? t('mirror.setupStatus.installing', 'Installing…')
                  : t('mirror.setupStatus.install', 'Install Tools')}
              </Button>
            )}
          </Stack>
        </Stack>

        {error && (
          <Alert severity="error" sx={{ mt: 2 }}>
            {error}
          </Alert>
        )}

        {neverProbed && !error && (
          <Alert severity="info" sx={{ mt: 2 }}>
            {t(
              'mirror.setupStatus.notProbedYet',
              'No probe has run yet — click Refresh to check this host.',
            )}
          </Alert>
        )}

        {status?.last_check_error && (
          <Alert severity="warning" sx={{ mt: 2 }}>
            {t('mirror.setupStatus.lastCheckError', 'Last check failed: ')}
            {status.last_check_error}
          </Alert>
        )}

        {status?.last_install_error && (
          <Alert severity="warning" sx={{ mt: 2 }}>
            {t('mirror.setupStatus.lastInstallError', 'Last install failed: ')}
            {status.last_install_error}
          </Alert>
        )}

        {status && !neverProbed && (
          <Box sx={{ mt: 2 }}>
            <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
              {toolsToShow.map(({ key, label }) => {
                const present = status.tools[key] === 'present';
                return (
                  <Chip
                    key={key}
                    label={label}
                    color={present ? 'success' : 'default'}
                    variant={present ? 'filled' : 'outlined'}
                    size="small"
                  />
                );
              })}
            </Stack>
            <Typography variant="caption" color="text.secondary" sx={{ mt: 1, display: 'block' }}>
              {ready
                ? t(
                    'mirror.setupStatus.ready',
                    'Ready to mirror {{pm}} repositories.',
                    { pm: packageManager },
                  )
                : t(
                    'mirror.setupStatus.notReady',
                    'Missing required tooling for {{pm}} — install before triggering a sync.',
                    { pm: packageManager },
                  )}
              {status.platform && status.distro && (
                <>
                  {' '}
                  ({status.platform} / {status.distro})
                </>
              )}
            </Typography>
          </Box>
        )}
      </CardContent>
    </Card>
  );
};

export default MirrorSetupStatusCard;
