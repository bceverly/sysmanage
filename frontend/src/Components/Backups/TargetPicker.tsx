// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

/**
 * Which backup target a policy uses (ROADMAP 27.3; several targets are
 * Enterprise, backup_ops_engine).  Shown only when there is more than one
 * target.  "Default" follows whichever target is the default.  Without the
 * engine, the policy can keep the target it has or take the default, and
 * nothing else: a lapse freezes, never breaks.
 */

import React, { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';

import FormControl from '@mui/material/FormControl';
import FormHelperText from '@mui/material/FormHelperText';
import InputLabel from '@mui/material/InputLabel';
import MenuItem from '@mui/material/MenuItem';
import Select from '@mui/material/Select';

import { useModuleLicensed } from '../../hooks/useModuleLicensed';
import { listTargets } from '../../Services/backups';
import type { TargetBrief } from '../../Services/backups';

export const DEFAULT_CHOICE = '';

export const targetLabel = (target: TargetBrief): string =>
    target.location ? `${target.name} (${target.location})` : target.name;

const TargetPicker: React.FC<{
    /** The chosen target's id, or DEFAULT_CHOICE for the default. */
    value: string;
    onChange: (value: string) => void;
    /** The target the policy has now, which it may always keep. */
    current?: string | null;
    disabled?: boolean;
    helper?: string;
    /** Offer "the default", which follows whichever target is the default
     *  (tag policies).  A host's own policy picks a target instead. */
    followDefault?: boolean;
}> = ({ value, onChange, current, disabled, helper, followDefault }) => {
    const { t } = useTranslation();
    const licensed = useModuleLicensed('backup_ops_engine');
    const [targets, setTargets] = useState<TargetBrief[]>([]);
    useEffect(() => {
        listTargets().then(setTargets).catch(() => setTargets([]));
    }, []);
    if (targets.length < 2) return null;
    const allowed = (target: TargetBrief) => licensed || target.is_default || target.id === current;
    const defaultTarget = targets.find(target => target.is_default) ?? targets[0];
    const shown = value || (followDefault ? DEFAULT_CHOICE : defaultTarget.id);
    return (
        <FormControl fullWidth size="small" sx={{ mt: 1 }} disabled={disabled}>
            <InputLabel id="backup-target-picker">{t('backups.targets.picker', 'Backup target')}</InputLabel>
            <Select labelId="backup-target-picker" label={t('backups.targets.picker', 'Backup target')}
                value={shown} onChange={e => onChange(String(e.target.value))} data-testid="backup-target-picker">
                {followDefault && (
                    <MenuItem value={DEFAULT_CHOICE}>
                        {t('backups.targets.followDefault', 'The default ({{name}})', { name: defaultTarget.name })}
                    </MenuItem>
                )}
                {targets.map(target => (
                    <MenuItem key={target.id} value={target.id} disabled={!allowed(target)}>
                        {targetLabel(target)}
                    </MenuItem>
                ))}
            </Select>
            <FormHelperText>
                {helper ?? (licensed
                    ? t('backups.targets.pickerHelp', 'Where this backup is stored.')
                    : t('backups.targets.pickerUnlicensed', 'Choosing another target needs the Enterprise license; a host keeps the target it has.'))}
            </FormHelperText>
        </FormControl>
    );
};

export default TargetPicker;
