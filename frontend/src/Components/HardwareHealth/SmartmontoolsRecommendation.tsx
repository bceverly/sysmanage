// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

// smartmontools where drive health cannot be read (Phase 23.1 S6).  SATA and
// SAS drives on Linux and FreeBSD are read through smartctl; without it they
// are "unknown", never healthy.  An operator installs it on one host or on
// all of them; with Enterprise, an administrator can let the server do it.

import React, { useEffect, useState } from 'react';
import { Alert, Box, Button, FormControlLabel, Stack, Switch, Typography } from '@mui/material';
import { useTranslation } from 'react-i18next';
import type { TFunction } from 'i18next';
import { getUserPermissions, hasPermission, SecurityRoles } from '../../Services/permissions';
import {
    getSmartmontools,
    installSmartmontools,
    setSmartmontoolsAuto,
} from '../../Services/hardwareHealth';
import type { SmartmontoolsStatus, ToolInstall } from '../../Services/hardwareHealth';

/** Manage Hardware Health AND Add Package, as the server requires. */
const useCanInstall = (): boolean => {
    const [can, setCan] = useState(false);
    useEffect(() => {
        void Promise.all([
            hasPermission(SecurityRoles.MANAGE_HARDWARE_HEALTH),
            hasPermission(SecurityRoles.ADD_PACKAGE),
        ])
            .then(([manage, add]) => setCan(manage && add))
            .catch(() => setCan(false));
    }, []);
    return can;
};

export const installText = (t: TFunction, install: ToolInstall | null | undefined): string | null => {
    if (!install) {
        return null;
    }
    if (install.status === 'queued') {
        return t('hardwareHealth.smartmontools.queued', 'Install requested.');
    }
    if (install.status === 'succeeded') {
        return t('hardwareHealth.smartmontools.succeeded', 'Installed. The drives are read at the next report.');
    }
    return t('hardwareHealth.smartmontools.failed', 'Install failed: {{error}}', { error: install.last_error ?? '' });
};

interface HostProps {
    hostId: string;
    install: ToolInstall | null;
    onChanged: () => void;
}

const HostAlert: React.FC<HostProps> = ({ hostId, install, onChanged }) => {
    const { t } = useTranslation();
    const canInstall = useCanInstall();
    const [error, setError] = useState(false);
    const requestInstall = async () => {
        try {
            await installSmartmontools([hostId]);
            setError(false);
            onChanged();
        } catch {
            setError(true);
        }
    };
    return (
        <Alert
            severity="info"
            sx={{ mb: 2 }}
            action={canInstall && install?.status !== 'queued' ? (
                <Button color="inherit" size="small" onClick={() => void requestInstall()}>
                    {t('hardwareHealth.smartmontools.install', 'Install smartmontools')}
                </Button>
            ) : undefined}
        >
            {t('hardwareHealth.smartmontools.hostNeeds',
                'Some drives on this host can only be read with smartmontools, which is not installed.')}
            {installText(t, install) && <Box>{installText(t, install)}</Box>}
            {error && <Box>{t('hardwareHealth.smartmontools.installError', 'The install could not be requested.')}</Box>}
        </Alert>
    );
};

/** Only on a host it is recommended for (no permission lookups otherwise). */
export const HostSmartmontools: React.FC<HostProps & { recommended: boolean }> = ({ recommended, ...props }) =>
    recommended ? <HostAlert {...props} /> : null;

const AutoSwitch: React.FC<{ status: SmartmontoolsStatus; onChanged: () => void }> = ({ status, onChanged }) => {
    const { t } = useTranslation();
    const [isAdmin, setIsAdmin] = useState(false);
    const [error, setError] = useState(false);
    useEffect(() => {
        void getUserPermissions()
            .then(p => setIsAdmin(Boolean(p.is_admin)))
            .catch(() => setIsAdmin(false));
    }, []);
    const toggle = async (auto: boolean) => {
        try {
            await setSmartmontoolsAuto(auto);
            setError(false);
            onChanged();
        } catch {
            setError(true);
        }
    };
    return (
        <Box>
            <FormControlLabel
                control={(
                    <Switch
                        checked={status.auto}
                        disabled={!isAdmin || (!status.licensed && !status.auto)}
                        onChange={e => void toggle(e.target.checked)}
                    />
                )}
                label={t('hardwareHealth.smartmontools.auto', 'Install automatically wherever it is needed')}
            />
            {!status.licensed && (
                <Typography variant="caption" color="text.secondary" component="div">
                    {t('hardwareHealth.smartmontools.autoLicense',
                        'Automatic installation requires a SysManage Enterprise license.')}
                </Typography>
            )}
            {error && (
                <Typography variant="caption" color="error" component="div">
                    {t('hardwareHealth.smartmontools.autoError', 'The setting could not be saved.')}
                </Typography>
            )}
        </Box>
    );
};

export const FleetSmartmontools: React.FC<{ onChanged: () => void }> = ({ onChanged }) => {
    const { t } = useTranslation();
    const canInstall = useCanInstall();
    const [status, setStatus] = useState<SmartmontoolsStatus | null>(null);
    const [message, setMessage] = useState<string | null>(null);

    const load = async () => {
        try {
            setStatus(await getSmartmontools());
        } catch {
            setStatus(null);
        }
    };
    useEffect(() => {
        void load();
    }, []);

    if (!status || (status.hosts.length === 0 && !status.auto)) {
        return null;
    }
    const waiting = status.hosts.filter(h => h.install?.status !== 'queued');
    const installAll = async () => {
        try {
            const result = await installSmartmontools(waiting.map(h => h.host_id));
            setMessage(t('hardwareHealth.smartmontools.queuedHosts', 'Hosts where the install was requested: {{n}}', { n: result.queued }));
            await load();
            onChanged();
        } catch {
            setMessage(t('hardwareHealth.smartmontools.installError', 'The install could not be requested.'));
        }
    };
    return (
        <Alert severity="info" sx={{ mb: 2 }}>
            <Stack spacing={1}>
                <Typography variant="body2">
                    {t('hardwareHealth.smartmontools.fleetNeeds',
                        'Hosts whose drives can only be read with smartmontools, which is not installed: {{n}}',
                        { n: status.hosts.length })}
                </Typography>
                {status.hosts.length > 0 && (
                    <Typography variant="caption" color="text.secondary">
                        {status.hosts.map(h => h.fqdn).join(', ')}
                    </Typography>
                )}
                {canInstall && waiting.length > 0 && (
                    <Box>
                        <Button size="small" variant="outlined" onClick={() => void installAll()}>
                            {t('hardwareHealth.smartmontools.installAll', 'Install smartmontools on these hosts')}
                        </Button>
                    </Box>
                )}
                {message && <Typography variant="body2">{message}</Typography>}
                {canInstall && <AutoSwitch status={status} onChanged={() => void load()} />}
            </Stack>
        </Alert>
    );
};
