// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

// One host's advisor view (Phase 21.2 S7): its grade, its findings with
// remediation and proposed fixes, and -- as its own list, never hidden --
// every rule that could not be assessed here, with exactly what is missing.
// A host with no findings and a long not-assessable list is not healthy; it
// is unmeasured, and this tab must make that obvious.

import React, { useCallback, useEffect, useState } from 'react';
import {
    Accordion,
    AccordionDetails,
    AccordionSummary,
    Alert,
    Box,
    Chip,
    CircularProgress,
    List,
    ListItem,
    ListItemText,
    Stack,
    Typography,
} from '@mui/material';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import { useTranslation } from 'react-i18next';
import {
    advisorService,
    type AdvisorHostView,
    type AdvisorProposal,
    type AdvisorResult,
} from '../../Services/advisorService';
import AdvisorScoreSummary from '../Advisor/AdvisorScoreSummary';
import AdvisorProposalList from '../Advisor/AdvisorProposalList';
import { gapText, lensLabel } from '../Advisor/advisorLabels';

const Finding: React.FC<{ result: AdvisorResult }> = ({ result }) => {
    const { t } = useTranslation();
    return (
        <ListItem alignItems="flex-start" divider>
            <ListItemText
                primary={
                    <Stack direction="row" spacing={1} alignItems="center">
                        <Typography>{result.title ?? result.key}</Typography>
                        <Chip size="small" label={lensLabel(t, result.lens)} />
                        <Chip size="small" color="error" variant="outlined"
                            label={t('advisor.host.risk', 'Risk {{risk}}', { risk: result.risk ?? '--' })} />
                    </Stack>
                }
                secondary={
                    <>
                        {(result.remediation ?? []).map(line => (
                            <Typography key={line} variant="body2" component="span" display="block">{line}</Typography>
                        ))}
                        {(result.match_count ?? 0) > (result.remediation ?? []).length && (
                            <Typography variant="caption" component="span" display="block">
                                {t('advisor.host.moreMatches', '{{count}} matches in total', { count: result.match_count })}
                            </Typography>
                        )}
                    </>
                }
            />
        </ListItem>
    );
};

const Unassessed: React.FC<{ result: AdvisorResult }> = ({ result }) => {
    const { t } = useTranslation();
    return (
        <ListItem divider>
            <ListItemText
                primary={result.title ?? result.key}
                secondary={(result.gaps ?? []).map(g => gapText(t, g)).join('; ')}
            />
        </ListItem>
    );
};

const Section: React.FC<{ title: string; count: number; defaultExpanded?: boolean; children: React.ReactNode }> = ({
    title,
    count,
    defaultExpanded,
    children,
}) => (
    <Accordion defaultExpanded={defaultExpanded} disableGutters>
        <AccordionSummary expandIcon={<ExpandMoreIcon />}>
            <Typography>{`${title} (${count})`}</Typography>
        </AccordionSummary>
        <AccordionDetails sx={{ p: 0 }}>{children}</AccordionDetails>
    </Accordion>
);

const HostAdvisorTab: React.FC<{ hostId: string }> = ({ hostId }) => {
    const { t } = useTranslation();
    const [view, setView] = useState<AdvisorHostView | null>(null);
    const [proposals, setProposals] = useState<AdvisorProposal[]>([]);
    const [error, setError] = useState(false);

    const load = useCallback(async () => {
        setError(false);
        try {
            const [v, p] = await Promise.all([
                advisorService.getHost(hostId),
                advisorService.listProposals(undefined, hostId),
            ]);
            setView(v);
            setProposals(p);
        } catch {
            setError(true);
        }
    }, [hostId]);

    useEffect(() => { load(); }, [load]);

    if (error) {
        return <Alert severity="error">{t('advisor.loadFailed', 'The advisor could not be loaded.')}</Alert>;
    }
    if (view === null) {
        return <CircularProgress />;
    }
    const nothingEvaluated = view.findings.length + view.not_assessable.length
        + view.not_applicable.length + view.clean.length === 0;
    return (
        <Box>
            <Box sx={{ mb: 2 }}><AdvisorScoreSummary host={view.score} /></Box>
            {nothingEvaluated && (
                <Alert severity="info" sx={{ mb: 2 }}>
                    {t('advisor.host.notEvaluated', 'The advisor has not evaluated this host yet.')}
                </Alert>
            )}
            <Section title={t('advisor.host.findings', 'Findings')} count={view.findings.length} defaultExpanded>
                <List dense>{view.findings.map(r => <Finding key={`${r.source}:${r.key}`} result={r} />)}</List>
            </Section>
            <Section title={t('advisor.host.notAssessable', 'Not assessable')} count={view.not_assessable.length}
                defaultExpanded={view.not_assessable.length > 0}>
                <List dense>{view.not_assessable.map(r => <Unassessed key={`${r.source}:${r.key}`} result={r} />)}</List>
            </Section>
            <Section title={t('advisor.host.proposals', 'Proposed fixes')} count={proposals.length}
                defaultExpanded={proposals.some(p => p.status === 'proposed')}>
                <AdvisorProposalList proposals={proposals} onChanged={load} hideHost />
            </Section>
            <Section title={t('advisor.host.notApplicable', 'Not applicable')} count={view.not_applicable.length}>
                <List dense>{view.not_applicable.map(r => <Unassessed key={`${r.source}:${r.key}`} result={r} />)}</List>
            </Section>
            <Section title={t('advisor.host.clean', 'Clean')} count={view.clean.length}>
                <List dense>
                    {view.clean.map(r => (
                        <ListItem key={`${r.source}:${r.key}`} divider>
                            <ListItemText primary={r.title ?? r.key} />
                        </ListItem>
                    ))}
                </List>
            </Section>
        </Box>
    );
};

export default HostAdvisorTab;
