// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

import React from 'react';
import { Box, Card, CardContent, Chip, Divider, Tooltip, Typography } from '@mui/material';
import CheckCircleIcon from '@mui/icons-material/CheckCircle';
import WarningAmberIcon from '@mui/icons-material/WarningAmber';
import HelpOutlineIcon from '@mui/icons-material/HelpOutline';
import { useTranslation } from 'react-i18next';

/**
 * What the agent on this host advertises it can do — ROADMAP Phase 19.
 *
 * THREE states, deliberately, matching the server service:
 *   - a report with nothing missing .... full capability
 *   - a report with gaps ............... limited, with the reason per group
 *   - NO report ........................ UNKNOWN, not "full"
 *
 * The third is the one worth being careful about: every agent that has not yet
 * upgraded advertises nothing, and showing those as "full" would state
 * something the server cannot know. It reads as unknown until an agent says
 * otherwise.
 */

export interface AgentCapabilityReport {
    schema_version?: number;
    capabilities?: string[];
    commands?: string[];
    unavailable?: Record<string, string>;
    partial?: Record<string, string[]>;
}

interface HostCapabilitiesCardProps {
    report?: AgentCapabilityReport | null;
    limited?: boolean | null;
    updatedAt?: string | null;
}

const HostCapabilitiesCard: React.FC<HostCapabilitiesCardProps> = ({ report, limited, updatedAt }) => {
    const { t } = useTranslation();

    // Reason CODES come from the agent, never prose — so they can be localized
    // here rather than shipped in whatever language the agent was built with.
    const reasonText = (code: string): string => {
        const known: Record<string, string> = {
            no_handler: t('hostCapabilities.reasonNoHandler', 'Not built into this agent'),
            unsupported_os: t('hostCapabilities.reasonUnsupportedOs', 'Not supported on this OS'),
            unsupported_arch: t('hostCapabilities.reasonUnsupportedArch', 'No build for this architecture'),
        };
        // An unknown code from a newer agent still tells the operator something,
        // so show it rather than swallowing it.
        return known[code] || code;
    };

    if (!report) {
        return (
            <Card sx={{ mb: 2 }}>
                <CardContent>
                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1 }}>
                        <HelpOutlineIcon color="disabled" />
                        <Typography variant="h6">
                            {t('hostCapabilities.title', 'Agent Capabilities')}
                        </Typography>
                    </Box>
                    <Typography variant="body2" color="text.secondary">
                        {t(
                            'hostCapabilities.unknown',
                            'This agent has not advertised its capabilities. Older agents do not report them; the host is not restricted.'
                        )}
                    </Typography>
                </CardContent>
            </Card>
        );
    }

    const unavailable = report.unavailable || {};
    const partial = report.partial || {};
    const groups = report.capabilities || [];
    const unavailableKeys = Object.keys(unavailable);
    const partialKeys = Object.keys(partial);

    return (
        <Card sx={{ mb: 2 }}>
            <CardContent>
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1 }}>
                    {limited ? <WarningAmberIcon color="warning" /> : <CheckCircleIcon color="success" />}
                    <Typography variant="h6" sx={{ flexGrow: 1 }}>
                        {t('hostCapabilities.title', 'Agent Capabilities')}
                    </Typography>
                    <Chip
                        size="small"
                        color={limited ? 'warning' : 'success'}
                        label={
                            limited
                                ? t('hostCapabilities.limited', 'Limited')
                                : t('hostCapabilities.full', 'Full')
                        }
                    />
                </Box>

                {updatedAt && (
                    <Typography variant="caption" color="text.secondary">
                        {t('hostCapabilities.updated', 'Reported')}: {new Date(updatedAt).toLocaleString()}
                    </Typography>
                )}

                {groups.length > 0 && (
                    <Box sx={{ mt: 2 }}>
                        <Typography variant="subtitle2" gutterBottom>
                            {t('hostCapabilities.supported', 'Supported')}
                        </Typography>
                        <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.5 }}>
                            {groups.map((group) => (
                                <Chip key={group} size="small" variant="outlined" label={group} />
                            ))}
                        </Box>
                    </Box>
                )}

                {unavailableKeys.length > 0 && (
                    <>
                        <Divider sx={{ my: 2 }} />
                        <Typography variant="subtitle2" gutterBottom>
                            {t('hostCapabilities.unavailable', 'Unavailable')}
                        </Typography>
                        <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.5 }}>
                            {unavailableKeys.map((group) => (
                                <Tooltip key={group} title={reasonText(unavailable[group])}>
                                    <Chip
                                        size="small"
                                        color="warning"
                                        variant="outlined"
                                        label={`${group} — ${reasonText(unavailable[group])}`}
                                    />
                                </Tooltip>
                            ))}
                        </Box>
                    </>
                )}

                {partialKeys.length > 0 && (
                    <>
                        <Divider sx={{ my: 2 }} />
                        <Typography variant="subtitle2" gutterBottom>
                            {t('hostCapabilities.partial', 'Partially supported')}
                        </Typography>
                        <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.5 }}>
                            {partialKeys.map((group) => (
                                <Tooltip
                                    key={group}
                                    title={(partial[group] || []).join(', ')}
                                >
                                    <Chip
                                        size="small"
                                        color="warning"
                                        variant="outlined"
                                        label={`${group} (${(partial[group] || []).length})`}
                                    />
                                </Tooltip>
                            ))}
                        </Box>
                    </>
                )}
            </CardContent>
        </Card>
    );
};

export default HostCapabilitiesCard;
