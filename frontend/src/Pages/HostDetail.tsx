import { useNavigate, useParams } from "react-router-dom";
import React, { useEffect, useState } from 'react';
import { 
    Box, 
    Card, 
    CardContent, 
    Typography, 
    Grid, 
    Chip,
    Button,
    CircularProgress,
    Paper
} from '@mui/material';
import ArrowBackIcon from '@mui/icons-material/ArrowBack';
import ComputerIcon from '@mui/icons-material/Computer';
import SecurityIcon from '@mui/icons-material/Security';
import InfoIcon from '@mui/icons-material/Info';
import MemoryIcon from '@mui/icons-material/Memory';
import StorageIcon from '@mui/icons-material/Storage';
import { useTranslation } from 'react-i18next';

import { SysManageHost, doGetHostByID } from '../Services/hosts';

const HostDetail = () => {
    const { hostId } = useParams<{ hostId: string }>();
    const [host, setHost] = useState<SysManageHost | null>(null);
    const [loading, setLoading] = useState<boolean>(true);
    const [error, setError] = useState<string | null>(null);
    const navigate = useNavigate();
    const { t } = useTranslation();

    useEffect(() => {
        if (!localStorage.getItem('bearer_token')) {
            navigate("/login");
            return;
        }

        if (!hostId) {
            setError(t('hostDetail.invalidId', 'Invalid host ID'));
            setLoading(false);
            return;
        }

        const fetchHost = async () => {
            try {
                setLoading(true);
                const hostData = await doGetHostByID(BigInt(hostId));
                setHost(hostData);
                setError(null);
            } catch (err) {
                console.error('Error fetching host:', err);
                setError(t('hostDetail.loadError', 'Failed to load host details'));
            } finally {
                setLoading(false);
            }
        };

        fetchHost();
    }, [hostId, navigate, t]);

    const formatDate = (dateString: string | undefined) => {
        if (!dateString) return t('common.notAvailable', 'N/A');
        try {
            const date = new Date(dateString);
            return date.toLocaleString();
        } catch {
            return t('common.invalidDate', 'Invalid date');
        }
    };

    const getStatusColor = (status: string) => {
        return status === 'up' ? 'success' : 'error';
    };

    const getApprovalStatusColor = (status: string) => {
        switch (status) {
            case 'approved': return 'success';
            case 'pending': return 'warning';
            case 'rejected': return 'error';
            case 'revoked': return 'error';
            default: return 'default';
        }
    };

    const formatMemorySize = (mb: number | undefined) => {
        if (!mb) return t('common.notAvailable');
        if (mb >= 1024) {
            return `${(mb / 1024).toFixed(1)} GB`;
        }
        return `${mb} MB`;
    };

    const formatCpuFrequency = (mhz: number | undefined) => {
        if (!mhz) return t('common.notAvailable');
        if (mhz >= 1000) {
            return `${(mhz / 1000).toFixed(1)} GHz`;
        }
        return `${mhz} MHz`;
    };

    if (loading) {
        return (
            <Box display="flex" justifyContent="center" alignItems="center" minHeight="400px">
                <CircularProgress />
            </Box>
        );
    }

    if (error || !host) {
        return (
            <Box>
                <Button 
                    startIcon={<ArrowBackIcon />} 
                    onClick={() => navigate('/hosts')}
                    sx={{ mb: 2 }}
                >
                    {t('common.back')}
                </Button>
                <Paper sx={{ p: 3, textAlign: 'center' }}>
                    <Typography variant="h6" color="error">
                        {error || t('hostDetail.notFound', 'Host not found')}
                    </Typography>
                </Paper>
            </Box>
        );
    }

    return (
        <Box>
            <Button 
                startIcon={<ArrowBackIcon />} 
                onClick={() => navigate('/hosts')}
                sx={{ mb: 2 }}
            >
                {t('common.back')}
            </Button>

            <Typography variant="h4" sx={{ mb: 3, display: 'flex', alignItems: 'center' }}>
                <ComputerIcon sx={{ mr: 2, fontSize: '2rem' }} />
                {host.fqdn}
            </Typography>

            <Grid container spacing={3}>
                {/* Basic Information */}
                <Grid item xs={12} md={6}>
                    <Card>
                        <CardContent>
                            <Typography variant="h6" sx={{ mb: 2, display: 'flex', alignItems: 'center' }}>
                                <InfoIcon sx={{ mr: 1 }} />
                                {t('hostDetail.basicInfo', 'Basic Information')}
                            </Typography>
                            <Grid container spacing={2}>
                                <Grid item xs={12} sm={6}>
                                    <Typography variant="body2" color="textSecondary">
                                        {t('hostDetail.hostId', 'Host ID')}
                                    </Typography>
                                    <Typography variant="body1">{host.id.toString()}</Typography>
                                </Grid>
                                <Grid item xs={12} sm={6}>
                                    <Typography variant="body2" color="textSecondary">
                                        {t('hosts.fqdn', 'FQDN')}
                                    </Typography>
                                    <Typography variant="body1">{host.fqdn}</Typography>
                                </Grid>
                                <Grid item xs={12} sm={6}>
                                    <Typography variant="body2" color="textSecondary">
                                        {t('hosts.ipv4', 'IPv4')}
                                    </Typography>
                                    <Typography variant="body1">{host.ipv4 || t('common.notAvailable')}</Typography>
                                </Grid>
                                <Grid item xs={12} sm={6}>
                                    <Typography variant="body2" color="textSecondary">
                                        {t('hosts.ipv6', 'IPv6')}
                                    </Typography>
                                    <Typography variant="body1">{host.ipv6 || t('common.notAvailable')}</Typography>
                                </Grid>
                                <Grid item xs={12} sm={6}>
                                    <Typography variant="body2" color="textSecondary">
                                        {t('hosts.status', 'Status')}
                                    </Typography>
                                    <Chip 
                                        label={host.status === 'up' ? t('hosts.up') : t('hosts.down')}
                                        color={getStatusColor(host.status)}
                                        size="small"
                                    />
                                </Grid>
                                <Grid item xs={12} sm={6}>
                                    <Typography variant="body2" color="textSecondary">
                                        {t('hostDetail.approvalStatus', 'Approval Status')}
                                    </Typography>
                                    <Chip 
                                        label={host.approval_status}
                                        color={getApprovalStatusColor(host.approval_status)}
                                        size="small"
                                    />
                                </Grid>
                                <Grid item xs={12}>
                                    <Typography variant="body2" color="textSecondary">
                                        {t('hosts.lastCheckin', 'Last Check-in')}
                                    </Typography>
                                    <Typography variant="body1">{formatDate(host.last_access)}</Typography>
                                </Grid>
                                <Grid item xs={12}>
                                    <Typography variant="body2" color="textSecondary">
                                        {t('hostDetail.active', 'Active')}
                                    </Typography>
                                    <Chip 
                                        label={host.active ? t('common.yes') : t('common.no')}
                                        color={host.active ? 'success' : 'default'}
                                        size="small"
                                    />
                                </Grid>
                            </Grid>
                        </CardContent>
                    </Card>
                </Grid>

                {/* Operating System Information */}
                <Grid item xs={12} md={6}>
                    <Card>
                        <CardContent>
                            <Typography variant="h6" sx={{ mb: 2, display: 'flex', alignItems: 'center' }}>
                                <ComputerIcon sx={{ mr: 1 }} />
                                {t('hostDetail.osInfo', 'Operating System')}
                            </Typography>
                            <Grid container spacing={2}>
                                <Grid item xs={12}>
                                    <Typography variant="body2" color="textSecondary">
                                        {t('hostDetail.platform', 'Platform')}
                                    </Typography>
                                    <Typography variant="body1">{host.platform || t('common.notAvailable')}</Typography>
                                </Grid>
                                <Grid item xs={12}>
                                    <Typography variant="body2" color="textSecondary">
                                        {t('hostDetail.platformRelease', 'Platform Release')}
                                    </Typography>
                                    <Typography variant="body1">{host.platform_release || t('common.notAvailable')}</Typography>
                                </Grid>
                                <Grid item xs={12}>
                                    <Typography variant="body2" color="textSecondary">
                                        {t('hostDetail.platformVersion', 'Platform Version')}
                                    </Typography>
                                    <Typography variant="body1" sx={{ wordBreak: 'break-word' }}>
                                        {host.platform_version || t('common.notAvailable')}
                                    </Typography>
                                </Grid>
                                <Grid item xs={12} sm={6}>
                                    <Typography variant="body2" color="textSecondary">
                                        {t('hostDetail.architecture', 'Architecture')}
                                    </Typography>
                                    <Typography variant="body1">{host.machine_architecture || t('common.notAvailable')}</Typography>
                                </Grid>
                                <Grid item xs={12} sm={6}>
                                    <Typography variant="body2" color="textSecondary">
                                        {t('hostDetail.processor', 'Processor')}
                                    </Typography>
                                    <Typography variant="body1">{host.processor || t('common.notAvailable')}</Typography>
                                </Grid>
                                <Grid item xs={12}>
                                    <Typography variant="body2" color="textSecondary">
                                        {t('hostDetail.osVersionUpdated', 'OS Info Updated')}
                                    </Typography>
                                    <Typography variant="body1">{formatDate(host.os_version_updated_at)}</Typography>
                                </Grid>
                                {host.os_details && (
                                    <Grid item xs={12}>
                                        <Typography variant="body2" color="textSecondary">
                                            {t('hostDetail.osDetails', 'Additional OS Details')}
                                        </Typography>
                                        <Box sx={{ mt: 1, p: 1, backgroundColor: 'grey.900', borderRadius: 1, overflow: 'auto' }}>
                                            <Typography variant="body2" component="pre" sx={{ fontSize: '0.75rem', whiteSpace: 'pre-wrap' }}>
                                                {host.os_details}
                                            </Typography>
                                        </Box>
                                    </Grid>
                                )}
                            </Grid>
                        </CardContent>
                    </Card>
                </Grid>

                {/* Hardware Information */}
                <Grid item xs={12}>
                    <Card>
                        <CardContent>
                            <Typography variant="h6" sx={{ mb: 2, display: 'flex', alignItems: 'center' }}>
                                <MemoryIcon sx={{ mr: 1 }} />
                                {t('hostDetail.hardwareInfo', 'Hardware Information')}
                            </Typography>
                            <Grid container spacing={3}>
                                {/* CPU Information */}
                                <Grid item xs={12} md={6}>
                                    <Typography variant="subtitle1" sx={{ mb: 1, fontWeight: 'bold' }}>
                                        {t('hostDetail.cpuInfo', 'CPU')}
                                    </Typography>
                                    <Grid container spacing={2}>
                                        <Grid item xs={12}>
                                            <Typography variant="body2" color="textSecondary">
                                                {t('hostDetail.cpuVendor', 'CPU Vendor')}
                                            </Typography>
                                            <Typography variant="body1">{host.cpu_vendor || t('common.notAvailable')}</Typography>
                                        </Grid>
                                        <Grid item xs={12}>
                                            <Typography variant="body2" color="textSecondary">
                                                {t('hostDetail.cpuModel', 'CPU Model')}
                                            </Typography>
                                            <Typography variant="body1">{host.cpu_model || t('common.notAvailable')}</Typography>
                                        </Grid>
                                        <Grid item xs={6}>
                                            <Typography variant="body2" color="textSecondary">
                                                {t('hostDetail.cpuCores', 'Cores')}
                                            </Typography>
                                            <Typography variant="body1">{host.cpu_cores || t('common.notAvailable')}</Typography>
                                        </Grid>
                                        <Grid item xs={6}>
                                            <Typography variant="body2" color="textSecondary">
                                                {t('hostDetail.cpuThreads', 'Threads')}
                                            </Typography>
                                            <Typography variant="body1">{host.cpu_threads || t('common.notAvailable')}</Typography>
                                        </Grid>
                                        <Grid item xs={12}>
                                            <Typography variant="body2" color="textSecondary">
                                                {t('hostDetail.cpuFrequency', 'Frequency')}
                                            </Typography>
                                            <Typography variant="body1">{formatCpuFrequency(host.cpu_frequency_mhz)}</Typography>
                                        </Grid>
                                    </Grid>
                                </Grid>

                                {/* Memory Information */}
                                <Grid item xs={12} md={6}>
                                    <Typography variant="subtitle1" sx={{ mb: 1, fontWeight: 'bold' }}>
                                        {t('hostDetail.memoryInfo', 'Memory')}
                                    </Typography>
                                    <Grid container spacing={2}>
                                        <Grid item xs={12}>
                                            <Typography variant="body2" color="textSecondary">
                                                {t('hostDetail.totalMemory', 'Total Memory')}
                                            </Typography>
                                            <Typography variant="body1">{formatMemorySize(host.memory_total_mb)}</Typography>
                                        </Grid>
                                    </Grid>
                                </Grid>

                                {/* Hardware Update Timestamp */}
                                <Grid item xs={12}>
                                    <Typography variant="body2" color="textSecondary">
                                        {t('hostDetail.hardwareUpdated', 'Hardware Info Updated')}
                                    </Typography>
                                    <Typography variant="body1">{formatDate(host.hardware_updated_at)}</Typography>
                                </Grid>

                                {/* Storage Details */}
                                {host.storage_details && (
                                    <Grid item xs={12}>
                                        <Typography variant="subtitle1" sx={{ mb: 1, fontWeight: 'bold', display: 'flex', alignItems: 'center' }}>
                                            <StorageIcon sx={{ mr: 1 }} />
                                            {t('hostDetail.storageDetails', 'Storage Details')}
                                        </Typography>
                                        <Box sx={{ mt: 1, p: 1, backgroundColor: 'grey.900', borderRadius: 1, overflow: 'auto' }}>
                                            <Typography variant="body2" component="pre" sx={{ fontSize: '0.75rem', whiteSpace: 'pre-wrap' }}>
                                                {host.storage_details}
                                            </Typography>
                                        </Box>
                                    </Grid>
                                )}

                                {/* Network Details */}
                                {host.network_details && (
                                    <Grid item xs={12}>
                                        <Typography variant="subtitle1" sx={{ mb: 1, fontWeight: 'bold' }}>
                                            {t('hostDetail.networkDetails', 'Network Interfaces')}
                                        </Typography>
                                        <Box sx={{ mt: 1, p: 1, backgroundColor: 'grey.900', borderRadius: 1, overflow: 'auto' }}>
                                            <Typography variant="body2" component="pre" sx={{ fontSize: '0.75rem', whiteSpace: 'pre-wrap' }}>
                                                {host.network_details}
                                            </Typography>
                                        </Box>
                                    </Grid>
                                )}

                                {/* Additional Hardware Details */}
                                {host.hardware_details && (
                                    <Grid item xs={12}>
                                        <Typography variant="subtitle1" sx={{ mb: 1, fontWeight: 'bold' }}>
                                            {t('hostDetail.additionalHardware', 'Additional Hardware Details')}
                                        </Typography>
                                        <Box sx={{ mt: 1, p: 1, backgroundColor: 'grey.900', borderRadius: 1, overflow: 'auto' }}>
                                            <Typography variant="body2" component="pre" sx={{ fontSize: '0.75rem', whiteSpace: 'pre-wrap' }}>
                                                {host.hardware_details}
                                            </Typography>
                                        </Box>
                                    </Grid>
                                )}
                            </Grid>
                        </CardContent>
                    </Card>
                </Grid>

                {/* Certificate Information */}
                <Grid item xs={12}>
                    <Card>
                        <CardContent>
                            <Typography variant="h6" sx={{ mb: 2, display: 'flex', alignItems: 'center' }}>
                                <SecurityIcon sx={{ mr: 1 }} />
                                {t('hostDetail.certificateInfo', 'Certificate Information')}
                            </Typography>
                            <Grid container spacing={2}>
                                <Grid item xs={12} sm={6}>
                                    <Typography variant="body2" color="textSecondary">
                                        {t('hostDetail.certificateSerial', 'Certificate Serial')}
                                    </Typography>
                                    <Typography variant="body1">{host.certificate_serial || t('common.notAvailable')}</Typography>
                                </Grid>
                                <Grid item xs={12} sm={6}>
                                    <Typography variant="body2" color="textSecondary">
                                        {t('hostDetail.certificateIssued', 'Certificate Issued')}
                                    </Typography>
                                    <Typography variant="body1">{formatDate(host.certificate_issued_at)}</Typography>
                                </Grid>
                                <Grid item xs={12}>
                                    <Typography variant="body2" color="textSecondary">
                                        {t('hostDetail.hasCertificate', 'Has Client Certificate')}
                                    </Typography>
                                    <Chip 
                                        label={host.client_certificate ? t('common.yes') : t('common.no')}
                                        color={host.client_certificate ? 'success' : 'default'}
                                        size="small"
                                    />
                                </Grid>
                            </Grid>
                        </CardContent>
                    </Card>
                </Grid>
            </Grid>
        </Box>
    );
};

export default HostDetail;