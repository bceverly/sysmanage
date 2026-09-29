// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

// Who decided which devices are fine, and why (Phase 21.6 S3).  Revoking
// keeps the row: withdrawn decisions stay visible as history.

import React, { useState } from 'react';
import {
    Button,
    Dialog,
    DialogActions,
    DialogContent,
    DialogTitle,
    FormControlLabel,
    Switch,
    Table,
    TableBody,
    TableCell,
    TableHead,
    TableRow,
    TextField,
    Typography,
} from '@mui/material';
import { useTranslation } from 'react-i18next';
import type { Exclusion, ExclusionCategory } from '../../Services/assetDiscoveryService';
import { categoryLabel, formatSeen } from './discoveryLabels';
import StaticAddressDialog from './StaticAddressDialog';

interface Props {
    exclusions: Exclusion[];
    showRevoked: boolean;
    canManage: boolean;
    onShowRevoked: (value: boolean) => void;
    onRevoke: (id: string, reason: string) => Promise<void>;
    onAddAddress: (address: string, category: ExclusionCategory, reason: string) => Promise<void>;
}

const RevokeDialog: React.FC<{
    target: Exclusion | null;
    onClose: () => void;
    onConfirm: (reason: string) => Promise<void>;
}> = ({ target, onClose, onConfirm }) => {
    const { t } = useTranslation();
    const [reason, setReason] = useState('');
    return (
        <Dialog open={target !== null} onClose={onClose} fullWidth maxWidth="sm">
            <DialogTitle>{t('assetDiscovery.revoke.title', 'Show this device as unmanaged again')}</DialogTitle>
            <DialogContent>
                <TextField fullWidth multiline minRows={2} size="small" sx={{ mt: 1 }}
                    label={t('assetDiscovery.exclude.reason', 'Reason')}
                    value={reason} onChange={e => setReason(e.target.value)} />
            </DialogContent>
            <DialogActions>
                <Button onClick={onClose}>{t('common.cancel', 'Cancel')}</Button>
                <Button variant="contained" color="warning" disabled={reason.trim().length < 3}
                    onClick={async () => { await onConfirm(reason.trim()); setReason(''); }}>
                    {t('assetDiscovery.revoke.confirm', 'Revoke')}
                </Button>
            </DialogActions>
        </Dialog>
    );
};

const ExclusionList: React.FC<Props> = ({ exclusions, showRevoked, canManage, onShowRevoked, onRevoke, onAddAddress }) => {
    const { t } = useTranslation();
    const [target, setTarget] = useState<Exclusion | null>(null);
    const [adding, setAdding] = useState(false);
    return (
        <>
            {canManage && (
                <Button variant="outlined" sx={{ mb: 1, mr: 2 }} onClick={() => setAdding(true)}>
                    {t('assetDiscovery.address.title', 'Register a static address')}
                </Button>
            )}
            <FormControlLabel sx={{ mb: 1 }}
                control={<Switch checked={showRevoked} onChange={e => onShowRevoked(e.target.checked)} />}
                label={t('assetDiscovery.exclusions.showRevoked', 'Show revoked decisions')} />
            {exclusions.length === 0 ? (
                <Typography color="text.secondary" sx={{ py: 3 }}>
                    {t('assetDiscovery.exclusions.empty', 'No devices have been marked as known.')}
                </Typography>
            ) : (
                <Table size="small">
                    <TableHead>
                        <TableRow>
                            <TableCell>{t('assetDiscovery.table.device', 'Device')}</TableCell>
                            <TableCell>{t('assetDiscovery.exclude.category', 'What is it?')}</TableCell>
                            <TableCell>{t('assetDiscovery.exclude.reason', 'Reason')}</TableCell>
                            <TableCell>{t('assetDiscovery.exclusions.decidedBy', 'Decided by')}</TableCell>
                            <TableCell>{t('assetDiscovery.table.lastSeen', 'Last seen')}</TableCell>
                            <TableCell />
                        </TableRow>
                    </TableHead>
                    <TableBody>
                        {exclusions.map(row => (
                            <TableRow key={row.id} sx={row.revoked_at ? { opacity: 0.6 } : undefined}>
                                <TableCell sx={{ fontFamily: 'monospace' }}>{row.identity}</TableCell>
                                <TableCell>{categoryLabel(t, row.category)}</TableCell>
                                <TableCell>
                                    {row.reason}
                                    {row.revoked_at && (
                                        <Typography variant="caption" display="block" color="text.secondary">
                                            {t('assetDiscovery.exclusions.revokedBy', 'Revoked by {{who}}: {{why}}', { who: row.revoked_by, why: row.revoke_reason })}
                                        </Typography>
                                    )}
                                </TableCell>
                                <TableCell>
                                    {row.created_by}
                                    <Typography variant="caption" display="block" color="text.secondary">{formatSeen(row.created_at)}</Typography>
                                </TableCell>
                                <TableCell>{formatSeen(row.last_seen_at ?? null)}</TableCell>
                                <TableCell align="right">
                                    {canManage && !row.revoked_at && (
                                        <Button size="small" onClick={() => setTarget(row)}>
                                            {t('assetDiscovery.revoke.confirm', 'Revoke')}
                                        </Button>
                                    )}
                                </TableCell>
                            </TableRow>
                        ))}
                    </TableBody>
                </Table>
            )}
            {adding && <StaticAddressDialog open={adding} onClose={() => setAdding(false)} onConfirm={onAddAddress} />}
            <RevokeDialog target={target} onClose={() => setTarget(null)}
                onConfirm={async reason => { if (target) await onRevoke(target.id, reason); setTarget(null); }} />
        </>
    );
};

export default ExclusionList;
