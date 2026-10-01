// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

// Fixing a posture item (Phase 21.4 S7). Always a preview first: what will
// change and on which hosts, before anything does. A setting or fleet remedy
// is applied from here; a guided one links to the screen that fixes it; one
// with no remedy says so plainly.

import React, { useEffect, useState } from 'react';
import {
    Alert,
    Button,
    CircularProgress,
    Dialog,
    DialogActions,
    DialogContent,
    DialogTitle,
    List,
    ListItem,
    ListItemText,
    Typography,
} from '@mui/material';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router';
import {
    postureService,
    refusalCode,
    type PostureItem,
    type RemedyPreview,
    type RemedyResult,
} from '../../Services/postureService';
import { GUIDED_ROUTES, refusalLabel, remedyText, ruleTitle } from './postureLabels';

interface Props {
    item: PostureItem;
    onClose: () => void;
    onApplied: () => void;
}

const show = (value: unknown): string => {
    if (value === null || value === undefined || value === '') return '-';
    // Structured values (lists, settings maps) read as JSON, not "[object Object]".
    return typeof value === 'object' ? JSON.stringify(value) : String(value);
};

const PreviewBody: React.FC<{ preview: RemedyPreview }> = ({ preview }) => {
    const { t } = useTranslation();
    return (
        <>
            {preview.changes.length > 0 && (
                <List dense>
                    {preview.changes.map(c => (
                        <ListItem key={c.setting} disableGutters>
                            <ListItemText primary={c.setting}
                                secondary={t('posture.remedy.change', '{{from}} to {{to}}',
                                    { from: show(c.from), to: show(c.to) })} />
                        </ListItem>
                    ))}
                </List>
            )}
            {preview.hosts.length > 0 && (
                <>
                    <Typography variant="subtitle2" sx={{ mt: 1 }}>
                        {t('posture.remedy.hosts', 'Hosts that will change: {{n}}', { n: preview.hosts.length })}
                    </Typography>
                    <List dense>
                        {preview.hosts.map(h => (
                            <ListItem key={h.id} disableGutters><ListItemText primary={h.fqdn} /></ListItem>
                        ))}
                    </List>
                </>
            )}
        </>
    );
};

const ResultBody: React.FC<{ result: RemedyResult }> = ({ result }) => {
    const { t } = useTranslation();
    return (
        <>
            <Alert severity={result.failed.length ? 'warning' : 'success'} sx={{ mb: 1 }}>
                {t('posture.remedy.applied', 'The fix was applied. The item is re-checked on the next evaluation.')}
            </Alert>
            {result.failed.map(f => (
                <Typography key={f.fqdn} variant="body2" color="error">
                    {t('posture.remedy.hostFailed', '{{host}}: {{reason}}', { host: f.fqdn, reason: f.reason })}
                </Typography>
            ))}
        </>
    );
};

const RemedyDialog: React.FC<Props> = ({ item, onClose, onApplied }) => {
    const { t } = useTranslation();
    const navigate = useNavigate();
    const [preview, setPreview] = useState<RemedyPreview | null>(null);
    const [result, setResult] = useState<RemedyResult | null>(null);
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
        postureService.previewRemedy(item.rule_key)
            .then(setPreview)
            .catch(() => setError(t('posture.remedy.previewFailed', 'The fix could not be previewed.')));
    }, [item.rule_key, t]);

    const apply = async () => {
        setBusy(true);
        setError(null);
        try {
            setResult(await postureService.applyRemedy(item.rule_key));
            onApplied();
        } catch (err) {
            const code = refusalCode(err);
            setError(code ? refusalLabel(t, code) : t('posture.remedy.applyFailed', 'The fix could not be applied.'));
        }
        setBusy(false);
    };

    const automated = preview?.kind === 'setting' || preview?.kind === 'fleet';
    const route = preview?.kind === 'guided' && preview.target ? GUIDED_ROUTES[preview.target] : undefined;

    return (
        <Dialog open onClose={onClose} fullWidth maxWidth="sm">
            <DialogTitle>{ruleTitle(t, item.rule_key)}</DialogTitle>
            <DialogContent>
                <Typography variant="body2" sx={{ mb: 1 }}>{remedyText(t, item.remedy)}</Typography>
                {!preview && !error && <CircularProgress size={24} />}
                {preview && !preview.available && preview.unavailable_reason && (
                    <Alert severity="info">{refusalLabel(t, preview.unavailable_reason)}</Alert>
                )}
                {preview && !result && <PreviewBody preview={preview} />}
                {result && <ResultBody result={result} />}
                {error && <Alert severity="error" sx={{ mt: 1 }}>{error}</Alert>}
            </DialogContent>
            <DialogActions>
                <Button onClick={onClose}>{t('common.close', 'Close')}</Button>
                {route && (
                    <Button variant="contained" onClick={() => navigate(route)}>
                        {t('posture.remedy.goThere', 'Go there')}
                    </Button>
                )}
                {automated && !result && (
                    <Button variant="contained" disabled={!preview?.available || busy} onClick={apply}>
                        {t('posture.remedy.apply', 'Apply fix')}
                    </Button>
                )}
            </DialogActions>
        </Dialog>
    );
};

export default RemedyDialog;
