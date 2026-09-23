// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import Alert from '@mui/material/Alert';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Chip from '@mui/material/Chip';
import CircularProgress from '@mui/material/CircularProgress';
import Dialog from '@mui/material/Dialog';
import DialogActions from '@mui/material/DialogActions';
import DialogContent from '@mui/material/DialogContent';
import DialogContentText from '@mui/material/DialogContentText';
import DialogTitle from '@mui/material/DialogTitle';
import Stack from '@mui/material/Stack';
import Tab from '@mui/material/Tab';
import Tabs from '@mui/material/Tabs';
import Typography from '@mui/material/Typography';
import BuildIcon from '@mui/icons-material/Build';
import HealingIcon from '@mui/icons-material/Healing';
import { DataGrid, GridColDef } from '@mui/x-data-grid';

import Divider from '@mui/material/Divider';

import BaselineDiffPanel from '../Components/BaselineDiffPanel';
import ConfigRemediationRulesPanel from '../Components/ConfigRemediationRulesPanel';
import FileWatchPanel from '../Components/FileWatchPanel';
import { formatUTCTimestamp } from '../utils/dateUtils';
import { hasPermission, SecurityRoles } from '../Services/permissions';
import {
    ConfigDriftFinding,
    ConfigDriftHostSummary,
    getDriftingHosts,
    getHostDrift,
    remediateDrift,
} from '../Services/configManagementService';
import {
    ConfigRemediationMatch,
    getFindingRemediation,
    repairFinding,
} from '../Services/configFleetService';

/** Pull the server's explanation out of an axios error, or fall back. */
const messageFrom = (err: unknown, fallback: string): string => {
    const detail = (err as { response?: { data?: { detail?: unknown } } })?.response
        ?.data?.detail;
    return typeof detail === 'string' && detail ? detail : fallback;
};

/** How long a divergence has stood, in whole days. */
const daysSince = (iso: string | null): number | null => {
    if (!iso) return null;
    const then = Date.parse(iso);
    if (Number.isNaN(then)) return null;
    return Math.floor((Date.now() - then) / 86_400_000);
};

const ConfigDrift: React.FC = () => {
    const { t } = useTranslation();
    const [hosts, setHosts] = useState<ConfigDriftHostSummary[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const [notice, setNotice] = useState<string | null>(null);

    const [detailHost, setDetailHost] = useState<ConfigDriftHostSummary | null>(null);
    const [findings, setFindings] = useState<ConfigDriftFinding[]>([]);
    const [findingsError, setFindingsError] = useState<string | null>(null);


    const [confirmTarget, setConfirmTarget] = useState<{
        host: ConfigDriftHostSummary;
        profileId: string;
        profileName: string;
    } | null>(null);
    const [remediating, setRemediating] = useState(false);
    const [canRemediate, setCanRemediate] = useState(false);
    const [tab, setTab] = useState(0);
    // Which findings a remediation playbook covers, keyed by finding id.
    // Fetched when the detail dialog opens rather than per row on hover:
    // an operator deciding how to fix a host wants to see every option at
    // once, not discover them one mouse-over at a time.
    const [matches, setMatches] = useState<Record<string, ConfigRemediationMatch>>(
        {},
    );

    const load = useCallback(async () => {
        try {
            setHosts(await getDriftingHosts());
            setError(null);
        } catch (err) {
            setError(
                messageFrom(err, t('configDrift.loadFailed', 'Could not load drift status')),
            );
        } finally {
            setLoading(false);
        }
    }, [t]);

    useEffect(() => {
        load();
    }, [load]);

    useEffect(() => {
        const check = async () => {
            try {
                setCanRemediate(await hasPermission(SecurityRoles.RUN_SCRIPT));
            } catch (err) {
                // Fail closed and say so: a page of dead buttons with no
                // explanation is the outcome to avoid.
                console.error('Failed to resolve drift permissions:', err);
            }
        };
        check();
    }, []);

    const openDetail = useCallback(async (row: ConfigDriftHostSummary) => {
        setDetailHost(row);
        setFindings([]);
        setMatches({});
        setFindingsError(null);
        try {
            const rows = await getHostDrift(row.host_id);
            setFindings(rows);
            // Settled, not all: one lookup failing must not hide every other
            // finding's repair. A finding with no entry simply shows the
            // baseline button, which is the behavior before playbooks existed.
            const resolved = await Promise.allSettled(
                rows.map((finding) => getFindingRemediation(finding.id)),
            );
            const found: Record<string, ConfigRemediationMatch> = {};
            resolved.forEach((result, index) => {
                if (result.status === 'fulfilled' && result.value.matched) {
                    found[rows[index].id] = result.value;
                }
            });
            setMatches(found);
        } catch (err) {
            setFindingsError(
                messageFrom(
                    err,
                    t('configDrift.findingsFailed', 'Could not load the findings for this host'),
                ),
            );
        }
    }, [t]);

    const runRepair = async (findingId: string) => {
        setRemediating(true);
        try {
            const result = await repairFinding(findingId);
            setNotice(result.message);
            setDetailHost(null);
            // Deliberately NOT reloading: the finding stays open until a
            // check-mode run confirms the fix, so a refresh would show
            // unchanged drift and read as "the button did nothing".
        } catch (err) {
            setError(
                messageFrom(
                    err,
                    t('configDrift.repairFailed', 'Could not queue the repair'),
                ),
            );
        } finally {
            setRemediating(false);
        }
    };

    const confirmRemediation = async () => {
        if (!confirmTarget) return;
        setRemediating(true);
        try {
            const result = await remediateDrift(
                confirmTarget.host.host_id,
                confirmTarget.profileId,
            );
            setNotice(result.message);
            setConfirmTarget(null);
            setDetailHost(null);
            // Deliberately NOT reloading the drift list: the findings stay
            // open until a check-mode run confirms the fix, so a refresh here
            // would show unchanged drift and read as "the button did nothing".
        } catch (err) {
            setError(
                messageFrom(err, t('configDrift.remediateFailed', 'Could not queue remediation')),
            );
            setConfirmTarget(null);
        } finally {
            setRemediating(false);
        }
    };

    const columns: GridColDef[] = useMemo(
        () => [
            {
                field: 'host_fqdn',
                headerName: t('configDrift.host', 'Host'),
                flex: 1,
                minWidth: 200,
                renderCell: (params) => params.value || params.row.host_id,
            },
            {
                field: 'finding_count',
                headerName: t('configDrift.differences', 'Differences'),
                width: 130,
            },
            {
                field: 'drifting_since',
                headerName: t('configDrift.driftingFor', 'Drifting for'),
                width: 170,
                renderCell: (params) => {
                    const days = daysSince(params.value as string | null);
                    if (days === null) return '';
                    // Days, not a timestamp: "19 days" is the triage signal;
                    // the exact moment it started rarely changes what you do.
                    return (
                        <Chip
                            size="small"
                            color={days >= 7 ? 'warning' : 'default'}
                            label={t('configDrift.days', '{{count}} days', { count: days })}
                        />
                    );
                },
            },
            {
                field: 'profile_names',
                headerName: t('configDrift.profiles', 'Profiles'),
                flex: 1,
                minWidth: 180,
                renderCell: (params) => ((params.value as string[]) || []).join(', '),
            },
            {
                field: 'actions',
                headerName: t('configDrift.actions', 'Actions'),
                width: 140,
                sortable: false,
                filterable: false,
                renderCell: (params) => (
                    <Button
                        size="small"
                        onClick={() => openDetail(params.row as ConfigDriftHostSummary)}
                    >
                        {t('configDrift.view', 'View')}
                    </Button>
                ),
            },
        ],
        [t, openDetail],
    );

    if (loading) {
        return (
            <Box sx={{ display: 'flex', justifyContent: 'center', p: 4 }}>
                <CircularProgress />
            </Box>
        );
    }

    return (
        <Box sx={{ p: 3 }}>
            <Typography variant="h5" sx={{ mb: 1 }}>
                {t('configDrift.title', 'Configuration Drift')}
            </Typography>
            <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
                {t(
                    'configDrift.intro',
                    'Hosts that no longer match the profile assigned to them. Drift is ' +
                        'detected by dry runs, so nothing here has been changed -- ' +
                        'remediating re-applies the profile for real.',
                )}
            </Typography>

            {error && (
                <Alert severity="error" sx={{ mb: 2 }} onClose={() => setError(null)}>
                    {error}
                </Alert>
            )}
            {notice && (
                <Alert severity="success" sx={{ mb: 2 }} onClose={() => setNotice(null)}>
                    {notice}
                </Alert>
            )}

            {/* Playbooks share this page rather than getting their own nav
                entry: a rule is written in response to drift you are looking
                at, so the two belong one click apart. */}
            <Tabs value={tab} onChange={(_e, value) => setTab(value)} sx={{ mb: 2 }}>
                <Tab label={t('configDrift.tabDrift', 'Drifting hosts')} />
                <Tab label={t('configDrift.tabPlaybooks', 'Remediation playbooks')} />
                <Tab label={t('configDrift.tabFileWatches', 'Watched files')} />
            </Tabs>

            {tab === 1 && <ConfigRemediationRulesPanel canEdit={canRemediate} />}
            {tab === 2 && <FileWatchPanel canEdit={canRemediate} />}

            {tab === 0 &&
                (hosts.length === 0 ? (
                    <Alert severity="success">
                        {t(
                            'configDrift.noDrift',
                            'Every host matches its assigned profile.',
                        )}
                    </Alert>
                ) : (
                    <div style={{ width: '100%', height: 520 }}>
                        <DataGrid
                            rows={hosts}
                            columns={columns}
                            getRowId={(row) => row.host_id}
                            initialState={{
                                pagination: { paginationModel: { pageSize: 25 } },
                            }}
                            pageSizeOptions={[10, 25, 50]}
                            disableRowSelectionOnClick
                        />
                    </div>
                ))}

            <Dialog
                open={Boolean(detailHost)}
                onClose={() => setDetailHost(null)}
                maxWidth="md"
                fullWidth
            >
                <DialogTitle>
                    {t('configDrift.detailTitle', 'Differences on {{host}}', {
                        host: detailHost?.host_fqdn || detailHost?.host_id || '',
                    })}
                </DialogTitle>
                <DialogContent>
                    {findingsError && <Alert severity="error">{findingsError}</Alert>}
                    {!findingsError && findings.length === 0 && (
                        <DialogContentText>
                            {t('configDrift.noFindings', 'No open differences for this host.')}
                        </DialogContentText>
                    )}
                    <Stack spacing={2} sx={{ mt: 1 }}>
                        {findings.map((finding) => (
                            <Box key={finding.id}>
                                <Typography variant="subtitle2">
                                    {finding.task_name}
                                </Typography>
                                <Typography variant="body2" color="text.secondary">
                                    {finding.detail ||
                                        t('configDrift.noDetail', 'No further detail reported.')}
                                </Typography>
                                <Typography variant="caption" color="text.secondary">
                                    {/* Label and timestamp are separate on purpose. As
                                        'First seen {{when}}' the placeholder was pinned to
                                        the end of the sentence, which Hindi (SOV, time
                                        expression first) has no correct rendering for --
                                        the translation service returned it unchanged for
                                        hi alone while all twelve other locales were fine.
                                        A label plus a machine-formatted value carries no
                                        word order to get wrong. */}
                                    {t('configDrift.seenSince', 'First seen')}
                                    {finding.first_seen_at
                                        ? `: ${formatUTCTimestamp(finding.first_seen_at)}`
                                        : ''}
                                    {finding.profile_name ? ` -- ${finding.profile_name}` : ''}
                                </Typography>
                                {canRemediate && detailHost && (
                                    <Stack direction="row" spacing={1} sx={{ mt: 1 }}>
                                        {/* The targeted repair comes FIRST when one
                                            exists: re-applying a four-hundred-task
                                            baseline to fix one file mode is the
                                            blunter of the two, and the order of the
                                            buttons is what says so. */}
                                        {matches[finding.id] &&
                                            !matches[finding.id].unavailable && (
                                                <Button
                                                    size="small"
                                                    variant="contained"
                                                    startIcon={<HealingIcon />}
                                                    disabled={remediating}
                                                    onClick={() => runRepair(finding.id)}
                                                >
                                                    {t(
                                                        'configDrift.repairWith',
                                                        'Repair with {{profile}}',
                                                        {
                                                            profile:
                                                                matches[finding.id]
                                                                    .remediation_profile_name ||
                                                                '',
                                                        },
                                                    )}
                                                </Button>
                                            )}
                                        {matches[finding.id]?.unavailable && (
                                            <Chip
                                                size="small"
                                                color="warning"
                                                label={t(
                                                    'configDrift.repairUnavailable',
                                                    'Its repair profile is not active',
                                                )}
                                            />
                                        )}
                                        {finding.profile_id && (
                                            <Button
                                                size="small"
                                                variant="outlined"
                                                startIcon={<BuildIcon />}
                                                onClick={() =>
                                                    setConfirmTarget({
                                                        host: detailHost,
                                                        profileId: finding.profile_id as string,
                                                        profileName:
                                                            finding.profile_name || '',
                                                    })
                                                }
                                            >
                                                {t(
                                                    'configDrift.remediate',
                                                    'Remediate to baseline',
                                                )}
                                            </Button>
                                        )}
                                    </Stack>
                                )}
                            </Box>
                        ))}
                    </Stack>

                    {detailHost && (
                        <>
                            <Divider sx={{ my: 3 }} />
                            <BaselineDiffPanel hostId={detailHost.host_id} />
                        </>
                    )}
                </DialogContent>
                <DialogActions>
                    <Button onClick={() => setDetailHost(null)}>
                        {t('common.close', 'Close')}
                    </Button>
                </DialogActions>
            </Dialog>

            <Dialog open={Boolean(confirmTarget)} onClose={() => setConfirmTarget(null)}>
                <DialogTitle>
                    {t('configDrift.confirmTitle', 'Re-apply this profile?')}
                </DialogTitle>
                <DialogContent>
                    {/* Names both the host and the profile on purpose: the same
                        button pressed from a fleet view is a fleet-wide change,
                        and "are you sure?" without a subject is not a check. */}
                    <DialogContentText>
                        {t(
                            'configDrift.confirmBody',
                            'This runs {{profile}} on {{host}} for real and changes the ' +
                                'host to match it. It is held until the next maintenance ' +
                                'window if one applies.',
                            {
                                profile: confirmTarget?.profileName || '',
                                host:
                                    confirmTarget?.host.host_fqdn ||
                                    confirmTarget?.host.host_id ||
                                    '',
                            },
                        )}
                    </DialogContentText>
                </DialogContent>
                <DialogActions>
                    <Button onClick={() => setConfirmTarget(null)} disabled={remediating}>
                        {t('common.cancel', 'Cancel')}
                    </Button>
                    <Button
                        variant="contained"
                        color="warning"
                        onClick={confirmRemediation}
                        disabled={remediating}
                    >
                        {t('configDrift.confirmAction', 'Remediate')}
                    </Button>
                </DialogActions>
            </Dialog>
        </Box>
    );
};

export default ConfigDrift;
