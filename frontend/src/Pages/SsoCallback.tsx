// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

// Where the server lands the browser after a single sign-on (/login/sso).
// Signed in: take the session from the server (it travels in a short-lived
// HttpOnly cookie, never the URL) and enter the app the way a password login
// does.  Not signed in: say why, with a way back to the login page.

import React, { useEffect, useRef, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router';
import { Alert, Box, Button, CircularProgress, Container, Typography } from '@mui/material';
import type { TFunction } from 'i18next';
import { useTranslation } from 'react-i18next';
import { clearPermissionsCache } from '../Services/permissions';
import { takeSsoSession, type SsoFailure } from '../Services/sso';

const failureMessage = (t: TFunction, reason: SsoFailure): string => {
    switch (reason) {
        case 'denied':
            return t('login.sso.denied', 'Your identity provider signed you in, but there is no active SysManage account for that identity. Ask an administrator to give you access.');
        case 'unavailable':
            return t('login.sso.unavailable', 'Single sign-on is not available on this server.');
        case 'expired':
            return t('login.sso.expired', 'The single sign-on session has expired. Sign in again.');
        case 'mfa_required':
            return t('login.sso.mfaRequired', 'Your identity provider did not confirm multi-factor sign-in. Sign in again using your second factor, or ask an administrator to check the identity provider\'s multi-factor policy.');
        default:
            return t('login.sso.failed', 'Single sign-on did not complete. Try again, or sign in with your password.');
    }
};

const KNOWN: SsoFailure[] = ['denied', 'unavailable', 'failed', 'expired', 'mfa_required'];

const SsoCallback: React.FC = () => {
    const { t } = useTranslation();
    const navigate = useNavigate();
    const [params] = useSearchParams();
    const sent = params.get('error');
    const [failure, setFailure] = useState<SsoFailure | null>(
        sent ? (KNOWN.find(k => k === sent) ?? 'failed') : null,
    );
    // The hand-off is one-shot: React's development double-mount must not
    // spend it twice (the second request would find the cookie gone).
    const taken = useRef(false);

    useEffect(() => {
        if (sent || taken.current) return;
        taken.current = true;
        takeSsoSession()
            .then(session => {
                clearPermissionsCache();
                localStorage.setItem('userid', session.userid);
                localStorage.setItem('bearer_token', session.Authorization);
                globalThis.location.replace('/');
            })
            .catch(() => setFailure('expired'));
    }, [sent]);

    return (
        <Container component="main" maxWidth="sm">
            <Box sx={{ boxShadow: 3, borderRadius: 2, px: 4, py: 6, mt: 8, textAlign: 'center' }}>
                {failure ? (
                    <>
                        <Alert severity="error" sx={{ mb: 3, textAlign: 'left' }}>{failureMessage(t, failure)}</Alert>
                        <Button variant="contained" onClick={() => navigate('/login', { replace: true })}>
                            {t('login.sso.backToLogin', 'Back to sign in')}
                        </Button>
                    </>
                ) : (
                    <>
                        <CircularProgress sx={{ mb: 2 }} />
                        <Typography>{t('login.sso.signingIn', 'Signing you in...')}</Typography>
                    </>
                )}
            </Box>
        </Container>
    );
};

export default SsoCallback;
