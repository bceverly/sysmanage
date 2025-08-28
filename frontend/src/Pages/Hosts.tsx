import { useNavigate } from "react-router-dom";
import React, { useEffect, useState } from 'react';
import { DataGrid, GridColDef, GridRowSelectionModel } from '@mui/x-data-grid';
import Box from '@mui/material/Box';
import Stack from '@mui/material/Stack';
import Button from '@mui/material/Button';
import DeleteIcon from '@mui/icons-material/Delete';
import RefreshIcon from '@mui/icons-material/Refresh';
import { Chip, Typography, CircularProgress } from '@mui/material';
import { useTranslation } from 'react-i18next';

import { SysManageHost, doDeleteHost, doGetHosts } from '../Services/hosts'

const Hosts = () => {
    const [tableData, setTableData] = useState<SysManageHost[]>([]);
    const [selection, setSelection] = useState<GridRowSelectionModel>([]);
    const [lastRefresh, setLastRefresh] = useState<Date | null>(null);
    const [isRefreshing, setIsRefreshing] = useState<boolean>(false);
    const navigate = useNavigate();
    const { t } = useTranslation();

    const columns: GridColDef[] = [
        { field: 'id', headerName: 'ID', width: 70 },
        { field: 'fqdn', headerName: t('hosts.fqdn'), width: 200 },
        { field: 'ipv4', headerName: t('hosts.ipv4'), width: 150 },
        { field: 'ipv6', headerName: t('hosts.ipv6'), width: 200 },
        { 
            field: 'status', 
            headerName: t('hosts.status'), 
            width: 120,
            renderCell: (params) => {
                const row = params.row;
                // Server returns UTC timestamps without 'Z', so we need to add it
                const rawLastAccess = row.last_access;
                const utcLastAccess = typeof rawLastAccess === 'string' && !rawLastAccess.endsWith('Z')
                    ? rawLastAccess + 'Z'
                    : rawLastAccess;
                
                const lastAccess = new Date(utcLastAccess);
                const now = new Date();
                const diffMinutes = Math.floor((now.getTime() - lastAccess.getTime()) / 60000);
                
                // Consider host "up" if last access was within 5 minutes
                const isRecentlyActive = diffMinutes <= 5;
                const displayStatus = isRecentlyActive ? 'up' : 'down';
                
                return (
                    <Chip 
                        label={displayStatus === 'up' ? t('hosts.up') : t('hosts.down')}
                        color={displayStatus === 'up' ? 'success' : 'error'}
                        size="small"
                        title={`Last seen ${diffMinutes} minutes ago`}
                    />
                );
            }
        },
        { 
            field: 'last_access', 
            headerName: t('hosts.lastCheckin'), 
            width: 200,
            renderCell: (params) => {
                // Server returns UTC timestamps without 'Z', so we need to add it
                // This forces JavaScript to parse as UTC instead of local time
                const rawValue = params.value;
                const utcTimestamp = typeof rawValue === 'string' && !rawValue.endsWith('Z')
                    ? rawValue + 'Z'  // Add UTC marker if missing
                    : rawValue;
                
                const date = new Date(utcTimestamp);
                const now = new Date();
                
                
                // Check if date is valid
                if (isNaN(date.getTime())) {
                    return <span style={{ color: '#f44336' }}>Invalid date</span>;
                }
                
                const diffSeconds = Math.floor((now.getTime() - date.getTime()) / 1000);
                
                // Handle negative differences (clock skew)
                const absDiff = Math.abs(diffSeconds);
                let timeText = '';
                
                if (absDiff < 60) {
                    timeText = diffSeconds < 0 ? 'Just now' : `${absDiff}s ago`;
                } else if (absDiff < 3600) {
                    timeText = `${Math.floor(absDiff / 60)}m ago`;
                } else if (absDiff < 86400) {
                    timeText = `${Math.floor(absDiff / 3600)}h ago`;
                } else {
                    timeText = `${Math.floor(absDiff / 86400)}d ago`;
                }
                
                return (
                    <div title={date.toLocaleString()}>
                        <div style={{ fontSize: '0.85em', color: absDiff < 120 ? '#4caf50' : absDiff < 300 ? '#ff9800' : '#f44336' }}>
                            {timeText}
                        </div>
                        <div style={{ fontSize: '0.7em', color: '#666' }}>
                            {date.toLocaleTimeString()}
                        </div>
                    </div>
                );
            }
        }
    ]

    const handleDelete = async () => {
        try {
            // Call the API to remove the selected rows
            const deletePromises = selection.map(id => {
                const theID = BigInt(id.toString());
                return doDeleteHost(theID);
            });
            
            await Promise.all(deletePromises);
            
            // Refresh the data from the server
            const updatedHosts = await doGetHosts();
            setTableData(updatedHosts);
            
            // Clear selection
            setSelection([]);
        } catch (error) {
            console.error('Error deleting hosts:', error);
        }
    }

    const refreshHosts = async (showLoading: boolean = false) => {
        try {
            if (showLoading) {
                setIsRefreshing(true);
            }
            const response = await doGetHosts();
            setTableData(response);
            setLastRefresh(new Date());
            console.log('Hosts refreshed:', response.length, 'hosts at', new Date().toISOString());
        } catch (error) {
            console.error('Error refreshing hosts:', error);
        } finally {
            if (showLoading) {
                setIsRefreshing(false);
            }
        }
    };

    useEffect(() => {
        if (!localStorage.getItem('bearer_token')) {
            navigate("/login");
        }
        
        // Initial load with loading indicator
        refreshHosts(true);
        
        // Set up periodic refresh every 30 seconds (background refresh)
        const intervalId = window.setInterval(() => refreshHosts(false), 30000);
        
        // Cleanup interval on unmount
        return () => window.clearInterval(intervalId);
    }, [navigate]);
    const formatLastRefresh = () => {
        if (!lastRefresh) return 'never';
        const now = new Date();
        const diffSeconds = Math.floor((now.getTime() - lastRefresh.getTime()) / 1000);
        
        if (diffSeconds < 10) return 'just now';
        if (diffSeconds < 60) return `${diffSeconds}s ago`;
        if (diffSeconds < 3600) return `${Math.floor(diffSeconds / 60)}m ago`;
        return lastRefresh.toLocaleTimeString();
    };

    return (
        <div>
            {/* Subtle Refresh Status */}
            <Box sx={{ mb: 1, mr: 2, display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <Typography variant="caption" color="textSecondary" sx={{ display: 'flex', alignItems: 'center' }}>
                    {isRefreshing ? (
                        <><CircularProgress size={12} sx={{ mr: 1 }} /> Refreshing...</>
                    ) : (
                        <>Updated {formatLastRefresh()} <span style={{ marginLeft: '4px', color: '#4caf50', fontSize: '8px' }}>●</span></>
                    )}
                </Typography>
                <Typography variant="caption" color="textSecondary">
                    Auto-refresh: 30s
                </Typography>
            </Box>
            
            <div  style={{ height: 400, width: '99%' }}>
                <DataGrid
                    rows={tableData}
                    columns={columns}
                    initialState={{
                        pagination: {
                        paginationModel: { page: 0, pageSize: 5 },
                        },
                        sorting: {
                            sortModel: [{ field: 'fqdn', sort: 'asc'}],
                        },
                        columns: {
                            columnVisibilityModel: {
                                id: false,
                            },
                        },
                    }}
                    pageSizeOptions={[5, 10]}
                    checkboxSelection
                    onRowSelectionModelChange={setSelection}
                    localeText={{
                        MuiTablePagination: {
                            labelRowsPerPage: t('common.rowsPerPage'),
                            labelDisplayedRows: ({ from, to, count }: { from: number, to: number, count: number }) =>
                                `${from}–${to} ${t('common.of')} ${count !== -1 ? count : `${t('common.of')} ${to}`}`,
                        },
                    }}
                />
            </div>
            <Box component="section">&nbsp;</Box>
            <Stack direction="row" spacing={2}>
                <Button 
                    variant="outlined" 
                    startIcon={<RefreshIcon />} 
                    onClick={() => refreshHosts(true)}
                    disabled={isRefreshing}
                >
                    {isRefreshing ? 'Refreshing...' : 'Refresh Now'}
                </Button>
                <Button variant="outlined" startIcon={<DeleteIcon />} disabled={selection.length === 0} onClick={handleDelete}>
                    {t('common.delete')} {t('common.selected', { defaultValue: 'Selected' })}
                </Button>
            </Stack>
        </div>
    );
}
 
export default Hosts;