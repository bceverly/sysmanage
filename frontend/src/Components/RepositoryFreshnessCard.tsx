/**
 * Repository Freshness card (Phase 11 B4) — visible only when this
 * server is the private-side half of an air-gap pair (``role:
 * repository``).  Surfaces ``days_since_ingest`` and the
 * freshness label returned by ``GET /api/v1/airgap/repository/
 * freshness`` so an operator can tell at a glance whether the
 * private mirror is current, stale, or critically out of date.
 *
 * The endpoint short-circuits with ``{label: "never", engine_loaded:
 * false}`` when the air-gap repository engine isn't loaded, so this
 * card renders a degraded-mode message in that case.
 */

import React, { useEffect, useState } from 'react';
import {
  Alert,
  Box,
  Card,
  CardContent,
  CircularProgress,
  Typography,
} from '@mui/material';
import { useTranslation } from 'react-i18next';

interface FreshnessResponse {
  last_ingest_at: string | null;
  days_since_ingest: number | null;
  freshness_label: 'current' | 'stale' | 'very_stale' | 'never';
  engine_loaded: boolean;
}

const LABEL_COLOR: Record<FreshnessResponse['freshness_label'], string> = {
  current: '#2d5a3d',
  stale: '#b8860b',
  very_stale: '#b32d2d',
  never: '#666666',
};

const RepositoryFreshnessCard: React.FC = () => {
  const { t } = useTranslation();
  const [data, setData] = useState<FreshnessResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [serverRole, setServerRole] = useState<string>('standard');

  useEffect(() => {
    // First check the server's role so we don't hit the freshness
    // endpoint on standard / collector deployments where it's not
    // meaningful.
    fetch('/api/v1/server-info')
      .then((r) => (r.ok ? r.json() : null))
      .then((info) => {
        if (!info) return;
        setServerRole(info.role || 'standard');
      })
      .catch(() => {});
  }, []);

  useEffect(() => {
    if (serverRole !== 'repository') {
      setLoading(false);
      return;
    }
    let cancelled = false;
    const token = localStorage.getItem('bearer_token');
    fetch('/api/v1/airgap/repository/freshness', {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    })
      .then((r) => {
        if (!r.ok) {
          throw new Error(`HTTP ${r.status}`);
        }
        return r.json();
      })
      .then((body: FreshnessResponse) => {
        if (cancelled) return;
        setData(body);
        setLoading(false);
      })
      .catch((err: Error) => {
        if (cancelled) return;
        setError(err.message);
        setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [serverRole]);

  // Hide entirely on non-repository roles — this card is meaningless
  // on a standard or collector deployment.
  if (serverRole !== 'repository') {
    return null;
  }

  return (
    <Card>
      <CardContent>
        <Typography variant="h6" gutterBottom>
          {t('airgap.freshness.title', 'Repository Freshness')}
        </Typography>
        {loading && <CircularProgress size={24} />}
        {error && (
          <Alert severity="error">
            {t('airgap.freshness.error', 'Failed to load freshness:')} {error}
          </Alert>
        )}
        {data && !data.engine_loaded && (
          <Alert severity="warning">
            {t(
              'airgap.freshness.engineMissing',
              'airgap_repository_engine not loaded; freshness data unavailable.',
            )}
          </Alert>
        )}
        {data && data.engine_loaded && (
          <Box>
            <Typography
              variant="h3"
              sx={{ color: LABEL_COLOR[data.freshness_label], fontWeight: 600 }}
            >
              {t(`airgap.freshness.label.${data.freshness_label}`)}
            </Typography>
            {data.days_since_ingest === null ? (
              <Typography variant="body2" sx={{ mt: 1 }}>
                {t('airgap.freshness.no_ingest', 'No media ever ingested.')}
              </Typography>
            ) : (
              <Typography variant="body2" sx={{ mt: 1 }}>
                {t(
                  'airgap.freshness.days_since',
                  '{{days}} day(s) since last ingest',
                  { days: data.days_since_ingest },
                )}
              </Typography>
            )}
            {data.last_ingest_at && (
              <Typography
                variant="caption"
                sx={{ display: 'block', mt: 0.5, color: 'text.secondary' }}
              >
                {t('airgap.freshness.last_ingest_at', 'Last ingest:')}{' '}
                {new Date(data.last_ingest_at).toLocaleString()}
              </Typography>
            )}
          </Box>
        )}
      </CardContent>
    </Card>
  );
};

export default RepositoryFreshnessCard;
