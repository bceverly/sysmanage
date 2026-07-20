// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

import React from 'react';
import { useTranslation } from 'react-i18next';
import { Box, Typography } from '@mui/material';
import OpenBAOStatusCard from '../OpenBAOStatusCard';
import GrafanaIntegrationCard from '../GrafanaIntegrationCard';
import GraylogIntegrationCard from '../GraylogIntegrationCard';
import OpenTelemetryStatusCard from '../OpenTelemetryStatusCard';
import PrometheusStatusCard from '../PrometheusStatusCard';

const IntegrationsTab: React.FC = () => {
  const { t } = useTranslation();

  return (
    <Box>
      <Typography variant="h5" sx={{ mb: 2 }}>
        {t('integrations.title', 'Integrations')}
      </Typography>

      <Typography variant="body1" sx={{ mb: 3 }}>
        {t('integrations.description', 'Configure external service integrations and settings.')}
      </Typography>

      {/* Email configuration now lives on the Configuration tab (Phase 13.1.H). */}

      <Box sx={{ mb: 3 }}>
        <OpenBAOStatusCard />
      </Box>

      <Box sx={{ mb: 3 }}>
        <GrafanaIntegrationCard />
      </Box>

      <Box sx={{ mb: 3 }}>
        <GraylogIntegrationCard />
      </Box>

      <Box sx={{ mb: 3 }}>
        <OpenTelemetryStatusCard />
      </Box>

      <Box>
        <PrometheusStatusCard />
      </Box>
    </Box>
  );
};

export default IntegrationsTab;
