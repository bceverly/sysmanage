// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

// The advisor dashboard (Phase 21.2 S7): the fleet's risk, the recommendation
// feed, proposed fixes and curated rule packs.
//
// The one rule this page must not break: what the advisor could NOT assess is
// shown -- counted in the fleet summary, a column in every feed row, with the
// reasons -- and never folded into "no findings".  Computing the honest
// answer is half the work; showing it is the other half (21.1 S6 shipped a
// correct `comparable: false` that was never rendered).

import React, { useCallback, useEffect, useState } from 'react';
import {
    Alert,
    Box,
    Button,
    Card,
    CardContent,
    Chip,
    CircularProgress,
    FormControl,
    Grid,
    InputLabel,
    MenuItem,
    Select,
    Stack,
    Tab,
    Tabs,
    Typography,
} from '@mui/material';
import RefreshIcon from '@mui/icons-material/Refresh';
import { useTranslation } from 'react-i18next';
import {
    advisorService,
    type AdvisorFeed,
    type AdvisorPack,
    type AdvisorProposal,
} from '../Services/advisorService';
import AdvisorScoreSummary from '../Components/Advisor/AdvisorScoreSummary';
import AdvisorRuleTable from '../Components/Advisor/AdvisorRuleTable';
import AdvisorProposalList from '../Components/Advisor/AdvisorProposalList';
import AdvisorPacks from '../Components/Advisor/AdvisorPacks';
import { lensLabel } from '../Components/Advisor/advisorLabels';

const LENSES = ['security', 'performance', 'availability', 'stability'];

const Totals: React.FC<{ feed: AdvisorFeed }> = ({ feed }) => {
    const { t } = useTranslation();
    return (
        <Card variant="outlined" sx={{ height: '100%' }}>
            <CardContent>
                <Typography variant="overline">{t('advisor.totals.title', 'Host and rule results')}</Typography>
                <Stack direction="row" spacing={1} sx={{ mt: 1, flexWrap: 'wrap', rowGap: 1 }}>
                    <Chip color="error" label={t('advisor.totals.findings', '{{count}} findings', { count: feed.totals.findings })} />
                    <Chip color="warning" variant="outlined"
                        label={t('advisor.totals.notAssessable', '{{count}} not assessable', { count: feed.totals.not_assessable })} />
                    <Chip label={t('advisor.totals.notApplicable', '{{count}} not applicable', { count: feed.totals.not_applicable })} />
                    <Chip color="success" variant="outlined"
                        label={t('advisor.totals.clean', '{{count}} clean', { count: feed.totals.clean })} />
                </Stack>
            </CardContent>
        </Card>
    );
};

const Advisor: React.FC = () => {
    const { t } = useTranslation();
    const [tab, setTab] = useState(0);
    const [lens, setLens] = useState('');
    const [feed, setFeed] = useState<AdvisorFeed | null>(null);
    const [proposals, setProposals] = useState<AdvisorProposal[]>([]);
    const [packs, setPacks] = useState<AdvisorPack[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(false);
    const [evaluating, setEvaluating] = useState(false);

    const load = useCallback(async () => {
        setError(false);
        try {
            const [f, p, k] = await Promise.all([
                advisorService.getFeed(lens || undefined),
                advisorService.listProposals(),
                advisorService.listPacks(),
            ]);
            setFeed(f);
            setProposals(p);
            setPacks(k);
        } catch {
            setError(true);
        } finally {
            setLoading(false);
        }
    }, [lens]);

    useEffect(() => { load(); }, [load]);

    const evaluate = async () => {
        setEvaluating(true);
        try {
            await advisorService.evaluate();
        } catch {
            setError(true);
        }
        setEvaluating(false);
        load();
    };

    const openProposals = proposals.filter(p => p.status === 'proposed').length;

    return (
        <Box sx={{ p: 2 }}>
            <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 2 }}>
                <Typography variant="h5">{t('advisor.title', 'Advisor')}</Typography>
                <Button startIcon={evaluating ? <CircularProgress size={16} /> : <RefreshIcon />}
                    onClick={evaluate} disabled={evaluating}>
                    {t('advisor.evaluateNow', 'Evaluate now')}
                </Button>
            </Stack>
            {error && <Alert severity="error" sx={{ mb: 2 }}>{t('advisor.loadFailed', 'The advisor could not be loaded.')}</Alert>}
            {loading && <CircularProgress />}
            {feed && (
                <Grid container spacing={2} sx={{ mb: 2 }}>
                    <Grid size={{ xs: 12, md: 6 }}><AdvisorScoreSummary fleet={feed.fleet} /></Grid>
                    <Grid size={{ xs: 12, md: 6 }}><Totals feed={feed} /></Grid>
                </Grid>
            )}
            <Tabs value={tab} onChange={(_, v) => setTab(v)} sx={{ mb: 1 }}>
                <Tab label={t('advisor.tabs.recommendations', 'Recommendations')} />
                <Tab label={t('advisor.tabs.proposals', 'Proposed fixes ({{count}})', { count: openProposals })} />
                <Tab label={t('advisor.tabs.packs', 'Rule packs')} />
            </Tabs>
            {tab === 0 && feed && (
                <>
                    <FormControl size="small" sx={{ minWidth: 180, mb: 1 }}>
                        <InputLabel id="advisor-lens" shrink>{t('advisor.feed.lens', 'Lens')}</InputLabel>
                        <Select labelId="advisor-lens" value={lens} label={t('advisor.feed.lens', 'Lens')}
                            displayEmpty notched onChange={e => setLens(e.target.value)}>
                            <MenuItem value="">{t('advisor.feed.allLenses', 'All')}</MenuItem>
                            {LENSES.map(l => <MenuItem key={l} value={l}>{lensLabel(t, l)}</MenuItem>)}
                        </Select>
                    </FormControl>
                    <AdvisorRuleTable rules={feed.rules} />
                </>
            )}
            {tab === 1 && <AdvisorProposalList proposals={proposals} onChanged={load} />}
            {tab === 2 && <AdvisorPacks packs={packs} onChanged={load} />}
        </Box>
    );
};

export default Advisor;
