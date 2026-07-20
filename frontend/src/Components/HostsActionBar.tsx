// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

import React from 'react';
import Button from '@mui/material/Button';
import { Tooltip } from '@mui/material';
import DeleteIcon from '@mui/icons-material/Delete';
import CheckIcon from '@mui/icons-material/Check';
import SyncIcon from '@mui/icons-material/Sync';
import MedicalServicesIcon from '@mui/icons-material/MedicalServices';
import RestartAltIcon from '@mui/icons-material/RestartAlt';
import PowerSettingsNewIcon from '@mui/icons-material/PowerSettingsNew';
import SystemUpdateAltIcon from '@mui/icons-material/SystemUpdateAlt';
import SecurityIcon from '@mui/icons-material/Security';
import CampaignIcon from '@mui/icons-material/Campaign';
import { useTranslation } from 'react-i18next';
import ScrollableButtonBar from './ScrollableButtonBar';

interface HostsActionBarProps {
    canApproveHosts: boolean;
    canDeployAntivirus: boolean;
    canRebootHost: boolean;
    canShutdownHost: boolean;
    canUpdateAgent: boolean;
    canDeleteHost: boolean;
    selectionCount: number;
    hasPendingSelection: boolean;
    hasActivePrivilegedSelection: boolean;
    onApprove: () => void;
    onRefreshData: () => void;
    onBroadcastRefresh: () => void;
    onGetDiagnostics: () => void;
    onDeployOpenTelemetry: () => void;
    onDeployAntivirus: () => void;
    onRebootSelected: () => void;
    onShutdownSelected: () => void;
    onUpdateAgentSelected: () => void;
    onDelete: () => void;
}

/**
 * The bottom action-button bar for the Hosts grid.  Purely
 * presentational: all gating flags and handlers are supplied by the
 * parent so the Hosts component keeps ownership of state and hooks.
 */
const HostsActionBar: React.FC<HostsActionBarProps> = ({
    canApproveHosts,
    canDeployAntivirus,
    canRebootHost,
    canShutdownHost,
    canUpdateAgent,
    canDeleteHost,
    selectionCount,
    hasPendingSelection,
    hasActivePrivilegedSelection,
    onApprove,
    onRefreshData,
    onBroadcastRefresh,
    onGetDiagnostics,
    onDeployOpenTelemetry,
    onDeployAntivirus,
    onRebootSelected,
    onShutdownSelected,
    onUpdateAgentSelected,
    onDelete,
}) => {
    const { t } = useTranslation();

    return (
        <ScrollableButtonBar sx={{ flexShrink: 0, pb: 2 }}>
            {canApproveHosts && (
                <Button
                    variant="outlined"
                    startIcon={<CheckIcon />}
                    disabled={!hasPendingSelection}
                    onClick={onApprove}
                    color="success"
                >
                    {t('hosts.approveSelected', { defaultValue: 'Approve Selected' })}
                </Button>
            )}
            <Button
                variant="outlined"
                startIcon={<SyncIcon />}
                disabled={selectionCount === 0}
                onClick={onRefreshData}
                color="info"
            >
                {t('hosts.refreshAllData', 'Refresh All Data')}
            </Button>
            <Tooltip title={t('broadcast.refreshTooltip', 'Send a refresh-inventory broadcast to every connected agent')}>
                <Button
                    variant="outlined"
                    startIcon={<CampaignIcon />}
                    onClick={onBroadcastRefresh}
                    color="info"
                >
                    {t('broadcast.refresh', 'Broadcast Refresh')}
                </Button>
            </Tooltip>
            <Button
                variant="outlined"
                startIcon={<MedicalServicesIcon />}
                disabled={selectionCount !== 1}
                onClick={onGetDiagnostics}
                color="secondary"
            >
                {t('hosts.getDiagnostics', 'Get Diagnostics')}
            </Button>
            <Button
                variant="outlined"
                startIcon={<SystemUpdateAltIcon />}
                disabled={selectionCount === 0}
                onClick={onDeployOpenTelemetry}
                color="success"
            >
                {t('hosts.deployOpenTelemetry', 'Deploy OpenTelemetry')}
            </Button>
            {canDeployAntivirus && (
                <Button
                    variant="outlined"
                    startIcon={<SecurityIcon />}
                    disabled={selectionCount === 0}
                    onClick={onDeployAntivirus}
                    color="success"
                >
                    {t('hosts.deployAntivirus', 'Deploy Antivirus')}
                </Button>
            )}
            {canRebootHost && (
                <Button
                    variant="outlined"
                    startIcon={<RestartAltIcon />}
                    disabled={!hasActivePrivilegedSelection}
                    onClick={onRebootSelected}
                    color="warning"
                >
                    {t('hosts.rebootSelected', 'Reboot Selected')}
                </Button>
            )}
            {canShutdownHost && (
                <Button
                    variant="outlined"
                    startIcon={<PowerSettingsNewIcon />}
                    disabled={!hasActivePrivilegedSelection}
                    onClick={onShutdownSelected}
                    color="error"
                >
                    {t('hosts.shutdownSelected', 'Shutdown Selected')}
                </Button>
            )}
            {canUpdateAgent && (
                <Button
                    variant="outlined"
                    startIcon={<SystemUpdateAltIcon />}
                    disabled={!hasActivePrivilegedSelection}
                    onClick={onUpdateAgentSelected}
                    color="info"
                >
                    {t('hosts.updateAgentSelected', 'Update Agent on Selected')}
                </Button>
            )}
            {canDeleteHost && (
                <Button variant="outlined" startIcon={<DeleteIcon />} disabled={selectionCount === 0} onClick={onDelete}>
                    {t('common.delete')} {t('common.selected', { defaultValue: 'Selected' })}
                </Button>
            )}
        </ScrollableButtonBar>
    );
};

export default HostsActionBar;
