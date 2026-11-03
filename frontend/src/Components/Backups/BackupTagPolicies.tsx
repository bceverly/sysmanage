// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

// The Backups page's "Policies by tag" section (Pro+ 24.6): every tag policy
// with its tag, priority and how many hosts follow it; add, change, remove,
// and "Apply now" (otherwise the scheduler applies tag changes on its next
// pass).  Shown only where the backup engine is licensed.

import React, { useCallback, useEffect, useState } from 'react';
import {
    Alert,
    Button,
    Chip,
    IconButton,
    Paper,
    Stack,
    Table,
    TableBody,
    TableCell,
    TableHead,
    TableRow,
    Tooltip,
    Typography,
} from '@mui/material';
import DeleteIcon from '@mui/icons-material/Delete';
import EditIcon from '@mui/icons-material/Edit';
import { useTranslation } from 'react-i18next';
import AsyncButton from '../AsyncButton';
import { useModuleLicensed } from '../../hooks/useModuleLicensed';
import {
    applyTagPolicies,
    deleteTagPolicy,
    listHostTags,
    listTagPolicies,
} from '../../Services/backupTagPolicies';
import type { HostTag, TagPolicy, TagPolicyOutcome } from '../../Services/backupTagPolicies';
import TagPolicyDialog from './TagPolicyDialog';
import { apiDetail } from './backupLabels';

const BackupTagPolicies: React.FC<{
    canManage: boolean;
    onChanged: () => void;
    onNotice: (message: string) => void;
    onError: (message: string) => void;
}> = ({ canManage, onChanged, onNotice, onError }) => {
    const { t } = useTranslation();
    const licensed = useModuleLicensed('backup_engine');
    const [rows, setRows] = useState<TagPolicy[] | null>(null);
    const [tags, setTags] = useState<HostTag[]>([]);
    const [editing, setEditing] = useState<TagPolicy | null>(null);
    const [open, setOpen] = useState(false);

    const load = useCallback(async () => {
        try {
            const [policies, hostTags] = await Promise.all([listTagPolicies(), listHostTags()]);
            setRows(policies);
            setTags(hostTags);
        } catch {
            setRows([]);
        }
    }, []);

    useEffect(() => {
        if (licensed) void load();
    }, [licensed, load]);

    if (!licensed) return null;

    const summary = (outcome: TagPolicyOutcome): string =>
        t('backups.tagPolicies.outcome', '{{applied}} applied, {{removed}} removed, {{skipped}} skipped.', {
            applied: outcome.applied.length,
            removed: outcome.removed.length,
            skipped: outcome.skipped.length,
        });

    const applyNow = async () => {
        try {
            onNotice(summary(await applyTagPolicies()));
            void load();
            onChanged();
        } catch (err) {
            onError(apiDetail(err, t('backups.tagPolicies.applyError', 'The tag policies could not be applied.')));
        }
    };

    const remove = async (row: TagPolicy) => {
        try {
            const result = await deleteTagPolicy(row.id);
            onNotice(summary(result.applied));
            void load();
            onChanged();
        } catch (err) {
            onError(apiDetail(err, t('backups.tagPolicies.deleteError', 'The tag policy could not be removed.')));
        }
    };

    const saved = (message: string) => {
        onNotice(message);
        void load();
        onChanged();
    };

    return (
        <Paper variant="outlined" sx={{ p: 2, mb: 3, overflowX: 'auto' }}>
            <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 1 }}>
                <Typography variant="h6">{t('backups.tagPolicies.title', 'Policies by tag')}</Typography>
                {canManage && (
                    <Stack direction="row" spacing={1}>
                        <AsyncButton size="small" onClick={applyNow} disabled={!rows?.length}>
                            {t('backups.tagPolicies.apply', 'Apply now')}
                        </AsyncButton>
                        <Button size="small" variant="outlined" disabled={tags.length === 0}
                            onClick={() => { setEditing(null); setOpen(true); }}>
                            {t('backups.tagPolicies.add', 'Add tag policy')}
                        </Button>
                    </Stack>
                )}
            </Stack>
            <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
                {t('backups.tagPolicies.help',
                    'Every host with the tag gets these settings. Where several cover a host, the lowest priority wins; a host\'s own policy (Configure) always wins.')}
            </Typography>
            {rows !== null && rows.length === 0 && (
                <Alert severity="info">
                    {tags.length === 0
                        ? t('backups.tagPolicies.noTags', 'Add a tag to some hosts first; a tag policy covers every host with its tag.')
                        : t('backups.tagPolicies.empty', 'No tag policies yet.')}
                </Alert>
            )}
            {rows !== null && rows.length > 0 && (
                <Table size="small">
                    <TableHead>
                        <TableRow>
                            <TableCell>{t('backups.tagPolicies.name', 'Name')}</TableCell>
                            <TableCell>{t('backups.tagPolicies.tagColumn', 'Tag')}</TableCell>
                            <TableCell>{t('backups.tagPolicies.priority', 'Priority')}</TableCell>
                            <TableCell>{t('backups.tagPolicies.hosts', 'Hosts following it')}</TableCell>
                            <TableCell />
                        </TableRow>
                    </TableHead>
                    <TableBody>
                        {rows.map(row => (
                            <TableRow key={row.id}>
                                <TableCell>
                                    {row.name}
                                    {!row.enabled && (
                                        <Chip size="small" sx={{ ml: 1 }}
                                            label={t('backups.tagPolicies.paused', 'Paused')} />
                                    )}
                                </TableCell>
                                <TableCell>{row.tag_name ?? '-'}</TableCell>
                                <TableCell>{row.priority}</TableCell>
                                <TableCell>
                                    {t('backups.tagPolicies.hostsCount', '{{applied}} of {{tagged}} tagged',
                                        { applied: row.hosts_applied, tagged: row.hosts_tagged })}
                                </TableCell>
                                <TableCell align="right">
                                    {canManage && (
                                        <>
                                            <Tooltip title={t('backups.tagPolicies.edit', 'Change')}>
                                                <IconButton size="small" aria-label={t('backups.tagPolicies.edit', 'Change')}
                                                    onClick={() => { setEditing(row); setOpen(true); }}>
                                                    <EditIcon fontSize="small" />
                                                </IconButton>
                                            </Tooltip>
                                            <Tooltip title={t('backups.tagPolicies.remove', 'Remove')}>
                                                <IconButton size="small" aria-label={t('backups.tagPolicies.remove', 'Remove')}
                                                    onClick={() => void remove(row)}>
                                                    <DeleteIcon fontSize="small" />
                                                </IconButton>
                                            </Tooltip>
                                        </>
                                    )}
                                </TableCell>
                            </TableRow>
                        ))}
                    </TableBody>
                </Table>
            )}
            <TagPolicyDialog open={open} tags={tags} existing={editing}
                onClose={() => setOpen(false)} onSaved={saved} />
        </Paper>
    );
};

export default BackupTagPolicies;
