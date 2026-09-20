// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

import React, { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import Alert from '@mui/material/Alert';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Chip from '@mui/material/Chip';
import Dialog from '@mui/material/Dialog';
import DialogActions from '@mui/material/DialogActions';
import DialogContent from '@mui/material/DialogContent';
import DialogTitle from '@mui/material/DialogTitle';
import FormControlLabel from '@mui/material/FormControlLabel';
import MenuItem from '@mui/material/MenuItem';
import Stack from '@mui/material/Stack';
import Switch from '@mui/material/Switch';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';

import {
    ConfigRemediationRule,
    createRemediationRule,
    deleteRemediationRule,
    getRemediationRules,
    updateRemediationRule,
} from '../Services/configFleetService';
import { ConfigProfile, getConfigProfiles } from '../Services/configManagementService';

const messageFrom = (err: unknown, fallback: string): string => {
    const detail = (err as { response?: { data?: { detail?: unknown } } })?.response
        ?.data?.detail;
    return typeof detail === 'string' && detail ? detail : fallback;
};

const emptyForm = {
    name: '',
    description: '',
    taskPattern: '',
    remediationProfileId: '',
    profileId: '',
    priority: '100',
    autoApply: false,
};

interface Props {
    canEdit: boolean;
}

/**
 * Remediation playbooks: which profile repairs which divergence.
 *
 * The playbook itself is an ordinary profile authored on the Config Profiles
 * page -- this panel only binds one to the findings it fixes. That is why
 * there is no editor here: a second authoring surface would mean a second
 * validation, a second version history and a second way for the two to
 * disagree.
 *
 * Rules are listed in PRECEDENCE order, not by name. The list is the sequence
 * a finding is tested against, and an operator who cannot predict which repair
 * fires will never turn automatic ones on.
 */
const ConfigRemediationRulesPanel: React.FC<Props> = ({ canEdit }) => {
    const { t } = useTranslation();
    const [rules, setRules] = useState<ConfigRemediationRule[]>([]);
    const [profiles, setProfiles] = useState<ConfigProfile[]>([]);
    const [error, setError] = useState<string | null>(null);
    const [creating, setCreating] = useState(false);
    const [form, setForm] = useState(emptyForm);
    const [saving, setSaving] = useState(false);

    const load = useCallback(async () => {
        try {
            const [ruleRows, profileRows] = await Promise.all([
                getRemediationRules(),
                getConfigProfiles(),
            ]);
            setRules(ruleRows);
            setProfiles(profileRows);
            setError(null);
        } catch (err) {
            setError(
                messageFrom(
                    err,
                    t('configRemediation.loadFailed', 'Could not load remediation rules'),
                ),
            );
        }
    }, [t]);

    useEffect(() => {
        load();
    }, [load]);

    const save = async () => {
        setSaving(true);
        try {
            await createRemediationRule({
                name: form.name,
                description: form.description || null,
                task_pattern: form.taskPattern,
                remediation_profile_id: form.remediationProfileId,
                profile_id: form.profileId || null,
                priority: Number(form.priority) || 100,
                auto_apply: form.autoApply,
            });
            setForm(emptyForm);
            setCreating(false);
            await load();
        } catch (err) {
            setError(
                messageFrom(
                    err,
                    t('configRemediation.saveFailed', 'Could not save the rule'),
                ),
            );
        } finally {
            setSaving(false);
        }
    };

    const toggleAuto = async (rule: ConfigRemediationRule) => {
        try {
            await updateRemediationRule(rule.id, { auto_apply: !rule.auto_apply });
            await load();
        } catch (err) {
            setError(
                messageFrom(
                    err,
                    t('configRemediation.saveFailed', 'Could not save the rule'),
                ),
            );
        }
    };

    const remove = async (rule: ConfigRemediationRule) => {
        try {
            await deleteRemediationRule(rule.id);
            await load();
        } catch (err) {
            setError(
                messageFrom(
                    err,
                    t('configRemediation.deleteFailed', 'Could not delete the rule'),
                ),
            );
        }
    };

    return (
        <Box>
            <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
                {t(
                    'configRemediation.intro',
                    'A rule points a drift finding at the profile that repairs it — a ' +
                        'narrower fix than re-applying the whole baseline. Rules are ' +
                        'tried in the order shown; the first match wins.',
                )}
            </Typography>

            {error && (
                <Alert severity="error" sx={{ mb: 2 }} onClose={() => setError(null)}>
                    {error}
                </Alert>
            )}

            {canEdit && (
                <Button
                    variant="contained"
                    sx={{ mb: 2 }}
                    onClick={() => setCreating(true)}
                    disabled={profiles.length === 0}
                >
                    {t('configRemediation.newRule', 'New rule')}
                </Button>
            )}

            {rules.length === 0 ? (
                <Alert severity="info">
                    {t(
                        'configRemediation.noRules',
                        'No remediation rules yet. Without one, the only repair available ' +
                            'is re-applying the whole profile.',
                    )}
                </Alert>
            ) : (
                <Stack spacing={1}>
                    {rules.map((rule) => (
                        <Box
                            key={rule.id}
                            sx={{ border: 1, borderColor: 'divider', borderRadius: 1, p: 2 }}
                        >
                            <Stack
                                direction="row"
                                spacing={2}
                                alignItems="center"
                                flexWrap="wrap"
                            >
                                <Typography variant="subtitle1" sx={{ flexGrow: 1 }}>
                                    {rule.name}
                                </Typography>
                                <Chip
                                    size="small"
                                    label={t('configRemediation.priority', 'Priority {{n}}', {
                                        n: rule.priority,
                                    })}
                                />
                                {rule.auto_apply && (
                                    <Chip
                                        size="small"
                                        color="warning"
                                        label={t('configRemediation.automatic', 'Automatic')}
                                    />
                                )}
                                {canEdit && (
                                    <>
                                        <Button size="small" onClick={() => toggleAuto(rule)}>
                                            {rule.auto_apply
                                                ? t(
                                                      'configRemediation.makeManual',
                                                      'Require approval',
                                                  )
                                                : t(
                                                      'configRemediation.makeAutomatic',
                                                      'Repair automatically',
                                                  )}
                                        </Button>
                                        <Button
                                            size="small"
                                            color="error"
                                            onClick={() => remove(rule)}
                                        >
                                            {t('common.delete', 'Delete')}
                                        </Button>
                                    </>
                                )}
                            </Stack>
                            <Typography variant="body2" color="text.secondary">
                                <code>{rule.task_pattern}</code>
                                {' → '}
                                {rule.remediation_profile_name ||
                                    rule.remediation_profile_id}
                            </Typography>
                            <Typography variant="caption" color="text.secondary">
                                {rule.profile_name
                                    ? t(
                                          'configRemediation.scoped',
                                          'Only drift from {{profile}}',
                                          { profile: rule.profile_name },
                                      )
                                    : t(
                                          'configRemediation.anyProfile',
                                          'Drift from any profile',
                                      )}
                            </Typography>
                        </Box>
                    ))}
                </Stack>
            )}

            <Dialog
                open={creating}
                onClose={() => setCreating(false)}
                maxWidth="sm"
                fullWidth
            >
                <DialogTitle>
                    {t('configRemediation.newRule', 'New rule')}
                </DialogTitle>
                <DialogContent>
                    <Stack spacing={2} sx={{ mt: 1 }}>
                        <TextField
                            label={t('configRemediation.name', 'Name')}
                            value={form.name}
                            onChange={(e) => setForm({ ...form, name: e.target.value })}
                            fullWidth
                        />
                        <TextField
                            label={t('configRemediation.pattern', 'Task pattern')}
                            value={form.taskPattern}
                            onChange={(e) =>
                                setForm({ ...form, taskPattern: e.target.value })
                            }
                            helperText={t(
                                'configRemediation.patternHelp',
                                'Matched against the drifting task name, case-insensitively. ' +
                                    'Wildcards allowed, e.g. "ensure nginx*".',
                            )}
                            fullWidth
                        />
                        <TextField
                            select
                            label={t('configRemediation.repairWith', 'Repair with')}
                            value={form.remediationProfileId}
                            onChange={(e) =>
                                setForm({ ...form, remediationProfileId: e.target.value })
                            }
                            fullWidth
                        >
                            {profiles.map((p) => (
                                <MenuItem key={p.id} value={p.id}>
                                    {p.name}
                                </MenuItem>
                            ))}
                        </TextField>
                        <TextField
                            select
                            label={t('configRemediation.scopeTo', 'Only drift from')}
                            value={form.profileId}
                            onChange={(e) =>
                                setForm({ ...form, profileId: e.target.value })
                            }
                            helperText={t(
                                'configRemediation.scopeHelp',
                                'Leave empty to repair this task wherever it drifts.',
                            )}
                            fullWidth
                        >
                            <MenuItem value="">
                                {t('configRemediation.anyProfile', 'Drift from any profile')}
                            </MenuItem>
                            {profiles.map((p) => (
                                <MenuItem key={p.id} value={p.id}>
                                    {p.name}
                                </MenuItem>
                            ))}
                        </TextField>
                        <TextField
                            label={t('configRemediation.priorityField', 'Priority')}
                            value={form.priority}
                            onChange={(e) =>
                                setForm({ ...form, priority: e.target.value })
                            }
                            helperText={t(
                                'configRemediation.priorityHelp',
                                'Lowest number wins when two rules match.',
                            )}
                            fullWidth
                        />
                        <FormControlLabel
                            control={
                                <Switch
                                    checked={form.autoApply}
                                    onChange={(e) =>
                                        setForm({ ...form, autoApply: e.target.checked })
                                    }
                                />
                            }
                            label={t(
                                'configRemediation.autoLabel',
                                'Repair automatically, without waiting for an operator',
                            )}
                        />
                        <Typography variant="caption" color="text.secondary">
                            {t(
                                'configRemediation.autoHelp',
                                'An automatic repair runs the moment this drift is first ' +
                                    'detected, and is still held until the next maintenance ' +
                                    'window if one applies.',
                            )}
                        </Typography>
                    </Stack>
                </DialogContent>
                <DialogActions>
                    <Button onClick={() => setCreating(false)} disabled={saving}>
                        {t('common.cancel', 'Cancel')}
                    </Button>
                    <Button
                        variant="contained"
                        onClick={save}
                        disabled={
                            saving ||
                            !form.name ||
                            !form.taskPattern ||
                            !form.remediationProfileId
                        }
                    >
                        {t('common.save', 'Save')}
                    </Button>
                </DialogActions>
            </Dialog>
        </Box>
    );
};

export default ConfigRemediationRulesPanel;
