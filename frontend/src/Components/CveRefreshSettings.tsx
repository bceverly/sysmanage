import React, { useState, useEffect, useCallback } from 'react';
import {
    Box,
    Card,
    CardContent,
    Typography,
    Button,
    CircularProgress,
    Alert,
    Switch,
    FormControlLabel,
    TextField,
    Chip,
    Grid,
    List,
    ListItem,
    ListItemIcon,
    ListItemText,
    Checkbox,
    IconButton,
    Tooltip,
    Accordion,
    AccordionSummary,
    AccordionDetails,
    Table,
    TableBody,
    TableCell,
    TableContainer,
    TableHead,
    TableRow,
    Paper,
    Select,
    MenuItem,
    FormControl,
    InputLabel,
    InputAdornment,
} from '@mui/material';
import RefreshIcon from '@mui/icons-material/Refresh';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import SecurityIcon from '@mui/icons-material/Security';
import StorageIcon from '@mui/icons-material/Storage';
import ScheduleIcon from '@mui/icons-material/Schedule';
import HistoryIcon from '@mui/icons-material/History';
import CheckCircleIcon from '@mui/icons-material/CheckCircle';
import ErrorIcon from '@mui/icons-material/Error';
import KeyIcon from '@mui/icons-material/Key';
import DeleteIcon from '@mui/icons-material/Delete';
import VisibilityIcon from '@mui/icons-material/Visibility';
import VisibilityOffIcon from '@mui/icons-material/VisibilityOff';
import SaveIcon from '@mui/icons-material/Save';
import { useTranslation } from 'react-i18next';
import {
    getCveSources,
    getCveRefreshSettings,
    updateCveRefreshSettings,
    getCveDatabaseStats,
    getCveIngestionHistory,
    triggerCveRefresh,
    clearNvdApiKey,
    CveSourceInfo,
    CveRefreshSettings as CveRefreshSettingsType,
    CveDatabaseStats,
    CveIngestionLog,
} from '../Services/license';

const CveRefreshSettingsComponent: React.FC = () => {
    const { t } = useTranslation();
    const [loading, setLoading] = useState(true);
    const [saving, setSaving] = useState(false);
    const [refreshing, setRefreshing] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [success, setSuccess] = useState<string | null>(null);

    // Data state
    const [sources, setSources] = useState<Record<string, CveSourceInfo>>({});
    const [settings, setSettings] = useState<CveRefreshSettingsType | null>(null);
    const [stats, setStats] = useState<CveDatabaseStats | null>(null);
    const [history, setHistory] = useState<CveIngestionLog[]>([]);

    // Form state
    const [enabled, setEnabled] = useState(true);
    const [refreshInterval, setRefreshInterval] = useState(24);
    const [enabledSources, setEnabledSources] = useState<string[]>([]);
    const [nvdApiKey, setNvdApiKey] = useState('');
    const [showApiKey, setShowApiKey] = useState(false);

    const loadData = useCallback(async () => {
        setLoading(true);
        setError(null);
        try {
            const [sourcesData, settingsData, statsData, historyData] = await Promise.all([
                getCveSources(),
                getCveRefreshSettings(),
                getCveDatabaseStats(),
                getCveIngestionHistory(10),
            ]);
            setSources(sourcesData);
            setSettings(settingsData);
            setStats(statsData);
            setHistory(historyData);

            // Initialize form state from settings
            setEnabled(settingsData.enabled);
            setRefreshInterval(settingsData.refresh_interval_hours);
            setEnabledSources(settingsData.enabled_sources);
        } catch (err) {
            console.error('Error loading CVE refresh settings:', err);
            setError(t('cveRefresh.loadError', 'Failed to load CVE refresh settings'));
        } finally {
            setLoading(false);
        }
    }, [t]);

    useEffect(() => {
        loadData();
    }, [loadData]);

    const handleSaveSettings = async () => {
        setSaving(true);
        setError(null);
        setSuccess(null);
        try {
            const updateData: { enabled?: boolean; refresh_interval_hours?: number; enabled_sources?: string[]; nvd_api_key?: string } = {
                enabled,
                refresh_interval_hours: refreshInterval,
                enabled_sources: enabledSources,
            };

            // Only include API key if it was changed
            if (nvdApiKey) {
                updateData.nvd_api_key = nvdApiKey;
            }

            const updatedSettings = await updateCveRefreshSettings(updateData);
            setSettings(updatedSettings);
            setNvdApiKey(''); // Clear API key field after save
            setSuccess(t('cveRefresh.saveSuccess', 'Settings saved successfully'));
        } catch (err) {
            console.error('Error saving CVE refresh settings:', err);
            setError(t('cveRefresh.saveError', 'Failed to save settings'));
        } finally {
            setSaving(false);
        }
    };

    const handleRefresh = async (source?: string) => {
        setRefreshing(true);
        setError(null);
        setSuccess(null);
        try {
            await triggerCveRefresh(source);
            setSuccess(t('cveRefresh.refreshSuccess', 'CVE database refresh completed'));
            // Reload data to show updated stats
            await loadData();
        } catch (err) {
            console.error('Error refreshing CVE database:', err);
            setError(t('cveRefresh.refreshError', 'Failed to refresh CVE database'));
        } finally {
            setRefreshing(false);
        }
    };

    const handleClearApiKey = async () => {
        try {
            await clearNvdApiKey();
            setSettings(prev => prev ? { ...prev, has_nvd_api_key: false } : null);
            setSuccess(t('cveRefresh.apiKeyCleared', 'NVD API key cleared'));
        } catch (err) {
            console.error('Error clearing NVD API key:', err);
            setError(t('cveRefresh.clearApiKeyError', 'Failed to clear API key'));
        }
    };

    const handleSourceToggle = (sourceId: string) => {
        setEnabledSources(prev => {
            if (prev.includes(sourceId)) {
                return prev.filter(s => s !== sourceId);
            } else {
                return [...prev, sourceId];
            }
        });
    };

    const formatDate = (dateString?: string) => {
        if (!dateString) return t('common.never', 'Never');
        return new Date(dateString).toLocaleString();
    };

    const getStatusColor = (status: string): 'success' | 'error' | 'warning' | 'info' => {
        switch (status) {
            case 'success':
                return 'success';
            case 'failed':
                return 'error';
            case 'running':
                return 'info';
            default:
                return 'warning';
        }
    };

    const getStatusIcon = (status: string) => {
        switch (status) {
            case 'success':
                return <CheckCircleIcon />;
            case 'failed':
                return <ErrorIcon />;
            default:
                return undefined;
        }
    };

    if (loading) {
        return (
            <Box sx={{ display: 'flex', justifyContent: 'center', p: 4 }}>
                <CircularProgress />
            </Box>
        );
    }

    return (
        <Box>
            {error && (
                <Alert severity="error" sx={{ mb: 2 }} onClose={() => setError(null)}>
                    {error}
                </Alert>
            )}
            {success && (
                <Alert severity="success" sx={{ mb: 2 }} onClose={() => setSuccess(null)}>
                    {success}
                </Alert>
            )}

            {/* Database Statistics Card */}
            <Card sx={{ mb: 3 }}>
                <CardContent>
                    <Box sx={{ display: 'flex', alignItems: 'center', mb: 2 }}>
                        <StorageIcon sx={{ mr: 1, color: 'primary.main' }} />
                        <Typography variant="h6">
                            {t('cveRefresh.databaseStats', 'CVE Database Statistics')}
                        </Typography>
                    </Box>

                    <Grid container spacing={2}>
                        <Grid size={{ xs: 6, sm: 3 }}>
                            <Box sx={{ textAlign: 'center', p: 2, bgcolor: 'background.default', borderRadius: 1 }}>
                                <Typography variant="h4" color="primary.main">
                                    {stats?.total_cves?.toLocaleString() || 0}
                                </Typography>
                                <Typography variant="body2" color="text.secondary">
                                    {t('cveRefresh.totalCves', 'Total CVEs')}
                                </Typography>
                            </Box>
                        </Grid>
                        <Grid size={{ xs: 6, sm: 3 }}>
                            <Box sx={{ textAlign: 'center', p: 2, bgcolor: 'background.default', borderRadius: 1 }}>
                                <Typography variant="h4" color="secondary.main">
                                    {stats?.total_package_mappings?.toLocaleString() || 0}
                                </Typography>
                                <Typography variant="body2" color="text.secondary">
                                    {t('cveRefresh.packageMappings', 'Package Mappings')}
                                </Typography>
                            </Box>
                        </Grid>
                        <Grid size={{ xs: 6, sm: 3 }}>
                            <Box sx={{ textAlign: 'center', p: 2, bgcolor: 'background.default', borderRadius: 1 }}>
                                <Typography variant="body2" color="text.secondary">
                                    {t('cveRefresh.lastRefresh', 'Last Refresh')}
                                </Typography>
                                <Typography variant="body1">
                                    {formatDate(stats?.last_refresh_at)}
                                </Typography>
                            </Box>
                        </Grid>
                        <Grid size={{ xs: 6, sm: 3 }}>
                            <Box sx={{ textAlign: 'center', p: 2, bgcolor: 'background.default', borderRadius: 1 }}>
                                <Typography variant="body2" color="text.secondary">
                                    {t('cveRefresh.nextRefresh', 'Next Refresh')}
                                </Typography>
                                <Typography variant="body1">
                                    {formatDate(stats?.next_refresh_at)}
                                </Typography>
                            </Box>
                        </Grid>
                    </Grid>

                    {/* Severity breakdown */}
                    <Box sx={{ mt: 2 }}>
                        <Typography variant="subtitle2" sx={{ mb: 1 }}>
                            {t('cveRefresh.severityBreakdown', 'Severity Breakdown')}
                        </Typography>
                        <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap' }}>
                            <Chip
                                label={`${t('vulnerabilities.critical', 'Critical')}: ${stats?.severity_counts?.critical || 0}`}
                                color="error"
                                size="small"
                            />
                            <Chip
                                label={`${t('vulnerabilities.high', 'High')}: ${stats?.severity_counts?.high || 0}`}
                                sx={{ bgcolor: 'error.light', color: 'white' }}
                                size="small"
                            />
                            <Chip
                                label={`${t('vulnerabilities.medium', 'Medium')}: ${stats?.severity_counts?.medium || 0}`}
                                color="warning"
                                size="small"
                            />
                            <Chip
                                label={`${t('vulnerabilities.low', 'Low')}: ${stats?.severity_counts?.low || 0}`}
                                color="info"
                                size="small"
                            />
                        </Box>
                    </Box>

                    {/* Reload All Button */}
                    <Box sx={{ mt: 3, display: 'flex', justifyContent: 'center' }}>
                        <Button
                            variant="contained"
                            color="primary"
                            size="large"
                            startIcon={refreshing ? <CircularProgress size={20} color="inherit" /> : <RefreshIcon />}
                            onClick={() => handleRefresh()}
                            disabled={refreshing}
                            sx={{ px: 4 }}
                        >
                            {refreshing ? t('cveRefresh.reloadingAll', 'Reloading All Sources...') : t('cveRefresh.reloadAll', 'Reload All Sources')}
                        </Button>
                    </Box>
                </CardContent>
            </Card>

            {/* Settings Card */}
            <Card sx={{ mb: 3 }}>
                <CardContent>
                    <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 2 }}>
                        <Box sx={{ display: 'flex', alignItems: 'center' }}>
                            <ScheduleIcon sx={{ mr: 1, color: 'primary.main' }} />
                            <Typography variant="h6">
                                {t('cveRefresh.refreshSettings', 'Refresh Settings')}
                            </Typography>
                        </Box>
                        <Button
                            variant="contained"
                            startIcon={saving ? <CircularProgress size={16} /> : <SaveIcon />}
                            onClick={handleSaveSettings}
                            disabled={saving}
                        >
                            {t('common.save', 'Save')}
                        </Button>
                    </Box>

                    <Grid container spacing={3}>
                        <Grid size={{ xs: 12, md: 6 }}>
                            <FormControlLabel
                                control={
                                    <Switch
                                        checked={enabled}
                                        onChange={(e) => setEnabled(e.target.checked)}
                                    />
                                }
                                label={t('cveRefresh.enableAutoRefresh', 'Enable automatic refresh')}
                            />

                            <FormControl fullWidth sx={{ mt: 2 }}>
                                <InputLabel>{t('cveRefresh.refreshInterval', 'Refresh Interval')}</InputLabel>
                                <Select
                                    value={refreshInterval}
                                    label={t('cveRefresh.refreshInterval', 'Refresh Interval')}
                                    onChange={(e) => setRefreshInterval(Number(e.target.value))}
                                    disabled={!enabled}
                                >
                                    <MenuItem value={6}>{t('cveRefresh.every6Hours', 'Every 6 hours')}</MenuItem>
                                    <MenuItem value={12}>{t('cveRefresh.every12Hours', 'Every 12 hours')}</MenuItem>
                                    <MenuItem value={24}>{t('cveRefresh.everyDay', 'Every day')}</MenuItem>
                                    <MenuItem value={48}>{t('cveRefresh.every2Days', 'Every 2 days')}</MenuItem>
                                    <MenuItem value={168}>{t('cveRefresh.everyWeek', 'Every week')}</MenuItem>
                                </Select>
                            </FormControl>
                        </Grid>

                        <Grid size={{ xs: 12, md: 6 }}>
                            <Typography variant="subtitle2" sx={{ mb: 1 }}>
                                {t('cveRefresh.nvdApiKey', 'NVD API Key (optional)')}
                            </Typography>
                            <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
                                {t('cveRefresh.nvdApiKeyHelp', 'Provides higher rate limits for NVD API requests')}
                            </Typography>
                            <TextField
                                fullWidth
                                type={showApiKey ? 'text' : 'password'}
                                placeholder={settings?.has_nvd_api_key ? t('cveRefresh.apiKeyConfigured', 'API key configured') : t('cveRefresh.enterApiKey', 'Enter NVD API key')}
                                value={nvdApiKey}
                                onChange={(e) => setNvdApiKey(e.target.value)}
                                slotProps={{
                                    input: {
                                        startAdornment: (
                                            <InputAdornment position="start">
                                                <KeyIcon />
                                            </InputAdornment>
                                        ),
                                        endAdornment: (
                                            <InputAdornment position="end">
                                                <IconButton
                                                    onClick={() => setShowApiKey(!showApiKey)}
                                                    edge="end"
                                                >
                                                    {showApiKey ? <VisibilityOffIcon /> : <VisibilityIcon />}
                                                </IconButton>
                                                {settings?.has_nvd_api_key && (
                                                    <IconButton onClick={handleClearApiKey} edge="end">
                                                        <DeleteIcon />
                                                    </IconButton>
                                                )}
                                            </InputAdornment>
                                        ),
                                    },
                                }}
                            />
                        </Grid>
                    </Grid>
                </CardContent>
            </Card>

            {/* Data Sources Card */}
            <Card sx={{ mb: 3 }}>
                <CardContent>
                    <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 2 }}>
                        <Box sx={{ display: 'flex', alignItems: 'center' }}>
                            <SecurityIcon sx={{ mr: 1, color: 'primary.main' }} />
                            <Typography variant="h6">
                                {t('cveRefresh.dataSources', 'CVE Data Sources')}
                            </Typography>
                        </Box>
                        <Button
                            variant="outlined"
                            startIcon={refreshing ? <CircularProgress size={16} /> : <RefreshIcon />}
                            onClick={() => handleRefresh()}
                            disabled={refreshing}
                        >
                            {refreshing ? t('cveRefresh.refreshing', 'Refreshing...') : t('cveRefresh.refreshNow', 'Refresh Now')}
                        </Button>
                    </Box>

                    <List>
                        {Object.entries(sources).map(([sourceId, sourceInfo]) => (
                            <ListItem
                                key={sourceId}
                                divider
                                secondaryAction={
                                    <Tooltip title={t('cveRefresh.refreshSource', 'Refresh from this source')}>
                                        <IconButton
                                            edge="end"
                                            onClick={() => handleRefresh(sourceId)}
                                            disabled={refreshing}
                                        >
                                            <RefreshIcon />
                                        </IconButton>
                                    </Tooltip>
                                }
                            >
                                <ListItemIcon>
                                    <Checkbox
                                        edge="start"
                                        checked={enabledSources.includes(sourceId)}
                                        onChange={() => handleSourceToggle(sourceId)}
                                    />
                                </ListItemIcon>
                                <ListItemText
                                    primary={sourceInfo.name}
                                    secondary={sourceInfo.description}
                                />
                            </ListItem>
                        ))}
                    </List>
                </CardContent>
            </Card>

            {/* Ingestion History Accordion */}
            <Accordion>
                <AccordionSummary expandIcon={<ExpandMoreIcon />}>
                    <Box sx={{ display: 'flex', alignItems: 'center' }}>
                        <HistoryIcon sx={{ mr: 1, color: 'primary.main' }} />
                        <Typography variant="h6">
                            {t('cveRefresh.ingestionHistory', 'Ingestion History')}
                        </Typography>
                    </Box>
                </AccordionSummary>
                <AccordionDetails>
                    <TableContainer component={Paper} variant="outlined">
                        <Table size="small">
                            <TableHead>
                                <TableRow>
                                    <TableCell>{t('cveRefresh.source', 'Source')}</TableCell>
                                    <TableCell>{t('cveRefresh.status', 'Status')}</TableCell>
                                    <TableCell>{t('cveRefresh.startedAt', 'Started')}</TableCell>
                                    <TableCell>{t('cveRefresh.completedAt', 'Completed')}</TableCell>
                                    <TableCell>{t('cveRefresh.processed', 'Processed')}</TableCell>
                                </TableRow>
                            </TableHead>
                            <TableBody>
                                {history.map((log) => (
                                    <TableRow key={log.id}>
                                        <TableCell>
                                            {sources[log.source]?.name || log.source}
                                        </TableCell>
                                        <TableCell>
                                            <Chip
                                                icon={getStatusIcon(log.status)}
                                                label={log.status}
                                                color={getStatusColor(log.status)}
                                                size="small"
                                            />
                                        </TableCell>
                                        <TableCell>{formatDate(log.started_at)}</TableCell>
                                        <TableCell>{formatDate(log.completed_at)}</TableCell>
                                        <TableCell>
                                            {log.vulnerabilities_processed !== undefined && (
                                                <Typography variant="body2">
                                                    {log.vulnerabilities_processed} CVEs, {log.packages_processed || 0} packages
                                                </Typography>
                                            )}
                                            {log.error_message && (
                                                <Typography variant="body2" color="error">
                                                    {log.error_message}
                                                </Typography>
                                            )}
                                        </TableCell>
                                    </TableRow>
                                ))}
                                {history.length === 0 && (
                                    <TableRow>
                                        <TableCell colSpan={5} align="center">
                                            <Typography color="text.secondary">
                                                {t('cveRefresh.noHistory', 'No ingestion history available')}
                                            </Typography>
                                        </TableCell>
                                    </TableRow>
                                )}
                            </TableBody>
                        </Table>
                    </TableContainer>
                </AccordionDetails>
            </Accordion>
        </Box>
    );
};

export default CveRefreshSettingsComponent;
