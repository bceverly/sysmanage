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