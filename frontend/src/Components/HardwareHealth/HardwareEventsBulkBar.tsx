// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

// Bulk acknowledge / resolve for the hardware events list (2026-10-19).  A
// laptop serving with its lid closed flapped its CPU sensor dozens of times a
// night, and each event had to be resolved by hand ("managing the bajillion
// resolves is exhausting").  Pick events -- or every open one -- and act once.

import React, { useEffect, useMemo, useState } from 'react';
import { Alert, Box, Button, CircularProgress, Link, Stack, Typography } from '@mui/material';
import { useTranslation } from 'react-i18next';
import { useActionInFlight } from '../../hooks/useActionInFlight';
import { bulkChangeHardwareEvents } from '../../Services/hardwareHealth';
import type { BulkScope, HardwareEvent } from '../../Services/hardwareHealth';

type Action = 'acknowledge' | 'resolve';

export interface EventSelection {
    selected: Set<string>;
    /** Every open event, not just the listed ones ("Select all N"). */
    allMatching: boolean;
    pageSelected: boolean;
    somePageSelected: boolean;
    selectable: (event: HardwareEvent) => boolean;
    toggle: (id: string) => void;
    togglePage: () => void;
    selectAllMatching: () => void;
    clear: () => void;
}

/** Which listed events are picked.  Resolved events cannot be. */
export const useEventSelection = (events: HardwareEvent[]): EventSelection => {
    const [selected, setSelected] = useState<Set<string>>(new Set());
    const [allMatching, setAllMatching] = useState(false);
    const openIds = useMemo(() => events.filter(e => !e.resolved_at).map(e => e.id), [events]);

    // A refreshed list drops what is no longer listed (just resolved, say).
    useEffect(() => {
        const listed = new Set(openIds);
        setSelected(prev => {
            const kept = Array.from(prev).filter(id => listed.has(id));
            return kept.length === prev.size ? prev : new Set(kept); // unchanged: no re-render
        });
        setAllMatching(false);
    }, [openIds]);

    const pageSelected = openIds.length > 0 && openIds.every(id => selected.has(id));
    return {
        selected,
        allMatching,
        pageSelected,
        somePageSelected: selected.size > 0 && !pageSelected,
        selectable: event => !event.resolved_at,
        toggle: id => {
            setAllMatching(false);
            setSelected(prev => {
                const next = new Set(prev);
                if (next.has(id)) next.delete(id);
                else next.add(id);
                return next;
            });
        },
        togglePage: () => {
            setAllMatching(false);
            setSelected(pageSelected ? new Set() : new Set(openIds));
        },
        selectAllMatching: () => {
            setSelected(new Set(openIds));
            setAllMatching(true);
        },
        clear: () => {
            setSelected(new Set());
            setAllMatching(false);
        },
    };
};

interface Outcome {
    severity: 'success' | 'error';
    changed?: number;
    skipped?: number;
}

const HardwareEventsBulkBar: React.FC<{
    selection: EventSelection;
    /** Open events in all, beyond the listed page. */
    total: number;
    /** Scope "all open" to one host (the host card). */
    hostId?: string;
    onChanged?: () => void;
}> = ({ selection, total, hostId, onChanged }) => {
    const { t } = useTranslation();
    const { busy, run } = useActionInFlight();
    const [outcome, setOutcome] = useState<Outcome | null>(null);
    const count = selection.selected.size;

    const act = (action: Action) => run(action, async () => {
        const scope: BulkScope = selection.allMatching
            ? { allOpen: true, hostId }
            : { eventIds: Array.from(selection.selected) };
        try {
            const result = await bulkChangeHardwareEvents(action, scope);
            setOutcome({ severity: 'success', ...result });
            selection.clear();
            onChanged?.();
        } catch {
            setOutcome({ severity: 'error' });
        }
    });

    const busyIcon = <CircularProgress size={16} color="inherit" />;
    const offerAll = selection.pageSelected && !selection.allMatching && total > count;
    return (
        <Box sx={{ mb: 1 }}>
            {outcome && (
                <Alert severity={outcome.severity} onClose={() => setOutcome(null)} sx={{ mb: 1 }}>
                    {outcome.severity === 'error'
                        ? t('hardwareHealth.events.bulkError', 'The selected events could not be changed.')
                        : t('hardwareHealth.events.bulkChanged', 'Events changed: {{n}}', { n: outcome.changed })}
                    {outcome.severity === 'success' && (outcome.skipped ?? 0) > 0 && (
                        <>
                            {' '}
                            {t('hardwareHealth.events.bulkSkipped', 'Already done or not found: {{n}}', {
                                n: outcome.skipped,
                            })}
                        </>
                    )}
                </Alert>
            )}
            {count > 0 && (
                <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
                    <Typography variant="body2">
                        {selection.allMatching
                            ? t('hardwareHealth.events.allMatchingSelected', 'All unresolved events are selected ({{n}}).', {
                                  n: total,
                              })
                            : t('hardwareHealth.events.selectedCount', 'Selected: {{n}}', { n: count })}
                    </Typography>
                    {offerAll && (
                        <Link component="button" variant="body2" onClick={selection.selectAllMatching}>
                            {t('hardwareHealth.events.selectAllMatching', 'Select all {{n}} unresolved events', {
                                n: total,
                            })}
                        </Link>
                    )}
                    <Button
                        size="small"
                        variant="outlined"
                        disabled={busy !== null}
                        startIcon={busy === 'acknowledge' ? busyIcon : undefined}
                        onClick={() => void act('acknowledge')}
                    >
                        {t('hardwareHealth.events.acknowledgeSelected', 'Acknowledge selected')}
                    </Button>
                    <Button
                        size="small"
                        variant="contained"
                        disabled={busy !== null}
                        startIcon={busy === 'resolve' ? busyIcon : undefined}
                        onClick={() => void act('resolve')}
                    >
                        {t('hardwareHealth.events.resolveSelected', 'Resolve selected')}
                    </Button>
                    <Button size="small" disabled={busy !== null} onClick={selection.clear}>
                        {t('hardwareHealth.events.clearSelection', 'Clear selection')}
                    </Button>
                </Stack>
            )}
        </Box>
    );
};

export default HardwareEventsBulkBar;
