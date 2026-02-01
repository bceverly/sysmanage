import React, { useState, useEffect, useCallback } from 'react';
import {
    Box,
    Card,
    CardContent,
    Typography,
    Chip,
    Grid,
    Alert,
    CircularProgress,
    Divider,
    List,
    ListItem,
    ListItemIcon,
    ListItemText,
} from '@mui/material';
import CheckCircleIcon from '@mui/icons-material/CheckCircle';
import BusinessIcon from '@mui/icons-material/Business';
import CalendarTodayIcon from '@mui/icons-material/CalendarToday';
import ExtensionIcon from '@mui/icons-material/Extension';
import StarIcon from '@mui/icons-material/Star';
import ComputerIcon from '@mui/icons-material/Computer';
import { useTranslation } from 'react-i18next';
import { getLicenseInfo, LicenseInfo } from '../Services/license';

const ProPlusSettings: React.FC = () => {
    const { t } = useTranslation();
    const [licenseInfo, setLicenseInfo] = useState<LicenseInfo | null>(null);
    const [loading, setLoading] = useState<boolean>(true);
    const [error, setError] = useState<string | null>(null);

    const loadLicenseInfo = useCallback(async () => {
        setLoading(true);
        setError(null);
        try {
            const info = await getLicenseInfo();
            setLicenseInfo(info);
        } catch (err) {
            console.error('Error loading license info:', err);
            setError(t('proPlus.loadError', 'Failed to load license information'));
        } finally {
            setLoading(false);
        }
    }, [t]);

    useEffect(() => {
        loadLicenseInfo();
    }, [loadLicenseInfo]);

    if (loading) {
        return (
            <Box sx={{ display: 'flex', justifyContent: 'center', p: 4 }}>
                <CircularProgress />
            </Box>
        );
    }

    if (error) {
        return (
            <Alert severity="error" sx={{ mb: 2 }}>
                {error}
            </Alert>
        );
    }

    if (!licenseInfo?.active) {
        return (
            <Alert severity="info">
                {t('proPlus.notActive', 'Sysmanage Professional+ is not active. Contact sales for licensing information.')}
            </Alert>
        );
    }

    // Format expiration date
    const expiresAt = licenseInfo.expires_at
        ? new Date(licenseInfo.expires_at).toLocaleDateString(undefined, {
            year: 'numeric',
            month: 'long',
            day: 'numeric'
          })
        : t('common.unknown', 'Unknown');

    // Calculate days until expiration
    const daysUntilExpiry = licenseInfo.expires_at
        ? Math.ceil((new Date(licenseInfo.expires_at).getTime() - Date.now()) / (1000 * 60 * 60 * 24))
        : null;

    // Determine expiry warning level
    const getExpiryColor = () => {
        if (daysUntilExpiry === null) return 'default';
        if (daysUntilExpiry <= 0) return 'error';
        if (daysUntilExpiry <= 30) return 'warning';
        return 'success';
    };

    // Get tier display name
    const getTierDisplayName = (tier: string) => {
        switch (tier?.toLowerCase()) {
            case 'enterprise':
                return t('proPlus.tierEnterprise', 'Enterprise');
            case 'professional':
                return t('proPlus.tierProfessional', 'Professional');
            default:
                return tier || t('common.unknown', 'Unknown');
        }
    };

    // Get feature display name
    const getFeatureDisplayName = (feature: string) => {
        const featureNames: Record<string, string> = {
            'health': t('proPlus.featureHealth', 'Health Analysis'),
            'vuln': t('proPlus.featureVuln', 'Vulnerability Scanning'),
            'compliance': t('proPlus.featureCompliance', 'Compliance Checking'),
            'alerts': t('proPlus.featureAlerts', 'Advanced Alerting'),
            'reports': t('proPlus.featureReports', 'Custom Reports'),
            'api': t('proPlus.featureApi', 'API Access'),
            'multiuser': t('proPlus.featureMultiuser', 'Multi-user Support'),
            'sso': t('proPlus.featureSso', 'Single Sign-On'),
            'rbac': t('proPlus.featureRbac', 'Role-based Access Control'),
            'audit': t('proPlus.featureAudit', 'Advanced Audit Logging'),
            'ha': t('proPlus.featureHa', 'High Availability'),
            'cluster': t('proPlus.featureCluster', 'Multi-cluster Management'),
            'whitelabel': t('proPlus.featureWhitelabel', 'White-labeling'),
            'priority': t('proPlus.featurePriority', 'Priority Support'),
        };
        return featureNames[feature] || feature;
    };

    // Get module display name
    const getModuleDisplayName = (module: string) => {
        const moduleNames: Record<string, string> = {
            'health_engine': t('proPlus.moduleHealthEngine', 'Health Analysis Engine'),
            'vuln_engine': t('proPlus.moduleVulnEngine', 'Vulnerability Engine'),
            'compliance_engine': t('proPlus.moduleComplianceEngine', 'Compliance Engine'),
            'report_engine': t('proPlus.moduleReportEngine', 'Report Engine'),
        };
        return moduleNames[module] || module;
    };

    return (
        <Box>
            {/* License Status Card */}
            <Card sx={{ mb: 3 }}>
                <CardContent>
                    <Box sx={{ display: 'flex', alignItems: 'center', mb: 2 }}>
                        <StarIcon sx={{ mr: 1, color: 'primary.main', fontSize: 28 }} />
                        <Typography variant="h6">
                            {t('proPlus.licenseStatus', 'License Status')}
                        </Typography>
                        <Chip
                            label={t('proPlus.active', 'Active')}
                            color="success"
                            size="small"
                            sx={{ ml: 2 }}
                        />
                    </Box>

                    <Grid container spacing={3}>
                        {/* Tier */}
                        <Grid size={{ xs: 12, sm: 6, md: 3 }}>
                            <Box sx={{ display: 'flex', alignItems: 'center', mb: 1 }}>
                                <StarIcon sx={{ mr: 1, color: 'text.secondary', fontSize: 20 }} />
                                <Typography variant="body2" color="text.secondary">
                                    {t('proPlus.tier', 'Tier')}
                                </Typography>
                            </Box>
                            <Typography variant="h6">
                                {getTierDisplayName(licenseInfo.tier || '')}
                            </Typography>
                        </Grid>

                        {/* Customer */}
                        <Grid size={{ xs: 12, sm: 6, md: 3 }}>
                            <Box sx={{ display: 'flex', alignItems: 'center', mb: 1 }}>
                                <BusinessIcon sx={{ mr: 1, color: 'text.secondary', fontSize: 20 }} />
                                <Typography variant="body2" color="text.secondary">
                                    {t('proPlus.customer', 'Customer')}
                                </Typography>
                            </Box>
                            <Typography variant="h6">
                                {licenseInfo.customer_name || t('common.unknown', 'Unknown')}
                            </Typography>
                        </Grid>

                        {/* Expiration */}
                        <Grid size={{ xs: 12, sm: 6, md: 3 }}>
                            <Box sx={{ display: 'flex', alignItems: 'center', mb: 1 }}>
                                <CalendarTodayIcon sx={{ mr: 1, color: 'text.secondary', fontSize: 20 }} />
                                <Typography variant="body2" color="text.secondary">
                                    {t('proPlus.expiresAt', 'Expires')}
                                </Typography>
                            </Box>
                            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                                <Typography variant="h6">
                                    {expiresAt}
                                </Typography>
                                {daysUntilExpiry !== null && (
                                    <Chip
                                        label={daysUntilExpiry <= 0
                                            ? t('proPlus.expired', 'Expired')
                                            : t('proPlus.daysRemaining', '{{days}} days', { days: daysUntilExpiry })
                                        }
                                        color={getExpiryColor()}
                                        size="small"
                                    />
                                )}
                            </Box>
                        </Grid>

                        {/* Host Limits */}
                        <Grid size={{ xs: 12, sm: 6, md: 3 }}>
                            <Box sx={{ display: 'flex', alignItems: 'center', mb: 1 }}>
                                <ComputerIcon sx={{ mr: 1, color: 'text.secondary', fontSize: 20 }} />
                                <Typography variant="body2" color="text.secondary">
                                    {t('proPlus.hostLimits', 'Host Limits')}
                                </Typography>
                            </Box>
                            <Typography variant="body1">
                                {t('proPlus.parentHosts', '{{count}} parent hosts', { count: licenseInfo.parent_hosts || 0 })}
                            </Typography>
                            <Typography variant="body1">
                                {t('proPlus.childHosts', '{{count}} child hosts', { count: licenseInfo.child_hosts || 0 })}
                            </Typography>
                        </Grid>
                    </Grid>
                </CardContent>
            </Card>

            {/* Features Card */}
            <Card sx={{ mb: 3 }}>
                <CardContent>
                    <Box sx={{ display: 'flex', alignItems: 'center', mb: 2 }}>
                        <CheckCircleIcon sx={{ mr: 1, color: 'success.main' }} />
                        <Typography variant="h6">
                            {t('proPlus.licensedFeatures', 'Licensed Features')}
                        </Typography>
                    </Box>
                    <Divider sx={{ mb: 2 }} />
                    <Grid container spacing={1}>
                        {licenseInfo.features?.map((feature) => (
                            <Grid size={{ xs: 12, sm: 6, md: 4 }} key={feature}>
                                <Box sx={{ display: 'flex', alignItems: 'center', p: 1 }}>
                                    <CheckCircleIcon sx={{ mr: 1, color: 'success.main', fontSize: 18 }} />
                                    <Typography variant="body2">
                                        {getFeatureDisplayName(feature)}
                                    </Typography>
                                </Box>
                            </Grid>
                        ))}
                    </Grid>
                </CardContent>
            </Card>

            {/* Modules Card */}
            {licenseInfo.modules && licenseInfo.modules.length > 0 && (
                <Card>
                    <CardContent>
                        <Box sx={{ display: 'flex', alignItems: 'center', mb: 2 }}>
                            <ExtensionIcon sx={{ mr: 1, color: 'primary.main' }} />
                            <Typography variant="h6">
                                {t('proPlus.licensedModules', 'Licensed Modules')}
                            </Typography>
                        </Box>
                        <Divider sx={{ mb: 2 }} />
                        <List dense>
                            {licenseInfo.modules.map((module) => (
                                <ListItem key={module}>
                                    <ListItemIcon sx={{ minWidth: 36 }}>
                                        <ExtensionIcon sx={{ color: 'primary.main', fontSize: 20 }} />
                                    </ListItemIcon>
                                    <ListItemText
                                        primary={getModuleDisplayName(module)}
                                    />
                                </ListItem>
                            ))}
                        </List>
                    </CardContent>
                </Card>
            )}
        </Box>
    );
};

export default ProPlusSettings;
