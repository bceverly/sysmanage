// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

// Agent certificates (ROADMAP 25.10): whether agents must present their
// client certificate, and who is not ready yet.  The rollout is off ->
// optional -> enforced; enforcing while hosts are not presenting would cut
// them off, so the server refuses it with their count until confirmed.

import React, { useCallback, useEffect, useState } from 'react';
import {
    Alert, Box, Button, Card, CardContent, CircularProgress, Divider, FormControl,
    InputLabel, List, ListItem, ListItemText, MenuItem, Select, Typography,
} from '@mui/material';
import { useTranslation } from 'react-i18next';

import { certificateStatus } from './hostsColumns';
import {
    AgentCertificateMode, AgentCertificateSettings, agentCertificatesService,
} from '../Services/agentCertificates';

interface ApiError {
    response?: { status?: number; data?: { detail?: { code?: string; message?: string } | string } };
}

const detailOf = (err: unknown) => (err as ApiError)?.response?.data?.detail;

const AgentCertificatesCard: React.FC = () => {
    const { t } = useTranslation();
    const [data, setData] = useState<AgentCertificateSettings | null>(null);
    const [mode, setMode] = useState<AgentCertificateMode>('optional');
    const [error, setError] = useState<string | null>(null);
    const [confirm, setConfirm] = useState<string | null>(null);
    const [saving, setSaving] = useState(false);

    const load = useCallback(async () => {
        try {
            const settings = await agentCertificatesService.get();
            if (!settings?.fleet) throw new Error('unexpected response');
            setData(settings);
            setMode(settings.mode);
            setError(null);
        } catch {
            setError(t('agentCertificates.loadError', 'Could not load the agent certificate settings.'));
        }
    }, [t]);

    useEffect(() => { void load(); }, [load]);

    const save = async (force: boolean) => {
        setSaving(true);
        setError(null);
        try {
            const settings = await agentCertificatesService.setMode(mode, force);
            setData(settings);
            setMode(settings.mode);
            setConfirm(null);
        } catch (err) {
            const detail = detailOf(err);
            if (typeof detail === 'object' && detail?.code === 'hosts_not_presenting') {
                setConfirm(detail.message ?? '');
            } else {
                setError(t('agentCertificates.saveError', 'Could not save the agent certificate setting.'));
            }
        } finally {
            setSaving(false);
        }
    };

    if (!data) {
        return error ? <Alert severity="error">{error}</Alert> : <CircularProgress size={24} />;
    }

    const modeHelp: Record<AgentCertificateMode, string> = {
        off: t('agentCertificates.modeOffHelp', 'Client certificates are ignored. Agents connect with their host token alone.'),
        optional: t('agentCertificates.modeOptionalHelp', 'A certificate an agent presents must be valid for its host; an agent with none still connects on its host token.'),
        enforced: t('agentCertificates.modeEnforcedHelp', 'Every approved host must present a valid certificate. A host without a current one may still request one, and nothing else.'),
    };
    const { fleet } = data;

    return (
        <Card variant="outlined" sx={{ mb: 2 }}>
            <CardContent>
                <Typography variant="subtitle1" sx={{ fontWeight: 600 }}>
                    {t('agentCertificates.title', 'Agent certificates (mutual TLS)')}
                </Typography>
                <Divider sx={{ my: 1.5 }} />
                <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
                    {t('agentCertificates.intro', 'Each agent gets a client certificate for a key it generates itself, renews it before it expires, and presents it on every connection. Agents also pin this server, so a proxy or another server presenting a different certificate is refused.')}
                </Typography>
                {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}
                <Box sx={{ display: 'flex', gap: 2, alignItems: 'center', maxWidth: 480, mb: 1 }}>
                    <FormControl size="small" fullWidth>
                        <InputLabel id="agent-cert-mode">{t('agentCertificates.mode', 'Mode')}</InputLabel>
                        <Select labelId="agent-cert-mode" label={t('agentCertificates.mode', 'Mode')} value={mode}
                            onChange={e => { setMode(e.target.value as AgentCertificateMode); setConfirm(null); }}>
                            <MenuItem value="off">{t('agentCertificates.modeOff', 'Off')}</MenuItem>
                            <MenuItem value="optional">{t('agentCertificates.modeOptional', 'Optional')}</MenuItem>
                            <MenuItem value="enforced">{t('agentCertificates.modeEnforced', 'Enforced')}</MenuItem>
                        </Select>
                    </FormControl>
                    <Button variant="contained" disabled={saving || mode === data.mode} onClick={() => void save(false)}>
                        {t('common.save', 'Save')}
                    </Button>
                </Box>
                <Typography variant="caption" color="text.secondary" component="p" sx={{ mb: 2 }}>
                    {modeHelp[mode]}
                </Typography>
                {confirm !== null && (
                    <Alert severity="warning" sx={{ mb: 2 }} action={
                        <Button color="inherit" size="small" disabled={saving} onClick={() => void save(true)}>
                            {t('agentCertificates.enforceAnyway', 'Enforce anyway')}
                        </Button>
                    }>
                        {confirm}
                    </Alert>
                )}
                <Typography variant="body2">
                    {t('agentCertificates.fleet', '{{presenting}} of {{approved}} approved hosts present a valid certificate; {{expiring}} renewing, {{expired}} expired.', {
                        presenting: fleet.presenting, approved: fleet.approved,
                        expiring: fleet.expiring, expired: fleet.expired,
                    })}
                </Typography>
                {fleet.approved > 0 && fleet.presenting === 0 && (
                    <Alert severity="info" sx={{ mt: 1 }}>
                        {t('agentCertificates.noneYet', 'No host presents a certificate yet. Agents get one when they are updated; nginx asks for it once the server package has added its agent certificate settings (an upgrade does this when the SysManage CA exists).')}
                    </Alert>
                )}
                {fleet.not_ready.length > 0 && (
                    <List dense sx={{ mt: 1 }}>
                        {fleet.not_ready.map(host => (
                            <ListItem key={host.id} disableGutters>
                                <ListItemText primary={host.fqdn}
                                    secondary={certificateStatus(t, host.status)?.label ?? host.status} />
                            </ListItem>
                        ))}
                    </List>
                )}
            </CardContent>
        </Card>
    );
};

export default AgentCertificatesCard;
