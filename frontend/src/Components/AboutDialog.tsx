// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

import React, { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
    Box,
    Button,
    Dialog,
    DialogActions,
    DialogContent,
    DialogTitle,
    Link,
    Typography,
} from '@mui/material';

/** The fields of GET /api/v1/server-info the dialog shows. */
export interface AboutServerInfo {
    version?: string | null;
    license_tier?: string | null;
    role?: string | null;
    federation_role?: string | null;
}

interface AboutDialogProps {
    open: boolean;
    onClose: () => void;
    // The Navbar already fetched server-info; when it did not (or failed),
    // the dialog asks once itself on open.
    serverInfo?: AboutServerInfo | null;
}

// Not translated: the product name, the copyright line and the docs URL.
const PRODUCT = 'SysManage';
const COPYRIGHT = 'Copyright (c) 2024-2026 Bryan Everly';
const DOCS_URL = 'https://sysmanage.org';

// Edition names are product names: shown as-is in every language.
const EDITIONS: Record<string, string> = {
    community: 'Community',
    professional: 'Professional',
    enterprise: 'Enterprise',
};

/** "3.11.0.11+ppa1~resolute1" -> "3.11.0.11": the release number without
 *  the packaging suffix (+ppa..., -1, ~rc). */
export const shortVersion = (version: string): string =>
    version.split(/[+~-]/)[0];

const AboutDialog: React.FC<AboutDialogProps> = ({ open, onClose, serverInfo }) => {
    const { t } = useTranslation();
    const [fetched, setFetched] = useState<AboutServerInfo | null>(null);

    useEffect(() => {
        if (!open || serverInfo?.version || fetched) return;
        let cancelled = false;
        fetch('/api/v1/server-info')
            .then(r => (r.ok ? r.json() : null))
            .then(info => { if (!cancelled && info) setFetched(info); })
            .catch(() => { /* the dialog shows "unknown" */ });
        return () => { cancelled = true; };
    }, [open, serverInfo, fetched]);

    const info = serverInfo?.version ? serverInfo : fetched;
    const version = info?.version || '';
    const unknown = t('about.unknown', 'Unknown');
    const row = (label: string, value: React.ReactNode, testId?: string) => (
        <Box sx={{ display: 'flex', gap: 1, mb: 0.5 }}>
            <Typography variant="body2" color="text.secondary" sx={{ minWidth: 140 }}>
                {label}
            </Typography>
            <Typography variant="body2" data-testid={testId}>{value}</Typography>
        </Box>
    );

    return (
        <Dialog open={open} onClose={onClose} maxWidth="xs" fullWidth>
            <DialogTitle>{t('about.title', 'About SysManage')}</DialogTitle>
            <DialogContent>
                <Typography variant="h6" gutterBottom>{PRODUCT}</Typography>
                {row(
                    t('about.serverVersion', 'Server version'),
                    version ? shortVersion(version) : unknown,
                    'about-version',
                )}
                {version && shortVersion(version) !== version
                    && row(t('about.serverBuild', 'Server build'), version, 'about-build')}
                {info?.license_tier
                    && row(t('about.edition', 'Edition'), EDITIONS[info.license_tier] || info.license_tier, 'about-edition')}
                {info?.role && info.role !== 'standard'
                    && row(t('about.airgapRole', 'Air-gap role'), info.role)}
                {info?.federation_role && info.federation_role !== 'none'
                    && row(t('about.federationRole', 'Federation role'), info.federation_role)}
                <Box sx={{ mt: 2 }}>
                    <Typography variant="body2">{COPYRIGHT}</Typography>
                    <Typography variant="body2">
                        {t('about.license', 'Licensed under {{license}}', { license: 'AGPL-3.0' })}
                    </Typography>
                    <Link href={DOCS_URL} target="_blank" rel="noopener noreferrer" variant="body2">
                        {DOCS_URL}
                    </Link>
                </Box>
            </DialogContent>
            <DialogActions>
                <Button onClick={onClose}>{t('common.close', 'Close')}</Button>
            </DialogActions>
        </Dialog>
    );
};

export default AboutDialog;
