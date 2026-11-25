// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

/**
 * The off-site cloud copy's dialogs (ROADMAP 27.3): set it up or change it
 * (Professional+), restore from it, export its keys and read the bucket
 * setup guide.  Restoring and the export work in every edition.
 */

import React, { useEffect, useState } from 'react';
import {
    Alert, Button, Checkbox, Dialog, DialogActions, DialogContent, DialogTitle,
    FormControlLabel, MenuItem, Stack, TextField, Typography,
} from '@mui/material';
import { useTranslation } from 'react-i18next';

import {
    CloudCopy, CloudCopyOverview, CloudCopySettings, CopyChanges, RestoreEstimate, RestorePoint,
    SetupGuide, createCloudCopy, estimateRestore, exportCloudCopyKeys, getRestorePoints,
    getSetupGuide, restoreCloudCopy, updateCloudCopy,
} from '../../Services/backupCloudCopy';
import { apiDetail, formatBytes, formatTime } from './backupLabels';

// File names the commands above read (not prose).
const LIFECYCLE_FILE = 'lifecycle.json';
const POLICY_FILE = 'iam-policy.json';
const CLASSES = ['DEEP_ARCHIVE', 'GLACIER', 'GLACIER_IR', 'STANDARD_IA', 'STANDARD'];
const lines = (text: string): string[] => text.split('\n').map(s => s.trim()).filter(Boolean);

const saveText = (text: string, name: string): void => {
    const url = globalThis.URL.createObjectURL(new Blob([text], { type: 'application/pgp-encrypted' }));
    const link = document.createElement('a');
    link.href = url;
    link.download = name;
    document.body.appendChild(link);
    link.click();
    link.remove();
    globalThis.URL.revokeObjectURL(url);
};

const numberField = (value: number, set: (n: number) => void) => ({
    type: 'number', value, onChange: (e: React.ChangeEvent<HTMLInputElement>) => set(Number(e.target.value)),
});

/** Set up a copy (no ``copy``) or change one. */
export const CloudCopyDialog: React.FC<{
    copy: CloudCopy | null;
    overview: CloudCopyOverview;
    onClose: () => void;
    onSaved: () => void;
}> = ({ copy, overview, onClose, onSaved }) => {
    const { t } = useTranslation();
    const start: CloudCopySettings = { ...(overview.defaults as CloudCopySettings), ...(copy?.settings ?? {}) };
    const freeTargets = overview.targets.filter(tg => !overview.copies.some(c => c.target_id === tg.id));
    const [targetId, setTargetId] = useState(copy?.target_id ?? freeTargets[0]?.id ?? '');
    const [bucket, setBucket] = useState(copy?.bucket ?? '');
    const [region, setRegion] = useState(copy?.region ?? 'us-east-1');
    const [prefix, setPrefix] = useState(copy?.prefix ?? '');
    const [endpoint, setEndpoint] = useState(copy?.endpoint ?? '');
    const [storageClass, setStorageClass] = useState(copy?.storage_class ?? 'DEEP_ARCHIVE');
    const [objectLock, setObjectLock] = useState(copy?.object_lock ?? true);
    const [accessKey, setAccessKey] = useState('');
    const [secretKey, setSecretKey] = useState('');
    const [settings, setSettings] = useState<CloudCopySettings>(start);
    const [exclude, setExclude] = useState((start.exclude ?? []).join('\n'));
    const [include, setInclude] = useState((start.include ?? []).join('\n'));
    const firstRule = start.bandwidth?.rules?.[0];
    const [capKbps, setCapKbps] = useState(firstRule?.kbps ?? 0);
    const [error, setError] = useState('');
    const [busy, setBusy] = useState(false);
    const set = (field: keyof CloudCopySettings) => (n: number) => setSettings(s => ({ ...s, [field]: n }));

    const save = async () => {
        setBusy(true);
        setError('');
        const rules = capKbps > 0
            ? [{ days: firstRule?.days ?? [0, 1, 2, 3, 4], start: firstRule?.start ?? '08:00',
                 end: firstRule?.end ?? '18:00', kbps: capKbps }]
            : [];
        const body: CopyChanges = {
            bucket: bucket.trim(), region: region.trim(), prefix: prefix.trim(),
            endpoint: endpoint.trim() || null, storage_class: storageClass, object_lock: objectLock,
            settings: { ...settings, exclude: lines(exclude), include: lines(include),
                        bandwidth: { rules, default_kbps: 0 } },
        };
        if (accessKey.trim() || secretKey) {
            body.access_key = accessKey.trim();
            body.secret_key = secretKey;
        }
        try {
            if (copy) await updateCloudCopy(copy.id, body);
            else await createCloudCopy({ ...body, target_id: targetId });
            onSaved();
        } catch (err) {
            setError(apiDetail(err, t('backups.cloudCopy.saveFailed', 'The cloud copy could not be saved.')));
        } finally {
            setBusy(false);
        }
    };

    return (
        <Dialog open onClose={onClose} fullWidth maxWidth="sm">
            <DialogTitle>{copy ? t('backups.cloudCopy.editTitle', 'Cloud copy settings')
                : t('backups.cloudCopy.setUpTitle', 'Set up the cloud copy')}</DialogTitle>
            <DialogContent>
                <Typography variant="body2" sx={{ mb: 2 }}>
                    {t('backups.cloudCopy.setUpHelp', 'The storage host encrypts its datasets with a key only you hold and uploads them straight to your S3 bucket. Only the bucket, its region and an access key are needed; everything else has a safe default.')}
                </Typography>
                <Stack spacing={2}>
                    {!copy && (
                        <TextField select label={t('backups.cloudCopy.target', 'Backup target')} value={targetId}
                                   onChange={e => setTargetId(e.target.value)}>
                            {freeTargets.map(tg => <MenuItem key={tg.id} value={tg.id}>{tg.name}</MenuItem>)}
                        </TextField>
                    )}
                    <TextField label={t('backups.cloudCopy.bucket', 'S3 bucket')} value={bucket} onChange={e => setBucket(e.target.value)} />
                    <TextField label={t('backups.cloudCopy.region', 'Region')} value={region} onChange={e => setRegion(e.target.value)} />
                    <TextField label={t('backups.cloudCopy.accessKey', 'Access key ID')} value={accessKey}
                               placeholder={copy?.access_key_hint ? `...${copy.access_key_hint}` : ''}
                               onChange={e => setAccessKey(e.target.value)} />
                    <TextField type="password" label={t('backups.cloudCopy.secretKey', 'Secret access key')} value={secretKey}
                               helperText={copy ? t('backups.cloudCopy.keepCredentials', 'Leave both empty to keep the current credentials.') : ''}
                               onChange={e => setSecretKey(e.target.value)} />
                    <TextField label={t('backups.cloudCopy.prefix', 'Prefix in the bucket')} value={prefix} onChange={e => setPrefix(e.target.value)} />
                    <TextField select label={t('backups.cloudCopy.storageClass', 'Storage class')} value={storageClass}
                               onChange={e => setStorageClass(e.target.value)}>
                        {CLASSES.map(c => <MenuItem key={c} value={c}>{c}</MenuItem>)}
                    </TextField>
                    <FormControlLabel control={<Checkbox checked={objectLock} onChange={e => setObjectLock(e.target.checked)} />}
                                      label={t('backups.cloudCopy.objectLock', 'Object Lock: nobody can delete a copy before it expires')} />
                    <TextField label={t('backups.cloudCopy.fullEvery', 'A full copy every (days)')} {...numberField(settings.full_every_days, set('full_every_days'))} />
                    <TextField label={t('backups.cloudCopy.runHour', 'Upload each day at (hour, UTC)')} {...numberField(settings.run_hour_utc, set('run_hour_utc'))} />
                    <TextField label={t('backups.cloudCopy.keepMonthly', 'Monthly copies to keep')} {...numberField(settings.keep_monthly, set('keep_monthly'))} />
                    <TextField label={t('backups.cloudCopy.keepYearly', 'Yearly copies to keep')} {...numberField(settings.keep_yearly, set('keep_yearly'))} />
                    <TextField label={t('backups.cloudCopy.cap', 'Upload cap on weekdays 08:00-18:00 (kbit/s, 0 for none)')} {...numberField(capKbps, setCapKbps)} />
                    <TextField multiline minRows={2} label={t('backups.cloudCopy.exclude', 'Datasets to leave out (one per line)')}
                               value={exclude} onChange={e => setExclude(e.target.value)} />
                    <TextField multiline minRows={2} label={t('backups.cloudCopy.include', "Other datasets on the storage host to copy (one per line)")}
                               value={include} onChange={e => setInclude(e.target.value)} />
                    <TextField label={t('backups.cloudCopy.endpoint', 'S3-compatible endpoint (leave empty for AWS)')} value={endpoint}
                               onChange={e => setEndpoint(e.target.value)} />
                    {error && <Alert severity="error">{error}</Alert>}
                </Stack>
            </DialogContent>
            <DialogActions>
                <Button onClick={onClose}>{t('common.cancel', 'Cancel')}</Button>
                <Button variant="contained" disabled={busy || !bucket.trim() || (!copy && (!accessKey.trim() || !secretKey))}
                        onClick={() => { void save(); }}>{t('common.save', 'Save')}</Button>
            </DialogActions>
        </Dialog>
    );
};

/** Pick a restore point, see the thaw's cost and time, restore into a new dataset. */
export const CloudRestoreDialog: React.FC<{ copy: CloudCopy; onClose: () => void; onStarted: () => void }> = ({
    copy, onClose, onStarted,
}) => {
    const { t } = useTranslation();
    const [points, setPoints] = useState<RestorePoint[] | null>(null);
    const [picked, setPicked] = useState('');
    const [tier, setTier] = useState('Bulk');
    const [target, setTarget] = useState('');
    const [cost, setCost] = useState<RestoreEstimate | null>(null);
    const [error, setError] = useState('');
    const point = points?.find(p => `${p.dataset}@${p.snapshot}` === picked);

    useEffect(() => {
        getRestorePoints(copy.id).then(found => {
            setPoints(found);
            if (found[0]) setPicked(`${found[0].dataset}@${found[0].snapshot}`);
        }).catch(err => setError(apiDetail(err, t('backups.cloudCopy.pointsFailed', 'The restore points could not be read.'))));
    }, [copy.id, t]);

    useEffect(() => {
        if (!point) return;
        setTarget(`${point.dataset}-restored`);
        estimateRestore(copy.id, point.dataset, point.snapshot, tier).then(setCost).catch(() => setCost(null));
    }, [copy.id, point, tier]);

    const start = async () => {
        if (!point) return;
        try {
            await restoreCloudCopy(copy.id, point.dataset, point.snapshot, tier, target.trim());
            onStarted();
        } catch (err) {
            setError(apiDetail(err, t('backups.cloudCopy.restoreFailed', 'The restore could not be started.')));
        }
    };

    return (
        <Dialog open onClose={onClose} fullWidth maxWidth="sm">
            <DialogTitle>{t('backups.cloudCopy.restoreTitle', 'Restore from the cloud copy')}</DialogTitle>
            <DialogContent>
                <Typography variant="body2" sx={{ mb: 2 }}>
                    {t('backups.cloudCopy.restoreHelp', 'S3 thaws the copy first, then the storage host downloads, decrypts and receives it into a new dataset. Nothing existing is overwritten.')}
                </Typography>
                <Stack spacing={2}>
                    <TextField select label={t('backups.cloudCopy.point', 'Restore point')} value={picked}
                               onChange={e => setPicked(e.target.value)} disabled={!points?.length}>
                        {(points ?? []).map(p => (
                            <MenuItem key={`${p.dataset}@${p.snapshot}`} value={`${p.dataset}@${p.snapshot}`}>
                                {`${p.dataset} - ${formatTime(p.uploaded_at)} (${formatBytes(p.bytes)})`}
                            </MenuItem>
                        ))}
                    </TextField>
                    <TextField select label={t('backups.cloudCopy.tier', 'Thaw speed')} value={tier} onChange={e => setTier(e.target.value)}>
                        <MenuItem value="Bulk">{t('backups.cloudCopy.bulk', 'Bulk (cheapest, up to 48 hours)')}</MenuItem>
                        <MenuItem value="Standard">{t('backups.cloudCopy.standard', 'Standard (up to 12 hours)')}</MenuItem>
                    </TextField>
                    <TextField label={t('backups.cloudCopy.newDataset', 'New dataset to restore into')} value={target}
                               onChange={e => setTarget(e.target.value)} />
                    {cost && (
                        <Alert severity="info">
                            {t('backups.cloudCopy.estimate', 'About {{hours}} hours to thaw {{size}} in {{parts}} parts; about {{thaw}} to thaw and {{transfer}} to download (AWS list prices, an estimate).', {
                                hours: cost.thaw_hours, size: formatBytes(cost.bytes), parts: cost.parts,
                                thaw: `$${cost.usd_thaw.toFixed(2)}`, transfer: `$${cost.usd_transfer.toFixed(2)}`,
                            })}
                        </Alert>
                    )}
                    {points && !points.length && <Alert severity="warning">{t('backups.cloudCopy.noPoints', 'Nothing in the bucket can be restored yet.')}</Alert>}
                    {error && <Alert severity="error">{error}</Alert>}
                </Stack>
            </DialogContent>
            <DialogActions>
                <Button onClick={onClose}>{t('common.cancel', 'Cancel')}</Button>
                <Button variant="contained" disabled={!point || !target.trim()} onClick={() => { void start(); }}>
                    {t('backups.cloudCopy.startRestore', 'Thaw and restore')}
                </Button>
            </DialogActions>
        </Dialog>
    );
};

/** The sealed export of the copy's keys and credentials. */
export const CloudKeyExportDialog: React.FC<{ copy: CloudCopy; onClose: () => void }> = ({ copy, onClose }) => {
    const { t } = useTranslation();
    const [reason, setReason] = useState('');
    const [key, setKey] = useState('');
    const [error, setError] = useState('');
    const run = async () => {
        setError('');
        try {
            const { name, content } = await exportCloudCopyKeys(copy.id, reason.trim(), key.trim());
            saveText(content, name);
            onClose();
        } catch (err) {
            setError(apiDetail(err, t('backups.cloudCopy.exportFailed', 'The keys could not be exported.')));
        }
    };
    return (
        <Dialog open onClose={onClose} fullWidth maxWidth="sm">
            <DialogTitle>{t('backups.cloudCopy.exportTitle', "Export the cloud copy's keys")}</DialogTitle>
            <DialogContent>
                <Typography variant="body2" sx={{ mb: 2 }}>
                    {t('backups.cloudCopy.exportHelp', 'Everything a restore needs without SysManage: the bucket, the credentials and every key, sealed to your own OpenPGP key. Keep it somewhere the site cannot take with it.')}
                </Typography>
                <Stack spacing={2}>
                    <TextField multiline minRows={4} label={t('backups.cloudCopy.recipient', 'OpenPGP public key (empty: the saved escrow key)')}
                               value={key} onChange={e => setKey(e.target.value)} />
                    <TextField label={t('backups.cloudCopy.reason', 'Why you are exporting them')} value={reason}
                               onChange={e => setReason(e.target.value)} />
                    {error && <Alert severity="error">{error}</Alert>}
                </Stack>
            </DialogContent>
            <DialogActions>
                <Button onClick={onClose}>{t('common.cancel', 'Cancel')}</Button>
                <Button variant="contained" disabled={reason.trim().length < 10} onClick={() => { void run(); }}>
                    {t('backups.cloudCopy.exportButton', 'Export and download')}
                </Button>
            </DialogActions>
        </Dialog>
    );
};

/** What to apply to the bucket and the IAM user. */
export const CloudSetupGuideDialog: React.FC<{ copy: CloudCopy; onClose: () => void }> = ({ copy, onClose }) => {
    const { t } = useTranslation();
    const [guide, setGuide] = useState<SetupGuide | null>(null);
    const [error, setError] = useState('');
    useEffect(() => {
        getSetupGuide(copy.id).then(setGuide)
            .catch(err => setError(apiDetail(err, t('backups.cloudCopy.guideFailed', 'The setup guide could not be read.'))));
    }, [copy.id, t]);
    const block = (text: string) => (
        <TextField multiline fullWidth value={text} slotProps={{ input: { readOnly: true, sx: { fontFamily: 'monospace', fontSize: 12 } } }} />
    );
    return (
        <Dialog open onClose={onClose} fullWidth maxWidth="md">
            <DialogTitle>{t('backups.cloudCopy.guideTitle', 'Bucket setup')}</DialogTitle>
            <DialogContent>
                {error && <Alert severity="error">{error}</Alert>}
                {guide && (
                    <Stack spacing={2}>
                        <Typography variant="body2">{t('backups.cloudCopy.guideCommands', 'Create the bucket with Object Lock, its lifecycle rules and an IAM user that can upload but never delete:')}</Typography>
                        {block(guide.commands.join('\n'))}
                        <Typography variant="subtitle2">{LIFECYCLE_FILE}</Typography>
                        {block(JSON.stringify(guide.lifecycle, null, 2))}
                        <Typography variant="subtitle2">{POLICY_FILE}</Typography>
                        {block(JSON.stringify(guide.iam_policy, null, 2))}
                    </Stack>
                )}
            </DialogContent>
            <DialogActions><Button onClick={onClose}>{t('common.close', 'Close')}</Button></DialogActions>
        </Dialog>
    );
};
