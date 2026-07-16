// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { DataGrid, GridColDef } from '@mui/x-data-grid';
import Box from '@mui/material/Box';
import Stack from '@mui/material/Stack';
import Button from '@mui/material/Button';
import Typography from '@mui/material/Typography';
import Alert from '@mui/material/Alert';
import Dialog from '@mui/material/Dialog';
import DialogTitle from '@mui/material/DialogTitle';
import DialogContent from '@mui/material/DialogContent';
import DialogContentText from '@mui/material/DialogContentText';
import DialogActions from '@mui/material/DialogActions';
import FormControlLabel from '@mui/material/FormControlLabel';
import Checkbox from '@mui/material/Checkbox';
import RefreshIcon from '@mui/icons-material/Refresh';
import StopCircleIcon from '@mui/icons-material/StopCircle';
import SearchBox from './SearchBox';
import {
    HostProcess,
    doGetHostProcesses,
    doRefreshHostProcesses,
    doKillHostProcess,
} from '../Services/processes';
import { hasPermission, SecurityRoles } from '../Services/permissions';

interface ProcessesPanelProps {
    hostId: string;
    hostActive?: boolean;
    isAgentPrivileged?: boolean;
}

const formatBytes = (bytes: number | null): string => {
    if (bytes === null || bytes === undefined) return '';
    const units = ['B', 'KB', 'MB', 'GB', 'TB'];
    let value = bytes;
    let unit = 0;
    while (value >= 1024 && unit < units.length - 1) {
        value /= 1024;
        unit += 1;
    }
    return `${value.toFixed(unit === 0 ? 0 : 1)} ${units[unit]}`;
};

const ProcessesPanel: React.FC<ProcessesPanelProps> = ({
    hostId,
    hostActive,
    isAgentPrivileged,
}) => {
    const { t } = useTranslation();

    const [rows, setRows] = useState<HostProcess[]>([]);
    const [loading, setLoading] = useState<boolean>(true);
    const [error, setError] = useState<string | null>(null);
    const [info, setInfo] = useState<string | null>(null);
    const [canKill, setCanKill] = useState<boolean>(false);
    const [searchTerm, setSearchTerm] = useState<string>('');
    const [searchColumn, setSearchColumn] = useState<string>('process_name');

    // Kill confirmation dialog
    const [killTarget, setKillTarget] = useState<HostProcess | null>(null);
    const [killForce, setKillForce] = useState<boolean>(false);

    const loadProcesses = useCallback(async () => {
        setLoading(true);
        try {
            const data = await doGetHostProcesses(hostId);
            setRows(data);
            setError(null);
        } catch (err) {
            console.error('Error loading processes:', err);
            setError(t('processes.loadError', 'Failed to load processes'));
        } finally {
            setLoading(false);
        }
    }, [hostId, t]);

    useEffect(() => {
        loadProcesses();
    }, [loadProcesses]);

    useEffect(() => {
        hasPermission(SecurityRoles.KILL_HOST_PROCESS).then(setCanKill);
    }, []);

    const handleRefresh = async () => {
        setError(null);
        setInfo(null);
        try {
            const resp = await doRefreshHostProcesses(hostId);
            setInfo(resp.message || t('processes.refreshRequested', 'Refresh requested'));
        } catch (err) {
            console.error('Error refreshing processes:', err);
            setError(t('processes.refreshError', 'Failed to request refresh'));
        }
    };

    const handleConfirmKill = async () => {
        if (!killTarget) return;
        setError(null);
        setInfo(null);
        try {
            const resp = await doKillHostProcess(hostId, killTarget.pid, {
                force: killForce,
                expectedName: killTarget.process_name,
            });
            setInfo(resp.message || t('processes.killRequested', 'Termination requested'));
        } catch (err) {
            console.error('Error killing process:', err);
            setError(t('processes.killError', 'Failed to request termination'));
        } finally {
            setKillTarget(null);
            setKillForce(false);
        }
    };

    const filteredRows = useMemo(() => {
        if (!searchTerm.trim()) return rows;
        const term = searchTerm.toLowerCase();
        return rows.filter((r) => {
            const value = r[searchColumn as keyof HostProcess];
            return value !== null && value !== undefined
                ? String(value).toLowerCase().includes(term)
                : false;
        });
    }, [rows, searchTerm, searchColumn]);

    const collectedAt = rows.length > 0 ? rows[0].collected_at : null;

    const columns: GridColDef[] = useMemo(() => {
        const cols: GridColDef[] = [
            { field: 'pid', headerName: t('processes.pid', 'PID'), width: 90 },
            {
                field: 'process_name',
                headerName: t('processes.name', 'Name'),
                width: 200,
            },
            {
                field: 'username',
                headerName: t('processes.user', 'User'),
                width: 140,
            },
            {
                field: 'cpu_percent',
                headerName: t('processes.cpu', 'CPU %'),
                width: 100,
                type: 'number',
                valueFormatter: (value: number | null) =>
                    value === null || value === undefined ? '' : value.toFixed(1),
            },
            {
                field: 'memory_percent',
                headerName: t('processes.memory', 'Mem %'),
                width: 100,
                type: 'number',
                valueFormatter: (value: number | null) =>
                    value === null || value === undefined ? '' : value.toFixed(1),
            },
            {
                field: 'memory_rss_bytes',
                headerName: t('processes.rss', 'RSS'),
                width: 110,
                type: 'number',
                valueFormatter: (value: number | null) => formatBytes(value),
            },
            {
                field: 'status',
                headerName: t('processes.status', 'Status'),
                width: 110,
            },
            {
                field: 'command_line',
                headerName: t('processes.command', 'Command'),
                flex: 1,
                minWidth: 240,
            },
        ];
        if (canKill) {
            cols.push({
                field: 'actions',
                headerName: t('common.actions', 'Actions'),
                width: 110,
                sortable: false,
                filterable: false,
                renderCell: (params) => (
                    <Button
                        size="small"
                        color="error"
                        startIcon={<StopCircleIcon />}
                        disabled={!hostActive || !isAgentPrivileged}
                        onClick={() => {
                            setKillForce(false);
                            setKillTarget(params.row as HostProcess);
                        }}
                    >
                        {t('processes.kill', 'Kill')}
                    </Button>
                ),
            });
        }
        return cols;
    }, [t, canKill, hostActive, isAgentPrivileged]);

    const searchColumns = [
        { field: 'process_name', label: t('processes.name', 'Name') },
        { field: 'username', label: t('processes.user', 'User') },
        { field: 'command_line', label: t('processes.command', 'Command') },
    ];

    return (
        <Box sx={{ display: 'flex', flexDirection: 'column', height: 'calc(100vh - 260px)', gap: 2 }}>
            {error && (
                <Alert severity="error" onClose={() => setError(null)}>
                    {error}
                </Alert>
            )}
            {info && (
                <Alert severity="success" onClose={() => setInfo(null)}>
                    {info}
                </Alert>
            )}

            <Stack direction="row" spacing={2} alignItems="center" sx={{ flexShrink: 0 }}>
                <Box sx={{ flexGrow: 1 }}>
                    <SearchBox
                        searchTerm={searchTerm}
                        setSearchTerm={setSearchTerm}
                        searchColumn={searchColumn}
                        setSearchColumn={setSearchColumn}
                        columns={searchColumns}
                        placeholder={t('processes.search', 'Search processes')}
                    />
                </Box>
                <Button
                    variant="outlined"
                    startIcon={<RefreshIcon />}
                    onClick={handleRefresh}
                    disabled={!hostActive}
                >
                    {t('processes.refresh', 'Refresh')}
                </Button>
            </Stack>

            {collectedAt && (
                <Typography variant="caption" color="text.secondary" sx={{ flexShrink: 0 }}>
                    {t('processes.collectedAt', 'Snapshot taken')}:{' '}
                    {new Date(
                        collectedAt.endsWith('Z') ? collectedAt : `${collectedAt}Z`,
                    ).toLocaleString()}
                </Typography>
            )}

            <Box sx={{ flexGrow: 1, minHeight: 0 }}>
                <DataGrid
                    rows={filteredRows}
                    columns={columns}
                    loading={loading}
                    getRowId={(row) => row.id}
                    initialState={{
                        sorting: { sortModel: [{ field: 'cpu_percent', sort: 'desc' }] },
                        pagination: { paginationModel: { pageSize: 25 } },
                    }}
                    pageSizeOptions={[25, 50, 100]}
                    disableRowSelectionOnClick
                    localeText={{
                        noRowsLabel: t('processes.noRows', 'No process data yet'),
                    }}
                />
            </Box>

            <Dialog open={killTarget !== null} onClose={() => setKillTarget(null)}>
                <DialogTitle>{t('processes.killTitle', 'Terminate Process')}</DialogTitle>
                <DialogContent>
                    <DialogContentText>
                        {t('processes.killConfirm', {
                            defaultValue:
                                'Terminate process "{{name}}" (PID {{pid}})? This cannot be undone.',
                            name: killTarget?.process_name,
                            pid: killTarget?.pid,
                        })}
                    </DialogContentText>
                    <FormControlLabel
                        sx={{ mt: 1 }}
                        control={
                            <Checkbox
                                checked={killForce}
                                onChange={(e) => setKillForce(e.target.checked)}
                            />
                        }
                        label={t(
                            'processes.forceKill',
                            'Force kill (SIGKILL instead of SIGTERM)',
                        )}
                    />
                </DialogContent>
                <DialogActions>
                    <Button onClick={() => setKillTarget(null)}>
                        {t('common.cancel', 'Cancel')}
                    </Button>
                    <Button color="error" onClick={handleConfirmKill}>
                        {t('processes.kill', 'Kill')}
                    </Button>
                </DialogActions>
            </Dialog>
        </Box>
    );
};

export default ProcessesPanel;
