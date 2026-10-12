// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

// The fleet NTP policy editor (Phase 23.3 S5b; the rules are Pro+).  Which
// NTP servers hosts should use -- for the fleet, a site or a tag -- whether
// to apply it or only report differences, and whether a clock that breaches
// its bounds is resynchronized automatically.

import React, { useCallback, useEffect, useState } from 'react';
import {
    Alert,
    Box,
    Button,
    Card,
    CardContent,
    Chip,
    FormControl,
    FormControlLabel,
    IconButton,
    InputLabel,
    MenuItem,
    Select,
    Stack,
    Switch,
    TextField,
    Typography,
} from '@mui/material';
import DeleteIcon from '@mui/icons-material/Delete';
import { useTranslation } from 'react-i18next';
import type { TFunction } from 'i18next';
import { errorCode } from '../../Services/machines';
import { hasPermission, SecurityRoles } from '../../Services/permissions';
import { clearNtpPolicy, getNtpPolicies, setNtpPolicy } from '../../Services/timeSync';
import type { NtpPolicy, PolicyScope } from '../../Services/timeSync';
import type { Named } from '../../hooks/useTimeSyncBounds';
import { policyErrorText } from './timeSyncLabels';

const scopeLabel = (t: TFunction, scope: PolicyScope): string => {
    switch (scope) {
        case 'fleet':
            return t('timeSync.policy.scope.fleet', 'Whole fleet');
        case 'site':
            return t('timeSync.boundsSource.site', 'Site');
        default:
            return t('timeSync.boundsSource.tag', 'Tag');
    }
};

const splitServers = (text: string): string[] =>
    text.split(/[\s,]+/).map(s => s.trim()).filter(Boolean);

const PolicyRow: React.FC<{
    policy: NtpPolicy;
    target: string;
    canEdit: boolean;
    onRemove: () => void;
}> = ({ policy, target, canEdit, onRemove }) => {
    const { t } = useTranslation();
    return (
        <Stack direction="row" spacing={1} alignItems="center" sx={{ flexWrap: 'wrap', rowGap: 0.5 }}>
            <Typography variant="body2" sx={{ minWidth: 160 }}>{target}</Typography>
            <Typography variant="body2" sx={{ fontFamily: 'monospace' }}>{policy.servers.join(', ')}</Typography>
            <Chip
                size="small"
                color={policy.enforce ? 'primary' : 'default'}
                label={policy.enforce
                    ? t('timeSync.policy.enforced', 'Applied')
                    : t('timeSync.policy.reportOnly', 'Report only')}
            />
            {policy.auto_resync && (
                <Chip size="small" label={t('timeSync.policy.autoResyncChip', 'Auto-resync')} />
            )}
            <IconButton
                size="small"
                aria-label={t('timeSync.policy.remove', 'Remove policy')}
                disabled={!canEdit}
                onClick={onRemove}
            >
                <DeleteIcon fontSize="small" />
            </IconButton>
        </Stack>
    );
};

interface Props {
    tags: Named[];
    sites: Named[];
}

const NtpPolicySettings: React.FC<Props> = ({ tags, sites }) => {
    const { t } = useTranslation();
    const [policies, setPolicies] = useState<NtpPolicy[] | null>(null);
    const [canEdit, setCanEdit] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [scope, setScope] = useState<PolicyScope>('fleet');
    const [ref, setRef] = useState('');
    const [servers, setServers] = useState('');
    const [enforce, setEnforce] = useState(false);
    const [autoResync, setAutoResync] = useState(false);

    const load = useCallback(async () => {
        try {
            setPolicies((await getNtpPolicies()).policies);
        } catch {
            setPolicies([]);
        }
    }, []);

    useEffect(() => {
        void load();
        void hasPermission(SecurityRoles.MANAGE_TIME_SYNC).then(setCanEdit).catch(() => setCanEdit(false));
    }, [load]);

    const targetName = (p: NtpPolicy): string => {
        if (p.scope_kind === 'fleet') {
            return scopeLabel(t, 'fleet');
        }
        const pool = p.scope_kind === 'tag' ? tags : sites;
        return `${scopeLabel(t, p.scope_kind)}: ${pool.find(x => x.id === p.scope_ref)?.name ?? p.scope_ref}`;
    };

    const save = async () => {
        setError(null);
        try {
            await setNtpPolicy({
                scope_kind: scope,
                scope_ref: scope === 'fleet' ? '' : ref,
                servers: splitServers(servers),
                enforce,
                auto_resync: autoResync,
            });
            setServers('');
            await load();
        } catch (e) {
            setError(policyErrorText(t, errorCode(e)));
        }
    };

    const remove = async (p: NtpPolicy) => {
        await clearNtpPolicy(p.scope_kind, p.scope_ref).catch(() => undefined);
        await load();
    };

    const scopes: PolicyScope[] = ['fleet', ...(sites.length ? ['site' as const] : []), 'tag'];
    const targets = scope === 'site' ? sites : tags;

    return (
        <Card sx={{ mt: 3 }}>
            <CardContent>
                <Typography variant="h6">{t('timeSync.policy.title', 'NTP policy')}</Typography>
                <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
                    {t('timeSync.policy.intro', "The NTP servers hosts should use, for the whole fleet or per site or tag. A tag's policy wins over a site's, a site's over the fleet's. Applied, SysManage writes the host's time service configuration and enables it at boot; report only, it shows the differences.")}
                </Typography>
                {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}
                <Stack spacing={1} sx={{ mb: 2 }}>
                    {(policies ?? []).length === 0 && (
                        <Typography variant="body2" color="text.secondary">
                            {t('timeSync.policy.none', 'No NTP policy: hosts keep their own time servers.')}
                        </Typography>
                    )}
                    {(policies ?? []).map(p => (
                        <PolicyRow key={p.id} policy={p} target={targetName(p)} canEdit={canEdit} onRemove={() => void remove(p)} />
                    ))}
                </Stack>
                <Stack direction={{ xs: 'column', md: 'row' }} spacing={2} alignItems="flex-start">
                    <FormControl size="small" sx={{ minWidth: 160 }}>
                        <InputLabel id="ntp-scope">{t('timeSync.bounds.scope', 'Applies to')}</InputLabel>
                        <Select
                            labelId="ntp-scope"
                            label={t('timeSync.bounds.scope', 'Applies to')}
                            value={scope}
                            disabled={!canEdit}
                            onChange={e => { setScope(e.target.value as PolicyScope); setRef(''); }}
                        >
                            {scopes.map(s => <MenuItem key={s} value={s}>{scopeLabel(t, s)}</MenuItem>)}
                        </Select>
                    </FormControl>
                    {scope !== 'fleet' && (
                        <FormControl size="small" sx={{ minWidth: 180 }}>
                            <InputLabel id="ntp-target">{scopeLabel(t, scope)}</InputLabel>
                            <Select
                                labelId="ntp-target"
                                label={scopeLabel(t, scope)}
                                value={ref}
                                disabled={!canEdit}
                                onChange={e => setRef(e.target.value)}
                            >
                                {targets.map(x => <MenuItem key={x.id} value={x.id}>{x.name}</MenuItem>)}
                            </Select>
                        </FormControl>
                    )}
                    <TextField
                        size="small"
                        label={t('timeSync.policy.servers', 'NTP servers')}
                        helperText={t('timeSync.policy.serversHelp', 'Host names or IP addresses, separated by spaces or commas')}
                        value={servers}
                        disabled={!canEdit}
                        onChange={e => setServers(e.target.value)}
                        sx={{ minWidth: 260 }}
                    />
                    <Box>
                        <FormControlLabel
                            control={<Switch checked={enforce} disabled={!canEdit} onChange={e => setEnforce(e.target.checked)} />}
                            label={t('timeSync.policy.enforce', 'Apply to hosts')}
                        />
                        <FormControlLabel
                            control={<Switch checked={autoResync} disabled={!canEdit} onChange={e => setAutoResync(e.target.checked)} />}
                            label={t('timeSync.policy.autoResync', 'Resynchronize clocks that breach their bounds')}
                        />
                    </Box>
                    <Button
                        variant="contained"
                        disabled={!canEdit || !servers.trim() || (scope !== 'fleet' && !ref)}
                        onClick={() => void save()}
                    >
                        {t('timeSync.bounds.save', 'Save')}
                    </Button>
                </Stack>
            </CardContent>
        </Card>
    );
};

export default NtpPolicySettings;
