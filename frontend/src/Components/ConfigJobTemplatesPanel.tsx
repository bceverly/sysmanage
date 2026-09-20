// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

import React, { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import Alert from '@mui/material/Alert';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Chip from '@mui/material/Chip';
import Dialog from '@mui/material/Dialog';
import DialogActions from '@mui/material/DialogActions';
import DialogContent from '@mui/material/DialogContent';
import DialogContentText from '@mui/material/DialogContentText';
import DialogTitle from '@mui/material/DialogTitle';
import FormControlLabel from '@mui/material/FormControlLabel';
import MenuItem from '@mui/material/MenuItem';
import Stack from '@mui/material/Stack';
import Switch from '@mui/material/Switch';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import PlayArrowIcon from '@mui/icons-material/PlayArrow';

import {
    ConfigInventory,
    ConfigJobTemplate,
    createJobTemplate,
    deleteJobTemplate,
    getInventories,
    getJobTemplates,
    launchJobTemplate,
} from '../Services/configFleetService';
import { ConfigProfile, getConfigProfiles } from '../Services/configManagementService';

const messageFrom = (err: unknown, fallback: string): string => {
    const detail = (err as { response?: { data?: { detail?: unknown } } })?.response
        ?.data?.detail;
    return typeof detail === 'string' && detail ? detail : fallback;
};

interface Props {
    canEdit: boolean;
    canLaunch: boolean;
    onLaunched?: () => void;
}

const emptyForm = {
    name: '',
    description: '',
    profileId: '',
    inventoryId: '',
    checkMode: true,
    concurrency: '20',
    schedule: '',
};

/**
 * Job templates: a profile, an inventory and how hard to run it.
 *
 * `check_mode` defaults ON here, unlike the single-host apply dialog. At fleet
 * scale the first thing anybody should do with a new template is find out what
 * it WOULD change; defaulting to a live run across an inventory is the one
 * mistake this page can make that cannot be undone.
 */
const ConfigJobTemplatesPanel: React.FC<Props> = ({
    canEdit,
    canLaunch,
    onLaunched,
}) => {
    const { t } = useTranslation();
    const [rows, setRows] = useState<ConfigJobTemplate[]>([]);
    const [profiles, setProfiles] = useState<ConfigProfile[]>([]);
    const [inventories, setInventories] = useState<ConfigInventory[]>([]);
    const [error, setError] = useState<string | null>(null);
    const [notice, setNotice] = useState<string | null>(null);
    const [creating, setCreating] = useState(false);
    const [form, setForm] = useState(emptyForm);
    const [saving, setSaving] = useState(false);
    const [confirmLaunch, setConfirmLaunch] = useState<ConfigJobTemplate | null>(null);
    const [launching, setLaunching] = useState(false);

    const load = useCallback(async () => {
        try {
            const [templates, profileRows, inventoryRows] = await Promise.all([
                getJobTemplates(),
                getConfigProfiles(),
                getInventories(),
            ]);
            setRows(templates);
            setProfiles(profileRows);
            setInventories(inventoryRows);
            setError(null);
        } catch (err) {
            setError(
                messageFrom(
                    err,
                    t('configFleet.templatesFailed', 'Could not load job templates'),
                ),
            );
        }
    }, [t]);

    useEffect(() => {
        load();
    }, [load]);

    const save = async () => {
        setSaving(true);
        try {
            const created = await createJobTemplate({
                name: form.name,
                description: form.description || null,
                profile_id: form.profileId,
                inventory_id: form.inventoryId,
                check_mode: form.checkMode,
                concurrency: Number(form.concurrency) || null,
                schedule: form.schedule || null,
            });
            // The server CLAMPS concurrency, so what came back may not be what
            // was typed. Saying so is the only way an operator learns the
            // ceiling exists.
            if (String(created.concurrency) !== form.concurrency) {
                setNotice(
                    t(
                        'configFleet.concurrencyClamped',
                        'Concurrency was adjusted to {{value}}, the highest this server allows.',
                        { value: created.concurrency },
                    ),
                );
            }
            setForm(emptyForm);
            setCreating(false);
            await load();
        } catch (err) {
            setError(
                messageFrom(
                    err,
                    t('configFleet.templateSaveFailed', 'Could not save the job template'),
                ),
            );
        } finally {
            setSaving(false);
        }
    };

    const remove = async (row: ConfigJobTemplate) => {
        try {
            await deleteJobTemplate(row.id);
            await load();
        } catch (err) {
            setError(
                messageFrom(
                    err,
                    t('configFleet.templateDeleteFailed', 'Could not delete the template'),
                ),
            );
        }
    };

    const launch = async () => {
        if (!confirmLaunch) return;
        setLaunching(true);
        try {
            const job = await launchJobTemplate(confirmLaunch.id);
            setNotice(
                t(
                    'configFleet.launched',
                    'Launched against {{count}} hosts. Progress is on the Jobs tab.',
                    { count: job.total_targets },
                ),
            );
            setConfirmLaunch(null);
            onLaunched?.();
        } catch (err) {
            setError(
                messageFrom(err, t('configFleet.launchFailed', 'Could not launch this job')),
            );
            setConfirmLaunch(null);
        } finally {
            setLaunching(false);
        }
    };

    const inventoryName = (id: string) =>
        inventories.find((i) => i.id === id)?.name || id;
    const profileName = (id: string) => profiles.find((p) => p.id === id)?.name || id;

    return (
        <Box>
            {error && (
                <Alert severity="error" sx={{ mb: 2 }} onClose={() => setError(null)}>
                    {error}
                </Alert>
            )}
            {notice && (
                <Alert severity="info" sx={{ mb: 2 }} onClose={() => setNotice(null)}>
                    {notice}
                </Alert>
            )}

            {canEdit && (
                <Button
                    variant="contained"
                    sx={{ mb: 2 }}
                    onClick={() => setCreating(true)}
                    disabled={profiles.length === 0 || inventories.length === 0}
                >
                    {t('configFleet.newTemplate', 'New job template')}
                </Button>
            )}

            {rows.length === 0 ? (
                <Alert severity="info">
                    {t(
                        'configFleet.noTemplates',
                        'No job templates yet. A template runs one profile across one ' +
                            'inventory, on demand or on a schedule.',
                    )}
                </Alert>
            ) : (
                <Stack spacing={1}>
                    {rows.map((row) => (
                        <Box
                            key={row.id}
                            sx={{ border: 1, borderColor: 'divider', borderRadius: 1, p: 2 }}
                        >
                            <Stack
                                direction="row"
                                spacing={2}
                                alignItems="center"
                                flexWrap="wrap"
                            >
                                <Typography variant="subtitle1" sx={{ flexGrow: 1 }}>
                                    {row.name}
                                </Typography>
                                {row.check_mode && (
                                    <Chip
                                        size="small"
                                        label={t('configFleet.checkMode', 'Dry run')}
                                    />
                                )}
                                {row.schedule && (
                                    <Chip size="small" color="info" label={row.schedule} />
                                )}
                                <Chip
                                    size="small"
                                    label={t('configFleet.atATime', '{{count}} hosts at once', {
                                        count: row.concurrency,
                                    })}
                                />
                                {canLaunch && (
                                    <Button
                                        size="small"
                                        variant="outlined"
                                        startIcon={<PlayArrowIcon />}
                                        onClick={() => setConfirmLaunch(row)}
                                    >
                                        {t('configFleet.launch', 'Launch')}
                                    </Button>
                                )}
                                {canEdit && (
                                    <Button
                                        size="small"
                                        color="error"
                                        onClick={() => remove(row)}
                                    >
                                        {t('common.delete', 'Delete')}
                                    </Button>
                                )}
                            </Stack>
                            <Typography variant="body2" color="text.secondary">
                                {profileName(row.profile_id)}
                                {' → '}
                                {inventoryName(row.inventory_id)}
                            </Typography>
                        </Box>
                    ))}
                </Stack>
            )}

            <Dialog
                open={creating}
                onClose={() => setCreating(false)}
                maxWidth="sm"
                fullWidth
            >
                <DialogTitle>
                    {t('configFleet.newTemplate', 'New job template')}
                </DialogTitle>
                <DialogContent>
                    <Stack spacing={2} sx={{ mt: 1 }}>
                        <TextField
                            label={t('configFleet.name', 'Name')}
                            value={form.name}
                            onChange={(e) => setForm({ ...form, name: e.target.value })}
                            fullWidth
                        />
                        <TextField
                            select
                            label={t('configFleet.profile', 'Profile')}
                            value={form.profileId}
                            onChange={(e) => setForm({ ...form, profileId: e.target.value })}
                            fullWidth
                        >
                            {profiles.map((p) => (
                                <MenuItem key={p.id} value={p.id}>
                                    {p.name}
                                </MenuItem>
                            ))}
                        </TextField>
                        <TextField
                            select
                            label={t('configFleet.inventory', 'Inventory')}
                            value={form.inventoryId}
                            onChange={(e) =>
                                setForm({ ...form, inventoryId: e.target.value })
                            }
                            fullWidth
                        >
                            {inventories.map((i) => (
                                <MenuItem key={i.id} value={i.id}>
                                    {i.name}
                                </MenuItem>
                            ))}
                        </TextField>
                        <TextField
                            label={t('configFleet.concurrency', 'Hosts at a time')}
                            value={form.concurrency}
                            onChange={(e) =>
                                setForm({ ...form, concurrency: e.target.value })
                            }
                            helperText={t(
                                'configFleet.concurrencyHelp',
                                'How many hosts may be running at once. The server caps this.',
                            )}
                            fullWidth
                        />
                        <TextField
                            label={t('configFleet.schedule', 'Schedule (cron)')}
                            value={form.schedule}
                            onChange={(e) => setForm({ ...form, schedule: e.target.value })}
                            helperText={t(
                                'configFleet.scheduleHelp',
                                'Leave empty to launch by hand only.',
                            )}
                            fullWidth
                        />
                        <FormControlLabel
                            control={
                                <Switch
                                    checked={form.checkMode}
                                    onChange={(e) =>
                                        setForm({ ...form, checkMode: e.target.checked })
                                    }
                                />
                            }
                            label={t(
                                'configFleet.checkModeLabel',
                                'Dry run — report what would change, change nothing',
                            )}
                        />
                    </Stack>
                </DialogContent>
                <DialogActions>
                    <Button onClick={() => setCreating(false)} disabled={saving}>
                        {t('common.cancel', 'Cancel')}
                    </Button>
                    <Button
                        variant="contained"
                        onClick={save}
                        disabled={
                            saving || !form.name || !form.profileId || !form.inventoryId
                        }
                    >
                        {t('common.save', 'Save')}
                    </Button>
                </DialogActions>
            </Dialog>

            <Dialog open={Boolean(confirmLaunch)} onClose={() => setConfirmLaunch(null)}>
                <DialogTitle>
                    {t('configFleet.confirmLaunchTitle', 'Launch this job?')}
                </DialogTitle>
                <DialogContent>
                    {/* Names the profile, the inventory and whether it is live.
                        "Are you sure?" without a subject is not a check, and at
                        fleet scale the subject is the whole question. */}
                    <DialogContentText>
                        {confirmLaunch?.check_mode
                            ? t(
                                  'configFleet.confirmLaunchDry',
                                  'This runs {{profile}} against {{inventory}} as a dry run. ' +
                                      'Nothing will be changed.',
                                  {
                                      profile: profileName(confirmLaunch?.profile_id || ''),
                                      inventory: inventoryName(
                                          confirmLaunch?.inventory_id || '',
                                      ),
                                  },
                              )
                            : t(
                                  'configFleet.confirmLaunchLive',
                                  'This runs {{profile}} for real on every host in ' +
                                      '{{inventory}} and changes them to match it. Delivery ' +
                                      'is held for any host inside a maintenance window.',
                                  {
                                      profile: profileName(confirmLaunch?.profile_id || ''),
                                      inventory: inventoryName(
                                          confirmLaunch?.inventory_id || '',
                                      ),
                                  },
                              )}
                    </DialogContentText>
                </DialogContent>
                <DialogActions>
                    <Button onClick={() => setConfirmLaunch(null)} disabled={launching}>
                        {t('common.cancel', 'Cancel')}
                    </Button>
                    <Button
                        variant="contained"
                        color={confirmLaunch?.check_mode ? 'primary' : 'warning'}
                        onClick={launch}
                        disabled={launching}
                    >
                        {t('configFleet.launch', 'Launch')}
                    </Button>
                </DialogActions>
            </Dialog>
        </Box>
    );
};

export default ConfigJobTemplatesPanel;
