import React, { useEffect, useState } from 'react';
import { Alert, AlertTitle, Box } from '@mui/material';
import { useTranslation } from 'react-i18next';
import api from '../Services/api';

interface MigrationStatusResponse {
  tenants_pending: number;
  tenant_slugs: string[];
  tenant_head?: string | null;
}

/**
 * TenantMigrationBanner — non-blocking warning shown when one or more tenant
 * databases are behind the code's tenant Alembic head (Phase 13.1).
 *
 * After a package upgrade the control plane is migrated, but each tenant DB is
 * migrated by the per-tenant fan-out (`sysmanage-migrate`).  A lagging tenant
 * DB is otherwise silent, so this surfaces it.  Polls the control-plane status
 * endpoint, which only exists when multi-tenancy is enabled (404 → no banner).
 */
const TenantMigrationBanner: React.FC = () => {
  const { t } = useTranslation();
  const [pending, setPending] = useState<string[]>([]);

  useEffect(() => {
    let cancelled = false;

    const check = async () => {
      if (!localStorage.getItem('bearer_token')) {
        if (!cancelled) setPending([]);
        return;
      }
      try {
        const r = await api.get<MigrationStatusResponse>(
          '/api/control-plane/migration-status',
        );
        if (!cancelled) setPending(r.data?.tenant_slugs ?? []);
      } catch {
        // Endpoint absent (multi-tenancy off / older server) → no banner.
        if (!cancelled) setPending([]);
      }
    };

    check();
    const interval = globalThis.setInterval(check, 60000);
    return () => {
      cancelled = true;
      globalThis.clearInterval(interval);
    };
  }, []);

  if (pending.length === 0) {
    return null;
  }

  return (
    <Box sx={{ position: 'sticky', top: 0, zIndex: 1100, width: '100%' }}>
      <Alert severity="warning" variant="filled" sx={{ borderRadius: 0 }}>
        <AlertTitle>
          {t('tenantMigration.title', 'Tenant database migration required')}
        </AlertTitle>
        {t(
          'tenantMigration.intro',
          'These tenant databases are behind the current code. Run',
        )}{' '}
        <code>sysmanage-migrate</code>{' '}
        {t('tenantMigration.outro', 'on the server (OpenBAO must be running):')}
        <Box component="ul" sx={{ mt: 1, mb: 0, pl: 3 }}>
          {pending.map((slug) => (
            <li key={slug}>
              <strong>{slug}</strong>
            </li>
          ))}
        </Box>
      </Alert>
    </Box>
  );
};

export default TenantMigrationBanner;
