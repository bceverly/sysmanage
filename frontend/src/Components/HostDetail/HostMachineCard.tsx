// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

// The "Machine" card (Phase 23.2).  A host is one operating system; a machine
// is the hardware under it, shared by every OS on a multi-boot machine.  The
// asset tag belongs to the machine, so it is shown and edited here.

import React, { useCallback, useEffect, useState } from 'react';
import {
    Alert,
    AlertTitle,
    Box,
    Button,
    Card,
    CardContent,
    Chip,
    CircularProgress,
    Grid,
    Link,
    List,
    ListItem,
    Stack,
    TextField,
    Typography,
} from '@mui/material';
import ComputerIcon from '@mui/icons-material/Computer';
import { Link as RouterLink } from 'react-router';
import { useTranslation } from 'react-i18next';
import type { TFunction } from 'i18next';
import {
    checkAssetTag,
    errorCode,
    getHostMachine,
    resolveMachineConflict,
    setMachineAssetTag,
} from '../../Services/machines';
import type {
    HostBrief,
    HostMachine,
    IdentitySourceStatus,
    MachineSummary,
} from '../../Services/machines';
import { hasPermission, SecurityRoles } from '../../Services/permissions';

const CHECK_DEBOUNCE_MS = 300;

/** Translated text for a tag refusal reason (entry check or save). */
export const tagReasonText = (t: TFunction, reason: string): string => {
    switch (reason) {
        case 'empty':
            return t('machine.tagReason.empty', 'Enter an asset tag.');
        case 'too_long':
            return t('machine.tagReason.tooLong', 'The asset tag is too long.');
        case 'bad_characters':
            return t('machine.tagReason.badCharacters', 'The asset tag contains characters that are not allowed.');
        case 'does_not_match_scheme':
            return t('machine.tagReason.doesNotMatchScheme', 'The asset tag does not match the asset tag scheme.');
        case 'scheme_timeout':
            return t('machine.tagReason.schemeTimeout', 'The asset tag scheme took too long to check this tag.');
        case 'duplicate':
            return t('machine.tagReason.duplicate', 'Another machine already has this asset tag.');
        default:
            return t('machine.tagReason.unknown', 'The asset tag was refused ({{code}}).', { code: reason });
    }
};

type NoMachineReason = 'not_reported' | 'placeholder' | 'needs_sudo_rule' | 'unprivileged' | 'failed' | 'absent' | 'unknown';

/** Why the host has no machine, from the per-source identity status. */
export const noMachineReason = (identity: HostMachine['identity']): NoMachineReason => {
    const statuses = Object.values(identity.status).filter(Boolean);
    if (!identity.reported_at && statuses.length === 0) {
        return 'not_reported';
    }
    const order: IdentitySourceStatus[] = ['placeholder', 'needs_sudo_rule', 'unprivileged', 'failed'];
    const found = order.find((s) => statuses.includes(s));
    if (found) {
        return found as NoMachineReason;
    }
    if (statuses.length > 0 && statuses.every((s) => s === 'absent')) {
        return 'absent';
    }
    return 'unknown';
};

const noMachineText = (t: TFunction, reason: NoMachineReason): string => {
    switch (reason) {
        case 'not_reported':
            return t('machine.noMachine.notReported', 'The agent has not reported this host\'s hardware identity yet.');
        case 'placeholder':
            return t('machine.noMachine.placeholder', 'The firmware on this hardware ships a placeholder UUID, so it cannot be told apart from other machines.');
        case 'needs_sudo_rule':
            // The agent runs unprivileged and its installed sudo rules predate
            // the identity reads (an older agent package) -- not a host
            // without privilege, which is what the old text claimed.
            return t('machine.noMachine.needsSudoRule', 'The agent\'s sudo rules do not allow reading the hardware identity. Upgrade the agent package to install the current rules.');
        case 'unprivileged':
            return t('machine.noMachine.unprivileged', 'The agent is not running as root and cannot use sudo, so it cannot read the hardware identity on this OS.');
        case 'failed':
            return t('machine.noMachine.failed', 'The agent tried to read the hardware identity but the read failed.');
        case 'absent':
            return t('machine.noMachine.absent', 'This hardware does not expose a system UUID or serial number.');
        default:
            return t('machine.noMachine.unknown', 'This host is not linked to a machine yet.');
    }
};

const usePermission = (role: string): boolean => {
    const [allowed, setAllowed] = useState(false);
    useEffect(() => {
        let live = true;
        hasPermission(role)
            .then((ok) => { if (live) setAllowed(ok); })
            .catch(() => { if (live) setAllowed(false); });
        return () => { live = false; };
    }, [role]);
    return allowed;
};

const useHostMachine = (hostId: string) => {
    const [data, setData] = useState<HostMachine | null>(null);
    const [loading, setLoading] = useState(true);
    const [failed, setFailed] = useState(false);
    const reload = useCallback(async () => {
        try {
            setData(await getHostMachine(hostId));
            setFailed(false);
        } catch {
            setFailed(true);
        } finally {
            setLoading(false);
        }
    }, [hostId]);
    useEffect(() => { void reload(); }, [reload]);
    return { data, loading, failed, reload };
};

/** Debounced entry-time check of a draft tag. */
const useTagCheck = (draft: string, machineId: string) => {
    const [reason, setReason] = useState<string | null>(null);
    const [checking, setChecking] = useState(false);
    useEffect(() => {
        let live = true;
        setChecking(true);
        const timer = setTimeout(() => {
            checkAssetTag(draft.trim(), machineId)
                .then((res) => { if (live) setReason(res.ok ? null : (res.reason ?? 'unknown')); })
                .catch(() => { if (live) setReason(null); })
                .finally(() => { if (live) setChecking(false); });
        }, CHECK_DEBOUNCE_MS);
        return () => { live = false; clearTimeout(timer); };
    }, [draft, machineId]);
    return { reason, checking };
};

interface AssetTagEditorProps {
    machine: MachineSummary;
    onDone: () => void;
    onCancel: () => void;
}

const AssetTagEditor: React.FC<AssetTagEditorProps> = ({ machine, onDone, onCancel }) => {
    const { t } = useTranslation();
    const [draft, setDraft] = useState(machine.asset_tag ?? '');
    const [saving, setSaving] = useState(false);
    const [saveError, setSaveError] = useState<string | null>(null);
    const { reason, checking } = useTagCheck(draft, machine.id);

    const save = async () => {
        setSaving(true);
        setSaveError(null);
        try {
            await setMachineAssetTag(machine.id, draft.trim());
            onDone();
        } catch (err) {
            const code = errorCode(err);
            setSaveError(code ? tagReasonText(t, code) : t('machine.saveFailed', 'The asset tag could not be saved.'));
        } finally {
            setSaving(false);
        }
    };

    return (
        <Box sx={{ mt: 1 }}>
            <TextField
                size="small"
                label={t('machine.assetTag', 'Asset tag')}
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
                error={Boolean(reason)}
                helperText={reason ? tagReasonText(t, reason) : ' '}
                slotProps={{ htmlInput: { 'aria-label': t('machine.assetTag', 'Asset tag') } }}
                autoFocus
            />
            <Stack direction="row" spacing={1} sx={{ mt: 1 }}>
                <Button
                    variant="contained"
                    size="small"
                    onClick={() => { void save(); }}
                    disabled={saving || checking || Boolean(reason)}
                >
                    {t('common.save', 'Save')}
                </Button>
                <Button size="small" onClick={onCancel} disabled={saving}>
                    {t('common.cancel', 'Cancel')}
                </Button>
            </Stack>
            {saveError && <Alert severity="error" sx={{ mt: 1 }}>{saveError}</Alert>}
        </Box>
    );
};

interface AssetTagSectionProps {
    machine: MachineSummary;
    canEdit: boolean;
    onChanged: () => Promise<void>;
}

const AssetTagSection: React.FC<AssetTagSectionProps> = ({ machine, canEdit, onChanged }) => {
    const { t } = useTranslation();
    const [editing, setEditing] = useState(false);
    const [clearError, setClearError] = useState<string | null>(null);

    const clear = async () => {
        setClearError(null);
        try {
            await setMachineAssetTag(machine.id, null);
            await onChanged();
        } catch (err) {
            const code = errorCode(err);
            setClearError(code ? tagReasonText(t, code) : t('machine.saveFailed', 'The asset tag could not be saved.'));
        }
    };

    const tag = machine.asset_tag;
    return (
        <Box sx={{ mb: 2 }}>
            <Typography variant="body2" color="textSecondary">
                {t('machine.assetTag', 'Asset tag')}
            </Typography>
            <Typography variant="h5" component="div" data-testid="machine-asset-tag">
                {tag || t('machine.noAssetTag', 'No asset tag')}
            </Typography>
            {canEdit && editing && (
                <AssetTagEditor
                    machine={machine}
                    onCancel={() => setEditing(false)}
                    onDone={() => { setEditing(false); void onChanged(); }}
                />
            )}
            {canEdit && !editing && (
                <Stack direction="row" spacing={1} sx={{ mt: 1 }}>
                    <Button size="small" variant="outlined" onClick={() => setEditing(true)}>
                        {tag ? t('machine.changeAssetTag', 'Change') : t('machine.setAssetTag', 'Set asset tag')}
                    </Button>
                    {tag && (
                        <Button size="small" color="warning" onClick={() => { void clear(); }}>
                            {t('machine.clearAssetTag', 'Clear')}
                        </Button>
                    )}
                </Stack>
            )}
            {clearError && <Alert severity="error" sx={{ mt: 1 }}>{clearError}</Alert>}
        </Box>
    );
};

const Field: React.FC<{ label: string; value: string | null }> = ({ label, value }) => {
    const { t } = useTranslation();
    return (
        <Grid size={{ xs: 12, sm: 6 }}>
            <Typography variant="body2" color="textSecondary">{label}</Typography>
            <Typography variant="body1" sx={{ wordBreak: 'break-all' }}>
                {value || t('machine.notAvailable', 'Not available')}
            </Typography>
        </Grid>
    );
};

const MachineDetails: React.FC<{ machine: MachineSummary }> = ({ machine }) => {
    const { t } = useTranslation();
    return (
        <Box sx={{ mb: 2 }}>
            {machine.is_virtual && (
                <Chip size="small" color="info" label={t('machine.virtualMachine', 'Virtual machine')} sx={{ mb: 1 }} />
            )}
            <Grid container spacing={2}>
                <Field label={t('machine.vendor', 'Vendor')} value={machine.vendor} />
                <Field label={t('machine.model', 'Model')} value={machine.model} />
                <Field label={t('machine.systemUuid', 'System UUID')} value={machine.system_uuid} />
                <Field label={t('machine.systemSerial', 'System serial')} value={machine.system_serial} />
                <Field label={t('machine.boardSerial', 'Board serial')} value={machine.board_serial} />
            </Grid>
        </Box>
    );
};

const OtherHosts: React.FC<{ hosts: HostBrief[] }> = ({ hosts }) => {
    const { t } = useTranslation();
    return (
        <Box>
            <Typography variant="subtitle2" sx={{ fontWeight: 'bold' }}>
                {t('machine.otherHosts', 'Other operating systems on this machine')}
            </Typography>
            {hosts.length === 0 ? (
                <Typography variant="body2" color="textSecondary">
                    {t('machine.noOtherHosts', 'No other operating system on this machine has reported in.')}
                </Typography>
            ) : (
                <List dense disablePadding>
                    {hosts.map((h) => (
                        <ListItem key={h.id} disableGutters sx={{ gap: 1 }}>
                            <Link component={RouterLink} to={`/hosts/${h.id}`}>{h.fqdn}</Link>
                            {h.platform && <Typography variant="body2" color="textSecondary">{h.platform}</Typography>}
                            {!h.active && (
                                <Chip size="small" variant="outlined" label={t('machine.hostInactive', 'Inactive')} />
                            )}
                        </ListItem>
                    ))}
                </List>
            )}
        </Box>
    );
};

interface ConflictAlertProps {
    hostId: string;
    reason: string;
    canResolve: boolean;
    onResolved: () => Promise<void>;
}

const ConflictAlert: React.FC<ConflictAlertProps> = ({ hostId, reason, canResolve, onResolved }) => {
    const { t } = useTranslation();
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState<string | null>(null);

    const resolve = async (decision: 'same' | 'different') => {
        setBusy(true);
        setError(null);
        try {
            await resolveMachineConflict(hostId, decision);
            await onResolved();
        } catch (err) {
            const code = errorCode(err);
            setError(code
                ? t('machine.resolveFailedCode', 'The conflict could not be resolved ({{code}}).', { code })
                : t('machine.resolveFailed', 'The conflict could not be resolved.'));
        } finally {
            setBusy(false);
        }
    };

    const message = reason === 'virtual_clone'
        ? t('machine.conflict.virtualClone', 'Another host already reports this virtual machine\'s identity. It is usually a clone that kept its UUID.')
        : t('machine.conflict.serialMismatch', 'Another machine reports the same system UUID but a different serial number.');

    return (
        <Alert severity="warning" sx={{ mb: 2 }}>
            <AlertTitle>{t('machine.conflict.title', 'Machine identity conflict')}</AlertTitle>
            <Typography variant="body2">{message}</Typography>
            {canResolve && (
                <Stack direction="row" spacing={1} sx={{ mt: 1 }}>
                    <Button size="small" variant="outlined" disabled={busy} onClick={() => { void resolve('same'); }}>
                        {t('machine.conflict.same', 'Same machine')}
                    </Button>
                    <Button size="small" variant="outlined" disabled={busy} onClick={() => { void resolve('different'); }}>
                        {t('machine.conflict.different', 'Different machine')}
                    </Button>
                </Stack>
            )}
            {error && <Typography variant="body2" color="error" sx={{ mt: 1 }}>{error}</Typography>}
        </Alert>
    );
};

interface MachineBodyProps {
    hostId: string;
    data: HostMachine;
    canEditTag: boolean;
    canResolve: boolean;
    reload: () => Promise<void>;
}

const MachineBody: React.FC<MachineBodyProps> = ({ hostId, data, canEditTag, canResolve, reload }) => {
    const { t } = useTranslation();
    return (
        <>
            {data.conflict && (
                <ConflictAlert
                    hostId={hostId}
                    reason={data.conflict.reason}
                    canResolve={canResolve}
                    onResolved={reload}
                />
            )}
            {data.machine ? (
                <>
                    <AssetTagSection machine={data.machine} canEdit={canEditTag} onChanged={reload} />
                    <MachineDetails machine={data.machine} />
                    <OtherHosts hosts={data.other_hosts} />
                </>
            ) : (
                <Alert severity="info">
                    <AlertTitle>{t('machine.noMachine.title', 'No machine identified')}</AlertTitle>
                    {noMachineText(t, noMachineReason(data.identity))}
                </Alert>
            )}
        </>
    );
};

const HostMachineCard: React.FC<{ hostId: string }> = ({ hostId }) => {
    const { t } = useTranslation();
    const { data, loading, failed, reload } = useHostMachine(hostId);
    const canEditTag = usePermission(SecurityRoles.MANAGE_ASSET_TAGS);
    const canResolve = usePermission(SecurityRoles.APPROVE_HOST_REGISTRATION);

    let body: React.ReactNode;
    if (loading) {
        body = <CircularProgress size={24} />;
    } else if (failed || !data) {
        body = <Alert severity="error">{t('machine.loadFailed', 'The machine could not be loaded.')}</Alert>;
    } else {
        body = (
            <MachineBody
                hostId={hostId}
                data={data}
                canEditTag={canEditTag}
                canResolve={canResolve}
                reload={reload}
            />
        );
    }

    return (
        <Card>
            <CardContent>
                <Typography
                    variant="subtitle1"
                    sx={{ mb: 2, display: 'flex', alignItems: 'center', gap: 1, fontWeight: 'bold', fontSize: '1.1rem' }}
                >
                    <ComputerIcon />
                    {t('machine.title', 'Machine')}
                </Typography>
                {body}
            </CardContent>
        </Card>
    );
};

export default HostMachineCard;
