// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

// The advisor's grade for the fleet or one host.  A score is WITHHELD from
// anything that could not be assessed, and this card shows the withholding
// rather than hiding it: "Not assessed" is its own state (never 0, never
// green), a floor-only score says so, and the fleet's unassessed hosts are
// counted right beside its average.

import React from 'react';
import { Alert, Box, Card, CardContent, Chip, Stack, Typography } from '@mui/material';
import { useTranslation } from 'react-i18next';
import type { AdvisorFleetScore, AdvisorHostScore } from '../../Services/advisorService';
import { levelColor, levelLabel } from './advisorLabels';

interface Props {
    fleet?: AdvisorFleetScore;
    host?: AdvisorHostScore;
}

const ScoreLine: React.FC<{ score: number | null; level: AdvisorHostScore['level'] }> = ({ score, level }) => {
    const { t } = useTranslation();
    return (
        <Stack direction="row" spacing={2} alignItems="center">
            <Typography variant="h4" component="span">
                {score === null ? '--' : Math.round(score)}
            </Typography>
            <Chip label={levelLabel(t, level)} color={levelColor(level)} />
        </Stack>
    );
};

const FleetDetail: React.FC<{ fleet: AdvisorFleetScore }> = ({ fleet }) => {
    const { t } = useTranslation();
    return (
        <>
            <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>
                {t('advisor.summary.fleetAssessed', '{{assessed}} of {{total}} hosts assessed', {
                    assessed: fleet.assessed_hosts,
                    total: fleet.total_hosts,
                })}
            </Typography>
            {fleet.unknown_hosts > 0 && (
                <Alert severity="warning" sx={{ mt: 1 }}>
                    {t(
                        'advisor.summary.fleetUnknown',
                        '{{count}} hosts could not be assessed and are not in this score. They are not clean -- they are unmeasured.',
                        { count: fleet.unknown_hosts },
                    )}
                </Alert>
            )}
            {fleet.incomplete_hosts > 0 && (
                <Alert severity="info" sx={{ mt: 1 }}>
                    {t(
                        'advisor.summary.fleetIncomplete',
                        '{{count}} hosts were only partly assessed; their scores are a minimum.',
                        { count: fleet.incomplete_hosts },
                    )}
                </Alert>
            )}
        </>
    );
};

const HostDetail: React.FC<{ host: AdvisorHostScore }> = ({ host }) => {
    const { t } = useTranslation();
    if (host.score === null) {
        return (
            <Alert severity="warning" sx={{ mt: 1 }}>
                {t(
                    'advisor.summary.hostUnknown',
                    'This host could not be fully assessed, so it has no grade. See the not-assessable list below for what is missing.',
                )}
            </Alert>
        );
    }
    if (!host.complete) {
        return (
            <Alert severity="info" sx={{ mt: 1 }}>
                {t(
                    'advisor.summary.hostIncomplete',
                    'Some rules could not be assessed on this host; this score is a minimum.',
                )}
            </Alert>
        );
    }
    return null;
};

const AdvisorScoreSummary: React.FC<Props> = ({ fleet, host }) => {
    const { t } = useTranslation();
    const score = fleet ? fleet.average_score : host?.score ?? null;
    const level = fleet ? fleet.level : host?.level ?? 'UNKNOWN';
    return (
        <Card variant="outlined">
            <CardContent>
                <Box sx={{ mb: 1 }}>
                    <Typography variant="overline">
                        {fleet
                            ? t('advisor.summary.fleetTitle', 'Fleet risk')
                            : t('advisor.summary.hostTitle', 'Host risk')}
                    </Typography>
                </Box>
                <ScoreLine score={score} level={level} />
                {fleet && <FleetDetail fleet={fleet} />}
                {host && <HostDetail host={host} />}
            </CardContent>
        </Card>
    );
};

export default AdvisorScoreSummary;
