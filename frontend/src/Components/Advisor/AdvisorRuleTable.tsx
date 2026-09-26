// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

// The fleet feed: one row per rule, worst first.  "Not assessable" is a
// COLUMN beside the findings, with the reasons, because a feed that showed
// only findings would read as a healthy fleet whenever the advisor was blind.
// Expanding a rule lists the hosts behind each count.

import React, { useState } from 'react';
import {
    Box,
    Chip,
    CircularProgress,
    Collapse,
    IconButton,
    Link,
    Table,
    TableBody,
    TableCell,
    TableHead,
    TableRow,
    Tooltip,
    Typography,
} from '@mui/material';
import KeyboardArrowDownIcon from '@mui/icons-material/KeyboardArrowDown';
import KeyboardArrowUpIcon from '@mui/icons-material/KeyboardArrowUp';
import { useTranslation } from 'react-i18next';
import { Link as RouterLink } from 'react-router';
import {
    advisorService,
    type AdvisorFeedEntry,
    type AdvisorResult,
} from '../../Services/advisorService';
import { gapReasonLabel, gapText, lensLabel, outcomeLabel } from './advisorLabels';

const GapReasons: React.FC<{ reasons: Record<string, number> }> = ({ reasons }) => {
    const { t } = useTranslation();
    return (
        <Box sx={{ display: 'flex', gap: 0.5, flexWrap: 'wrap', mt: 0.5 }}>
            {Object.entries(reasons).map(([reason, count]) => (
                <Chip key={reason} size="small" variant="outlined"
                    label={`${gapReasonLabel(t, reason)} (${count})`} />
            ))}
        </Box>
    );
};

const HostLine: React.FC<{ host: AdvisorResult }> = ({ host }) => {
    const { t } = useTranslation();
    const detail = host.outcome === 'fires'
        ? (host.remediation ?? []).slice(0, 2).join('; ')
        : (host.gaps ?? []).map(g => gapText(t, g)).join('; ');
    return (
        <TableRow>
            <TableCell>
                <Link component={RouterLink} to={`/hosts/${host.host_id}#advisor`}>{host.fqdn}</Link>
            </TableCell>
            <TableCell>{outcomeLabel(t, host.outcome)}</TableCell>
            <TableCell>{detail}</TableCell>
        </TableRow>
    );
};

const RuleHosts: React.FC<{ entry: AdvisorFeedEntry }> = ({ entry }) => {
    const { t } = useTranslation();
    const [hosts, setHosts] = useState<AdvisorResult[] | null>(null);
    const [error, setError] = useState(false);
    React.useEffect(() => {
        advisorService.getRuleHosts(entry.source, entry.key)
            .then(r => setHosts(r.hosts.filter(h => h.outcome !== 'does_not_fire')))
            .catch(() => setError(true));
    }, [entry.source, entry.key]);
    if (error) {
        return <Typography color="error">{t('advisor.feed.hostsFailed', 'Could not load the hosts for this rule.')}</Typography>;
    }
    if (hosts === null) {
        return <CircularProgress size={20} />;
    }
    if (hosts.length === 0) {
        return <Typography variant="body2">{t('advisor.feed.noOpenHosts', 'No findings and nothing unassessed for this rule.')}</Typography>;
    }
    return (
        <Table size="small">
            <TableBody>
                {hosts.map(h => <HostLine key={h.host_id} host={h} />)}
            </TableBody>
        </Table>
    );
};

const RuleRow: React.FC<{ entry: AdvisorFeedEntry }> = ({ entry }) => {
    const { t } = useTranslation();
    const [open, setOpen] = useState(false);
    const title = entry.rule?.title ?? entry.key;
    return (
        <>
            <TableRow hover>
                <TableCell padding="checkbox">
                    <IconButton size="small" onClick={() => setOpen(o => !o)}
                        aria-label={t('advisor.feed.showHosts', 'Show hosts')}>
                        {open ? <KeyboardArrowUpIcon /> : <KeyboardArrowDownIcon />}
                    </IconButton>
                </TableCell>
                <TableCell>
                    <Typography variant="body2">{title}</Typography>
                    <Typography variant="caption" color="text.secondary">{entry.key}</Typography>
                </TableCell>
                <TableCell>{lensLabel(t, entry.rule?.lens)}</TableCell>
                <TableCell align="right">{entry.risk ?? '--'}</TableCell>
                <TableCell align="right">{entry.hosts_firing}</TableCell>
                <TableCell>
                    <Tooltip title={t('advisor.feed.notAssessableHelp', 'Hosts this rule could not be evaluated on -- not clean, unmeasured.')}>
                        <span>{entry.hosts_not_assessable}</span>
                    </Tooltip>
                    {entry.hosts_not_assessable > 0 && <GapReasons reasons={entry.gap_reasons} />}
                </TableCell>
                <TableCell align="right">{entry.hosts_not_applicable}</TableCell>
                <TableCell align="right">{entry.hosts_clean}</TableCell>
            </TableRow>
            <TableRow>
                <TableCell colSpan={8} sx={{ py: 0, borderBottom: open ? undefined : 'none' }}>
                    <Collapse in={open} unmountOnExit>
                        <Box sx={{ py: 1 }}><RuleHosts entry={entry} /></Box>
                    </Collapse>
                </TableCell>
            </TableRow>
        </>
    );
};

const AdvisorRuleTable: React.FC<{ rules: AdvisorFeedEntry[] }> = ({ rules }) => {
    const { t } = useTranslation();
    if (rules.length === 0) {
        return (
            <Typography sx={{ p: 2 }}>
                {t('advisor.feed.noRules', 'No rules have been evaluated yet. Enable a rule pack, then evaluate.')}
            </Typography>
        );
    }
    return (
        <Table size="small">
            <TableHead>
                <TableRow>
                    <TableCell />
                    <TableCell>{t('advisor.feed.rule', 'Rule')}</TableCell>
                    <TableCell>{t('advisor.feed.lens', 'Lens')}</TableCell>
                    <TableCell align="right">{t('advisor.feed.risk', 'Risk')}</TableCell>
                    <TableCell align="right">{t('advisor.feed.findings', 'Findings')}</TableCell>
                    <TableCell>{t('advisor.feed.notAssessable', 'Not assessable')}</TableCell>
                    <TableCell align="right">{t('advisor.feed.notApplicable', 'Not applicable')}</TableCell>
                    <TableCell align="right">{t('advisor.feed.clean', 'Clean')}</TableCell>
                </TableRow>
            </TableHead>
            <TableBody>
                {rules.map(e => <RuleRow key={`${e.source}:${e.key}`} entry={e} />)}
            </TableBody>
        </Table>
    );
};

export default AdvisorRuleTable;
