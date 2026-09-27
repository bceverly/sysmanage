// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

// Waiving or re-affirming a posture item (Phase 21.4 S7). A waiver is an
// audited acceptance of a specific risk, so it always needs a reason, and it
// is said plainly that the item stays open underneath.

import React, { useState } from 'react';
import {
    Alert,
    Button,
    Dialog,
    DialogActions,
    DialogContent,
    DialogTitle,
    TextField,
    Typography,
} from '@mui/material';
import { useTranslation } from 'react-i18next';
import { postureService, refusalCode, type PostureItem } from '../../Services/postureService';
import { refusalLabel, ruleTitle, staleLabel } from './postureLabels';

interface Props {
    item: PostureItem;
    mode: 'waive' | 'reaffirm';
    onClose: () => void;
    onDone: () => void;
}

const WaiverDialog: React.FC<Props> = ({ item, mode, onClose, onDone }) => {
    const { t } = useTranslation();
    const [reason, setReason] = useState(mode === 'reaffirm' ? item.waiver?.reason ?? '' : '');
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState<string | null>(null);

    const submit = async () => {
        setBusy(true);
        setError(null);
        try {
            if (mode === 'waive') await postureService.waive(item.rule_key, reason.trim());
            else await postureService.reaffirmWaiver(item.rule_key, reason.trim() || undefined);
            onDone();
        } catch (err) {
            const code = refusalCode(err);
            setError(code ? refusalLabel(t, code) : t('posture.waiver.failed', 'The waiver could not be saved.'));
            setBusy(false);
        }
    };

    const stale = mode === 'reaffirm' && item.waiver?.stale_reason;

    return (
        <Dialog open onClose={onClose} fullWidth maxWidth="sm">
            <DialogTitle>
                {mode === 'waive'
                    ? t('posture.waiver.title', 'Waive: {{title}}', { title: ruleTitle(t, item.rule_key) })
                    : t('posture.waiver.reaffirmTitle', 'Re-affirm waiver: {{title}}', { title: ruleTitle(t, item.rule_key) })}
            </DialogTitle>
            <DialogContent>
                <Typography variant="body2" sx={{ mb: 2 }}>
                    {t('posture.waiver.explain',
                        'A waiver records that you accept this risk. The item stays open underneath, and the waiver lapses if the risk rises or its basis changes.')}
                </Typography>
                {stale && <Alert severity="warning" sx={{ mb: 2 }}>{staleLabel(t, stale)}</Alert>}
                <TextField label={t('posture.waiver.reason', 'Reason')} value={reason} fullWidth multiline minRows={3}
                    required={mode === 'waive'} onChange={e => setReason(e.target.value)} />
                {error && <Alert severity="error" sx={{ mt: 2 }}>{error}</Alert>}
            </DialogContent>
            <DialogActions>
                <Button onClick={onClose}>{t('common.cancel', 'Cancel')}</Button>
                <Button variant="contained" onClick={submit}
                    disabled={busy || (mode === 'waive' && !reason.trim())}>
                    {mode === 'waive' ? t('posture.waiver.submit', 'Waive') : t('posture.waiver.reaffirm', 'Re-affirm')}
                </Button>
            </DialogActions>
        </Dialog>
    );
};

export default WaiverDialog;
