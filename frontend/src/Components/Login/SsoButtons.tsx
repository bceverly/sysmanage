// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

// "Sign in with <provider>" on the login page's second step -- one button per
// provider the email's domain may use (see discoverLoginMethods).  Renders
// nothing when there are none, so a password-only login is unchanged.

import React from 'react';
import { Button, Divider, Stack } from '@mui/material';
import LoginIcon from '@mui/icons-material/Login';
import { useTranslation } from 'react-i18next';
import type { SsoProvider } from '../../Services/sso';

const SsoButtons: React.FC<{ providers: SsoProvider[]; divider?: boolean }> = ({
    providers,
    divider = true,
}) => {
    const { t } = useTranslation();
    if (providers.length === 0) return null;
    return (
        <Stack spacing={1} sx={{ width: '100%', mt: 2 }}>
            {divider && <Divider>{t('login.sso.or', 'or')}</Divider>}
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
