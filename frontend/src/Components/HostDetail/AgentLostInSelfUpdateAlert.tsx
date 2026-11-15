// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

import React from 'react';
import { useTranslation } from 'react-i18next';
import Alert from '@mui/material/Alert';
import AlertTitle from '@mui/material/AlertTitle';
import Box from '@mui/material/Box';
import Typography from '@mui/material/Typography';

import type { SysManageHost } from '../../Services/hosts';
import { formatUTCTimestamp } from '../../utils/dateUtils';

const AGENT = 'sysmanage-agent';
const START = [`sudo systemctl daemon-reload`, `sudo systemctl start ${AGENT}`];

const APT = [
    'sudo dpkg --configure -a',
    'sudo apt-get install -f -y',
    `sudo apt-get install --only-upgrade -y ${AGENT}`,
    `sudo systemctl start ${AGENT}`,
];

/** dnf and yum: drop a half-finished transaction's duplicate package, then
 *  finish the upgrade and put back any files the interrupted one removed. */
const rpm = (tool: string) => [
    `sudo ${tool} remove --duplicates -y`,
    `sudo ${tool} upgrade -y ${AGENT}`,
    `sudo ${tool} reinstall -y ${AGENT}`,
    ...START,
];

const ZYPPER = [
    'sudo zypper --non-interactive verify',
    `sudo zypper --non-interactive install --force ${AGENT}`,
    ...START,
];

/** The hand repair for the package manager the agent update went through,
 *  or null when there is no single right answer (every other platform). */
export function repairCommands(packageManager?: string | null): string[] | null {
    switch ((packageManager ?? '').toLowerCase()) {
        case 'apt':
        case 'apt-get':
        case 'dpkg':
            return APT;
        case 'dnf':
            return rpm('dnf');
        case 'yum':
            return rpm('yum');
        case 'zypper':
            return ZYPPER;
        default:
            return null;
    }
}

interface Props {
    host: SysManageHost | null;
}

/**
 * Shown on the host page when the agent was lost during its own upgrade
 * (2026-11-15): the package manager that upgrades the agent ran as the
 * agent's child, and stopping the agent's service killed it.  No command can
 * reach the host until someone repairs it by hand, so say what happened and
 * how.
 */
const AgentLostInSelfUpdateAlert: React.FC<Props> = ({ host }) => {
    const { t } = useTranslation();
    if (!host?.agent_lost_in_self_update) {
        return null;
    }
    const commands = repairCommands(host.agent_self_update_package_manager);
    return (
        <Alert severity="error" sx={{ mb: 2 }} data-testid="agent-lost-in-self-update">
            <AlertTitle>{t('hostDetail.agentLost.title', 'Agent lost during its own upgrade')}</AlertTitle>
            <Typography variant="body2" sx={{ mb: 1 }}>
                {t(
                    'hostDetail.agentLost.explanation',
                    'An update that included the agent package was sent to this host at {{time}}, and the agent has not checked in since. Upgrading the package stopped the agent before the package manager finished, so the package is probably half-installed. The server cannot repair this host, because no agent is running to receive the command.',
                    { time: formatUTCTimestamp(host.agent_self_update_dispatched_at) },
                )}
            </Typography>
            {commands ? (
                <>
                    <Typography variant="body2">
                        {t('hostDetail.agentLost.runCommands', 'Sign in to the host and run these commands to finish the upgrade and start the agent:')}
                    </Typography>
                    <Box
                        component="pre"
                        data-testid="agent-lost-commands"
                        sx={{ fontFamily: 'monospace', fontSize: '0.85rem', my: 1, p: 1, borderRadius: 1, bgcolor: 'action.hover', overflowX: 'auto' }}
                    >
                        {commands.join('\n')}
                    </Box>
                </>
            ) : (
                <Typography variant="body2" sx={{ mb: 1 }}>
                    {t('hostDetail.agentLost.generic', 'Sign in to the host, reinstall the agent package with the host\'s package manager, and then start the agent service.')}
                </Typography>
            )}
            <Typography variant="body2">
                {t('hostDetail.agentLost.clears', 'This notice clears as soon as the agent checks in again.')}
            </Typography>
        </Alert>
    );
};

export default AgentLostInSelfUpdateAlert;
