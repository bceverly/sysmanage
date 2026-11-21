// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

/**
 * Off-site copies (ROADMAP 27.3; setting one up is Enterprise).  A target
 * may copy every repository on it to another target, reached through
 * restate-proxy on another storage host: this site can add to the copy but
 * never delete from it.  The off-site storage host keeps the copy with the
 * same retention and legal holds as the source.
 */

import React, { useState } from 'react';
import {
    Alert,
    Button,
    Dialog,
    DialogActions,
    DialogContent,
    DialogTitle,
    MenuItem,
    TextField,
    Typography,
} from '@mui/material';
import { useTranslation } from 'react-i18next';

import AsyncButton from '../AsyncButton';
import { setReplicaTarget } from '../../Services/backups';
import type { BackupTarget, OffsiteCopy } from '../../Services/backups';
import { apiDetail, formatBytes } from './backupLabels';

const NONE = '';

/** The target card's line: where it copies to, and who copies into it. */
export const TargetOffsite: React.FC<{
    target: BackupTarget;
    targets: BackupTarget[];
    canChange: boolean;
    onChanged: () => void;
}> = ({ target, targets, canChange, onChanged }) => {
    const { t } = useTranslation();
    const [open, setOpen] = useState(false);
    const others = targets.filter(other => other.id !== target.id);
    const from = target.copies_from ?? [];
    if (others.length === 0 && !target.replica_target && from.length === 0) return null;
    return (
        <>
            <Typography variant="body2" data-testid={`offsite-${target.id}`}>
                {t('backups.offsite.label', 'Off-site copy')}:{' '}
                {target.replica_target ?? t('backups.offsite.none', 'None')}
                {canChange && others.length > 0 && (
                    <Button size="small" sx={{ ml: 1 }} onClick={() => setOpen(true)}>
                        {t('backups.offsite.change', 'Change')}
                    </Button>
                )}
            </Typography>
            <OffsiteSeal target={target} />
            {from.length > 0 && (
                <Typography variant="body2" color="text.secondary">
                    {t('backups.offsite.holds', 'Holds the off-site copies of: {{names}}',
                        { names: from.join(', ') })}
                </Typography>
            )}
            {open && (
                <OffsiteDialog target={target} others={others}
                    onClose={() => setOpen(false)} onSaved={onChanged} />
            )}
        </>
    );
};

/** Is the off-site copy immutable: append-only for this site, and sealed there. */
const OffsiteSeal: React.FC<{ target: BackupTarget }> = ({ target }) => {
    const { t } = useTranslation();
    const seal = target.offsite_seal;
    if (!seal) return null;
    if (!seal.sealed) {
        return (
            <Alert severity="warning" sx={{ my: 0.5 }} data-testid={`offsite-unsealed-${target.id}`}>
                {t('backups.offsite.unsealed',
                    '{{name}} does not seal its copies. This site can only add to them, but if they are damaged or deleted on that storage host, no earlier version is kept. Give it ZFS or btrfs seals to make the copy immutable.',
                    { name: target.replica_target ?? '?' })}
            </Alert>
        );
    }
    return (
        <Typography variant="body2" color="text.secondary" data-testid={`offsite-sealed-${target.id}`}>
            {seal.keep_days
                ? t('backups.offsite.immutable', 'Immutable: append-only for this site, and sealed there for {{days}} days.',
                    { days: seal.keep_days })
                : t('backups.offsite.immutableKept', 'Immutable: append-only for this site, and sealed there.')}
        </Typography>
    );
};

const OffsiteDialog: React.FC<{
    target: BackupTarget;
    others: BackupTarget[];
    onClose: () => void;
    onSaved: () => void;
}> = ({ target, others, onClose, onSaved }) => {
    const { t } = useTranslation();
    const [choice, setChoice] = useState<string>(target.replica_target_id ?? NONE);
    const [error, setError] = useState<string | null>(null);
    const save = async () => {
        setError(null);
        try {
            await setReplicaTarget(target.id, choice || null);
            onSaved();
            onClose();
        } catch (err) {
            setError(apiDetail(err, t('backups.offsite.error', 'The off-site copy could not be changed.')));
        }
    };
    return (
        <Dialog open onClose={onClose} maxWidth="sm" fullWidth>
            <DialogTitle>{t('backups.offsite.title', 'Off-site copy of {{name}}', { name: target.name })}</DialogTitle>
            <DialogContent>
                <Typography variant="body2" sx={{ mb: 2 }}>
                    {t('backups.offsite.intro',
                        'Every repository on this target is copied after each night\'s backup to the target chosen here. It must be reached through restate-proxy on another storage host, so this site can add to the copy but never delete from it. The copy keeps the same snapshots and legal holds as the source.')}
                </Typography>
                <TextField select fullWidth size="small" value={choice}
                    label={t('backups.offsite.label', 'Off-site copy')}
                    onChange={event => setChoice(event.target.value)}
                    slotProps={{ htmlInput: { 'data-testid': 'offsite-choice' } }}>
                    <MenuItem value={NONE}>{t('backups.offsite.stop', 'None (stop copying; the copies stay where they are)')}</MenuItem>
                    {others.map(other => (
                        <MenuItem key={other.id} value={other.id}>
                            {other.location ? `${other.name} (${other.location})` : other.name}
                        </MenuItem>
                    ))}
                </TextField>
                {error && <Alert severity="error" sx={{ mt: 2 }}>{error}</Alert>}
            </DialogContent>
            <DialogActions>
                <Button onClick={onClose}>{t('common.cancel', 'Cancel')}</Button>
                <AsyncButton variant="contained" onClick={save}>{t('common.save', 'Save')}</AsyncButton>
            </DialogActions>
        </Dialog>
    );
};

/** A host's off-site copies on its Backup card. */
export const HostOffsite: React.FC<{ offsite?: OffsiteCopy[] }> = ({ offsite }) => {
    const { t } = useTranslation();
    if (!offsite || offsite.length === 0) return null;
    return (
        <>
            {offsite.map(copy => (
                <React.Fragment key={copy.id}>
                    <Typography variant="body2" data-testid={`host-offsite-${copy.id}`}>
                        {t('backups.offsite.hostLine', 'Off-site copy at {{target}}', { target: copy.target ?? '?' })}:{' '}
                        {!copy.ready
                            ? t('backups.offsite.settingUp', 'being set up')
                            : copy.newest_snapshot
                                ? t('backups.offsite.newest', 'newest snapshot {{hours}} h old, {{size}}',
                                    { hours: copy.lag_hours ?? '?', size: formatBytes(copy.bytes) })
                                : t('backups.offsite.empty', 'no snapshot copied yet')}
                        {copy.ready && copy.behind > 0 && (
                            <>{' - '}{t('backups.offsite.behind', '{{n}} to copy', { n: copy.behind })}</>
                        )}
                    </Typography>
                    {copy.last_copy_status && copy.last_copy_status !== 'ok' && (
                        <Alert severity="warning" sx={{ my: 0.5 }}>
                            {t('backups.offsite.failed', 'The last off-site copy did not finish: {{error}}',
                                { error: copy.last_copy_error ?? copy.last_copy_status })}
                        </Alert>
                    )}
                </React.Fragment>
            ))}
        </>
    );
};
