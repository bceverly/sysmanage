// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

/**
 * Settings panel for the Pro+ Repository Mirroring feature.
 *
 * Phase 10.4.2 layout — tab strip per platform:
 *
 *     [ Linux ] [ FreeBSD ]
 *     ────────────────────────────────────────────────────
 *     <PlatformPanel> for the active tab:
 *       1. Platform-config card (host picker + filesystem
 *          + retention + bandwidth defaults)
 *       2. Mirror-tooling setup status card (Phase 10.4.1)
 *       3. Repository table for mirrors that hang off this
 *          platform's config + Add Mirror button
 *
 * If the active platform has no config yet, the panel shows an
 * empty-state "Configure {Platform} mirroring" form instead.
 *
 * The component is rendered from a Settings tab that's already
 * gated on ``isModuleLicensed('repository_mirroring_engine')`` —
 * we don't re-check inside.  All API calls 402 if the engine is
 * unlicensed; we surface those as inline error alerts.
 */

import React, { useEffect, useState } from 'react';
import {
  Alert,
  Box,
  CircularProgress,
  Tab,
  Tabs,
} from '@mui/material';
import { useTranslation } from 'react-i18next';
import axiosInstance from '../Services/api';

import {
  listMirrors,
  listPlatformConfigs,
  MirrorPlatform,
  MirrorPlatformConfig,
  MirrorRepository,
} from '../Services/repositoryMirroring';
import { HostSummary } from './repositoryMirroring/helpers';
import PlatformPanel from './repositoryMirroring/PlatformPanel';

const RepositoryMirroringSettings: React.FC = () => {
  const { t } = useTranslation();
  const [activePlatform, setActivePlatform] = useState<MirrorPlatform>('apt');
  const [configs, setConfigs] = useState<MirrorPlatformConfig[]>([]);
  const [mirrors, setMirrors] = useState<MirrorRepository[]>([]);
  const [hosts, setHosts] = useState<HostSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = async () => {
    setLoading(true);
    setError(null);
    try {
      const [c, m, h] = await Promise.all([
        listPlatformConfigs(),
        listMirrors(),
        axiosInstance.get<HostSummary[]>('/api/v1/hosts').then((r) => r.data),
      ]);
      setConfigs(c);
      setMirrors(m);
      setHosts(h);
    } catch {
      setError(t('mirror.loadError', 'Could not load repository mirrors.'));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    refresh();
    // refresh is stable for the component lifetime; mount-only fetch
    // is intentional.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Auto-poll while ANY action on ANY mirror is in-flight.  We key off
  // the per-action ``last_*_message_id`` columns (stamped at dispatch,
  // cleared on result) rather than ``status == DISPATCHED``; the
  // message_id is the load-bearing "still running" signal because a
  // result handler always clears it, including on failure.  Once every
  // row's marker is NULL the interval clears so we don't pin the
  // backend.  Re-arms automatically when the next op fires.
  useEffect(() => {
    const inflight = mirrors.some(
      (m) =>
        m.last_sync_message_id ||
        m.last_snapshot_message_id ||
        m.last_restore_message_id ||
        m.last_integrity_message_id ||
        m.last_gc_message_id,
    );
    if (!inflight) return;
    const handle = setInterval(() => {
      // Only refetch the mirror list (lightweight) rather than the
      // full configs+hosts+mirrors triple-load so the polling cost is
      // a single GET every 10s.
      listMirrors().then(setMirrors).catch(() => { /* keep last-known on error */ });
    }, 10000);
    return () => clearInterval(handle);
  }, [mirrors]);

  if (loading) {
    return (
      <Box sx={{ display: 'flex', justifyContent: 'center', p: 4 }}>
        <CircularProgress />
      </Box>
    );
  }

  return (
    <Box sx={{ p: 3 }}>
      {error && (
        <Alert severity="error" sx={{ mb: 2 }}>
          {error}
        </Alert>
      )}
      <Tabs
        value={activePlatform}
        onChange={(_, v) => setActivePlatform(v)}
        sx={{ borderBottom: 1, borderColor: 'divider', mb: 2 }}
      >
        <Tab value="apt" label={t('mirror.platform.apt', 'Ubuntu/Debian')} />
        <Tab value="dnf" label={t('mirror.platform.dnf', 'RHEL/Fedora')} />
        <Tab value="zypper" label={t('mirror.platform.zypper', 'openSUSE/SLES')} />
        <Tab value="pkg" label={t('mirror.platform.pkg', 'FreeBSD')} />
      </Tabs>
      <PlatformPanel
        platform={activePlatform}
        config={configs.find((c) => c.platform === activePlatform) ?? null}
        hosts={hosts}
        mirrors={mirrors}
        onChange={refresh}
      />
    </Box>
  );
};

export default RepositoryMirroringSettings;
