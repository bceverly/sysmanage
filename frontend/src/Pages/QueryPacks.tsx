// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

import React, { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import Alert from '@mui/material/Alert';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Chip from '@mui/material/Chip';
import CircularProgress from '@mui/material/CircularProgress';
import Dialog from '@mui/material/Dialog';
import DialogActions from '@mui/material/DialogActions';
import DialogContent from '@mui/material/DialogContent';
import DialogContentText from '@mui/material/DialogContentText';
import DialogTitle from '@mui/material/DialogTitle';
import IconButton from '@mui/material/IconButton';
import Stack from '@mui/material/Stack';
import Tab from '@mui/material/Tab';
import Tabs from '@mui/material/Tabs';
import TextField from '@mui/material/TextField';
import Tooltip from '@mui/material/Tooltip';
import Typography from '@mui/material/Typography';
import AddIcon from '@mui/icons-material/Add';
import DeleteIcon from '@mui/icons-material/Delete';
import EditIcon from '@mui/icons-material/Edit';
import Checkbox from '@mui/material/Checkbox';
import FormControlLabel from '@mui/material/FormControlLabel';
import { DataGrid, GridColDef } from '@mui/x-data-grid';

import LiveQueryPanel from '../Components/LiveQueryPanel';
import { doGetHosts, SysManageHost } from '../Services/hosts';

import { formatUTCTimestamp } from '../utils/dateUtils';
import { hasPermission, SecurityRoles } from '../Services/permissions';
import {
    QueryPack,
    QueryPackQuery,
    QueryPackRun,
    createPack,
    deletePack,
    getCatalog,
    getPacks,
    getRuns,
    updatePack,
    validatePack,
} from '../Services/queryPackService';

/**
 * How a run status is rendered.
 *
 * `partial` is deliberately WARNING and not success-with-a-note: it means
 * some queries could not be answered on that host, and a host that could not
 * answer must never look like a host that answered "nothing found". That
 * distinction is the entire point of the Phase 21.1 fact substrate, and this
 * is the last place it can be thrown away.
 */
const STATUS_COLOR: Record<string, 'success' | 'warning' | 'error' | 'default'> = {
    success: 'success',
    partial: 'warning',
    failed: 'error',
    pending: 'default',
};

/**
 * Human labels, with a real fallback each.
 *
 * The fallback is spelled out rather than reusing the raw status value: a
 * missing catalog key would otherwise show an operator the bare word
 * `partial`, which is both untranslated and -- worse -- easy to read as a
 * lesser success rather than as "this host could not answer some of it".
 */
const STATUS_LABEL: Record<string, string> = {
    success: 'Success',
    partial: 'Partially answered',
    failed: 'Failed',
    pending: 'Pending',
};

interface QueryForm {
    name: string;
    sql: string;
    required_tables: string;
}

interface PackForm {
    name: string;
    description: string;
    queries: QueryForm[];
}

const emptyQuery = (): QueryForm => ({ name: '', sql: '', required_tables: '' });

const emptyForm = (): PackForm => ({
    name: '',
    description: '',
    queries: [emptyQuery()],
});

/** Pull the server's explanation out of an axios error, or fall back. */
const messageFrom = (err: unknown, fallback: string): string => {
    const detail = (err as { response?: { data?: { detail?: unknown } } })?.response
        ?.data?.detail;
    return typeof detail === 'string' && detail ? detail : fallback;
};

/** Form rows -> API queries. Tables are typed comma-separated. */
const toQueries = (rows: QueryForm[]): QueryPackQuery[] =>
    rows.map((row) => ({
        name: row.name.trim(),
        sql: row.sql,
        required_tables: row.required_tables
            .split(',')
            .map((t) => t.trim())
            .filter(Boolean),
    }));

const QueryPacks: React.FC = () => {
    const { t } = useTranslation();
    const [tab, setTab] = useState(0);
    const [packs, setPacks] = useState<QueryPack[]>([]);
    const [catalog, setCatalog] = useState<QueryPack[]>([]);
    const [runs, setRuns] = useState<QueryPackRun[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);

    const [dialogOpen, setDialogOpen] = useState(false);
    const [dialogError, setDialogError] = useState<string | null>(null);
    const [editId, setEditId] = useState<string | null>(null);
    const [form, setForm] = useState<PackForm>(emptyForm());
    const [saving, setSaving] = useState(false);
    const [problems, setProblems] = useState<string[]>([]);

    const [deleteTarget, setDeleteTarget] = useState<QueryPack | null>(null);
    const [canAdd, setCanAdd] = useState(false);
    const [canEdit, setCanEdit] = useState(false);
    const [canDelete, setCanDelete] = useState(false);

    // Live-query host selection. Loaded lazily: the list is only needed once
    // the operator opens that tab, and it is the one tab that needs it.
    const [hosts, setHosts] = useState<SysManageHost[]>([]);
    const [selectedHosts, setSelectedHosts] = useState<string[]>([]);

    const load = useCallback(async () => {
        try {
            const [mine, curated, recent] = await Promise.all([
                getPacks(),
                getCatalog(),
                getRuns(),
            ]);
            setPacks(mine);
            setCatalog(curated);
            setRuns(recent);
            setError(null);
        } catch (err) {
            setError(
                messageFrom(err, t('queryPacks.loadFailed', 'Could not load query packs')),
            );
        } finally {
            setLoading(false);
        }
    }, [t]);

    useEffect(() => {
        load();
    }, [load]);

    useEffect(() => {
        if (tab !== 3 || hosts.length > 0) return;
        doGetHosts()
            .then((all) =>
                // Only ACTIVE hosts: dispatching to an inactive one buries the
                // command in a queue that may never drain, while the operator
                // watches a target that will never answer.
                setHosts(all.filter((h) => h.active && h.approval_status === 'approved')),
            )
            .catch(() => setHosts([]));
    }, [tab, hosts.length]);

    useEffect(() => {
        const check = async () => {
            const [add, edit, remove] = await Promise.all([
                hasPermission(SecurityRoles.ADD_SCRIPT),
                hasPermission(SecurityRoles.EDIT_SCRIPT),
                hasPermission(SecurityRoles.DELETE_SCRIPT),
            ]);
            setCanAdd(add);
            setCanEdit(edit);
            setCanDelete(remove);
        };
        check();
    }, []);

    const openCreate = () => {
        setEditId(null);
        setForm(emptyForm());
        setProblems([]);
        setDialogError(null);
        setDialogOpen(true);
    };

    const openEdit = (pack: QueryPack) => {
        setEditId(pack.id);
        setForm({
            name: pack.name,
            description: pack.description ?? '',
            queries: (pack.queries ?? []).map((q) => ({
                name: q.name,
                sql: q.sql,
                required_tables: (q.required_tables ?? []).join(', '),
            })),
        });
        setProblems([]);
        setDialogError(null);
        setDialogOpen(true);
    };

    /**
     * Check without saving.
     *
     * Separate from save so an author can find out the SQL is acceptable
     * before committing a name -- a rejected save leaves no draft behind.
     */
    const check = async () => {
        try {
            const verdict = await validatePack({
                name: form.name,
                queries: toQueries(form.queries),
            });
            setProblems(verdict.problems);
            if (verdict.valid) {
                setDialogError(null);
            }
        } catch (err) {
            setDialogError(
                messageFrom(err, t('queryPacks.validateFailed', 'Could not check the pack')),
            );
        }
    };

    const save = async () => {
        setSaving(true);
        setDialogError(null);
        try {
            const payload = {
                name: form.name,
                description: form.description,
                queries: toQueries(form.queries),
            };
            if (editId) {
                await updatePack(editId, payload);
            } else {
                await createPack(payload);
            }
            setDialogOpen(false);
            await load();
        } catch (err) {
            setDialogError(
                messageFrom(err, t('queryPacks.saveFailed', 'Could not save the query pack')),
            );
        } finally {
            setSaving(false);
        }
    };

    const confirmDelete = async () => {
        if (!deleteTarget) return;
        try {
            await deletePack(deleteTarget.id);
            setDeleteTarget(null);
            await load();
        } catch (err) {
            setError(
                messageFrom(err, t('queryPacks.deleteFailed', 'Could not delete the query pack')),
            );
        }
    };

    const packColumns: GridColDef[] = [
        { field: 'name', headerName: t('queryPacks.name', 'Name'), flex: 1, minWidth: 160 },
        {
            field: 'query_count',
            headerName: t('queryPacks.queries', 'Queries'),
            width: 110,
        },
        { field: 'version', headerName: t('queryPacks.version', 'Version'), width: 100 },
        {
            field: 'description',
            headerName: t('queryPacks.description', 'Description'),
            flex: 1,
            minWidth: 180,
        },
        {
            field: 'actions',
            headerName: t('queryPacks.actions', 'Actions'),
            width: 130,
            sortable: false,
            renderCell: (params) => (
                <Stack direction="row" spacing={1}>
                    <Tooltip title={t('queryPacks.edit', 'Edit')}>
                        <span>
                            <IconButton
                                size="small"
                                disabled={!canEdit}
                                onClick={() => openEdit(params.row as QueryPack)}
                            >
                                <EditIcon fontSize="small" />
                            </IconButton>
                        </span>
                    </Tooltip>
                    <Tooltip title={t('queryPacks.delete', 'Delete')}>
                        <span>
                            <IconButton
                                size="small"
                                disabled={!canDelete}
                                onClick={() => setDeleteTarget(params.row as QueryPack)}
                            >
                                <DeleteIcon fontSize="small" />
                            </IconButton>
                        </span>
                    </Tooltip>
                </Stack>
            ),
        },
    ];

    const catalogColumns: GridColDef[] = [
        { field: 'name', headerName: t('queryPacks.name', 'Name'), flex: 1, minWidth: 160 },
        {
            field: 'category',
            headerName: t('queryPacks.category', 'Category'),
            width: 150,
        },
        {
            field: 'query_count',
            headerName: t('queryPacks.queries', 'Queries'),
            width: 110,
        },
        {
            field: 'description',
            headerName: t('queryPacks.description', 'Description'),
            flex: 1,
            minWidth: 200,
        },
    ];

    const runColumns: GridColDef[] = [
        {
            field: 'pack_name',
            headerName: t('queryPacks.pack', 'Pack'),
            flex: 1,
            minWidth: 150,
        },
        {
            field: 'status',
            headerName: t('queryPacks.status', 'Status'),
            width: 130,
            renderCell: (params) => (
                <Chip
                    size="small"
                    label={t(
                        // NOT `queryPacks.status`: that key is the column
                        // header above, a leaf string. Using one key as both a
                        // leaf and a namespace makes the seeder flatten the
                        // object and silently lose every label under it.
                        `queryPacks.runStatus.${params.value}`,
                        STATUS_LABEL[String(params.value)] ?? String(params.value),
                    )}
                    color={STATUS_COLOR[String(params.value)] ?? 'default'}
                />
            ),
        },
        {
            field: 'queries_ok',
            headerName: t('queryPacks.answered', 'Answered'),
            width: 110,
        },
        {
            // Surfaced as its own column rather than folded into a total: a
            // host that could not answer is a different fact from a host that
            // answered and found nothing, and an operator needs to see which.
            field: 'queries_not_covered',
            headerName: t('queryPacks.notCovered', 'Not covered'),
            width: 130,
        },
        {
            field: 'queries_failed',
            headerName: t('queryPacks.failed', 'Failed'),
            width: 100,
        },
        {
            field: 'started_at',
            headerName: t('queryPacks.started', 'Started'),
            width: 180,
            renderCell: (params) =>
                params.value ? formatUTCTimestamp(String(params.value)) : '',
        },
    ];

    if (loading) {
        return (
            <Box sx={{ display: 'flex', justifyContent: 'center', p: 4 }}>
                <CircularProgress />
            </Box>
        );
    }

    return (
        <Box sx={{ p: 3 }}>
            <Stack
                direction="row"
                justifyContent="space-between"
                alignItems="center"
                sx={{ mb: 2 }}
            >
                <Typography variant="h5">
                    {t('queryPacks.title', 'Query Packs')}
                </Typography>
                <Button
                    variant="contained"
                    startIcon={<AddIcon />}
                    disabled={!canAdd}
                    onClick={openCreate}
                >
                    {t('queryPacks.create', 'New Pack')}
                </Button>
            </Stack>

            <Typography variant="body2" sx={{ mb: 2 }} color="text.secondary">
                {t(
                    'queryPacks.intro',
                    'Query packs run SQL against the fact tables every agent serves, so one query works across every platform.',
                )}
            </Typography>

            {error && (
                <Alert severity="error" sx={{ mb: 2 }}>
                    {error}
                </Alert>
            )}

            <Tabs value={tab} onChange={(_e, v) => setTab(v)} sx={{ mb: 2 }}>
                <Tab label={t('queryPacks.tabMine', 'My Packs')} />
                <Tab label={t('queryPacks.tabCatalog', 'Curated Catalog')} />
                <Tab label={t('queryPacks.tabRuns', 'Recent Runs')} />
                <Tab label={t('queryPacks.tabLive', 'Live Query')} />
            </Tabs>

            {tab === 0 && (
                <div style={{ height: 480, width: '100%' }}>
                    <DataGrid rows={packs} columns={packColumns} getRowId={(r) => r.id} />
                </div>
            )}

            {tab === 1 && (
                <div style={{ height: 480, width: '100%' }}>
                    <DataGrid
                        rows={catalog}
                        columns={catalogColumns}
                        getRowId={(r) => r.id}
                    />
                </div>
            )}

            {tab === 2 && (
                <div style={{ height: 480, width: '100%' }}>
                    <DataGrid rows={runs} columns={runColumns} getRowId={(r) => r.id} />
                </div>
            )}

            {tab === 3 && (
                <Box>
                    <Typography variant="subtitle2" sx={{ mb: 1 }}>
                        {t('queryPacks.selectHosts', 'Hosts to query')}
                    </Typography>
                    <Box sx={{ maxHeight: 200, overflowY: 'auto', mb: 1 }}>
                        {hosts.map((h) => (
                            <FormControlLabel
                                key={h.id}
                                control={
                                    <Checkbox
                                        size="small"
                                        checked={selectedHosts.includes(h.id)}
                                        onChange={(e) =>
                                            setSelectedHosts((prev) =>
                                                e.target.checked
                                                    ? [...prev, h.id]
                                                    : prev.filter((x) => x !== h.id),
                                            )
                                        }
                                    />
                                }
                                label={`${h.fqdn} (${h.platform ?? '?'})`}
                            />
                        ))}
                    </Box>
                    <LiveQueryPanel hostIds={selectedHosts} />
                </Box>
            )}

            <Dialog
                open={dialogOpen}
                onClose={() => setDialogOpen(false)}
                maxWidth="md"
                fullWidth
            >
                <DialogTitle>
                    {editId
                        ? t('queryPacks.editTitle', 'Edit Query Pack')
                        : t('queryPacks.createTitle', 'New Query Pack')}
                </DialogTitle>
                <DialogContent>
                    {dialogError && (
                        <Alert severity="error" sx={{ mb: 2 }}>
                            {dialogError}
                        </Alert>
                    )}
                    {problems.length > 0 && (
                        <Alert severity="warning" sx={{ mb: 2 }}>
                            <ul style={{ margin: 0, paddingLeft: '1.2em' }}>
                                {problems.map((p) => (
                                    <li key={p}>{p}</li>
                                ))}
                            </ul>
                        </Alert>
                    )}
                    {problems.length === 0 && (
                        <Box sx={{ mb: 2 }} />
                    )}
                    <TextField
                        fullWidth
                        margin="dense"
                        label={t('queryPacks.name', 'Name')}
                        value={form.name}
                        onChange={(e) => setForm({ ...form, name: e.target.value })}
                    />
                    <TextField
                        fullWidth
                        margin="dense"
                        label={t('queryPacks.description', 'Description')}
                        value={form.description}
                        onChange={(e) =>
                            setForm({ ...form, description: e.target.value })
                        }
                    />

                    {form.queries.map((query, index) => (
                        <Box
                            key={index}
                            sx={{ mt: 2, p: 2, border: '1px solid', borderColor: 'divider' }}
                        >
                            <Stack direction="row" justifyContent="space-between">
                                <Typography variant="subtitle2">
                                    {t('queryPacks.query', 'Query')} {index + 1}
                                </Typography>
                                <IconButton
                                    size="small"
                                    onClick={() =>
                                        setForm({
                                            ...form,
                                            queries: form.queries.filter(
                                                (_q, i) => i !== index,
                                            ),
                                        })
                                    }
                                >
                                    <DeleteIcon fontSize="small" />
                                </IconButton>
                            </Stack>
                            <TextField
                                fullWidth
                                margin="dense"
                                label={t('queryPacks.queryName', 'Query name')}
                                value={query.name}
                                onChange={(e) => {
                                    const queries = [...form.queries];
                                    queries[index] = {
                                        ...query,
                                        name: e.target.value,
                                    };
                                    setForm({ ...form, queries });
                                }}
                            />
                            <TextField
                                fullWidth
                                multiline
                                minRows={3}
                                margin="dense"
                                label={t('queryPacks.sql', 'SQL')}
                                value={query.sql}
                                onChange={(e) => {
                                    const queries = [...form.queries];
                                    queries[index] = { ...query, sql: e.target.value };
                                    setForm({ ...form, queries });
                                }}
                            />
                            <TextField
                                fullWidth
                                margin="dense"
                                label={t('queryPacks.requiredTables', 'Fact tables used')}
                                helperText={t(
                                    'queryPacks.requiredTablesHelp',
                                    'Comma-separated. A host that does not serve these reports the query as not covered rather than returning nothing.',
                                )}
                                value={query.required_tables}
                                onChange={(e) => {
                                    const queries = [...form.queries];
                                    queries[index] = {
                                        ...query,
                                        required_tables: e.target.value,
                                    };
                                    setForm({ ...form, queries });
                                }}
                            />
                        </Box>
                    ))}

                    <Button
                        sx={{ mt: 2 }}
                        startIcon={<AddIcon />}
                        onClick={() =>
                            setForm({ ...form, queries: [...form.queries, emptyQuery()] })
                        }
                    >
                        {t('queryPacks.addQuery', 'Add Query')}
                    </Button>
                </DialogContent>
                <DialogActions>
                    <Button onClick={check}>{t('queryPacks.check', 'Check')}</Button>
                    <Button onClick={() => setDialogOpen(false)}>
                        {t('queryPacks.cancel', 'Cancel')}
                    </Button>
                    <Button variant="contained" onClick={save} disabled={saving}>
                        {t('queryPacks.save', 'Save')}
                    </Button>
                </DialogActions>
            </Dialog>

            <Dialog open={!!deleteTarget} onClose={() => setDeleteTarget(null)}>
                <DialogTitle>{t('queryPacks.deleteTitle', 'Delete Query Pack')}</DialogTitle>
                <DialogContent>
                    <DialogContentText>
                        {t(
                            'queryPacks.deleteConfirm',
                            'This removes the pack and every assignment that uses it.',
                        )}
                    </DialogContentText>
                </DialogContent>
                <DialogActions>
                    <Button onClick={() => setDeleteTarget(null)}>
                        {t('queryPacks.cancel', 'Cancel')}
                    </Button>
                    <Button color="error" variant="contained" onClick={confirmDelete}>
                        {t('queryPacks.delete', 'Delete')}
                    </Button>
                </DialogActions>
            </Dialog>
        </Box>
    );
};

export default QueryPacks;
