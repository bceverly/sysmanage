import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Chip from '@mui/material/Chip';
import CircularProgress from '@mui/material/CircularProgress';
import Dialog from '@mui/material/Dialog';
import DialogActions from '@mui/material/DialogActions';
import DialogContent from '@mui/material/DialogContent';
import DialogContentText from '@mui/material/DialogContentText';
import DialogTitle from '@mui/material/DialogTitle';
import FormControlLabel from '@mui/material/FormControlLabel';
import IconButton from '@mui/material/IconButton';
import MenuItem from '@mui/material/MenuItem';
import Stack from '@mui/material/Stack';
import Switch from '@mui/material/Switch';
import TextField from '@mui/material/TextField';
import ToggleButton from '@mui/material/ToggleButton';
import ToggleButtonGroup from '@mui/material/ToggleButtonGroup';
import Tooltip from '@mui/material/Tooltip';
import Typography from '@mui/material/Typography';
import Autocomplete from '@mui/material/Autocomplete';
import Alert from '@mui/material/Alert';
import Snackbar from '@mui/material/Snackbar';
import AddIcon from '@mui/icons-material/Add';
import EditIcon from '@mui/icons-material/Edit';
import DeleteIcon from '@mui/icons-material/Delete';
import EventBusyIcon from '@mui/icons-material/EventBusy';
import EventAvailableIcon from '@mui/icons-material/EventAvailable';
import { DataGrid, GridColDef } from '@mui/x-data-grid';

import axiosInstance from '../Services/api.js';
import {
    MaintenanceScope,
    MaintenanceWindow,
    MaintenanceWindowInput,
    ScopeType,
    WindowKind,
    WindowRecurrence,
    maintenanceWindowsService,
} from '../Services/maintenanceWindows';

const WEEKDAYS = ['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun'];

// A small, sensible IANA timezone set; the backend accepts any valid IANA name.
const TIMEZONES = [
    'UTC',
    'America/New_York',
    'America/Chicago',
    'America/Denver',
    'America/Los_Angeles',
    'America/Sao_Paulo',
    'Europe/London',
    'Europe/Paris',
    'Europe/Berlin',
    'Europe/Moscow',
    'Asia/Dubai',
    'Asia/Kolkata',
    'Asia/Shanghai',
    'Asia/Tokyo',
    'Australia/Sydney',
];

interface TagOption {
    id: string;
    name: string;
}
interface HostOption {
    id: string;
    fqdn: string;
}

const emptyForm = (): MaintenanceWindowInput => ({
    name: '',
    description: '',
    enabled: true,
    kind: 'allow',
    recurrence: 'daily',
    timezone: 'UTC',
    start_time: '02:00',
    duration_minutes: 120,
    days_of_week: [],
    starts_at: null,
    ends_at: null,
    scopes: [{ scope_type: 'all' }],
});

const MaintenanceWindows: React.FC = () => {
    const { t } = useTranslation();

    const [windows, setWindows] = useState<MaintenanceWindow[]>([]);
    const [tags, setTags] = useState<TagOption[]>([]);
    const [hosts, setHosts] = useState<HostOption[]>([]);
    const [loading, setLoading] = useState(true);
    const [saving, setSaving] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [toast, setToast] = useState<string | null>(null);

    const [dialogOpen, setDialogOpen] = useState(false);
    const [editId, setEditId] = useState<string | null>(null);
    const [form, setForm] = useState<MaintenanceWindowInput>(emptyForm());
    // Scope editing state (translated to `form.scopes` on save).
    const [scopeType, setScopeType] = useState<ScopeType>('all');
    const [scopeHostIds, setScopeHostIds] = useState<string[]>([]);
    const [scopeTagIds, setScopeTagIds] = useState<string[]>([]);

    const [deleteId, setDeleteId] = useState<string | null>(null);

    const load = useCallback(async () => {
        setLoading(true);
        try {
            const [w, tagRes, hostRes] = await Promise.all([
                maintenanceWindowsService.list(),
                axiosInstance.get('/api/v1/tags'),
                axiosInstance.get('/api/v1/hosts'),
            ]);
            setWindows(w);
            setTags(tagRes.data || []);
            setHosts(
                (hostRes.data || []).map((h: { id: string; fqdn: string }) => ({
                    id: h.id,
                    fqdn: h.fqdn,
                })),
            );
            setError(null);
        } catch (err) {
            console.error('Error loading maintenance windows:', err);
            setError(
                t('maintenanceWindows.loadError', 'Failed to load maintenance windows'),
            );
        } finally {
            setLoading(false);
        }
    }, [t]);

    useEffect(() => {
        load();
    }, [load]);

    const scheduleText = useCallback(
        (w: MaintenanceWindow): string => {
            if (w.recurrence === 'once') {
                return `${w.starts_at ?? '?'} → ${w.ends_at ?? '?'}`;
            }
            const when =
                w.recurrence === 'weekly'
                    ? (w.days_of_week || [])
                          .map((d) => t(`maintenanceWindows.day.${d}`, d))
                          .join(', ')
                    : t('maintenanceWindows.everyDay', 'Every day');
            return `${when} · ${w.start_time} ${w.timezone} · ${w.duration_minutes}m`;
        },
        [t],
    );

    const scopeText = useCallback(
        (w: MaintenanceWindow): string => {
            const scopes = w.scopes || [];
            if (scopes.some((s) => s.scope_type === 'all')) {
                return t('maintenanceWindows.scopeAll', 'All hosts');
            }
            const hostCount = scopes.filter((s) => s.scope_type === 'host').length;
            const tagCount = scopes.filter((s) => s.scope_type === 'tag').length;
            const parts: string[] = [];
            if (hostCount) {
                parts.push(
                    t('maintenanceWindows.nHosts', '{{count}} host(s)', {
                        count: hostCount,
                    }),
                );
            }
            if (tagCount) {
                parts.push(
                    t('maintenanceWindows.nTags', '{{count}} tag(s)', {
                        count: tagCount,
                    }),
                );
            }
            return parts.join(', ') || '—';
        },
        [t],
    );

    const openCreate = () => {
        setEditId(null);
        setForm(emptyForm());
        setScopeType('all');
        setScopeHostIds([]);
        setScopeTagIds([]);
        setDialogOpen(true);
    };

    const openEdit = (w: MaintenanceWindow) => {
        setEditId(w.id);
        setForm({
            name: w.name,
            description: w.description || '',
            enabled: w.enabled,
            kind: w.kind,
            recurrence: w.recurrence,
            timezone: w.timezone,
            start_time: w.start_time || '02:00',
            duration_minutes: w.duration_minutes || 120,
            days_of_week: w.days_of_week || [],
            starts_at: w.starts_at,
            ends_at: w.ends_at,
            scopes: w.scopes,
        });
        const scopes = w.scopes || [];
        if (scopes.some((s) => s.scope_type === 'all')) {
            setScopeType('all');
        } else if (scopes.some((s) => s.scope_type === 'tag')) {
            setScopeType('tag');
        } else {
            setScopeType('host');
        }
        setScopeHostIds(
            scopes.filter((s) => s.host_id).map((s) => s.host_id as string),
        );
        setScopeTagIds(
            scopes.filter((s) => s.tag_id).map((s) => s.tag_id as string),
        );
        setDialogOpen(true);
    };

    const buildScopes = (): MaintenanceScope[] => {
        if (scopeType === 'all') return [{ scope_type: 'all' }];
        if (scopeType === 'host') {
            return scopeHostIds.map((id) => ({ scope_type: 'host', host_id: id }));
        }
        return scopeTagIds.map((id) => ({ scope_type: 'tag', tag_id: id }));
    };

    const handleSave = async () => {
        setSaving(true);
        setError(null);
        try {
            const payload: MaintenanceWindowInput = {
                ...form,
                scopes: buildScopes(),
            };
            if (editId) {
                await maintenanceWindowsService.update(editId, payload);
                setToast(t('maintenanceWindows.updated', 'Maintenance window updated'));
            } else {
                await maintenanceWindowsService.create(payload);
                setToast(t('maintenanceWindows.created', 'Maintenance window created'));
            }
            setDialogOpen(false);
            await load();
        } catch (err: unknown) {
            const detail =
                (err as { response?: { data?: { detail?: string } } })?.response?.data
                    ?.detail;
            setError(
                detail ||
                    t('maintenanceWindows.saveError', 'Failed to save maintenance window'),
            );
        } finally {
            setSaving(false);
        }
    };

    const handleDelete = async () => {
        if (!deleteId) return;
        try {
            await maintenanceWindowsService.remove(deleteId);
            setToast(t('maintenanceWindows.deleted', 'Maintenance window deleted'));
            setDeleteId(null);
            await load();
        } catch (err) {
            console.error('Error deleting maintenance window:', err);
            setError(
                t('maintenanceWindows.deleteError', 'Failed to delete maintenance window'),
            );
        }
    };

    const columns: GridColDef[] = useMemo(
        () => [
            {
                field: 'name',
                headerName: t('maintenanceWindows.name', 'Name'),
                flex: 1,
                minWidth: 160,
            },
            {
                field: 'kind',
                headerName: t('maintenanceWindows.kind', 'Kind'),
                width: 120,
                renderCell: (params) =>
                    params.value === 'blackout' ? (
                        <Chip
                            size="small"
                            color="error"
                            icon={<EventBusyIcon />}
                            label={t('maintenanceWindows.kindBlackout', 'Blackout')}
                        />
                    ) : (
                        <Chip
                            size="small"
                            color="success"
                            icon={<EventAvailableIcon />}
                            label={t('maintenanceWindows.kindAllow', 'Allow')}
                        />
                    ),
            },
            {
                field: 'schedule',
                headerName: t('maintenanceWindows.schedule', 'Schedule'),
                flex: 1.4,
                minWidth: 240,
                valueGetter: (_v, row) => scheduleText(row as MaintenanceWindow),
            },
            {
                field: 'scope',
                headerName: t('maintenanceWindows.scope', 'Scope'),
                flex: 0.8,
                minWidth: 140,
                valueGetter: (_v, row) => scopeText(row as MaintenanceWindow),
            },
            {
                field: 'enabled',
                headerName: t('maintenanceWindows.enabled', 'Enabled'),
                width: 110,
                renderCell: (params) =>
                    params.value ? (
                        <Chip
                            size="small"
                            color="primary"
                            label={t('common.yes', 'Yes')}
                        />
                    ) : (
                        <Chip size="small" label={t('common.no', 'No')} />
                    ),
            },
            {
                field: 'actions',
                headerName: t('common.actions', 'Actions'),
                width: 120,
                sortable: false,
                filterable: false,
                renderCell: (params) => (
                    <>
                        <Tooltip title={t('common.edit', 'Edit')}>
                            <IconButton
                                size="small"
                                onClick={() => openEdit(params.row as MaintenanceWindow)}
                            >
                                <EditIcon fontSize="small" />
                            </IconButton>
                        </Tooltip>
                        <Tooltip title={t('common.delete', 'Delete')}>
                            <IconButton
                                size="small"
                                onClick={() => setDeleteId((params.row as MaintenanceWindow).id)}
                            >
                                <DeleteIcon fontSize="small" />
                            </IconButton>
                        </Tooltip>
                    </>
                ),
            },
        ],
        [t, scheduleText, scopeText],
    );

    if (loading) {
        return (
            <Box sx={{ display: 'flex', justifyContent: 'center', p: 4 }}>
                <CircularProgress />
            </Box>
        );
    }

    const recurring = form.recurrence !== 'once';

    return (
        <Box sx={{ p: 3 }}>
            <Box
                sx={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                    mb: 1,
                }}
            >
                <Typography variant="h5">
                    {t('maintenanceWindows.title', 'Maintenance Windows')}
                </Typography>
                <Button
                    variant="contained"
                    startIcon={<AddIcon />}
                    onClick={openCreate}
                >
                    {t('maintenanceWindows.addWindow', 'Schedule Maintenance')}
                </Button>
            </Box>
            <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
                {t(
                    'maintenanceWindows.intro',
                    'Define when updates and remote commands may run. Hosts inside an ' +
                        'allow window (and outside any blackout) receive changes; other ' +
                        'changes are held and released when the next window opens. Hosts ' +
                        'with no window are unrestricted.',
                )}
            </Typography>

            {error && !dialogOpen && (
                <Alert severity="error" sx={{ mb: 2 }} onClose={() => setError(null)}>
                    {error}
                </Alert>
            )}

            <div style={{ width: '100%', height: 520 }}>
                <DataGrid
                    rows={windows}
                    columns={columns}
                    getRowId={(row) => row.id}
                    initialState={{
                        pagination: { paginationModel: { pageSize: 25 } },
                    }}
                    pageSizeOptions={[10, 25, 50]}
                    disableRowSelectionOnClick
                />
            </div>

            {/* Create / edit dialog */}
            <Dialog
                open={dialogOpen}
                onClose={() => setDialogOpen(false)}
                maxWidth="md"
                fullWidth
            >
                <DialogTitle>
                    {editId
                        ? t('maintenanceWindows.editWindow', 'Edit Maintenance Window')
                        : t('maintenanceWindows.addWindow', 'Schedule Maintenance')}
                </DialogTitle>
                <DialogContent>
                    {error && dialogOpen && (
                        <Alert severity="error" sx={{ mb: 2 }}>
                            {error}
                        </Alert>
                    )}
                    <Stack spacing={2} sx={{ mt: 1 }}>
                        <TextField
                            label={t('maintenanceWindows.name', 'Name')}
                            value={form.name}
                            required
                            fullWidth
                            size="small"
                            onChange={(e) => setForm({ ...form, name: e.target.value })}
                        />
                        <TextField
                            label={t('maintenanceWindows.description', 'Description')}
                            value={form.description ?? ''}
                            fullWidth
                            size="small"
                            onChange={(e) =>
                                setForm({ ...form, description: e.target.value })
                            }
                        />
                        <Stack direction="row" spacing={2}>
                            <TextField
                                select
                                label={t('maintenanceWindows.kind', 'Kind')}
                                value={form.kind}
                                fullWidth
                                size="small"
                                onChange={(e) =>
                                    setForm({
                                        ...form,
                                        kind: e.target.value as WindowKind,
                                    })
                                }
                            >
                                <MenuItem value="allow">
                                    {t('maintenanceWindows.kindAllow', 'Allow')}
                                </MenuItem>
                                <MenuItem value="blackout">
                                    {t('maintenanceWindows.kindBlackout', 'Blackout')}
                                </MenuItem>
                            </TextField>
                            <TextField
                                select
                                label={t('maintenanceWindows.recurrence', 'Recurrence')}
                                value={form.recurrence}
                                fullWidth
                                size="small"
                                onChange={(e) =>
                                    setForm({
                                        ...form,
                                        recurrence: e.target.value as WindowRecurrence,
                                    })
                                }
                            >
                                <MenuItem value="once">
                                    {t('maintenanceWindows.recurrenceOnce', 'One-time')}
                                </MenuItem>
                                <MenuItem value="daily">
                                    {t('maintenanceWindows.recurrenceDaily', 'Daily')}
                                </MenuItem>
                                <MenuItem value="weekly">
                                    {t('maintenanceWindows.recurrenceWeekly', 'Weekly')}
                                </MenuItem>
                            </TextField>
                        </Stack>

                        {form.recurrence === 'weekly' && (
                            <Box>
                                <Typography variant="caption" color="text.secondary">
                                    {t('maintenanceWindows.daysOfWeek', 'Days of week')}
                                </Typography>
                                <Box>
                                    <ToggleButtonGroup
                                        size="small"
                                        value={form.days_of_week}
                                        onChange={(_e, val) =>
                                            setForm({ ...form, days_of_week: val })
                                        }
                                    >
                                        {WEEKDAYS.map((d) => (
                                            <ToggleButton key={d} value={d}>
                                                {t(`maintenanceWindows.day.${d}`, d)}
                                            </ToggleButton>
                                        ))}
                                    </ToggleButtonGroup>
                                </Box>
                            </Box>
                        )}

                        {recurring ? (
                            <Stack direction="row" spacing={2}>
                                <TextField
                                    type="time"
                                    label={t('maintenanceWindows.startTime', 'Start time')}
                                    value={form.start_time ?? ''}
                                    size="small"
                                    fullWidth
                                    slotProps={{ inputLabel: { shrink: true } }}
                                    onChange={(e) =>
                                        setForm({ ...form, start_time: e.target.value })
                                    }
                                />
                                <TextField
                                    type="number"
                                    label={t(
                                        'maintenanceWindows.durationMinutes',
                                        'Duration (minutes)',
                                    )}
                                    value={form.duration_minutes ?? ''}
                                    size="small"
                                    fullWidth
                                    onChange={(e) =>
                                        setForm({
                                            ...form,
                                            duration_minutes: e.target.value
                                                ? Number(e.target.value)
                                                : null,
                                        })
                                    }
                                />
                                <TextField
                                    select
                                    label={t('maintenanceWindows.timezone', 'Timezone')}
                                    value={form.timezone}
                                    size="small"
                                    fullWidth
                                    onChange={(e) =>
                                        setForm({ ...form, timezone: e.target.value })
                                    }
                                >
                                    {TIMEZONES.map((tz) => (
                                        <MenuItem key={tz} value={tz}>
                                            {tz}
                                        </MenuItem>
                                    ))}
                                </TextField>
                            </Stack>
                        ) : (
                            <Stack direction="row" spacing={2}>
                                <TextField
                                    type="datetime-local"
                                    label={t('maintenanceWindows.startsAt', 'Starts at (UTC)')}
                                    value={(form.starts_at ?? '').slice(0, 16)}
                                    size="small"
                                    fullWidth
                                    slotProps={{ inputLabel: { shrink: true } }}
                                    onChange={(e) =>
                                        setForm({
                                            ...form,
                                            starts_at: e.target.value || null,
                                        })
                                    }
                                />
                                <TextField
                                    type="datetime-local"
                                    label={t('maintenanceWindows.endsAt', 'Ends at (UTC)')}
                                    value={(form.ends_at ?? '').slice(0, 16)}
                                    size="small"
                                    fullWidth
                                    slotProps={{ inputLabel: { shrink: true } }}
                                    onChange={(e) =>
                                        setForm({
                                            ...form,
                                            ends_at: e.target.value || null,
                                        })
                                    }
                                />
                            </Stack>
                        )}

                        {/* Scope */}
                        <TextField
                            select
                            label={t('maintenanceWindows.scopeType', 'Applies to')}
                            value={scopeType}
                            size="small"
                            fullWidth
                            onChange={(e) => setScopeType(e.target.value as ScopeType)}
                        >
                            <MenuItem value="all">
                                {t('maintenanceWindows.scopeAll', 'All hosts')}
                            </MenuItem>
                            <MenuItem value="host">
                                {t('maintenanceWindows.scopeHosts', 'Specific hosts')}
                            </MenuItem>
                            <MenuItem value="tag">
                                {t('maintenanceWindows.scopeTags', 'Hosts by tag')}
                            </MenuItem>
                        </TextField>

                        {scopeType === 'host' && (
                            <Autocomplete
                                multiple
                                size="small"
                                options={hosts}
                                getOptionLabel={(o) => o.fqdn}
                                value={hosts.filter((h) => scopeHostIds.includes(h.id))}
                                onChange={(_e, val) =>
                                    setScopeHostIds(val.map((h) => h.id))
                                }
                                renderInput={(params) => (
                                    <TextField
                                        {...params}
                                        label={t('maintenanceWindows.selectHosts', 'Hosts')}
                                    />
                                )}
                            />
                        )}
                        {scopeType === 'tag' && (
                            <Autocomplete
                                multiple
                                size="small"
                                options={tags}
                                getOptionLabel={(o) => o.name}
                                value={tags.filter((tg) => scopeTagIds.includes(tg.id))}
                                onChange={(_e, val) =>
                                    setScopeTagIds(val.map((tg) => tg.id))
                                }
                                renderInput={(params) => (
                                    <TextField
                                        {...params}
                                        label={t('maintenanceWindows.selectTags', 'Tags')}
                                    />
                                )}
                            />
                        )}

                        <FormControlLabel
                            control={
                                <Switch
                                    checked={form.enabled}
                                    onChange={(e) =>
                                        setForm({ ...form, enabled: e.target.checked })
                                    }
                                />
                            }
                            label={t('maintenanceWindows.enabled', 'Enabled')}
                        />
                    </Stack>
                </DialogContent>
                <DialogActions>
                    <Button onClick={() => setDialogOpen(false)}>
                        {t('common.cancel', 'Cancel')}
                    </Button>
                    <Button
                        variant="contained"
                        onClick={handleSave}
                        disabled={saving}
                        startIcon={saving ? <CircularProgress size={16} /> : undefined}
                    >
                        {t('common.save', 'Save')}
                    </Button>
                </DialogActions>
            </Dialog>

            {/* Delete confirm */}
            <Dialog open={!!deleteId} onClose={() => setDeleteId(null)}>
                <DialogTitle>
                    {t('maintenanceWindows.deleteWindow', 'Delete Maintenance Window')}
                </DialogTitle>
                <DialogContent>
                    <DialogContentText>
                        {t(
                            'maintenanceWindows.confirmDelete',
                            'Are you sure you want to delete this maintenance window?',
                        )}
                    </DialogContentText>
                </DialogContent>
                <DialogActions>
                    <Button onClick={() => setDeleteId(null)}>
                        {t('common.cancel', 'Cancel')}
                    </Button>
                    <Button color="error" variant="contained" onClick={handleDelete}>
                        {t('common.delete', 'Delete')}
                    </Button>
                </DialogActions>
            </Dialog>

            <Snackbar
                open={!!toast}
                autoHideDuration={4000}
                onClose={() => setToast(null)}
                message={toast || ''}
            />
        </Box>
    );
};

export default MaintenanceWindows;
