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
  /** Notify the parent whenever the "tools all present" boolean flips,
   *  so it can ghost out the downstream cards (PlatformConfigCard,
   *  MirrorListCard) until setup passes green.  ``undefined`` while
   *  the status is still loading or unknown — the parent should treat
   *  that as "not yet ready" and keep the gate engaged. */
  onReadyChange?: (ready: boolean | undefined) => void;
}

const POLL_MS = 2000;
// Max time we'll wait for a probe / install to come back before we
// surface "agent didn't respond" to the user and stop the spinner.
// Sized for: a slow first ``apt-get update`` + ``apt-get install``
// chain on a fresh VM with empty caches (~60-90s typical) + safety
// margin.  Past this, something is wrong (agent dedup swallowed the
// result, agent crashed, WebSocket died mid-flight, etc.) and the
// operator needs a definitive failure state instead of an
// indefinite "Checking..." spinner.
const IN_FLIGHT_TIMEOUT_MS = 5 * 60 * 1000;

// Derives the in-flight / timeout state for the probe + install
// operations.  Pulled out of the component body to keep its cognitive
// complexity in check — pure function of the current status + clock.
const computeFlightState = (
  status: MirrorSetupStatus | null,
  now: number,
) => {
  const elapsedSinceCheckMs =
    status?.last_check_at && status.last_check_message_id
      ? now - new Date(status.last_check_at).getTime()
      : 0;
  const elapsedSinceInstallMs =
    status?.last_install_at && status.last_install_message_id
      ? now - new Date(status.last_install_at).getTime()
      : 0;
  const probeTimedOut = elapsedSinceCheckMs > IN_FLIGHT_TIMEOUT_MS;
  const installTimedOut = elapsedSinceInstallMs > IN_FLIGHT_TIMEOUT_MS;
  // Treat a timed-out operation as no longer in-flight — stops the
  // spinner + re-enables the buttons so the operator can retry.
  const probeInFlight = !!status?.last_check_message_id && !probeTimedOut;
  const installInFlight = !!status?.last_install_message_id && !installTimedOut;
  const neverProbed = status && !status.last_check_at;
  return {
    probeTimedOut,
    installTimedOut,
    probeInFlight,
    installInFlight,
    neverProbed,
  };
};

const MirrorSetupStatusCard: React.FC<Props> = ({
  hostId,
  hostFqdn,
  packageManager,
  onReadyChange,
}) => {
  const { t } = useTranslation();
  const [status, setStatus] = useState<MirrorSetupStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  // ``now`` ticks once per poll so the elapsed-time check below
  // re-evaluates each cycle.  Refs would be marginally cheaper but
  // we need a re-render anyway to flip the "timed out" UI state.
  const [now, setNow] = useState<number>(() => Date.now());

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
    const handle = setInterval(() => {
      fetchStatus();
      setNow(Date.now());
    }, POLL_MS);
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

  // Surface the ready boolean upward so the parent section can ghost
  // out the downstream cards (config + mirror list + actions) until
  // setup_check passes green.  ``undefined`` while loading — the
  // parent treats that as "keep the gate engaged" so the operator
  // can't queue a sync against a host with missing tooling.
  useEffect(() => {
    if (onReadyChange) {
      onReadyChange(ready === undefined ? undefined : Boolean(ready));
    }
  }, [ready, onReadyChange]);

  // Compute "in flight" but also a timeout — if the agent silently
  // swallowed our command (e.g. duplicate-skip without emitting a
  // result), the server-side ``last_*_message_id`` never clears and
  // we'd spin forever without this gate.
  const {
    probeTimedOut,
    installTimedOut,
    probeInFlight,
    installInFlight,
    neverProbed,
  } = computeFlightState(status, now);

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

        {(probeTimedOut || installTimedOut) && (
          <Alert severity="warning" sx={{ mt: 2 }}>
            {t(
              'mirror.setupStatus.timedOut',
              'Agent did not respond within {{minutes}} minutes. The most likely causes are: the agent crashed mid-plan, the WebSocket dropped before the command_result was sent, or the agent silently de-duplicated the command without emitting a result. Check the agent log on this host and consider restarting the sysmanage-agent service. Click Refresh / Install Tools again to retry — the in-flight marker will be cleared and a fresh attempt dispatched.',
              { minutes: Math.round(IN_FLIGHT_TIMEOUT_MS / 60000) },
            )}
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
