// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

// The advisor's posture tab (Phase 21.4 S7): the threat model, and the punch
// list it produces. Four states, and the two that are not a pass never look
// like one: a waived item is an accepted risk, and a not-assessable item was
// not measured.

import React, { useCallback, useEffect, useState } from 'react';
import {
    Alert,
    Button,
    Card,
    CardContent,
    Chip,
    CircularProgress,
    FormControl,
    InputLabel,
    MenuItem,
    Select,
    Stack,
    Table,
    TableBody,
    TableCell,
    TableHead,
    TableRow,
    Typography,
} from '@mui/material';
import { useTranslation } from 'react-i18next';
import {
    postureService,
    refusalCode,
    type ModelChanges,
    type PostureItem,
    type PostureList,
    type PostureState,
    type Questionnaire,
    type ThreatModelVersion,
} from '../../Services/postureService';
import ThreatModelWizard from './ThreatModelWizard';
import ThreatModelSummary from './ThreatModelSummary';
import PostureItemRow, { type RowAction } from './PostureItemRow';
import RemedyDialog from './RemedyDialog';
import WaiverDialog from './WaiverDialog';
import { refusalLabel, stateColor, stateLabel } from './postureLabels';
import { attributeText } from './threatModelText';

const STATES: PostureState[] = ['open', 'not_assessable', 'waived', 'satisfied'];

const NoModel: React.FC<{ onStart: () => void }> = ({ onStart }) => {
    const { t } = useTranslation();
    return (
        <Card variant="outlined">
            <CardContent>
                <Typography variant="h6">{t('posture.noModel.title', 'Describe your installation first')}</Typography>
                <Typography variant="body2" sx={{ my: 1 }}>
                    {t('posture.noModel.body',
                        'A few questions about your data, obligations and exposure decide which installation-wide checks apply to you. Until then, the posture checks cannot be assessed.')}
                </Typography>
                <Button variant="contained" onClick={onStart}>{t('posture.noModel.start', 'Start the questionnaire')}</Button>
            </CardContent>
        </Card>
    );
};

const Totals: React.FC<{ totals: PostureList['totals'] }> = ({ totals }) => {
    const { t } = useTranslation();
    return (
        <Stack direction="row" spacing={1} sx={{ mb: 2, flexWrap: 'wrap', rowGap: 1 }}>
            {STATES.map(s => (
                <Chip key={s} color={stateColor(s)} variant={s === 'open' ? 'filled' : 'outlined'}
                    label={`${stateLabel(t, s)}: ${totals[s] ?? 0}`} />
            ))}
        </Stack>
    );
};

const ChangesNotice: React.FC<{ changes: ModelChanges; onClose: () => void }> = ({ changes, onClose }) => {
    const { t } = useTranslation();
    const parts = [
        ...changes.attributes_on.map(a => `+ ${attributeText(t, a)}`),
        ...changes.attributes_off.map(a => `- ${attributeText(t, a)}`),
    ];
    return (
        <Alert severity="success" onClose={onClose} sx={{ mb: 2 }}>
            {t('posture.saved', 'Threat model saved. The punch list is re-evaluated on the next advisor pass.')}
            {parts.length > 0 && <div>{parts.join(', ')}</div>}
        </Alert>
    );
};

type Dialog = { item: PostureItem; action: RowAction } | null;

const PostureTab: React.FC = () => {
    const { t } = useTranslation();
    const [questionnaire, setQuestionnaire] = useState<Questionnaire | null>(null);
    const [versions, setVersions] = useState<ThreatModelVersion[]>([]);
    const [posture, setPosture] = useState<PostureList | null>(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const [wizard, setWizard] = useState(false);
    const [changes, setChanges] = useState<ModelChanges | null>(null);
    const [filter, setFilter] = useState<PostureState | ''>('');
    const [dialog, setDialog] = useState<Dialog>(null);

    const load = useCallback(async () => {
        try {
            const [q, m, p] = await Promise.all([
                postureService.getQuestionnaire(),
                postureService.getThreatModel(),
                postureService.getPosture(),
            ]);
            setQuestionnaire(q);
            setVersions(m.versions);
            setPosture(p);
            setError(null);
        } catch {
            setError(t('posture.loadFailed', 'The posture could not be loaded.'));
        } finally {
            setLoading(false);
        }
    }, [t]);

    useEffect(() => { void load(); }, [load]);

    const revoke = async (item: PostureItem) => {
        try {
            await postureService.revokeWaiver(item.rule_key);
        } catch (err) {
            const code = refusalCode(err);
            setError(code ? refusalLabel(t, code) : t('posture.waiver.revokeFailed', 'The waiver could not be revoked.'));
        }
        void load();
    };

    if (loading) return <CircularProgress />;
    const model = posture?.threat_model ?? null;
    const items = (posture?.items ?? []).filter(i => !filter || i.state === filter);

    return (
        <>
            {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}
            {changes && <ChangesNotice changes={changes} onClose={() => setChanges(null)} />}
            {!model && questionnaire && <NoModel onStart={() => setWizard(true)} />}
            {model && <ThreatModelSummary model={model} versions={versions} onEdit={() => setWizard(true)} />}
            {model && posture && (
                <>
                    {posture.items.some(i => !i.evaluated_under_current_model) && (
                        <Alert severity="info" sx={{ mb: 2 }}>
                            {t('posture.stalePass', 'Some items were last evaluated under an earlier threat model. They update on the next evaluation.')}
                        </Alert>
                    )}
                    <Totals totals={posture.totals} />
                    <FormControl size="small" sx={{ minWidth: 180, mb: 1 }}>
                        <InputLabel id="posture-filter" shrink>{t('posture.filter', 'Show')}</InputLabel>
                        <Select labelId="posture-filter" value={filter} label={t('posture.filter', 'Show')} displayEmpty notched
                            onChange={e => setFilter(e.target.value)}>
                            <MenuItem value="">{t('posture.filterAll', 'All items')}</MenuItem>
                            {STATES.map(s => <MenuItem key={s} value={s}>{stateLabel(t, s)}</MenuItem>)}
                        </Select>
                    </FormControl>
                    <Table size="small">
                        <TableHead>
                            <TableRow>
                                <TableCell padding="checkbox" />
                                <TableCell>{t('posture.col.state', 'State')}</TableCell>
                                <TableCell>{t('posture.col.check', 'Check')}</TableCell>
                                <TableCell>{t('posture.col.risk', 'Risk')}</TableCell>
                                <TableCell>{t('posture.col.coverage', 'Coverage')}</TableCell>
                                <TableCell>{t('posture.col.actions', 'Actions')}</TableCell>
                            </TableRow>
                        </TableHead>
                        <TableBody>
                            {items.map(i => (
                                <PostureItemRow key={i.rule_key} item={i} onRevoke={revoke}
                                    onAction={(item, action) => setDialog({ item, action })} />
                            ))}
                        </TableBody>
                    </Table>
                    {items.length === 0 && (
                        <Typography sx={{ mt: 1 }}>{t('posture.empty', 'No items in this view.')}</Typography>
                    )}
                </>
            )}
            {wizard && questionnaire && (
                <ThreatModelWizard open questionnaire={questionnaire} initial={model?.answers ?? {}}
                    onClose={() => setWizard(false)}
                    onSaved={(_m, c) => { setWizard(false); setChanges(c); void load(); }} />
            )}
            {dialog?.action === 'fix' && (
                <RemedyDialog item={dialog.item} onClose={() => setDialog(null)} onApplied={load} />
            )}
            {(dialog?.action === 'waive' || dialog?.action === 'reaffirm') && (
                <WaiverDialog item={dialog.item} mode={dialog.action} onClose={() => setDialog(null)}
                    onDone={() => { setDialog(null); void load(); }} />
            )}
        </>
    );
};

export default PostureTab;
