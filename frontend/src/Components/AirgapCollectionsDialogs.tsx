// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

/**
 * Dialogs for the Air-Gap Collection Runs page: the "New Collection Run"
 * create dialog and the multi-disc download picker.  Both are purely
 * presentational — the owning page holds all state and passes it in via
 * props.  Extracted from AirgapCollections.tsx to keep the page under the
 * max-lines budget.
 */

import React from 'react';
import {
  Alert,
  Button,
  Checkbox,
  CircularProgress,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  FormControl,
  FormControlLabel,
  InputLabel,
  MenuItem,
  Select,
  Stack,
  TextField,
  Typography,
} from '@mui/material';
import { Download as DownloadIcon } from '@mui/icons-material';
import { useTranslation } from 'react-i18next';

import {
  CollectionRun,
  DiscInfo,
  MirrorPickItem,
  formatBytes,
} from './AirgapCollectionsHelpers';

interface NewRunDialogProps {
  open: boolean;
  onClose: () => void;
  submitting: boolean;
  onCreate: () => void;
  isoLabel: string;
  onIsoLabelChange: (v: string) => void;
  mediaSizeMB: number;
  onMediaSizeMBChange: (v: number) => void;
  includeCve: boolean;
  onIncludeCveChange: (v: boolean) => void;
  includeCompliance: boolean;
  onIncludeComplianceChange: (v: boolean) => void;
  mirrorIds: string[];
  onMirrorIdsChange: (v: string[]) => void;
  availableMirrors: MirrorPickItem[];
  pickedHostMismatch: boolean;
  burnDevice: string;
  onBurnDeviceChange: (v: string) => void;
}

/** The "New Collection Run" create dialog. */
export const NewRunDialog: React.FC<NewRunDialogProps> = ({
  open,
  onClose,
  submitting,
  onCreate,
  isoLabel,
  onIsoLabelChange,
  mediaSizeMB,
  onMediaSizeMBChange,
  includeCve,
  onIncludeCveChange,
  includeCompliance,
  onIncludeComplianceChange,
  mirrorIds,
  onMirrorIdsChange,
  availableMirrors,
  pickedHostMismatch,
  burnDevice,
  onBurnDeviceChange,
}) => {
  const { t } = useTranslation();
  return (
    <Dialog open={open} onClose={onClose} fullWidth maxWidth="sm">
      <DialogTitle>
        {t('airgapCollections.dialog.title', 'New Collection Run')}
      </DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ mt: 1 }}>
          <TextField
            autoFocus
            required
            fullWidth
            label={t('airgapCollections.dialog.isoLabel', 'ISO Label')}
            value={isoLabel}
            onChange={(e) => onIsoLabelChange(e.target.value)}
            slotProps={{ htmlInput: { maxLength: 80 } }}
            helperText={t(
              'airgapCollections.dialog.isoLabelHelper',
              'Short identifier embedded in the produced ISO (e.g. "monthly-2026-05").',
            )}
          />
          <TextField
            required
            fullWidth
            type="number"
            label={t('airgapCollections.dialog.mediaSizeMb', 'Media Size (MB)')}
            value={mediaSizeMB}
            onChange={(e) =>
              onMediaSizeMBChange(
                Math.max(1, Number.parseInt(e.target.value, 10) || 0),
              )
            }
            helperText={t(
              'airgapCollections.dialog.mediaSizeHelper',
              'Maximum size per disc in MB. Defaults to 4700 (DVD-5).',
            )}
          />
          <FormControlLabel
            control={
              <Checkbox
                checked={includeCve}
                onChange={(e) => onIncludeCveChange(e.target.checked)}
              />
            }
            label={t(
              'airgapCollections.dialog.includeCve',
              'Include CVE feed snapshot',
            )}
          />
          <FormControlLabel
            control={
              <Checkbox
                checked={includeCompliance}
                onChange={(e) => onIncludeComplianceChange(e.target.checked)}
              />
            }
            label={t(
              'airgapCollections.dialog.includeCompliance',
              'Include compliance bundle',
            )}
          />

          {/* Mirror picker.  Option-B sources the bundle from
              snapshots of configured mirror_repository rows — the
              operator picks which ones to bundle and the backend
              handles snapshot dispatch + distro/version derivation. */}
          <Typography variant="subtitle2" sx={{ mt: 1 }}>
            {t('airgapCollections.dialog.mirrorsTitle', 'Mirrors')}
          </Typography>
          <Typography variant="caption" color="text.secondary">
            {t(
              'airgapCollections.dialog.mirrorsHelper',
              'Pick one or more configured mirrors. The bundle is built from a fresh snapshot of each mirror tree taken at run creation. All picks must share a host.',
            )}
          </Typography>
          {availableMirrors.length === 0 ? (
            <Alert severity="info" sx={{ mt: 1 }}>
              {t(
                'airgapCollections.dialog.noMirrors',
                'No enabled mirrors configured. Go to Settings → Repository Mirroring to add one, then try again.',
              )}
            </Alert>
          ) : (
            <FormControl size="small" fullWidth>
              <InputLabel id="mirror-picker-label">
                {t('airgapCollections.dialog.mirrorPicker', 'Pick mirrors')}
              </InputLabel>
              <Select
                labelId="mirror-picker-label"
                multiple
                value={mirrorIds}
                label={t('airgapCollections.dialog.mirrorPicker', 'Pick mirrors')}
                onChange={(e) =>
                  onMirrorIdsChange(
                    typeof e.target.value === 'string'
                      ? e.target.value.split(',')
                      : e.target.value,
                  )
                }
                renderValue={(selected) =>
                  selected
                    .map(
                      (id) =>
                        availableMirrors.find((m) => m.id === id)?.name ?? id,
                    )
                    .join(', ')
                }
              >
                {availableMirrors.map((m) => (
                  <MenuItem key={m.id} value={m.id}>
                    <Checkbox checked={mirrorIds.includes(m.id)} />
                    <Typography variant="body2">
                      {m.name}{' '}
                      <Typography
                        variant="caption"
                        color="text.secondary"
                        component="span"
                      >
                        ({m.package_manager}
                        {m.known_version_id ? '' : ' — no catalog version!'})
                      </Typography>
                    </Typography>
                  </MenuItem>
                ))}
              </Select>
            </FormControl>
          )}
          {pickedHostMismatch && (
            <Alert severity="warning" sx={{ mt: 1 }}>
              {t(
                'airgapCollections.dialog.hostMismatchWarning',
                'The mirrors you picked span multiple hosts. The collection plan dispatches to a single host, so all picks must share one.',
              )}
            </Alert>
          )}

          <TextField
            fullWidth
            size="small"
            label={t(
              'airgapCollections.dialog.burnDevice',
              'Optical burn device (optional)',
            )}
            placeholder="/dev/sr0"
            value={burnDevice}
            onChange={(e) => onBurnDeviceChange(e.target.value)}
            helperText={t(
              'airgapCollections.dialog.burnDeviceHelper',
              'Leave blank to build a downloadable ISO file only. Setting a device adds a BURNING stage after ISO_BUILT.',
            )}
          />
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose} disabled={submitting}>
          {t('airgapCollections.dialog.cancel', 'Cancel')}
        </Button>
        <Button
          variant="contained"
          onClick={onCreate}
          disabled={submitting}
          startIcon={submitting ? <CircularProgress size={16} /> : undefined}
        >
          {t('airgapCollections.dialog.submit', 'Queue Run')}
        </Button>
      </DialogActions>
    </Dialog>
  );
};

interface DiscPickerDialogProps {
  run: CollectionRun | null;
  entries: DiscInfo[];
  onClose: () => void;
  onSelect: (run: CollectionRun, discIndex: number) => void;
}

/** Multi-disc download picker.  Opens when a run produced >1 disc; closes
 * on disc selection or cancel. */
export const DiscPickerDialog: React.FC<DiscPickerDialogProps> = ({
  run,
  entries,
  onClose,
  onSelect,
}) => {
  const { t } = useTranslation();
  return (
    <Dialog open={run !== null} onClose={onClose} fullWidth maxWidth="xs">
      <DialogTitle>
        {t('airgapCollections.discPicker.title', 'Pick a disc to download')}
      </DialogTitle>
      <DialogContent>
        <Stack spacing={1} sx={{ mt: 1 }}>
          {entries.map((d) => (
            <Button
              key={d.disc_index}
              variant="outlined"
              startIcon={<DownloadIcon />}
              onClick={() => {
                if (!run) return;
                onSelect(run, d.disc_index);
              }}
            >
              {t('airgapCollections.discPicker.row', 'Disc {{n}} — {{size}}', {
                n: d.disc_index,
                size: formatBytes(d.size_bytes),
              })}
            </Button>
          ))}
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>
          {t('airgapCollections.discPicker.cancel', 'Cancel')}
        </Button>
      </DialogActions>
    </Dialog>
  );
};
