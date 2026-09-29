// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

// What the agents could NOT see (Phase 21.6 S3).  Shown on every visit, never
// collapsed away: a list of unmanaged devices without its limits reads as
// "these are all of them", which this feature must never claim.

import React from 'react';
import { Alert, Stack, Typography } from '@mui/material';
import { useTranslation } from 'react-i18next';
import type { DiscoverySummary } from '../../Services/assetDiscoveryService';
import { methodLabel, unavailableLabel } from './discoveryLabels';

const ObserverLimits: React.FC<{ summary: DiscoverySummary }> = ({ summary }) => {
    const { t } = useTranslation();
    const limited = summary.observers.filter(o => o.stale || Object.keys(o.unavailable).length > 0);
    if (limited.length === 0) return null;
    return (
        <Alert severity="warning">
            <Typography variant="body2" sx={{ mb: 0.5 }}>
                {t('assetDiscovery.blindSpots.agentsLimited', 'Some agents cannot see everything on their networks:')}
            </Typography>
            {limited.map(o => (
                <Typography key={o.host_id} variant="body2">
                    {o.fqdn}
                    {': '}
                    {[
                        ...(o.stale ? [t('assetDiscovery.blindSpots.stale', 'has stopped reporting')] : []),
                        ...Object.entries(o.unavailable).map(
                            ([method, reason]) => `${methodLabel(t, method)} (${unavailableLabel(t, reason)})`,
                        ),
                    ].join('; ')}
                </Typography>
            ))}
        </Alert>
    );
};

const BlindSpots: React.FC<{ summary: DiscoverySummary }> = ({ summary }) => {
    const { t } = useTranslation();
    const { coverage } = summary;
    const cannotTakePart = coverage.not_equipped + coverage.unknown;
    return (
        <Stack spacing={1} sx={{ mb: 2 }}>
            {!summary.policy.enabled && (
                <Alert severity="info">
                    {t('assetDiscovery.blindSpots.off', 'Discovery is turned off: agents are not listening, so nothing new will be found.')}
                </Alert>
            )}
            {summary.blind_spots.silent_devices_unseen && (
                <Alert severity="info">
                    {t('assetDiscovery.blindSpots.silent', 'Agents only listen. A device that sends nothing is not seen, so this list may be incomplete.')}
                    {(summary.blind_spots.unswept_networks ?? []).length > 0 && (
                        <Typography variant="body2" sx={{ mt: 0.5 }}>
                            {t('assetDiscovery.blindSpots.unswept', 'Not swept in the last 7 days: {{networks}}', { networks: (summary.blind_spots.unswept_networks ?? []).join(', ') })}
                        </Typography>
                    )}
                </Alert>
            )}
            <ObserverLimits summary={summary} />
            {cannotTakePart > 0 && (
                <Alert severity="info">
                    {t('assetDiscovery.blindSpots.notEquipped', '{{count}} hosts run an agent that cannot take part in discovery; their networks are not covered.', { count: cannotTakePart })}
                </Alert>
            )}
        </Stack>
    );
};

export default BlindSpots;
