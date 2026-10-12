// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

// Clock offset bounds (Phase 23.3 S4).  A warning and a critical offset for
// the whole server, overridable per tenant, site and tag -- tighter for domain
// controllers and signing hosts, looser for lab machines.  Entered in seconds;
// stored in milliseconds.

import React, { useEffect, useState } from 'react';
import {
    Alert,
    Box,
    Button,
    Card,
    CardContent,
    CircularProgress,
    FormControl,
    IconButton,
    InputLabel,
    MenuItem,
    Select,
    Stack,
    Table,
    TableBody,
    TableCell,
    TableHead,
    TableRow,
    TextField,
    Typography,
} from '@mui/material';
import DeleteIcon from '@mui/icons-material/Delete';
import { useTranslation } from 'react-i18next';
import type { TFunction } from 'i18next';
import { useTimeSyncBounds } from '../../hooks/useTimeSyncBounds';
import type { Named } from '../../hooks/useTimeSyncBounds';
import type { BoundOverride, OverrideScope } from '../../Services/timeSync';
import { boundsErrorText, formatOffset, sourceLabel } from './timeSyncLabels';
import NtpPolicySettings from './NtpPolicySettings';
import { useModuleLicensed } from '../../hooks/useModuleLicensed';

const toSeconds = (ms: number): string => String(ms / 1000);
const toMs = (seconds: string): number => Math.round(Number(seconds) * 1000 * 1000) / 1000;

interface PairProps {
    warning: string;
    critical: string;
    onWarning: (v: string) => void;
    onCritical: (v: string) => void;
    disabled: boolean;
}

const BoundPair: React.FC<PairProps> = ({ warning, critical, onWarning, onCritical, disabled }) => {
    const { t } = useTranslation();
    return (
        <>
            <TextField
                size="small"
                type="number"
                label={t('timeSync.bounds.warning', 'Warning (seconds)')}
                value={warning}
                onChange={e => onWarning(e.target.value)}
                disabled={disabled}
                slotProps={{ htmlInput: { min: 0.001, step: 0.1 } }}
            />
            <TextField
                size="small"
                type="number"
                label={t('timeSync.bounds.critical', 'Critical (seconds)')}
                value={critical}
                onChange={e => onCritical(e.target.value)}
                disabled={disabled}
                slotProps={{ htmlInput: { min: 0.001, step: 0.1 } }}
            />
        </>
    );
};

const scopeName = (t: TFunction, o: BoundOverride, tags: Named[], sites: Named[]): string => {
    if (o.scope_kind === 'tenant') {
        return t('timeSync.bounds.thisTenant', 'This tenant');
    }
    const pool = o.scope_kind === 'tag' ? tags : sites;
    return pool.find(p => p.id === o.scope_ref)?.name ?? o.scope_ref;
};

const ServerBounds: React.FC<{ state: ReturnType<typeof useTimeSyncBounds> }> = ({ state }) => {
    const { t } = useTranslation();
    const server = state.config?.server;
    const [warning, setWarning] = useState('');
    const [critical, setCritical] = useState('');
    useEffect(() => {
        if (server) {
            setWarning(toSeconds(server.warning_ms));
            setCritical(toSeconds(server.critical_ms));
        }
    }, [server]);
    if (!server) {
        return null;
    }
    return (
        <Box sx={{ mb: 3 }}>
            <Typography variant="subtitle1">{t('timeSync.bounds.serverTitle', 'Server-wide bounds')}</Typography>
            <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
                {t('timeSync.bounds.serverSource', 'Currently: {{source}}.', { source: sourceLabel(t, server.source) })}
            </Typography>
            <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2} alignItems="flex-start">
                <BoundPair
                    warning={warning}
                    critical={critical}
                    onWarning={setWarning}
                    onCritical={setCritical}
                    disabled={!state.canEdit}
                />
                <Button
                    variant="contained"
                    disabled={!state.canEdit}
                    onClick={() => void state.saveServer(toMs(warning), toMs(critical))}
                >
                    {t('timeSync.bounds.save', 'Save')}
                </Button>
            </Stack>
        </Box>
    );
};

const AddOverride: React.FC<{ state: ReturnType<typeof useTimeSyncBounds> }> = ({ state }) => {
    const { t } = useTranslation();
    const scopes: OverrideScope[] = [
        ...(state.config?.multitenancy ? ['tenant' as const] : []),
        ...(state.sites.length ? ['site' as const] : []),
        'tag',
    ];
    const [scope, setScope] = useState<OverrideScope>('tag');
    const [ref, setRef] = useState('');
    const [warning, setWarning] = useState('0.5');
    const [critical, setCritical] = useState('2');
    const targets = scope === 'site' ? state.sites : state.tags;

    const add = async () => {
        if (await state.saveOverride(scope, scope === 'tenant' ? '' : ref, toMs(warning), toMs(critical))) {
            setRef('');
        }
    };

    return (
        <Stack direction={{ xs: 'column', md: 'row' }} spacing={2} alignItems="flex-start" sx={{ mt: 2 }}>
            <FormControl size="small" sx={{ minWidth: 140 }}>
                <InputLabel id="bound-scope">{t('timeSync.bounds.scope', 'Applies to')}</InputLabel>
                <Select
                    labelId="bound-scope"
                    label={t('timeSync.bounds.scope', 'Applies to')}
                    value={scope}
                    onChange={e => { setScope(e.target.value as OverrideScope); setRef(''); }}
                    disabled={!state.canEdit}
                >
                    {scopes.map(s => <MenuItem key={s} value={s}>{sourceLabel(t, s)}</MenuItem>)}
                </Select>
            </FormControl>
            {scope !== 'tenant' && (
                <FormControl size="small" sx={{ minWidth: 200 }}>
                    <InputLabel id="bound-target">{sourceLabel(t, scope)}</InputLabel>
                    <Select
                        labelId="bound-target"
                        label={sourceLabel(t, scope)}
                        value={ref}
                        onChange={e => setRef(e.target.value)}
                        disabled={!state.canEdit}
                    >
                        {targets.map(p => <MenuItem key={p.id} value={p.id}>{p.name}</MenuItem>)}
                    </Select>
                </FormControl>
            )}
            <BoundPair
                warning={warning}
                critical={critical}
                onWarning={setWarning}
                onCritical={setCritical}
                disabled={!state.canEdit}
            />
            <Button
                variant="outlined"
                disabled={!state.canEdit || (scope !== 'tenant' && !ref)}
                onClick={() => void add()}
            >
                {t('timeSync.bounds.add', 'Add override')}
            </Button>
        </Stack>
    );
};

const BoundsCard: React.FC<{ state: ReturnType<typeof useTimeSyncBounds> }> = ({ state }) => {
    const { t } = useTranslation();

    if (state.loadFailed) {
        return <Alert severity="error">{t('timeSync.bounds.loadError', 'Could not load the clock bounds.')}</Alert>;
    }
    if (!state.config) {
        return <CircularProgress size={24} />;
    }
    return (
        <Card>
            <CardContent>
                <Typography variant="h6">{t('timeSync.bounds.title', 'Clock offset bounds')}</Typography>
                <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
                    {t('timeSync.bounds.intro', "A host whose clock is off by the warning bound or more is shown as a warning; by the critical bound or more, as critical. The most specific bounds apply: a tag's, then a site's, then the tenant's, then the server-wide ones. A host with several tags is held to the tightest.")}
                </Typography>
                {!state.canEdit && (
                    <Alert severity="info" sx={{ mb: 2 }}>
                        {t('timeSync.bounds.readOnly', 'You can view the bounds, but changing them requires the Manage Time Sync role.')}
                    </Alert>
                )}
                {state.error && <Alert severity="error" sx={{ mb: 2 }}>{boundsErrorText(t, state.error)}</Alert>}
                <ServerBounds state={state} />
                <Typography variant="subtitle1">{t('timeSync.bounds.overridesTitle', 'Overrides')}</Typography>
                {state.config.overrides.length === 0 ? (
                    <Typography variant="body2" color="text.secondary">
                        {t('timeSync.bounds.noOverrides', 'No overrides: every host uses the server-wide bounds.')}
                    </Typography>
                ) : (
                    <Table size="small">
                        <TableHead>
                            <TableRow>
                                <TableCell>{t('timeSync.bounds.scope', 'Applies to')}</TableCell>
                                <TableCell>{t('timeSync.bounds.warningShort', 'Warning')}</TableCell>
                                <TableCell>{t('timeSync.bounds.criticalShort', 'Critical')}</TableCell>
                                <TableCell />
                            </TableRow>
                        </TableHead>
                        <TableBody>
                            {state.config.overrides.map(o => (
                                <TableRow key={`${o.scope_kind}:${o.scope_ref}`}>
                                    <TableCell>{`${sourceLabel(t, o.scope_kind)}: ${scopeName(t, o, state.tags, state.sites)}`}</TableCell>
                                    <TableCell>{formatOffset(t, o.warning_ms).replace('+', '')}</TableCell>
                                    <TableCell>{formatOffset(t, o.critical_ms).replace('+', '')}</TableCell>
                                    <TableCell align="right">
                                        <IconButton
                                            aria-label={t('timeSync.bounds.remove', 'Remove override')}
                                            disabled={!state.canEdit}
                                            onClick={() => void state.removeOverride(o.scope_kind, o.scope_ref)}
                                        >
                                            <DeleteIcon />
                                        </IconButton>
                                    </TableCell>
                                </TableRow>
                            ))}
                        </TableBody>
                    </Table>
                )}
                <AddOverride state={state} />
            </CardContent>
        </Card>
    );
};

const TimeSyncBoundsSettings: React.FC = () => <BoundsCard state={useTimeSyncBounds()} />;

/** Settings > Time Sync: the bounds, and (licensed) the fleet NTP policy. */
export const TimeSyncSettings: React.FC = () => {
    const state = useTimeSyncBounds();
    const policyLicensed = useModuleLicensed('config_management_engine');
    return (
        <>
            <BoundsCard state={state} />
            {policyLicensed && <NtpPolicySettings tags={state.tags} sites={state.sites} />}
        </>
    );
};

export default TimeSyncBoundsSettings;
