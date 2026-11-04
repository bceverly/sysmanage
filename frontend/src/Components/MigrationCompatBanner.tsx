// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

import React, { useEffect, useRef, useState } from 'react';
import { Alert, AlertTitle, Box } from '@mui/material';
import { useTranslation } from 'react-i18next';
import api from '../Services/api';

interface ModuleCompatibilityEntry {
  module_code: string;
  required_revision: string;
  required_revision_human?: string | null;
  current_revision?: string | null;
  // 'migration_pending' (run the migrations) or 'server_too_old' (the engine
  // needs a migration this server does not ship; only a newer server helps).
  kind?: string;
}

interface PendingEngineUpdate {
  module_code: string;
  version?: string | null;
  required_revision: string;
  kept_version?: string | null;
}

interface ModuleCompatibilityResponse {
  incompatibilities: ModuleCompatibilityEntry[];
  pending_updates?: PendingEngineUpdate[];
}

/**
 * MigrationCompatBanner -- fallback banner shown when one or more Pro+
 * modules failed to load because the OSS database schema is older than
 * the module's declared minimum alembic revision.
 *
 * The normal path is for the operator to run `alembic upgrade head` as
 * part of the upgrade procedure.  This banner is the safety net for the
 * case where a Pro+ module is downloaded after an OSS upgrade but
 * before migrations have been applied.
 *
 * An engine built for a NEWER server names a migration this server does not
 * ship; running migrations cannot help, so those get their own message
 * ("needs a newer SysManage server").  When such an update was refused and
 * the installed version kept, an informational notice says so instead.
 */
const MigrationCompatBanner: React.FC = () => {
  const { t } = useTranslation();
  const [entries, setEntries] = useState<ModuleCompatibilityEntry[]>([]);
  const [pending, setPending] = useState<PendingEngineUpdate[]>([]);
  const migrationEntries = entries.filter((e) => e.kind !== 'server_too_old');
  const tooNewEntries = entries.filter((e) => e.kind === 'server_too_old');
  const visible = entries.length > 0 || pending.length > 0;
  const ref = useRef<HTMLDivElement>(null);

  // Reserve layout space so the fixed banner pushes content down instead of
  // overlaying it (and it sits BELOW the navbar -- see the Box sx -- so it never
  // covers the menu bar).  Mirrors the tenant-migration banner.
  useEffect(() => {
    const root = document.documentElement;
    const clear = () => root.style.setProperty('--migration-banner-height', '0px');
    if (!visible || !ref.current) {
      clear();
      return clear;
    }
    root.style.setProperty('--migration-banner-height', `${ref.current.offsetHeight}px`);
    return clear;
  }, [entries, pending, visible]);

  useEffect(() => {
    let cancelled = false;

    const check = async () => {
      const token = localStorage.getItem('bearer_token');
      if (!token) {
        if (!cancelled) {
          setEntries([]);
          setPending([]);
        }
        return;
      }
      try {
        const response = await api.get<ModuleCompatibilityResponse>(
          '/api/v1/license/module-compat',
        );
        if (!cancelled) {
          setEntries(response.data?.incompatibilities ?? []);
          setPending(response.data?.pending_updates ?? []);
        }
      } catch {
        // Endpoint may not exist on older servers; treat as no incompatibilities.
        if (!cancelled) {
          setEntries([]);
          setPending([]);
        }
      }
    };

    void check();
    const interval = globalThis.setInterval(check, 60000);
    return () => {
      cancelled = true;
      globalThis.clearInterval(interval);
    };
  }, []);

  if (!visible) {
    return null;
  }

  return (
    <Box
      ref={ref}
      sx={{
        // Sit directly BELOW the fixed navbar (top: var(--security-banner-height),
        // height ~7rem) instead of over it, at a z-index below the navbar's (1000).
        position: 'fixed',
        top: 'calc(var(--security-banner-height, 0px) + 7rem)',
        left: 0,
        right: 0,
        zIndex: 999,
        width: '100%',
      }}
    >
      {migrationEntries.length > 0 && (
        <Alert severity="warning" variant="filled" sx={{ borderRadius: 0 }}>
          <AlertTitle>
            {t(
              'migrationCompat.title',
              'Database migration required',
            )}
          </AlertTitle>
          {t(
            'migrationCompat.intro',
            'One or more Pro+ modules cannot load because the database schema is older than they require. Run',
          )}{' '}
          {/* eslint-disable-next-line i18next/no-literal-string -- CLI command is not translatable */}
          <code>alembic upgrade head</code>{' '}
          {t(
            'migrationCompat.outro',
            'on the server, then restart sysmanage.',
          )}
          <Box component="ul" sx={{ mt: 1, mb: 0, pl: 3 }}>
            {migrationEntries.map((e) => (
              <li key={e.module_code}>
                <strong>{e.module_code}</strong>
                {' -- '}
                {t('migrationCompat.requires', 'requires')} {e.required_revision}
                {e.required_revision_human ? ` (${e.required_revision_human})` : ''}
                {e.current_revision
                  ? `; ${t('migrationCompat.currently', 'currently at')} ${e.current_revision}`
                  : `; ${t('migrationCompat.noVersion', 'no alembic_version row found')}`}
              </li>
            ))}
          </Box>
        </Alert>
      )}
      {tooNewEntries.length > 0 && (
        <Alert severity="warning" variant="filled" sx={{ borderRadius: 0 }}>
          <AlertTitle>
            {t(
              'migrationCompat.serverTooOldTitle',
              'Pro+ engine needs a newer SysManage server',
            )}
          </AlertTitle>
          {t(
            'migrationCompat.serverTooOldIntro',
            'These Pro+ engines were built for a newer SysManage server and cannot load. Running database migrations will not help: upgrade the SysManage server package, then restart sysmanage.',
          )}
          <Box component="ul" sx={{ mt: 1, mb: 0, pl: 3 }}>
            {tooNewEntries.map((e) => (
              <li key={e.module_code}>
                <strong>{e.module_code}</strong>
                {' -- '}
                {t('migrationCompat.requires', 'requires')} {e.required_revision}
              </li>
            ))}
          </Box>
        </Alert>
      )}
      {pending.length > 0 && (
        <Alert severity="info" variant="filled" sx={{ borderRadius: 0 }}>
          <AlertTitle>
            {t(
              'migrationCompat.pendingTitle',
              'Pro+ engine update waiting for a newer SysManage server',
            )}
          </AlertTitle>
          {t(
            'migrationCompat.pendingIntro',
            'An update to these Pro+ engines needs a newer SysManage server. The installed version stays in use until the server is upgraded.',
          )}
          <Box component="ul" sx={{ mt: 1, mb: 0, pl: 3 }}>
            {pending.map((p) => (
              <li key={p.module_code}>
                <strong>{p.module_code}</strong>
                {' -- '}
                {p.kept_version
                  ? t('migrationCompat.pendingItem', '{{version}} is waiting; {{kept}} stays in use', {
                    version: p.version ?? '',
                    kept: p.kept_version,
                  })
                  : t('migrationCompat.pendingItemNoKept', '{{version}} is waiting', {
                    version: p.version ?? '',
                  })}
              </li>
            ))}
          </Box>
        </Alert>
      )}
    </Box>
  );
};

export default MigrationCompatBanner;
