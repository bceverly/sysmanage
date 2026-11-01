// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

// The network shares a host's backup leaves out (2026-11-01).  The agent
// leaves the host's network and automount points out of its backup: they
// hold another server's data, and opening an automount would mount it.  A
// path inside one in "Also back up" opts that share back in.  A restate that
// leaves them out itself names, in each capture's result, what it skipped:
// the note then shows that.

import React from 'react';
import { Alert, Stack, Tooltip, Typography } from '@mui/material';
import InfoOutlinedIcon from '@mui/icons-material/InfoOutlined';
import { useTranslation } from 'react-i18next';
import type { TFunction } from 'i18next';
import type { NetworkMounts } from '../../Services/backups';

/** The lines to show, or [] when the host left nothing out. */
export const networkMountLines = (t: TFunction, mounts?: NetworkMounts | null): string[] => {
    if (!mounts) return [];
    const lines: string[] = [];
    if (mounts.native && mounts.skipped?.length) {
        lines.push(t('backups.network.skipped',
            'Left out of the last backup by restate (network mounts on this host): {{paths}}',
            { paths: mounts.skipped.map(m => (m.type ? `${m.path} (${m.type})` : m.path)).join(', ') }));
    } else if (mounts.excluded.length) {
        lines.push(t('backups.network.leftOut', 'Left out automatically (network mounts on this host): {{paths}}',
            { paths: mounts.excluded.join(', ') }));
    }
    if (mounts.kept.length) {
        lines.push(t('backups.network.kept',
            'Backed up although they are network mounts, because "Also back up" names a path inside them: {{paths}}',
            { paths: mounts.kept.join(', ') }));
    }
    if (lines.length) {
        lines.push(t('backups.network.hint', 'A network share is best backed up on the server that owns it.'));
    }
    return lines;
};

/** The policy dialog's note. */
export const NetworkMountsNote: React.FC<{ mounts?: NetworkMounts | null }> = ({ mounts }) => {
    const { t } = useTranslation();
    const lines = networkMountLines(t, mounts);
    if (!lines.length) return null;
    return (
        <Alert severity="info">
            <Stack spacing={0.5}>
                {lines.map(line => <Typography key={line} variant="body2">{line}</Typography>)}
            </Stack>
        </Alert>
    );
};

/** The Backups row's icon: the same note on hover. */
export const NetworkMountsIcon: React.FC<{ mounts?: NetworkMounts | null }> = ({ mounts }) => {
    const { t } = useTranslation();
    const lines = networkMountLines(t, mounts);
    if (!lines.length) return null;
    return (
        <Tooltip title={<span style={{ whiteSpace: 'pre-line' }}>{lines.join('\n')}</span>}>
            <InfoOutlinedIcon fontSize="small" color="action" aria-label={lines[0]} sx={{ ml: 0.5 }} />
        </Tooltip>
    );
};
