// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

// A host's pending updates under the policy it follows (ROADMAP 26.3,
// Enterprise): each one says when it becomes eligible and why -- shown,
// not guessed.  "critical CVE-2026-1234: eligible now"; "regular: eligible
// on Nov 9"; or why it is never applied automatically.

import React from 'react';
import {
  Alert,
  Box,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  Typography,
} from '@mui/material';
import type { TFunction } from 'i18next';
import { useTranslation } from 'react-i18next';
import type { HostAutoUpdates, PendingUpdate } from '../../Services/autoUpdates';
import { formatUTCTimestamp } from '../../utils/dateUtils';
import { packageReasonLabel } from './autoUpdateLabels';

export function eligibilityLabel(t: TFunction, row: PendingUpdate): string {
  const critical = row.kind === 'critical';
  const fix = row.fix_id ?? '';
  if (!row.reason) {
    return critical
      ? t('autoUpdates.eligible.criticalNow', 'critical {{fix}}: eligible now', { fix })
      : t('autoUpdates.eligible.now', 'eligible now');
  }
  if (row.reason === 'waiting_period') {
    const when = formatUTCTimestamp(row.eligible_at ?? '', '--');
    return critical
      ? t('autoUpdates.eligible.criticalOn', 'critical {{fix}}: eligible on {{when}}', { fix, when })
      : t('autoUpdates.eligible.regularOn', 'regular: eligible on {{when}}', { when });
  }
  return packageReasonLabel(t, row.reason);
}

interface Props {
  pending: NonNullable<HostAutoUpdates['pending']>;
  waits: boolean;
}

const PendingEligibility: React.FC<Props> = ({ pending, waits }) => {
  const { t } = useTranslation();
  const noData = !pending.sources.vulnerability && !pending.sources.advisory;
  return (
    <Box sx={{ mb: 2 }}>
      <Typography variant="subtitle2" sx={{ mb: 1 }}>
        {t('autoUpdates.pendingTitle', 'Pending updates under this policy')}
      </Typography>
      {waits && noData && (
        <Alert severity="info" sx={{ mb: 1 }}>
          {t(
            'autoUpdates.noCveData',
            'This host has no vulnerability scan or vendor advisories, so every patch on it waits the regular count.',
          )}
        </Alert>
      )}
      {pending.updates.length === 0 ? (
        <Typography variant="body2" color="text.secondary">
          {t('autoUpdates.noPending', 'No pending updates.')}
        </Typography>
      ) : (
        <Table size="small">
          <TableHead>
            <TableRow>
              <TableCell>{t('autoUpdates.package', 'Package')}</TableCell>
              <TableCell>{t('autoUpdates.eligibility', 'Applied automatically')}</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {pending.updates.map((row) => (
              <TableRow key={`${row.package_manager}-${row.package_name}`}>
                <TableCell>
                  {row.package_name}
                  {row.available_version ? ` ${row.available_version}` : ''}
                </TableCell>
                <TableCell>{eligibilityLabel(t, row)}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}
    </Box>
  );
};

export default PendingEligibility;
