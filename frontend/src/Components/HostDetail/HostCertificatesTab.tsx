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
    ToggleButton,
    ToggleButtonGroup,
} from '@mui/material';
import CertificateIcon from '@mui/icons-material/AdminPanelSettings';
import RefreshIcon from '@mui/icons-material/Refresh';
import AddIcon from '@mui/icons-material/Add';
import SearchIcon from '@mui/icons-material/Search';
import { DataGrid, GridColDef, GridColumnVisibilityModel } from '@mui/x-data-grid';
import { useTranslation } from 'react-i18next';
import ColumnVisibilityButton from '../ColumnVisibilityButton';
import { SysManageHost } from '../../Services/hosts';
import { Certificate } from './hostDetailTypes';
import { parseUTCTimestamp } from '../../utils/dateUtils';

interface HostCertificatesTabProps {
    host: SysManageHost;
    licenseModules: string[];
    certificates: Certificate[];
    certificatesLoading: boolean;
    certificateFilter: 'all' | 'ca' | 'server' | 'client';
    setCertificateFilter: (value: 'all' | 'ca' | 'server' | 'client') => void;
    certificateSearchTerm: string;
    setCertificateSearchTerm: (value: string) => void;
    certificatePaginationModel: { page: number; pageSize: number };
    setCertificatePaginationModel: React.Dispatch<React.SetStateAction<{ page: number; pageSize: number }>>;
    safePageSizeOptions: number[];
    canDeployCertificate: boolean;
    setAddCertificateDialogOpen: (value: boolean) => void;
    loadAvailableCertificates: () => void;
    requestCertificatesCollection: () => void;
    hiddenCertificatesColumns: string[];
    setHiddenCertificatesColumns: (columns: string[]) => void;
    resetCertificatesPreferences: () => void;
    getCertificatesColumnVisibilityModel: () => GridColumnVisibilityModel;
}

const HostCertificatesTab: React.FC<HostCertificatesTabProps> = ({
    host,
    licenseModules,
    certificates,
    certificatesLoading,
    certificateFilter,
    setCertificateFilter,
    certificateSearchTerm,
    setCertificateSearchTerm,
    certificatePaginationModel,
    setCertificatePaginationModel,
    safePageSizeOptions,
    canDeployCertificate,
    setAddCertificateDialogOpen,
    loadAvailableCertificates,
    requestCertificatesCollection,
    hiddenCertificatesColumns,
    setHiddenCertificatesColumns,
    resetCertificatesPreferences,
    getCertificatesColumnVisibilityModel,
}) => {
    const { t } = useTranslation();

    const certificateColumns: GridColDef[] = [
        {
            field: 'certificate_name',
            headerName: t('hostDetail.certificateName', 'Certificate Name'),
            minWidth: 200,
            flex: 1,
            renderCell: (params) => (
                <Box>
                    <Typography variant="body2" sx={{ fontWeight: 500 }}>
                        {params.value || params.row.common_name || t('common.unknown', 'Unknown')}
                    </Typography>
                    <Box sx={{ display: 'flex', gap: 0.5, mt: 0.25 }}>
                        {params.row.is_expired && (
                            <Chip
                                label={t('hostDetail.expired', 'Expired')}
                                size="small"
                                color="error"
                                sx={{
                                    fontSize: '0.7rem',
                                    height: '18px'
                                }}
                            />
                        )}
                        {!params.row.is_expired && params.row.days_until_expiry !== null && params.row.days_until_expiry <= 30 && (
                            <Chip
                                label={t('hostDetail.expiringSoon', 'Expiring Soon')}
                                size="small"
                                color="warning"
                                sx={{
                                    fontSize: '0.7rem',
                                    height: '18px'
                                }}
                            />
                        )}
                        {params.row.is_ca && (
                            <Chip
                                label="CA"
                                size="small"
                                color="primary"
                                variant="outlined"
                                sx={{
                                    fontSize: '0.7rem',
                                    height: '18px'
                                }}
                            />
                        )}
                    </Box>
                </Box>
            ),
        },
        {
            field: 'issuer',
            headerName: t('hostDetail.issuer', 'Issuer'),
            minWidth: 250,
            flex: 1,
            renderCell: (params) => (
                <Typography
                    variant="body2"
                    sx={{
                        whiteSpace: 'nowrap',
                        overflow: 'hidden',
                        textOverflow: 'ellipsis',
                    }}
                    title={params.value}
                >
                    {params.value}
                </Typography>
            ),
        },
        {
            field: 'not_after',
            headerName: t('hostDetail.expiryDate', 'Expiry Date'),
            minWidth: 130,
            renderCell: (params) => {
                if (!params.value) return t('common.unknown', 'Unknown');

                const expiryDate = parseUTCTimestamp(params.value);
                const isExpired = params.row.is_expired;
                const daysUntilExpiry = params.row.days_until_expiry;

                let expiryColor: string;
                if (isExpired) {
                    expiryColor = 'error.main';
                } else if (daysUntilExpiry !== null && daysUntilExpiry <= 30) {
                    expiryColor = 'warning.main';
                } else {
                    expiryColor = 'text.primary';
                }

                return (
                    <Box>
                        <Typography
                            variant="body2"
                            sx={{
                                color: expiryColor
                            }}
                        >
                            {expiryDate ? expiryDate.toLocaleDateString() : t('common.unknown', 'Unknown')}
                        </Typography>
                        {daysUntilExpiry !== null && (
                            <Typography variant="caption" sx={{ display: 'block', lineHeight: 1 }}>
                                {isExpired ?
                                    t('hostDetail.expired', 'Expired') :
                                    t('hostDetail.daysUntilExpiry', '{{days}} days', { days: daysUntilExpiry })
                                }
                            </Typography>
                        )}
                    </Box>
                );
            },
        },
        {
            field: 'file_path',
            headerName: t('hostDetail.location', 'Location'),
            minWidth: 300,
            flex: 1,
            renderCell: (params) => (
                <Typography
                    variant="body2"
                    sx={{
                        fontFamily: 'monospace',
                        fontSize: '0.85rem',
                        whiteSpace: 'nowrap',
                        overflow: 'hidden',
                        textOverflow: 'ellipsis',
                    }}
                    title={params.value}
                >
                    {params.value}
                </Typography>
            ),
        },
        {
            field: 'serial_number',
            headerName: t('hostDetail.serialNumber', 'Serial'),
            minWidth: 120,
            renderCell: (params) => (
                <Typography
                    variant="body2"
                    sx={{
                        fontFamily: 'monospace',
                        fontSize: '0.8rem',
                        whiteSpace: 'nowrap',
                        overflow: 'hidden',
                        textOverflow: 'ellipsis',
                    }}
                    title={params.value}
                >
                    {params.value}
                </Typography>
            ),
        },
    ];
    return (
                <Grid container spacing={3}>
                    <Grid size={{ xs: 12 }}>
                        <Card>
                            <CardContent>
                                <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 2 }}>
                                    <Typography variant="subtitle1" sx={{ display: 'flex', alignItems: 'center', fontWeight: 'bold', fontSize: '1.1rem' }}>
                                        <CertificateIcon sx={{ mr: 1 }} />
                                        {t('hostDetail.certificates', 'SSL Certificates')} ({certificates.length})
                                    </Typography>
                                    <Box sx={{ display: 'flex', gap: 4, alignItems: 'center' }}>
                                        <TextField
                                            size="small"
                                            placeholder={t('hostDetail.searchCertificates', 'Search certificates...')}
                                            value={certificateSearchTerm}
                                            onChange={(e) => {
                                                setCertificateSearchTerm(e.target.value);
                                                setCertificatePaginationModel({ page: 0, pageSize: certificatePaginationModel.pageSize });
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
                                            sx={{ width: 350 }}
                                        />
                                        <ToggleButtonGroup
                                            value={certificateFilter}
                                            exclusive
                                            onChange={(_, newFilter) => {
                                                if (newFilter !== null) {
                                                    setCertificateFilter(newFilter);
                                                    setCertificatePaginationModel({ page: 0, pageSize: certificatePaginationModel.pageSize });
                                                }
                                            }}
                                            size="small"
                                            sx={{ height: '36.5px' }}
                                        >
                                            <ToggleButton value="server" sx={{ px: 2 }}>
                                                {t('hostDetail.server', 'Server')}
                                            </ToggleButton>
                                            <ToggleButton value="client" sx={{ px: 2 }}>
                                                {t('hostDetail.client', 'Client')}
                                            </ToggleButton>
                                            <ToggleButton value="ca" sx={{ px: 2 }}>
                                                CA
                                            </ToggleButton>
                                            <ToggleButton value="all" sx={{ px: 2 }}>
                                                {t('common.all', 'All')}
                                            </ToggleButton>
                                        </ToggleButtonGroup>
                                        {canDeployCertificate && licenseModules.includes('secrets_engine') && (
                                            <Button
                                                variant="outlined"
                                                startIcon={<AddIcon />}
                                                onClick={() => {
                                                    setAddCertificateDialogOpen(true);
                                                    loadAvailableCertificates();
                                                }}
                                                disabled={!host.active || !host.is_agent_privileged}
                                                sx={{ minWidth: 100, height: '36.5px' }}
                                            >
                                                {t('hostDetail.addCertificate', 'Add')}
                                            </Button>
                                        )}
                                        <Button
                                            variant="outlined"
                                            startIcon={<RefreshIcon />}
                                            onClick={requestCertificatesCollection}
                                            disabled={certificatesLoading || !host.active}
                                            sx={{ minWidth: 120, height: '36.5px' }}
                                        >
                                            {certificatesLoading ?
                                                <CircularProgress size={20} /> :
                                                t('hostDetail.collectCertificates', 'Collect')
                                            }
                                        </Button>
                                    </Box>
                                </Box>

                                {/* Certificates will be implemented in the next step */}
                                {certificatesLoading && (
                                    <Box sx={{ display: 'flex', justifyContent: 'center', p: 3 }}>
                                        <CircularProgress />
                                    </Box>
                                )}

                                {/* Certificate DataGrid */}
                                {!certificatesLoading && (
                                    <>
                                        <Box sx={{ mb: 1, display: 'flex', alignItems: 'center', justifyContent: 'flex-end' }}>
                                            <ColumnVisibilityButton
                                                columns={certificateColumns.map(col => ({ field: col.field, headerName: col.headerName || col.field }))}
                                                hiddenColumns={hiddenCertificatesColumns}
                                                onColumnsChange={setHiddenCertificatesColumns}
                                                onReset={resetCertificatesPreferences}
                                            />
                                        </Box>
                                        <Box sx={{ height: 500 }}>
                                            <DataGrid
                                                rows={certificates.filter(cert => {
                                                    // Apply search filter first
                                                    if (certificateSearchTerm) {
                                                        const searchLower = certificateSearchTerm.toLowerCase();
                                                        const nameMatch = cert.certificate_name?.toLowerCase().includes(searchLower);
                                                        const subjectMatch = cert.subject?.toLowerCase().includes(searchLower);
                                                        const issuerMatch = cert.issuer?.toLowerCase().includes(searchLower);
                                                        if (!nameMatch && !subjectMatch && !issuerMatch) {
                                                            return false;
                                                        }
                                                    }

                                                    // Apply type filter
                                                    if (certificateFilter === 'all') return true;
                                                    if (certificateFilter === 'ca') {
                                                        return cert.is_ca || cert.key_usage === 'CA';
                                                    }
                                                    if (certificateFilter === 'server') {
                                                        return cert.key_usage === 'Server';
                                                    }
                                                    if (certificateFilter === 'client') {
                                                        return cert.key_usage === 'Client';
                                                    }
                                                    return true;
                                                })}
                                                columns={certificateColumns}
                                                loading={certificatesLoading}
                                                initialState={{
                                                    sorting: {
                                                        sortModel: [{ field: 'days_until_expiry', sort: 'asc' }],
                                                    },
                                                }}
                                                columnVisibilityModel={getCertificatesColumnVisibilityModel()}
                                                paginationModel={certificatePaginationModel}
                                                onPaginationModelChange={setCertificatePaginationModel}
                                                pageSizeOptions={safePageSizeOptions}
                                                disableRowSelectionOnClick
                                                sx={{
                                                    '& .MuiDataGrid-row': {
                                                        '&:hover': {
                                                            backgroundColor: 'action.hover',
                                                        },
                                                    },
                                                }}
                                            />
                                        </Box>
                                    </>
                                )}
                            </CardContent>
                        </Card>
                    </Grid>
                </Grid>    );
};

export default HostCertificatesTab;
