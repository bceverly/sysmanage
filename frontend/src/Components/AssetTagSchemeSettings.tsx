// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

// Asset-tag naming scheme (Phase 23.2).  A BUILDER (prefix, separator, zero
// padded number, suffix) with a live preview of the draft, plus an advanced
// regular-expression mode for schemes the builder cannot express.  Existing
// tags that do not fit are reported by the server, never rewritten.

import React, { useState } from 'react';
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
  Divider,
  FormControl,
  FormControlLabel,
  FormHelperText,
  InputLabel,
  MenuItem,
  Select,
  Snackbar,
  Stack,
  Switch,
  TextField,
  Typography,
} from '@mui/material';
import { useTranslation } from 'react-i18next';
import {
  AssetTagScheme,
  MAX_DIGITS,
  MIN_DIGITS,
  SEPARATORS,
  SchemeReport,
} from '../Services/machines';
import { SaveOutcome, useAssetTagScheme } from '../hooks/useAssetTagScheme';

type Update = (changes: Partial<AssetTagScheme>) => void;

interface FieldsProps {
  draft: AssetTagScheme;
  readOnly: boolean;
  invalid: string[];
  update: Update;
}

const DIGIT_CHOICES = Array.from(
  { length: MAX_DIGITS - MIN_DIGITS + 1 },
  (_, i) => MIN_DIGITS + i,
);

const monoSx = { fontFamily: 'monospace' };

const useInvalidText = (invalid: string[]) => {
  const { t } = useTranslation();
  return (field: string, normal?: string) =>
    invalid.includes(field)
      ? t('assetTags.scheme.fieldInvalid', 'This value is not valid for the scheme.')
      : normal;
};

const SeparatorSelect: React.FC<FieldsProps> = ({ draft, readOnly, invalid, update }) => {
  const { t } = useTranslation();
  const bad = invalid.includes('separator');
  return (
    <FormControl size="small" sx={{ minWidth: 140 }} error={bad} disabled={readOnly}>
      <InputLabel id="asset-tag-separator-label">
        {t('assetTags.scheme.separator', 'Separator')}
      </InputLabel>
      <Select
        labelId="asset-tag-separator-label"
        label={t('assetTags.scheme.separator', 'Separator')}
        value={draft.separator}
        onChange={e => update({ separator: String(e.target.value) })}
        inputProps={{ 'data-testid': 'asset-tag-separator' }}
      >
        {SEPARATORS.map(sep => (
          <MenuItem key={sep === '' ? 'none' : sep} value={sep}>
            {sep === '' ? t('assetTags.scheme.separatorNone', 'none') : <Box component="span" sx={monoSx}>{sep}</Box>}
          </MenuItem>
        ))}
      </Select>
      {bad && <FormHelperText>{t('assetTags.scheme.fieldInvalid', 'This value is not valid for the scheme.')}</FormHelperText>}
    </FormControl>
  );
};

const DigitsSelect: React.FC<FieldsProps> = ({ draft, readOnly, invalid, update }) => {
  const { t } = useTranslation();
  const bad = invalid.includes('digits');
  return (
    <FormControl size="small" sx={{ minWidth: 140 }} error={bad} disabled={readOnly}>
      <InputLabel id="asset-tag-digits-label">
        {t('assetTags.scheme.digits', 'Digits')}
      </InputLabel>
      <Select
        labelId="asset-tag-digits-label"
        label={t('assetTags.scheme.digits', 'Digits')}
        value={draft.digits}
        onChange={e => update({ digits: Number(e.target.value) })}
        inputProps={{ 'data-testid': 'asset-tag-digits' }}
      >
        {DIGIT_CHOICES.map(n => (
          <MenuItem key={n} value={n}>{n}</MenuItem>
        ))}
      </Select>
      <FormHelperText>
        {bad
          ? t('assetTags.scheme.fieldInvalid', 'This value is not valid for the scheme.')
          : t('assetTags.scheme.digitsHelp', 'Numbers are zero padded to this width.')}
      </FormHelperText>
    </FormControl>
  );
};

const BuilderFields: React.FC<FieldsProps> = props => {
  const { t } = useTranslation();
  const { draft, readOnly, invalid, update } = props;
  const helper = useInvalidText(invalid);
  return (
    <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2} alignItems="flex-start" flexWrap="wrap" useFlexGap>
      <TextField
        size="small"
        label={t('assetTags.scheme.prefix', 'Prefix')}
        value={draft.prefix}
        disabled={readOnly}
        error={invalid.includes('prefix')}
        helperText={helper('prefix', t('assetTags.scheme.prefixHelp', 'For example IT or HQ-LAPTOP.'))}
        onChange={e => update({ prefix: e.target.value })}
        slotProps={{ htmlInput: { 'data-testid': 'asset-tag-prefix', style: monoSx } }}
      />
      <SeparatorSelect {...props} />
      <DigitsSelect {...props} />
      <TextField
        size="small"
        label={t('assetTags.scheme.suffix', 'Suffix (optional)')}
        value={draft.suffix}
        disabled={readOnly}
        error={invalid.includes('suffix')}
        helperText={helper('suffix')}
        onChange={e => update({ suffix: e.target.value })}
        slotProps={{ htmlInput: { 'data-testid': 'asset-tag-suffix', style: monoSx } }}
      />
    </Stack>
  );
};

const RegexField: React.FC<FieldsProps> = ({ draft, readOnly, invalid, update }) => {
  const { t } = useTranslation();
  const helper = useInvalidText(invalid);
  return (
    <TextField
      fullWidth
      size="small"
      label={t('assetTags.scheme.pattern', 'Regular expression')}
      value={draft.pattern}
      disabled={readOnly}
      error={invalid.includes('pattern')}
      helperText={helper(
        'pattern',
        t(
          'assetTags.scheme.patternHelp',
          'The whole tag must match this pattern. Use it only for schemes the builder cannot express.',
        ),
      )}
      onChange={e => update({ pattern: e.target.value })}
      slotProps={{ htmlInput: { 'data-testid': 'asset-tag-pattern', style: monoSx } }}
    />
  );
};

const TagChips: React.FC<{ tags: string[]; color: 'success' | 'error'; testId: string }> = ({
  tags,
  color,
  testId,
}) => {
  const { t } = useTranslation();
  if (tags.length === 0) {
    return <Typography variant="body2" color="text.secondary">{t('assetTags.scheme.noExamples', 'No examples.')}</Typography>;
  }
  return (
    <Box data-testid={testId} sx={{ display: 'flex', flexWrap: 'wrap', gap: 1 }}>
      {tags.map(tag => (
        <Chip key={tag} label={tag} color={color} variant="outlined" size="small" sx={monoSx} />
      ))}
    </Box>
  );
};

const PreviewValue: React.FC<{ label: string; value: string | null; testId: string }> = ({
  label,
  value,
  testId,
}) => (
  <Box>
    <Typography variant="caption" color="text.secondary">{label}</Typography>
    <Typography data-testid={testId} sx={{ ...monoSx, fontSize: '1.1rem' }}>
      {value ?? '-'}
    </Typography>
  </Box>
);

const PreviewPanel: React.FC<{
  preview: SchemeReport | null;
  mode: AssetTagScheme['mode'];
  previewing: boolean;
  failed: boolean;
}> = ({ preview, mode, previewing, failed }) => {
  const { t } = useTranslation();
  return (
    <Box data-testid="asset-tag-preview">
      <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 1 }}>
        <Typography variant="subtitle1">{t('assetTags.scheme.previewTitle', 'Live preview')}</Typography>
        {previewing && <CircularProgress size={16} aria-label={t('assetTags.scheme.previewing', 'Updating preview')} />}
      </Stack>
      {failed && (
        <Alert severity="warning" sx={{ mb: 1 }}>
          {t('assetTags.scheme.previewFailed', 'This draft cannot be previewed. Check the highlighted fields.')}
        </Alert>
      )}
      {preview && (
        <Stack spacing={1.5}>
          <Stack direction="row" spacing={4} flexWrap="wrap" useFlexGap>
            {mode === 'builder' && (
              <PreviewValue label={t('assetTags.scheme.sampleTag', 'Sample tag')} value={preview.preview} testId="asset-tag-sample" />
            )}
            <PreviewValue label={t('assetTags.scheme.nextFree', 'Next free tag')} value={preview.next_free} testId="asset-tag-next-free" />
          </Stack>
          <Typography variant="body2">{t('assetTags.scheme.examplesPass', 'Tags that pass')}</Typography>
          <TagChips tags={preview.examples.pass} color="success" testId="asset-tag-pass" />
          <Typography variant="body2">{t('assetTags.scheme.examplesFail', 'Tags that fail')}</Typography>
          <TagChips tags={preview.examples.fail} color="error" testId="asset-tag-fail" />
          {preview.tagged > 0 && (
            <Typography variant="body2" color="text.secondary" data-testid="asset-tag-draft-nonconforming">
              {t(
                'assetTags.scheme.draftNonconforming',
                'With this draft, {{bad}} of {{total}} existing tags would not conform.',
                { bad: preview.nonconforming.length, total: preview.tagged },
              )}
            </Typography>
          )}
        </Stack>
      )}
    </Box>
  );
};

const conformanceSeverity = (tagged: number, bad: number): 'info' | 'warning' | 'success' => {
  if (tagged === 0) return 'info';
  return bad > 0 ? 'warning' : 'success';
};

const conformanceMessage = (t: TFunction, tagged: number, bad: number): string => {
  if (tagged === 0) {
    return t('assetTags.scheme.noTags', 'No machine has an asset tag yet.');
  }
  if (bad > 0) {
    return t(
      'assetTags.scheme.nonconformingCount',
      '{{bad}} of {{total}} existing tags do not conform to the saved scheme.',
      { bad, total: tagged },
    );
  }
  return t('assetTags.scheme.allConform', 'Every existing tag conforms to the saved scheme.');
};

const ConformancePanel: React.FC<{ saved: SchemeReport }> = ({ saved }) => {
  const { t } = useTranslation();
  const bad = saved.nonconforming;
  return (
    <Box data-testid="asset-tag-conformance">
      <Typography variant="subtitle1" sx={{ mb: 1 }}>
        {t('assetTags.scheme.conformanceTitle', 'Existing tags')}
      </Typography>
      <Alert severity={conformanceSeverity(saved.tagged, bad.length)} sx={{ mb: 1 }}>
        {conformanceMessage(t, saved.tagged, bad.length)}
      </Alert>
      {bad.length > 0 && <TagChips tags={bad} color="error" testId="asset-tag-nonconforming" />}
      <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>
        {t(
          'assetTags.scheme.reportOnly',
          'SysManage only reports tags that do not conform. It never rewrites existing tags; change them on each machine if needed.',
        )}
      </Typography>
    </Box>
  );
};

const SchemeFields: React.FC<FieldsProps> = props => {
  const { t } = useTranslation();
  const { draft, readOnly, update } = props;
  const regex = draft.mode === 'regex';
  return (
    <Stack spacing={2}>
      <FormControlLabel
        control={
          <Switch
            checked={regex}
            disabled={readOnly}
            onChange={e => update({ mode: e.target.checked ? 'regex' : 'builder' })}
            slotProps={{ input: { 'data-testid': 'asset-tag-regex-mode' } as React.InputHTMLAttributes<HTMLInputElement> }}
          />
        }
        label={t('assetTags.scheme.advancedRegex', 'Advanced: regular expression')}
      />
      {regex ? <RegexField {...props} /> : <BuilderFields {...props} />}
      <FormControlLabel
        control={
          <Switch
            checked={draft.enforce}
            disabled={readOnly}
            onChange={e => update({ enforce: e.target.checked })}
            slotProps={{ input: { 'data-testid': 'asset-tag-enforce' } as React.InputHTMLAttributes<HTMLInputElement> }}
          />
        }
        label={t('assetTags.scheme.enforce', 'Enforce at entry')}
      />
      <Typography variant="body2" color="text.secondary" sx={{ mt: -1.5 }}>
        {t(
          'assetTags.scheme.enforceHelp',
          'When on, a tag that does not fit the scheme is refused when it is entered. When off, it is accepted and reported.',
        )}
      </Typography>
    </Stack>
  );
};

const useFeedback = () => {
  const { t } = useTranslation();
  const [message, setMessage] = useState<{ severity: 'success' | 'error'; text: string } | null>(null);
  const show = (outcome: SaveOutcome) => {
    const text: Record<SaveOutcome, string> = {
      saved: t('assetTags.scheme.saved', 'Asset tag scheme saved.'),
      invalid: t('assetTags.scheme.saveInvalid', 'The scheme is not valid. Fix the highlighted fields and save again.'),
      failed: t('assetTags.scheme.saveFailed', 'Could not save the asset tag scheme.'),
    };
    setMessage({ severity: outcome === 'saved' ? 'success' : 'error', text: text[outcome] });
  };
  return { message, show, clear: () => setMessage(null) };
};

const AssetTagSchemeSettings: React.FC = () => {
  const { t } = useTranslation();
  const state = useAssetTagScheme();
  const feedback = useFeedback();

  if (state.loading) {
    return (
      <Box sx={{ display: 'flex', justifyContent: 'center', p: 4 }}>
        <CircularProgress aria-label={t('assetTags.scheme.loading', 'Loading asset tag scheme')} />
      </Box>
    );
  }
  if (state.loadFailed || !state.draft || !state.saved) {
    return <Alert severity="error">{t('assetTags.scheme.loadFailed', 'Could not load the asset tag scheme.')}</Alert>;
  }

  const readOnly = !state.canManage;
  const onSave = async () => feedback.show(await state.save());

  return (
    <Card>
      <CardHeader
        title={t('assetTags.scheme.title', 'Asset tag naming scheme')}
        subheader={t(
          'assetTags.scheme.subtitle',
          'Define what a valid asset tag looks like. The preview updates as you edit; nothing is saved until you press Save.',
        )}
      />
      <CardContent>
        <Stack spacing={3}>
          {readOnly && (
            <Alert severity="info" data-testid="asset-tag-read-only">
              {t(
                'assetTags.scheme.readOnly',
                'You can view the scheme, but changing it requires the Manage Asset Tags role.',
              )}
            </Alert>
          )}
          <SchemeFields draft={state.draft} readOnly={readOnly} invalid={state.invalidFields} update={state.update} />
          <Divider />
          <PreviewPanel
            preview={state.preview}
            mode={state.draft.mode}
            previewing={state.previewing}
            failed={state.previewFailed}
          />
          <Divider />
          <ConformancePanel saved={state.saved} />
          {!readOnly && (
            <Box>
              <Button variant="contained" onClick={() => void onSave()} disabled={state.saving}>
                {state.saving ? t('common.saving', 'Saving...') : t('common.save', 'Save')}
              </Button>
            </Box>
          )}
        </Stack>
      </CardContent>
      <Snackbar open={feedback.message !== null} autoHideDuration={6000} onClose={feedback.clear}>
        <Alert severity={feedback.message?.severity ?? 'success'} onClose={feedback.clear}>
          {feedback.message?.text}
        </Alert>
      </Snackbar>
    </Card>
  );
};

export default AssetTagSchemeSettings;
