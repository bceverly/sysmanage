// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

import React, { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import Alert from '@mui/material/Alert';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Chip from '@mui/material/Chip';
import Dialog from '@mui/material/Dialog';
import DialogActions from '@mui/material/DialogActions';
import DialogContent from '@mui/material/DialogContent';
import DialogTitle from '@mui/material/DialogTitle';
import LinearProgress from '@mui/material/LinearProgress';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';

import { formatUTCTimestamp } from '../utils/dateUtils';
import {
    ConfigJob,
    ConfigJobTarget,
    cancelJob,
    getJobTargets,
    getJobs,
} from '../Services/configFleetService';

const messageFrom = (err: unknown, fallback: string): string => {
    const detail = (err as { response?: { data?: { detail?: unknown } } })?.response
        ?.data?.detail;
    return typeof detail === 'string' && detail ? detail : fallback;
};

/** How often a running job is re-read. */
const POLL_MS = 5000;

const STATUS_COLOR: Record<string, 'default' | 'info' | 'success' | 'error' | 'warning'> =
    {
        pending: 'default',
        running: 'info',
        completed: 'success',
        failed: 'error',
        canceled: 'warning',
    };

const TARGET_COLOR: Record<string, 'default' | 'info' | 'success' | 'error' | 'warning'> =
    {
        pending: 'default',
        queued: 'info',
        succeeded: 'success',
        failed: 'error',
        skipped: 'warning',
    };

interface Props {
    canCancel: boolean;
    /** Bumped by the templates panel after a launch, to force a refresh. */
    refreshToken?: number;
}

/**
 * Fleet job progress.
 *
 * Polls only while something is moving. A finished job never changes again, so
 * a page left open on last night's jobs costs nothing -- and a fleet job is
 * exactly the page people leave open.
 */
const ConfigJobsPanel: React.FC<Props> = ({ canCancel, refreshToken }) => {
    const { t } = useTranslation();
    const [jobs, setJobs] = useState<ConfigJob[]>([]);
    const [error, setError] = useState<string | null>(null);
    const [detail, setDetail] = useState<ConfigJob | null>(null);
    const [targets, setTargets] = useState<ConfigJobTarget[]>([]);

    const load = useCallback(async () => {
        try {
            setJobs(await getJobs());
            setError(null);
        } catch (err) {
            setError(messageFrom(err, t('configFleet.jobsFailed', 'Could not load jobs')));
        }
    }, [t]);

    useEffect(() => {
        load();
    }, [load, refreshToken]);

    const anyActive = jobs.some(
        (job) => job.status === 'running' || job.status === 'pending',
    );

    useEffect(() => {
        if (!anyActive) return undefined;
        const handle = setInterval(load, POLL_MS);
        return () => clearInterval(handle);
    }, [anyActive, load]);

    const openDetail = async (job: ConfigJob) => {
        setDetail(job);
        setTargets([]);
        try {
            setTargets(await getJobTargets(job.id));
        } catch (err) {
            setError(
                messageFrom(err, t('configFleet.targetsFailed', 'Could not load the hosts')),
            );
        }
    };

    const stop = async (job: ConfigJob) => {
        try {
            await cancelJob(
                job.id,
                t('configFleet.cancelledByOperator', 'Cancelled by an operator'),
            );
            await load();
        } catch (err) {
            setError(
                messageFrom(err, t('configFleet.cancelFailed', 'Could not cancel this job')),
            );
        }
    };

    const doneCount = (job: ConfigJob) =>
        job.succeeded_count + job.failed_count + job.skipped_count;

    return (
        <Box>
            {error && (
                <Alert severity="error" sx={{ mb: 2 }} onClose={() => setError(null)}>
                    {error}
                </Alert>
            )}

            {jobs.length === 0 ? (
                <Alert severity="info">
                    {t(
                        'configFleet.noJobs',
                        'No fleet jobs have run yet. Launch one from the Templates tab.',
                    )}
                </Alert>
            ) : (
                <Stack spacing={1}>
                    {jobs.map((job) => (
                        <Box
                            key={job.id}
                            sx={{ border: 1, borderColor: 'divider', borderRadius: 1, p: 2 }}
                        >
                            <Stack
                                direction="row"
                                spacing={2}
                                alignItems="center"
                                flexWrap="wrap"
                            >
                                <Typography variant="subtitle1" sx={{ flexGrow: 1 }}>
                                    {job.template_name || job.profile_name || job.id}
                                </Typography>
                                <Chip
                                    size="small"
                                    color={STATUS_COLOR[job.status] || 'default'}
                                    label={job.status}
                                />
                                {job.check_mode && (
                                    <Chip
                                        size="small"
                                        label={t('configFleet.checkMode', 'Dry run')}
                                    />
                                )}
                                <Button size="small" onClick={() => openDetail(job)}>
                                    {t('configFleet.hosts', 'Per-host results')}
                                </Button>
                                {canCancel &&
                                    (job.status === 'running' || job.status === 'pending') && (
                                        <Button
                                            size="small"
                                            color="warning"
                                            onClick={() => stop(job)}
                                        >
                                            {t('configFleet.cancel', 'Cancel')}
                                        </Button>
                                    )}
                            </Stack>

                            <LinearProgress
                                variant="determinate"
                                value={
                                    job.total_targets
                                        ? (doneCount(job) / job.total_targets) * 100
                                        : 100
                                }
                                sx={{ my: 1 }}
                            />
                            {/* Counts, not just a bar: "3,997 of 4,000, 3 failed"
                                is the sentence an operator needs, and a bar at
                                99.9% looks identical to one at 100%. */}
                            <Typography variant="body2" color="text.secondary">
                                {t(
                                    'configFleet.progress',
                                    '{{done}} of {{total}} — {{ok}} succeeded, {{failed}} failed, {{skipped}} skipped',
                                    {
                                        done: doneCount(job),
                                        total: job.total_targets,
                                        ok: job.succeeded_count,
                                        failed: job.failed_count,
                                        skipped: job.skipped_count,
                                    },
                                )}
                            </Typography>
                            {job.detail && (
                                <Typography variant="caption" color="text.secondary">
                                    {job.detail}
                                </Typography>
                            )}
                        </Box>
                    ))}
                </Stack>
            )}

            <Dialog
                open={Boolean(detail)}
                onClose={() => setDetail(null)}
                maxWidth="md"
                fullWidth
            >
                <DialogTitle>
                    {t('configFleet.hostsIn', 'Per-host results for {{name}}', {
                        name: detail?.template_name || detail?.profile_name || '',
                    })}
                </DialogTitle>
                <DialogContent>
                    <Stack spacing={1} sx={{ mt: 1 }}>
                        {targets.map((target) => (
                            <Stack
                                key={target.id}
                                direction="row"
                                spacing={2}
                                alignItems="center"
                            >
                                <Chip
                                    size="small"
                                    color={TARGET_COLOR[target.status] || 'default'}
                                    label={target.status}
                                />
                                <Typography variant="body2" sx={{ flexGrow: 1 }}>
                                    {target.host_fqdn || target.host_id}
                                </Typography>
                                {target.finished_at && (
                                    <Typography variant="caption" color="text.secondary">
                                        {formatUTCTimestamp(target.finished_at)}
                                    </Typography>
                                )}
                                {target.detail && (
                                    <Typography variant="caption" color="text.secondary">
                                        {target.detail}
                                    </Typography>
                                )}
                            </Stack>
                        ))}
                        {targets.length === 0 && (
                            <Typography variant="body2" color="text.secondary">
                                {t('configFleet.noTargets', 'No hosts to show.')}
                            </Typography>
                        )}
                    </Stack>
                </DialogContent>
                <DialogActions>
                    <Button onClick={() => setDetail(null)}>
                        {t('common.close', 'Close')}
                    </Button>
                </DialogActions>
            </Dialog>
        </Box>
    );
};

export default ConfigJobsPanel;
