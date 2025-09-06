import { useNavigate } from "react-router-dom";
import React, { useEffect, useState } from 'react';
import { DataGrid, GridColDef, GridRowSelectionModel } from '@mui/x-data-grid';
import Box from '@mui/material/Box';
import Stack from '@mui/material/Stack';
import Button from '@mui/material/Button';
import DeleteIcon from '@mui/icons-material/Delete';
import CheckIcon from '@mui/icons-material/Check';
import VisibilityIcon from '@mui/icons-material/Visibility';
import SyncIcon from '@mui/icons-material/Sync';
import { Chip, Typography, IconButton } from '@mui/material';
import { useTranslation } from 'react-i18next';

import { SysManageHost, doDeleteHost, doGetHosts, doApproveHost, doRefreshAllHostData } from '../Services/hosts'
import { useTablePageSize } from '../hooks/useTablePageSize';
import { useNotificationRefresh } from '../hooks/useNotificationRefresh';

const Hosts = () => {
    const [tableData, setTableData] = useState<SysManageHost[]>([]);
    const [selection, setSelection] = useState<GridRowSelectionModel>([]);
    const [lastRefresh, setLastRefresh] = useState<Date | null>(null);
    const navigate = useNavigate();
    const { t } = useTranslation();
    const { triggerRefresh } = useNotificationRefresh();
    
    // Dynamic table page sizing based on window height
    const { pageSize, pageSizeOptions } = useTablePageSize({
        reservedHeight: 350, // Account for navbar, title, buttons, margins, and action buttons below table
        minRows: 5,
        maxRows: 50,
    });

    const columns: GridColDef[] = [
        { field: 'id', headerName: t('common.id', 'ID'), width: 70 },
        { field: 'fqdn', headerName: t('hosts.fqdn'), width: 200 },
        { field: 'ipv4', headerName: t('hosts.ipv4'), width: 150 },
        { field: 'ipv6', headerName: t('hosts.ipv6'), width: 200 },
        { 
            field: 'status', 
            headerName: t('hosts.status'), 
            width: 200,  // Increased width for dual status chips
            renderCell: (params) => {
                const row = params.row;
                // Server returns timezone-aware timestamps  
                const rawLastAccess = row.last_access;
                const utcLastAccess = typeof rawLastAccess === 'string' && 
                    !rawLastAccess.endsWith('Z') && 
                    !rawLastAccess.includes('+') && 
                    !rawLastAccess.includes('-')
                    ? rawLastAccess + 'Z'
                    : rawLastAccess;
                
                const lastAccess = new Date(utcLastAccess);
                const now = new Date();
                const diffMinutes = Math.floor((now.getTime() - lastAccess.getTime()) / 60000);
                
                // Consider host "up" if last access was within 5 minutes
                const isRecentlyActive = diffMinutes <= 5;
                const displayStatus = isRecentlyActive ? 'up' : 'down';
                
                // Check if approval is needed
                const needsApproval = row.approval_status === 'pending';
                
                return (
                    <Box>
                        <Chip 
                            label={displayStatus === 'up' ? t('hosts.up') : t('hosts.down')}
                            color={displayStatus === 'up' ? 'success' : 'error'}
                            size="small"
                            title={t('hosts.lastSeen', 'Last seen {{minutes}} minutes ago', { minutes: diffMinutes })}
                        />
                        {needsApproval && (
                            <Chip 
                                label={t('hosts.approvalNeeded')}
                                color="warning"
                                size="small"
                                variant="outlined"
                                sx={{ ml: 0.5 }}
                            />
                        )}
                    </Box>
                );
            }
        },
        { 
            field: 'last_access', 
            headerName: t('hosts.lastCheckin'), 
            width: 200,
            renderCell: (params) => {
                // Server returns timezone-aware timestamps
                const rawValue = params.value;
                // Don't modify if it already has timezone info (+ or - offset) or Z
                const utcTimestamp = typeof rawValue === 'string' && 
                    !rawValue.endsWith('Z') && 
                    !rawValue.includes('+') && 
                    !rawValue.includes('-')
                    ? rawValue + 'Z'  // Add UTC marker only if no timezone info
                    : rawValue;
                
                const date = new Date(utcTimestamp);
                const now = new Date();
                
                
                // Check if date is valid
                if (isNaN(date.getTime())) {
                    return <span style={{ color: '#f44336' }}>{t('hosts.invalidDate', 'Invalid date')}</span>;
                }
                
                const diffSeconds = Math.floor((now.getTime() - date.getTime()) / 1000);
                
                // Handle negative differences (clock skew)
                const absDiff = Math.abs(diffSeconds);
                let timeText = '';
                
                if (absDiff < 60) {
                    timeText = diffSeconds < 0 ? t('hosts.justNow', 'Just now') : t('hosts.secondsAgo', '{{seconds}}s ago', { seconds: absDiff });
                } else if (absDiff < 3600) {
                    timeText = t('hosts.minutesAgo', '{{minutes}}m ago', { minutes: Math.floor(absDiff / 60) });
                } else if (absDiff < 86400) {
                    timeText = t('hosts.hoursAgo', '{{hours}}h ago', { hours: Math.floor(absDiff / 3600) });
                } else {
                    timeText = t('hosts.daysAgo', '{{days}}d ago', { days: Math.floor(absDiff / 86400) });
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
        },
        {
            field: 'actions',
            headerName: t('common.actions'),
            width: 100,
            sortable: false,
            filterable: false,
            renderCell: (params) => (
                <IconButton
                    color="primary"
                    size="small"
                    onClick={() => navigate(`/hosts/${params.row.id}`)}
                    title={t('common.view')}
                >
                    <VisibilityIcon />
                </IconButton>
            )
        }
    ]

    const handleApprove = async () => {
        try {
            // Get selected hosts that need approval
            const selectedHosts = tableData.filter(host => 
                selection.includes(host.id) && host.approval_status === 'pending'
            );
            
            // Approve each selected pending host
            const approvePromises = selectedHosts.map(host => 
                doApproveHost(BigInt(host.id.toString()))
            );
            
            await Promise.all(approvePromises);
            
            // Refresh the data from the server
            const updatedHosts = await doGetHosts();
            setTableData(updatedHosts);
            
            // Trigger notification bell refresh
            await triggerRefresh();
            
            // Clear selection
            setSelection([]);
        } catch (error) {
            console.error('Error approving hosts:', error);
            // Still clear selection even if there was an error
            setSelection([]);
        }
    };

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
            
            // Trigger notification bell refresh
            await triggerRefresh();
            
            // Clear selection
            setSelection([]);
        } catch (error) {
            console.error('Error deleting hosts:', error);
            // Still clear selection even if there was an error
            setSelection([]);
        }
    }

    const handleRefreshData = async () => {
        try {
            // Request comprehensive data refresh (OS + hardware) for selected hosts
            const refreshPromises = selection.map(id => {
                const theID = BigInt(id.toString());
                return doRefreshAllHostData(theID);
            });
            
            await Promise.all(refreshPromises);
            
            // Clear selection after successful requests
            setSelection([]);
            
            // Optional: Show success message or refresh data after a delay
            console.log(`Comprehensive data refresh requested for ${selection.length} hosts`);
        } catch (error) {
            console.error('Error requesting comprehensive data refresh:', error);
            // Still clear selection even if there was an error
            setSelection([]);
        }
    }

    const refreshHosts = async () => {
        try {
            const response = await doGetHosts();
            setTableData(response);
            setLastRefresh(new Date());
            console.log('Hosts refreshed:', response.length, 'hosts at', new Date().toISOString());
        } catch (error) {
            console.error('Error refreshing hosts:', error);
        }
    };

    useEffect(() => {
        if (!localStorage.getItem('bearer_token')) {
            navigate("/login");
        }
        
        // Initial load
        refreshHosts();
        
        // Set up periodic refresh every 30 seconds
        const intervalId = window.setInterval(() => refreshHosts(), 30000);
        
        // Cleanup interval on unmount
        return () => window.clearInterval(intervalId);
    }, [navigate]);
    const formatLastRefresh = () => {
        if (!lastRefresh) return t('hosts.never', 'never');
        const now = new Date();
        const diffSeconds = Math.floor((now.getTime() - lastRefresh.getTime()) / 1000);
        
        if (diffSeconds < 10) return t('hosts.justNow', 'just now');
        if (diffSeconds < 60) return t('hosts.secondsAgo', '{{seconds}}s ago', { seconds: diffSeconds });
        if (diffSeconds < 3600) return t('hosts.minutesAgo', '{{minutes}}m ago', { minutes: Math.floor(diffSeconds / 60) });
        return lastRefresh.toLocaleTimeString();
    };

    // Check if any selected hosts need approval
    const hasPendingSelection = tableData.some(host => 
        selection.includes(host.id) && host.approval_status === 'pending'
    );

    return (
        <div>
            {/* Subtle Refresh Status */}
            <Box sx={{ mb: 1, mr: 2, display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <Typography variant="caption" color="textSecondary" sx={{ display: 'flex', alignItems: 'center' }}>
                    {t('hosts.updated', 'Updated')} {formatLastRefresh()} <span style={{ marginLeft: '4px', color: '#4caf50', fontSize: '8px' }}>●</span>
                </Typography>
                <Typography variant="caption" color="textSecondary">
                    {t('hosts.autoRefresh', 'Auto-refresh')}: 30s
                </Typography>
            </Box>
            
            <div  style={{ height: `${Math.min(600, Math.max(300, (pageSize + 2) * 52 + 120))}px`, width: '99%' }}>
                <DataGrid
                    rows={tableData}
                    columns={columns}
                    initialState={{
                        pagination: {
                            paginationModel: { page: 0, pageSize: pageSize },
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
                    pageSizeOptions={pageSizeOptions}
                    checkboxSelection
                    rowSelectionModel={selection}
                    onRowSelectionModelChange={setSelection}
                    localeText={{
                        MuiTablePagination: {
                            labelRowsPerPage: t('common.rowsPerPage'),
                            labelDisplayedRows: ({ from, to, count }: { from: number, to: number, count: number }) =>
                                `${from}–${to} ${t('common.of')} ${count !== -1 ? count : `${t('common.of')} ${to}`}`,
                        },
                        noRowsLabel: t('hosts.noRows'),
                        noResultsOverlayLabel: t('hosts.noResults'),
                        // Additional DataGrid locale text
                        footerRowSelected: (count: number) => 
                            count !== 1 
                                ? `${count.toLocaleString()} ${t('common.rowsSelected')}`
                                : `${count.toLocaleString()} ${t('common.rowSelected')}`,
                    }}
                />
            </div>
            <Box component="section">&nbsp;</Box>
            <Stack direction="row" spacing={2}>
                <Button 
                    variant="outlined" 
                    startIcon={<CheckIcon />} 
                    disabled={!hasPendingSelection}
                    onClick={handleApprove}
                    color="success"
                >
                    {t('hosts.approveSelected', { defaultValue: 'Approve Selected' })}
                </Button>
                <Button 
                    variant="outlined" 
                    startIcon={<SyncIcon />} 
                    disabled={selection.length === 0}
                    onClick={handleRefreshData}
                    color="info"
                >
                    {t('hosts.refreshAllData', 'Refresh All Data')}
                </Button>
                <Button variant="outlined" startIcon={<DeleteIcon />} disabled={selection.length === 0} onClick={handleDelete}>
                    {t('common.delete')} {t('common.selected', { defaultValue: 'Selected' })}
                </Button>
            </Stack>
        </div>
    );
}
 
export default Hosts;