// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

import React, { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import Box from '@mui/material/Box';
import Tab from '@mui/material/Tab';
import Tabs from '@mui/material/Tabs';
import Typography from '@mui/material/Typography';

import ConfigInventoriesPanel from '../Components/ConfigInventoriesPanel';
import ConfigJobTemplatesPanel from '../Components/ConfigJobTemplatesPanel';
import ConfigJobsPanel from '../Components/ConfigJobsPanel';
import { hasPermission, SecurityRoles } from '../Services/permissions';

/**
 * Fleet-scale configuration management (Phase 20.1).
 *
 * Three tabs in the order the work happens: name the hosts, name the run,
 * watch it. Jobs is first because it is the tab people return to -- the other
 * two are authored once and then rarely touched.
 */
const ConfigJobs: React.FC = () => {
    const { t } = useTranslation();
    const [tab, setTab] = useState(0);
    const [canEdit, setCanEdit] = useState(false);
    const [canLaunch, setCanLaunch] = useState(false);
    const [refreshToken, setRefreshToken] = useState(0);

    useEffect(() => {
        const check = async () => {
            try {
                const [edit, launch] = await Promise.all([
                    hasPermission(SecurityRoles.ADD_SCRIPT),
                    hasPermission(SecurityRoles.RUN_SCRIPT),
                ]);
                setCanEdit(edit);
                setCanLaunch(launch);
            } catch (err) {
                // Fail closed. A page of dead buttons with no explanation is
                // the outcome to avoid, so the error is at least visible in
                // the console rather than swallowed.
                console.error('Failed to resolve fleet job permissions:', err);
            }
        };
        check();
    }, []);

    return (
        <Box sx={{ p: 3 }}>
            <Typography variant="h5" sx={{ mb: 1 }}>
                {t('configFleet.title', 'Fleet Configuration Jobs')}
            </Typography>
            <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
                {t(
                    'configFleet.intro',
                    'Run one configuration profile across many hosts at once. A job ' +
                        'works through its inventory in waves rather than all at once, ' +
                        'and records what happened on every host.',
                )}
            </Typography>

            <Tabs value={tab} onChange={(_e, value) => setTab(value)} sx={{ mb: 2 }}>
                <Tab label={t('configFleet.tabJobs', 'Jobs')} />
                <Tab label={t('configFleet.tabTemplates', 'Templates')} />
                <Tab label={t('configFleet.tabInventories', 'Inventories')} />
            </Tabs>

            {tab === 0 && (
                <ConfigJobsPanel canCancel={canLaunch} refreshToken={refreshToken} />
            )}
            {tab === 1 && (
                <ConfigJobTemplatesPanel
                    canEdit={canEdit}
                    canLaunch={canLaunch}
                    onLaunched={() => {
                        // Jump to Jobs and force a reload: a launch that leaves
                        // the operator on the Templates tab looks like nothing
                        // happened, and the first thing they do is press it
                        // again.
                        setRefreshToken((n) => n + 1);
                        setTab(0);
                    }}
                />
            )}
            {tab === 2 && <ConfigInventoriesPanel canEdit={canEdit} />}
        </Box>
    );
};

export default ConfigJobs;
