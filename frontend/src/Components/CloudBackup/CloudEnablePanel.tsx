// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

// "Enable iCloud backup" (ROADMAP 24.12): one push installs the pinned
// icloudpd on the backup storage host and prepares the place for the photos
// under the storage path.  Pressing it again repairs or upgrades.  It runs on
// the storage host only, and the panel says which one.

import React, { useState } from 'react';
import { Alert, Box, Button, Chip, CircularProgress, Stack, Typography } from '@mui/material';
import { useTranslation } from 'react-i18next';
import { enableCloudBackup } from '../../Services/cloudBackup';
import type { CloudOverview } from '../../Services/cloudBackup';
import { apiDetail, formatTime } from '../Backups/backupLabels';
import { reasonText } from './cloudBackupLabels';

interface Props {
    data: CloudOverview;
    canManage: boolean;
    onChanged: () => void;
}

const CloudEnablePanel: React.FC<Props> = ({ data, canManage, onChanged }) => {
    const { t } = useTranslation();
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState('');
    const host = data.storage_host?.fqdn ?? '';
    const enable = data.enable ?? null;
    const running = enable?.status === 'running';
    const unsupported = data.support?.supported === false;

    const press = async () => {
        setBusy(true);
        setError('');
        try {
            await enableCloudBackup();
            onChanged();
        } catch (err) {
            setError(apiDetail(err, t('cloudBackup.enable.failedToStart', 'Enable iCloud backup could not be started.')));
        } finally {
            setBusy(false);
        }
    };

    return (
        <Box sx={{ mb: 2 }}>
            <Typography variant="body2" sx={{ mb: 1 }}>
                {t('cloudBackup.enable.where',
                    'Runs on your backup storage host, {{host}}. iCloud Photos are downloaded straight into the backup storage, beside the hosts\' backups and never inside one.',
                    { host })}
            </Typography>
            <Stack direction="row" spacing={2} alignItems="center" sx={{ flexWrap: 'wrap', rowGap: 1 }}>
                {data.enabled && (
                    <Chip color="success" size="small" label={t('cloudBackup.enable.on', 'Enabled: icloudpd {{version}}',
                        { version: enable?.tool_version ?? '' })} />
                )}
                {running && (
                    <Stack direction="row" spacing={1} alignItems="center">
                        <CircularProgress size={16} />
                        <Typography variant="body2">
                            {t('cloudBackup.enable.running', 'Installing icloudpd and preparing the storage on {{host}}...', { host })}
                        </Typography>
                    </Stack>
                )}
                {canManage && !unsupported && (
                    <Button variant={data.enabled ? 'outlined' : 'contained'} disabled={busy || running}
                        onClick={() => void press()} data-testid="cloud-enable">
                        {data.enabled
                            ? t('cloudBackup.enable.again', 'Repair or upgrade')
                            : t('cloudBackup.enable.button', 'Enable iCloud backup')}
                    </Button>
                )}
            </Stack>
            {unsupported && (
                <Alert severity="info" sx={{ mt: 1 }}>{reasonText(t, data.support?.reason ?? null, null)}</Alert>
            )}
            {enable?.status === 'failed' && (
                <Alert severity="error" sx={{ mt: 1 }}>
                    {reasonText(t, enable.reason, null)}
                    {enable.detail && (
                        // eslint-disable-next-line i18next/no-literal-string -- the tool's own output
                        <Box component="pre" sx={{ whiteSpace: 'pre-wrap', fontSize: 12, mt: 1, mb: 0 }}>{enable.detail}</Box>
                    )}
                </Alert>
            )}
            {data.enabled && enable?.cloud_root && (
                <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 1 }}>
                    {t('cloudBackup.enable.root', 'Photos are kept under {{path}} (prepared {{when}}).',
                        { path: enable.cloud_root, when: formatTime(enable.finished_at) })}
                </Typography>
            )}
            {error && <Alert severity="error" sx={{ mt: 1 }}>{error}</Alert>}
        </Box>
    );
};

export default CloudEnablePanel;
