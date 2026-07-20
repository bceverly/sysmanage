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
    Alert,
    Checkbox,
    FormControlLabel,
    IconButton,
    Table,
    TableBody,
    TableRow,
    TableCell,
} from '@mui/material';
import VerifiedUserIcon from '@mui/icons-material/VerifiedUser';
import DeleteIcon from '@mui/icons-material/Delete';
import EditIcon from '@mui/icons-material/Edit';
import SaveIcon from '@mui/icons-material/Save';
import CancelIcon from '@mui/icons-material/Cancel';
import { useTranslation } from 'react-i18next';
import { SysManageHost, UbuntuProInfo } from '../../Services/hosts';
import { formatUTCDate } from '../../utils/dateUtils';
import {
    getServiceStatusLabel,
    getServiceStatusColor,
} from './hostDetailHelpers';

interface HostUbuntuProTabProps {
    host: SysManageHost;
    ubuntuProInfo: UbuntuProInfo;
    ubuntuProAttaching: boolean;
    ubuntuProDetaching: boolean;
    canAttachUbuntuPro: boolean;
    canDetachUbuntuPro: boolean;
    servicesEditMode: boolean;
    servicesSaving: boolean;
    servicesMessage: string;
    editedServices: { [serviceName: string]: boolean };
    handleUbuntuProAttach: () => void;
    handleUbuntuProDetach: () => void;
    handleServicesEditToggle: () => void;
    handleServicesSave: () => void;
    handleServiceToggle: (serviceName: string, enabled: boolean) => void;
    getEditedServiceLabel: (serviceName: string, serviceStatus: string) => string;
}

const HostUbuntuProTab: React.FC<HostUbuntuProTabProps> = ({
    host,
    ubuntuProInfo,
    ubuntuProAttaching,
    ubuntuProDetaching,
    canAttachUbuntuPro,
    canDetachUbuntuPro,
    servicesEditMode,
    servicesSaving,
    servicesMessage,
    editedServices,
    handleUbuntuProAttach,
    handleUbuntuProDetach,
    handleServicesEditToggle,
    handleServicesSave,
    handleServiceToggle,
    getEditedServiceLabel,
}) => {
    const { t } = useTranslation();
    return (
                <Grid container spacing={3}>
                    <Grid size={{ xs: 12 }}>
                        <Card>
                            <CardContent>
                                <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 2 }}>
                                    <Typography variant="h6" sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                                        <VerifiedUserIcon />
                                        {t('hostDetail.ubuntuProInfo', 'Ubuntu Pro Information')}
                                    </Typography>

                                    {/* Attach/Detach Button - only show if agent is privileged */}
                                    {host?.is_agent_privileged && (
                                        <Box>
                                            {ubuntuProAttaching && (
                                                <Button
                                                    variant="outlined"
                                                    color="primary"
                                                    size="small"
                                                    disabled
                                                    startIcon={<CircularProgress size={16} />}
                                                >
                                                    {t('hostDetail.ubuntuProAttaching', 'Attaching...')}
                                                </Button>
                                            )}
                                            {ubuntuProDetaching && (
                                                <Button
                                                    variant="outlined"
                                                    color="warning"
                                                    size="small"
                                                    disabled
                                                    startIcon={<CircularProgress size={16} />}
                                                >
                                                    {t('hostDetail.ubuntuProDetaching', 'Detaching...')}
                                                </Button>
                                            )}
                                            {!ubuntuProAttaching && !ubuntuProDetaching && (
                                                <>
                                                    {ubuntuProInfo.attached ? (
                                                        canDetachUbuntuPro && (
                                                            <Button
                                                                variant="outlined"
                                                                color="warning"
                                                                size="small"
                                                                onClick={handleUbuntuProDetach}
                                                                startIcon={<DeleteIcon />}
                                                            >
                                                                {t('hostDetail.ubuntuProDetach', 'Detach')}
                                                            </Button>
                                                        )
                                                    ) : (
                                                        canAttachUbuntuPro && (
                                                            <Button
                                                                variant="outlined"
                                                                color="primary"
                                                                size="small"
                                                                onClick={handleUbuntuProAttach}
                                                                startIcon={<VerifiedUserIcon />}
                                                            >
                                                                {t('hostDetail.ubuntuProAttach', 'Attach')}
                                                            </Button>
                                                        )
                                                    )}
                                                </>
                                            )}
                                        </Box>
                                    )}
                                </Box>

                                <Grid container spacing={2} sx={{ mt: 1 }}>
                                    <Grid size={{ xs: 12, md: 6 }}>
                                        <Card variant="outlined" sx={{ mb: 2 }}>
                                            <CardContent>
                                                <Typography variant="h6" gutterBottom>
                                                    {t('hostDetail.subscriptionStatus', 'Subscription Status')}
                                                </Typography>
                                                <Table size="small">
                                                    <TableBody>
                                                        <TableRow>
                                                            <TableCell variant="head" sx={{ fontWeight: 'bold', color: 'textSecondary' }}>
                                                                {t('hostDetail.attached', 'Attached')}
                                                            </TableCell>
                                                            <TableCell>
                                                                <Chip
                                                                    label={ubuntuProInfo.attached ? t('common.yes', 'Yes') : t('common.no', 'No')}
                                                                    color={ubuntuProInfo.attached ? 'success' : 'default'}
                                                                    size="small"
                                                                />
                                                            </TableCell>
                                                        </TableRow>
                                                        {ubuntuProInfo.version && (
                                                            <TableRow>
                                                                <TableCell variant="head" sx={{ fontWeight: 'bold', color: 'textSecondary' }}>
                                                                    {t('hostDetail.version', 'Version')}
                                                                </TableCell>
                                                                <TableCell>{ubuntuProInfo.version}</TableCell>
                                                            </TableRow>
                                                        )}
                                                        {ubuntuProInfo.expires && (
                                                            <TableRow>
                                                                <TableCell variant="head" sx={{ fontWeight: 'bold', color: 'textSecondary' }}>
                                                                    {t('hostDetail.expires', 'Expires')}
                                                                </TableCell>
                                                                <TableCell>{formatUTCDate(ubuntuProInfo.expires)}</TableCell>
                                                            </TableRow>
                                                        )}
                                                        {ubuntuProInfo.account_name && (
                                                            <TableRow>
                                                                <TableCell variant="head" sx={{ fontWeight: 'bold', color: 'textSecondary' }}>
                                                                    {t('hostDetail.accountName', 'Account Name')}
                                                                </TableCell>
                                                                <TableCell>{ubuntuProInfo.account_name}</TableCell>
                                                            </TableRow>
                                                        )}
                                                        {ubuntuProInfo.contract_name && (
                                                            <TableRow>
                                                                <TableCell variant="head" sx={{ fontWeight: 'bold', color: 'textSecondary' }}>
                                                                    {t('hostDetail.contractName', 'Contract Name')}
                                                                </TableCell>
                                                                <TableCell>{ubuntuProInfo.contract_name}</TableCell>
                                                            </TableRow>
                                                        )}
                                                        {ubuntuProInfo.tech_support_level && (
                                                            <TableRow>
                                                                <TableCell variant="head" sx={{ fontWeight: 'bold', color: 'textSecondary' }}>
                                                                    {t('hostDetail.techSupportLevel', 'Tech Support Level')}
                                                                </TableCell>
                                                                <TableCell>{ubuntuProInfo.tech_support_level}</TableCell>
                                                            </TableRow>
                                                        )}
                                                    </TableBody>
                                                </Table>
                                            </CardContent>
                                        </Card>
                                    </Grid>

                                    <Grid size={{ xs: 12, md: 6 }}>
                                        <Card variant="outlined">
                                            <CardContent>
                                                <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 1 }}>
                                                    <Typography variant="h6">
                                                        {t('hostDetail.services', 'Services')}
                                                    </Typography>
                                                    <Box sx={{ display: 'flex', gap: 1 }}>
                                                        {servicesEditMode ? (
                                                            <>
                                                                <Button
                                                                    size="small"
                                                                    variant="contained"
                                                                    color="primary"
                                                                    onClick={handleServicesSave}
                                                                    disabled={servicesSaving || !host?.is_agent_privileged}
                                                                    startIcon={servicesSaving ? <CircularProgress size={16} /> : <SaveIcon />}
                                                                >
                                                                    {t('common.save', 'Save')}
                                                                </Button>
                                                                <Button
                                                                    size="small"
                                                                    variant="outlined"
                                                                    onClick={handleServicesEditToggle}
                                                                    disabled={servicesSaving}
                                                                    startIcon={<CancelIcon />}
                                                                >
                                                                    {t('common.cancel', 'Cancel')}
                                                                </Button>
                                                            </>
                                                        ) : (
                                                            host?.is_agent_privileged && ubuntuProInfo.attached && (
                                                                <IconButton
                                                                    size="small"
                                                                    onClick={handleServicesEditToggle}
                                                                    title={t('hostDetail.editServices', 'Edit services')}
                                                                >
                                                                    <EditIcon />
                                                                </IconButton>
                                                            )
                                                        )}
                                                    </Box>
                                                </Box>
                                                {servicesMessage && (
                                                    <Alert severity="info" sx={{ mb: 2 }}>
                                                        {servicesMessage}
                                                    </Alert>
                                                )}
                                                {ubuntuProInfo.services.length > 0 ? (
                                                    <Grid container spacing={1}>
                                                        {(() => {
                                                            const sortedServices = [...ubuntuProInfo.services].sort((a, b) => {
                                                                // Sort: enabled first, then disabled, then n/a
                                                                const statusOrder = { 'enabled': 0, 'disabled': 1, 'n/a': 2 };
                                                                return statusOrder[a.status as keyof typeof statusOrder] - statusOrder[b.status as keyof typeof statusOrder];
                                                            });
                                                            return sortedServices.map((service) => (
                                                            <Grid size={{ xs: 12 }} key={service.name}>
                                                                <Card variant="outlined" sx={{ p: 1 }}>
                                                                    <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                                                                        <Box sx={{ flex: 1 }}>
                                                                            <Typography variant="subtitle2" sx={{ fontWeight: 'bold' }}>
                                                                                {service.name}
                                                                            </Typography>
                                                                            {service.description && (
                                                                                <Typography variant="caption" color="textSecondary">
                                                                                    {service.description}
                                                                                </Typography>
                                                                            )}
                                                                        </Box>
                                                                        <Box sx={{ display: 'flex', gap: 1, alignItems: 'center' }}>
                                                                            {servicesEditMode && service.status !== 'n/a' ? (
                                                                                <FormControlLabel
                                                                                    control={
                                                                                        <Checkbox
                                                                                            checked={editedServices[service.name] ?? (service.status === 'enabled')}
                                                                                            onChange={(e) => handleServiceToggle(service.name, e.target.checked)}
                                                                                            size="small"
                                                                                        />
                                                                                    }
                                                                                    label={getEditedServiceLabel(service.name, service.status)}
                                                                                />
                                                                            ) : (
                                                                                <Chip
                                                                                    label={getServiceStatusLabel(t, service.status)}
                                                                                    color={getServiceStatusColor(service.status)}
                                                                                    size="small"
                                                                                />
                                                                            )}
                                                                            {service.entitled && (
                                                                                <Chip
                                                                                    label={t('hostDetail.entitled', 'Entitled')}
                                                                                    color="primary"
                                                                                    size="small"
                                                                                />
                                                                            )}
                                                                        </Box>
                                                                    </Box>
                                                                </Card>
                                                            </Grid>
                                                        ));
                                                        })()}
                                                    </Grid>
                                                ) : (
                                                    <Typography variant="body2" color="textSecondary" sx={{ fontStyle: 'italic' }}>
                                                        {t('hostDetail.noServices', 'No services available')}
                                                    </Typography>
                                                )}
                                            </CardContent>
                                        </Card>
                                    </Grid>
                                </Grid>
                            </CardContent>
                        </Card>
                    </Grid>

                    {/* Kernel Livepatch detail (only when livepatch is enabled) */}
                    {ubuntuProInfo.livepatch?.enabled && (
                        <Grid size={{ xs: 12 }}>
                            <Card>
                                <CardContent>
                                    <Typography variant="h6" gutterBottom sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                                        <VerifiedUserIcon />
                                        {t('hostDetail.livepatchTitle', 'Kernel Livepatch')}
                                    </Typography>
                                    <Table size="small">
                                        <TableBody>
                                            <TableRow>
                                                <TableCell variant="head" sx={{ fontWeight: 'bold', color: 'textSecondary' }}>
                                                    {t('hostDetail.livepatchState', 'Patch Status')}
                                                </TableCell>
                                                <TableCell>
                                                    <Chip
                                                        size="small"
                                                        label={ubuntuProInfo.livepatch.patch_state || t('common.unknown', 'Unknown')}
                                                        color={
                                                            (
                                                                {
                                                                    applied: 'success',
                                                                    'nothing-to-apply': 'default',
                                                                } as Record<string, 'success' | 'default'>
                                                            )[ubuntuProInfo.livepatch.patch_state ?? ''] ?? 'warning'
                                                        }
                                                    />
                                                </TableCell>
                                            </TableRow>
                                            <TableRow>
                                                <TableCell variant="head" sx={{ fontWeight: 'bold', color: 'textSecondary' }}>
                                                    {t('hostDetail.livepatchKernel', 'Patched Kernel')}
                                                </TableCell>
                                                <TableCell>{ubuntuProInfo.livepatch.kernel || '—'}</TableCell>
                                            </TableRow>
                                            <TableRow>
                                                <TableCell variant="head" sx={{ fontWeight: 'bold', color: 'textSecondary' }}>
                                                    {t('hostDetail.livepatchPatchVersion', 'Patch Version')}
                                                </TableCell>
                                                <TableCell>{ubuntuProInfo.livepatch.patch_version || '—'}</TableCell>
                                            </TableRow>
                                            <TableRow>
                                                <TableCell variant="head" sx={{ fontWeight: 'bold', color: 'textSecondary' }}>
                                                    {t('hostDetail.livepatchClientVersion', 'Client Version')}
                                                </TableCell>
                                                <TableCell>{ubuntuProInfo.livepatch.client_version || '—'}</TableCell>
                                            </TableRow>
                                            <TableRow>
                                                <TableCell variant="head" sx={{ fontWeight: 'bold', color: 'textSecondary' }}>
                                                    {t('hostDetail.livepatchLastCheck', 'Last Check-in')}
                                                </TableCell>
                                                <TableCell>
                                                    {ubuntuProInfo.livepatch.last_check
                                                        ? new Date(ubuntuProInfo.livepatch.last_check).toLocaleString()
                                                        : '—'}
                                                </TableCell>
                                            </TableRow>
                                        </TableBody>
                                    </Table>
                                    {ubuntuProInfo.livepatch.fixes && ubuntuProInfo.livepatch.fixes.length > 0 && (
                                        <Box sx={{ mt: 2 }}>
                                            <Typography variant="subtitle2" gutterBottom>
                                                {t('hostDetail.livepatchFixes', 'Applied Fixes')}
                                            </Typography>
                                            <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.5 }}>
                                                {ubuntuProInfo.livepatch.fixes.map((fix) => (
                                                    <Chip key={fix} size="small" variant="outlined" label={fix} />
                                                ))}
                                            </Box>
                                        </Box>
                                    )}
                                </CardContent>
                            </Card>
                        </Grid>
                    )}
                </Grid>    );
};

export default HostUbuntuProTab;
