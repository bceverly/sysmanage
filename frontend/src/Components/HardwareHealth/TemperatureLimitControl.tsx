// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

// A host's own temperature warning limit (2026-10-19): for machines that run
// hot by design -- laptops serving with their lids closed sit at their CPU's
// "high" mark all day.  Every temperature sensor on the host is then judged
// against this instead of the limit its hardware declares; the hardware's
// critical limit still applies.  The server re-judges from the next report.

import React, { useEffect, useState } from 'react';
import { Alert, Stack, TextField, Typography } from '@mui/material';
import { useTranslation } from 'react-i18next';
import AsyncButton from '../AsyncButton';
import { setTemperatureLimit } from '../../Services/hardwareHealth';
import { hasPermission, SecurityRoles } from '../../Services/permissions';

// Keep equal to LIMIT_RANGE_C in backend/services/hardware_temperature_limit.py.
const RANGE_C: [number, number] = [30, 125];

const parsed = (text: string): number | null => {
    const value = Number(text);
    if (text.trim() === '' || !Number.isFinite(value)) {
        return null;
    }
    return value >= RANGE_C[0] && value <= RANGE_C[1] ? value : null;
};

const TemperatureLimitControl: React.FC<{
    hostId: string;
    limit: number | null;
    onChanged: () => void;
}> = ({ hostId, limit, onChanged }) => {
    const { t } = useTranslation();
    const [text, setText] = useState(limit === null ? '' : String(limit));
    const [error, setError] = useState<string | null>(null);
    const [canManage, setCanManage] = useState(false);

    useEffect(() => {
        setText(limit === null ? '' : String(limit));
    }, [limit]);

    useEffect(() => {
        void hasPermission(SecurityRoles.MANAGE_HARDWARE_HEALTH)
            .then(setCanManage)
            .catch(() => setCanManage(false));
    }, []);

    const save = async (value: number | null) => {
        setError(null);
        try {
            await setTemperatureLimit(hostId, value);
            onChanged();
        } catch {
            setError(t('hardwareHealth.tempLimit.saveError', 'The limit could not be saved.'));
        }
    };

    const value = parsed(text);
    const invalid = text.trim() !== '' && value === null;
    return (
        <Stack spacing={1} sx={{ mt: 2 }}>
            <Typography variant="subtitle2">
                {t('hardwareHealth.tempLimit.title', 'Temperature warning limit')}
            </Typography>
            <Typography variant="body2" color="text.secondary">
                {limit === null
                    ? t('hardwareHealth.tempLimit.none', 'Each sensor warns at the limit its hardware declares.')
                    : t('hardwareHealth.tempLimit.active', 'This host warns at {{limit}} C instead of each sensor\'s own limit.', { limit })}
            </Typography>
            {canManage && (
            <Stack direction="row" spacing={1} alignItems="flex-start">
                <TextField
                    size="small"
                    type="number"
                    label={t('hardwareHealth.tempLimit.label', 'Warn at (C)')}
                    value={text}
                    onChange={e => setText(e.target.value)}
                    error={invalid}
                    helperText={invalid ? t('hardwareHealth.tempLimit.invalid', 'Enter a temperature between 30 and 125 C.') : ' '}
                    slotProps={{ htmlInput: { min: RANGE_C[0], max: RANGE_C[1], step: 1 } }}
                    sx={{ width: 160 }}
                />
                <AsyncButton
                    variant="contained"
                    size="small"
                    disabled={value === null || value === limit}
                    onClick={() => save(value)}
                    sx={{ mt: 0.5 }}
                >
                    {t('hardwareHealth.tempLimit.save', 'Save')}
                </AsyncButton>
                {limit !== null && (
                    <AsyncButton size="small" onClick={() => save(null)} sx={{ mt: 0.5 }}>
                        {t('hardwareHealth.tempLimit.clear', 'Use device limits')}
                    </AsyncButton>
                )}
            </Stack>
            )}
            <Typography variant="caption" color="text.secondary">
                {t(
                    'hardwareHealth.tempLimit.help',
                    'The hardware\'s critical limit always still applies. A change takes effect at the host\'s next report; past events are not rewritten.',
                )}
            </Typography>
            {error && <Alert severity="error">{error}</Alert>}
        </Stack>
    );
};

export default TemperatureLimitControl;
