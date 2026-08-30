// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

import React, { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import Accordion from '@mui/material/Accordion';
import AccordionDetails from '@mui/material/AccordionDetails';
import AccordionSummary from '@mui/material/AccordionSummary';
import Alert from '@mui/material/Alert';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Chip from '@mui/material/Chip';
import CircularProgress from '@mui/material/CircularProgress';
import FormControl from '@mui/material/FormControl';
import InputLabel from '@mui/material/InputLabel';
import MenuItem from '@mui/material/MenuItem';
import Select from '@mui/material/Select';
import Stack from '@mui/material/Stack';
import Table from '@mui/material/Table';
import TableBody from '@mui/material/TableBody';
import TableCell from '@mui/material/TableCell';
import TableHead from '@mui/material/TableHead';
import TableRow from '@mui/material/TableRow';
import Typography from '@mui/material/Typography';
import CompareArrowsIcon from '@mui/icons-material/CompareArrows';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';

import { doGetHosts } from '../Services/hosts';
import {
    BaselineCategoryResult,
    BaselineDiff,
    getBaselineCategories,
    getBaselineDiff,
} from '../Services/configManagementService';

/** Pull the server's explanation out of an axios error, or fall back. */
const messageFrom = (err: unknown, fallback: string): string => {
    const detail = (err as { response?: { data?: { detail?: unknown } } })?.response
        ?.data?.detail;
    return typeof detail === 'string' && detail ? detail : fallback;
};

export interface BaselineDiffPanelProps {
    /** The host being examined — the one an operator is trying to fix. */
    hostId: string;
    /**
     * Candidate reference hosts. Optional: the panel loads them itself when
     * omitted, so a caller does not have to know where hosts come from just to
     * embed this. Supplied by callers that already hold the list.
     */
    hosts?: { id: string; fqdn: string }[];
}

/**
 * Compare this host against a reference ("golden") host.
 *
 * The other kind of drift: the drift dashboard answers "does this host match
 * its assigned profile", this answers "does this host match THAT host" — what
 * an operator reaches for when there is no profile yet and staging works while
 * production does not.
 */
const BaselineDiffPanel: React.FC<BaselineDiffPanelProps> = ({ hostId, hosts }) => {
    const { t } = useTranslation();
    const [categories, setCategories] = useState<string[]>([]);
    const [loadedHosts, setLoadedHosts] = useState<{ id: string; fqdn: string }[]>([]);
    const [reference, setReference] = useState('');
    const [diff, setDiff] = useState<BaselineDiff | null>(null);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
        let cancelled = false;
        // Served by the API so the picker cannot offer a category the server
        // would refuse, and a new one appears without a frontend release.
        getBaselineCategories()
            .then((names) => {
                if (!cancelled) setCategories(names);
            })
            .catch(() => {
                // A failure here only costs the category labels; the
                // comparison itself still works against every category.
                if (!cancelled) setCategories([]);
            });
        return () => {
            cancelled = true;
        };
    }, []);

    useEffect(() => {
        if (hosts) return undefined;
        let cancelled = false;
        // Every APPROVED host, not only the ones whose agent is connected
        // right now. This comparison reads stored inventory and never talks to
        // an agent, so liveness is irrelevant -- and filtering on it would
        // empty the picker in exactly the situation it exists for: production
        // is broken, quite possibly offline, and the operator wants to know
        // how it differs from a host that works.
        doGetHosts()
            .then((rows) => {
                if (!cancelled) {
                    setLoadedHosts(
                        rows
                            .filter((h) => h.approval_status === 'approved')
                            .map((h) => ({ id: String(h.id), fqdn: h.fqdn })),
                    );
                }
            })
            .catch(() => {
                // Only costs the picker; the surrounding page is unaffected,
                // so this must not surface as an error there.
                if (!cancelled) setLoadedHosts([]);
            });
        return () => {
            cancelled = true;
        };
    }, [hosts]);

    const runComparison = useCallback(async () => {
        if (!reference) return;
        setLoading(true);
        setError(null);
        setDiff(null);
        try {
            setDiff(await getBaselineDiff(hostId, reference));
        } catch (err) {
            setError(messageFrom(err, t('baselineDiff.error', 'Comparison failed')));
        } finally {
            setLoading(false);
        }
    }, [hostId, reference, t]);

    const others = (hosts ?? loadedHosts).filter((h) => h.id !== hostId);

    /**
     * A translated label for a comparison category.
     *
     * Written out rather than looked up as t(`baselineDiff.category.${name}`),
     * because the i18n scanner cannot see an interpolated key: the eight labels
     * would never be extracted and every locale would silently fall back to the
     * raw English identifier. An unknown category (one the server gained but
     * this build has no label for) degrades to its identifier, which is still
     * readable.
     */
    const categoryLabel = (name: string): string => {
        switch (name) {
            case 'packages':
                return t('baselineDiff.category.packages', 'Packages');
            case 'repositories':
                return t('baselineDiff.category.repositories', 'Repositories');
            case 'users':
                return t('baselineDiff.category.users', 'Users');
            case 'groups':
                return t('baselineDiff.category.groups', 'Groups');
            case 'interfaces':
                return t('baselineDiff.category.interfaces', 'Network interfaces');
            case 'storage':
                return t('baselineDiff.category.storage', 'Storage');
            case 'certificates':
                return t('baselineDiff.category.certificates', 'Certificates');
            case 'firewall':
                return t('baselineDiff.category.firewall', 'Firewall');
            default:
                return name;
        }
    };

    const renderCategory = (name: string, result: BaselineCategoryResult) => {
        const { missing, extra, different, counts, truncated } = result;
        const total = counts.missing + counts.extra + counts.different;
        return (
            <Accordion key={name} disableGutters>
                <AccordionSummary expandIcon={<ExpandMoreIcon />}>
                    <Stack direction="row" spacing={1} alignItems="center" sx={{ width: '100%' }}>
                        <Typography sx={{ flexGrow: 1, textTransform: 'capitalize' }}>
                            {categoryLabel(name)}
                        </Typography>
                        {total === 0 ? (
                            <Chip
                                size="small"
                                color="success"
                                label={t('baselineDiff.matches', 'Matches')}
                            />
                        ) : (
                            <>
                                {counts.missing > 0 && (
                                    <Chip
                                        size="small"
                                        color="warning"
                                        label={t('baselineDiff.missingCount', {
                                            defaultValue: '{{count}} missing',
                                            count: counts.missing,
                                        })}
                                    />
                                )}
                                {counts.extra > 0 && (
                                    <Chip
                                        size="small"
                                        color="info"
                                        label={t('baselineDiff.extraCount', {
                                            defaultValue: '{{count}} only here',
                                            count: counts.extra,
                                        })}
                                    />
                                )}
                                {counts.different > 0 && (
                                    <Chip
                                        size="small"
                                        color="error"
                                        label={t('baselineDiff.differentCount', {
                                            defaultValue: '{{count}} different',
                                            count: counts.different,
                                        })}
                                    />
                                )}
                            </>
                        )}
                    </Stack>
                </AccordionSummary>
                <AccordionDetails>
                    {truncated && (
                        <Alert severity="info" sx={{ mb: 2 }}>
                            {t(
                                'baselineDiff.truncated',
                                'Only the first entries are listed; the counts above are exact.',
                            )}
                        </Alert>
                    )}
                    {different.length > 0 && (
                        <>
                            <Typography variant="subtitle2" sx={{ mt: 1 }}>
                                {t('baselineDiff.differentTitle', 'Present on both, but different')}
                            </Typography>
                            <Table size="small">
                                <TableHead>
                                    <TableRow>
                                        <TableCell>{t('baselineDiff.name', 'Name')}</TableCell>
                                        <TableCell>{t('baselineDiff.field', 'Field')}</TableCell>
                                        <TableCell>
                                            {t('baselineDiff.reference', 'Reference')}
                                        </TableCell>
                                        <TableCell>{t('baselineDiff.thisHost', 'This host')}</TableCell>
                                    </TableRow>
                                </TableHead>
                                <TableBody>
                                    {different.flatMap((item) =>
                                        Object.entries(item.fields).map(([field, delta]) => (
                                            <TableRow key={`${item.name}-${field}`}>
                                                <TableCell>{item.name}</TableCell>
                                                <TableCell>{field}</TableCell>
                                                <TableCell>{delta.reference ?? '—'}</TableCell>
                                                <TableCell>{delta.target ?? '—'}</TableCell>
                                            </TableRow>
                                        )),
                                    )}
                                </TableBody>
                            </Table>
                        </>
                    )}
                    {missing.length > 0 && (
                        <>
                            <Typography variant="subtitle2" sx={{ mt: 2 }}>
                                {t('baselineDiff.missingTitle', 'On the reference, not on this host')}
                            </Typography>
                            <Typography variant="body2" color="text.secondary">
                                {missing.map((item) => item.name).join(', ')}
                            </Typography>
                        </>
                    )}
                    {extra.length > 0 && (
                        <>
                            <Typography variant="subtitle2" sx={{ mt: 2 }}>
                                {t('baselineDiff.extraTitle', 'On this host, not on the reference')}
                            </Typography>
                            <Typography variant="body2" color="text.secondary">
                                {extra.map((item) => item.name).join(', ')}
                            </Typography>
                        </>
                    )}
                    {total === 0 && (
                        <Typography variant="body2" color="text.secondary">
                            {t('baselineDiff.categoryMatches', 'This category matches the reference host.')}
                        </Typography>
                    )}
                </AccordionDetails>
            </Accordion>
        );
    };

    return (
        <Box>
            <Typography variant="h6" gutterBottom>
                {t('baselineDiff.title', 'Compare to a reference host')}
            </Typography>
            <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
                {t(
                    'baselineDiff.description',
                    'Compare this host against a known-good host across the inventory already collected. Useful when there is no profile yet and one host works while another does not.',
                )}
            </Typography>

            <Stack direction="row" spacing={2} alignItems="center" sx={{ mb: 2 }}>
                <FormControl size="small" sx={{ minWidth: 260 }}>
                    <InputLabel id="baseline-reference-label">
                        {t('baselineDiff.referenceHost', 'Reference host')}
                    </InputLabel>
                    <Select
                        labelId="baseline-reference-label"
                        value={reference}
                        label={t('baselineDiff.referenceHost', 'Reference host')}
                        onChange={(event) => setReference(event.target.value)}
                        inputProps={{
                            'aria-label': t('baselineDiff.referenceHost', 'Reference host'),
                        }}
                    >
                        {others.map((host) => (
                            <MenuItem key={host.id} value={host.id}>
                                {host.fqdn}
                            </MenuItem>
                        ))}
                    </Select>
                </FormControl>
                <Button
                    variant="contained"
                    startIcon={<CompareArrowsIcon />}
                    disabled={!reference || loading}
                    onClick={runComparison}
                >
                    {t('baselineDiff.compare', 'Compare')}
                </Button>
                {loading && <CircularProgress size={22} />}
            </Stack>

            {others.length === 0 && (
                <Alert severity="info">
                    {t(
                        'baselineDiff.noOtherHosts',
                        'There is no other host to compare against yet.',
                    )}
                </Alert>
            )}

            {error && (
                <Alert severity="error" sx={{ mb: 2 }}>
                    {error}
                </Alert>
            )}

            {diff && (
                <>
                    <Alert severity={diff.identical ? 'success' : 'warning'} sx={{ mb: 2 }}>
                        {diff.identical
                            ? t('baselineDiff.identical', {
                                  defaultValue:
                                      'This host matches {{reference}} across every category compared.',
                                  reference: diff.reference_fqdn ?? '',
                              })
                            : t('baselineDiff.summary', {
                                  defaultValue:
                                      '{{count}} difference(s) from {{reference}}.',
                                  count: diff.total_differences,
                                  reference: diff.reference_fqdn ?? '',
                              })}
                    </Alert>
                    {categories
                        .filter((name) => diff.categories[name])
                        .map((name) => renderCategory(name, diff.categories[name]))}
                </>
            )}
        </Box>
    );
};

export default BaselineDiffPanel;
