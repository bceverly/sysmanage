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
    Paper,
    Alert,
    Snackbar,
    Dialog,
    DialogTitle,
    DialogContent,
    DialogContentText,
    DialogActions
} from '@mui/material';
import ArrowBackIcon from '@mui/icons-material/ArrowBack';
import PersonIcon from '@mui/icons-material/Person';
import SecurityIcon from '@mui/icons-material/Security';
import LockIcon from '@mui/icons-material/Lock';
import LockOpenIcon from '@mui/icons-material/LockOpen';
import LockResetIcon from '@mui/icons-material/LockReset';
import { useTranslation } from 'react-i18next';

import { SysManageUser, doGetUsers } from '../Services/users';
import axiosInstance from '../Services/api';

interface AxiosError {
    response?: {
        data?: {
            detail?: string;
        };
    };
}

const UserDetail = () => {
    const { userId } = useParams<{ userId: string }>();
    const [user, setUser] = useState<SysManageUser | null>(null);
    const [loading, setLoading] = useState<boolean>(true);
    const [error, setError] = useState<string | null>(null);
    const [resettingPassword, setResettingPassword] = useState<boolean>(false);
    const [resetSuccess, setResetSuccess] = useState<string | null>(null);
    const [resetError, setResetError] = useState<string | null>(null);
    const [confirmDialogOpen, setConfirmDialogOpen] = useState<boolean>(false);
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

    const handlePasswordResetClick = () => {
        setConfirmDialogOpen(true);
    };

    const handleConfirmPasswordReset = async () => {
        if (!user) return;

        setConfirmDialogOpen(false);
        setResettingPassword(true);
        setResetError(null);
        setResetSuccess(null);

        try {
            const response = await axiosInstance.post(`/api/admin/reset-user-password/${user.id}`);

            setResetSuccess(
                response.data.message ||
                t('userDetail.passwordResetSuccess', 'Password reset email has been sent to {email}', { email: user.userid })
            );
        } catch (err: unknown) {
            console.error('Password reset error:', err);
            const axiosErr = err as AxiosError;
            const errorMessage = axiosErr?.response?.data?.detail ||
                t('userDetail.passwordResetError', 'Failed to send password reset email. Please try again.');
            setResetError(errorMessage);
        } finally {
            setResettingPassword(false);
        }
    };

    const handleCancelPasswordReset = () => {
        setConfirmDialogOpen(false);
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

            <Box sx={{ mb: 3, display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <Typography variant="h4" sx={{ display: 'flex', alignItems: 'center' }}>
                    <PersonIcon sx={{ mr: 2, fontSize: '2rem' }} />
                    {user.userid}
                </Typography>

                <Button
                    variant="outlined"
                    color="warning"
                    startIcon={<LockResetIcon />}
                    onClick={handlePasswordResetClick}
                    disabled={resettingPassword}
                >
                    {resettingPassword
                        ? t('userDetail.resettingPassword', 'Sending Reset Email...')
                        : t('userDetail.resetPassword', 'Reset Password')
                    }
                </Button>
            </Box>

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

            {/* Success Snackbar */}
            <Snackbar
                open={!!resetSuccess}
                autoHideDuration={6000}
                onClose={() => setResetSuccess(null)}
            >
                <Alert
                    onClose={() => setResetSuccess(null)}
                    severity="success"
                    sx={{ width: '100%' }}
                >
                    {resetSuccess}
                </Alert>
            </Snackbar>

            {/* Error Snackbar */}
            <Snackbar
                open={!!resetError}
                autoHideDuration={6000}
                onClose={() => setResetError(null)}
            >
                <Alert
                    onClose={() => setResetError(null)}
                    severity="error"
                    sx={{ width: '100%' }}
                >
                    {resetError}
                </Alert>
            </Snackbar>

            {/* Confirmation Dialog */}
            <Dialog
                open={confirmDialogOpen}
                onClose={handleCancelPasswordReset}
                aria-labelledby="password-reset-dialog-title"
                aria-describedby="password-reset-dialog-description"
            >
                <DialogTitle id="password-reset-dialog-title">
                    {t('userDetail.confirmResetTitle', 'Confirm Password Reset')}
                </DialogTitle>
                <DialogContent>
                    <DialogContentText id="password-reset-dialog-description">
                        {t('userDetail.confirmResetMessage', 'Are you sure you want to send a password reset email to {email}? This will allow the user to set a new password.', { email: user?.userid })}
                    </DialogContentText>
                </DialogContent>
                <DialogActions>
                    <Button onClick={handleCancelPasswordReset} color="primary">
                        {t('common.cancel', 'Cancel')}
                    </Button>
                    <Button
                        onClick={handleConfirmPasswordReset}
                        color="warning"
                        variant="contained"
                        autoFocus
                    >
                        {t('userDetail.sendResetEmail', 'Send Reset Email')}
                    </Button>
                </DialogActions>
            </Dialog>
        </Box>
    );
};

export default UserDetail;