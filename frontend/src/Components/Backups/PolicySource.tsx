// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

// Where a host's backup settings come from (Pro+ 24.6): its own policy
// (Configure) or a tag policy, named with its priority -- the rule that won.

import React from 'react';
import { Alert, Typography } from '@mui/material';
import type { TFunction } from 'i18next';
import { useTranslation } from 'react-i18next';
import type { PolicySource } from '../../Services/backups';

export const policySourceText = (t: TFunction, source?: PolicySource | null): string | null => {
    if (!source || source.kind === 'none') return null;
    if (source.kind === 'tag') {
        return t('backups.policySource.tag', 'From tag policy {{name}} (priority {{priority}})',
            { name: source.name ?? '', priority: source.priority ?? 0 });
    }
    return t('backups.policySource.own', "This host's own policy");
};

/** The host card's line. */
export const PolicySourceLine: React.FC<{ source?: PolicySource | null }> = ({ source }) => {
    const { t } = useTranslation();
    const text = policySourceText(t, source);
    return text ? <Typography variant="body2">{text}</Typography> : null;
};

/** The policy dialog's note for a host that follows a tag policy. */
export const TagPolicyNote: React.FC<{ source?: PolicySource | null }> = ({ source }) => {
    const { t } = useTranslation();
    if (source?.kind !== 'tag') return null;
    return (
        <Alert severity="info">
            {t('backups.policySource.dialogNote',
                'This host follows the tag policy {{name}}. Saving here makes these settings this host\'s own, which then always win; "Use the tag policy" on its backup card returns it to the tag policy.',
                { name: source.name ?? '' })}
        </Alert>
    );
};

/** The policy dialog's note for a host on its own policy that a tag policy
 *  also covers: its own policy wins, and the card can hand it back. */
export const OwnPolicyNote: React.FC<{ source?: PolicySource | null }> = ({ source }) => {
    const { t } = useTranslation();
    const available = source?.kind === 'own' ? source.tag_policy_available : undefined;
    if (!available) return null;
    return (
        <Alert severity="info">
            {t('backups.policySource.ownCovered',
                'The tag policy {{name}} (priority {{priority}}) also covers this host; this host\'s own policy wins over it. "Use the tag policy" on its backup card switches it over, keeping its repository, keys and history.',
                { name: available.name, priority: available.priority })}
        </Alert>
    );
};

