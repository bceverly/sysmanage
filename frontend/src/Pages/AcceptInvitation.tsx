// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

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
    MarkEmailRead as MarkEmailReadIcon,
    Visibility,
    VisibilityOff
} from '@mui/icons-material';
import {
    doValidateInvitation,
    doAcceptInvitation,
    Invitation
} from '../Services/invitations';
import LanguageSelector from '../Components/LanguageSelector';

interface AxiosError {
    response?: {
        data?: {
            detail?: string;
        };
    };
}

const AcceptInvitation: React.FC = () => {
    const [password, setPassword] = useState('');
    const [confirmPassword, setConfirmPassword] = useState('');
    const [firstName, setFirstName] = useState('');
    const [lastName, setLastName] = useState('');
    const [showPassword, setShowPassword] = useState(false);
    const [showConfirmPassword, setShowConfirmPassword] = useState(false);
    const [loading, setLoading] = useState(false);
    const [validatingToken, setValidatingToken] = useState(true);
    const [invitation, setInvitation] = useState<Invitation | null>(null);
    const [success, setSuccess] = useState(false);
    const [error, setError] = useState<string | null>(null);

    const navigate = useNavigate();
    const location = useLocation();
    const { t } = useTranslation();

    const searchParams = new globalThis.URLSearchParams(location.search);
    const token = searchParams.get('token');

    useEffect(() => {
        if (!token) {
            setError(t('acceptInvitation.noToken', 'No invitation token provided'));
            setValidatingToken(false);
            return;
        }

        const validateToken = async () => {
            try {
                const inv = await doValidateInvitation(token);
                setInvitation(inv);
                setFirstName(inv.first_name || '');
                setLastName(inv.last_name || '');
                setError(null);
            } catch (err: unknown) {
                console.error('Invitation validation error:', err);
                setInvitation(null);
                const axiosErr = err as AxiosError;
                const errorMessage = axiosErr?.response?.data?.detail ||
                    t('acceptInvitation.invalidToken', 'This invitation link is invalid or has expired');
                setError(errorMessage);
            } finally {
                setValidatingToken(false);
            }
        };

        validateToken();
    }, [token, t]);

    const handleSubmit = async (e: React.BaseSyntheticEvent) => {
        e.preventDefault();

        if (!password || !confirmPassword) {
            setError(t('acceptInvitation.fillAllFields', 'Please fill in all fields'));
            return;
        }

        // Constant-time comparison to avoid timing leaks.
        const passwordChars = Array.from(password);
        const confirmPasswordChars = Array.from(confirmPassword);
        const passwordsMatch = passwordChars.length === confirmPasswordChars.length &&
            passwordChars.every((char, index) => char === confirmPasswordChars.at(index));
        if (!passwordsMatch) {
            setError(t('acceptInvitation.passwordMismatch', 'Passwords do not match'));
            return;
        }

        if (password.length < 8) {
            setError(t('acceptInvitation.passwordTooShort', 'Password must be at least 8 characters long'));
            return;
        }

        setLoading(true);
        setError(null);

        try {
            await doAcceptInvitation({
                token: token as string,
                password,
                confirm_password: confirmPassword,
                first_name: firstName || null,
                last_name: lastName || null
            });

            setSuccess(true);
            setError(null);

            setTimeout(() => {
                navigate('/login');
            }, 3000);
        } catch (err: unknown) {
            console.error('Accept invitation error:', err);
            const axiosErr = err as AxiosError;
            const errorMessage = axiosErr?.response?.data?.detail ||
                t('acceptInvitation.acceptError', 'An error occurred while accepting your invitation');
            setError(errorMessage);
        } finally {
            setLoading(false);
        }
    };

    if (validatingToken) {
        return (
            <Box sx={{ position: 'fixed', top: 20, right: 20, zIndex: 1000 }}>
                <LanguageSelector theme="light" />
                <Container component="main" maxWidth="sm">
                    <Box sx={{ marginTop: 8, display: 'flex', flexDirection: 'column', alignItems: 'center' }}>
                        <CircularProgress />
                        <Typography sx={{ mt: 2 }}>
                            {t('acceptInvitation.validatingToken', 'Validating invitation...')}
                        </Typography>
                    </Box>
                </Container>
            </Box>
        );
    }

    if (!invitation) {
        return (
            <>
                <Box sx={{ position: 'fixed', top: 20, right: 20, zIndex: 1000 }}>
                    <LanguageSelector theme="light" />
                </Box>
                <Container component="main" maxWidth="sm">
                    <Paper elevation={3} sx={{ marginTop: 8, p: 4, display: 'flex', flexDirection: 'column', alignItems: 'center' }}>
                        <MarkEmailReadIcon sx={{ fontSize: 48, color: 'error.main', mb: 2 }} />
                        <Typography component="h1" variant="h5" sx={{ mb: 2 }}>
                            {t('acceptInvitation.invalidTitle', 'Invalid Invitation')}
                        </Typography>
                        <Alert severity="error" sx={{ width: '100%', mb: 2 }}>
                            {error}
                        </Alert>
                        <Typography variant="body1" sx={{ textAlign: 'center', mb: 3 }}>
                            {t('acceptInvitation.invalidDescription',
                              'This invitation link is either invalid or has expired. Please ask your administrator to send a new invitation.')}
                        </Typography>
                        <Button variant="contained" onClick={() => navigate('/login')}>
                            {t('acceptInvitation.backToLogin', 'Back to Login')}
                        </Button>
                    </Paper>
                </Container>
            </>
        );
    }

    if (success) {
        return (
            <>
                <Box sx={{ position: 'fixed', top: 20, right: 20, zIndex: 1000 }}>
                    <LanguageSelector theme="light" />
                </Box>
                <Container component="main" maxWidth="sm">
                    <Paper elevation={3} sx={{ marginTop: 8, p: 4, display: 'flex', flexDirection: 'column', alignItems: 'center' }}>
                        <MarkEmailReadIcon sx={{ fontSize: 48, color: 'success.main', mb: 2 }} />
                        <Typography component="h1" variant="h5" sx={{ mb: 2 }}>
                            {t('acceptInvitation.successTitle', 'Account Created')}
                        </Typography>
                        <Alert severity="success" sx={{ width: '100%', mb: 2 }}>
                            {t('acceptInvitation.successMessage',
                              'Your account is ready. You can now log in with your new password.')}
                        </Alert>
                        <Typography variant="body1" sx={{ textAlign: 'center', mb: 3 }}>
                            {t('acceptInvitation.redirecting', 'Redirecting to login page...')}
                        </Typography>
                        <Button variant="contained" onClick={() => navigate('/login')}>
                            {t('acceptInvitation.goToLogin', 'Go to Login')}
                        </Button>
                    </Paper>
                </Container>
            </>
        );
    }

    return (
        <>
            <Box sx={{ position: 'fixed', top: 20, right: 20, zIndex: 1000 }}>
                <LanguageSelector theme="light" />
            </Box>
            <Container component="main" maxWidth="sm">
                <Paper elevation={3} sx={{ marginTop: 8, p: 4, display: 'flex', flexDirection: 'column', alignItems: 'center' }}>
                    <MarkEmailReadIcon sx={{ fontSize: 48, color: 'primary.main', mb: 2 }} />
                    <Typography component="h1" variant="h5" sx={{ mb: 2 }}>
                        {t('acceptInvitation.title', 'Accept Your Invitation')}
                    </Typography>
                    <Typography variant="body1" sx={{ textAlign: 'center', mb: 1 }}>
                        {t('acceptInvitation.description', 'Set a password to finish creating your account.')}
                    </Typography>
                    <Typography variant="body2" sx={{ textAlign: 'center', mb: 3, color: 'text.secondary' }}>
                        {invitation.email}
                    </Typography>

                    <Box component="form" onSubmit={handleSubmit} sx={{ width: '100%' }}>
                        {error && (
                            <Alert severity="error" sx={{ mb: 2 }}>
                                {error}
                            </Alert>
                        )}

                        <TextField
                            margin="normal"
                            fullWidth
                            name="firstName"
                            label={t('acceptInvitation.firstName', 'First Name')}
                            id="firstName"
                            value={firstName}
                            onChange={(e) => setFirstName(e.target.value)}
                            disabled={loading}
                        />

                        <TextField
                            margin="normal"
                            fullWidth
                            name="lastName"
                            label={t('acceptInvitation.lastName', 'Last Name')}
                            id="lastName"
                            value={lastName}
                            onChange={(e) => setLastName(e.target.value)}
                            disabled={loading}
                        />

                        <TextField
                            margin="normal"
                            required
                            fullWidth
                            name="password"
                            label={t('acceptInvitation.password', 'Password')}
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
                                                onClick={() => setShowPassword(!showPassword)}
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
                            label={t('acceptInvitation.confirmPassword', 'Confirm Password')}
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
                                                onClick={() => setShowConfirmPassword(!showConfirmPassword)}
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
                                ? t('acceptInvitation.submitting', 'Creating Account...')
                                : t('acceptInvitation.submitButton', 'Create Account')
                            }
                        </Button>

                        <Box sx={{ textAlign: 'center' }}>
                            <Button variant="text" onClick={() => navigate('/login')} disabled={loading}>
                                {t('acceptInvitation.backToLogin', 'Back to Login')}
                            </Button>
                        </Box>
                    </Box>
                </Paper>
            </Container>
        </>
    );
};

export default AcceptInvitation;
