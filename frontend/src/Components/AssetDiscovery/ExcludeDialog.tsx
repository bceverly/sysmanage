// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

// "These devices are known and fine" (Phase 21.6 S3).  A category and a
// reason are required: an exclusion is an audit record of who accepted what,
// not a way to make a list shorter.

import React, { useState } from 'react';
import {
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
    Typography,
} from '@mui/material';
import { useTranslation } from 'react-i18next';
import { EXCLUSION_CATEGORIES, type ExclusionCategory } from '../../Services/assetDiscoveryService';
import { categoryLabel } from './discoveryLabels';

interface Props {
    open: boolean;
    count: number;
    suggested?: ExclusionCategory | null;
    onClose: () => void;
    onConfirm: (category: ExclusionCategory, reason: string) => Promise<void>;
}

const ExcludeDialog: React.FC<Props> = ({ open, count, suggested, onClose, onConfirm }) => {
    const { t } = useTranslation();
    const [category, setCategory] = useState<ExclusionCategory>(suggested ?? 'printer');
    const [reason, setReason] = useState('');
    const [busy, setBusy] = useState(false);
    const valid = reason.trim().length >= 3;

    const submit = async () => {
        setBusy(true);
        try {
            await onConfirm(category, reason.trim());
            setReason('');
        } finally {
            setBusy(false);
        }
    };

    return (
        <Dialog open={open} onClose={onClose} fullWidth maxWidth="sm">
            <DialogTitle>{t('assetDiscovery.exclude.title', 'Mark as known and fine')}</DialogTitle>
            <DialogContent>
                <Typography variant="body2" sx={{ mb: 2 }}>
                    {t('assetDiscovery.exclude.intro', '{{count}} devices will no longer be shown as unmanaged. This is recorded with your name and reason, and follows each device by its MAC address even if its IP address changes.', { count })}
                </Typography>
                <FormControl fullWidth size="small" sx={{ mb: 2 }}>
                    <InputLabel id="exclude-category">{t('assetDiscovery.exclude.category', 'What is it?')}</InputLabel>
                    <Select labelId="exclude-category" value={category}
                        label={t('assetDiscovery.exclude.category', 'What is it?')}
                        onChange={e => setCategory(e.target.value as ExclusionCategory)}>
                        {EXCLUSION_CATEGORIES.map(c => <MenuItem key={c} value={c}>{categoryLabel(t, c)}</MenuItem>)}
                    </Select>
                </FormControl>
                <TextField fullWidth multiline minRows={2} size="small"
                    label={t('assetDiscovery.exclude.reason', 'Reason')}
                    helperText={t('assetDiscovery.exclude.reasonHelp', 'Required. For example: the front office printer, owned by facilities.')}
                    value={reason} onChange={e => setReason(e.target.value)} />
            </DialogContent>
            <DialogActions>
                <Button onClick={onClose}>{t('common.cancel', 'Cancel')}</Button>
                <Button variant="contained" disabled={!valid || busy} onClick={submit}>
                    {t('assetDiscovery.exclude.confirm', 'Mark as known')}
                </Button>
            </DialogActions>
        </Dialog>
    );
};

export default ExcludeDialog;
