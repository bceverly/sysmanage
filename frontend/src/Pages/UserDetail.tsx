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
    DialogActions,
    Checkbox,
    FormControlLabel,
    FormGroup,
    Divider
} from '@mui/material';
import ArrowBackIcon from '@mui/icons-material/ArrowBack';
import PersonIcon from '@mui/icons-material/Person';
import SecurityIcon from '@mui/icons-material/Security';
import LockIcon from '@mui/icons-material/Lock';
import LockOpenIcon from '@mui/icons-material/LockOpen';
import LockResetIcon from '@mui/icons-material/LockReset';
import AdminPanelSettingsIcon from '@mui/icons-material/AdminPanelSettings';
import EditIcon from '@mui/icons-material/Edit';
import IconButton from '@mui/material/IconButton';
import { useTranslation } from 'react-i18next';

import { SysManageUser, doGetUsers, doLockUser, doUnlockUser } from '../Services/users';
import {
    SecurityRoleGroup,
    doGetAllRoleGroups,
    doGetUserRoles,
    doUpdateUserRoles
} from '../Services/securityRoles';
import { hasPermission, SecurityRoles } from '../Services/permissions';
import axiosInstance from '../Services/api';

interface AxiosError {
    response?: {
        data?: {
            detail?: string;
        };
    };
}

const UserDetail = () => { // NOSONAR
    const { userId } = useParams<{ userId: string }>();
    const [user, setUser] = useState<SysManageUser | null>(null);
    const [loading, setLoading] = useState<boolean>(true);
    const [error, setError] = useState<string | null>(null);
    const [resettingPassword, setResettingPassword] = useState<boolean>(false);
    const [resetSuccess, setResetSuccess] = useState<string | null>(null);
    const [resetError, setResetError] = useState<string | null>(null);
    const [confirmDialogOpen, setConfirmDialogOpen] = useState<boolean>(false);

    // Security roles state
    const [roleGroups, setRoleGroups] = useState<SecurityRoleGroup[]>([]);
    const [selectedRoles, setSelectedRoles] = useState<number[]>([]);
    const [originalRoles, setOriginalRoles] = useState<number[]>([]);
    const [rolesLoading, setRolesLoading] = useState<boolean>(false);
    const [rolesSaving, setRolesSaving] = useState<boolean>(false);
    const [rolesSuccess, setRolesSuccess] = useState<string | null>(null);
    const [rolesError, setRolesError] = useState<string | null>(null);
    const [rolesEditMode, setRolesEditMode] = useState<boolean>(false);

    // Permission states
    const [canLockUser, setCanLockUser] = useState<boolean>(false);
    const [canUnlockUser, setCanUnlockUser] = useState<boolean>(false);
    const [canResetUserPassword, setCanResetUserPassword] = useState<boolean>(false);
    const [canViewUserSecurityRoles, setCanViewUserSecurityRoles] = useState<boolean>(false);
    const [canEditUserSecurityRoles, setCanEditUserSecurityRoles] = useState<boolean>(false);

    const navigate = useNavigate();
    const { t } = useTranslation();

    // Check permissions
    useEffect(() => {
        const checkPermissions = async () => {
            const [lockUser, unlockUser, resetUserPassword, viewRoles, editRoles] = await Promise.all([
                hasPermission(SecurityRoles.LOCK_USER),
                hasPermission(SecurityRoles.UNLOCK_USER),
                hasPermission(SecurityRoles.RESET_USER_PASSWORD),
                hasPermission(SecurityRoles.VIEW_USER_SECURITY_ROLES),
                hasPermission(SecurityRoles.EDIT_USER_SECURITY_ROLES)
            ]);
            setCanLockUser(lockUser);
            setCanUnlockUser(unlockUser);
            setCanResetUserPassword(resetUserPassword);
            setCanViewUserSecurityRoles(viewRoles);
            setCanEditUserSecurityRoles(editRoles);
        };
        checkPermissions();
    }, []);

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

    // Fetch security roles and user's current roles - only if user has view permission
    useEffect(() => {
        if (!userId || !canViewUserSecurityRoles) return;

        const fetchSecurityRoles = async () => {
            try {
                setRolesLoading(true);
                const [groups, userRoles] = await Promise.all([
                    doGetAllRoleGroups(),
                    doGetUserRoles(userId)
                ]);

                // Sort groups alphabetically by name, with roles sorted within each group
                const sortedGroups = [...groups]
                    .sort((a, b) => a.name.localeCompare(b.name))
                    .map(group => ({ ...group, roles: [...group.roles].sort((a, b) => a.name.localeCompare(b.name)) }));

                setRoleGroups(sortedGroups);
                setSelectedRoles(userRoles.role_ids);
                setOriginalRoles(userRoles.role_ids);
            } catch (err) {
                console.error('Error fetching security roles:', err);
                setRolesError(t('userDetail.rolesLoadError', 'Failed to load security roles'));
            } finally {
                setRolesLoading(false);
            }
        };

        fetchSecurityRoles();
    }, [userId, canViewUserSecurityRoles, t]);

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

    const handleRoleToggle = (roleId: number) => {
        setSelectedRoles(prev =>
            prev.includes(roleId)
                ? prev.filter(id => id !== roleId)
                : [...prev, roleId]
        );
    };

    const handleCheckAll = () => {
        const allRoleIds = roleGroups.flatMap(group => group.roles.map(role => role.id));
        setSelectedRoles(allRoleIds);
    };

    const handleClearAll = () => {
        setSelectedRoles([]);
    };

    const handleSaveRoles = async () => {
        if (!userId) return;

        try {
            setRolesSaving(true);
            setRolesError(null);
            setRolesSuccess(null);

            await doUpdateUserRoles(userId, selectedRoles);

            setOriginalRoles(selectedRoles);
            setRolesSuccess(t('userDetail.rolesSaveSuccess', 'Security roles updated successfully'));
            setRolesEditMode(false);
        } catch (err) {
            console.error('Error saving roles:', err);
            setRolesError(t('userDetail.rolesSaveError', 'Failed to update security roles'));
        } finally {
            setRolesSaving(false);
        }
    };

    const handleCancelRoles = () => {
        setSelectedRoles(originalRoles);
        setRolesError(null);
        setRolesSuccess(null);
        setRolesEditMode(false);
    };

    const handleLockUser = async () => {
        if (!userId) return;
        try {
            await doLockUser(userId);
            // Refresh user data
            const users = await doGetUsers();
            const updatedUser = users.find((u: SysManageUser) => u.id.toString() === userId);
            if (updatedUser) {
                setUser(updatedUser);
            }
        } catch (err) {
            console.error('Error locking user:', err);
        }
    };

    const handleUnlockUser = async () => {
        if (!userId) return;
        try {
            await doUnlockUser(userId);
            // Refresh user data
            const users = await doGetUsers();
            const updatedUser = users.find((u: SysManageUser) => u.id.toString() === userId);
            if (updatedUser) {
                setUser(updatedUser);
            }
        } catch (err) {
            console.error('Error unlocking user:', err);
        }
    };

    const hasUnsavedChanges = JSON.stringify(selectedRoles.toSorted((a, b) => a - b)) !== JSON.stringify(originalRoles.toSorted((a, b) => a - b));

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

                {canResetUserPassword && (
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
                )}
            </Box>

            <Grid container spacing={3}>
                {/* Basic Information */}
                <Grid size={{ xs: 12, md: 6 }}>
                    <Card>
                        <CardContent>
                            <Typography variant="h6" sx={{ mb: 2, display: 'flex', alignItems: 'center' }}>
                                <PersonIcon sx={{ mr: 1 }} />
                                {t('userDetail.basicInfo', 'Basic Information')}
                            </Typography>
                            <Grid container spacing={2}>
                                {/* Left Column */}
                                <Grid size={{ xs: 12, sm: 6 }}>
                                    <Grid container spacing={2}>
                                        <Grid size={{ xs: 12 }}>
                                            <Typography variant="body2" color="textSecondary">
                                                {t('userDetail.userId', 'User ID')}
                                            </Typography>
                                            <Typography variant="body1">{user.id.toString()}</Typography>
                                        </Grid>
                                        <Grid size={{ xs: 12 }}>
                                            <Typography variant="body2" color="textSecondary">
                                                {t('userDetail.active', 'Active')}
                                            </Typography>
                                            <Chip
                                                label={user.active ? t('common.yes') : t('common.no')}
                                                color={user.active ? 'success' : 'default'}
                                                size="small"
                                            />
                                        </Grid>
                                        <Grid size={{ xs: 12 }}>
                                            <Typography variant="body2" color="textSecondary">
                                                {t('userDetail.lastAccess', 'Last Access')}
                                            </Typography>
                                            <Typography variant="body1">{formatDate(user.last_access)}</Typography>
                                        </Grid>
                                    </Grid>
                                </Grid>
                                {/* Right Column */}
                                <Grid size={{ xs: 12, sm: 6 }}>
                                    <Grid container spacing={2}>
                                        <Grid size={{ xs: 12 }}>
                                            <Typography variant="body2" color="textSecondary">
                                                {t('users.email', 'Email')}
                                            </Typography>
                                            <Typography variant="body1">{user.userid}</Typography>
                                        </Grid>
                                        <Grid size={{ xs: 12 }}>
                                            <Typography variant="body2" color="textSecondary">
                                                {t('userDetail.firstName', 'First Name')}
                                            </Typography>
                                            <Typography variant="body1">{user.first_name || t('common.notAvailable', 'N/A')}</Typography>
                                        </Grid>
                                        <Grid size={{ xs: 12 }}>
                                            <Typography variant="body2" color="textSecondary">
                                                {t('userDetail.lastName', 'Last Name')}
                                            </Typography>
                                            <Typography variant="body1">{user.last_name || t('common.notAvailable', 'N/A')}</Typography>
                                        </Grid>
                                    </Grid>
                                </Grid>
                            </Grid>
                        </CardContent>
                    </Card>
                </Grid>

                {/* Security Information */}
                <Grid size={{ xs: 12, md: 6 }}>
                    <Card>
                        <CardContent>
                            <Box sx={{ mb: 2, display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                                <Typography variant="h6" sx={{ display: 'flex', alignItems: 'center' }}>
                                    <SecurityIcon sx={{ mr: 1 }} />
                                    {t('userDetail.securityInfo', 'Security Information')}
                                </Typography>
                                <Box>
                                    {user.is_locked ? (
                                        canUnlockUser && (
                                            <Button
                                                size="small"
                                                variant="outlined"
                                                startIcon={<LockOpenIcon />}
                                                onClick={handleUnlockUser}
                                            >
                                                {t('userDetail.unlockUser', 'Unlock User')}
                                            </Button>
                                        )
                                    ) : (
                                        canLockUser && (
                                            <Button
                                                size="small"
                                                variant="outlined"
                                                startIcon={<LockIcon />}
                                                onClick={handleLockUser}
                                            >
                                                {t('userDetail.lockUser', 'Lock User')}
                                            </Button>
                                        )
                                    )}
                                </Box>
                            </Box>
                            <Grid container spacing={2}>
                                <Grid size={{ xs: 12 }}>
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
                                <Grid size={{ xs: 12 }}>
                                    <Typography variant="body2" color="textSecondary">
                                        {t('userDetail.failedAttempts', 'Failed Login Attempts')}
                                    </Typography>
                                    <Typography variant="body1">
                                        {user.failed_login_attempts || 0}
                                    </Typography>
                                </Grid>
                                <Grid size={{ xs: 12 }}>
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

                {/* Security Roles - Only show if user has VIEW permission */}
                {canViewUserSecurityRoles && (
                <Grid size={{ xs: 12 }}>
                    <Card>
                        <CardContent>
                            <Box sx={{ mb: 2, display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                                <Box sx={{ display: 'flex', alignItems: 'center' }}>
                                    <Typography variant="h6" sx={{ display: 'flex', alignItems: 'center' }}>
                                        <AdminPanelSettingsIcon sx={{ mr: 1 }} />
                                        {t('userDetail.securityRoles', 'Security Roles')}
                                    </Typography>
                                    {canEditUserSecurityRoles && (
                                    <IconButton
                                        size="small"
                                        onClick={() => setRolesEditMode(!rolesEditMode)}
                                        disabled={rolesSaving || rolesLoading}
                                        sx={{ ml: 2 }}
                                        color={rolesEditMode ? 'primary' : 'default'}
                                    >
                                        <EditIcon fontSize="small" />
                                    </IconButton>
                                    )}
                                </Box>
                                {rolesEditMode && (
                                    <Box>
                                        <Button
                                            size="small"
                                            onClick={handleCheckAll}
                                            disabled={rolesSaving || rolesLoading}
                                            sx={{ mr: 1 }}
                                        >
                                            {t('userDetail.checkAll', 'Check All')}
                                        </Button>
                                        <Button
                                            size="small"
                                            onClick={handleClearAll}
                                            disabled={rolesSaving || rolesLoading}
                                        >
                                            {t('userDetail.clearAll', 'Clear All')}
                                        </Button>
                                    </Box>
                                )}
                            </Box>

                            {(() => {
                                if (rolesLoading) {
                                    return (
                                        <Box display="flex" justifyContent="center" py={3}>
                                            <CircularProgress />
                                        </Box>
                                    );
                                }
                                if (rolesError) {
                                    return (
                                        <Alert severity="error" sx={{ mb: 2 }}>
                                            {rolesError}
                                        </Alert>
                                    );
                                }
                                return (
                                    <>
                                        {roleGroups.map((group, index) => (
                                            <Box key={group.id}>
                                                <Typography variant="subtitle1" sx={{ fontWeight: 'bold', mb: 1, textDecoration: 'underline' }}>
                                                    {group.name}
                                                </Typography>
                                                <FormGroup>
                                                    <Grid container spacing={1}>
                                                        {group.roles.map((role) => (
                                                            <Grid size={{ xs: 12, sm: 6, md: 4 }} key={role.id}>
                                                                <FormControlLabel
                                                                    control={
                                                                        <Checkbox
                                                                            checked={selectedRoles.includes(role.id)}
                                                                            onChange={() => handleRoleToggle(role.id)}
                                                                            disabled={!rolesEditMode || rolesSaving}
                                                                        />
                                                                    }
                                                                    label={role.name}
                                                                />
                                                            </Grid>
                                                        ))}
                                                    </Grid>
                                                </FormGroup>
                                                {index < roleGroups.length - 1 && (
                                                    <Divider sx={{ my: 3 }} />
                                                )}
                                            </Box>
                                        ))}

                                        {rolesSuccess && (
                                            <Alert severity="success" sx={{ mb: 2 }}>
                                                {rolesSuccess}
                                            </Alert>
                                        )}

                                        {rolesEditMode && canEditUserSecurityRoles && (
                                            <Box sx={{ display: 'flex', gap: 2, mt: 2 }}>
                                                <Button
                                                    variant="contained"
                                                    color="primary"
                                                    onClick={handleSaveRoles}
                                                    disabled={!hasUnsavedChanges || rolesSaving}
                                                >
                                                    {rolesSaving ? t('common.saving', 'Saving...') : t('common.save', 'Save')}
                                                </Button>
                                                <Button
                                                    variant="outlined"
                                                    onClick={handleCancelRoles}
                                                    disabled={!hasUnsavedChanges || rolesSaving}
                                                >
                                                    {t('common.cancel', 'Cancel')}
                                                </Button>
                                            </Box>
                                        )}
                                    </>
                                );
                            })()}
                        </CardContent>
                    </Card>
                </Grid>
                )}
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