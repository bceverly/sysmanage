// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

import React from 'react';
import { Grid } from '@mui/material';
import AntivirusStatusCard from '../AntivirusStatusCard';
import CommercialAntivirusStatusCard from '../CommercialAntivirusStatusCard';
import FirewallStatusCard from '../FirewallStatusCard';
import { SysManageHost } from '../../Services/hosts';

interface HostSecurityTabProps {
    host: SysManageHost;
    hostId: string;
    hasAntivirusOsDefault: boolean;
    antivirusRefreshTrigger: number;
    canDeployAntivirus: boolean;
    canEnableAntivirus: boolean;
    canDisableAntivirus: boolean;
    canRemoveAntivirus: boolean;
    handleDeployAntivirus: () => void;
    handleEnableAntivirus: () => void;
    handleDisableAntivirus: () => void;
    handleRemoveAntivirus: () => void;
}

const HostSecurityTab: React.FC<HostSecurityTabProps> = ({
    host,
    hostId,
    hasAntivirusOsDefault,
    antivirusRefreshTrigger,
    canDeployAntivirus,
    canEnableAntivirus,
    canDisableAntivirus,
    canRemoveAntivirus,
    handleDeployAntivirus,
    handleEnableAntivirus,
    handleDisableAntivirus,
    handleRemoveAntivirus,
}) => {
    return (
                <Grid container spacing={3}>
                    <Grid size={{ xs: 12, md: 6 }} sx={{ display: 'flex' }}>
                        <AntivirusStatusCard
                            hostId={hostId}
                            onDeployAntivirus={handleDeployAntivirus}
                            onEnableAntivirus={handleEnableAntivirus}
                            onDisableAntivirus={handleDisableAntivirus}
                            onRemoveAntivirus={handleRemoveAntivirus}
                            canDeployAntivirus={canDeployAntivirus}
                            canEnableAntivirus={canEnableAntivirus}
                            canDisableAntivirus={canDisableAntivirus}
                            canRemoveAntivirus={canRemoveAntivirus}
                            isHostActive={host?.active || false}
                            isAgentPrivileged={host?.is_agent_privileged || false}
                            hasOsDefault={hasAntivirusOsDefault}
                            refreshTrigger={antivirusRefreshTrigger}
                            sx={{ height: '100%', width: '100%' }}
                        />
                    </Grid>
                    <Grid size={{ xs: 12, md: 6 }} sx={{ display: 'flex' }}>
                        <CommercialAntivirusStatusCard
                            hostId={hostId}
                            refreshTrigger={antivirusRefreshTrigger}
                            sx={{ height: '100%', width: '100%' }}
                        />
                    </Grid>
                    <Grid size={{ xs: 12, md: 6 }}>
                        <FirewallStatusCard
                            hostId={hostId}
                            refreshTrigger={antivirusRefreshTrigger}
                        />
                    </Grid>
                </Grid>    );
};

export default HostSecurityTab;
