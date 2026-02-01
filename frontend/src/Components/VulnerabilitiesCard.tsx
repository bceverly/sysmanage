import React, { useState, useEffect, useCallback } from 'react';
import {
    Box,
    Card,
    CardContent,
    Typography,
    Button,
    CircularProgress,
    Alert,
    Chip,
    Grid,
    Divider,
    List,
    ListItem,
    ListItemIcon,
    ListItemText,
    Accordion,
    AccordionSummary,
    AccordionDetails,
} from '@mui/material';
import RefreshIcon from '@mui/icons-material/Refresh';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import ErrorIcon from '@mui/icons-material/Error';
import WarningIcon from '@mui/icons-material/Warning';
import InfoIcon from '@mui/icons-material/Info';
import CheckCircleIcon from '@mui/icons-material/CheckCircle';
import BugReportIcon from '@mui/icons-material/BugReport';
import SecurityIcon from '@mui/icons-material/Security';
import { useTranslation } from 'react-i18next';
import { getHostVulnerabilityScan, runHostVulnerabilityScan, VulnerabilityScan, VulnerabilityFinding } from '../Services/license';

interface VulnerabilitiesCardProps {
    hostId: string;
}

const VulnerabilitiesCard: React.FC<VulnerabilitiesCardProps> = ({ hostId }) => {
    const { t } = useTranslation();
    const [scan, setScan] = useState<VulnerabilityScan | null>(null);
    const [loading, setLoading] = useState<boolean>(true);
    const [running, setRunning] = useState<boolean>(false);
    const [error, setError] = useState<string | null>(null);

    const loadScan = useCallback(async () => {
        setLoading(true);
        setError(null);
        try {
            const data = await getHostVulnerabilityScan(hostId);
            setScan(data);
        } catch (err: unknown) {
            const errorObj = err as { response?: { status?: number; data?: { error?: string; message?: string } } };
            if (errorObj.response?.status === 403) {
                setError(t('vulnerabilities.notLicensed', 'Vulnerability scanning requires a Sysmanage Professional+ license'));
            } else if (errorObj.response?.status === 503) {
                const detail = errorObj.response?.data;
                if (detail?.error === 'module_not_available') {
                    setError(t('vulnerabilities.moduleNotLoaded', 'Vulnerability engine module is not loaded'));
                } else {
                    setError(t('vulnerabilities.loadError', 'Failed to load vulnerability data'));
                }
            } else if (errorObj.response?.status === 404) {
                // No scan yet
                setScan(null);
            } else {
                console.error('Error loading vulnerability scan:', err);
                setError(t('vulnerabilities.loadError', 'Failed to load vulnerability data'));
            }
        } finally {
            setLoading(false);
        }
    }, [hostId, t]);

    const handleRunScan = async () => {
        setRunning(true);
        setError(null);
        try {
            const data = await runHostVulnerabilityScan(hostId);
            setScan(data);
        } catch (err: unknown) {
            const errorObj = err as { response?: { status?: number; data?: { error?: string; message?: string } } };
            if (errorObj.response?.status === 403) {
                setError(t('vulnerabilities.notLicensed', 'Vulnerability scanning requires a Sysmanage Professional+ license'));
            } else if (errorObj.response?.status === 503) {
                const detail = errorObj.response?.data;
                if (detail?.error === 'module_not_available') {
                    setError(t('vulnerabilities.moduleNotLoaded', 'Vulnerability engine module is not loaded'));
                } else {
                    setError(t('vulnerabilities.scanError', 'Failed to run vulnerability scan'));
                }
            } else {
                console.error('Error running vulnerability scan:', err);
                setError(t('vulnerabilities.scanError', 'Failed to run vulnerability scan'));
            }
        } finally {
            setRunning(false);
        }
    };

    useEffect(() => {
        loadScan();
    }, [loadScan]);

    // Get risk level color
    const getRiskLevelColor = (riskLevel: string): 'error' | 'warning' | 'info' | 'success' | 'default' => {
        switch (riskLevel?.toUpperCase()) {
            case 'CRITICAL':
                return 'error';
            case 'HIGH':
                return 'error';
            case 'MEDIUM':
                return 'warning';
            case 'LOW':
                return 'info';
            case 'NONE':
                return 'success';
            default:
                return 'default';
        }
    };

    // Get severity icon
    const getSeverityIcon = (severity: string) => {
        switch (severity?.toUpperCase()) {
            case 'CRITICAL':
                return <ErrorIcon sx={{ color: 'error.main' }} />;
            case 'HIGH':
                return <ErrorIcon sx={{ color: 'error.light' }} />;
            case 'MEDIUM':
                return <WarningIcon sx={{ color: 'warning.main' }} />;
            case 'LOW':
                return <InfoIcon sx={{ color: 'info.main' }} />;
            default:
                return <InfoIcon sx={{ color: 'text.secondary' }} />;
        }
    };

    // Get risk score color
    const getRiskScoreColor = (score: number) => {
        if (score >= 75) return 'error.main';
        if (score >= 50) return 'warning.main';
        if (score >= 25) return 'info.main';
        return 'success.main';
    };

    if (loading) {
        return (
            <Card>
                <CardContent>
                    <Box sx={{ display: 'flex', justifyContent: 'center', p: 4 }}>
                        <CircularProgress />
                    </Box>
                </CardContent>
            </Card>
        );
    }

    if (error) {
        return (
            <Card>
                <CardContent>
                    <Alert severity="error" sx={{ mb: 2 }}>
                        {error}
                    </Alert>
                </CardContent>
            </Card>
        );
    }

    return (
        <Box>
            {/* Vulnerability Scan Summary Card */}
            <Card sx={{ mb: 3 }}>
                <CardContent>
                    <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 2 }}>
                        <Box sx={{ display: 'flex', alignItems: 'center' }}>
                            <BugReportIcon sx={{ mr: 1, color: 'primary.main', fontSize: 28 }} />
                            <Typography variant="h6">
                                {t('vulnerabilities.title', 'Vulnerability Scan')}
                            </Typography>
                        </Box>
                        <Button
                            variant="outlined"
                            startIcon={running ? <CircularProgress size={16} /> : <RefreshIcon />}
                            onClick={handleRunScan}
                            disabled={running}
                        >
                            {running ? t('vulnerabilities.scanning', 'Scanning...') : t('vulnerabilities.runScan', 'Run Scan')}
                        </Button>
                    </Box>

                    {scan ? (
                        <Grid container spacing={3} alignItems="center">
                            {/* Risk Score Circle */}
                            <Grid size={{ xs: 12, sm: 4 }}>
                                <Box sx={{ display: 'flex', flexDirection: 'column', alignItems: 'center' }}>
                                    <Box sx={{ position: 'relative', display: 'inline-flex' }}>
                                        <CircularProgress
                                            variant="determinate"
                                            value={100 - scan.risk_score}
                                            size={120}
                                            thickness={8}
                                            sx={{ color: getRiskScoreColor(scan.risk_score) }}
                                        />
                                        <Box
                                            sx={{
                                                top: 0,
                                                left: 0,
                                                bottom: 0,
                                                right: 0,
                                                position: 'absolute',
                                                display: 'flex',
                                                alignItems: 'center',
                                                justifyContent: 'center',
                                                flexDirection: 'column',
                                            }}
                                        >
                                            <Typography variant="h4" component="div" sx={{ fontWeight: 'bold' }}>
                                                {scan.risk_score}
                                            </Typography>
                                            <Typography variant="caption" color="text.secondary">
                                                {t('vulnerabilities.riskScore', 'Risk Score')}
                                            </Typography>
                                        </Box>
                                    </Box>
                                    <Chip
                                        label={scan.risk_level}
                                        color={getRiskLevelColor(scan.risk_level)}
                                        sx={{ mt: 2, fontWeight: 'bold', fontSize: '1rem' }}
                                    />
                                </Box>
                            </Grid>

                            {/* Summary Stats */}
                            <Grid size={{ xs: 12, sm: 8 }}>
                                <Grid container spacing={2}>
                                    <Grid size={{ xs: 6, sm: 3 }}>
                                        <Box sx={{ textAlign: 'center', p: 2, bgcolor: 'background.default', borderRadius: 1 }}>
                                            <Typography variant="h4" color="error.main">
                                                {scan.critical_count}
                                            </Typography>
                                            <Typography variant="body2" color="text.secondary">
                                                {t('vulnerabilities.critical', 'Critical')}
                                            </Typography>
                                        </Box>
                                    </Grid>
                                    <Grid size={{ xs: 6, sm: 3 }}>
                                        <Box sx={{ textAlign: 'center', p: 2, bgcolor: 'background.default', borderRadius: 1 }}>
                                            <Typography variant="h4" color="error.light">
                                                {scan.high_count}
                                            </Typography>
                                            <Typography variant="body2" color="text.secondary">
                                                {t('vulnerabilities.high', 'High')}
                                            </Typography>
                                        </Box>
                                    </Grid>
                                    <Grid size={{ xs: 6, sm: 3 }}>
                                        <Box sx={{ textAlign: 'center', p: 2, bgcolor: 'background.default', borderRadius: 1 }}>
                                            <Typography variant="h4" color="warning.main">
                                                {scan.medium_count}
                                            </Typography>
                                            <Typography variant="body2" color="text.secondary">
                                                {t('vulnerabilities.medium', 'Medium')}
                                            </Typography>
                                        </Box>
                                    </Grid>
                                    <Grid size={{ xs: 6, sm: 3 }}>
                                        <Box sx={{ textAlign: 'center', p: 2, bgcolor: 'background.default', borderRadius: 1 }}>
                                            <Typography variant="h4" color="info.main">
                                                {scan.low_count}
                                            </Typography>
                                            <Typography variant="body2" color="text.secondary">
                                                {t('vulnerabilities.low', 'Low')}
                                            </Typography>
                                        </Box>
                                    </Grid>
                                    <Grid size={{ xs: 6 }}>
                                        <Box sx={{ textAlign: 'center', p: 2, bgcolor: 'background.default', borderRadius: 1 }}>
                                            <Typography variant="h5" color="text.primary">
                                                {scan.total_vulnerabilities}
                                            </Typography>
                                            <Typography variant="body2" color="text.secondary">
                                                {t('vulnerabilities.totalVulnerabilities', 'Total Vulnerabilities')}
                                            </Typography>
                                        </Box>
                                    </Grid>
                                    <Grid size={{ xs: 6 }}>
                                        <Box sx={{ textAlign: 'center', p: 2, bgcolor: 'background.default', borderRadius: 1 }}>
                                            <Typography variant="body2" color="text.secondary">
                                                {t('vulnerabilities.lastScanned', 'Last scanned')}
                                            </Typography>
                                            <Typography variant="body1">
                                                {new Date(scan.scanned_at).toLocaleString()}
                                            </Typography>
                                        </Box>
                                    </Grid>
                                </Grid>
                            </Grid>
                        </Grid>
                    ) : (
                        <Alert severity="info" icon={<SecurityIcon />}>
                            {t('vulnerabilities.noScan', 'No vulnerability scan available. Click "Run Scan" to scan this host.')}
                        </Alert>
                    )}
                </CardContent>
            </Card>

            {/* Vulnerabilities List Accordion */}
            {scan?.vulnerabilities && scan.vulnerabilities.length > 0 && (
                <Accordion defaultExpanded sx={{ mb: 2 }}>
                    <AccordionSummary expandIcon={<ExpandMoreIcon />}>
                        <Box sx={{ display: 'flex', alignItems: 'center' }}>
                            <BugReportIcon sx={{ mr: 1, color: 'error.main' }} />
                            <Typography variant="h6">
                                {t('vulnerabilities.vulnerabilitiesTitle', 'Vulnerabilities ({{count}})', { count: scan.vulnerabilities.length })}
                            </Typography>
                        </Box>
                    </AccordionSummary>
                    <AccordionDetails>
                        <List dense>
                            {scan.vulnerabilities.map((vuln: VulnerabilityFinding, index: number) => (
                                <React.Fragment key={vuln.id || `${vuln.cve_id}-${vuln.package_name}-${index}`}>
                                    <ListItem alignItems="flex-start">
                                        <ListItemIcon sx={{ mt: 0.5 }}>
                                            {getSeverityIcon(vuln.severity)}
                                        </ListItemIcon>
                                        <ListItemText
                                            primary={
                                                <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, flexWrap: 'wrap' }}>
                                                    <Typography variant="body1" component="span" sx={{ fontWeight: 'bold' }}>
                                                        {vuln.cve_id}
                                                    </Typography>
                                                    <Chip
                                                        label={vuln.severity}
                                                        size="small"
                                                        color={getRiskLevelColor(vuln.severity)}
                                                    />
                                                    {vuln.cvss_score && (
                                                        <Chip
                                                            label={`CVSS: ${vuln.cvss_score}`}
                                                            size="small"
                                                            variant="outlined"
                                                        />
                                                    )}
                                                </Box>
                                            }
                                            primaryTypographyProps={{ component: 'div' }}
                                            secondary={
                                                <Box component="span" sx={{ display: 'block', mt: 0.5 }}>
                                                    <Typography variant="body2" component="span" sx={{ display: 'block' }} color="text.primary">
                                                        {t('vulnerabilities.package', 'Package')}: {vuln.package_name} ({vuln.installed_version})
                                                    </Typography>
                                                    {vuln.fixed_version && (
                                                        <Typography variant="body2" component="span" sx={{ display: 'block' }} color="success.main">
                                                            {t('vulnerabilities.fixedIn', 'Fixed in')}: {vuln.fixed_version}
                                                        </Typography>
                                                    )}
                                                    {vuln.description && (
                                                        <Typography variant="body2" component="span" sx={{ display: 'block', mt: 0.5 }} color="text.secondary">
                                                            {vuln.description}
                                                        </Typography>
                                                    )}
                                                    {vuln.remediation && (
                                                        <Typography variant="body2" component="span" sx={{ display: 'block', mt: 0.5 }} color="info.main">
                                                            {t('vulnerabilities.remediation', 'Remediation')}: {vuln.remediation}
                                                        </Typography>
                                                    )}
                                                </Box>
                                            }
                                            secondaryTypographyProps={{ component: 'div' }}
                                        />
                                    </ListItem>
                                    {index < scan.vulnerabilities!.length - 1 && <Divider variant="inset" component="li" />}
                                </React.Fragment>
                            ))}
                        </List>
                    </AccordionDetails>
                </Accordion>
            )}

            {/* Recommendations Accordion */}
            {scan?.recommendations && scan.recommendations.length > 0 && (
                <Accordion defaultExpanded>
                    <AccordionSummary expandIcon={<ExpandMoreIcon />}>
                        <Box sx={{ display: 'flex', alignItems: 'center' }}>
                            <CheckCircleIcon sx={{ mr: 1, color: 'success.main' }} />
                            <Typography variant="h6">
                                {t('vulnerabilities.recommendationsTitle', 'Recommendations ({{count}})', { count: scan.recommendations.length })}
                            </Typography>
                        </Box>
                    </AccordionSummary>
                    <AccordionDetails>
                        <List dense>
                            {scan.recommendations.map((rec: string, index: number) => (
                                <React.Fragment key={`rec-${index}`}>
                                    <ListItem>
                                        <ListItemIcon>
                                            <CheckCircleIcon sx={{ color: 'success.main' }} />
                                        </ListItemIcon>
                                        <ListItemText primary={rec} />
                                    </ListItem>
                                    {index < scan.recommendations!.length - 1 && <Divider variant="inset" component="li" />}
                                </React.Fragment>
                            ))}
                        </List>
                    </AccordionDetails>
                </Accordion>
            )}

            {/* No vulnerabilities message */}
            {scan && scan.total_vulnerabilities === 0 && (
                <Alert severity="success" icon={<CheckCircleIcon />}>
                    {t('vulnerabilities.noVulnerabilities', 'No vulnerabilities found')}
                </Alert>
            )}
        </Box>
    );
};

export default VulnerabilitiesCard;
