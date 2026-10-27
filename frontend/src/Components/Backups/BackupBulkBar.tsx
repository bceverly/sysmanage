// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

// "Back up now" for the hosts picked in the Backups table (ROADMAP 24.4).
// The server starts as many as the target's concurrency cap allows and the
// rest as running captures finish, so the outcome says how many started,
// how many are waiting for a slot, and which were skipped and why.
//
// "Equip selected for backup" has each picked host that is not equipped
// install restate (Phase 24); each action goes only to the picked hosts it
// applies to.

import React, { useState } from 'react';
import { Alert, Box, Button, Stack, Typography } from '@mui/material';
import { useTranslation } from 'react-i18next';
import type { TFunction } from 'i18next';
import AsyncButton from '../AsyncButton';
import { bulkBackupNow, bulkEquipBackup } from '../../Services/backups';
import type { BackupHost, BulkBackupResult, BulkEquipResult } from '../../Services/backups';
import { apiDetail, reasonLabel } from './backupLabels';

/** Why a picked host was not backed up, as something to act on. */
export const skipLabel = (t: TFunction, reason: string): string => {
    switch (reason) {
        case 'no_policy':
            return t('backups.bulk.skipNoPolicy', 'No backup policy');
        case 'not_configured':
            return t('backups.bulk.skipNotConfigured', 'Job files not confirmed by the host yet');
        case 'running':
            return t('backups.bulk.skipRunning', 'Already backing up');
        case 'no_host':
            return t('backups.bulk.skipNoHost', 'Host not found');
        case 'equipped':
            return t('backups.bulk.skipEquipped', 'Already equipped');
        case 'in_progress':
            return t('backups.bulk.skipEquipping', 'Already equipping');
        case 'not_applicable':
            return t('backups.bulk.skipEquipPlatform', 'restate has no package the agent can install here');
        default:
            return reasonLabel(t, reason);
    }
};

const BackupBulkBar: React.FC<{
    selected: string[];
    rows: BackupHost[];
    onClear: () => void;
    onDone: () => void;
}> = ({ selected, rows, onClear, onDone }) => {
    const { t } = useTranslation();
    const [result, setResult] = useState<BulkBackupResult | null>(null);
    const [equipResult, setEquipResult] = useState<BulkEquipResult | null>(null);
    const [error, setError] = useState<string | null>(null);
    const picked = new Set(selected);
    const toEquip = rows.filter(r => picked.has(r.host_id) && !r.equipped).map(r => r.host_id);
    const toBackUp = rows.filter(r => picked.has(r.host_id) && r.equipped).map(r => r.host_id);

    const run = async () => {
        setError(null);
        try {
            setResult(await bulkBackupNow(toBackUp));
            onClear();
            onDone();
        } catch (err) {
            setResult(null);
            setError(apiDetail(err, t('backups.bulk.error', 'The backups could not be requested.')));
        }
    };

    const equip = async () => {
        setError(null);
        try {
            setEquipResult(await bulkEquipBackup(toEquip));
            onClear();
            onDone();
        } catch (err) {
            setEquipResult(null);
            setError(apiDetail(err, t('backups.bulk.equipError', 'Equip for backup could not be requested.')));
        }
    };

    return (
        <Box sx={{ mb: 1 }}>
            {selected.length > 0 && (
                <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 1 }}>
                    <Typography variant="body2">
                        {t('backups.bulk.selected', 'Hosts selected: {{n}}', { n: selected.length })}
                    </Typography>
                    {toBackUp.length > 0 && (
                        <AsyncButton size="small" variant="contained" onClick={run}
                            busyLabel={t('backups.hosts.starting', 'Starting...')}>
                            {t('backups.bulk.backupSelected', 'Back up selected')}
                        </AsyncButton>
                    )}
                    {toEquip.length > 0 && (
                        <AsyncButton size="small" variant="outlined" onClick={equip}
                            busyLabel={t('backups.hosts.starting', 'Starting...')}>
                            {t('backups.bulk.equipSelected', 'Equip selected for backup ({{n}})', { n: toEquip.length })}
                        </AsyncButton>
                    )}
                    <Button size="small" onClick={onClear}>{t('common.clearSelection', 'Clear selection')}</Button>
                </Stack>
            )}
            {error && <Alert severity="error" onClose={() => setError(null)}>{error}</Alert>}
            {equipResult && (
                <Alert severity={equipResult.skipped.length ? 'warning' : 'success'} onClose={() => setEquipResult(null)}>
                    {t('backups.bulk.equipResult', 'Equipping: {{started}}. Skipped: {{skipped}}.', {
                        started: equipResult.started,
                        skipped: equipResult.skipped.length,
                    })}
                    {equipResult.skipped.map(s => (
                        <Typography key={s.host_id} variant="body2">
                            {s.fqdn ?? s.host_id}: {skipLabel(t, s.reason)}
                        </Typography>
                    ))}
                </Alert>
            )}
            {result && (
                <Alert severity={result.skipped.length ? 'warning' : 'success'} onClose={() => setResult(null)}>
                    {t('backups.bulk.result', 'Started: {{started}}. Waiting for a free slot: {{waiting}}. Skipped: {{skipped}}.', {
                        started: result.started,
                        waiting: result.waiting,
                        skipped: result.skipped.length,
                    })}
                    {result.skipped.map(s => (
                        <Typography key={s.host_id} variant="body2">
                            {s.fqdn ?? s.host_id}: {skipLabel(t, s.reason)}
                        </Typography>
                    ))}
                </Alert>
            )}
        </Box>
    );
};

export default BackupBulkBar;
