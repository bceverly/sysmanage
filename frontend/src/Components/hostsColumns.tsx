// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

import React from 'react';
import { GridColDef } from '@mui/x-data-grid';
import Box from '@mui/material/Box';
import { Chip, IconButton, Tooltip } from '@mui/material';
import VisibilityIcon from '@mui/icons-material/Visibility';
import AccountTreeIcon from '@mui/icons-material/AccountTree';
import HealthAndSafetyIcon from '@mui/icons-material/HealthAndSafety';
import { TFunction } from 'i18next';
import { parseUTCTimestamp } from '../utils/dateUtils';
import { SysManageHost } from '../Services/hosts';

interface BuildHostColumnsArgs {
    t: TFunction;
    navigate: (path: string) => void;
    canViewHostDetails: boolean;
    tableData: SysManageHost[];
    hasHealthData: boolean;
}

/** Build the DataGrid column definitions for the Hosts grid. */
export function buildHostColumns({
    t,
    navigate,
    canViewHostDetails,
    tableData,
    hasHealthData,
}: BuildHostColumnsArgs): GridColDef[] {
    return [
        { field: 'id', headerName: t('common.id', 'ID'), width: 70 },
        {
            field: 'fqdn',
            headerName: t('hosts.fqdn'),
            width: 220,
            renderCell: (params) => {
                const row = params.row;
                const isChildHost = !!row.parent_host_id;
                // Find parent hostname for tooltip
                const parentHost = isChildHost ? tableData.find(h => h.id === row.parent_host_id) : null;

                return (
                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
                        {isChildHost && (
                            <Tooltip title={t('hosts.childHostOf', 'Child host of {{parent}}', { parent: parentHost?.fqdn || row.parent_host_id })}>
                                <AccountTreeIcon
                                    sx={{
                                        fontSize: 16,
                                        color: 'info.main',
                                        ml: 1
                                    }}
                                />
                            </Tooltip>
                        )}
                        <span>{row.fqdn}</span>
                    </Box>
                );
            }
        },
        { field: 'platform', headerName: t('hosts.platform'), width: 120 },
        { field: 'ipv4', headerName: t('hosts.ipv4'), width: 150 },
        { field: 'ipv6', headerName: t('hosts.ipv6'), width: 200 },
        {
            field: 'status',
            headerName: t('hosts.status'),
            width: 280,  // Increased width for status and update chips
            display: 'flex',
            renderCell: (params) => {
                const row = params.row;
                const lastAccess = parseUTCTimestamp(row.last_access);
                const now = new Date();
                const diffMinutes = lastAccess ? Math.floor((now.getTime() - lastAccess.getTime()) / 60000) : Infinity;

                // Consider host "up" if last access was within 5 minutes
                const isRecentlyActive = diffMinutes <= 5;
                const displayStatus = isRecentlyActive ? 'up' : 'down';

                // Check if approval is needed
                const needsApproval = row.approval_status === 'pending';

                return (
                    <Box component="span" sx={{ display: 'inline-flex', flexWrap: 'wrap', gap: 0.5, alignItems: 'center' }}>
                        <Chip
                            label={displayStatus === 'up' ? t('hosts.up') : t('hosts.down')}
                            color={displayStatus === 'up' ? 'success' : 'error'}
                            size="small"
                            title={t('hosts.lastSeen', 'Last seen {{minutes}} minutes ago', { minutes: diffMinutes })}
                        />
                        {needsApproval && (
                            <Chip
                                label={t('hosts.approvalNeeded')}
                                color="warning"
                                size="small"
                                variant="outlined"
                            />
                        )}
                        {row.reboot_required && (
                            <Chip
                                label={t('hosts.rebootRequired')}
                                color="error"
                                size="small"
                                variant="outlined"
                            />
                        )}
                        {(row.security_updates_count > 0 || row.system_updates_count > 0) && (() => {
                            const hasBothUpdates = row.security_updates_count > 0 && row.system_updates_count > 0;
                            const hasSecurityOnly = row.security_updates_count > 0;
                            let updatesTitle: string;
                            if (hasBothUpdates) {
                                updatesTitle = t('hosts.securityAndSystemUpdates', '{{security}} security, {{system}} system updates', {
                                    security: row.security_updates_count,
                                    system: row.system_updates_count
                                });
                            } else if (hasSecurityOnly) {
                                updatesTitle = t('hosts.securityUpdatesOnly', '{{count}} security updates', { count: row.security_updates_count });
                            } else {
                                updatesTitle = t('hosts.systemUpdatesOnly', '{{count}} system updates', { count: row.system_updates_count });
                            }
                            return (
                                <Chip
                                    label={t('hosts.swUpdates', 'SW Updates')}
                                    color={row.security_updates_count > 0 ? 'error' : 'warning'}
                                    size="small"
                                    variant="outlined"
                                    title={updatesTitle}
                                />
                            );
                        })()}
                        {(row.os_upgrades_count && row.os_upgrades_count > 0) && (
                            <Chip
                                label={t('hosts.osUpgrade', 'OS Upgrade')}
                                color="info"
                                size="small"
                                variant="outlined"
                                title={t('hosts.osUpgradeAvailable', 'OS upgrade available for this host')}
                            />
                        )}
                    </Box>
                );
            }
        },
        {
            field: 'is_agent_privileged',
            headerName: t('hosts.privileged'),
            width: 100,
            renderCell: (params) => {
                // Don't show anything if host is down
                if (params.row.status === 'down') {
                    return null;
                }
                const isPrivileged = params.value;
                if (isPrivileged === undefined || isPrivileged === null) {
                    return <span style={{ color: '#666', fontStyle: 'italic' }}>{t('hosts.unknown', 'Unknown')}</span>;
                }
                return (
                    <Chip
                        label={isPrivileged ? t('common.yes') : t('common.no')}
                        color={isPrivileged ? 'success' : 'error'}
                        size="small"
                        variant="filled"
                        title={isPrivileged ? t('hosts.runningPrivileged') : t('hosts.runningUnprivileged')}
                    />
                );
            }
        },
        {
            field: 'agent_version',
            headerName: t('hosts.agentVersion', 'Agent Version'),
            width: 130,
        },
        {
            field: 'script_execution_enabled',
            headerName: t('hosts.scriptsEnabled'),
            width: 120,
            renderCell: (params) => {
                // Don't show anything if host is down
                if (params.row.status === 'down') {
                    return null;
                }
                const scriptsEnabled = params.value;
                if (scriptsEnabled === undefined || scriptsEnabled === null) {
                    return <span style={{ color: '#666', fontStyle: 'italic' }}>{t('hosts.unknown', 'Unknown')}</span>;
                }
                return (
                    <Chip
                        label={scriptsEnabled ? t('common.yes') : t('common.no')}
                        color={scriptsEnabled ? 'success' : 'error'}
                        size="small"
                        variant="filled"
                        title={scriptsEnabled ? t('hosts.scriptsEnabledTooltip') : t('hosts.scriptsDisabledTooltip')}
                    />
                );
            }
        },
        {
            field: 'last_access',
            headerName: t('hosts.lastCheckin'),
            width: 200,
            renderCell: (params) => {
                // Backend stores naive UTC; parseUTCTimestamp appends "Z" if needed
                const date = parseUTCTimestamp(params.value) || new Date(Number.NaN);
                const now = new Date();

                // Check if date is valid
                if (Number.isNaN(date.getTime())) {
                    return <span style={{ color: '#f44336' }}>{t('hosts.invalidDate', 'Invalid date')}</span>;
                }

                const diffSeconds = Math.floor((now.getTime() - date.getTime()) / 1000);

                // Handle negative differences (clock skew)
                const absDiff = Math.abs(diffSeconds);
                let timeText = '';

                if (absDiff < 60) {
                    timeText = diffSeconds < 0 ? t('hosts.justNow', 'Just now') : t('hosts.secondsAgo', '{{seconds}}s ago', { seconds: absDiff });
                } else if (absDiff < 3600) {
                    timeText = t('hosts.minutesAgo', '{{minutes}}m ago', { minutes: Math.floor(absDiff / 60) });
                } else if (absDiff < 86400) {
                    timeText = t('hosts.hoursAgo', '{{hours}}h ago', { hours: Math.floor(absDiff / 3600) });
                } else {
                    timeText = t('hosts.daysAgo', '{{days}}d ago', { days: Math.floor(absDiff / 86400) });
                }

                // Determine status color based on time difference
                let statusColor: string;
                if (absDiff < 120) {
                    statusColor = '#4caf50'; // green - very recent
                } else if (absDiff < 300) {
                    statusColor = '#ff9800'; // orange - somewhat recent
                } else {
                    statusColor = '#f44336'; // red - stale
                }

                return (
                    <div title={date.toLocaleString()}>
                        <div style={{ fontSize: '0.85em', color: statusColor }}>
                            {timeText}
                        </div>
                        <div style={{ fontSize: '0.7em', color: '#666' }}>
                            {date.toLocaleTimeString()}
                        </div>
                    </div>
                );
            }
        },
        {
            field: 'tags',
            headerName: t('hosts.tags', 'Tags'),
            width: 200,
            sortable: false,
            renderCell: (params) => {
                const tags = params.row.tags || [];
                if (tags.length === 0) {
                    return null;
                }
                return (
                    <Box sx={{
                        display: 'flex',
                        gap: 0.5,
                        flexWrap: 'wrap',
                        alignItems: 'center',
                        justifyContent: 'center',
                        height: '100%'
                    }}>
                        {tags.map((tag: { id: string; name: string }) => (
                            <Chip
                                key={tag.id}
                                label={tag.name}
                                size="small"
                                variant="filled"
                                sx={{
                                    fontSize: '0.75rem',
                                    backgroundColor: '#1976d2',
                                    color: '#ffffff',
                                    '&:hover': {
                                        backgroundColor: '#1565c0'
                                    }
                                }}
                            />
                        ))}
                    </Box>
                );
            }
        },
        ...(hasHealthData ? [{
            field: 'health_grade',
            headerName: t('hosts.healthGrade', 'Health'),
            width: 90,
            renderCell: (params: { row: { health_grade?: string; health_score?: number } }) => {
                const grade = params.row.health_grade;
                const score = params.row.health_score;
                if (!grade) {
                    return (
                        <Chip
                            icon={<HealthAndSafetyIcon sx={{ fontSize: 16 }} />}
                            label="-"
                            size="small"
                            variant="outlined"
                            sx={{ color: 'text.secondary' }}
                        />
                    );
                }
                const getGradeColor = () => {
                    switch (grade) {
                        case 'A+':
                        case 'A':
                            return 'success';
                        case 'B':
                            return 'info';
                        case 'C':
                            return 'warning';
                        case 'D':
                        case 'F':
                            return 'error';
                        default:
                            return 'default';
                    }
                };
                return (
                    <Chip
                        icon={<HealthAndSafetyIcon sx={{ fontSize: 16 }} />}
                        label={grade}
                        size="small"
                        color={getGradeColor()}
                        title={score === undefined ? undefined : t('hosts.healthScore', 'Health Score: {{score}}', { score })}
                    />
                );
            }
        }] : []),
        {
            field: 'actions',
            headerName: t('common.actions'),
            width: 100,
            sortable: false,
            filterable: false,
            renderCell: (params) => (
                canViewHostDetails ? (
                    <IconButton
                        color="primary"
                        size="small"
                        onClick={() => navigate(`/hosts/${params.row.id}`)}
                        title={t('common.view')}
                    >
                        <VisibilityIcon />
                    </IconButton>
                ) : null
            )
        }
    ];
}
