import { useNavigate } from "react-router-dom";
import React, { useEffect, useState, useCallback, useMemo } from 'react';
import { DataGrid, GridColDef, GridRowSelectionModel } from '@mui/x-data-grid';
import Box from '@mui/material/Box';
import Stack from '@mui/material/Stack';
import Button from '@mui/material/Button';
import DeleteIcon from '@mui/icons-material/Delete';
import CheckIcon from '@mui/icons-material/Check';
import VisibilityIcon from '@mui/icons-material/Visibility';
import SyncIcon from '@mui/icons-material/Sync';
import MedicalServicesIcon from '@mui/icons-material/MedicalServices';
import RestartAltIcon from '@mui/icons-material/RestartAlt';
import PowerSettingsNewIcon from '@mui/icons-material/PowerSettingsNew';
import SystemUpdateAltIcon from '@mui/icons-material/SystemUpdateAlt';
import SecurityIcon from '@mui/icons-material/Security';
import { Chip, IconButton, Autocomplete, TextField } from '@mui/material';
import { useTranslation } from 'react-i18next';

import { SysManageHost, doDeleteHost, doGetHosts, doApproveHost, doRefreshAllHostData, doRebootHost, doShutdownHost, doRequestHostDiagnostics } from '../Services/hosts'
import { doDeployOpenTelemetry } from '../Services/opentelemetry'
import { useTablePageSize } from '../hooks/useTablePageSize';
import { useNotificationRefresh } from '../hooks/useNotificationRefresh';
import { useColumnVisibility } from '../Hooks/useColumnVisibility';
import SearchBox from '../Components/SearchBox';
import ColumnVisibilityButton from '../Components/ColumnVisibilityButton';
import axiosInstance from '../Services/api';
import { hasPermission, SecurityRoles } from '../Services/permissions';

const Hosts = () => {
    const [tableData, setTableData] = useState<SysManageHost[]>([]);
    const [filteredData, setFilteredData] = useState<SysManageHost[]>([]);
    const [selection, setSelection] = useState<GridRowSelectionModel>([]);
    const [loading, setLoading] = useState<boolean>(true);
    const [searchTerm, setSearchTerm] = useState<string>('');
    const [searchColumn, setSearchColumn] = useState<string>('fqdn');
    const [selectedTags, setSelectedTags] = useState<string[]>([]);
    const [allTags, setAllTags] = useState<Array<{id: string, name: string}>>([]);
    const [canApproveHosts, setCanApproveHosts] = useState<boolean>(false);
    const [canDeleteHost, setCanDeleteHost] = useState<boolean>(false);
    const [canViewHostDetails, setCanViewHostDetails] = useState<boolean>(false);
    const [canRebootHost, setCanRebootHost] = useState<boolean>(false);
    const [canShutdownHost, setCanShutdownHost] = useState<boolean>(false);
    const [canDeployAntivirus, setCanDeployAntivirus] = useState<boolean>(false);
    const navigate = useNavigate();
    const { t } = useTranslation();
    const { triggerRefresh } = useNotificationRefresh();

    // Dynamic table page sizing based on window height
    const { pageSize, pageSizeOptions } = useTablePageSize({
        reservedHeight: 250, // Reduced to account for navbar + search box + buttons at bottom
        minRows: 5,
        maxRows: 100,
    });

    // Controlled pagination state for v7
    const [paginationModel, setPaginationModel] = useState({ page: 0, pageSize: 10 });

    // Update pagination when pageSize from hook changes
    useEffect(() => {
        setPaginationModel(prev => ({ ...prev, pageSize }));
    }, [pageSize]);

    // Ensure current page size is always in options to avoid MUI warning
    const safePageSizeOptions = useMemo(() => {
        const currentPageSize = paginationModel.pageSize;
        if (!pageSizeOptions.includes(currentPageSize)) {
            return [...pageSizeOptions, currentPageSize].sort((a, b) => a - b);
        }
        return pageSizeOptions;
    }, [pageSizeOptions, paginationModel.pageSize]);

    // Column visibility preferences
    const {
        hiddenColumns,
        setHiddenColumns,
        resetPreferences,
        getColumnVisibilityModel,
    } = useColumnVisibility('hosts-grid');

    // Memoize columns to prevent recreation on every render
    const columns: GridColDef[] = useMemo(() => [
        { field: 'id', headerName: t('common.id', 'ID'), width: 70 },
        { field: 'fqdn', headerName: t('hosts.fqdn'), width: 200 },
        { field: 'platform', headerName: t('hosts.platform'), width: 120 },
        { field: 'ipv4', headerName: t('hosts.ipv4'), width: 150 },
        { field: 'ipv6', headerName: t('hosts.ipv6'), width: 200 },
        { 
            field: 'status', 
            headerName: t('hosts.status'), 
            width: 280,  // Increased width for status and update chips
            renderCell: (params) => {
                const row = params.row;
                // Server sends naive UTC timestamps as ISO strings with Z suffix
                const lastAccess = new Date(row.last_access);
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
                        {row.reboot_required && (
                            <Chip
                                label={t('hosts.rebootRequired')}
                                color="error"
                                size="small"
                                variant="outlined"
                                sx={{ ml: 0.5 }}
                            />
                        )}
                        {(row.security_updates_count > 0 || row.system_updates_count > 0) && (
                            <Chip
                                label={t('hosts.swUpdates', 'SW Updates')}
                                color={row.security_updates_count > 0 ? 'error' : 'warning'}
                                size="small"
                                variant="outlined"
                                sx={{ ml: 0.5 }}
                                title={
                                    row.security_updates_count > 0 && row.system_updates_count > 0
                                        ? t('hosts.securityAndSystemUpdates', '{{security}} security, {{system}} system updates', {
                                            security: row.security_updates_count,
                                            system: row.system_updates_count
                                        })
                                        : row.security_updates_count > 0
                                        ? t('hosts.securityUpdatesOnly', '{{count}} security updates', { count: row.security_updates_count })
                                        : t('hosts.systemUpdatesOnly', '{{count}} system updates', { count: row.system_updates_count })
                                }
                            />
                        )}
                        {(row.os_upgrades_count && row.os_upgrades_count > 0) && (
                            <Chip
                                label={t('hosts.osUpgrade', 'OS Upgrade')}
                                color="info"
                                size="small"
                                variant="outlined"
                                sx={{ ml: 0.5 }}
                                title={t('hosts.osUpgradeAvailable', 'OS upgrade available for this host')}
                            />
                        )}
                    </Box>
                );
            }
        },
        {
            field: 'is_agent_privileged',
            headerName: t('hosts.privileged'),
            width: 100,
            renderCell: (params) => {
                // Don't show anything if host is down
                if (params.row.status === 'down') {
                    return null;
                }
                const isPrivileged = params.value;
                if (isPrivileged === undefined || isPrivileged === null) {
                    return <span style={{ color: '#666', fontStyle: 'italic' }}>Unknown</span>;
                }
                return (
                    <Chip
                        label={isPrivileged ? t('common.yes') : t('common.no')}
                        color={isPrivileged ? 'success' : 'error'}
                        size="small"
                        variant="filled"
                        title={isPrivileged ? t('hosts.runningPrivileged') : t('hosts.runningUnprivileged')}
                    />
                );
            }
        },
        {
            field: 'script_execution_enabled',
            headerName: t('hosts.scriptsEnabled'),
            width: 120,
            renderCell: (params) => {
                // Don't show anything if host is down
                if (params.row.status === 'down') {
                    return null;
                }
                const scriptsEnabled = params.value;
                if (scriptsEnabled === undefined || scriptsEnabled === null) {
                    return <span style={{ color: '#666', fontStyle: 'italic' }}>Unknown</span>;
                }
                return (
                    <Chip
                        label={scriptsEnabled ? t('common.yes') : t('common.no')}
                        color={scriptsEnabled ? 'success' : 'error'}
                        size="small"
                        variant="filled"
                        title={scriptsEnabled ? t('hosts.scriptsEnabledTooltip') : t('hosts.scriptsDisabledTooltip')}
                    />
                );
            }
        },
        {
            field: 'last_access',
            headerName: t('hosts.lastCheckin'),
            width: 200,
            renderCell: (params) => {
                // Server sends naive UTC timestamps as ISO strings with Z suffix
                const date = new Date(params.value);
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
            field: 'tags',
            headerName: t('hosts.tags', 'Tags'),
            width: 200,
            sortable: false,
            renderCell: (params) => {
                const tags = params.row.tags || [];
                if (tags.length === 0) {
                    return null;
                }
                return (
                    <Box sx={{
                        display: 'flex',
                        gap: 0.5,
                        flexWrap: 'wrap',
                        alignItems: 'center',
                        justifyContent: 'center',
                        height: '100%'
                    }}>
                        {tags.map((tag: { id: string; name: string }) => (
                            <Chip
                                key={tag.id}
                                label={tag.name}
                                size="small"
                                variant="filled"
                                sx={{
                                    fontSize: '0.75rem',
                                    backgroundColor: '#1976d2',
                                    color: '#ffffff',
                                    '&:hover': {
                                        backgroundColor: '#1565c0'
                                    }
                                }}
                            />
                        ))}
                    </Box>
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
                canViewHostDetails ? (
                    <IconButton
                        color="primary"
                        size="small"
                        onClick={() => navigate(`/hosts/${params.row.id}`)}
                        title={t('common.view')}
                    >
                        <VisibilityIcon />
                    </IconButton>
                ) : null
            )
        }
    ], [t, navigate, canViewHostDetails]);

    // Search columns configuration (excluding irrelevant columns)
    const searchColumns = [
        { field: 'fqdn', label: t('hosts.fqdn') },
        { field: 'platform', label: t('hosts.platform') },
        { field: 'ipv4', label: t('hosts.ipv4') },
        { field: 'ipv6', label: t('hosts.ipv6') }
    ];

    const handleApprove = async () => {
        try {
            // Get selected hosts that need approval
            const selectedHosts = filteredData.filter(host =>
                selection.includes(host.id.toString()) && host.approval_status === 'pending'
            );
            
            // Approve each selected pending host
            const approvePromises = selectedHosts.map(host => 
                doApproveHost(host.id.toString())
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
                return doDeleteHost(id.toString());
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

    const handleRebootSelected = async () => {
        try {
            // Only reboot hosts that are active and have privileged agents
            const activePrivilegedSelections = selection.filter(id => {
                const host = filteredData.find(h => h.id.toString() === id.toString());
                return host && host.active && host.is_agent_privileged;
            });

            if (activePrivilegedSelections.length === 0) {
                console.log('No active hosts with privileged agents selected');
                return;
            }

            // Call the API to reboot the selected active hosts with privileged agents
            const rebootPromises = activePrivilegedSelections.map(id => {
                return doRebootHost(Number(id));
            });
            
            await Promise.all(rebootPromises);
            console.log(`Reboot command sent to ${activePrivilegedSelections.length} hosts`);
            
            // Clear selection
            setSelection([]);
        } catch (error) {
            console.error('Error rebooting hosts:', error);
            // Still clear selection even if there was an error
            setSelection([]);
        }
    }

    const handleShutdownSelected = async () => {
        try {
            // Only shutdown hosts that are active and have privileged agents
            const activePrivilegedSelections = selection.filter(id => {
                const host = filteredData.find(h => h.id.toString() === id.toString());
                return host && host.active && host.is_agent_privileged;
            });

            if (activePrivilegedSelections.length === 0) {
                console.log('No active hosts with privileged agents selected');
                return;
            }

            // Call the API to shutdown the selected active hosts with privileged agents
            const shutdownPromises = activePrivilegedSelections.map(id => {
                return doShutdownHost(Number(id));
            });
            
            await Promise.all(shutdownPromises);
            console.log(`Shutdown command sent to ${activePrivilegedSelections.length} hosts`);
            
            // Clear selection
            setSelection([]);
        } catch (error) {
            console.error('Error shutting down hosts:', error);
            // Still clear selection even if there was an error
            setSelection([]);
        }
    }

    // Helper function to check if any selected hosts can be rebooted/shutdown - memoized
    const hasActivePrivilegedSelection = useMemo(() =>
        selection.some(id => {
            const host = filteredData.find(h => h.id.toString() === id.toString());
            return host && host.active && host.is_agent_privileged;
        }), [selection, filteredData]);

    const handleRefreshData = async () => {
        try {
            // Request comprehensive data refresh for selected hosts
            const refreshPromises = selection.map(id => {
                return doRefreshAllHostData(id.toString());
            });

            await Promise.all(refreshPromises);

            // Clear selection after successful requests
            setSelection([]);
        } catch {
            // Still clear selection even if there was an error
            setSelection([]);
        }
    }

    const handleGetDiagnostics = async () => {
        try {
            if (selection.length === 0) return;

            const hostId = String(selection[0]);
            console.log(`Requesting diagnostics for host ${hostId}`);

            // Request diagnostics collection
            await doRequestHostDiagnostics(hostId);
            console.log('Diagnostics collection requested successfully');

            // Show success message
            alert(`Diagnostics collection requested for host ${hostId}. Check the host details page to view results when available.`);

            // Clear selection
            setSelection([]);
        } catch (error) {
            console.error('Error requesting diagnostics:', error);
            alert('Failed to request diagnostics collection. Please try again.');
            setSelection([]);
        }
    }
    const handleDeployOpenTelemetry = async () => {
        try {
            if (selection.length === 0) return;

            // Deploy to all selected hosts - backend will validate eligibility
            const deploymentPromises = selection.map(hostId => doDeployOpenTelemetry(String(hostId)));
            await Promise.all(deploymentPromises);

            // Show success message
            alert(t('hosts.opentelemetryDeploySuccess', `OpenTelemetry deployment queued for ${selection.length} host(s)`));

            // Refresh hosts
            await refreshHosts();

            // Clear selection
            setSelection([]);
        } catch (error) {
            console.error('Error deploying OpenTelemetry:', error);
            alert(t('hosts.opentelemetryDeployFailed', 'Failed to deploy OpenTelemetry. Please try again.'));
            setSelection([]);
        }
    }

    const handleDeployAntivirus = async () => {
        try {
            if (selection.length === 0) return;

            // Deploy to all selected hosts that are active and in privileged mode
            const eligibleHosts = selection.filter(hostId => {
                const host = tableData.find(h => h.id === hostId);
                return host && host.active && host.privileged_mode;
            });

            if (eligibleHosts.length === 0) {
                alert(t('hosts.noEligibleHostsForAntivirus', 'No eligible hosts selected. Hosts must be active and in privileged mode for antivirus deployment.'));
                return;
            }

            // Call backend API to deploy antivirus
            const response = await axiosInstance.post('/api/deploy', {
                host_ids: eligibleHosts.map(id => String(id))
            });

            // Check for errors
            if (response.data.failed_hosts && response.data.failed_hosts.length > 0) {
                const failedHostsList = response.data.failed_hosts
                    .map((fh: {hostname: string, reason: string}) => `${fh.hostname}: ${fh.reason}`)
                    .join('\n');

                if (response.data.success_count > 0) {
                    alert(t('hosts.antivirusDeployPartialSuccess', `Antivirus deployment initiated for ${response.data.success_count} host(s).\n\nFailed hosts:\n${failedHostsList}`));
                } else {
                    alert(t('hosts.antivirusDeployAllFailed', `Antivirus deployment failed for all hosts:\n\n${failedHostsList}`));
                }
            } else {
                // Show success message
                alert(t('hosts.antivirusDeploySuccess', `Antivirus deployment initiated for ${response.data.success_count} host(s)`));
            }

            // Refresh hosts
            await refreshHosts();

            // Clear selection
            setSelection([]);
        } catch (error) {
            console.error('Error deploying antivirus:', error);
            alert(t('hosts.antivirusDeployFailed', 'Failed to deploy antivirus. Please try again.'));
            setSelection([]);
        }
    }

    const refreshHosts = async () => {
        try {
            setLoading(true);
            const response = await doGetHosts();
            setTableData(response);
        } catch (error) {
            console.error('Error refreshing hosts:', error);
            // Don't show error to user for background refresh failures
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        if (!localStorage.getItem('bearer_token')) {
            navigate("/login");
        }

        // Initial load
        refreshHosts();

        // Set up periodic refresh every 60 seconds (increased from 30 to reduce load)
        const intervalId = window.setInterval(() => {
            // Refresh hosts periodically
            refreshHosts();
        }, 60000);

        // Cleanup interval on unmount
        return () => window.clearInterval(intervalId);
    }, [navigate]);

    // Check permissions
    useEffect(() => {
        const checkPermissions = async () => {
            const [approve, deleteHost, viewDetails, reboot, shutdown, deployAntivirus] = await Promise.all([
                hasPermission(SecurityRoles.APPROVE_HOST_REGISTRATION),
                hasPermission(SecurityRoles.DELETE_HOST),
                hasPermission(SecurityRoles.VIEW_HOST_DETAILS),
                hasPermission(SecurityRoles.REBOOT_HOST),
                hasPermission(SecurityRoles.SHUTDOWN_HOST),
                hasPermission(SecurityRoles.DEPLOY_ANTIVIRUS)
            ]);
            setCanApproveHosts(approve);
            setCanDeleteHost(deleteHost);
            setCanViewHostDetails(viewDetails);
            setCanRebootHost(reboot);
            setCanShutdownHost(shutdown);
            setCanDeployAntivirus(deployAntivirus);
        };
        checkPermissions();
    }, []);


    // Check if any selected hosts need approval - memoized
    const hasPendingSelection = useMemo(() =>
        filteredData.some(host =>
            selection.includes(host.id.toString()) && host.approval_status === 'pending'
        ), [filteredData, selection]);


    // Load all tags for filtering
    const loadAllTags = useCallback(async () => {
        try {
            const response = await axiosInstance.get('/api/tags');
            setAllTags(response.data);
        } catch (error) {
            console.error('Error loading tags:', error);
        }
    }, []);

    // Enhanced search and filter functionality
    const performSearchAndFilter = useCallback(() => {
        let filtered = [...tableData];

        // Apply search filter
        if (searchTerm.trim()) {
            filtered = filtered.filter(host => {
                const fieldValue = host[searchColumn as keyof SysManageHost];
                if (fieldValue === null || fieldValue === undefined) {
                    return false;
                }
                return String(fieldValue).toLowerCase().includes(searchTerm.toLowerCase());
            });
        }

        // Apply tag filter
        if (selectedTags.length > 0) {
            filtered = filtered.filter(host => {
                // Check if host has ALL of the selected tags (AND logic)
                if (!host.tags || !Array.isArray(host.tags)) {
                    return false; // If host has no tags, it doesn't match
                }
                
                // Check if ALL selected tags are present on this host
                const hostTagIds = host.tags.map(tag => tag.id);
                return selectedTags.every(selectedTagId => 
                    hostTagIds.includes(selectedTagId)
                );
            });
        }

        setFilteredData(filtered);
    }, [tableData, searchTerm, searchColumn, selectedTags]);

    // Update filtered data when any filter criteria changes
    React.useEffect(() => {
        performSearchAndFilter();
    }, [performSearchAndFilter]);

    // Load tags on component mount
    React.useEffect(() => {
        loadAllTags();
    }, [loadAllTags]);

    // Memoize column visibility model
    const columnVisibilityModel = useMemo(() => ({
        id: false,
        ...getColumnVisibilityModel(),
    }), [getColumnVisibilityModel]);

    return (
        <Box sx={{
            display: 'flex',
            flexDirection: 'column',
            height: 'calc(100vh - 120px)', // Full viewport height minus navbar and padding
            gap: 2,
            p: 2
        }}>
            {/* Search and Filter Controls */}
            <Box sx={{
                p: 2,
                bgcolor: 'background.paper',
                borderRadius: 1,
                boxShadow: 1,
                display: 'flex',
                alignItems: 'center',
                gap: 3,
                flexWrap: 'wrap',
                flexShrink: 0
            }}>
                {/* Search Box inline */}
                <SearchBox
                    searchTerm={searchTerm}
                    setSearchTerm={setSearchTerm}
                    searchColumn={searchColumn}
                    setSearchColumn={setSearchColumn}
                    columns={searchColumns}
                    placeholder={t('search.searchHosts', 'Search hosts')}
                    inline={true}
                />

                {/* Spacer for significant horizontal separation */}
                <Box sx={{ flexGrow: 1, minWidth: 50 }} />

                {/* Tag Filter */}
                <Autocomplete
                    multiple
                    size="small"
                    options={allTags}
                    getOptionLabel={(option) => option.name}
                    value={allTags.filter(tag => selectedTags.includes(tag.id))}
                    onChange={(event, newValue) => {
                        setSelectedTags(newValue.map(tag => tag.id));
                    }}
                    renderInput={(params) => (
                        <TextField
                            {...params}
                            label={t('hosts.filterByTags', 'Filter by Tags')}
                            placeholder={t('hosts.selectTags', 'Select tags')}
                        />
                    )}
                    sx={{ minWidth: 300, flexGrow: 1 }}
                />
            </Box>

            {/* Column Visibility Button */}
            <Box sx={{ mr: 2, display: 'flex', alignItems: 'center', justifyContent: 'flex-end', flexShrink: 0 }}>
                <ColumnVisibilityButton
                    columns={columns
                        .filter(col => col.field !== 'actions')
                        .map(col => ({ field: col.field, headerName: col.headerName || col.field }))}
                    hiddenColumns={hiddenColumns}
                    onColumnsChange={setHiddenColumns}
                    onReset={resetPreferences}
                />
            </Box>

            {/* DataGrid - flexGrow to fill available space */}
            <Box sx={{ flexGrow: 1, minHeight: 0 }}>
                <DataGrid
                    rows={filteredData}
                    columns={columns}
                    loading={loading}
                    paginationModel={paginationModel}
                    onPaginationModelChange={setPaginationModel}
                    initialState={{
                        sorting: {
                            sortModel: [{ field: 'fqdn', sort: 'asc'}],
                        },
                    }}
                    columnVisibilityModel={columnVisibilityModel}
                    pageSizeOptions={safePageSizeOptions}
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
                        footerRowSelected: (count: number) =>
                            count !== 1
                                ? `${count.toLocaleString()} ${t('common.rowsSelected')}`
                                : `${count.toLocaleString()} ${t('common.rowSelected')}`,
                    }}
                />
            </Box>

            {/* Action Buttons - flexShrink: 0 to stay at bottom */}
            <Stack direction="row" spacing={2} sx={{ flexShrink: 0, pb: 2 }}>
                {canApproveHosts && (
                    <Button
                        variant="outlined"
                        startIcon={<CheckIcon />}
                        disabled={!hasPendingSelection}
                        onClick={handleApprove}
                        color="success"
                    >
                        {t('hosts.approveSelected', { defaultValue: 'Approve Selected' })}
                    </Button>
                )}
                <Button 
                    variant="outlined" 
                    startIcon={<SyncIcon />} 
                    disabled={selection.length === 0}
                    onClick={handleRefreshData}
                    color="info"
                >
                    {t('hosts.refreshAllData', 'Refresh All Data')}
                </Button>
                <Button
                    variant="outlined"
                    startIcon={<MedicalServicesIcon />}
                    disabled={selection.length !== 1}
                    onClick={handleGetDiagnostics}
                    color="secondary"
                >
                    {t('hosts.getDiagnostics', 'Get Diagnostics')}
                </Button>
                <Button
                    variant="outlined"
                    startIcon={<SystemUpdateAltIcon />}
                    disabled={selection.length === 0}
                    onClick={handleDeployOpenTelemetry}
                    color="success"
                >
                    {t('hosts.deployOpenTelemetry', 'Deploy OpenTelemetry')}
                </Button>
                {canDeployAntivirus && (
                    <Button
                        variant="outlined"
                        startIcon={<SecurityIcon />}
                        disabled={selection.length === 0}
                        onClick={handleDeployAntivirus}
                        color="success"
                    >
                        {t('hosts.deployAntivirus', 'Deploy Antivirus')}
                    </Button>
                )}
                {canRebootHost && (
                    <Button
                        variant="outlined"
                        startIcon={<RestartAltIcon />}
                        disabled={!hasActivePrivilegedSelection}
                        onClick={handleRebootSelected}
                        color="warning"
                    >
                        {t('hosts.rebootSelected', 'Reboot Selected')}
                    </Button>
                )}
                {canShutdownHost && (
                    <Button
                        variant="outlined"
                        startIcon={<PowerSettingsNewIcon />}
                        disabled={!hasActivePrivilegedSelection}
                        onClick={handleShutdownSelected}
                        color="error"
                    >
                        {t('hosts.shutdownSelected', 'Shutdown Selected')}
                    </Button>
                )}
                {canDeleteHost && (
                    <Button variant="outlined" startIcon={<DeleteIcon />} disabled={selection.length === 0} onClick={handleDelete}>
                        {t('common.delete')} {t('common.selected', { defaultValue: 'Selected' })}
                    </Button>
                )}
            </Stack>
        </Box>
    );
}
 
export default Hosts;