// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

// The "apply automatically" half of an upgrade profile (ROADMAP 26.1,
// Enterprise): on/off, reboots, excluded packages, backups first, and the
// hosts the policy lists by name (which take precedence over its tag).

import React from 'react';
import {
  Autocomplete,
  Checkbox,
  FormControl,
  FormControlLabel,
  InputLabel,
  MenuItem,
  Select,
  TextField,
} from '@mui/material';
import { useTranslation } from 'react-i18next';

export interface AutomaticForm {
  auto_apply: boolean;
  reboot_mode: 'never' | 'when_needed';
  excluded_packages: string;
  require_backup_hours: number | '';
  host_ids: string[];
}

interface Props<F extends AutomaticForm> {
  form: F;
  setForm: (form: F) => void;
  hosts: { id: string; fqdn: string }[];
}

function AutomaticFields<F extends AutomaticForm>({ form, setForm, hosts }: Props<F>) {
  const { t } = useTranslation();
  const selected = hosts.filter((h) => form.host_ids.includes(h.id));
  return (
    <>
      <FormControlLabel
        control={
          <Checkbox
            checked={form.auto_apply}
            onChange={(e) => setForm({ ...form, auto_apply: e.target.checked })}
          />
        }
        label={t('upgradeProfiles.autoApply', 'Apply automatically on this schedule')}
      />
      {form.auto_apply && (
        <>
          <FormControl fullWidth>
            <InputLabel>{t('upgradeProfiles.reboot', 'Reboots')}</InputLabel>
            <Select
              label={t('upgradeProfiles.reboot', 'Reboots')}
              value={form.reboot_mode}
              onChange={(e) =>
                setForm({ ...form, reboot_mode: e.target.value as AutomaticForm['reboot_mode'] })
              }
            >
              <MenuItem value="never">
                {t('upgradeProfiles.rebootNever', 'Never (the host shows "reboot required")')}
              </MenuItem>
              <MenuItem value="when_needed">
                {t('upgradeProfiles.rebootWhenNeeded', 'Reboot when the update needs it')}
              </MenuItem>
            </Select>
          </FormControl>
          <TextField
            label={t('upgradeProfiles.excluded', 'Never apply these packages')}
            value={form.excluded_packages}
            onChange={(e) => setForm({ ...form, excluded_packages: e.target.value })}
            helperText={t(
              'upgradeProfiles.excludedHelp',
              'Comma-separated names; * matches anything (linux-image-*, postgresql*)',
            )}
            fullWidth
          />
          <TextField
            label={t('upgradeProfiles.backupHours', 'Only after a good backup within (hours)')}
            type="number"
            value={form.require_backup_hours}
            onChange={(e) => {
              const n = Number.parseInt(e.target.value, 10);
              setForm({ ...form, require_backup_hours: Number.isNaN(n) ? '' : Math.max(1, Math.min(720, n)) });
            }}
            helperText={t('upgradeProfiles.backupHelp', 'Blank: do not check backups')}
            slotProps={{ htmlInput: { min: 1, max: 720 } }}
            fullWidth
          />
          <Autocomplete
            multiple
            options={hosts}
            value={selected}
            getOptionLabel={(h) => h.fqdn}
            isOptionEqualToValue={(a, b) => a.id === b.id}
            onChange={(_e, value) => setForm({ ...form, host_ids: value.map((h) => h.id) })}
            renderInput={(params) => (
              <TextField
                {...params}
                label={t('upgradeProfiles.listedHostsLabel', 'Only these hosts')}
                helperText={t(
                  'upgradeProfiles.listedHostsHelp',
                  'Listed hosts take precedence over the tag. A host covered by several policies follows the most specific one.',
                )}
              />
            )}
          />
        </>
      )}
    </>
  );
}

export default AutomaticFields;
