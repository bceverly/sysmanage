import React, { useState, useEffect, useCallback } from 'react';
import {
  Card,
  CardContent,
  Typography,
  Box,
  CircularProgress,
  Alert,
  Stack,
  Divider,
  LinearProgress,
} from '@mui/material';
import {
  Security as SecurityIcon,
  CheckCircle as CheckCircleIcon,
  Warning as WarningIcon,
} from '@mui/icons-material';
import { useTranslation } from 'react-i18next';
import axiosInstance from '../Services/api';

interface AntivirusCoverageData {
  total_hosts: number;
  hosts_with_antivirus: number;
  hosts_without_antivirus: number;
  coverage_percentage: number;
}

const AntivirusCoverageCard: React.FC = () => {
  const { t } = useTranslation();
  const [coverage, setCoverage] = useState<AntivirusCoverageData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchCoverage = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const response = await axiosInstance.get('/api/antivirus-coverage');
      setCoverage(response.data);
    } catch (err: unknown) {
      console.error('Error fetching antivirus coverage:', err);
      const errorMessage = err && typeof err === 'object' && 'response' in err ?
        (err as {response?: {data?: {detail?: string}}}).response?.data?.detail || 'Failed to fetch antivirus coverage' :
        'Failed to fetch antivirus coverage';
      setError(errorMessage);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchCoverage();

    // Refresh every 60 seconds
    const interval = setInterval(fetchCoverage, 60000);
    return () => clearInterval(interval);
  }, [fetchCoverage]);

  if (loading) {
    return (
      <Card>
        <CardContent>
          <Box display="flex" justifyContent="center" alignItems="center" py={3}>
            <CircularProgress />
          </Box>
        </CardContent>
      </Card>
    );
  }

  const getCoverageColor = (percentage: number): 'success' | 'warning' | 'error' => {
    if (percentage >= 80) return 'success';
    if (percentage >= 50) return 'warning';
    return 'error';
  };

  const getCoverageIcon = (percentage: number) => {
    if (percentage >= 80) return <CheckCircleIcon color="success" />;
    return <WarningIcon color="warning" />;
  };

  const coveragePercentage = coverage?.coverage_percentage ?? 0;
  const coverageColor = getCoverageColor(coveragePercentage);

  return (
    <Card>
      <CardContent>
        <Box display="flex" alignItems="center" gap={1} mb={2}>
          <SecurityIcon color={coverageColor} />
          <Typography variant="h6">
            {t('security.antivirusCoverage.title', 'Antivirus Coverage')}
          </Typography>
        </Box>

        {error && (
          <Alert severity="error" sx={{ mb: 2 }}>
            {error}
          </Alert>
        )}

        {coverage && (
          <Stack spacing={2}>
            <Box>
              <Box display="flex" justifyContent="space-between" alignItems="center" mb={1}>
                <Typography variant="body2" color="text.secondary">
                  {t('security.antivirusCoverage.coverage', 'Coverage')}
                </Typography>
                <Box display="flex" alignItems="center" gap={0.5}>
                  {getCoverageIcon(coveragePercentage)}
                  <Typography variant="h5" fontWeight="bold" color={`${coverageColor}.main`}>
                    {coveragePercentage.toFixed(1)}%
                  </Typography>
                </Box>
              </Box>
              <LinearProgress
                variant="determinate"
                value={coveragePercentage}
                color={coverageColor}
                sx={{ height: 8, borderRadius: 1 }}
              />
            </Box>

            <Divider />

            <Stack direction="row" spacing={3} justifyContent="space-around">
              <Box textAlign="center">
                <Typography variant="body2" color="text.secondary">
                  {t('security.antivirusCoverage.totalHosts', 'Total Hosts')}
                </Typography>
                <Typography variant="h4" fontWeight="bold">
                  {coverage.total_hosts}
                </Typography>
              </Box>

              <Box textAlign="center">
                <Typography variant="body2" color="text.secondary">
                  {t('security.antivirusCoverage.protected', 'Protected')}
                </Typography>
                <Typography variant="h4" fontWeight="bold" color="success.main">
                  {coverage.hosts_with_antivirus}
                </Typography>
              </Box>

              <Box textAlign="center">
                <Typography variant="body2" color="text.secondary">
                  {t('security.antivirusCoverage.unprotected', 'Unprotected')}
                </Typography>
                <Typography variant="h4" fontWeight="bold" color="error.main">
                  {coverage.hosts_without_antivirus}
                </Typography>
              </Box>
            </Stack>

            {coverage.hosts_without_antivirus > 0 && (
              <>
                <Divider />
                <Alert severity="warning" variant="outlined">
                  <Typography variant="body2">
                    {t('security.antivirusCoverage.warningMessage',
                      '{{count}} host(s) do not have antivirus protection enabled.',
                      { count: coverage.hosts_without_antivirus }
                    )}
                  </Typography>
                </Alert>
              </>
            )}

            {coverage.total_hosts > 0 && coverage.hosts_without_antivirus === 0 && (
              <>
                <Divider />
                <Alert severity="success" variant="outlined">
                  <Typography variant="body2">
                    {t('security.antivirusCoverage.successMessage', 'All hosts have antivirus protection enabled.')}
                  </Typography>
                </Alert>
              </>
            )}
          </Stack>
        )}
      </CardContent>
    </Card>
  );
};

export default AntivirusCoverageCard;
