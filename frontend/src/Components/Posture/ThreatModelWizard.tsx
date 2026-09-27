// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

// The threat-model wizard (Phase 21.4 S7): one question per step, each with
// why it is asked. It opens on the current answers, so re-running it is an
// edit, not a restart. Only answers to questions still shown are saved -- a
// branch the operator closed must not carry its old answer into the model.

import React, { useMemo, useState } from 'react';
import {
    Alert,
    Button,
    Checkbox,
    Dialog,
    DialogActions,
    DialogContent,
    DialogTitle,
    FormControlLabel,
    FormGroup,
    LinearProgress,
    Radio,
    RadioGroup,
    Typography,
} from '@mui/material';
import { useTranslation } from 'react-i18next';
import {
    postureService,
    type Answers,
    type ModelChanges,
    type Question,
    type Questionnaire,
    type ThreatModel,
} from '../../Services/postureService';
import { isAnswered, visibleAnswers, visibleQuestions } from './threatModelLogic';
import { optionText, questionText } from './threatModelText';

interface Props {
    open: boolean;
    questionnaire: Questionnaire;
    initial: Answers;
    onClose: () => void;
    onSaved: (model: ThreatModel, changes: ModelChanges) => void;
}

const QuestionInput: React.FC<{
    question: Question;
    value: string | string[] | undefined;
    onChange: (value: string | string[]) => void;
}> = ({ question, value, onChange }) => {
    const { t } = useTranslation();
    if (question.kind === 'one') {
        return (
            <RadioGroup value={typeof value === 'string' ? value : ''} onChange={e => onChange(e.target.value)}>
                {question.options.map(o => (
                    <FormControlLabel key={o.id} value={o.id} control={<Radio />}
                        label={optionText(t, question.id, o.id)} />
                ))}
            </RadioGroup>
        );
    }
    const selected = Array.isArray(value) ? value : [];
    const toggle = (id: string, on: boolean) =>
        onChange(on ? [...selected, id] : selected.filter(v => v !== id));
    return (
        <FormGroup>
            {question.options.map(o => (
                <FormControlLabel key={o.id}
                    control={<Checkbox checked={selected.includes(o.id)} onChange={e => toggle(o.id, e.target.checked)} />}
                    label={optionText(t, question.id, o.id)} />
            ))}
        </FormGroup>
    );
};

const ThreatModelWizard: React.FC<Props> = ({ open, questionnaire, initial, onClose, onSaved }) => {
    const { t } = useTranslation();
    const [answers, setAnswers] = useState<Answers>(initial);
    const [step, setStep] = useState(0);
    const [saving, setSaving] = useState(false);
    const [error, setError] = useState(false);

    // Recomputed on every answer: an answer can open or close later branches.
    const questions = useMemo(() => visibleQuestions(questionnaire, answers), [questionnaire, answers]);
    const index = Math.min(step, questions.length - 1);
    const question = questions[index];
    const last = index === questions.length - 1;
    const canAdvance = question.required === false || isAnswered(question, answers);
    const text = questionText(t, question.id);

    const save = async () => {
        setSaving(true);
        setError(false);
        try {
            const result = await postureService.saveThreatModel(visibleAnswers(questionnaire, answers));
            onSaved(result.threat_model, result.changes);
        } catch {
            setError(true);
        }
        setSaving(false);
    };

    return (
        <Dialog open={open} onClose={onClose} fullWidth maxWidth="sm">
            <DialogTitle>{t('threatModel.wizard.title', 'Describe your installation')}</DialogTitle>
            <LinearProgress variant="determinate" value={((index + 1) / questions.length) * 100} />
            <DialogContent>
                <Typography variant="caption" color="text.secondary">
                    {t('threatModel.wizard.step', 'Question {{current}} of {{total}}',
                        { current: index + 1, total: questions.length })}
                </Typography>
                <Typography variant="h6" sx={{ mt: 1 }}>{text.title}</Typography>
                {text.why && (
                    <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>{text.why}</Typography>
                )}
                {question.kind === 'many' && (
                    <Typography variant="caption">{t('threatModel.wizard.chooseAll', 'Choose all that apply.')}</Typography>
                )}
                <QuestionInput question={question} value={answers[question.id]}
                    onChange={v => setAnswers({ ...answers, [question.id]: v })} />
                {error && (
                    <Alert severity="error" sx={{ mt: 2 }}>
                        {t('threatModel.wizard.saveFailed', 'The threat model could not be saved.')}
                    </Alert>
                )}
            </DialogContent>
            <DialogActions>
                <Button onClick={onClose}>{t('common.cancel', 'Cancel')}</Button>
                <Button disabled={index === 0} onClick={() => setStep(index - 1)}>
                    {t('threatModel.wizard.back', 'Back')}
                </Button>
                {last ? (
                    <Button variant="contained" disabled={!canAdvance || saving} onClick={save}>
                        {t('threatModel.wizard.save', 'Save threat model')}
                    </Button>
                ) : (
                    <Button variant="contained" disabled={!canAdvance} onClick={() => setStep(index + 1)}>
                        {t('threatModel.wizard.next', 'Next')}
                    </Button>
                )}
            </DialogActions>
        </Dialog>
    );
};

export default ThreatModelWizard;
