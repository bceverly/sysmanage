// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

import React, { useCallback, useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import Alert from '@mui/material/Alert';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Chip from '@mui/material/Chip';
import LinearProgress from '@mui/material/LinearProgress';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';

import {
    LiveQuery,
    cancelLiveQuery,
    createLiveQuery,
    getLiveQuery,
} from '../Services/queryPackService';

/**
 * Ad-hoc fleet-wide live query (Phase 21.1 S5).
 *
 * The panel polls while a query is running, because results arrive per host
 * as each one answers -- a single response at the end would make a bounded
 * fan-out look identical to a hung one.
 */

/** How often to re-read a running query. */
const POLL_MS = 2000;

/**
 * Human labels with REAL fallbacks, not the raw status string.
 *
 * `t(key, status)` would fall back to the bare value -- so a missing catalog
 * key shows an operator `waiting` instead of "Waiting", untranslated and
 * easily misread. Same fix as the run-status chip on the packs page.
 */
const LIVE_STATUS_LABEL: Record<string, string> = {
    pending: 'Pending',
    running: 'Running',
    completed: 'Completed',
    canceled: 'Cancelled',
};

const TARGET_STATUS_LABEL: Record<string, string> = {
    // "Waiting" is the bound made visible: this host has not been asked yet.
    waiting: 'Waiting',
    pending: 'Asked',
    success: 'Answered',
    partial: 'Partially answered',
    failed: 'Failed',
};

/** Per-host outcome colors. `not covered` is NOT an error -- see below. */
const TARGET_COLOR: Record<string, 'success' | 'warning' | 'error' | 'default'> = {
    waiting: 'default',
    pending: 'default',
    success: 'success',
    partial: 'warning',
    failed: 'error',
};

const messageFrom = (err: unknown, fallback: string): string => {
    const detail = (err as { response?: { data?: { detail?: unknown } } })?.response
        ?.data?.detail;
    return typeof detail === 'string' && detail ? detail : fallback;
};

interface Props {
    /** Hosts to target. The caller owns selection. */
    hostIds: string[];
}

const LiveQueryPanel: React.FC<Props> = ({ hostIds }) => {
    const { t } = useTranslation();
    const [sql, setSql] = useState('');
    const [tables, setTables] = useState('');
    const [live, setLive] = useState<LiveQuery | null>(null);
    const [error, setError] = useState<string | null>(null);
    const [running, setRunning] = useState(false);
    const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

    const stopPolling = useCallback(() => {
        if (timer.current) {
            clearTimeout(timer.current);
            timer.current = null;
        }
    }, []);

    // Stop the timer when the panel goes away, or a query that finished after
    // unmount keeps a handle alive and React warns about setting state on an
    // unmounted component.
    useEffect(() => stopPolling, [stopPolling]);

    const poll = useCallback(
        async (id: string) => {
            try {
                const next = await getLiveQuery(id);
                setLive(next);
                if (next.status === 'running' || next.status === 'pending') {
                    timer.current = setTimeout(() => poll(id), POLL_MS);
                } else {
                    setRunning(false);
                }
            } catch (err) {
                setError(messageFrom(err, t('queryPacks.liveFailed', 'Could not read the live query')));
                setRunning(false);
            }
        },
        [t],
    );

    const run = async () => {
        setError(null);
        setRunning(true);
        try {
            const created = await createLiveQuery({
                sql,
                host_ids: hostIds,
                required_tables: tables
                    .split(',')
                    .map((x) => x.trim())
                    .filter(Boolean),
            });
            setLive(created);
            poll(created.id);
        } catch (err) {
            setError(messageFrom(err, t('queryPacks.liveFailed', 'Could not run the query')));
            setRunning(false);
        }
    };

    const stop = async () => {
        if (!live) return;
        try {
            await cancelLiveQuery(live.id);
            stopPolling();
            setRunning(false);
            setLive(await getLiveQuery(live.id));
        } catch (err) {
            setError(messageFrom(err, t('queryPacks.cancelFailed', 'Could not cancel')));
        }
    };

    const answered = live ? live.completed_count : 0;
    const total = live ? live.total_targets : 0;

    return (
        <Box sx={{ mt: 2 }}>
            <Typography variant="h6">
                {t('queryPacks.liveTitle', 'Live Query')}
            </Typography>
            <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
                {t(
                    'queryPacks.liveIntro',
                    'Run one query across the selected hosts now. Dispatch is bounded, so hosts are asked in waves rather than all at once.',
                )}
            </Typography>

            {error && (
                <Alert severity="error" sx={{ mb: 2 }}>
                    {error}
                </Alert>
            )}

            <TextField
                fullWidth
                multiline
                minRows={3}
                label={t('queryPacks.sql', 'SQL')}
                value={sql}
                onChange={(e) => setSql(e.target.value)}
            />
            <TextField
                fullWidth
                margin="dense"
                label={t('queryPacks.requiredTables', 'Fact tables used')}
                value={tables}
                onChange={(e) => setTables(e.target.value)}
            />

            <Stack direction="row" spacing={1} sx={{ mt: 2 }}>
                <Button
                    variant="contained"
                    onClick={run}
                    disabled={running || !sql.trim() || hostIds.length === 0}
                >
                    {t('queryPacks.runNow', 'Run Now')}
                </Button>
                <Button onClick={stop} disabled={!running}>
                    {t('queryPacks.cancel', 'Cancel')}
                </Button>
            </Stack>

            {live && (
                <Box sx={{ mt: 2 }}>
                    <Stack direction="row" spacing={1} alignItems="center">
                        <Chip
                            size="small"
                            label={t(
                                `queryPacks.liveStatus.${live.status}`,
                                LIVE_STATUS_LABEL[live.status] ?? live.status,
                            )}
                        />
                        <Typography variant="body2">
                            {t(
                                'queryPacks.answeredOf',
                                'Hosts answered: {{answered}} / {{total}}',
                                { answered, total },
                            )}
                        </Typography>
                        {/* Shown separately from failures on purpose: a host
                            that does not serve the tables has not failed. */}
                        {live.not_covered_count > 0 && (
                            <Chip
                                size="small"
                                color="warning"
                                label={t(
                                    'queryPacks.notCoveredCount',
                                    '{{count}} not covered',
                                    { count: live.not_covered_count },
                                )}
                            />
                        )}
                        {live.failed_count > 0 && (
                            <Chip
                                size="small"
                                color="error"
                                label={t('queryPacks.failedCount', '{{count}} failed', {
                                    count: live.failed_count,
                                })}
                            />
                        )}
                    </Stack>
                    <LinearProgress
                        variant="determinate"
                        value={total > 0 ? (answered / total) * 100 : 0}
                        sx={{ mt: 1 }}
                    />

                    {(live.targets ?? []).map((target) => (
                        <Box key={target.run_id} sx={{ mt: 1 }} data-testid="live-target">
                            <Stack direction="row" spacing={1} alignItems="center">
                                <Chip
                                    size="small"
                                    color={TARGET_COLOR[target.status] ?? 'default'}
                                    label={t(
                                        `queryPacks.targetStatus.${target.status}`,
                                        TARGET_STATUS_LABEL[target.status] ??
                                            target.status,
                                    )}
                                />
                                <Typography variant="body2">{target.host_id}</Typography>
                            </Stack>
                            {target.rows.map((row, i) => (
                                <Typography
                                    key={i}
                                    variant="caption"
                                    component="div"
                                    sx={{ ml: 2, fontFamily: 'monospace' }}
                                >
                                    {row.status === 'ok' && row.columns
                                        ? JSON.stringify(row.columns)
                                        : t(
                                              'queryPacks.rowNotCovered',
                                              'not covered: {{reason}}',
                                              { reason: row.reason ?? row.status },
                                          )}
                                </Typography>
                            ))}
                        </Box>
                    ))}
                </Box>
            )}
        </Box>
    );
};

export default LiveQueryPanel;
