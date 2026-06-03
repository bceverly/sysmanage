/**
 * Repository Statistics Dashboard (Phase 11.2).
 *
 * Per-repo: package count, freshness timestamp, last successful ingest,
 * signer fingerprint.  Aggregate row: total repos, total packages,
 * oldest freshness, count of stale repos (default threshold: 7 days).
 *
 * Only renders meaningful content on ``role: repository`` deployments;
 * on standard / collector roles the page shows a "not applicable" notice.
 *
 * Backend endpoint contract:
 *   GET /api/v1/airgap/repository/repositories
 *     → {
 *         repositories: [{
 *           id, distro, version, repo_url,
 *           last_ingest_at, package_count,
 *           days_since_ingest, freshness_label,
 *           signer_fingerprint
 *         }, ...],
 *         aggregate: {
 *           total_repositories, total_packages,
 *           oldest_days_since_ingest, stale_repository_count,
 *           stale_threshold_days
 *         }
 *       }
 *
 * The backend's aggregate is the source of truth (it knows the
 * configured stale threshold + does the signer_fingerprint join).
 * The frontend computes a local aggregate as a fallback only when
 * the backend's aggregate field is missing (older deployments that
 * returned a flat list).  Backwards-compat handling:
 *   - Array response → wrap as { repositories: [...], aggregate: null }
 *   - Object response → use as-is.
 *
 * When the backend hasn't shipped the list endpoint yet, the page
 * renders an explanatory empty state rather than a hard error.
 */
import React, { useEffect, useMemo, useState } from 'react';
import {
  Alert,
  Box,
  Card,
  CardContent,
  CircularProgress,
  Paper,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Typography,
} from '@mui/material';
import { useTranslation } from 'react-i18next';

import AirgapImportPanel from '../Components/AirgapImportPanel';

// Default freshness threshold used by the dashboard when the backend
// doesn't surface its own.  Matches the conservative default used in
// other air-gap views.
const DEFAULT_STALE_DAYS = 7;
const MS_PER_DAY = 24 * 60 * 60 * 1000;

interface RepositoryRow {
  id: string;
  distro: string;
  version: string;
  repo_url?: string | null;
  last_ingest_at: string | null;
  package_count: number | null;
  days_since_ingest?: number | null;
  freshness_label?: string | null;
  signer_fingerprint?: string | null;
}

interface AggregateBlock {
  total_repositories: number;
  total_packages: number;
  oldest_days_since_ingest: number | null;
  stale_repository_count: number;
  stale_threshold_days: number;
}

interface RepositoriesResponse {
  repositories: RepositoryRow[];
  aggregate: AggregateBlock | null;
}

interface ServerInfo {
  role?: string;
}

const computeDaysAgo = (iso: string | null): number | null => {
  if (!iso) return null;
  const ts = Date.parse(iso);
  if (Number.isNaN(ts)) return null;
  return Math.floor((Date.now() - ts) / MS_PER_DAY);
};

const AirgapRepositories: React.FC = () => {
  const { t } = useTranslation();
  const [serverRole, setServerRole] = useState<string>('standard');
  const [roleLoaded, setRoleLoaded] = useState(false);
  const [repos, setRepos] = useState<RepositoryRow[] | null>(null);
  const [serverAggregate, setServerAggregate] = useState<AggregateBlock | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [endpointMissing, setEndpointMissing] = useState(false);

  useEffect(() => {
    let cancelled = false;
    fetch('/api/v1/server-info')
      .then((r) => (r.ok ? r.json() : null))
      .then((info: ServerInfo | null) => {
        if (cancelled) return;
        setServerRole(info?.role || 'standard');
        setRoleLoaded(true);
      })
      .catch(() => {
        if (cancelled) return;
        setRoleLoaded(true);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!roleLoaded) return;
    if (serverRole !== 'repository') {
      setLoading(false);
      return;
    }
    let cancelled = false;
    const token = localStorage.getItem('bearer_token');
    fetch('/api/v1/airgap/repository/repositories', {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    })
      .then((r) => {
        if (r.status === 404) {
          setEndpointMissing(true);
          return null;
        }
        if (!r.ok) {
          throw new Error(`HTTP ${r.status}`);
        }
        return r.json();
      })
      .then((body: RepositoriesResponse | RepositoryRow[] | null) => {
        if (cancelled) return;
        // Tolerate the legacy flat-array shape from older deployments.
        if (Array.isArray(body)) {
          setRepos(body);
          setServerAggregate(null);
        } else if (body && typeof body === 'object') {
          setRepos(body.repositories || []);
          setServerAggregate(body.aggregate || null);
        } else {
          setRepos([]);
          setServerAggregate(null);
        }
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
  }, [serverRole, roleLoaded]);

  const aggregate = useMemo(() => {
    // Prefer the backend-supplied aggregate when available — it
    // knows the configured stale threshold + already did the
    // signer_fingerprint join.  Local computation is only the
    // fallback for legacy deployments returning a flat list.
    if (serverAggregate) {
      return {
        totalRepos: serverAggregate.total_repositories,
        totalPackages: serverAggregate.total_packages,
        oldestFreshnessDays: serverAggregate.oldest_days_since_ingest,
        staleCount: serverAggregate.stale_repository_count,
        staleThresholdDays: serverAggregate.stale_threshold_days,
      };
    }
    if (!repos || repos.length === 0) {
      return {
        totalRepos: 0,
        totalPackages: 0,
        oldestFreshnessDays: null as number | null,
        staleCount: 0,
        staleThresholdDays: DEFAULT_STALE_DAYS,
      };
    }
    let totalPackages = 0;
    let oldestDays: number | null = null;
    let staleCount = 0;
    for (const repo of repos) {
      totalPackages += repo.package_count ?? 0;
      const days = computeDaysAgo(repo.last_ingest_at);
      if (days === null) {
        // Never ingested counts as stale.
        staleCount += 1;
      } else {
        if (oldestDays === null || days > oldestDays) {
          oldestDays = days;
        }
        if (days > DEFAULT_STALE_DAYS) {
          staleCount += 1;
        }
      }
    }
    return {
      totalRepos: repos.length,
      totalPackages,
      oldestFreshnessDays: oldestDays,
      staleCount,
      staleThresholdDays: DEFAULT_STALE_DAYS,
    };
  }, [repos, serverAggregate]);

  if (!roleLoaded || loading) {
    return (
      <Box sx={{ p: 4, display: 'flex', justifyContent: 'center' }}>
        <CircularProgress />
      </Box>
    );
  }

  if (serverRole !== 'repository') {
    return (
      <Box sx={{ p: 4 }}>
        <Typography variant="h4" gutterBottom>
          {t('airgap.repositories.title', 'Air-Gap Repositories')}
        </Typography>
        <Alert severity="info">
          {t(
            'airgap.repositories.notApplicable',
            'This dashboard is only meaningful on repository-role deployments.',
          )}
        </Alert>
      </Box>
    );
  }

  return (
    <Box sx={{ p: 4 }}>
      <Typography variant="h4" gutterBottom>
        {t('airgap.repositories.title', 'Air-Gap Repositories')}
      </Typography>
      <Typography variant="body2" sx={{ mb: 2, color: 'text.secondary' }}>
        {t(
          'airgap.repositories.subtitle',
          'Per-repository statistics for this private-side mirror, plus aggregate freshness.',
        )}
      </Typography>

      {serverRole === 'repository' && <AirgapImportPanel />}

      {error && (
        <Alert severity="error" sx={{ mb: 2 }}>
          {t('airgap.repositories.loadError', 'Failed to load repositories:')} {error}
        </Alert>
      )}

      {endpointMissing && (
        <Alert severity="warning" sx={{ mb: 2 }}>
          {t(
            'airgap.repositories.endpointMissing',
            'Backend list-all-repositories endpoint not available; dashboard cannot populate.',
          )}
        </Alert>
      )}

      <Card sx={{ mb: 2 }}>
        <CardContent>
          <Typography variant="h6" gutterBottom>
            {t('airgap.repositories.aggregate.title', 'Aggregate')}
          </Typography>
          <Box sx={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
            <Box>
              <Typography variant="caption" color="text.secondary">
                {t('airgap.repositories.aggregate.totalRepos', 'Total repositories')}
              </Typography>
              <Typography variant="h5">{aggregate.totalRepos}</Typography>
            </Box>
            <Box>
              <Typography variant="caption" color="text.secondary">
                {t('airgap.repositories.aggregate.totalPackages', 'Total packages')}
              </Typography>
              <Typography variant="h5">{aggregate.totalPackages}</Typography>
            </Box>
            <Box>
              <Typography variant="caption" color="text.secondary">
                {t('airgap.repositories.aggregate.oldestFreshness', 'Oldest freshness')}
              </Typography>
              <Typography variant="h5">
                {aggregate.oldestFreshnessDays === null
                  ? t('airgap.repositories.aggregate.noIngest', 'N/A')
                  : t('airgap.repositories.aggregate.daysAgo', '{{days}} day(s) ago', {
                      days: aggregate.oldestFreshnessDays,
                    })}
              </Typography>
            </Box>
            <Box>
              <Typography variant="caption" color="text.secondary">
                {t('airgap.repositories.aggregate.staleRepos', 'Stale repos (> {{days}}d)', {
                  days: aggregate.staleThresholdDays,
                })}
              </Typography>
              <Typography
                variant="h5"
                sx={{ color: aggregate.staleCount > 0 ? '#b32d2d' : '#2d5a3d' }}
              >
                {aggregate.staleCount}
              </Typography>
            </Box>
          </Box>
        </CardContent>
      </Card>

      <TableContainer component={Paper}>
        <Table size="small">
          <TableHead>
            <TableRow>
              <TableCell>
                {t('airgap.repositories.table.distro', 'Distro')}
              </TableCell>
              <TableCell>
                {t('airgap.repositories.table.version', 'Version')}
              </TableCell>
              <TableCell align="right">
                {t('airgap.repositories.table.packageCount', 'Packages')}
              </TableCell>
              <TableCell>
                {t('airgap.repositories.table.lastIngest', 'Last successful ingest')}
              </TableCell>
              <TableCell>
                {t('airgap.repositories.table.freshness', 'Freshness')}
              </TableCell>
              <TableCell>
                {t('airgap.repositories.table.signerFingerprint', 'Signer fingerprint')}
              </TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {(repos || []).length === 0 && (
              <TableRow>
                <TableCell colSpan={6} align="center">
                  <Typography variant="body2" color="text.secondary" sx={{ py: 2 }}>
                    {t('airgap.repositories.table.empty', 'No repositories ingested yet.')}
                  </Typography>
                </TableCell>
              </TableRow>
            )}
            {(repos || []).map((repo) => {
              // Prefer the backend-computed days; fall back to local
              // calc only when the field is missing.  ``??`` handles
              // both undefined and null in one operator.
              const days =
                repo.days_since_ingest ?? computeDaysAgo(repo.last_ingest_at);
              const staleThreshold = aggregate.staleThresholdDays;
              const isStale = days === null || days > staleThreshold;
              return (
                <TableRow key={repo.id}>
                  <TableCell>{repo.distro}</TableCell>
                  <TableCell>{repo.version}</TableCell>
                  <TableCell align="right">{repo.package_count ?? 0}</TableCell>
                  <TableCell>
                    {repo.last_ingest_at
                      ? new Date(repo.last_ingest_at).toLocaleString()
                      : t('airgap.repositories.table.neverIngested', 'Never')}
                  </TableCell>
                  <TableCell sx={{ color: isStale ? '#b8860b' : '#2d5a3d' }}>
                    {days === null
                      ? t('airgap.repositories.table.freshnessNever', 'Never ingested')
                      : t('airgap.repositories.table.freshnessDays', '{{days}} day(s)', {
                          days,
                        })}
                  </TableCell>
                  <TableCell
                    sx={{
                      fontFamily: 'monospace',
                      fontSize: '0.8rem',
                      maxWidth: 220,
                      overflow: 'hidden',
                      textOverflow: 'ellipsis',
                      whiteSpace: 'nowrap',
                    }}
                    title={repo.signer_fingerprint || ''}
                  >
                    {repo.signer_fingerprint
                      ? repo.signer_fingerprint
                      : t('airgap.repositories.table.noFingerprint', '—')}
                  </TableCell>
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
      </TableContainer>
    </Box>
  );
};

export default AirgapRepositories;
