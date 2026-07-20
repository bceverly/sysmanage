// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

import React from 'react';
import {
    Box,
    Card,
    CardContent,
    Typography,
    Grid,
    Chip,
    Button,
    CircularProgress,
    TextField,
    InputAdornment,
    Pagination,
} from '@mui/material';
import AppsIcon from '@mui/icons-material/Apps';
import AddIcon from '@mui/icons-material/Add';
import SystemUpdateAltIcon from '@mui/icons-material/SystemUpdateAlt';
import SearchIcon from '@mui/icons-material/Search';
import { useTranslation } from 'react-i18next';
import { SysManageHost, SoftwarePackage, PaginationInfo } from '../../Services/hosts';
import {
    formatTimestamp,
    formatDate,
    formatBytesWithCommas,
} from './hostDetailHelpers';

interface HostSoftwareTabProps {
    host: SysManageHost;
    licenseModules: string[];
    softwarePackages: SoftwarePackage[];
    softwarePagination: PaginationInfo;
    setSoftwarePagination: React.Dispatch<React.SetStateAction<PaginationInfo>>;
    softwareSearchTerm: string;
    setSoftwareSearchTerm: (value: string) => void;
    loadingSoftware: boolean;
    canAddPackage: boolean;
    setPackageInstallDialogOpen: (value: boolean) => void;
    canDeployOpenTelemetry: boolean;
    openTelemetryEligible: boolean;
    openTelemetryDeploying: boolean;
    handleDeployOpenTelemetry: () => void;
    canAttachGraylog: boolean;
    graylogEligible: boolean;
    graylogAttached: boolean;
    handleAttachToGraylog: () => void;
    handleUninstallPackage: (pkg: SoftwarePackage) => void;
}

const HostSoftwareTab: React.FC<HostSoftwareTabProps> = ({
    host,
    licenseModules,
    softwarePackages,
    softwarePagination,
    setSoftwarePagination,
    softwareSearchTerm,
    setSoftwareSearchTerm,
    loadingSoftware,
    canAddPackage,
    setPackageInstallDialogOpen,
    canDeployOpenTelemetry,
    openTelemetryEligible,
    openTelemetryDeploying,
    handleDeployOpenTelemetry,
    canAttachGraylog,
    graylogEligible,
    graylogAttached,
    handleAttachToGraylog,
    handleUninstallPackage,
}) => {
    const { t, i18n } = useTranslation();
    return (
                <Grid container spacing={3}>
                    <Grid size={{ xs: 12 }}>
                        <Card>
                            <CardContent>
                                <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 2 }}>
                                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
                                        <Typography variant="subtitle1" sx={{ display: 'flex', alignItems: 'center', fontWeight: 'bold', fontSize: '1.1rem' }}>
                                            <AppsIcon sx={{ mr: 1 }} />
                                            {t('hostDetail.softwarePackages', 'Software Packages')} ({softwarePagination.total_items})
                                        </Typography>
                                        <Typography variant="caption" color="textSecondary">
                                            {t('hosts.updated', 'Updated')}: {formatTimestamp(t, host.software_updated_at)}
                                        </Typography>
                                    </Box>
                                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
                                        {canAddPackage && (
                                            <Button
                                                variant="contained"
                                                startIcon={<AddIcon />}
                                                sx={{
                                                    backgroundColor: 'primary.main',
                                                    '&:hover': { backgroundColor: 'primary.dark' },
                                                    height: '40px', // Match ToggleButtonGroup height for small size
                                                    minHeight: '40px'
                                                }}
                                                onClick={() => setPackageInstallDialogOpen(true)}
                                            >
                                                {t('hostDetail.addPackage', 'Add Package')}
                                            </Button>
                                        )}
                                        {canDeployOpenTelemetry && licenseModules.includes('observability_engine') && (
                                            <Button
                                                variant="contained"
                                                startIcon={openTelemetryDeploying ? <CircularProgress size={20} color="inherit" /> : <SystemUpdateAltIcon />}
                                                disabled={!openTelemetryEligible || openTelemetryDeploying}
                                                sx={{
                                                    backgroundColor: 'success.main',
                                                    '&:hover': { backgroundColor: 'success.dark' },
                                                    height: '40px', // Match ToggleButtonGroup height for small size
                                                    minHeight: '40px'
                                                }}
                                                onClick={handleDeployOpenTelemetry}
                                            >
                                                {t('hostDetail.deployOpenTelemetry', 'Deploy OpenTelemetry')}
                                            </Button>
                                        )}
                                        {canAttachGraylog && licenseModules.includes('observability_engine') && (
                                            <Button
                                                variant="contained"
                                                startIcon={<SystemUpdateAltIcon />}
                                                disabled={!graylogEligible || graylogAttached}
                                                sx={{
                                                    backgroundColor: 'info.main',
                                                    '&:hover': { backgroundColor: 'info.dark' },
                                                    height: '40px',
                                                    minHeight: '40px'
                                                }}
                                                onClick={handleAttachToGraylog}
                                            >
                                                {t('hostDetail.attachToGraylog', 'Attach To Graylog')}
                                            </Button>
                                        )}
                                    </Box>
                                </Box>
                                <Box sx={{ mb: 2 }}>
                                    <TextField
                                        fullWidth
                                        variant="outlined"
                                        placeholder={t('hostDetail.searchSoftware', 'Search by package name or description...')}
                                        value={softwareSearchTerm}
                                        onChange={(e) => {
                                            setSoftwareSearchTerm(e.target.value);
                                            setSoftwarePagination(prev => ({ ...prev, page: 1 })); // Reset to page 1 on search
                                        }}
                                        slotProps={{
                                            input: {
                                                startAdornment: (
                                                    <InputAdornment position="start">
                                                        <SearchIcon />
                                                    </InputAdornment>
                                                ),
                                            },
                                        }}
                                        size="small"
                                    />
                                </Box>
                                {(() => {
                                    if (loadingSoftware) {
                                        return (
                                            <Box sx={{ display: 'flex', justifyContent: 'center', alignItems: 'center', py: 4 }}>
                                                <CircularProgress />
                                                <Typography variant="body2" color="textSecondary" sx={{ ml: 2 }}>
                                                    {t('hostDetail.loadingSoftware', 'Loading software packages...')}
                                                </Typography>
                                            </Box>
                                        );
                                    }
                                    if (softwarePackages.length === 0) {
                                        return (
                                            <Typography variant="body2" color="textSecondary" sx={{ fontStyle: 'italic', textAlign: 'center', py: 2 }}>
                                                {t('hostDetail.noSoftwareFound', 'No software packages found')}
                                            </Typography>
                                        );
                                    }
                                    return (
                                        <>
                                            <Typography variant="body2" color="textSecondary" sx={{ mb: 2 }}>
                                                {t('hostDetail.showingPackages', 'Showing {{start}}-{{end}} of {{total}} packages', {
                                                    start: ((softwarePagination.page - 1) * softwarePagination.page_size + 1).toLocaleString(i18n.language),
                                                    end: Math.min(softwarePagination.page * softwarePagination.page_size, softwarePagination.total_items).toLocaleString(i18n.language),
                                                    total: softwarePagination.total_items.toLocaleString(i18n.language)
                                                })}
                                            </Typography>
                                            <Grid container spacing={2}>
                                                {softwarePackages.map((pkg: SoftwarePackage, index: number) => (
                                                <Grid size={{ xs: 12, sm: 6, md: 4 }} key={pkg.id || index}>
                                                    <Card sx={{ backgroundColor: 'grey.900', height: '100%' }}>
                                                        <CardContent sx={{ p: 2 }}>
                                                            <Typography variant="subtitle2" sx={{ fontWeight: 'bold', mb: 1, wordBreak: 'break-word' }}>
                                                                {pkg.package_name || t('common.unknown', 'Unknown')}
                                                            </Typography>
                                                            {pkg.version && (
                                                                <Typography variant="body2" color="textSecondary" sx={{ mb: 0.5 }}>
                                                                    {t('hostDetail.version', 'Version')}: {pkg.version}
                                                                </Typography>
                                                            )}
                                                            {pkg.package_manager && (
                                                                <Chip
                                                                    label={pkg.package_manager}
                                                                    color="primary"
                                                                    size="small"
                                                                    sx={{ mb: 1 }}
                                                                />
                                                            )}
                                                            {pkg.description && (
                                                                <Typography variant="body2" color="textSecondary" sx={{
                                                                    fontSize: '0.75rem',
                                                                    mt: 1,
                                                                    overflow: 'hidden',
                                                                    textOverflow: 'ellipsis',
                                                                    display: '-webkit-box',
                                                                    WebkitLineClamp: 3,
                                                                    WebkitBoxOrient: 'vertical'
                                                                }}>
                                                                    {pkg.description}
                                                                </Typography>
                                                            )}
                                                            {(pkg.size_bytes || pkg.install_date || pkg.vendor) && (
                                                                <Box sx={{ mt: 1, pt: 1, borderTop: '1px solid', borderColor: 'grey.700' }}>
                                                                    {pkg.size_bytes && (
                                                                        <Typography variant="body2" color="textSecondary" sx={{ fontSize: '0.7rem' }}>
                                                                            {t('hostDetail.size', 'Size')}: {formatBytesWithCommas(t, pkg.size_bytes)}
                                                                        </Typography>
                                                                    )}
                                                                    {pkg.install_date && (
                                                                        <Typography variant="body2" color="textSecondary" sx={{ fontSize: '0.7rem' }}>
                                                                            {t('hostDetail.installed', 'Installed')}: {formatDate(t, pkg.install_date)}
                                                                        </Typography>
                                                                    )}
                                                                    {pkg.vendor && (
                                                                        <Typography variant="body2" color="textSecondary" sx={{ fontSize: '0.7rem' }}>
                                                                            {t('hostDetail.vendor', 'Vendor')}: {pkg.vendor}
                                                                        </Typography>
                                                                    )}
                                                                </Box>
                                                            )}
                                                            <Box sx={{ mt: 2, display: 'flex', justifyContent: 'flex-end' }}>
                                                                <Button
                                                                    variant="contained"
                                                                    color="error"
                                                                    size="small"
                                                                    disabled={!host?.active || !host?.is_agent_privileged}
                                                                    onClick={() => handleUninstallPackage(pkg)}
                                                                    sx={{ minWidth: 'auto' }}
                                                                >
                                                                    {t('hostDetail.uninstall', 'Uninstall')}
                                                                </Button>
                                                            </Box>
                                                        </CardContent>
                                                    </Card>
                                                </Grid>
                                            ))}
                                        </Grid>
                                        <Box sx={{ display: 'flex', justifyContent: 'center', mt: 3 }}>
                                            <Pagination
                                                count={softwarePagination.total_pages}
                                                page={softwarePagination.page}
                                                onChange={(_, page) => {
                                                    setSoftwarePagination(prev => ({ ...prev, page }));
                                                }}
                                                color="primary"
                                                size="large"
                                                showFirstButton
                                                showLastButton
                                            />
                                        </Box>
                                    </>
                                    );
                                })()}
                            </CardContent>
                        </Card>
                    </Grid>
                </Grid>    );
};

export default HostSoftwareTab;
