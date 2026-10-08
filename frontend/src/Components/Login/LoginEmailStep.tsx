// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

// Step one of the login page: the email address.  The server says how that
// address can sign in (password, and which single sign-on providers -- by
// the address's domain, see discoverLoginMethods); step two offers exactly
// that.  Replaced a login page that listed only server-wide providers, which
// left a tenant's own identity provider reachable only through a ?tenant=
// URL (2026-10-07).

import React, { useState } from 'react';
import { Box, Button, CircularProgress, InputAdornment, Link, TextField, Typography } from '@mui/material';
import AccountCircle from '@mui/icons-material/AccountCircle';
import { useTranslation } from 'react-i18next';
import { discoverLoginMethods, type LoginMethods } from '../../Services/sso';

interface EmailStepProps {
    email: string;
    onEmailChange: (email: string) => void;
    onMethods: (methods: LoginMethods) => void;
}

export const LoginEmailStep: React.FC<EmailStepProps> = ({ email, onEmailChange, onMethods }) => {
    const { t } = useTranslation();
    const [checking, setChecking] = useState(false);

    const submit = (e: React.SyntheticEvent) => {
        e.preventDefault();
        if (email.trim() === '') return;
        setChecking(true);
        discoverLoginMethods(email.trim())
            .then(onMethods)
            // The lookup failing must never lock anyone out: offer the password.
            .catch(() => onMethods({ password: true, providers: [] }))
            .finally(() => setChecking(false));
    };

    return (
        <Box component="form" onSubmit={submit} noValidate sx={{ mt: 1, width: '100%' }}>
            <TextField
                margin="normal"
                required
                fullWidth
                id="userid"
                label={t('login.username')}
                name="userid"
                value={email}
                autoComplete="email"
                autoFocus
                onChange={(e) => onEmailChange(e.target.value)}
                slotProps={{
                    input: {
                        startAdornment: (
                            <InputAdornment position="start">
                                <AccountCircle />
                            </InputAdornment>
                        ),
                    },
                }}
            />
            <Button
                type="submit"
                fullWidth
                variant="contained"
                sx={{ mt: 3, mb: 2 }}
                disabled={checking || email.trim() === ''}
                startIcon={checking ? <CircularProgress size={20} color="inherit" /> : undefined}
            >
                {t('login.next', 'Next')}
            </Button>
        </Box>
    );
};

/** Step two's reminder of whose sign-in this is, with a way back. */
export const LoginIdentity: React.FC<{ email: string; onChange: () => void }> = ({ email, onChange }) => {
    const { t } = useTranslation();
    return (
        <Box sx={{ width: '100%', textAlign: 'center', mb: 1 }}>
            <Typography variant="body2" data-testid="login-identity">
                {t('login.signingInAs', 'Signing in as {{email}}', { email })}
            </Typography>
            <Link component="button" type="button" variant="body2" onClick={onChange}>
                {t('login.useAnotherEmail', 'Use a different email')}
            </Link>
        </Box>
    );
};
