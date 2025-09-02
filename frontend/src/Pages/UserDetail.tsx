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
import PersonIcon from '@mui/icons-material/Person';
import SecurityIcon from '@mui/icons-material/Security';
import LockIcon from '@mui/icons-material/Lock';
import LockOpenIcon from '@mui/icons-material/LockOpen';
import { useTranslation } from 'react-i18next';

import { SysManageUser, doGetUsers } from '../Services/users';

const UserDetail = () => {
    const { userId } = useParams<{ userId: string }>();
    const [user, setUser] = useState<SysManageUser | null>(null);
    const [loading, setLoading] = useState<boolean>(true);
    const [error, setError] = useState<string | null>(null);
    const navigate = useNavigate();
    const { t } = useTranslation();

    useEffect(() => {
        if (!localStorage.getItem('bearer_token')) {
            navigate("/login");
            return;
        }

        if (!userId) {
            setError(t('userDetail.invalidId', 'Invalid user ID'));
            setLoading(false);
            return;
        }

        const fetchUser = async () => {
            try {
                setLoading(true);
                // Since there's no individual user fetch endpoint, we get all users and filter
                const users = await doGetUsers();
                const foundUser = users.find(u => u.id.toString() === userId);
                
                if (foundUser) {
                    setUser(foundUser);
                    setError(null);
                } else {
                    setError(t('userDetail.notFound', 'User not found'));
                }
            } catch (err) {
                console.error('Error fetching user:', err);
                setError(t('userDetail.loadError', 'Failed to load user details'));
            } finally {
                setLoading(false);
            }
        };

        fetchUser();
    }, [userId, navigate, t]);

    const formatDate = (dateString: string | null | undefined) => {
        if (!dateString) return t('common.notAvailable', 'N/A');
        try {
            const date = new Date(dateString);
            return date.toLocaleString();
        } catch {
            return t('common.invalidDate', 'Invalid date');
        }
    };

    if (loading) {
        return (
            <Box display="flex" justifyContent="center" alignItems="center" minHeight="400px">
                <CircularProgress />
            </Box>
        );
    }

    if (error || !user) {
        return (
            <Box>
                <Button 
                    startIcon={<ArrowBackIcon />} 
                    onClick={() => navigate('/users')}
                    sx={{ mb: 2 }}
                >
                    {t('common.back')}
                </Button>
                <Paper sx={{ p: 3, textAlign: 'center' }}>
                    <Typography variant="h6" color="error">
                        {error || t('userDetail.notFound', 'User not found')}
                    </Typography>
                </Paper>
            </Box>
        );
    }

    return (
        <Box>
            <Button 
                startIcon={<ArrowBackIcon />} 
                onClick={() => navigate('/users')}
                sx={{ mb: 2 }}
            >
                {t('common.back')}
            </Button>

            <Typography variant="h4" sx={{ mb: 3, display: 'flex', alignItems: 'center' }}>
                <PersonIcon sx={{ mr: 2, fontSize: '2rem' }} />
                {user.userid}
            </Typography>

            <Grid container spacing={3}>
                {/* Basic Information */}
                <Grid item xs={12} md={6}>
                    <Card>
                        <CardContent>
                            <Typography variant="h6" sx={{ mb: 2, display: 'flex', alignItems: 'center' }}>
                                <PersonIcon sx={{ mr: 1 }} />
                                {t('userDetail.basicInfo', 'Basic Information')}
                            </Typography>
                            <Grid container spacing={2}>
                                <Grid item xs={12}>
                                    <Typography variant="body2" color="textSecondary">
                                        {t('userDetail.userId', 'User ID')}
                                    </Typography>
                                    <Typography variant="body1">{user.id.toString()}</Typography>
                                </Grid>
                                <Grid item xs={12}>
                                    <Typography variant="body2" color="textSecondary">
                                        {t('users.email', 'Email')}
                                    </Typography>
                                    <Typography variant="body1">{user.userid}</Typography>
                                </Grid>
                                <Grid item xs={12}>
                                    <Typography variant="body2" color="textSecondary">
                                        {t('userDetail.firstName', 'First Name')}
                                    </Typography>
                                    <Typography variant="body1">{user.first_name || t('common.notAvailable', 'N/A')}</Typography>
                                </Grid>
                                <Grid item xs={12}>
                                    <Typography variant="body2" color="textSecondary">
                                        {t('userDetail.lastName', 'Last Name')}
                                    </Typography>
                                    <Typography variant="body1">{user.last_name || t('common.notAvailable', 'N/A')}</Typography>
                                </Grid>
                                <Grid item xs={12}>
                                    <Typography variant="body2" color="textSecondary">
                                        {t('userDetail.active', 'Active')}
                                    </Typography>
                                    <Chip 
                                        label={user.active ? t('common.yes') : t('common.no')}
                                        color={user.active ? 'success' : 'default'}
                                        size="small"
                                    />
                                </Grid>
                                <Grid item xs={12}>
                                    <Typography variant="body2" color="textSecondary">
                                        {t('userDetail.lastAccess', 'Last Access')}
                                    </Typography>
                                    <Typography variant="body1">{formatDate(user.last_access)}</Typography>
                                </Grid>
                            </Grid>
                        </CardContent>
                    </Card>
                </Grid>

                {/* Security Information */}
                <Grid item xs={12} md={6}>
                    <Card>
                        <CardContent>
                            <Typography variant="h6" sx={{ mb: 2, display: 'flex', alignItems: 'center' }}>
                                <SecurityIcon sx={{ mr: 1 }} />
                                {t('userDetail.securityInfo', 'Security Information')}
                            </Typography>
                            <Grid container spacing={2}>
                                <Grid item xs={12}>
                                    <Typography variant="body2" color="textSecondary">
                                        {t('users.status', 'Status')}
                                    </Typography>
                                    <Box display="flex" alignItems="center" mt={1}>
                                        {user.is_locked ? (
                                            <>
                                                <LockIcon color="error" sx={{ mr: 1 }} />
                                                <Chip label={t('users.locked')} color="error" size="small" />
                                            </>
                                        ) : (
                                            <>
                                                <LockOpenIcon color="success" sx={{ mr: 1 }} />
                                                <Chip label={t('users.unlocked')} color="success" size="small" />
                                            </>
                                        )}
                                    </Box>
                                </Grid>
                                <Grid item xs={12}>
                                    <Typography variant="body2" color="textSecondary">
                                        {t('userDetail.failedAttempts', 'Failed Login Attempts')}
                                    </Typography>
                                    <Typography variant="body1">
                                        {user.failed_login_attempts || 0}
                                    </Typography>
                                </Grid>
                                <Grid item xs={12}>
                                    <Typography variant="body2" color="textSecondary">
                                        {t('userDetail.lockedAt', 'Locked At')}
                                    </Typography>
                                    <Typography variant="body1">
                                        {formatDate(user.locked_at)}
                                    </Typography>
                                </Grid>
                            </Grid>
                        </CardContent>
                    </Card>
                </Grid>
            </Grid>
        </Box>
    );
};

export default UserDetail;