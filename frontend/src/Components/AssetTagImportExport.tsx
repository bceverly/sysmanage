// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

// Asset tag CSV import / export and held tags (Phase 23.2 S5).  Choosing a
// file shows the server's dry run -- every row as will-assign / unchanged /
// held / refused -- before anything is written.  Tags for machines that have
// not reported in yet are HELD and applied when they do.

import React from 'react';
import type { TFunction } from 'i18next';
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  CardHeader,
  Chip,
  CircularProgress,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Typography,
} from '@mui/material';
import { useTranslation } from 'react-i18next';
import { HeldTag, ImportResult, ImportRow, ImportStatus } from '../Services/machines';
import { tagReasonText } from './HostDetail/HostMachineCard';
import { ImportNotice, useAssetTagImport, writableCount } from '../hooks/useAssetTagImport';

/** The dry-run table shows this many rows; the summary counts them all. */
export const MAX_SHOWN_ROWS = 500;

type ChipColor = 'success' | 'default' | 'info' | 'error' | 'warning';

const STATUS_COLOR: Record<ImportStatus, ChipColor> = {
  assign: 'success',
  unchanged: 'default',
  hold: 'info',
  fails_scheme: 'error',
  duplicate: 'error',
  ambiguous: 'warning',
  invalid: 'error',
  skipped: 'default',
};

const STATUS_ORDER: ImportStatus[] = [
  'assign', 'hold', 'unchanged', 'skipped', 'fails_scheme', 'duplicate', 'ambiguous', 'invalid',
];

export const statusText = (t: TFunction, status: ImportStatus): string => {
  switch (status) {
    case 'assign': return t('assetTags.import.status.assign', 'Will assign');
    case 'unchanged': return t('assetTags.import.status.unchanged', 'Unchanged');
    case 'hold': return t('assetTags.import.status.hold', 'Will wait for the machine');
    case 'fails_scheme': return t('assetTags.import.status.failsScheme', 'Fails the scheme');
    case 'duplicate': return t('assetTags.import.status.duplicate', 'Duplicate');
    case 'ambiguous': return t('assetTags.import.status.ambiguous', 'Ambiguous');
    case 'skipped': return t('assetTags.import.status.skipped', 'Skipped');
    default: return t('assetTags.import.status.invalid', 'Invalid');
  }
};

/** A row-level refusal the server sent as a code, or null if it is not one. */
const rowReasonText = (t: TFunction, reason: string): string | null => {
  switch (reason) {
    case 'tag_in_use': return t('assetTags.import.reason.tagInUse', 'Another machine already has this tag.');
    case 'tag_held': return t('assetTags.import.reason.tagHeld', 'This tag is already waiting for another machine.');
    case 'duplicate_in_file': return t('assetTags.import.reason.duplicateInFile', 'An earlier row in the file uses this tag.');
    case 'identifier_repeated': return t('assetTags.import.reason.identifierRepeated', 'An earlier row in the file names this machine.');
    case 'bad_uuid': return t('assetTags.import.reason.badUuid', 'The system UUID is not a valid UUID.');
    case 'placeholder': return t('assetTags.import.reason.placeholder', 'A vendor placeholder identifies no machine.');
    case 'no_identifier': return t('assetTags.import.reason.noIdentifier', 'The row has no system UUID or serial number.');
    default: return null;
  }
};

/** Why a row is not written, or what it changes, in the user's language. */
export const rowDetail = (t: TFunction, row: ImportRow): string => {
  if (row.status === 'ambiguous') {
    return t('assetTags.import.reason.ambiguous', 'More than one machine reports this UUID. Add the serial number to choose one.');
  }
  if (row.reason) return rowReasonText(t, row.reason) ?? tagReasonText(t, row.reason);
  if (row.status === 'skipped') return t('assetTags.import.reason.noTag', 'No tag in this row; an import never clears a tag.');
  if (row.previous && row.status !== 'unchanged') {
    return t('assetTags.import.replaces', 'Replaces {{previous}}', { previous: row.previous });
  }
  if (row.discovered_mac) {
    return t('assetTags.import.discovered', 'Seen by bare-metal discovery ({{mac}})', { mac: row.discovered_mac });
  }
  return '';
};

const identifierOf = (row: ImportRow): string =>
  [row.system_uuid, row.system_serial].filter(Boolean).join(' / ');

const monoSx = { fontFamily: 'monospace' };

const PreviewTable: React.FC<{ result: ImportResult }> = ({ result }) => {
  const { t } = useTranslation();
  const shown = result.rows.slice(0, MAX_SHOWN_ROWS);
  return (
    <Box data-testid="asset-tag-import-preview">
      <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap sx={{ mb: 1 }}>
        {STATUS_ORDER.filter(s => result.summary[s]).map(s => (
          <Chip key={s} size="small" color={STATUS_COLOR[s]} label={`${statusText(t, s)}: ${result.summary[s]}`} />
        ))}
      </Stack>
      {result.rows.length > MAX_SHOWN_ROWS && (
        <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
          {t('assetTags.import.truncated', 'Showing the first {{shown}} of {{total}} rows.', {
            shown: MAX_SHOWN_ROWS,
            total: result.rows.length,
          })}
        </Typography>
      )}
      <TableContainer sx={{ maxHeight: 420 }}>
        <Table size="small" stickyHeader>
          <TableHead>
            <TableRow>
              <TableCell>{t('assetTags.import.col.line', 'Line')}</TableCell>
              <TableCell>{t('assetTags.import.col.identifier', 'System UUID / serial')}</TableCell>
              <TableCell>{t('assetTags.import.col.tag', 'Asset tag')}</TableCell>
              <TableCell>{t('assetTags.import.col.outcome', 'Outcome')}</TableCell>
              <TableCell>{t('assetTags.import.col.hosts', 'Hosts')}</TableCell>
              <TableCell>{t('assetTags.import.col.detail', 'Detail')}</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {shown.map(row => (
              <TableRow key={row.line}>
                <TableCell>{row.line}</TableCell>
                <TableCell sx={monoSx}>{identifierOf(row)}</TableCell>
                <TableCell sx={monoSx}>{row.asset_tag}</TableCell>
                <TableCell>
                  <Chip size="small" variant="outlined" color={STATUS_COLOR[row.status]} label={statusText(t, row.status)} />
                </TableCell>
                <TableCell>{row.hosts.join(', ')}</TableCell>
                <TableCell>{rowDetail(t, row)}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </TableContainer>
    </Box>
  );
};

const fileErrorText = (t: TFunction, code: string | null): string => {
  switch (code) {
    case 'missing_columns': return t('assetTags.import.fileError.missingColumns', 'The file needs an asset_tag column and a system_uuid or system_serial column.');
    case 'file_too_large': return t('assetTags.import.fileError.tooLarge', 'The file is larger than 1 MB.');
    case 'too_many_rows': return t('assetTags.import.fileError.tooManyRows', 'The file has more than 10,000 rows.');
    case 'not_csv': return t('assetTags.import.fileError.notCsv', 'The file is not a readable CSV file.');
    default: return t('assetTags.import.fileError.unreadable', 'The file could not be read.');
  }
};

const noticeAlert = (t: TFunction, notice: ImportNotice): React.ReactNode => {
  if (notice === null) return null;
  if (notice.kind === 'applied') {
    const s = notice.result.summary;
    return (
      <Alert severity="success" sx={{ mb: 2 }}>
        {t('assetTags.import.applied', 'Import applied: {{assigned}} assigned, {{held}} pending.', {
          assigned: s.assign ?? 0,
          held: s.hold ?? 0,
        })}
      </Alert>
    );
  }
  if (notice.kind === 'fileError') {
    return <Alert severity="error" sx={{ mb: 2 }}>{fileErrorText(t, notice.code)}</Alert>;
  }
  return <Alert severity="error" sx={{ mb: 2 }}>{t('assetTags.import.failed', 'The request failed. Try again.')}</Alert>;
};

const HeldTagsPanel: React.FC<{
  held: HeldTag[];
  failed: boolean;
  canManage: boolean;
  onRelease: (id: string) => void;
}> = ({ held, failed, canManage, onRelease }) => {
  const { t } = useTranslation();
  return (
    <Box data-testid="asset-tag-held">
      <Typography variant="subtitle1">{t('assetTags.held.title', 'Pending tags')}</Typography>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
        {t('assetTags.held.explain', 'Tags for machines that have not reported in yet. Each is applied the first time a machine with that UUID or serial number reports in without a tag.')}
      </Typography>
      {failed && <Alert severity="error">{t('assetTags.held.loadFailed', 'Pending tags could not be loaded.')}</Alert>}
      {!failed && held.length === 0 && (
        <Typography variant="body2" color="text.secondary">{t('assetTags.held.none', 'No tags are pending.')}</Typography>
      )}
      {held.length > 0 && (
        <Table size="small">
          <TableHead>
            <TableRow>
              <TableCell>{t('assetTags.import.col.tag', 'Asset tag')}</TableCell>
              <TableCell>{t('assetTags.held.waitingFor', 'Waiting for')}</TableCell>
              <TableCell>{t('assetTags.held.heldBy', 'Added by')}</TableCell>
              {canManage && <TableCell />}
            </TableRow>
          </TableHead>
          <TableBody>
            {held.map(h => (
              <TableRow key={h.id}>
                <TableCell sx={monoSx}>{h.asset_tag}</TableCell>
                <TableCell sx={monoSx}>
                  {h.kind === 'system_uuid'
                    ? t('assetTags.held.byUuid', 'System UUID {{id}}', { id: h.identifier })
                    : t('assetTags.held.bySerial', 'Serial number {{id}}', { id: h.identifier })}
                </TableCell>
                <TableCell>{h.created_by ?? ''}</TableCell>
                {canManage && (
                  <TableCell align="right">
                    <Button size="small" color="error" onClick={() => onRelease(h.id)}>
                      {t('assetTags.held.release', 'Remove')}
                    </Button>
                  </TableCell>
                )}
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}
    </Box>
  );
};

const AssetTagImportExport: React.FC = () => {
  const { t } = useTranslation();
  const s = useAssetTagImport();
  const writable = writableCount(s.preview);
  return (
    <Card sx={{ mt: 3 }}>
      <CardHeader
        title={t('assetTags.import.title', 'Import and export')}
        subheader={t('assetTags.import.subtitle', 'Map system UUIDs or serial numbers to asset tags with a CSV file. You see what every row will do before anything is written.')}
      />
      <CardContent>
        {noticeAlert(t, s.notice)}
        <Stack direction="row" spacing={2} sx={{ mb: 2 }} flexWrap="wrap" useFlexGap>
          <Button variant="outlined" onClick={() => void s.download()}>
            {t('assetTags.import.export', 'Export CSV')}
          </Button>
          {s.canManage && (
            <Button variant="outlined" component="label" disabled={s.busy}>
              {t('assetTags.import.choose', 'Import CSV...')}
              <input
                hidden
                type="file"
                accept=".csv,text/csv"
                data-testid="asset-tag-import-file"
                onChange={e => {
                  s.chooseFile(e.target.files?.[0]);
                  e.target.value = '';
                }}
              />
            </Button>
          )}
          {s.busy && <CircularProgress size={24} aria-label={t('assetTags.import.working', 'Working')} />}
        </Stack>
        {!s.canManage && (
          <Alert severity="info" sx={{ mb: 2 }}>
            {t('assetTags.import.readOnly', 'Importing requires the Manage Asset Tags role.')}
          </Alert>
        )}
        {s.preview && (
          <Box sx={{ mb: 3 }}>
            <Typography variant="subtitle1" sx={{ mb: 1 }}>
              {t('assetTags.import.previewTitle', 'Preview: {{file}}', { file: s.fileName ?? '' })}
            </Typography>
            <PreviewTable result={s.preview} />
            <Stack direction="row" spacing={2} sx={{ mt: 2 }}>
              <Button variant="contained" disabled={s.busy || writable === 0} onClick={() => void s.apply()}>
                {t('assetTags.import.apply', 'Apply import ({{rows}})', { rows: writable })}
              </Button>
              <Button onClick={s.reset} disabled={s.busy}>
                {t('common.cancel', 'Cancel')}
              </Button>
            </Stack>
          </Box>
        )}
        <HeldTagsPanel held={s.held} failed={s.heldFailed} canManage={s.canManage} onRelease={id => void s.release(id)} />
      </CardContent>
    </Card>
  );
};

export default AssetTagImportExport;
