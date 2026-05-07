import React, { useEffect, useState } from 'react';
import { Alert, AlertTitle, Box } from '@mui/material';
import { useTranslation } from 'react-i18next';
import api from '../Services/api';

interface ModuleCompatibilityEntry {
  module_code: string;
  required_revision: string;
  required_revision_human?: string | null;
  current_revision?: string | null;
}

interface ModuleCompatibilityResponse {
  incompatibilities: ModuleCompatibilityEntry[];
}

/**
 * MigrationCompatBanner — fallback banner shown when one or more Pro+
 * modules failed to load because the OSS database schema is older than
 * the module's declared minimum alembic revision.
 *
 * The normal path is for the operator to run `alembic upgrade head` as
 * part of the upgrade procedure.  This banner is the safety net for the
 * case where a Pro+ module is downloaded after an OSS upgrade but
 * before migrations have been applied.
 */
const MigrationCompatBanner: React.FC = () => {
  const { t } = useTranslation();
  const [entries, setEntries] = useState<ModuleCompatibilityEntry[]>([]);

  useEffect(() => {
    let cancelled = false;

    const check = async () => {
      const token = localStorage.getItem('bearer_token');
      if (!token) {
        if (!cancelled) setEntries([]);
        return;
      }
      try {
        const response = await api.get<ModuleCompatibilityResponse>(
          '/api/license/module-compat',
        );
        if (!cancelled) {
          setEntries(response.data?.incompatibilities ?? []);
        }
      } catch {
        // Endpoint may not exist on older servers; treat as no incompatibilities.
        if (!cancelled) setEntries([]);
      }
    };

    check();
    const interval = globalThis.setInterval(check, 60000);
    return () => {
      cancelled = true;
      globalThis.clearInterval(interval);
    };
  }, []);

  if (entries.length === 0) {
    return null;
  }

  return (
    <Box sx={{ position: 'sticky', top: 0, zIndex: 1100, width: '100%' }}>
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
        <code>alembic upgrade head</code>{' '}
        {t(
          'migrationCompat.outro',
          'on the server, then restart sysmanage.',
        )}
        <Box component="ul" sx={{ mt: 1, mb: 0, pl: 3 }}>
          {entries.map((e) => (
            <li key={e.module_code}>
              <strong>{e.module_code}</strong>
              {' — '}
              {t('migrationCompat.requires', 'requires')} {e.required_revision}
              {e.required_revision_human ? ` (${e.required_revision_human})` : ''}
              {e.current_revision
                ? `; ${t('migrationCompat.currently', 'currently at')} ${e.current_revision}`
                : `; ${t('migrationCompat.noVersion', 'no alembic_version row found')}`}
            </li>
          ))}
        </Box>
      </Alert>
    </Box>
  );
};

export default MigrationCompatBanner;
