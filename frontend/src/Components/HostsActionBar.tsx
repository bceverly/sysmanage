// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

import React from 'react';
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
import SelectionActionBar, { SelectionAction } from './SelectionActionBar';

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
    onClearSelection?: () => void;
}

/**
 * The action bar for the Hosts grid.  Purely presentational: all gating flags
 * and handlers are supplied by the parent so the Hosts component keeps
 * ownership of state and hooks.
 *
 * The four primaries are chosen by FREQUENCY, not importance -- the thing an
 * operator clicks twenty times a day earns the pixels.  Everything else lives
 * in the overflow menu, grouped, with the power operations kept away from the
 * benign ones and Delete alone behind the final divider.
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
    onClearSelection,
}) => {
    const { t } = useTranslation();

    const needsAny = t('common.requiresSelection', 'Select at least one row');
    const needsOne = t('common.requiresSingleSelection', 'Select exactly one row');
    const needsPending = t(
        'hosts.requiresPendingHost',
        'Select a host that is awaiting approval',
    );
    const needsPrivileged = t(
        'hosts.requiresActivePrivileged',
        'Select an active host running in privileged mode',
    );

    const groupDeploy = t('hosts.actionGroupDeploy', 'Deploy');
    const groupPower = t('hosts.actionGroupPower', 'Power');

    const actions: SelectionAction[] = [
        {
            id: 'approve',
            label: t('hosts.approveSelected', { defaultValue: 'Approve Selected' }),
            icon: <CheckIcon />,
            color: 'success',
            primary: true,
            hidden: !canApproveHosts,
            disabled: !hasPendingSelection,
            disabledReason: needsPending,
            onClick: onApprove,
        },
        {
            id: 'refresh-data',
            label: t('hosts.refreshAllData', 'Refresh All Data'),
            icon: <SyncIcon />,
            color: 'info',
            primary: true,
            disabled: selectionCount === 0,
            disabledReason: needsAny,
            onClick: onRefreshData,
        },
        {
            id: 'update-agent',
            label: t('hosts.updateAgentSelected', 'Update Agent on Selected'),
            icon: <SystemUpdateAltIcon />,
            color: 'info',
            primary: true,
            hidden: !canUpdateAgent,
            disabled: !hasActivePrivilegedSelection,
            disabledReason: needsPrivileged,
            onClick: onUpdateAgentSelected,
        },
        {
            id: 'diagnostics',
            label: t('hosts.getDiagnostics', 'Get Diagnostics'),
            icon: <MedicalServicesIcon />,
            color: 'secondary',
            primary: true,
            disabled: selectionCount !== 1,
            disabledReason: needsOne,
            onClick: onGetDiagnostics,
        },
        {
            id: 'broadcast-refresh',
            label: t('broadcast.refresh', 'Broadcast Refresh'),
            icon: <CampaignIcon />,
            tooltip: t(
                'broadcast.refreshTooltip',
                'Send a refresh-inventory broadcast to every connected agent',
            ),
            onClick: onBroadcastRefresh,
        },
        {
            id: 'deploy-otel',
            label: t('hosts.deployOpenTelemetry', 'Deploy OpenTelemetry'),
            icon: <SystemUpdateAltIcon />,
            group: groupDeploy,
            disabled: selectionCount === 0,
            disabledReason: needsAny,
            onClick: onDeployOpenTelemetry,
        },
        {
            id: 'deploy-antivirus',
            label: t('hosts.deployAntivirus', 'Deploy Antivirus'),
            icon: <SecurityIcon />,
            group: groupDeploy,
            hidden: !canDeployAntivirus,
            disabled: selectionCount === 0,
            disabledReason: needsAny,
            onClick: onDeployAntivirus,
        },
        {
            id: 'reboot',
            label: t('hosts.rebootSelected', 'Reboot Selected'),
            icon: <RestartAltIcon />,
            group: groupPower,
            color: 'warning',
            hidden: !canRebootHost,
            disabled: !hasActivePrivilegedSelection,
            disabledReason: needsPrivileged,
            onClick: onRebootSelected,
        },
        {
            id: 'shutdown',
            label: t('hosts.shutdownSelected', 'Shutdown Selected'),
            icon: <PowerSettingsNewIcon />,
            group: groupPower,
            color: 'error',
            hidden: !canShutdownHost,
            disabled: !hasActivePrivilegedSelection,
            disabledReason: needsPrivileged,
            onClick: onShutdownSelected,
        },
        {
            id: 'delete',
            label: `${t('common.delete')} ${t('common.selected', { defaultValue: 'Selected' })}`,
            icon: <DeleteIcon />,
            destructive: true,
            hidden: !canDeleteHost,
            disabled: selectionCount === 0,
            disabledReason: needsAny,
            onClick: onDelete,
        },
    ];

    return (
        <SelectionActionBar
            actions={actions}
            selectionCount={selectionCount}
            onClearSelection={onClearSelection}
            sx={{ flexShrink: 0, pb: 2 }}
        />
    );
};

export default HostsActionBar;
