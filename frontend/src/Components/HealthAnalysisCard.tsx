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
import LightbulbIcon from '@mui/icons-material/Lightbulb';
import HealthAndSafetyIcon from '@mui/icons-material/HealthAndSafety';
import { useTranslation } from 'react-i18next';
import { getHostHealthAnalysis, runHostHealthAnalysis, HealthAnalysis } from '../Services/license';

interface HealthAnalysisCardProps {
    hostId: string;
}

const HealthAnalysisCard: React.FC<HealthAnalysisCardProps> = ({ hostId }) => {
    const { t } = useTranslation();
    const [analysis, setAnalysis] = useState<HealthAnalysis | null>(null);
    const [loading, setLoading] = useState<boolean>(true);
    const [running, setRunning] = useState<boolean>(false);
    const [error, setError] = useState<string | null>(null);

    const loadAnalysis = useCallback(async () => {
        setLoading(true);
        setError(null);
        try {
            const data = await getHostHealthAnalysis(hostId);
            setAnalysis(data);
        } catch (err: unknown) {
            const errorObj = err as { response?: { status?: number } };
            if (errorObj.response?.status === 403) {
                setError(t('health.notLicensed', 'Health analysis requires a Sysmanage Professional+ license'));
            } else if (errorObj.response?.status === 404) {
                // No analysis yet
                setAnalysis(null);
            } else {
                console.error('Error loading health analysis:', err);
                setError(t('health.loadError', 'Failed to load health analysis'));
            }
        } finally {
            setLoading(false);
        }
    }, [hostId, t]);

    const handleRunAnalysis = async () => {
        setRunning(true);
        setError(null);
        try {
            const data = await runHostHealthAnalysis(hostId);
            setAnalysis(data);
        } catch (err: unknown) {
            const errorObj = err as { response?: { status?: number } };
            if (errorObj.response?.status === 403) {
                setError(t('health.notLicensed', 'Health analysis requires a Sysmanage Professional+ license'));
            } else {
                console.error('Error running health analysis:', err);
                setError(t('health.runError', 'Failed to run health analysis'));
            }
        } finally {
            setRunning(false);
        }
    };

    useEffect(() => {
        loadAnalysis();
    }, [loadAnalysis]);

    // Get grade color
    const getGradeColor = (grade: string) => {
        switch (grade) {
            case 'A+':
            case 'A':
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
        switch (severity?.toLowerCase()) {
            case 'critical':
                return <ErrorIcon sx={{ color: 'error.main' }} />;
            case 'warning':
                return <WarningIcon sx={{ color: 'warning.main' }} />;
            case 'info':
                return <InfoIcon sx={{ color: 'info.main' }} />;
            default:
                return <InfoIcon sx={{ color: 'text.secondary' }} />;
        }
    };

    // Get priority color
    const getPriorityColor = (priority: string): 'error' | 'warning' | 'info' | 'default' => {
        switch (priority?.toLowerCase()) {
            case 'high':
                return 'error';
            case 'medium':
                return 'warning';
            case 'low':
                return 'info';
            default:
                return 'default';
        }
    };

    // Get score color for progress indicator
    const getScoreColor = (score: number) => {
        if (score >= 90) return 'success.main';
        if (score >= 70) return 'info.main';
        if (score >= 50) return 'warning.main';
        return 'error.main';
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
            {/* Health Score Card */}
            <Card sx={{ mb: 3 }}>
                <CardContent>
                    <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 2 }}>
                        <Box sx={{ display: 'flex', alignItems: 'center' }}>
                            <HealthAndSafetyIcon sx={{ mr: 1, color: 'primary.main', fontSize: 28 }} />
                            <Typography variant="h6">
                                {t('health.title', 'Health Analysis')}
                            </Typography>
                        </Box>
                        <Button
                            variant="outlined"
                            startIcon={running ? <CircularProgress size={16} /> : <RefreshIcon />}
                            onClick={handleRunAnalysis}
                            disabled={running}
                        >
                            {running ? t('health.running', 'Analyzing...') : t('health.runAnalysis', 'Run Analysis')}
                        </Button>
                    </Box>

                    {analysis ? (
                        <Grid container spacing={3} alignItems="center">
                            {/* Score Circle */}
                            <Grid size={{ xs: 12, sm: 4 }}>
                                <Box sx={{ display: 'flex', flexDirection: 'column', alignItems: 'center' }}>
                                    <Box sx={{ position: 'relative', display: 'inline-flex' }}>
                                        <CircularProgress
                                            variant="determinate"
                                            value={analysis.score}
                                            size={120}
                                            thickness={8}
                                            sx={{ color: getScoreColor(analysis.score) }}
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
                                                {analysis.score}
                                            </Typography>
                                            <Typography variant="caption" color="text.secondary">
                                                {t('health.score', 'Score')}
                                            </Typography>
                                        </Box>
                                    </Box>
                                    <Chip
                                        label={t('health.grade', 'Grade: {{grade}}', { grade: analysis.grade })}
                                        color={getGradeColor(analysis.grade)}
                                        sx={{ mt: 2, fontWeight: 'bold', fontSize: '1rem' }}
                                    />
                                </Box>
                            </Grid>

                            {/* Summary Stats */}
                            <Grid size={{ xs: 12, sm: 8 }}>
                                <Grid container spacing={2}>
                                    <Grid size={{ xs: 6 }}>
                                        <Box sx={{ textAlign: 'center', p: 2, bgcolor: 'background.default', borderRadius: 1 }}>
                                            <Typography variant="h4" color="error.main">
                                                {analysis.issues?.filter(i => i.severity === 'critical').length || 0}
                                            </Typography>
                                            <Typography variant="body2" color="text.secondary">
                                                {t('health.criticalIssues', 'Critical Issues')}
                                            </Typography>
                                        </Box>
                                    </Grid>
                                    <Grid size={{ xs: 6 }}>
                                        <Box sx={{ textAlign: 'center', p: 2, bgcolor: 'background.default', borderRadius: 1 }}>
                                            <Typography variant="h4" color="warning.main">
                                                {analysis.issues?.filter(i => i.severity === 'warning').length || 0}
                                            </Typography>
                                            <Typography variant="body2" color="text.secondary">
                                                {t('health.warnings', 'Warnings')}
                                            </Typography>
                                        </Box>
                                    </Grid>
                                    <Grid size={{ xs: 6 }}>
                                        <Box sx={{ textAlign: 'center', p: 2, bgcolor: 'background.default', borderRadius: 1 }}>
                                            <Typography variant="h4" color="success.main">
                                                {analysis.recommendations?.length || 0}
                                            </Typography>
                                            <Typography variant="body2" color="text.secondary">
                                                {t('health.recommendations', 'Recommendations')}
                                            </Typography>
                                        </Box>
                                    </Grid>
                                    <Grid size={{ xs: 6 }}>
                                        <Box sx={{ textAlign: 'center', p: 2, bgcolor: 'background.default', borderRadius: 1 }}>
                                            <Typography variant="body2" color="text.secondary">
                                                {t('health.analyzedAt', 'Analyzed')}
                                            </Typography>
                                            <Typography variant="body1">
                                                {new Date(analysis.analyzed_at).toLocaleString()}
                                            </Typography>
                                        </Box>
                                    </Grid>
                                </Grid>
                            </Grid>
                        </Grid>
                    ) : (
                        <Alert severity="info" icon={<HealthAndSafetyIcon />}>
                            {t('health.noAnalysis', 'No health analysis available. Click "Run Analysis" to analyze this host.')}
                        </Alert>
                    )}
                </CardContent>
            </Card>

            {/* Issues Accordion */}
            {analysis?.issues && analysis.issues.length > 0 && (
                <Accordion defaultExpanded sx={{ mb: 2 }}>
                    <AccordionSummary expandIcon={<ExpandMoreIcon />}>
                        <Box sx={{ display: 'flex', alignItems: 'center' }}>
                            <WarningIcon sx={{ mr: 1, color: 'warning.main' }} />
                            <Typography variant="h6">
                                {t('health.issuesTitle', 'Issues ({{count}})', { count: analysis.issues.length })}
                            </Typography>
                        </Box>
                    </AccordionSummary>
                    <AccordionDetails>
                        <List dense>
                            {analysis.issues.map((issue, index) => (
                                <React.Fragment key={`${issue.severity}-${issue.category}-${issue.message}`}>
                                    <ListItem alignItems="flex-start">
                                        <ListItemIcon sx={{ mt: 0.5 }}>
                                            {getSeverityIcon(issue.severity)}
                                        </ListItemIcon>
                                        <ListItemText
                                            primary={
                                                <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                                                    <Typography variant="body1">
                                                        {issue.message}
                                                    </Typography>
                                                    <Chip
                                                        label={issue.category}
                                                        size="small"
                                                        variant="outlined"
                                                    />
                                                </Box>
                                            }
                                            secondary={
                                                issue.details ? (
                                                    <Typography variant="body2" color="text.secondary" component="pre" sx={{ whiteSpace: 'pre-wrap', mt: 0.5 }}>
                                                        {JSON.stringify(issue.details, null, 2)}
                                                    </Typography>
                                                ) : null
                                            }
                                        />
                                    </ListItem>
                                    {index < analysis.issues!.length - 1 && <Divider variant="inset" component="li" />}
                                </React.Fragment>
                            ))}
                        </List>
                    </AccordionDetails>
                </Accordion>
            )}

            {/* Recommendations Accordion */}
            {analysis?.recommendations && analysis.recommendations.length > 0 && (
                <Accordion defaultExpanded>
                    <AccordionSummary expandIcon={<ExpandMoreIcon />}>
                        <Box sx={{ display: 'flex', alignItems: 'center' }}>
                            <LightbulbIcon sx={{ mr: 1, color: 'info.main' }} />
                            <Typography variant="h6">
                                {t('health.recommendationsTitle', 'Recommendations ({{count}})', { count: analysis.recommendations.length })}
                            </Typography>
                        </Box>
                    </AccordionSummary>
                    <AccordionDetails>
                        <List dense>
                            {analysis.recommendations.map((rec, index) => (
                                <React.Fragment key={`${rec.priority}-${rec.category}-${rec.message}`}>
                                    <ListItem alignItems="flex-start">
                                        <ListItemIcon sx={{ mt: 0.5 }}>
                                            <CheckCircleIcon sx={{ color: 'success.main' }} />
                                        </ListItemIcon>
                                        <ListItemText
                                            primary={
                                                <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                                                    <Typography variant="body1">
                                                        {rec.message}
                                                    </Typography>
                                                    <Chip
                                                        label={rec.priority}
                                                        size="small"
                                                        color={getPriorityColor(rec.priority)}
                                                    />
                                                    <Chip
                                                        label={rec.category}
                                                        size="small"
                                                        variant="outlined"
                                                    />
                                                </Box>
                                            }
                                            secondary={
                                                rec.action ? (
                                                    <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>
                                                        {t('health.suggestedAction', 'Suggested action')}: {rec.action}
                                                    </Typography>
                                                ) : null
                                            }
                                        />
                                    </ListItem>
                                    {index < analysis.recommendations!.length - 1 && <Divider variant="inset" component="li" />}
                                </React.Fragment>
                            ))}
                        </List>
                    </AccordionDetails>
                </Accordion>
            )}
        </Box>
    );
};

export default HealthAnalysisCard;
