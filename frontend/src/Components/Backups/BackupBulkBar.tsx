// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

// "Back up now" for the hosts picked in the Backups table (ROADMAP 24.4).
// The server starts as many as the target's concurrency cap allows and the
// rest as running captures finish, so the outcome says how many started,
// how many are waiting for a slot, and which were skipped and why.
//
// "Equip selected for backup" has each picked host that is not equipped
// install restate (Phase 24); "Set up backups for selected" gives each picked
// equipped host without a policy the default one (2026-10-29).  Each action
// goes only to the picked hosts it applies to.

import React, { useState } from 'react';
import { Alert, Box, Button, Stack, Typography } from '@mui/material';
import { useTranslation } from 'react-i18next';
import type { TFunction } from 'i18next';
import AsyncButton from '../AsyncButton';
import { bulkBackupNow, bulkEquipBackup, bulkSetupBackups } from '../../Services/backups';
import type { BackupHost, BulkBackupResult, BulkEquipResult, BulkSetupResult } from '../../Services/backups';
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
        case 'has_policy':
            return t('backups.bulk.skipHasPolicy', 'Already has a backup policy');
        case 'not_equipped':
            return t('backups.bulk.skipNotEquipped', 'Not equipped for backup yet');
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
    const [setupResult, setSetupResult] = useState<BulkSetupResult | null>(null);
    const [error, setError] = useState<string | null>(null);
    const picked = new Set(selected);
    const toEquip = rows.filter(r => picked.has(r.host_id) && !r.equipped).map(r => r.host_id);
    const toBackUp = rows.filter(r => picked.has(r.host_id) && r.equipped && r.policy).map(r => r.host_id);
    const toSetUp = rows.filter(r => picked.has(r.host_id) && r.equipped && !r.policy).map(r => r.host_id);

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

    const setUp = async () => {
        setError(null);
        try {
            setSetupResult(await bulkSetupBackups(toSetUp));
            onClear();
            onDone();
        } catch (err) {
            setSetupResult(null);
            setError(apiDetail(err, t('backups.bulk.setupError', 'Backups could not be set up.')));
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
                    {toSetUp.length > 0 && (
                        <AsyncButton size="small" variant="outlined" onClick={setUp}
                            busyLabel={t('backups.hosts.starting', 'Starting...')}>
                            {t('backups.bulk.setupSelected', 'Set up backups for selected ({{n}})', { n: toSetUp.length })}
                        </AsyncButton>
                    )}
                    <Button size="small" onClick={onClear}>{t('common.clearSelection', 'Clear selection')}</Button>
                </Stack>
            )}
            {error && <Alert severity="error" onClose={() => setError(null)}>{error}</Alert>}
            {setupResult && (
                <Alert severity={setupResult.skipped.length ? 'warning' : 'success'} onClose={() => setSetupResult(null)}>
                    {t('backups.bulk.setupResult',
                        'Set up with the default policy: {{created}}. Skipped: {{skipped}}. Choose the services to pause on each host with Configure.', {
                            created: setupResult.created,
                            skipped: setupResult.skipped.length,
                        })}
                    {setupResult.skipped.map(s => (
                        <Typography key={s.host_id} variant="body2">
                            {s.fqdn ?? s.host_id}: {skipLabel(t, s.reason)}
                        </Typography>
                    ))}
                </Alert>
            )}
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
