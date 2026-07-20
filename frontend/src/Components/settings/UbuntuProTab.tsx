// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

import React from 'react';
import { useTranslation } from 'react-i18next';
import { Box, Typography } from '@mui/material';
import UbuntuProSettings from '../UbuntuProSettings';

const UbuntuProTab: React.FC = () => {
  const { t } = useTranslation();

  return (
    <Box>
      <Typography variant="h5" sx={{ mb: 2 }}>
        {t('ubuntuPro.title', 'Ubuntu Pro')}
      </Typography>

      <Typography variant="body1" sx={{ mb: 3 }}>
        {t('ubuntuPro.description', 'Configure Ubuntu Pro subscription management and master keys for bulk enrollment.')}
      </Typography>

      <UbuntuProSettings />
    </Box>
  );
};

export default UbuntuProTab;
