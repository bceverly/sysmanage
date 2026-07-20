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
    CircularProgress,
    IconButton,
    Table,
    TableBody,
    TableRow,
    TableCell,
    TableContainer,
    TableHead,
} from '@mui/material';
import HistoryIcon from '@mui/icons-material/History';
import VisibilityIcon from '@mui/icons-material/Visibility';
import DeleteIcon from '@mui/icons-material/Delete';
import { useTranslation } from 'react-i18next';
import { InstallationHistoryItem } from './hostDetailTypes';
import {
    formatDateTime,
    getTranslatedStatus,
    getInstallationStatusColor,
} from './hostDetailHelpers';

interface HostSoftwareChangesTabProps {
    installationHistory: InstallationHistoryItem[];
    installationHistoryLoading: boolean;
    handleViewInstallationLog: (installation: InstallationHistoryItem) => void;
    handleDeleteInstallation: (installation: InstallationHistoryItem) => void;
}

const HostSoftwareChangesTab: React.FC<HostSoftwareChangesTabProps> = ({
    installationHistory,
    installationHistoryLoading,
    handleViewInstallationLog,
    handleDeleteInstallation,
}) => {
    const { t } = useTranslation();
    return (
                <Grid container spacing={3}>
                    <Grid size={{ xs: 12 }}>
                        <Card>
                            <CardContent>
                                <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 2 }}>
                                    <Typography variant="subtitle1" sx={{ display: 'flex', alignItems: 'center', fontWeight: 'bold', fontSize: '1.1rem' }}>
                                        <HistoryIcon sx={{ mr: 1 }} />
                                        {t('hostDetail.softwareInstallationHistory', 'Software Installation History')}
                                    </Typography>
                                </Box>

                                {(() => {
                                    if (installationHistoryLoading) {
                                        return (
                                            <Box sx={{ display: 'flex', justifyContent: 'center', py: 4 }}>
                                                <CircularProgress />
                                            </Box>
                                        );
                                    }
                                    if (installationHistory.length === 0) {
                                        return (
                                            <Typography variant="body2" color="textSecondary" sx={{ textAlign: 'center', py: 4 }}>
                                                {t('hostDetail.noInstallationHistory', 'No software installation history found for this host.')}
                                            </Typography>
                                        );
                                    }
                                    return (
                                        <TableContainer>
                                            <Table>
                                                <TableHead>
                                                    <TableRow>
                                                        <TableCell>{t('hostDetail.packageNames', 'Package Names')}</TableCell>
                                                        <TableCell>{t('hostDetail.operation', 'Operation')}</TableCell>
                                                        <TableCell>{t('hostDetail.requestedBy', 'Requested By')}</TableCell>
                                                        <TableCell>{t('hostDetail.requestedAt', 'Requested At')}</TableCell>
                                                        <TableCell>{t('hostDetail.status', 'Status')}</TableCell>
                                                        <TableCell>{t('hostDetail.completedAt', 'Completed At')}</TableCell>
                                                        <TableCell>{t('hostDetail.actions', 'Actions')}</TableCell>
                                                    </TableRow>
                                                </TableHead>
                                                <TableBody>
                                                    {installationHistory.map((installation) => (
                                                        <TableRow key={installation.request_id}>
                                                            <TableCell>{installation.package_names}</TableCell>
                                                            <TableCell>
                                                                <Chip
                                                                    label={(installation.operation_type || 'install') === 'install' ? t('hostDetail.install', 'Install') : t('hostDetail.uninstall', 'Uninstall')}
                                                                    color={(installation.operation_type || 'install') === 'install' ? 'primary' : 'error'}
                                                                    size="small"
                                                                    variant="outlined"
                                                                />
                                                            </TableCell>
                                                            <TableCell>{installation.requested_by}</TableCell>
                                                            <TableCell>{formatDateTime(installation.requested_at)}</TableCell>
                                                            <TableCell>
                                                                <Chip
                                                                    label={getTranslatedStatus(t, installation.status)}
                                                                    color={getInstallationStatusColor(installation.status)}
                                                                    size="small"
                                                                />
                                                            </TableCell>
                                                            <TableCell>
                                                                {installation.completed_at ? formatDateTime(installation.completed_at) : '-'}
                                                            </TableCell>
                                                            <TableCell>
                                                                <IconButton
                                                                    size="small"
                                                                    onClick={() => handleViewInstallationLog(installation)}
                                                                    disabled={installation.status === 'pending' || installation.status === 'queued' || installation.status === 'in_progress' || installation.status === 'installing'}
                                                                    title={t('hostDetail.viewInstallationLog', 'View Installation Log')}
                                                                    sx={{ mr: 1 }}
                                                                >
                                                                    <VisibilityIcon />
                                                                </IconButton>
                                                                <IconButton
                                                                    size="small"
                                                                    onClick={() => handleDeleteInstallation(installation)}
                                                                    title={t('hostDetail.deleteInstallation', 'Delete Installation Record')}
                                                                    color="error"
                                                                >
                                                                    <DeleteIcon />
                                                                </IconButton>
                                                            </TableCell>
                                                        </TableRow>
                                                    ))}
                                                </TableBody>
                                            </Table>
                                        </TableContainer>
                                    );
                                })()}
                            </CardContent>
                        </Card>
                    </Grid>
                </Grid>    );
};

export default HostSoftwareChangesTab;
