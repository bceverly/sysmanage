// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

// Turn discovery on or off for the tenant (Phase 21.6 S2/S3).  Only for the
// Manage Network Discovery role; everyone else sees the state read-only.

import React, { useState } from 'react';
import {
    Button,
    Card,
    CardContent,
    FormControl,
    FormControlLabel,
    InputLabel,
    MenuItem,
    Select,
    Stack,
    Switch,
    Typography,
} from '@mui/material';
import { useTranslation } from 'react-i18next';
import { RETENTION_CHOICES, type DiscoveryPolicy } from '../../Services/assetDiscoveryService';
import { formatSeen } from './discoveryLabels';

const INTERVALS = [60, 300, 900, 3600];

interface Props {
    policy: DiscoveryPolicy;
    canManage: boolean;
    onSave: (enabled: boolean, interval: number, sweepEnabled: boolean, retentionDays: number) => Promise<void>;
}

const DiscoveryPolicyCard: React.FC<Props> = ({ policy, canManage, onSave }) => {
    const { t } = useTranslation();
    const [enabled, setEnabled] = useState(policy.enabled);
    const [interval, setIntervalValue] = useState(policy.report_interval_seconds);
    const [sweeps, setSweeps] = useState(policy.sweep_enabled);
    const [retention, setRetention] = useState(policy.retention_days ?? 30);
    const [busy, setBusy] = useState(false);
    const dirty = enabled !== policy.enabled
        || interval !== policy.report_interval_seconds
        || sweeps !== policy.sweep_enabled
        || retention !== (policy.retention_days ?? 30);
    const intervalLabel = (seconds: number) =>
        seconds < 3600
            ? t('assetDiscovery.policy.minutes', 'Every {{count}} minutes', { count: seconds / 60 })
            : t('assetDiscovery.policy.hour', 'Every hour');

    return (
        <Card variant="outlined" sx={{ mb: 2 }}>
            <CardContent>
                <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2} alignItems={{ sm: 'center' }}>
                    <FormControlLabel
                        control={<Switch checked={enabled} disabled={!canManage} onChange={e => setEnabled(e.target.checked)} />}
                        label={t('assetDiscovery.policy.enabled', 'Agents listen for devices on their networks')} />
                    <FormControl size="small" sx={{ minWidth: 200 }} disabled={!canManage}>
                        <InputLabel id="discovery-interval">{t('assetDiscovery.policy.interval', 'Report')}</InputLabel>
                        <Select labelId="discovery-interval" value={interval}
                            label={t('assetDiscovery.policy.interval', 'Report')}
                            onChange={e => setIntervalValue(Number(e.target.value))}>
                            {INTERVALS.map(s => <MenuItem key={s} value={s}>{intervalLabel(s)}</MenuItem>)}
                        </Select>
                    </FormControl>
                    <FormControl size="small" sx={{ minWidth: 220 }} disabled={!canManage}>
                        <InputLabel id="discovery-retention">{t('assetDiscovery.policy.retention', 'Forget devices not seen for')}</InputLabel>
                        <Select labelId="discovery-retention" value={retention}
                            label={t('assetDiscovery.policy.retention', 'Forget devices not seen for')}
                            onChange={e => setRetention(Number(e.target.value))}>
                            {RETENTION_CHOICES.map(d => (
                                <MenuItem key={d} value={d}>{t('assetDiscovery.policy.days', '{{count}} days', { count: d })}</MenuItem>
                            ))}
                        </Select>
                    </FormControl>
                    <FormControlLabel
                        control={<Switch checked={sweeps} disabled={!canManage || !enabled} onChange={e => setSweeps(e.target.checked)} />}
                        label={t('assetDiscovery.policy.sweeps', 'Allow active sweeps')} />
                    {canManage && (
                        <Button variant="contained" disabled={!dirty || busy}
                            onClick={async () => { setBusy(true); try { await onSave(enabled, interval, sweeps, retention); } finally { setBusy(false); } }}>
                            {t('common.save', 'Save')}
                        </Button>
                    )}
                </Stack>
                {policy.updated_by && (
                    <Typography variant="caption" color="text.secondary">
                        {t('assetDiscovery.policy.lastChanged', 'Last changed by {{who}} on {{when}}', { who: policy.updated_by, when: formatSeen(policy.updated_at) })}
                    </Typography>
                )}
            </CardContent>
        </Card>
    );
};

export default DiscoveryPolicyCard;
