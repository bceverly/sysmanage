// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

// Every host offset is measured against the SERVER's clock, so the server's
// own standing against its reference is shown first (Phase 23.3).

import React from 'react';
import { Alert } from '@mui/material';
import { useTranslation } from 'react-i18next';
import type { ServerClock } from '../../Services/timeSync';
import { serverClockSeverity, serverClockText } from './timeSyncLabels';

const ServerClockBanner: React.FC<{ server: ServerClock }> = ({ server }) => {
    const { t } = useTranslation();
    return (
        <Alert severity={serverClockSeverity(server)} sx={{ mb: 2 }} data-testid="server-clock">
            {serverClockText(t, server)}
        </Alert>
    );
};

export default ServerClockBanner;
