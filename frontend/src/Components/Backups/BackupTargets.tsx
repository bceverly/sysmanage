// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

/**
 * Every backup target, the default first (ROADMAP 27.3).  Community has
 * one; with the Enterprise backup_ops_engine an installation adds more, each
 * with its own storage host, capacity and health.  A host backs up to its
 * policy's target; new hosts go to the default.
 */

import React, { useState } from 'react';
import { useTranslation } from 'react-i18next';

import Button from '@mui/material/Button';
import Stack from '@mui/material/Stack';

import { useModuleLicensed } from '../../hooks/useModuleLicensed';
import type { BackupOverview, BackupTarget } from '../../Services/backups';
import BackupTargetCard, { TargetDialog } from './BackupTargetCard';

export const targetsOf = (data: BackupOverview): BackupTarget[] =>
    data.targets ?? (data.target ? [data.target] : []);

/** Every target's storage host: none of them is offered host actions. */
export const storageHostIds = (data: BackupOverview): string[] =>
    targetsOf(data).map(target => target.storage_host_id).filter((id): id is string => !!id);

const BackupTargets: React.FC<{
    data: BackupOverview;
    canManage: boolean;
    onChanged: () => void;
}> = ({ data, canManage, onChanged }) => {
    const { t } = useTranslation();
    const licensed = useModuleLicensed('backup_ops_engine');
    const [adding, setAdding] = useState(false);
    const every = targetsOf(data);
    const several = every.length > 1;
    if (every.length === 0) {
        return <BackupTargetCard target={null} hosts={data.hosts} versions={data.restate_versions}
            canManage={canManage} onChanged={onChanged} />;
    }
    return (
        <>
            {every.map(target => (
                <BackupTargetCard key={target.id} target={target} hosts={data.hosts}
                    versions={data.restate_versions} canManage={canManage} onChanged={onChanged}
                    several={several} canMakeDefault={licensed} targets={every} />
            ))}
            {canManage && licensed && (
                <Stack direction="row" justifyContent="flex-end" sx={{ mb: 2 }}>
                    <Button variant="outlined" size="small" onClick={() => setAdding(true)}
                        data-testid="add-backup-target">
                        {t('backups.targets.add', 'Add another target')}
                    </Button>
                </Stack>
            )}
            <TargetDialog open={adding} target={null} hosts={data.hosts}
                onClose={() => setAdding(false)} onSaved={onChanged} />
        </>
    );
};

export default BackupTargets;
