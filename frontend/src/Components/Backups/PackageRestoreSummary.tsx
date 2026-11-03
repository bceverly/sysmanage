// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

// What a package restore will do (Pro+ backup_engine, 24.6), from its plan:
// restate's ``restore --packages`` script, read by the engine, shown before
// the real run is offered -- the apt packages at their versions, the snaps,
// and plainly that apt then removes what the snapshot did not have.  The
// whole script can be opened too.

import React, { useState } from 'react';
import { Alert, Box, Button, Stack, Typography } from '@mui/material';
import { useTranslation } from 'react-i18next';
import type { BackupRun } from '../../Services/backups';

const SHOWN = 40;

const PackageRestoreSummary: React.FC<{ run: BackupRun }> = ({ run }) => {
    const { t } = useTranslation();
    const [open, setOpen] = useState(false);
    const summary = run.package_summary;
    const script = (run.result as { packages?: { script?: string } } | null)?.packages?.script;
    if (!summary) return null;
    return (
        <Stack spacing={1} sx={{ mt: 1 }}>
            <Typography variant="subtitle2">{t('backups.packages.title', 'Packages to put back')}</Typography>
            <Typography variant="body2">
                {t('backups.packages.counts', 'apt packages installed by hand: {{apt}}; snaps: {{snaps}}; repository keys: {{keys}}', {
                    apt: summary.apt_count, snaps: summary.snaps.length, keys: summary.repository_keys,
                })}
            </Typography>
            {summary.removes_unlisted && (
                <Alert severity="warning">
                    {t('backups.packages.removes', 'Packages the snapshot did not have are marked automatic and removed by apt. Anything installed on this host since the backup, the SysManage agent included if it was installed later, can be removed.')}
                </Alert>
            )}
            {summary.apt.length > 0 && (
                <Box component="pre" sx={{ fontSize: 12, bgcolor: 'action.hover', p: 1, maxHeight: 200, overflow: 'auto' }}>
                    {summary.apt.slice(0, SHOWN).join('\n')}
                    {summary.apt_count > SHOWN && `\n${t('backups.restore.more', 'Not shown: {{n}}', { n: summary.apt_count - SHOWN })}`}
                </Box>
            )}
            {summary.snaps.length > 0 && (
                <Typography variant="body2">
                    {t('backups.packages.snaps', 'Snaps: {{names}}', { names: summary.snaps.join(', ') })}
                </Typography>
            )}
            {script && (
                <Box>
                    <Button size="small" onClick={() => setOpen(o => !o)}>
                        {open ? t('backups.packages.hideScript', 'Hide the script')
                            : t('backups.packages.showScript', 'Show the whole script ({{n}} lines)', { n: summary.lines })}
                    </Button>
                    {open && (
                        <Box component="pre" sx={{ fontSize: 11, bgcolor: 'action.hover', p: 1, maxHeight: 400, overflow: 'auto' }}>
                            {script}
                        </Box>
                    )}
                </Box>
            )}
        </Stack>
    );
};

export default PackageRestoreSummary;
