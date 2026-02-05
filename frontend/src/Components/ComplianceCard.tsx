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
import VerifiedUserIcon from '@mui/icons-material/VerifiedUser';
import SecurityIcon from '@mui/icons-material/Security';
import { useTranslation } from 'react-i18next';
import { getHostComplianceScan, runHostComplianceScan, ComplianceScan, ComplianceRuleResult } from '../Services/license';

interface ComplianceCardProps {
    hostId: string;
}

const ComplianceCard: React.FC<ComplianceCardProps> = ({ hostId }) => {
    const { t } = useTranslation();
    const [scan, setScan] = useState<ComplianceScan | null>(null);
    const [loading, setLoading] = useState<boolean>(true);
    const [running, setRunning] = useState<boolean>(false);
    const [error, setError] = useState<string | null>(null);

    const loadScan = useCallback(async () => {
        setLoading(true);
        setError(null);
        try {
            const data = await getHostComplianceScan(hostId);
            setScan(data);
        } catch (err: unknown) {
            const errorObj = err as { response?: { status?: number; data?: { error?: string; message?: string } } };
            if (errorObj.response?.status === 403) {
                setError(t('compliance.notLicensed', 'Compliance scanning requires a Sysmanage Professional+ license'));
            } else if (errorObj.response?.status === 503) {
                const detail = errorObj.response?.data;
                if (detail?.error === 'module_not_available') {
                    setError(t('compliance.moduleNotLoaded', 'Compliance engine module is not loaded'));
                } else {
                    setError(t('compliance.loadError', 'Failed to load compliance data'));
                }
            } else if (errorObj.response?.status === 404) {
                // No scan yet
                setScan(null);
            } else {
                console.error('Error loading compliance scan:', err);
                setError(t('compliance.loadError', 'Failed to load compliance data'));
            }
        } finally {
            setLoading(false);
        }
    }, [hostId, t]);

    const handleRunScan = async () => {
        setRunning(true);
        setError(null);
        try {
            const data = await runHostComplianceScan(hostId);
            setScan(data);
        } catch (err: unknown) {
            const errorObj = err as { response?: { status?: number; data?: { error?: string; message?: string } } };
            if (errorObj.response?.status === 403) {
                setError(t('compliance.notLicensed', 'Compliance scanning requires a Sysmanage Professional+ license'));
            } else if (errorObj.response?.status === 503) {
                const detail = errorObj.response?.data;
                if (detail?.error === 'module_not_available') {
                    setError(t('compliance.moduleNotLoaded', 'Compliance engine module is not loaded'));
                } else {
                    setError(t('compliance.scanError', 'Failed to run compliance scan'));
                }
            } else {
                console.error('Error running compliance scan:', err);
                setError(t('compliance.scanError', 'Failed to run compliance scan'));
            }
        } finally {
            setRunning(false);
        }
    };

    useEffect(() => {
        loadScan();
    }, [loadScan]);

    // Get compliance grade color
    const getGradeColor = (grade: string): 'error' | 'warning' | 'info' | 'success' | 'default' => {
        switch (grade?.toUpperCase()) {
            case 'A':
            case 'A+':
                return 'success';
            case 'B':
                return 'info';
            case 'C':
                return 'warning';
            case 'D':
            case 'F':
                return 'error';
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

    // Get compliance score color (higher = better, inverted from vuln)
    const getScoreColor = (score: number) => {
        if (score >= 90) return 'success.main';
        if (score >= 70) return 'info.main';
        if (score >= 50) return 'warning.main';
        return 'error.main';
    };

    // Get status chip color
    const getStatusColor = (status: string): 'success' | 'error' | 'warning' | 'default' => {
        switch (status?.toLowerCase()) {
            case 'pass':
                return 'success';
            case 'fail':
                return 'error';
            case 'error':
                return 'warning';
            default:
                return 'default';
        }
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

    // Group failed rules by severity
    const failedRules = scan?.results?.filter(r => r.status?.toLowerCase() === 'fail') || [];
    const criticalFailures = failedRules.filter(r => r.severity?.toUpperCase() === 'CRITICAL');
    const highFailures = failedRules.filter(r => r.severity?.toUpperCase() === 'HIGH');
    const mediumFailures = failedRules.filter(r => r.severity?.toUpperCase() === 'MEDIUM');
    const lowFailures = failedRules.filter(r => r.severity?.toUpperCase() === 'LOW');

    const severityGroups = [
        { label: t('compliance.critical', 'Critical'), rules: criticalFailures, color: 'error' as const },
        { label: t('compliance.high', 'High'), rules: highFailures, color: 'error' as const },
        { label: t('compliance.medium', 'Medium'), rules: mediumFailures, color: 'warning' as const },
        { label: t('compliance.low', 'Low'), rules: lowFailures, color: 'info' as const },
    ];

    return (
        <Box>
            {/* Compliance Scan Summary Card */}
            <Card sx={{ mb: 3 }}>
                <CardContent>
                    <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 2 }}>
                        <Box sx={{ display: 'flex', alignItems: 'center' }}>
                            <VerifiedUserIcon sx={{ mr: 1, color: 'primary.main', fontSize: 28 }} />
                            <Typography variant="h6">
                                {t('compliance.title', 'Compliance Scan')}
                            </Typography>
                        </Box>
                        <Button
                            variant="outlined"
                            startIcon={running ? <CircularProgress size={16} /> : <RefreshIcon />}
                            onClick={handleRunScan}
                            disabled={running}
                        >
                            {running ? t('compliance.scanning', 'Scanning...') : t('compliance.runScan', 'Run Scan')}
                        </Button>
                    </Box>

                    {scan ? (
                        <Grid container spacing={3} alignItems="center">
                            {/* Compliance Score Circle */}
                            <Grid size={{ xs: 12, sm: 4 }}>
                                <Box sx={{ display: 'flex', flexDirection: 'column', alignItems: 'center' }}>
                                    <Box sx={{ position: 'relative', display: 'inline-flex' }}>
                                        <CircularProgress
                                            variant="determinate"
                                            value={scan.compliance_score}
                                            size={120}
                                            thickness={8}
                                            sx={{ color: getScoreColor(scan.compliance_score) }}
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
                                                {scan.compliance_score}
                                            </Typography>
                                            <Typography variant="caption" color="text.secondary">
                                                {t('compliance.complianceScore', 'Score')}
                                            </Typography>
                                        </Box>
                                    </Box>
                                    <Chip
                                        label={scan.compliance_grade}
                                        color={getGradeColor(scan.compliance_grade)}
                                        sx={{ mt: 2, fontWeight: 'bold', fontSize: '1rem' }}
                                    />
                                </Box>
                            </Grid>

                            {/* Summary Stats */}
                            <Grid size={{ xs: 12, sm: 8 }}>
                                <Grid container spacing={2}>
                                    <Grid size={{ xs: 6, sm: 3 }}>
                                        <Box sx={{ textAlign: 'center', p: 2, bgcolor: 'background.default', borderRadius: 1 }}>
                                            <Typography variant="h4" color="success.main">
                                                {scan.passed_rules}
                                            </Typography>
                                            <Typography variant="body2" color="text.secondary">
                                                {t('compliance.passed', 'Passed')}
                                            </Typography>
                                        </Box>
                                    </Grid>
                                    <Grid size={{ xs: 6, sm: 3 }}>
                                        <Box sx={{ textAlign: 'center', p: 2, bgcolor: 'background.default', borderRadius: 1 }}>
                                            <Typography variant="h4" color="error.main">
                                                {scan.failed_rules}
                                            </Typography>
                                            <Typography variant="body2" color="text.secondary">
                                                {t('compliance.failed', 'Failed')}
                                            </Typography>
                                        </Box>
                                    </Grid>
                                    <Grid size={{ xs: 6, sm: 3 }}>
                                        <Box sx={{ textAlign: 'center', p: 2, bgcolor: 'background.default', borderRadius: 1 }}>
                                            <Typography variant="h4" color="error.main">
                                                {scan.critical_failures}
                                            </Typography>
                                            <Typography variant="body2" color="text.secondary">
                                                {t('compliance.critical', 'Critical')}
                                            </Typography>
                                        </Box>
                                    </Grid>
                                    <Grid size={{ xs: 6, sm: 3 }}>
                                        <Box sx={{ textAlign: 'center', p: 2, bgcolor: 'background.default', borderRadius: 1 }}>
                                            <Typography variant="h4" color="error.light">
                                                {scan.high_failures}
                                            </Typography>
                                            <Typography variant="body2" color="text.secondary">
                                                {t('compliance.high', 'High')}
                                            </Typography>
                                        </Box>
                                    </Grid>
                                    <Grid size={{ xs: 6, sm: 3 }}>
                                        <Box sx={{ textAlign: 'center', p: 2, bgcolor: 'background.default', borderRadius: 1 }}>
                                            <Typography variant="h4" color="warning.main">
                                                {scan.medium_failures}
                                            </Typography>
                                            <Typography variant="body2" color="text.secondary">
                                                {t('compliance.medium', 'Medium')}
                                            </Typography>
                                        </Box>
                                    </Grid>
                                    <Grid size={{ xs: 6, sm: 3 }}>
                                        <Box sx={{ textAlign: 'center', p: 2, bgcolor: 'background.default', borderRadius: 1 }}>
                                            <Typography variant="h4" color="info.main">
                                                {scan.low_failures}
                                            </Typography>
                                            <Typography variant="body2" color="text.secondary">
                                                {t('compliance.low', 'Low')}
                                            </Typography>
                                        </Box>
                                    </Grid>
                                    <Grid size={{ xs: 6, sm: 3 }}>
                                        <Box sx={{ textAlign: 'center', p: 2, bgcolor: 'background.default', borderRadius: 1 }}>
                                            <Typography variant="h5" color="text.primary">
                                                {scan.total_rules}
                                            </Typography>
                                            <Typography variant="body2" color="text.secondary">
                                                {t('compliance.totalRules', 'Total Rules')}
                                            </Typography>
                                        </Box>
                                    </Grid>
                                    <Grid size={{ xs: 6, sm: 3 }}>
                                        <Box sx={{ textAlign: 'center', p: 2, bgcolor: 'background.default', borderRadius: 1 }}>
                                            <Typography variant="body2" color="text.secondary">
                                                {t('compliance.lastScanned', 'Last scanned')}
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
                            {t('compliance.noScan', 'No compliance scan available. Click "Run Scan" to scan this host.')}
                        </Alert>
                    )}
                </CardContent>
            </Card>

            {/* Rule Failures Accordion (grouped by severity) */}
            {failedRules.length > 0 && (
                <Accordion defaultExpanded sx={{ mb: 2 }}>
                    <AccordionSummary expandIcon={<ExpandMoreIcon />}>
                        <Box sx={{ display: 'flex', alignItems: 'center' }}>
                            <VerifiedUserIcon sx={{ mr: 1, color: 'error.main' }} />
                            <Typography variant="h6">
                                {t('compliance.failuresTitle', 'Rule Failures ({{count}})', { count: failedRules.length })}
                            </Typography>
                        </Box>
                    </AccordionSummary>
                    <AccordionDetails>
                        {severityGroups.map(group => group.rules.length > 0 && (
                            <Box key={group.label} sx={{ mb: 2 }}>
                                <Typography variant="subtitle2" sx={{ mb: 1, fontWeight: 'bold' }}>
                                    <Chip label={group.label} size="small" color={group.color} sx={{ mr: 1 }} />
                                    ({group.rules.length})
                                </Typography>
                                <List dense>
                                    {group.rules.map((rule: ComplianceRuleResult, index: number) => (
                                        <React.Fragment key={rule.rule_id}>
                                            <ListItem alignItems="flex-start">
                                                <ListItemIcon sx={{ mt: 0.5 }}>
                                                    {getSeverityIcon(rule.severity)}
                                                </ListItemIcon>
                                                <ListItemText
                                                    primary={
                                                        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, flexWrap: 'wrap' }}>
                                                            <Typography variant="body1" component="span" sx={{ fontWeight: 'bold' }}>
                                                                {rule.rule_id}
                                                            </Typography>
                                                            <Chip
                                                                label={rule.status}
                                                                size="small"
                                                                color={getStatusColor(rule.status)}
                                                            />
                                                            {rule.benchmark && (
                                                                <Chip
                                                                    label={rule.benchmark}
                                                                    size="small"
                                                                    variant="outlined"
                                                                />
                                                            )}
                                                        </Box>
                                                    }
                                                    secondary={
                                                        <Box component="span" sx={{ display: 'block', mt: 0.5 }}>
                                                            <Typography variant="body2" component="span" sx={{ display: 'block' }} color="text.primary">
                                                                {rule.rule_name}
                                                            </Typography>
                                                            {rule.category && (
                                                                <Typography variant="body2" component="span" sx={{ display: 'block' }} color="text.secondary">
                                                                    {t('compliance.category', 'Category')}: {rule.category}
                                                                </Typography>
                                                            )}
                                                            {rule.remediation && (
                                                                <Typography variant="body2" component="span" sx={{ display: 'block', mt: 0.5 }} color="info.main">
                                                                    {t('compliance.remediation', 'Remediation')}: {rule.remediation}
                                                                </Typography>
                                                            )}
                                                        </Box>
                                                    }
                                                    slotProps={{ primary: { component: 'div' }, secondary: { component: 'div' } }}
                                                />
                                            </ListItem>
                                            {index < group.rules.length - 1 && <Divider variant="inset" component="li" />}
                                        </React.Fragment>
                                    ))}
                                </List>
                            </Box>
                        ))}
                    </AccordionDetails>
                </Accordion>
            )}

            {/* No failures message */}
            {scan && failedRules.length === 0 && (
                <Alert severity="success" icon={<CheckCircleIcon />}>
                    {t('compliance.noFailures', 'All compliance rules passed')}
                </Alert>
            )}
        </Box>
    );
};

export default ComplianceCard;
