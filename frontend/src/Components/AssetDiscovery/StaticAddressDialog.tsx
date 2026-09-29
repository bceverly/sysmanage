// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

// Register a STATIC address as known (Phase 21.6 S5): a VIP, a load balancer,
// a virtual router.  Keyed by IP, so it covers whatever device holds that
// address -- which is exactly why it is only for addresses that never change:
// an ordinary DHCP device registered this way reappears after its next lease.

import React, { useState } from 'react';
import {
    Alert,
    Button,
    Dialog,
    DialogActions,
    DialogContent,
    DialogTitle,
    FormControl,
    InputLabel,
    MenuItem,
    Select,
    TextField,
} from '@mui/material';
import { useTranslation } from 'react-i18next';
import { EXCLUSION_CATEGORIES, type ExclusionCategory } from '../../Services/assetDiscoveryService';
import { categoryLabel } from './discoveryLabels';

interface Props {
    open: boolean;
    onClose: () => void;
    onConfirm: (address: string, category: ExclusionCategory, reason: string) => Promise<void>;
}

const errorMessage = (err: unknown): string | undefined =>
    (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;

const StaticAddressDialog: React.FC<Props> = ({ open, onClose, onConfirm }) => {
    const { t } = useTranslation();
    const [address, setAddress] = useState('');
    const [category, setCategory] = useState<ExclusionCategory>('virtual_address');
    const [reason, setReason] = useState('');
    const [error, setError] = useState<string | null>(null);
    const valid = address.trim().length > 0 && reason.trim().length >= 3;

    const submit = async () => {
        setError(null);
        try {
            await onConfirm(address.trim(), category, reason.trim());
            onClose();
        } catch (err: unknown) {
            setError(errorMessage(err) ?? t('assetDiscovery.address.error', 'The address could not be registered.'));
        }
    };

    return (
        <Dialog open={open} onClose={onClose} fullWidth maxWidth="sm">
            <DialogTitle>{t('assetDiscovery.address.title', 'Register a static address')}</DialogTitle>
            <DialogContent>
                <Alert severity="warning" sx={{ mb: 2 }}>
                    {t('assetDiscovery.address.warning', 'Only for addresses that never change, such as a virtual IP or a load balancer. It covers whatever device holds this address, so an ordinary device given addresses by DHCP will reappear after its next lease.')}
                </Alert>
                <TextField fullWidth size="small" sx={{ mb: 2 }}
                    label={t('assetDiscovery.address.address', 'IP address')}
                    value={address} onChange={e => setAddress(e.target.value)} />
                <FormControl fullWidth size="small" sx={{ mb: 2 }}>
                    <InputLabel id="address-category">{t('assetDiscovery.exclude.category', 'What is it?')}</InputLabel>
                    <Select labelId="address-category" value={category}
                        label={t('assetDiscovery.exclude.category', 'What is it?')}
                        onChange={e => setCategory(e.target.value as ExclusionCategory)}>
                        {EXCLUSION_CATEGORIES.map(c => <MenuItem key={c} value={c}>{categoryLabel(t, c)}</MenuItem>)}
                    </Select>
                </FormControl>
                <TextField fullWidth multiline minRows={2} size="small"
                    label={t('assetDiscovery.exclude.reason', 'Reason')}
                    value={reason} onChange={e => setReason(e.target.value)} />
                {error && <Alert severity="error" sx={{ mt: 2 }}>{error}</Alert>}
            </DialogContent>
            <DialogActions>
                <Button onClick={onClose}>{t('common.cancel', 'Cancel')}</Button>
                <Button variant="contained" disabled={!valid} onClick={submit}>
                    {t('assetDiscovery.address.confirm', 'Register')}
                </Button>
            </DialogActions>
        </Dialog>
    );
};

export default StaticAddressDialog;
