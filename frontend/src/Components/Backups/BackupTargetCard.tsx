// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

// The backup target (Phase 24): where repositories live, the storage host
// that maintains them, and whether each capture is sealed (a ZFS snapshot or
// a read-only btrfs snapshot).  Community has one target.  The storage
// side's status and warnings are in BackupStorageStatus.

import React, { useEffect, useState } from 'react';
import {
    Alert,
    Box,
    Button,
    Card,
    CardContent,
    Dialog,
    DialogActions,
    DialogContent,
    DialogTitle,
    FormControl,
    InputLabel,
    MenuItem,
    Select,
    Stack,
    TextField,
    Typography,
} from '@mui/material';
import StorageIcon from '@mui/icons-material/Storage';
import { useTranslation } from 'react-i18next';
import type { TFunction } from 'i18next';
import AsyncButton from '../AsyncButton';
import { saveTarget } from '../../Services/backups';
import type { BackupHost, BackupTarget, SealMode, TargetInput } from '../../Services/backups';
import { apiDetail, reasonLabel } from './backupLabels';
import BackupStorageStatus from './BackupStorageStatus';

const EMPTY: TargetInput = {
    name: '',
    host_mount_point: '/mnt/backups',
    storage_host_id: null,
    storage_path: '/srv/backups/restate',
    max_concurrent: 2,
    seal_mode: 'none',
    zfs_dataset: null,
    btrfs_snapshot_dir: null,
    service_account: null,
    seal_keep_days: 14,
    space_low_percent: 85,
    space_critical_percent: 95,
};

const toInput = (target: BackupTarget | null): TargetInput =>
    target
        ? {
              name: target.name,
              host_mount_point: target.host_mount_point,
              storage_host_id: target.storage_host_id,
              storage_path: target.storage_path,
              max_concurrent: target.max_concurrent,
              seal_mode: target.seal_mode,
              zfs_dataset: target.zfs_dataset,
              btrfs_snapshot_dir: target.btrfs_snapshot_dir,
              service_account: target.service_account ?? null,
              seal_keep_days: target.seal_keep_days ?? 14,
              space_low_percent: target.space_low_percent ?? 85,
              space_critical_percent: target.space_critical_percent ?? 95,
          }
        : EMPTY;

export const TargetDialog: React.FC<{
    open: boolean;
    target: BackupTarget | null;
    hosts: BackupHost[];
    onClose: () => void;
    onSaved: () => void;
}> = ({ open, target, hosts, onClose, onSaved }) => {
    const { t } = useTranslation();
    const [form, setForm] = useState<TargetInput>(toInput(target));
    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
        if (open) {
            setForm(toInput(target));
            setError(null);
        }
    }, [open, target]);

    const set = (patch: Partial<TargetInput>) => setForm(f => ({ ...f, ...patch }));

    const save = async () => {
        try {
            await saveTarget(
                {
                    ...form,
                    storage_host_id: form.storage_host_id || null,
                    zfs_dataset: form.zfs_dataset || null,
                    btrfs_snapshot_dir: form.btrfs_snapshot_dir || null,
                    service_account: form.service_account || null,
                },
                target?.id,
            );
            onSaved();
            onClose();
        } catch (err) {
            setError(apiDetail(err, t('backups.target.saveError', 'The target could not be saved.')));
        }
    };

    return (
        <Dialog open={open} onClose={onClose} maxWidth="sm" fullWidth>
            <DialogTitle>{t('backups.target.dialogTitle', 'Backup target')}</DialogTitle>
            <DialogContent>
                <Stack spacing={2} sx={{ mt: 1 }}>
                    {error && <Alert severity="error">{error}</Alert>}
                    <TextField label={t('backups.target.name', 'Name')} value={form.name}
                        onChange={e => set({ name: e.target.value })} required />
                    <TextField label={t('backups.target.hostMountPoint', 'Mount point on each host')}
                        value={form.host_mount_point} onChange={e => set({ host_mount_point: e.target.value })}
                        helperText={t('backups.target.hostMountPointHelp',
                            'Where every backed-up host mounts the target (NFS); each host writes only its own repository.')}
                        required />
                    <FormControl fullWidth>
                        <InputLabel id="backup-storage-host">{t('backups.target.storageHost', 'Storage host')}</InputLabel>
                        <Select labelId="backup-storage-host" label={t('backups.target.storageHost', 'Storage host')}
                            value={form.storage_host_id ?? ''} onChange={e => set({ storage_host_id: e.target.value || null })}>
                            <MenuItem value="">{t('backups.target.noStorageHost', 'None')}</MenuItem>
                            {hosts.map(h => <MenuItem key={h.host_id} value={h.host_id}>{h.fqdn}</MenuItem>)}
                        </Select>
                    </FormControl>
                    <TextField label={t('backups.target.storagePath', 'Path on the storage host')}
                        value={form.storage_path ?? ''} onChange={e => set({ storage_path: e.target.value || null })}
                        helperText={t('backups.target.storagePathHelp',
                            'The storage host prunes, checks and seals here; backed-up hosts never prune.')} />
                    <TextField type="number" label={t('backups.target.maxConcurrent', 'Backups at the same time')}
                        value={form.max_concurrent} inputProps={{ min: 1, max: 50 }}
                        onChange={e => set({ max_concurrent: Number(e.target.value) })} />
                    <FormControl fullWidth>
                        <InputLabel id="backup-seal-mode">{t('backups.target.sealMode', 'Seal each backup')}</InputLabel>
                        <Select labelId="backup-seal-mode" label={t('backups.target.sealMode', 'Seal each backup')}
                            value={form.seal_mode} onChange={e => set({ seal_mode: e.target.value as SealMode })}>
                            <MenuItem value="none">{t('backups.target.sealNone', 'Do not seal')}</MenuItem>
                            <MenuItem value="zfs_snapshot">{t('backups.target.sealZfs', 'ZFS snapshot')}</MenuItem>
                            <MenuItem value="btrfs_snapshot">
                                {t('backups.target.sealBtrfs', 'btrfs snapshot (read-only)')}
                            </MenuItem>
                        </Select>
                    </FormControl>
                    {form.seal_mode === 'btrfs_snapshot' && (
                        <TextField label={t('backups.target.btrfsSnapshotDir', 'Snapshot directory on the storage host')}
                            value={form.btrfs_snapshot_dir ?? ''} placeholder="/srv/backups/.snapshots"
                            onChange={e => set({ btrfs_snapshot_dir: e.target.value || null })} required
                            helperText={t('backups.target.btrfsHelp',
                                'The repositories must sit on a btrfs subvolume; snapshots go to a directory on the same filesystem, outside the subvolume.')} />
                    )}
                    <Stack direction="row" spacing={2}>
                        <TextField type="number" fullWidth label={t('backups.target.spaceLow', 'Warn when the storage is this full (%)')}
                            value={form.space_low_percent ?? ''} inputProps={{ min: 50, max: 99 }}
                            onChange={e => set({ space_low_percent: e.target.value === '' ? null : Number(e.target.value) })} />
                        <TextField type="number" fullWidth label={t('backups.target.spaceCritical', 'Critical when the storage is this full (%)')}
                            value={form.space_critical_percent ?? ''} inputProps={{ min: 51, max: 100 }}
                            onChange={e => set({ space_critical_percent: e.target.value === '' ? null : Number(e.target.value) })} />
                    </Stack>
                    <TextField label={t('backups.target.serviceAccount', 'Backup account on the storage host')}
                        value={form.service_account ?? ''} placeholder="restate"
                        onChange={e => set({ service_account: e.target.value || null })}
                        helperText={t('backups.target.serviceAccountHelp',
                            'Every host\'s export maps to this account and its group. Default: restate.')} />
                    {form.seal_mode === 'zfs_snapshot' && (
                        <TextField label={t('backups.target.zfsDataset', 'ZFS dataset')} value={form.zfs_dataset ?? ''}
                            onChange={e => set({ zfs_dataset: e.target.value || null })} required />
                    )}
                    {form.seal_mode !== 'none' && (
                        <TextField type="number" label={t('backups.target.sealKeepDays', 'Keep sealed snapshots for (days)')}
                            value={form.seal_keep_days ?? ''} inputProps={{ min: 1, max: 3650 }}
                            onChange={e => set({ seal_keep_days: e.target.value === '' ? null : Number(e.target.value) })}
                            helperText={t('backups.target.sealKeepHelp',
                                'The storage host removes older sealed snapshots itself; the newest is always kept.')} />
                    )}
                </Stack>
            </DialogContent>
            <DialogActions>
                <Button onClick={onClose}>{t('common.cancel', 'Cancel')}</Button>
                <AsyncButton variant="contained" onClick={save}
                    disabled={!form.name.trim() || !form.host_mount_point.trim()}>
                    {t('common.save', 'Save')}
                </AsyncButton>
            </DialogActions>
        </Dialog>
    );
};

const keptFor = (t: TFunction, target: BackupTarget): string =>
    `${t('backups.target.sealKeepDays', 'Keep sealed snapshots for (days)')}: ${target.seal_keep_days ?? 14}`;

const sealDescription = (t: TFunction, target: BackupTarget): string => {
    switch (target.seal_mode) {
        case 'zfs_snapshot':
            return `${t('backups.target.sealZfs', 'ZFS snapshot')} (${target.zfs_dataset}) - ${keptFor(t, target)}`;
        case 'btrfs_snapshot':
            return `${t('backups.target.sealBtrfs', 'btrfs snapshot (read-only)')} (${target.btrfs_snapshot_dir}) - ${keptFor(t, target)}`;
        default:
            return t('backups.target.sealNone', 'Do not seal');
    }
};

const BackupTargetCard: React.FC<{
    target: BackupTarget | null;
    hosts: BackupHost[];
    versions: string[];
    canManage: boolean;
    onChanged: () => void;
}> = ({ target, hosts, versions, canManage, onChanged }) => {
    const { t } = useTranslation();
    const [open, setOpen] = useState(false);
    return (
        <Card variant="outlined" sx={{ mb: 2 }}>
            <CardContent>
                <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 1 }}>
                    <StorageIcon />
                    <Typography variant="h6" sx={{ flexGrow: 1 }}>
                        {target ? target.name : t('backups.target.none', 'No backup target yet')}
                    </Typography>
                    {canManage && (
                        <Button variant="outlined" size="small" onClick={() => setOpen(true)}>
                            {target ? t('backups.target.edit', 'Edit target') : t('backups.target.add', 'Set up target')}
                        </Button>
                    )}
                </Stack>
                {!target && (
                    <Typography variant="body2" color="text.secondary">
                        {t('backups.target.intro',
                            'Point every host at one NFS share. Hosts only add to their own repository; the storage host seals, prunes and checks.')}
                    </Typography>
                )}
                {target && (
                    <Box>
                        <Typography variant="body2">
                            {t('backups.target.mountedAt', 'Hosts mount it at')}: <code>{target.host_mount_point}</code>
                        </Typography>
                        <Typography variant="body2">
                            {t('backups.target.storageHost', 'Storage host')}:{' '}
                            {target.storage_hostname
                                ? <>{target.storage_hostname} <code>{target.storage_path}</code></>
                                : t('backups.target.noStorageHost', 'None')}
                            {target.storage_reason && target.storage_hostname && ` (${reasonLabel(t, target.storage_reason)})`}
                        </Typography>
                        <Typography variant="body2">
                            {t('backups.target.sealMode', 'Seal each backup')}:{' '}
                            {sealDescription(t, target)}
                        </Typography>
                        {versions.length > 0 && (
                            <Typography variant="body2" color="text.secondary">
                                {t('backups.target.restateVersions', 'restate versions in use')}: {versions.join(', ')}
                            </Typography>
                        )}
                        <BackupStorageStatus target={target} hosts={hosts} />
                    </Box>
                )}
                <TargetDialog open={open} target={target} hosts={hosts} onClose={() => setOpen(false)} onSaved={onChanged} />
            </CardContent>
        </Card>
    );
};

export default BackupTargetCard;
