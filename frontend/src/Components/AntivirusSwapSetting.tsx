// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

/**
 * Settings > Antivirus: "Add swap to hosts with too little memory for ClamAV" (off until
 * turned on).  ClamAV needs about 3.5 GB of memory and swap; with this on,
 * SysManage adds a swap file to a smaller Linux or BSD host first, then
 * deploys ClamAV.  Saved the moment it is switched.
 */

import React, { useEffect, useState } from 'react';
import { Alert, Card, CardContent, FormControlLabel, Stack, Switch, Typography } from '@mui/material';
import { useTranslation } from 'react-i18next';

import axiosInstance from '../Services/api';

const URL = '/api/v1/antivirus-defaults/swap';

const AntivirusSwapSetting: React.FC<{ canManage: boolean }> = ({ canManage }) => {
    const { t } = useTranslation();
    const [enabled, setEnabled] = useState<boolean | null>(null);
    const [saving, setSaving] = useState(false);
    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
        axiosInstance.get<{ enabled: boolean }>(URL)
            .then(response => setEnabled(Boolean(response.data.enabled)))
            .catch(() => setEnabled(false));
    }, []);

    const change = async (value: boolean) => {
        setSaving(true);
        setError(null);
        try {
            const response = await axiosInstance.put<{ enabled: boolean }>(URL, { enabled: value });
            setEnabled(Boolean(response.data.enabled));
        } catch {
            setError(t('antivirus.swap.saveError', 'The setting could not be saved.'));
        } finally {
            setSaving(false);
        }
    };

    return (
        <Card sx={{ mt: 3 }} data-testid="antivirus-swap-setting">
            <CardContent>
                <Stack spacing={1}>
                    <Typography variant="h6" component="h3">
                        {t('antivirus.swap.title', 'Hosts with little memory')}
                    </Typography>
                    <Typography variant="body2" color="text.secondary">
                        {t('antivirus.swap.help',
                            'ClamAV needs about 3.5 GB of memory and swap combined, and is not deployed to a host with less. With this on, SysManage first adds a swap file to such a Linux or BSD host (whole GB, at most 8 GB, never on ZFS or btrfs, and only where enough disk space stays free), then deploys ClamAV.')}
                    </Typography>
                    <FormControlLabel
                        control={
                            <Switch
                                checked={Boolean(enabled)}
                                disabled={!canManage || enabled === null || saving}
                                onChange={event => void change(event.target.checked)}
                                slotProps={{ input: { 'aria-label': t('antivirus.swap.label', 'Add swap to hosts with too little memory for ClamAV') } }}
                            />
                        }
                        label={t('antivirus.swap.label', 'Add swap to hosts with too little memory for ClamAV')}
                    />
                    {error && <Alert severity="error">{error}</Alert>}
                </Stack>
            </CardContent>
        </Card>
    );
};

export default AntivirusSwapSetting;
