// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

import React from 'react';
import { Box, Typography, Button, IconButton } from '@mui/material';
import ArrowBackIcon from '@mui/icons-material/ArrowBack';
import ComputerIcon from '@mui/icons-material/Computer';
import SystemUpdateAltIcon from '@mui/icons-material/SystemUpdateAlt';
import RestartAltIcon from '@mui/icons-material/RestartAlt';
import PowerSettingsNewIcon from '@mui/icons-material/PowerSettingsNew';
import AppsIcon from '@mui/icons-material/Apps';
import EditIcon from '@mui/icons-material/Edit';
import AccountTreeIcon from '@mui/icons-material/AccountTree';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { hasPermissionSync, SecurityRoles } from '../../Services/permissions';
import { SysManageHost } from '../../Services/hosts';

interface HostDetailHeaderProps {
    host: SysManageHost;
    hostId: string | undefined;
    canEditHostname: boolean;
    handleHostnameEditClick: () => void;
    handleRequestPackages: () => void;
    handleRebootClick: () => void;
    handleShutdownClick: () => void;
    handleUpdateAgent: () => void;
}

const HostDetailHeader: React.FC<HostDetailHeaderProps> = ({
    host,
    hostId,
    canEditHostname,
    handleHostnameEditClick,
    handleRequestPackages,
    handleRebootClick,
    handleShutdownClick,
    handleUpdateAgent,
}) => {
    const navigate = useNavigate();
    const { t } = useTranslation();
    return (
        <>
            <Button
                startIcon={<ArrowBackIcon />}
                onClick={() => navigate('/hosts')}
                sx={{ flexShrink: 0, alignSelf: 'flex-start' }}
            >
                {t('common.back')}
            </Button>

            <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexShrink: 0 }}>
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
                    <Typography variant="h4" sx={{ display: 'flex', alignItems: 'center' }}>
                        <ComputerIcon sx={{ mr: 2, fontSize: '2rem' }} />
                        {host.fqdn}
                        {canEditHostname && host.active && host.is_agent_privileged && (
                            <IconButton
                                size="small"
                                onClick={handleHostnameEditClick}
                                sx={{ ml: 1 }}
                                title={t('hostDetail.editHostname', 'Edit Hostname')}
                            >
                                <EditIcon fontSize="small" />
                            </IconButton>
                        )}
                    </Typography>
                    {host.parent_host_id && (
                        <Button
                            variant="outlined"
                            size="small"
                            startIcon={<AccountTreeIcon />}
                            onClick={() => navigate(`/hosts/${host.parent_host_id}`)}
                            sx={{ textTransform: 'none' }}
                        >
                            {t('hosts.viewParent', 'View Parent Host')}
                        </Button>
                    )}
                </Box>
                <Box sx={{ display: 'flex', gap: 1 }}>
                    <Button
                        variant="outlined"
                        color="primary"
                        startIcon={<SystemUpdateAltIcon />}
                        onClick={() => navigate(`/updates?host=${hostId}&securityOnly=false`)}
                        disabled={!host.active || (host.security_updates_count || 0) + (host.system_updates_count || 0) === 0}
                    >
                        {t('hosts.updates', 'Updates')}
                    </Button>
                    <Button
                        variant="outlined"
                        color="primary"
                        startIcon={<AppsIcon />}
                        onClick={handleRequestPackages}
                        disabled={!host.active}
                    >
                        {t('hosts.requestPackages', 'Request Avail. Packages')}
                    </Button>
                    <Button
                        variant="outlined"
                        color="warning"
                        startIcon={<RestartAltIcon />}
                        onClick={handleRebootClick}
                        disabled={!host.active || !host.is_agent_privileged}
                    >
                        {t('hosts.reboot', 'Reboot')}
                    </Button>
                    <Button
                        variant="outlined"
                        color="error"
                        startIcon={<PowerSettingsNewIcon />}
                        onClick={handleShutdownClick}
                        disabled={!host.active || !host.is_agent_privileged}
                    >
                        {t('hosts.shutdown', 'Shutdown')}
                    </Button>
                    {hasPermissionSync(SecurityRoles.UPDATE_AGENT) && (
                    <Button
                        variant="outlined"
                        color="info"
                        startIcon={<SystemUpdateAltIcon />}
                        onClick={handleUpdateAgent}
                        disabled={!host.active}
                    >
                        {t('hosts.updateAgent', 'Update Agent')}
                    </Button>
                    )}
                </Box>
            </Box>        </>
    );
};

export default HostDetailHeader;
