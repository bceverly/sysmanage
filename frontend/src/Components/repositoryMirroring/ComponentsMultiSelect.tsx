// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

import React from 'react';
import {
  Checkbox,
  FormControl,
  InputLabel,
  MenuItem,
  Select,
} from '@mui/material';
import { useTranslation } from 'react-i18next';

// ---------------------------------------------------------------------
// APT components multi-select (Phase 10.4.4)
// ---------------------------------------------------------------------
//
// Keyed off the catalog entry's ``os_family`` so Ubuntu mirrors show
// Ubuntu-specific components and Debian mirrors show Debian-specific
// components.  When no catalog row is selected yet, we fall back to
// the union of common values so the operator isn't blocked.

const COMPONENTS_BY_FAMILY: Record<string, string[]> = {
  ubuntu: ['main', 'restricted', 'universe', 'multiverse'],
  debian: ['main', 'contrib', 'non-free', 'non-free-firmware'],
};
const COMPONENTS_FALLBACK = [
  'main', 'restricted', 'universe', 'multiverse',
  'contrib', 'non-free', 'non-free-firmware',
];

interface ComponentsMultiSelectProps {
  osFamily: string | undefined;
  value: string[];
  onChange: (next: string[]) => void;
}

const ComponentsMultiSelect: React.FC<ComponentsMultiSelectProps> = ({
  osFamily,
  value,
  onChange,
}) => {
  const { t } = useTranslation();
  const options = (osFamily && COMPONENTS_BY_FAMILY[osFamily]) || COMPONENTS_FALLBACK;
  return (
    <FormControl fullWidth required>
      <InputLabel id="apt-components-label">
        {t('mirror.field.components', 'Components')}
      </InputLabel>
      <Select
        labelId="apt-components-label"
        label={t('mirror.field.components', 'Components')}
        multiple
        value={value}
        onChange={(e) => {
          const v = e.target.value;
          onChange(typeof v === 'string' ? v.split(',') : v);
        }}
        renderValue={(selected: string[]) => selected.join(' ')}
      >
        {options.map((c) => (
          <MenuItem key={c} value={c}>
            <Checkbox checked={value.includes(c)} />
            {c}
          </MenuItem>
        ))}
      </Select>
    </FormControl>
  );
};

export default ComponentsMultiSelect;
