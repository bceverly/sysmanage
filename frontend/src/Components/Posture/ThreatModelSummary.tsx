// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

// The current threat model at a glance (Phase 21.4 S7): what it says about
// this installation, whether it is complete, and -- across versions -- what
// changed and what that change did to the punch list.

import React, { useState } from 'react';
import {
    Alert,
    Button,
    Card,
    CardContent,
    Chip,
    FormControl,
    InputLabel,
    MenuItem,
    Select,
    Stack,
    Typography,
} from '@mui/material';
import { useTranslation } from 'react-i18next';
import {
    postureService,
    type ModelDiff,
    type ThreatModel,
    type ThreatModelVersion,
} from '../../Services/postureService';
import { attributeText, questionText } from './threatModelText';
import { eventKindLabel, ruleTitle } from './postureLabels';

interface Props {
    model: ThreatModel;
    versions: ThreatModelVersion[];
    onEdit: () => void;
}

const DiffView: React.FC<{ diff: ModelDiff }> = ({ diff }) => {
    const { t } = useTranslation();
    const { attributes_on: on, attributes_off: off } = diff.model;
    return (
        <Stack spacing={1} sx={{ mt: 1 }}>
            {on.length + off.length === 0 && (
                <Typography variant="body2">{t('threatModel.diff.noAttributeChange', 'No change to what the model says about this installation.')}</Typography>
            )}
            <Stack direction="row" spacing={0.5} sx={{ flexWrap: 'wrap', rowGap: 0.5 }}>
                {on.map(a => <Chip key={`on-${a}`} size="small" color="primary" label={`+ ${attributeText(t, a)}`} />)}
                {off.map(a => <Chip key={`off-${a}`} size="small" variant="outlined" label={`- ${attributeText(t, a)}`} />)}
            </Stack>
            {diff.punch_list.length === 0
                ? <Typography variant="body2">{t('threatModel.diff.noPunchListChange', 'The punch list did not change.')}</Typography>
                : diff.punch_list.map(e => (
                    <Typography key={e.rule_key} variant="body2">
                        {eventKindLabel(t, e.kind)}: {ruleTitle(t, e.rule_key)}
                    </Typography>
                ))}
        </Stack>
    );
};

const VersionCompare: React.FC<{ versions: ThreatModelVersion[]; current: number }> = ({ versions, current }) => {
    const { t } = useTranslation();
    const [from, setFrom] = useState<number>(current - 1);
    const [diff, setDiff] = useState<ModelDiff | null>(null);
    const [error, setError] = useState(false);
    const compare = async () => {
        setError(false);
        try {
            setDiff(await postureService.getDiff(from, current));
        } catch {
            setError(true);
        }
    };
    return (
        <>
            <Stack direction="row" spacing={1} alignItems="center" sx={{ mt: 2 }}>
                <FormControl size="small" sx={{ minWidth: 160 }}>
                    <InputLabel id="tm-from">{t('threatModel.diff.from', 'Compare with')}</InputLabel>
                    <Select labelId="tm-from" value={from} label={t('threatModel.diff.from', 'Compare with')}
                        onChange={e => { setFrom(Number(e.target.value)); setDiff(null); }}>
                        {versions.filter(v => v.model_version < current).map(v => (
                            <MenuItem key={v.model_version} value={v.model_version}>
                                {t('threatModel.version', 'Version {{version}}', { version: v.model_version })}
                            </MenuItem>
                        ))}
                    </Select>
                </FormControl>
                <Button size="small" onClick={compare}>{t('threatModel.diff.compare', 'Compare')}</Button>
            </Stack>
            {error && <Alert severity="error" sx={{ mt: 1 }}>{t('threatModel.diff.failed', 'The versions could not be compared.')}</Alert>}
            {diff && <DiffView diff={diff} />}
        </>
    );
};

const ThreatModelSummary: React.FC<Props> = ({ model, versions, onEdit }) => {
    const { t } = useTranslation();
    const on = Object.entries(model.attributes).filter(([, v]) => v).map(([k]) => k);
    return (
        <Card variant="outlined" sx={{ mb: 2 }}>
            <CardContent>
                <Stack direction="row" justifyContent="space-between" alignItems="center">
                    <Typography variant="overline">
                        {t('threatModel.summary.title', 'Threat model, version {{version}}', { version: model.model_version })}
                    </Typography>
                    <Button size="small" onClick={onEdit}>{t('threatModel.summary.edit', 'Update threat model')}</Button>
                </Stack>
                {model.created_at && (
                    <Typography variant="caption" color="text.secondary">
                        {t('threatModel.summary.savedBy', 'Saved by {{user}} on {{date}}',
                            { user: model.created_by ?? '-', date: new Date(model.created_at).toLocaleString() })}
                    </Typography>
                )}
                {!model.complete && (
                    <Alert severity="warning" sx={{ my: 1 }}>
                        {t('threatModel.summary.incomplete', 'Some questions are unanswered, so some checks cannot be assessed: {{questions}}',
                            { questions: model.missing.map(q => questionText(t, q).title).join('; ') })}
                    </Alert>
                )}
                <Stack direction="row" spacing={0.5} sx={{ mt: 1, flexWrap: 'wrap', rowGap: 0.5 }}>
                    {on.length === 0
                        ? <Typography variant="body2">{t('threatModel.summary.baseline', 'Baseline: no elevated risk factors.')}</Typography>
                        : on.map(a => <Chip key={a} size="small" label={attributeText(t, a)} />)}
                </Stack>
                {versions.length > 1 && <VersionCompare versions={versions} current={model.model_version} />}
            </CardContent>
        </Card>
    );
};

export default ThreatModelSummary;
