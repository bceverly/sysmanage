// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

// "Sign in with <provider>" on the login page -- one button per enabled OIDC
// or SAML provider.  Renders nothing when there are none (or no license), so
// a password-only server's login page is unchanged.

import React, { useEffect, useState } from 'react';
import { Button, Divider, Stack } from '@mui/material';
import LoginIcon from '@mui/icons-material/Login';
import { useTranslation } from 'react-i18next';
import { getSsoProviders, type SsoProvider } from '../../Services/sso';

const SsoButtons: React.FC = () => {
    const { t } = useTranslation();
    const [providers, setProviders] = useState<SsoProvider[]>([]);

    useEffect(() => {
        let live = true;
        getSsoProviders()
            .then(found => { if (live) setProviders(found); })
            .catch(() => { /* no SSO on offer: the password form stands alone */ });
        return () => { live = false; };
    }, []);

    if (providers.length === 0) return null;
    return (
        <Stack spacing={1} sx={{ width: '100%', mt: 2 }}>
            <Divider>{t('login.sso.or', 'or')}</Divider>
            {providers.map(provider => (
                <Button key={provider.id} fullWidth variant="outlined" startIcon={<LoginIcon />}
                    onClick={() => globalThis.location.assign(provider.start_url)}>
                    {t('login.sso.signInWith', 'Sign in with {{name}}', { name: provider.name })}
                </Button>
            ))}
        </Stack>
    );
};

export default SsoButtons;
