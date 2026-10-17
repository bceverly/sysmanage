// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

// What a held command IS, in words, from the server's safe summary (the raw
// payload never reaches the browser -- it can carry an Ubuntu Pro token or a
// whole config file).

import type { TFunction } from 'i18next';

import type { HeldCommand } from '../../Services/maintenanceWindows';
import { formatUTCTimestamp } from '../../utils/dateUtils';

const commandName = (t: TFunction, type: string | null): string => {
    if (!type) {
        return t('maintenanceWindows.held.cmd.unknown', 'Command');
    }
    const names: Record<string, string> = {
        apply_updates: t('maintenanceWindows.held.cmd.applyUpdates', 'Apply updates'),
        apply_deployment_plan: t('maintenanceWindows.held.cmd.deploymentPlan', 'Deployment plan'),
        ubuntu_pro_attach: t('maintenanceWindows.held.cmd.proAttach', 'Ubuntu Pro attach'),
        ubuntu_pro_detach: t('maintenanceWindows.held.cmd.proDetach', 'Ubuntu Pro detach'),
        ubuntu_pro_enable_service: t('maintenanceWindows.held.cmd.proEnable', 'Ubuntu Pro: enable service'),
        ubuntu_pro_disable_service: t('maintenanceWindows.held.cmd.proDisable', 'Ubuntu Pro: disable service'),
        reboot_system: t('maintenanceWindows.held.cmd.reboot', 'Reboot'),
        shutdown_system: t('maintenanceWindows.held.cmd.shutdown', 'Shut down'),
        restart_service: t('maintenanceWindows.held.cmd.restartService', 'Restart service'),
        execute_script: t('maintenanceWindows.held.cmd.runScript', 'Run script'),
        update_agent: t('maintenanceWindows.held.cmd.updateAgent', 'Update agent'),
        collect_available_packages: t('maintenanceWindows.held.cmd.collectPackages', 'Refresh package list'),
        configure_network_discovery: t('maintenanceWindows.held.cmd.networkDiscovery', 'Configure network discovery'),
        run_query_pack: t('maintenanceWindows.held.cmd.queryPack', 'Collect facts'),
    };
    // An unlisted type is still identified, by its own name.
    return names[type] ?? type;
};

const packageText = (t: TFunction, packages?: { names: string[]; count: number }): string => {
    if (!packages || packages.count === 0) {
        return '';
    }
    const shown = packages.names.join(', ');
    const more = packages.count - packages.names.length;
    return more > 0
        ? t('maintenanceWindows.held.packagesMore', '{{names}} (+{{more}})', { names: shown, more })
        : shown;
};

/** e.g. "Apply updates: cups, snapd (+2)" or "Ubuntu Pro attach". */
export const heldCommandText = (t: TFunction, item: HeldCommand): string => {
    const name = commandName(t, item.command_type);
    const detail =
        packageText(t, item.details?.packages) ||
        (typeof item.details?.service_name === 'string' ? item.details.service_name : '');
    return detail ? `${name}: ${detail}` : name;
};

/** Which window releases it, and when. */
export const releaseText = (t: TFunction, item: HeldCommand): string => {
    const window = item.release?.window;
    if (window) {
        return t('maintenanceWindows.held.releasedBy', "'{{name}}' at {{time}}", {
            name: window.name,
            time: formatUTCTimestamp(window.starts_at ?? ''),
        });
    }
    if (item.release?.blackout) {
        return t('maintenanceWindows.held.afterBlackout', "When the '{{name}}' blackout ends", {
            name: item.release.blackout,
        });
    }
    return t('maintenanceWindows.held.nextCheck', 'At the next check');
};
