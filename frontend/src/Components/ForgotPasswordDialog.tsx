import React, { useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
    Dialog,
    DialogTitle,
    DialogContent,
    DialogActions,
    TextField,
    Button,
    Alert,
    CircularProgress,
    Typography,
    Box
} from '@mui/material';
import { Email as EmailIcon } from '@mui/icons-material';
import axiosInstance from '../Services/api';

interface AxiosError {
    response?: {
        data?: {
            detail?: string;
        };
    };
}

interface ForgotPasswordDialogProps {
    open: boolean;
    onClose: () => void;
}

const ForgotPasswordDialog: React.FC<ForgotPasswordDialogProps> = ({ open, onClose }) => {
    const [email, setEmail] = useState('');
    const [loading, setLoading] = useState(false);
    const [success, setSuccess] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const { t } = useTranslation();

    const handleClose = () => {
        if (!loading) {
            setEmail('');
            setError(null);
            setSuccess(false);
            onClose();
        }
    };

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();

        if (!email) {
            setError(t('forgotPassword.emailRequired', 'Email is required'));
            return;
        }

        setLoading(true);
        setError(null);

        try {
            await axiosInstance.post('/forgot-password', {
                email: email
            });

            setSuccess(true);
            setError(null);
        } catch (err: unknown) {
            console.error('Forgot password error:', err);
            const axiosErr = err as AxiosError;
            const errorMessage = axiosErr?.response?.data?.detail ||
                t('forgotPassword.error', 'An error occurred while processing your request');
            setError(errorMessage);
        } finally {
            setLoading(false);
        }
    };

    if (success) {
        return (
            <Dialog
                open={open}
                onClose={handleClose}
                maxWidth="sm"
                fullWidth
                disableRestoreFocus
                keepMounted={false}
            >
                <DialogTitle>
                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                        <EmailIcon color="primary" />
                        {t('forgotPassword.emailSent', 'Email Sent')}
                    </Box>
                </DialogTitle>
                <DialogContent>
                    <Alert severity="success" sx={{ mt: 1 }}>
                        <Typography>
                            {t('forgotPassword.checkEmail',
                              'If an account with that email exists, a password reset link has been sent. Please check your email and follow the instructions to reset your password.')}
                        </Typography>
                    </Alert>
                    <Typography variant="body2" color="text.secondary" sx={{ mt: 2 }}>
                        {t('forgotPassword.didntReceive',
                          "Didn't receive an email? Check your spam folder or try again.")}
                    </Typography>
                </DialogContent>
                <DialogActions>
                    <Button
                        onClick={handleClose}
                        variant="contained"
                        autoFocus
                    >
                        {t('common.close', 'Close')}
                    </Button>
                </DialogActions>
            </Dialog>
        );
    }

    return (
        <Dialog
            open={open}
            onClose={handleClose}
            maxWidth="sm"
            fullWidth
            disableRestoreFocus
            keepMounted={false}
        >
            <form onSubmit={handleSubmit}>
                <DialogTitle>
                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                        <EmailIcon color="primary" />
                        {t('forgotPassword.title', 'Forgot Password')}
                    </Box>
                </DialogTitle>
                <DialogContent>
                    <Typography variant="body1" sx={{ mb: 2 }}>
                        {t('forgotPassword.description',
                          'Enter your email address and we\'ll send you a link to reset your password.')}
                    </Typography>

                    {error && (
                        <Alert severity="error" sx={{ mb: 2 }}>
                            {error}
                        </Alert>
                    )}

                    <TextField
                        autoFocus
                        margin="dense"
                        label={t('forgotPassword.emailLabel', 'Email Address')}
                        type="email"
                        fullWidth
                        variant="outlined"
                        value={email}
                        onChange={(e) => setEmail(e.target.value)}
                        disabled={loading}
                        required
                        autoComplete="email"
                    />
                </DialogContent>
                <DialogActions sx={{ p: 3, pt: 1 }}>
                    <Button onClick={handleClose} disabled={loading}>
                        {t('common.cancel', 'Cancel')}
                    </Button>
                    <Button
                        type="submit"
                        variant="contained"
                        disabled={loading || !email}
                        startIcon={loading ? <CircularProgress size={20} /> : undefined}
                    >
                        {loading
                            ? t('forgotPassword.sending', 'Sending...')
                            : t('forgotPassword.sendReset', 'Send Reset Link')
                        }
                    </Button>
                </DialogActions>
            </form>
        </Dialog>
    );
};

export default ForgotPasswordDialog;