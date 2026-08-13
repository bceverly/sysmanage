// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

import React from 'react';
import { Box, LinearProgress, Typography } from '@mui/material';
import { useTranslation } from 'react-i18next';
import { formatRelative } from '../SiteDetailHelpers';
import { ChildHost } from './hostDetailTypes';

/**
 * How long a provision may go without a step report before the age is called
 * out rather than just stated.
 *
 * Deliberately generous.  Individual steps really are long: remastering
 * Windows install media extracts and re-authors a ~5 GB ISO, and Setup itself
 * runs unattended for 25-45 minutes between reports.  A tighter threshold would
 * cry wolf on every healthy Windows build, and a warning that is usually wrong
 * is worse than none — operators stop reading it.
 */
export const STALL_WARNING_MINUTES = 20;

interface ChildHostProgressProps {
    child: ChildHost;
}

/**
 * Provision progress for a child host that is still being created.
 *
 * Renders nothing unless the child is mid-provision.  A Windows Server guest
 * takes 25-45 minutes, during which the only prior signal was a spinner that
 * looked identical at minute 2 and minute 40 — "no news" could mean working or
 * wedged and the UI could not tell them apart.
 *
 * Two things fix that, and they are separate on purpose:
 *   - the step counter shows how far along the plan is;
 *   - the timestamp shows whether anything is still HAPPENING.
 * A provision can be at step 7 of 9 and dead; only the second one says so.
 */
const ChildHostProgress: React.FC<ChildHostProgressProps> = ({ child }) => {
    const { t, i18n } = useTranslation();

    if (child.status !== 'creating') {
        return null;
    }

    const step = child.installation_step_number;
    const total = child.installation_total_steps;
    // Determinate only when both numbers are real and sane.  An older agent
    // reports neither, and a bar that jumps to 100% because total was 0 is
    // worse than an honest indeterminate one.
    const determinate =
        typeof step === 'number' && typeof total === 'number' && total > 0 && step <= total;

    const lastUpdate = formatRelative(child.installation_step_at, i18n.language);
    const ageMinutes = child.installation_step_at
        ? (Date.now() - new Date(child.installation_step_at).getTime()) / 60000
        : null;
    const stalled = ageMinutes !== null && ageMinutes >= STALL_WARNING_MINUTES;

    return (
        <Box sx={{ width: '100%', mt: 0.5 }}>
            <LinearProgress
                variant={determinate ? 'determinate' : 'indeterminate'}
                // No non-null assertions: `determinate` is an aliased condition
                // built from typeof guards, so TS narrows step/total to number here.
                value={determinate ? (step / total) * 100 : undefined}
                sx={{ height: 4, borderRadius: 2 }}
            />
            {child.installation_step && (
                <Typography variant="caption" color="textSecondary" sx={{ display: 'block', mt: 0.5 }}>
                    {determinate
                        ? t('hostDetail.childHostProgressStep', '{{step}}/{{total}} · {{description}}', {
                              step,
                              total,
                              description: child.installation_step,
                          })
                        : child.installation_step}
                </Typography>
            )}
            {lastUpdate && (
                <Typography
                    variant="caption"
                    color={stalled ? 'warning.main' : 'textSecondary'}
                    sx={{ display: 'block' }}
                >
                    {stalled
                        ? t(
                              'hostDetail.childHostProgressStalled',
                              'No update {{when}} — the current step may be long-running, or the provision may have stalled.',
                              { when: lastUpdate },
                          )
                        : t('hostDetail.childHostProgressUpdated', 'Updated {{when}}', {
                              when: lastUpdate,
                          })}
                </Typography>
            )}
        </Box>
    );
};

export default ChildHostProgress;
