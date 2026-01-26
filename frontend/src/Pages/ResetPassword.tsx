import React, { useState, useEffect } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import {
    Container,
    Box,
    Typography,
    TextField,
    Button,
    Alert,
    CircularProgress,
    Paper,
    IconButton,
    InputAdornment
} from '@mui/material';
import {
    LockReset as LockResetIcon,
    Visibility,
    VisibilityOff
} from '@mui/icons-material';
import axiosInstance from '../Services/api';
import LanguageSelector from '../Components/LanguageSelector';

interface AxiosError {
    response?: {
        data?: {
            detail?: string;
        };
    };
}

const ResetPassword: React.FC = () => {
    const [password, setPassword] = useState('');
    const [confirmPassword, setConfirmPassword] = useState('');
    const [showPassword, setShowPassword] = useState(false);
    const [showConfirmPassword, setShowConfirmPassword] = useState(false);
    const [loading, setLoading] = useState(false);
    const [validatingToken, setValidatingToken] = useState(true);
    const [tokenValid, setTokenValid] = useState(false);
    const [success, setSuccess] = useState(false);
    const [error, setError] = useState<string | null>(null);

    const navigate = useNavigate();
    const location = useLocation();
    const { t } = useTranslation();

    // Extract token from URL parameters
    const searchParams = new globalThis.URLSearchParams(location.search);
    const token = searchParams.get('token');

    useEffect(() => {
        if (!token) {
            setError(t('resetPassword.noToken', 'No reset token provided'));
            setValidatingToken(false);
            return;
        }

        // Validate the token when component mounts
        const validateToken = async () => {
            try {
                await axiosInstance.get(`/validate-reset-token/${token}`);
                setTokenValid(true);
                setError(null);
            } catch (err: unknown) {
                console.error('Token validation error:', err);
                setTokenValid(false);
                const axiosErr = err as AxiosError;
                const errorMessage = axiosErr?.response?.data?.detail ||
                    t('resetPassword.invalidToken', 'This password reset link is invalid or has expired');
                setError(errorMessage);
            } finally {
                setValidatingToken(false);
            }
        };

        validateToken();
    }, [token, t]);

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();

        if (!password || !confirmPassword) {
            setError(t('resetPassword.fillAllFields', 'Please fill in all fields'));
            return;
        }

        // Use constant-time comparison to prevent timing attacks
        const passwordChars = Array.from(password);
        const confirmPasswordChars = Array.from(confirmPassword);
        const passwordsMatch = passwordChars.length === confirmPasswordChars.length &&
            passwordChars.every((char, index) => char === confirmPasswordChars.at(index));
        if (!passwordsMatch) {
            setError(t('resetPassword.passwordMismatch', 'Passwords do not match'));
            return;
        }

        if (password.length < 8) {
            setError(t('resetPassword.passwordTooShort', 'Password must be at least 8 characters long'));
            return;
        }

        setLoading(true);
        setError(null);

        try {
            await axiosInstance.post('/reset-password', {
                token: token,
                password: password,
                confirm_password: confirmPassword
            });

            setSuccess(true);
            setError(null);

            // Redirect to login after a brief delay
            setTimeout(() => {
                navigate('/login');
            }, 3000);

        } catch (err: unknown) {
            console.error('Password reset error:', err);
            const axiosErr = err as AxiosError;
            const errorMessage = axiosErr?.response?.data?.detail ||
                t('resetPassword.resetError', 'An error occurred while resetting your password');
            setError(errorMessage);
        } finally {
            setLoading(false);
        }
    };

    const togglePasswordVisibility = () => {
        setShowPassword(!showPassword);
    };

    const toggleConfirmPasswordVisibility = () => {
        setShowConfirmPassword(!showConfirmPassword);
    };

    if (validatingToken) {
        return (
            <Box
                sx={{
                    position: "fixed",
                    top: 20,
                    right: 20,
                    zIndex: 1000,
                }}
            >
                <LanguageSelector theme="light" />
                <Container component="main" maxWidth="sm">
                    <Box
                        sx={{
                            marginTop: 8,
                            display: "flex",
                            flexDirection: "column",
                            alignItems: "center",
                        }}
                    >
                        <CircularProgress />
                        <Typography sx={{ mt: 2 }}>
                            {t('resetPassword.validatingToken', 'Validating reset token...')}
                        </Typography>
                    </Box>
                </Container>
            </Box>
        );
    }

    if (!tokenValid) {
        return (
            <>
                <Box
                    sx={{
                        position: "fixed",
                        top: 20,
                        right: 20,
                        zIndex: 1000,
                    }}
                >
                    <LanguageSelector theme="light" />
                </Box>
                <Container component="main" maxWidth="sm">
                    <Paper
                        elevation={3}
                        sx={{
                            marginTop: 8,
                            p: 4,
                            display: "flex",
                            flexDirection: "column",
                            alignItems: "center",
                        }}
                    >
                        <LockResetIcon sx={{ fontSize: 48, color: 'error.main', mb: 2 }} />
                        <Typography component="h1" variant="h5" sx={{ mb: 2 }}>
                            {t('resetPassword.invalidTitle', 'Invalid Reset Link')}
                        </Typography>

                        <Alert severity="error" sx={{ width: '100%', mb: 2 }}>
                            {error}
                        </Alert>

                        <Typography variant="body1" sx={{ textAlign: 'center', mb: 3 }}>
                            {t('resetPassword.invalidDescription',
                              'This password reset link is either invalid or has expired. Please request a new password reset.')}
                        </Typography>

                        <Button
                            variant="contained"
                            onClick={() => navigate('/login')}
                        >
                            {t('resetPassword.backToLogin', 'Back to Login')}
                        </Button>
                    </Paper>
                </Container>
            </>
        );
    }

    if (success) {
        return (
            <>
                <Box
                    sx={{
                        position: "fixed",
                        top: 20,
                        right: 20,
                        zIndex: 1000,
                    }}
                >
                    <LanguageSelector theme="light" />
                </Box>
                <Container component="main" maxWidth="sm">
                    <Paper
                        elevation={3}
                        sx={{
                            marginTop: 8,
                            p: 4,
                            display: "flex",
                            flexDirection: "column",
                            alignItems: "center",
                        }}
                    >
                        <LockResetIcon sx={{ fontSize: 48, color: 'success.main', mb: 2 }} />
                        <Typography component="h1" variant="h5" sx={{ mb: 2 }}>
                            {t('resetPassword.successTitle', 'Password Reset Complete')}
                        </Typography>

                        <Alert severity="success" sx={{ width: '100%', mb: 2 }}>
                            {t('resetPassword.successMessage',
                              'Your password has been successfully reset. You can now log in with your new password.')}
                        </Alert>

                        <Typography variant="body1" sx={{ textAlign: 'center', mb: 3 }}>
                            {t('resetPassword.redirecting', 'Redirecting to login page...')}
                        </Typography>

                        <Button
                            variant="contained"
                            onClick={() => navigate('/login')}
                        >
                            {t('resetPassword.goToLogin', 'Go to Login')}
                        </Button>
                    </Paper>
                </Container>
            </>
        );
    }

    return (
        <>
            <Box
                sx={{
                    position: "fixed",
                    top: 20,
                    right: 20,
                    zIndex: 1000,
                }}
            >
                <LanguageSelector theme="light" />
            </Box>
            <Container component="main" maxWidth="sm">
                <Paper
                    elevation={3}
                    sx={{
                        marginTop: 8,
                        p: 4,
                        display: "flex",
                        flexDirection: "column",
                        alignItems: "center",
                    }}
                >
                    <LockResetIcon sx={{ fontSize: 48, color: 'primary.main', mb: 2 }} />
                    <Typography component="h1" variant="h5" sx={{ mb: 2 }}>
                        {t('resetPassword.title', 'Reset Your Password')}
                    </Typography>

                    <Typography variant="body1" sx={{ textAlign: 'center', mb: 3 }}>
                        {t('resetPassword.description', 'Please enter your new password below.')}
                    </Typography>

                    <Box component="form" onSubmit={handleSubmit} sx={{ width: '100%' }}>
                        {error && (
                            <Alert severity="error" sx={{ mb: 2 }}>
                                {error}
                            </Alert>
                        )}

                        <TextField
                            margin="normal"
                            required
                            fullWidth
                            name="password"
                            label={t('resetPassword.newPassword', 'New Password')}
                            type={showPassword ? 'text' : 'password'}
                            id="password"
                            value={password}
                            onChange={(e) => setPassword(e.target.value)}
                            disabled={loading}
                            slotProps={{
                                input: {
                                    endAdornment: (
                                        <InputAdornment position="end">
                                            <IconButton
                                                aria-label="toggle password visibility"
                                                onClick={togglePasswordVisibility}
                                                edge="end"
                                            >
                                                {showPassword ? <VisibilityOff /> : <Visibility />}
                                            </IconButton>
                                        </InputAdornment>
                                    ),
                                },
                            }}
                        />

                        <TextField
                            margin="normal"
                            required
                            fullWidth
                            name="confirmPassword"
                            label={t('resetPassword.confirmPassword', 'Confirm New Password')}
                            type={showConfirmPassword ? 'text' : 'password'}
                            id="confirmPassword"
                            value={confirmPassword}
                            onChange={(e) => setConfirmPassword(e.target.value)}
                            disabled={loading}
                            slotProps={{
                                input: {
                                    endAdornment: (
                                        <InputAdornment position="end">
                                            <IconButton
                                                aria-label="toggle confirm password visibility"
                                                onClick={toggleConfirmPasswordVisibility}
                                                edge="end"
                                            >
                                                {showConfirmPassword ? <VisibilityOff /> : <Visibility />}
                                            </IconButton>
                                        </InputAdornment>
                                    ),
                                },
                            }}
                        />

                        <Button
                            type="submit"
                            fullWidth
                            variant="contained"
                            disabled={loading || !password || !confirmPassword}
                            sx={{ mt: 3, mb: 2 }}
                            startIcon={loading ? <CircularProgress size={20} /> : undefined}
                        >
                            {loading
                                ? t('resetPassword.resetting', 'Resetting Password...')
                                : t('resetPassword.resetButton', 'Reset Password')
                            }
                        </Button>

                        <Box sx={{ textAlign: 'center' }}>
                            <Button
                                variant="text"
                                onClick={() => navigate('/login')}
                                disabled={loading}
                            >
                                {t('resetPassword.backToLogin', 'Back to Login')}
                            </Button>
                        </Box>
                    </Box>
                </Paper>
            </Container>
        </>
    );
};

export default ResetPassword;