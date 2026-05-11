/**
 * Air-Gap Compliance Buckets card (Phase 11 B5) — surfaces the
 * three-bucket classification produced by
 * ``backend/services/airgap_compliance_context.classify_compliance_gap``:
 *
 *   - ``not_applied``     : update is on the local mirror, host hasn't
 *                            installed it yet.  Cheap to fix.
 *   - ``not_transferred`` : public CVE feed lists a fix that isn't on
 *                            the local mirror at all.  Requires a new
 *                            collection / burn / ingest cycle.
 *   - ``current``         : host's installed version matches the
 *                            mirror's latest, no public-side CVE has
 *                            surfaced since last transfer.
 *
 * Visible only on ``role: repository`` deployments.  Loads its data
 * from a host-scoped endpoint passed in as ``hostId`` — caller is
 * responsible for resolving the host context (HostDetail page, etc.).
 */

import React, { useEffect, useState } from 'react';
import {
  Alert,
  Box,
  Card,
  CardContent,
  Chip,
  CircularProgress,
  List,
  ListItem,
  ListItemText,
  Typography,
} from '@mui/material';
import { useTranslation } from 'react-i18next';

interface NotAppliedEntry {
  package: string;
  installed: string;
  available: string;
}

interface NotTransferredEntry {
  package: string;
  cve_id: string;
  fix_version: string | null;
}

interface CurrentEntry {
  package: string;
  version: string;
}

interface BucketsResponse {
  not_applied: NotAppliedEntry[];
  not_transferred: NotTransferredEntry[];
  current: CurrentEntry[];
}

interface Props {
  hostId: string;
}

const BUCKET_COLOR = {
  not_applied: '#b8860b',
  not_transferred: '#b32d2d',
  current: '#2d5a3d',
} as const;

const AirgapComplianceBucketsCard: React.FC<Props> = ({ hostId }) => {
  const { t } = useTranslation();
  const [data, setData] = useState<BucketsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [serverRole, setServerRole] = useState<string>('standard');

  useEffect(() => {
    fetch('/api/v1/server-info')
      .then((r) => (r.ok ? r.json() : null))
      .then((info) => info && setServerRole(info.role || 'standard'))
      .catch(() => {});
  }, []);

  useEffect(() => {
    if (serverRole !== 'repository' || !hostId) {
      setLoading(false);
      return;
    }
    let cancelled = false;
    const token = localStorage.getItem('bearer_token');
    fetch(`/api/v1/airgap/repository/host/${hostId}/compliance-buckets`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    })
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      })
      .then((body: BucketsResponse) => {
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
  }, [serverRole, hostId]);

  if (serverRole !== 'repository') {
    return null;
  }

  return (
    <Card>
      <CardContent>
        <Typography variant="h6" gutterBottom>
          {t('airgap.compliance.title', 'Air-Gap Compliance')}
        </Typography>
        {loading && <CircularProgress size={24} />}
        {error && (
          <Alert severity="error">
            {t('airgap.compliance.error', 'Failed to load compliance buckets:')} {error}
          </Alert>
        )}
        {data && (
          <Box>
            <Box sx={{ display: 'flex', gap: 1, mb: 2, flexWrap: 'wrap' }}>
              <Chip
                label={t('airgap.compliance.bucket.not_applied_count', '{{n}} not applied', {
                  n: data.not_applied.length,
                })}
                sx={{ bgcolor: BUCKET_COLOR.not_applied, color: 'white' }}
              />
              <Chip
                label={t(
                  'airgap.compliance.bucket.not_transferred_count',
                  '{{n}} not transferred',
                  { n: data.not_transferred.length },
                )}
                sx={{ bgcolor: BUCKET_COLOR.not_transferred, color: 'white' }}
              />
              <Chip
                label={t('airgap.compliance.bucket.current_count', '{{n}} current', {
                  n: data.current.length,
                })}
                sx={{ bgcolor: BUCKET_COLOR.current, color: 'white' }}
              />
            </Box>

            {data.not_applied.length > 0 && (
              <Box sx={{ mb: 2 }}>
                <Typography variant="subtitle1" sx={{ color: BUCKET_COLOR.not_applied }}>
                  {t('airgap.compliance.bucket.not_applied', 'Not Applied (fixable locally)')}
                </Typography>
                <List dense>
                  {data.not_applied.map((e) => (
                    <ListItem key={`na-${e.package}`}>
                      <ListItemText
                        primary={e.package}
                        secondary={t(
                          'airgap.compliance.not_applied_detail',
                          'Installed {{installed}} → available {{available}}',
                          { installed: e.installed, available: e.available },
                        )}
                      />
                    </ListItem>
                  ))}
                </List>
              </Box>
            )}

            {data.not_transferred.length > 0 && (
              <Box sx={{ mb: 2 }}>
                <Typography
                  variant="subtitle1"
                  sx={{ color: BUCKET_COLOR.not_transferred }}
                >
                  {t(
                    'airgap.compliance.bucket.not_transferred',
                    'Not Transferred (next media cycle required)',
                  )}
                </Typography>
                <List dense>
                  {data.not_transferred.map((e) => (
                    <ListItem key={`nt-${e.package}-${e.cve_id}`}>
                      <ListItemText
                        primary={e.package}
                        secondary={
                          e.fix_version
                            ? `${e.cve_id} → ${e.fix_version}`
                            : e.cve_id
                        }
                      />
                    </ListItem>
                  ))}
                </List>
              </Box>
            )}
          </Box>
        )}
      </CardContent>
    </Card>
  );
};

export default AirgapComplianceBucketsCard;
