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
    Paper,
    IconButton,
} from '@mui/material';
import MedicalServicesIcon from '@mui/icons-material/MedicalServices';
import RefreshIcon from '@mui/icons-material/Refresh';
import DeleteIcon from '@mui/icons-material/Delete';
import { useTranslation } from 'react-i18next';
import { SysManageHost, DiagnosticReport } from '../../Services/hosts';
import {
    formatDate,
    formatTimestamp,
} from './hostDetailHelpers';

interface HostDiagnosticsTabProps {
    host: SysManageHost;
    diagnosticsData: DiagnosticReport[];
    diagnosticsLoading: boolean;
    isDiagnosticsProcessing: boolean;
    handleRequestDiagnostics: () => void;
    handleViewDiagnosticDetail: (diagnosticId: string) => void;
    handleDeleteDiagnostic: (diagnosticId: string) => void;
}

const HostDiagnosticsTab: React.FC<HostDiagnosticsTabProps> = ({
    host,
    diagnosticsData,
    diagnosticsLoading,
    isDiagnosticsProcessing,
    handleRequestDiagnostics,
    handleViewDiagnosticDetail,
    handleDeleteDiagnostic,
}) => {
    const { t } = useTranslation();
    return (
                <Grid container spacing={3}>
                    <Grid size={{ xs: 12 }}>
                        <Card>
                            <CardContent>
                                <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 2 }}>
                                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
                                        <Typography variant="subtitle1" sx={{ display: 'flex', alignItems: 'center', fontWeight: 'bold', fontSize: '1.1rem' }}>
                                            <MedicalServicesIcon sx={{ mr: 1 }} />
                                            {t('hostDetail.diagnosticsData', 'Diagnostics Data')}
                                        </Typography>
                                        {diagnosticsData.length > 0 && !isDiagnosticsProcessing && (
                                            <Typography variant="caption" color="textSecondary">
                                                {t('hosts.updated', 'Updated')}: {formatTimestamp(t, diagnosticsData[0]?.completed_at)}
                                            </Typography>
                                        )}
                                        {isDiagnosticsProcessing && (
                                            <Chip
                                                label={t('hostDetail.processingDiagnostics', 'Processing...')}
                                                color="warning"
                                                size="small"
                                                sx={{
                                                    animation: 'pulse 1.5s ease-in-out infinite',
                                                    '@keyframes pulse': {
                                                        '0%': { opacity: 1 },
                                                        '50%': { opacity: 0.5 },
                                                        '100%': { opacity: 1 }
                                                    }
                                                }}
                                            />
                                        )}
                                        {host?.diagnostics_requested_at && host?.diagnostics_request_status !== 'pending' && (
                                            <Typography variant="caption" color="textSecondary" sx={{ ml: 1 }}>
                                                {t('hostDetail.lastRequested', 'Last requested')}: {formatTimestamp(t, host.diagnostics_requested_at)}
                                            </Typography>
                                        )}
                                    </Box>
                                    <Button
                                        variant="contained"
                                        startIcon={<RefreshIcon />}
                                        onClick={handleRequestDiagnostics}
                                        disabled={diagnosticsLoading}
                                        color="primary"
                                        data-testid="request-host-data-button"
                                    >
                                        {diagnosticsLoading
                                            ? t('hostDetail.requestingDiagnostics', 'Requesting...')
                                            : t('hostDetail.requestHostData', 'Request Host Data')
                                        }
                                    </Button>
                                </Box>

                                {diagnosticsData.length === 0 ? (
                                    <Box sx={{ textAlign: 'center', py: 4 }}>
                                        <Typography variant="body1" color="textSecondary" sx={{ mb: 2 }}>
                                            {t('hostDetail.noDiagnosticsData', 'No diagnostics data available for this host.')}
                                        </Typography>
                                        <Typography variant="body2" color="textSecondary">
                                            {t('hostDetail.clickRequestData', 'Click "Request Host Data" to collect diagnostic information from the agent.')}
                                        </Typography>
                                    </Box>
                                ) : (
                                    <Grid container spacing={2}>
                                        {diagnosticsData.map((diagnostic: DiagnosticReport, index: number) => (
                                            <Grid size={{ xs: 12 }} key={diagnostic.id || index}>
                                                <Card 
                                                    sx={{ 
                                                        backgroundColor: 'grey.900',
                                                        cursor: 'pointer',
                                                        '&:hover': {
                                                            backgroundColor: 'grey.800'
                                                        }
                                                    }}
                                                    onClick={() => handleViewDiagnosticDetail(diagnostic.id)}
                                                >
                                                    <CardContent sx={{ p: 2 }}>
                                                        <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 2 }}>
                                                            <Box>
                                                                <Typography variant="subtitle1" sx={{ fontWeight: 'bold' }}>
                                                                    {t('hostDetail.diagnosticReport', 'Diagnostic Report')} #{diagnostic.collection_id?.substring(0, 8) || t('common.unknown', 'Unknown')}
                                                                </Typography>
                                                                <Typography variant="body2" color="textSecondary">
                                                                    {t('hostDetail.collectedAt', 'Collected')}: {formatDate(t, diagnostic.completed_at)}
                                                                </Typography>
                                                            </Box>
                                                            <IconButton
                                                                size="small"
                                                                onClick={(e) => {
                                                                    e.stopPropagation();
                                                                    handleDeleteDiagnostic(diagnostic.id);
                                                                }}
                                                                sx={{ 
                                                                    ml: 2,
                                                                    color: 'white',
                                                                    '&:hover': {
                                                                        backgroundColor: 'rgba(255, 255, 255, 0.1)'
                                                                    }
                                                                }}
                                                            >
                                                                <DeleteIcon />
                                                            </IconButton>
                                                        </Box>
                                                        
                                                        {/* System Logs Section */}
                                                        {diagnostic.system_logs && (
                                                            <Box sx={{ mb: 2 }}>
                                                                <Typography variant="subtitle2" sx={{ fontWeight: 'bold', mb: 1 }}>
                                                                    {t('hostDetail.systemLogs', 'System Logs')}
                                                                </Typography>
                                                                <Paper sx={{ p: 2, backgroundColor: 'grey.800', maxHeight: 200, overflow: 'auto' }}>
                                                                    <Typography variant="body2" sx={{ fontFamily: 'monospace', whiteSpace: 'pre-wrap' }}>
                                                                        {typeof diagnostic.system_logs === 'string' 
                                                                            ? diagnostic.system_logs 
                                                                            : JSON.stringify(diagnostic.system_logs, null, 2)
                                                                        }
                                                                    </Typography>
                                                                </Paper>
                                                            </Box>
                                                        )}
                                                        
                                                        {/* Configuration Files Section */}
                                                        {diagnostic.configuration_files && (
                                                            <Box sx={{ mb: 2 }}>
                                                                <Typography variant="subtitle2" sx={{ fontWeight: 'bold', mb: 1 }}>
                                                                    {t('hostDetail.configurationFiles', 'Configuration Files')}
                                                                </Typography>
                                                                <Paper sx={{ p: 2, backgroundColor: 'grey.800', maxHeight: 200, overflow: 'auto' }}>
                                                                    <Typography variant="body2" sx={{ fontFamily: 'monospace', whiteSpace: 'pre-wrap' }}>
                                                                        {typeof diagnostic.configuration_files === 'string' 
                                                                            ? diagnostic.configuration_files 
                                                                            : JSON.stringify(diagnostic.configuration_files, null, 2)
                                                                        }
                                                                    </Typography>
                                                                </Paper>
                                                            </Box>
                                                        )}
                                                        
                                                        {/* Process List Section */}
                                                        {diagnostic.process_list && (
                                                            <Box sx={{ mb: 2 }}>
                                                                <Typography variant="subtitle2" sx={{ fontWeight: 'bold', mb: 1 }}>
                                                                    {t('hostDetail.processList', 'Process List')}
                                                                </Typography>
                                                                <Paper sx={{ p: 2, backgroundColor: 'grey.800', maxHeight: 200, overflow: 'auto' }}>
                                                                    <Typography variant="body2" sx={{ fontFamily: 'monospace', whiteSpace: 'pre-wrap' }}>
                                                                        {typeof diagnostic.process_list === 'string' 
                                                                            ? diagnostic.process_list 
                                                                            : JSON.stringify(diagnostic.process_list, null, 2)
                                                                        }
                                                                    </Typography>
                                                                </Paper>
                                                            </Box>
                                                        )}
                                                        
                                                        {/* System Information Section */}
                                                        {diagnostic.system_information && (
                                                            <Box>
                                                                <Typography variant="subtitle2" sx={{ fontWeight: 'bold', mb: 1 }}>
                                                                    {t('hostDetail.systemInformation', 'System Information')}
                                                                </Typography>
                                                                <Paper sx={{ p: 2, backgroundColor: 'grey.800', maxHeight: 200, overflow: 'auto' }}>
                                                                    <Typography variant="body2" sx={{ fontFamily: 'monospace', whiteSpace: 'pre-wrap' }}>
                                                                        {typeof diagnostic.system_information === 'string' 
                                                                            ? diagnostic.system_information 
                                                                            : JSON.stringify(diagnostic.system_information, null, 2)
                                                                        }
                                                                    </Typography>
                                                                </Paper>
                                                            </Box>
                                                        )}
                                                    </CardContent>
                                                </Card>
                                            </Grid>
                                        ))}
                                    </Grid>
                                )}
                            </CardContent>
                        </Card>
                    </Grid>
                </Grid>    );
};

export default HostDiagnosticsTab;
