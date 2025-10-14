import React, { useEffect, useState, useRef } from 'react';
import {
  Card,
  CardContent,
  Typography,
  Box,
  Chip,
  CircularProgress,
  Alert,
  Grid,
} from '@mui/material';
import SecurityIcon from '@mui/icons-material/Security';
import CheckCircleIcon from '@mui/icons-material/CheckCircle';
import CancelIcon from '@mui/icons-material/Cancel';
import WarningIcon from '@mui/icons-material/Warning';
import { useTranslation } from 'react-i18next';
import { CommercialAntivirusStatus, getCommercialAntivirusStatus } from '../Services/commercialAntivirusService';

interface CommercialAntivirusStatusCardProps {
  hostId: string;
  refreshTrigger?: number;
  sx?: object;
}

const CommercialAntivirusStatusCard: React.FC<CommercialAntivirusStatusCardProps> = ({
  hostId,
  refreshTrigger = 0,
  sx = {},
}) => {
  const { t } = useTranslation();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<CommercialAntivirusStatus | null>(null);
  const isInitialLoad = useRef(true);

  useEffect(() => {
    const fetchStatus = async () => {
      if (isInitialLoad.current) {
        setLoading(true);
      }
      setError(null);
      try {
        const data = await getCommercialAntivirusStatus(hostId);
        setStatus(data);
        isInitialLoad.current = false;
      } catch (err) {
        console.error('Error fetching commercial antivirus status:', err);
        setError(t('security.commercialAntivirusError', 'Failed to load commercial antivirus status'));
      } finally {
        setLoading(false);
      }
    };

    if (hostId) {
      fetchStatus();
    }
  }, [hostId, t, refreshTrigger]);

  // Auto-refresh every 30 seconds
  useEffect(() => {
    if (!hostId) return;

    const intervalId = setInterval(async () => {
      try {
        const data = await getCommercialAntivirusStatus(hostId);
        setStatus(data);
      } catch (err) {
        console.error('Error refreshing commercial antivirus status:', err);
      }
    }, 30000); // 30 seconds

    return () => clearInterval(intervalId);
  }, [hostId]);

  const formatDate = (dateString: string | null): string => {
    if (!dateString) return t('common.notAvailable', 'N/A');
    try {
      // Database stores naive UTC datetime, so append 'Z' to indicate UTC
      const utcString = dateString.endsWith('Z') ? dateString : dateString + 'Z';
      const date = new Date(utcString);
      return date.toLocaleString();
    } catch {
      return t('common.notAvailable', 'N/A');
    }
  };

  const formatDaysAgo = (days: number | null): string => {
    if (days === null || days === undefined) return t('common.notAvailable', 'N/A');
    // Windows Defender uses 4294967295 (2^32-1) to indicate "never scanned"
    if (days >= 4294967295) return t('security.never', 'Never');
    if (days === 0) return t('security.today', 'Today');
    if (days === 1) return t('security.yesterday', 'Yesterday');
    return t('security.daysAgo', '{{days}} days ago', { days });
  };

  const BooleanStatus: React.FC<{ value: boolean | null; label: string }> = ({ value, label }) => {
    if (value === null || value === undefined) {
      return (
        <Box sx={{ display: 'flex', alignItems: 'center', mb: 1 }}>
          <WarningIcon sx={{ mr: 1, fontSize: '1rem', color: 'grey.500' }} />
          <Typography variant="body2">
            {label}: {t('common.unknown', 'Unknown')}
          </Typography>
        </Box>
      );
    }
    return (
      <Box sx={{ display: 'flex', alignItems: 'center', mb: 1 }}>
        {value ? (
          <CheckCircleIcon sx={{ mr: 1, fontSize: '1rem', color: 'success.main' }} />
        ) : (
          <CancelIcon sx={{ mr: 1, fontSize: '1rem', color: 'error.main' }} />
        )}
        <Typography variant="body2">
          {label}: {value ? t('common.enabled', 'Enabled') : t('common.disabled', 'Disabled')}
        </Typography>
      </Box>
    );
  };

  if (loading) {
    return (
      <Card sx={sx}>
        <CardContent>
          <Typography variant="subtitle1" sx={{ display: 'flex', alignItems: 'center', fontWeight: 'bold', fontSize: '1.1rem', mb: 2 }}>
            <SecurityIcon sx={{ mr: 1 }} />
            {t('security.commercialAntivirus', 'Antivirus - Commercial')}
          </Typography>
          <Box sx={{ display: 'flex', justifyContent: 'center', py: 2 }}>
            <CircularProgress />
          </Box>
        </CardContent>
      </Card>
    );
  }

  if (error) {
    return (
      <Card sx={sx}>
        <CardContent>
          <Typography variant="subtitle1" sx={{ display: 'flex', alignItems: 'center', fontWeight: 'bold', fontSize: '1.1rem', mb: 2 }}>
            <SecurityIcon sx={{ mr: 1 }} />
            {t('security.commercialAntivirus', 'Antivirus - Commercial')}
          </Typography>
          <Alert severity="error">{error}</Alert>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card sx={sx}>
      <CardContent>
        <Typography variant="subtitle1" sx={{ display: 'flex', alignItems: 'center', fontWeight: 'bold', fontSize: '1.1rem', mb: 2 }}>
          <SecurityIcon sx={{ mr: 1 }} />
          {t('security.commercialAntivirus', 'Antivirus - Commercial')}
        </Typography>

        {!status || !status.product_name ? (
          <Box sx={{ display: 'flex', alignItems: 'center', py: 2 }}>
            <WarningIcon sx={{ mr: 1, color: 'warning.main' }} />
            <Typography variant="body2" color="textSecondary">
              {t('security.noCommercialAntivirusDetected', 'No commercial antivirus detected')}
            </Typography>
          </Box>
        ) : (
          <>
            {/* Product Information */}
            <Box sx={{ mb: 2 }}>
              <Typography variant="body2" sx={{ fontWeight: 'bold', mb: 1 }}>
                {status.product_name}
              </Typography>
              {status.product_version && (
                <Typography variant="caption" color="textSecondary">
                  {t('security.version', 'Version')}: {status.product_version}
                </Typography>
              )}
            </Box>

            {/* Status Chips */}
            <Box sx={{ mb: 2, display: 'flex', gap: 1, flexWrap: 'wrap' }}>
              {status.antivirus_enabled ? (
                <Chip
                  label={t('security.protected', 'Protected')}
                  color="success"
                  size="small"
                  icon={<CheckCircleIcon />}
                />
              ) : (
                <Chip
                  label={t('security.notProtected', 'Not Protected')}
                  color="error"
                  size="small"
                  icon={<CancelIcon />}
                />
              )}
            </Box>

            {/* Protection Status */}
            <Grid container spacing={2}>
              <Grid size={{ xs: 12, md: 6 }}>
                <Typography variant="caption" sx={{ fontWeight: 'bold', display: 'block', mb: 1 }}>
                  {t('security.protectionStatus', 'Protection Status')}
                </Typography>
                <BooleanStatus
                  value={status.service_enabled}
                  label={t('security.coreService', 'Core Service')}
                />
                <BooleanStatus
                  value={status.antivirus_enabled}
                  label={t('security.antivirusProtection', 'Antivirus')}
                />
                <BooleanStatus
                  value={status.antispyware_enabled}
                  label={t('security.antispyware', 'Antispyware')}
                />
                <BooleanStatus
                  value={status.realtime_protection_enabled}
                  label={t('security.realtimeProtection', 'Real-time Protection')}
                />
                <BooleanStatus
                  value={status.tamper_protection_enabled}
                  label={t('security.tamperProtection', 'Tamper Protection')}
                />
              </Grid>

              <Grid size={{ xs: 12, md: 6 }}>
                <Typography variant="caption" sx={{ fontWeight: 'bold', display: 'block', mb: 1 }}>
                  {t('security.scanInformation', 'Scan Information')}
                </Typography>
                <Typography variant="body2" sx={{ mb: 1 }}>
                  {t('security.lastFullScan', 'Last Full Scan')}: {formatDaysAgo(status.full_scan_age)}
                </Typography>
                <Typography variant="body2" sx={{ mb: 1 }}>
                  {t('security.lastQuickScan', 'Last Quick Scan')}: {formatDaysAgo(status.quick_scan_age)}
                </Typography>
                {status.full_scan_end_time && (
                  <Typography variant="caption" color="textSecondary" sx={{ display: 'block', mb: 1 }}>
                    {formatDate(status.full_scan_end_time)}
                  </Typography>
                )}

                <Typography variant="caption" sx={{ fontWeight: 'bold', display: 'block', mt: 2, mb: 1 }}>
                  {t('security.signatureInformation', 'Signature Information')}
                </Typography>
                {status.signature_version && (
                  <Typography variant="body2" sx={{ mb: 1 }}>
                    {t('security.version', 'Version')}: {status.signature_version}
                  </Typography>
                )}
                {status.signature_last_updated && (
                  <Typography variant="caption" color="textSecondary">
                    {t('security.lastUpdated', 'Last Updated')}: {formatDate(status.signature_last_updated)}
                  </Typography>
                )}
              </Grid>
            </Grid>

            {/* Last Updated */}
            <Box sx={{ mt: 2, pt: 2, borderTop: 1, borderColor: 'divider' }}>
              <Typography variant="caption" color="textSecondary">
                {t('security.statusLastUpdated', 'Status last updated')}: {formatDate(status.last_updated)}
              </Typography>
            </Box>
          </>
        )}
      </CardContent>
    </Card>
  );
};

export default CommercialAntivirusStatusCard;
