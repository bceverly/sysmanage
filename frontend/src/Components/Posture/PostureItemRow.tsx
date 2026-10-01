// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

// One punch-list row (Phase 21.4 S7) and its detail: coverage, the gaps
// that kept it from being assessed, the waiver, the fix, and its history.

import React, { useState } from 'react';
import {
    Alert,
    Box,
    Button,
    Chip,
    Collapse,
    IconButton,
    Stack,
    TableCell,
    TableRow,
    Typography,
} from '@mui/material';
import KeyboardArrowDownIcon from '@mui/icons-material/KeyboardArrowDown';
import KeyboardArrowUpIcon from '@mui/icons-material/KeyboardArrowUp';
import { useTranslation } from 'react-i18next';
import { postureService, type PostureEvent, type PostureItem } from '../../Services/postureService';
import {
    eventKindLabel,
    gapLabel,
    remedyText,
    ruleTitle,
    stateColor,
    stateLabel,
    staleLabel,
} from './postureLabels';

export type RowAction = 'fix' | 'waive' | 'reaffirm';

interface Props {
    item: PostureItem;
    onAction: (item: PostureItem, action: RowAction) => void;
    onRevoke: (item: PostureItem) => void;
}

const when = (iso: string | null): string => (iso ? new Date(iso).toLocaleString() : '-');

const Coverage: React.FC<{ item: PostureItem }> = ({ item }) => {
    const { t } = useTranslation();
    const c = item.coverage;
    if (!c?.hosts_total) return <>-</>;
    return (
        <Typography variant="body2">
            {t('posture.coverage.summary', '{{ok}} of {{total}} hosts pass', { ok: c.hosts_ok, total: c.hosts_total })}
            {c.hosts_unknown > 0 && (
                <Typography component="span" variant="body2" color="warning.main">
                    {' '}{t('posture.coverage.unknown', '(not reported: {{n}})', { n: c.hosts_unknown })}
                </Typography>
            )}
        </Typography>
    );
};

const WaiverDetail: React.FC<{ item: PostureItem; onRevoke: () => void; onReaffirm: () => void }> = ({
    item, onRevoke, onReaffirm,
}) => {
    const { t } = useTranslation();
    const w = item.waiver;
    if (!w) return null;
    return (
        <Alert severity={w.stale_reason ? 'warning' : 'info'} sx={{ mb: 1 }}
            action={
                <Stack direction="row" spacing={1}>
                    {w.stale_reason && <Button size="small" onClick={onReaffirm}>{t('posture.waiver.reaffirm', 'Re-affirm')}</Button>}
                    <Button size="small" onClick={onRevoke}>{t('posture.waiver.revoke', 'Revoke')}</Button>
                </Stack>
            }>
            {t('posture.waiver.grantedBy', 'Waived by {{user}} on {{date}}: {{reason}}',
                { user: w.granted_by, date: when(w.granted_at), reason: w.reason })}
            {w.stale_reason && <div>{staleLabel(t, w.stale_reason)}</div>}
        </Alert>
    );
};

const History: React.FC<{ ruleKey: string }> = ({ ruleKey }) => {
    const { t } = useTranslation();
    const [events, setEvents] = useState<PostureEvent[] | null>(null);
    React.useEffect(() => {
        postureService.getHistory(ruleKey, 20).then(setEvents).catch(() => setEvents([]));
    }, [ruleKey]);
    if (events === null) return null;
    if (events.length === 0) {
        return <Typography variant="body2">{t('posture.history.none', 'No changes recorded yet.')}</Typography>;
    }
    return (
        <Box component="ul" sx={{ m: 0, pl: 2 }}>
            {events.map(e => (
                <li key={`${e.at}-${e.kind}`}>
                    <Typography variant="body2">{when(e.at)}: {eventKindLabel(t, e.kind)}</Typography>
                </li>
            ))}
        </Box>
    );
};

const Actions: React.FC<Omit<Props, 'onRevoke'>> = ({ item, onAction }) => {
    const { t } = useTranslation();
    const open = item.evaluated_state === 'open';
    return (
        <Stack direction="row" spacing={1}>
            {open && item.remedy && item.remedy_kind !== 'none' && (
                <Button size="small" onClick={() => onAction(item, 'fix')}>{t('posture.action.fix', 'Fix')}</Button>
            )}
            {open && !item.waiver && (
                <Button size="small" onClick={() => onAction(item, 'waive')}>{t('posture.action.waive', 'Waive')}</Button>
            )}
        </Stack>
    );
};

const PostureItemRow: React.FC<Props> = ({ item, onAction, onRevoke }) => {
    const { t } = useTranslation();
    const [expanded, setExpanded] = useState(false);
    return (
        <>
            <TableRow hover>
                <TableCell padding="checkbox">
                    <IconButton size="small" aria-label={t('posture.expand', 'Details')} onClick={() => setExpanded(!expanded)}>
                        {expanded ? <KeyboardArrowUpIcon /> : <KeyboardArrowDownIcon />}
                    </IconButton>
                </TableCell>
                <TableCell>
                    <Stack direction="row" spacing={0.5} sx={{ flexWrap: 'wrap', rowGap: 0.5 }}>
                        <Chip size="small" color={stateColor(item.state)} label={stateLabel(t, item.state)} />
                        {item.regressed && <Chip size="small" color="error" variant="outlined" label={t('posture.regressed', 'Regressed')} />}
                        {item.waiver?.stale_reason && <Chip size="small" color="warning" variant="outlined" label={t('posture.waiverStale', 'Waiver lapsed')} />}
                    </Stack>
                </TableCell>
                <TableCell>
                    <Typography variant="body2">{ruleTitle(t, item.rule_key)}</Typography>
                    {item.managed_by === 'server' && (
                        <Chip size="small" variant="outlined" sx={{ mt: 0.5 }} label={t('posture.managedByServer', 'Managed by the server operator')} />
                    )}
                </TableCell>
                <TableCell>{item.risk ?? '-'}</TableCell>
                <TableCell><Coverage item={item} /></TableCell>
                <TableCell><Actions item={item} onAction={onAction} /></TableCell>
            </TableRow>
            <TableRow>
                <TableCell colSpan={6} sx={{ py: 0, borderBottom: expanded ? undefined : 'none' }}>
                    <Collapse in={expanded} unmountOnExit>
                        <Box sx={{ py: 1 }}>
                            <WaiverDetail item={item} onRevoke={() => onRevoke(item)} onReaffirm={() => onAction(item, 'reaffirm')} />
                            {item.gaps.map(g => (
                                <Alert key={`${g.evidence}-${g.reason}`} severity="warning" sx={{ mb: 1 }}>{gapLabel(t, g.reason)}</Alert>
                            ))}
                            {item.remedy && <Typography variant="body2" sx={{ mb: 1 }}>{remedyText(t, item.remedy)}</Typography>}
                            <Typography variant="caption" color="text.secondary">
                                {t('posture.checkedAt', 'Last checked {{date}}', { date: when(item.evaluated_at) })} ({item.rule_key})
                            </Typography>
                            <Typography variant="subtitle2" sx={{ mt: 1 }}>{t('posture.history.title', 'History')}</Typography>
                            <History ruleKey={item.rule_key} />
                        </Box>
                    </Collapse>
                </TableCell>
            </TableRow>
        </>
    );
};

export default PostureItemRow;
