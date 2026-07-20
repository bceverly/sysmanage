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
    Checkbox,
    Table,
    TableBody,
    TableRow,
    TableCell,
    TableContainer,
    TableHead,
} from '@mui/material';
import AssignmentIcon from '@mui/icons-material/Assignment';
import PlayArrowIcon from '@mui/icons-material/PlayArrow';
import StopIcon from '@mui/icons-material/Stop';
import RestartAltIcon from '@mui/icons-material/RestartAlt';
import { useTranslation } from 'react-i18next';
import { SysManageHost } from '../../Services/hosts';
import { formatUTCDate } from '../../utils/dateUtils';
import { HostRole } from './hostDetailTypes';
import {
    getRoleServiceStatusLabel,
    getRoleServiceStatusColor,
} from './hostDetailHelpers';

interface HostServerRolesTabProps {
    host: SysManageHost;
    roles: HostRole[];
    rolesLoading: boolean;
    selectedRoles: string[];
    serviceControlLoading: boolean;
    canStartService: boolean;
    canStopService: boolean;
    canRestartService: boolean;
    requestRolesCollection: () => void;
    selectAllRoles: () => void;
    deselectAllRoles: () => void;
    addRoleToSelection: (roleId: string) => void;
    removeRoleFromSelection: (roleId: string) => void;
    handleServiceControl: (action: 'start' | 'stop' | 'restart') => void;
}

const HostServerRolesTab: React.FC<HostServerRolesTabProps> = ({
    host,
    roles,
    rolesLoading,
    selectedRoles,
    serviceControlLoading,
    canStartService,
    canStopService,
    canRestartService,
    requestRolesCollection,
    selectAllRoles,
    deselectAllRoles,
    addRoleToSelection,
    removeRoleFromSelection,
    handleServiceControl,
}) => {
    const { t } = useTranslation();
    return (
                <Grid container spacing={3}>
                    <Grid size={{ xs: 12 }}>
                        <Card>
                            <CardContent>
                                <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 2 }}>
                                    <Typography variant="subtitle1" sx={{ display: 'flex', alignItems: 'center', fontWeight: 'bold', fontSize: '1.1rem' }}>
                                        <AssignmentIcon sx={{ mr: 1 }} />
                                        {t('hostDetail.serverRoles', 'Server Roles')} ({roles.length})
                                    </Typography>
                                    <Box sx={{ display: 'flex', gap: 2, alignItems: 'center' }}>
                                        <Button
                                            variant="outlined"
                                            onClick={requestRolesCollection}
                                            disabled={rolesLoading || !host.active}
                                            sx={{ minWidth: 120, height: '36.5px' }}
                                        >
                                            {rolesLoading ?
                                                <CircularProgress size={20} /> :
                                                t('hostDetail.collectRoles', 'Collect')
                                            }
                                        </Button>
                                    </Box>
                                </Box>
                                {rolesLoading && (
                                    <Box sx={{ display: 'flex', justifyContent: 'center', p: 3 }}>
                                        <CircularProgress />
                                    </Box>
                                )}
                                {/* Server Roles Table */}
                                {!rolesLoading && (
                                    <TableContainer>
                                        <Table>
                                            <TableHead>
                                                <TableRow>
                                                    <TableCell padding="checkbox">
                                                        {(() => {
                                                            const rolesWithServiceCount = roles.filter(role => role.service_name && role.service_name.trim() !== '').length;
                                                            return (
                                                                <Checkbox
                                                                    indeterminate={selectedRoles.length > 0 && selectedRoles.length < rolesWithServiceCount}
                                                                    checked={rolesWithServiceCount > 0 && selectedRoles.length === rolesWithServiceCount}
                                                                    onChange={(e) => e.target.checked ? selectAllRoles() : deselectAllRoles()}
                                                                    disabled={!host.is_agent_privileged || rolesWithServiceCount === 0}
                                                                />
                                                            );
                                                        })()}
                                                    </TableCell>
                                                    <TableCell>{t('hostDetail.role', 'Role')}</TableCell>
                                                    <TableCell>{t('hostDetail.package', 'Package')}</TableCell>
                                                    <TableCell>{t('hostDetail.version', 'Version')}</TableCell>
                                                    <TableCell>{t('hostDetail.service', 'Service')}</TableCell>
                                                    <TableCell>{t('hostDetail.status', 'Status')}</TableCell>
                                                    <TableCell>{t('hostDetail.detected', 'Detected')}</TableCell>
                                                </TableRow>
                                            </TableHead>
                                            <TableBody>
                                                {roles.length === 0 ? (
                                                    <TableRow>
                                                        <TableCell colSpan={7} align="center">
                                                            <Typography variant="body2" sx={{ fontStyle: 'italic', color: 'textSecondary', py: 2 }}>
                                                                {t('hostDetail.noRolesDetected', 'No server roles detected')}
                                                            </Typography>
                                                        </TableCell>
                                                    </TableRow>
                                                ) : (
                                                    roles.map((role) => (
                                                        <TableRow key={role.id}>
                                                            <TableCell padding="checkbox">
                                                                <Checkbox
                                                                    checked={selectedRoles.includes(role.id)}
                                                                    onChange={(e) => e.target.checked ? addRoleToSelection(role.id) : removeRoleFromSelection(role.id)}
                                                                    disabled={!host.is_agent_privileged || !role.service_name || role.service_name.trim() === ''}
                                                                />
                                                            </TableCell>
                                                            <TableCell>
                                                                <Typography variant="body2" sx={{ fontWeight: 'bold' }}>
                                                                    {role.role}
                                                                </Typography>
                                                            </TableCell>
                                                            <TableCell>
                                                                <Typography variant="body2">
                                                                    {role.package_name}
                                                                </Typography>
                                                            </TableCell>
                                                            <TableCell>
                                                                <Typography variant="body2">
                                                                    {role.package_version || t('common.unknown', 'Unknown')}
                                                                </Typography>
                                                            </TableCell>
                                                            <TableCell>
                                                                <Typography variant="body2">
                                                                    {role.service_name || t('common.none', 'None')}
                                                                </Typography>
                                                            </TableCell>
                                                            <TableCell>
                                                                <Chip
                                                                    label={getRoleServiceStatusLabel(t, role.service_status)}
                                                                    color={getRoleServiceStatusColor(role.service_status)}
                                                                    size="small"
                                                                />
                                                            </TableCell>
                                                            <TableCell>
                                                                <Typography variant="body2" sx={{ color: 'textSecondary' }}>
                                                                    {formatUTCDate(role.detected_at)}
                                                                </Typography>
                                                            </TableCell>
                                                        </TableRow>
                                                    ))
                                                )}
                                            </TableBody>
                                        </Table>
                                    </TableContainer>
                                )}

                                {/* Service Control Buttons */}
                                {!rolesLoading && roles.some(role => role.service_name && role.service_name.trim() !== '') && (canStartService || canStopService || canRestartService) && (
                                    <Box sx={{ mt: 3, pt: 2, borderTop: '1px solid', borderColor: 'divider', display: 'flex', gap: 2, alignItems: 'center' }}>
                                        <Typography variant="body2" sx={{ color: 'textSecondary', mr: 2 }}>
                                            {t('hostDetail.serviceControlActions', 'Service Control Actions')}:
                                        </Typography>
                                        {canStartService && (
                                            <Button
                                                variant="contained"
                                                color="success"
                                                startIcon={<PlayArrowIcon />}
                                                onClick={() => handleServiceControl('start')}
                                                disabled={!host.is_agent_privileged || selectedRoles.length === 0 || serviceControlLoading}
                                                sx={{ minWidth: 100 }}
                                            >
                                                {serviceControlLoading ? <CircularProgress size={20} /> : t('hostDetail.start', 'Start')}
                                            </Button>
                                        )}
                                        {canStopService && (
                                            <Button
                                                variant="contained"
                                                color="error"
                                                startIcon={<StopIcon />}
                                                onClick={() => handleServiceControl('stop')}
                                                disabled={!host.is_agent_privileged || selectedRoles.length === 0 || serviceControlLoading}
                                                sx={{ minWidth: 100 }}
                                            >
                                                {serviceControlLoading ? <CircularProgress size={20} /> : t('hostDetail.stop', 'Stop')}
                                            </Button>
                                        )}
                                        {canRestartService && (
                                            <Button
                                                variant="contained"
                                                color="warning"
                                                startIcon={<RestartAltIcon />}
                                                onClick={() => handleServiceControl('restart')}
                                                disabled={!host.is_agent_privileged || selectedRoles.length === 0 || serviceControlLoading}
                                                sx={{ minWidth: 100 }}
                                            >
                                                {serviceControlLoading ? <CircularProgress size={20} /> : t('hostDetail.restart', 'Restart')}
                                            </Button>
                                        )}
                                        {!host.is_agent_privileged && (
                                            <Typography variant="caption" sx={{ color: 'warning.main', ml: 2 }}>
                                                {t('hostDetail.privilegedModeRequired', 'Privileged mode required for service control')}
                                            </Typography>
                                        )}
                                        {selectedRoles.length > 0 && (
                                            <Typography variant="caption" sx={{ color: 'primary.main', ml: 2 }}>
                                                {t('hostDetail.selectedServices', `${selectedRoles.length} service(s) selected`, { count: selectedRoles.length })}
                                            </Typography>
                                        )}
                                    </Box>
                                )}
                            </CardContent>
                        </Card>
                    </Grid>
                </Grid>    );
};

export default HostServerRolesTab;
