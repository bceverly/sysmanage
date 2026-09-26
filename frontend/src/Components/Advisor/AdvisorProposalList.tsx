// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

// Fixes the advisor PROPOSES.  Nothing here runs without an operator: approve
// opens a confirmation that shows exactly what would be applied -- the
// packages, what was skipped, and the playbook itself -- and an approved fix
// still waits for the host's maintenance window, so "approved" is never
// shown as "applied" until its run comes back.

import React, { useState } from 'react';
import {
    Alert,
    Box,
    Button,
    Chip,
    Dialog,
    DialogActions,
    DialogContent,
    DialogTitle,
    Table,
    TableBody,
    TableCell,
    TableHead,
    TableRow,
    Typography,
} from '@mui/material';
import { useTranslation } from 'react-i18next';
import { advisorService, type AdvisorProposal } from '../../Services/advisorService';
import { proposalReasonLabel, proposalStatusLabel } from './advisorLabels';

interface Props {
    proposals: AdvisorProposal[];
    onChanged: () => void;
    /** Hide the host column on a single host's tab. */
    hideHost?: boolean;
}

const RunState: React.FC<{ proposal: AdvisorProposal }> = ({ proposal }) => {
    const { t } = useTranslation();
    if (proposal.status !== 'approved') {
        return <>{proposalReasonLabel(t, proposal.reason)}</>;
    }
    if (proposal.run === null) {
        return <>{t('advisor.proposal.queued', 'Queued -- waiting for the host (and its maintenance window)')}</>;
    }
    return proposal.run.success
        ? <>{t('advisor.proposal.ranOk', 'Applied successfully')}</>
        : <>{t('advisor.proposal.ranFailed', 'Applied, but the run failed')}</>;
};

const FixPreview: React.FC<{ proposal: AdvisorProposal }> = ({ proposal }) => {
    const { t } = useTranslation();
    if (proposal.kind === 'profile') {
        return (
            <Typography>
                {t('advisor.proposal.appliesProfile', 'Applies the configuration profile "{{name}}".', {
                    name: proposal.profile_name,
                })}
            </Typography>
        );
    }
    return (
        <>
            <Typography gutterBottom>
                {t('advisor.proposal.upgrades', 'Upgrades {{count}} packages:', { count: proposal.packages.length })}
            </Typography>
            <Typography variant="body2" sx={{ fontFamily: 'monospace', mb: 1 }}>
                {proposal.packages.join(', ')}
            </Typography>
            {proposal.skipped > 0 && (
                <Alert severity="info" sx={{ mb: 1 }}>
                    {t(
                        'advisor.proposal.skipped',
                        '{{count}} matched items were left out: not packages this fix may upgrade (for example firmware or snaps).',
                        { count: proposal.skipped },
                    )}
                </Alert>
            )}
            <Box component="pre" sx={{ fontSize: 12, bgcolor: 'action.hover', p: 1, overflow: 'auto', maxHeight: 240 }}>
                {proposal.content}
            </Box>
        </>
    );
};

const AdvisorProposalList: React.FC<Props> = ({ proposals, onChanged, hideHost }) => {
    const { t } = useTranslation();
    const [pending, setPending] = useState<AdvisorProposal | null>(null);
    const [error, setError] = useState<string | null>(null);

    const decide = async (proposal: AdvisorProposal, approve: boolean) => {
        setError(null);
        try {
            if (approve) {
                await advisorService.approveProposal(proposal.id);
            } else {
                await advisorService.rejectProposal(proposal.id);
            }
        } catch (err: unknown) {
            const reason = (err as { response?: { data?: { detail?: { reason?: string } } } })
                ?.response?.data?.detail?.reason ?? null;
            setError(reason
                ? proposalReasonLabel(t, reason)
                : t('advisor.proposal.decideFailed', 'The decision could not be recorded.'));
        }
        setPending(null);
        onChanged();
    };

    if (proposals.length === 0) {
        return <Typography sx={{ p: 2 }}>{t('advisor.proposal.none', 'No proposed fixes.')}</Typography>;
    }
    return (
        <>
            {error && <Alert severity="error" sx={{ mb: 1 }}>{error}</Alert>}
            <Table size="small">
                <TableHead>
                    <TableRow>
                        {!hideHost && <TableCell>{t('advisor.proposal.host', 'Host')}</TableCell>}
                        <TableCell>{t('advisor.proposal.rule', 'Rule')}</TableCell>
                        <TableCell>{t('advisor.proposal.fix', 'Fix')}</TableCell>
                        <TableCell>{t('advisor.proposal.statusColumn', 'Status')}</TableCell>
                        <TableCell>{t('advisor.proposal.detail', 'Detail')}</TableCell>
                        <TableCell />
                    </TableRow>
                </TableHead>
                <TableBody>
                    {proposals.map(p => (
                        <TableRow key={p.id}>
                            {!hideHost && <TableCell>{p.fqdn}</TableCell>}
                            <TableCell>{p.key}</TableCell>
                            <TableCell>
                                {p.kind === 'profile'
                                    ? p.profile_name
                                    : t('advisor.proposal.packageCount', '{{count}} packages', { count: p.packages.length })}
                            </TableCell>
                            <TableCell><Chip size="small" label={proposalStatusLabel(t, p.status)} /></TableCell>
                            <TableCell><RunState proposal={p} /></TableCell>
                            <TableCell align="right">
                                {p.status === 'proposed' && (
                                    <Button size="small" onClick={() => setPending(p)}>
                                        {t('advisor.proposal.review', 'Review')}
                                    </Button>
                                )}
                            </TableCell>
                        </TableRow>
                    ))}
                </TableBody>
            </Table>
            <Dialog open={pending !== null} onClose={() => setPending(null)} maxWidth="md" fullWidth>
                <DialogTitle>
                    {t('advisor.proposal.reviewTitle', 'Review fix for {{rule}} on {{host}}', {
                        rule: pending?.key,
                        host: pending?.fqdn,
                    })}
                </DialogTitle>
                <DialogContent>
                    {pending && <FixPreview proposal={pending} />}
                    <Alert severity="warning" sx={{ mt: 1 }}>
                        {t(
                            'advisor.proposal.approveWarning',
                            'Approving applies this change to the host with administrative rights, at its next maintenance window (immediately if it has none).',
                        )}
                    </Alert>
                </DialogContent>
                <DialogActions>
                    <Button onClick={() => setPending(null)}>{t('common.cancel', 'Cancel')}</Button>
                    <Button color="inherit" onClick={() => pending && decide(pending, false)}>
                        {t('advisor.proposal.reject', 'Reject')}
                    </Button>
                    <Button variant="contained" onClick={() => pending && decide(pending, true)}>
                        {t('advisor.proposal.approve', 'Approve')}
                    </Button>
                </DialogActions>
            </Dialog>
        </>
    );
};

export default AdvisorProposalList;
