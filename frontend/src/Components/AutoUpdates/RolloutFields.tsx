// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

// Fleet-by-fleet rollout of an automatic policy (ROADMAP 26.4, Enterprise):
// the fleets in order -- each the hosts carrying a tag, the first being the
// canary -- their soak times, and how many failures halt the rollout.

import React from 'react';
import {
  Box,
  Button,
  Checkbox,
  FormControl,
  FormControlLabel,
  IconButton,
  InputLabel,
  MenuItem,
  Select,
  Stack,
  TextField,
  Tooltip,
  Typography,
} from '@mui/material';
import ArrowDownwardIcon from '@mui/icons-material/ArrowDownward';
import ArrowUpwardIcon from '@mui/icons-material/ArrowUpward';
import DeleteIcon from '@mui/icons-material/Delete';
import { useTranslation } from 'react-i18next';
import type { RolloutStageInput } from '../../Services/upgradeProfiles';

export interface RolloutForm {
  rollout_enabled: boolean;
  rollout_max_failure_pct: number;
  rollout_stages: RolloutStageInput[];
}

interface Props<F extends RolloutForm> {
  form: F;
  setForm: (form: F) => void;
  tags: { id: string; name: string }[];
}

function clamp(value: string, max: number, decimals = false): number {
  const n = decimals ? Number.parseFloat(value) : Number.parseInt(value, 10);
  return Number.isNaN(n) ? 0 : Math.max(0, Math.min(max, n));
}

function RolloutFields<F extends RolloutForm>({ form, setForm, tags }: Props<F>) {
  const { t } = useTranslation();
  const stages = form.rollout_stages;
  const setStages = (next: RolloutStageInput[]) => setForm({ ...form, rollout_stages: next });
  const change = (index: number, patch: Partial<RolloutStageInput>) =>
    setStages(stages.map((s, i) => (i === index ? { ...s, ...patch } : s)));
  const move = (index: number, by: number) => {
    const next = [...stages];
    [next[index], next[index + by]] = [next[index + by], next[index]];
    setStages(next);
  };
  const add = () =>
    setStages([
      ...stages,
      {
        name: stages.length === 0 ? t('upgradeProfiles.rolloutCanary', 'Canary fleet') : '',
        tag_id: '',
        soak_hours: stages.length === 0 ? 24 : 0,
      },
    ]);

  return (
    <Box>
      <FormControlLabel
        control={
          <Checkbox
            checked={form.rollout_enabled}
            onChange={(e) => {
              const on = e.target.checked;
              setForm({ ...form, rollout_enabled: on });
              if (on && stages.length === 0) add();
            }}
          />
        }
        label={t('upgradeProfiles.rolloutEnabled', 'Roll out fleet by fleet')}
      />
      {form.rollout_enabled && (
        <Stack spacing={2} sx={{ mt: 1 }}>
          <Typography variant="body2" color="text.secondary">
            {t(
              'upgradeProfiles.rolloutHelp',
              'One fleet at a time, in this order; the first is the canary. The next fleet starts only when this one has finished, is healthy and has soaked. A host is patched with the first fleet whose tag it carries; hosts in no fleet go last.',
            )}
          </Typography>
          {stages.map((stage, index) => (
            <Stack
              key={index}
              direction={{ xs: 'column', sm: 'row' }}
              spacing={1}
              sx={{ alignItems: { sm: 'center' } }}
            >
              <TextField
                size="small"
                label={t('upgradeProfiles.rolloutFleetName', 'Fleet {{n}}', { n: index + 1 })}
                value={stage.name}
                onChange={(e) => change(index, { name: e.target.value })}
                slotProps={{ htmlInput: { maxLength: 120 } }}
                sx={{ flex: 2 }}
              />
              <FormControl size="small" sx={{ flex: 2, minWidth: 140 }}>
                <InputLabel id={`rollout-fleet-tag-${index}`}>
                  {t('upgradeProfiles.rolloutFleetTag', 'Hosts tagged')}
                </InputLabel>
                <Select
                  labelId={`rollout-fleet-tag-${index}`}
                  label={t('upgradeProfiles.rolloutFleetTag', 'Hosts tagged')}
                  value={stage.tag_id}
                  onChange={(e) => change(index, { tag_id: e.target.value })}
                >
                  {tags.map((tag) => (
                    <MenuItem key={tag.id} value={tag.id}>
                      {tag.name}
                    </MenuItem>
                  ))}
                </Select>
              </FormControl>
              <TextField
                size="small"
                type="number"
                label={t('upgradeProfiles.rolloutSoak', 'Soak time (hours)')}
                value={stage.soak_hours}
                onChange={(e) => change(index, { soak_hours: clamp(e.target.value, 720, true) })}
                slotProps={{ htmlInput: { min: 0, max: 720, step: 0.5 } }}
                sx={{ flex: 1, minWidth: 100 }}
              />
              <Stack direction="row">
                <Tooltip title={t('upgradeProfiles.rolloutUp', 'Move earlier')}>
                  <span>
                    <IconButton
                      size="small"
                      aria-label={t('upgradeProfiles.rolloutUp', 'Move earlier')}
                      disabled={index === 0}
                      onClick={() => move(index, -1)}
                    >
                      <ArrowUpwardIcon fontSize="small" />
                    </IconButton>
                  </span>
                </Tooltip>
                <Tooltip title={t('upgradeProfiles.rolloutDown', 'Move later')}>
                  <span>
                    <IconButton
                      size="small"
                      aria-label={t('upgradeProfiles.rolloutDown', 'Move later')}
                      disabled={index === stages.length - 1}
                      onClick={() => move(index, 1)}
                    >
                      <ArrowDownwardIcon fontSize="small" />
                    </IconButton>
                  </span>
                </Tooltip>
                <Tooltip title={t('upgradeProfiles.rolloutRemove', 'Remove this fleet')}>
                  <IconButton
                    size="small"
                    aria-label={t('upgradeProfiles.rolloutRemove', 'Remove this fleet')}
                    onClick={() => setStages(stages.filter((_s, i) => i !== index))}
                  >
                    <DeleteIcon fontSize="small" />
                  </IconButton>
                </Tooltip>
              </Stack>
            </Stack>
          ))}
          <Box>
            <Button size="small" onClick={add} disabled={stages.length >= 20}>
              {t('upgradeProfiles.rolloutAdd', 'Add a fleet')}
            </Button>
          </Box>
          <TextField
            type="number"
            label={t('upgradeProfiles.rolloutMaxFailures', 'Halt when more than this share of a fleet fails (%)')}
            value={form.rollout_max_failure_pct}
            onChange={(e) => setForm({ ...form, rollout_max_failure_pct: clamp(e.target.value, 100) })}
            helperText={t(
              'upgradeProfiles.rolloutMaxFailuresHelp',
              '0: any failed run halts the rollout. A host not back from its reboot, a host that stopped reporting, or a new critical alert on the fleet always halts it.',
            )}
            slotProps={{ htmlInput: { min: 0, max: 100 } }}
            fullWidth
          />
        </Stack>
      )}
    </Box>
  );
}

export default RolloutFields;
