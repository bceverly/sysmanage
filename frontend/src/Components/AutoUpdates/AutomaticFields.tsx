// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

// The "apply automatically" half of an upgrade profile (ROADMAP 26.1,
// Enterprise): on/off, reboots, excluded packages, backups first, and the
// hosts the policy lists by name (which take precedence over its tag);
// reboots only inside a maintenance window (26.2) and the waiting periods
// for regular and critical-CVE patches (26.3); fleet-by-fleet rollout
// (26.4).

import React from 'react';
import {
  Autocomplete,
  Checkbox,
  FormControl,
  FormControlLabel,
  FormHelperText,
  InputLabel,
  MenuItem,
  Select,
  TextField,
} from '@mui/material';
import { useTranslation } from 'react-i18next';
import type { CriticalSource, RebootMode } from '../../Services/upgradeProfiles';
import RolloutFields, { type RolloutForm } from './RolloutFields';

export interface AutomaticForm extends RolloutForm {
  auto_apply: boolean;
  reboot_mode: RebootMode;
  excluded_packages: string;
  require_backup_hours: number | '';
  host_ids: string[];
  wait_days_regular: number;
  wait_days_critical: number;
  critical_source: CriticalSource;
}

function days(value: string): number {
  const n = Number.parseInt(value, 10);
  return Number.isNaN(n) ? 0 : Math.max(0, Math.min(365, n));
}

interface Props<F extends AutomaticForm> {
  form: F;
  setForm: (form: F) => void;
  hosts: { id: string; fqdn: string }[];
  tags?: { id: string; name: string }[];
}

function AutomaticFields<F extends AutomaticForm>({ form, setForm, hosts, tags = [] }: Readonly<Props<F>>) {
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
            <InputLabel id="automatic-fields-reboot-label">{t('upgradeProfiles.reboot', 'Reboots')}</InputLabel>
            <Select
              labelId="automatic-fields-reboot-label"
              label={t('upgradeProfiles.reboot', 'Reboots')}
              value={form.reboot_mode}
              onChange={(e) =>
                setForm({ ...form, reboot_mode: e.target.value })
              }
            >
              <MenuItem value="never">
                {t('upgradeProfiles.rebootNever', 'Never (the host shows "reboot required")')}
              </MenuItem>
              <MenuItem value="when_needed">
                {t('upgradeProfiles.rebootWhenNeeded', 'Reboot when the update needs it')}
              </MenuItem>
              <MenuItem value="in_window">
                {t(
                  'upgradeProfiles.rebootInWindow',
                  'Reboot when needed, only inside a maintenance window',
                )}
              </MenuItem>
            </Select>
          </FormControl>
          <TextField
            label={t('upgradeProfiles.waitRegular', 'Wait before applying a regular patch (days)')}
            type="number"
            value={form.wait_days_regular}
            onChange={(e) => setForm({ ...form, wait_days_regular: days(e.target.value) })}
            helperText={t(
              'upgradeProfiles.waitHelp',
              'Counted from when the host first saw the update, or the vendor released it if that was earlier. 0: apply at once.',
            )}
            slotProps={{ htmlInput: { min: 0, max: 365 } }}
            fullWidth
          />
          <TextField
            label={t(
              'upgradeProfiles.waitCritical',
              'Wait before applying a patch that fixes a critical CVE (days)',
            )}
            type="number"
            value={form.wait_days_critical}
            onChange={(e) => setForm({ ...form, wait_days_critical: days(e.target.value) })}
            slotProps={{ htmlInput: { min: 0, max: 365 } }}
            fullWidth
          />
          <FormControl fullWidth>
            <InputLabel id="automatic-fields-critical-source-label">
              {t('upgradeProfiles.criticalSource', 'Critical means rated critical by')}
            </InputLabel>
            <Select
              labelId="automatic-fields-critical-source-label"
              label={t('upgradeProfiles.criticalSource', 'Critical means rated critical by')}
              value={form.critical_source}
              onChange={(e) =>
                setForm({ ...form, critical_source: e.target.value })
              }
            >
              <MenuItem value="either">
                {t('upgradeProfiles.criticalEither', 'The vulnerability scan or the vendor advisory')}
              </MenuItem>
              <MenuItem value="vulnerability">
                {t('upgradeProfiles.criticalVulnerability', 'The vulnerability scan of the host')}
              </MenuItem>
              <MenuItem value="advisory">
                {t('upgradeProfiles.criticalAdvisory', 'The vendor advisory')}
              </MenuItem>
            </Select>
            <FormHelperText>
              {t(
                'upgradeProfiles.criticalHelp',
                'Without vulnerability scans or vendor advisories for a host, every patch on it waits the regular count.',
              )}
            </FormHelperText>
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
          <RolloutFields form={form} setForm={setForm} tags={tags} />
        </>
      )}
    </>
  );
}

export default AutomaticFields;
