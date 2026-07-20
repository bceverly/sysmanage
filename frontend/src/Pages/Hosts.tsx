// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

import { useNavigate } from "react-router-dom";
import React, { useEffect, useState, useCallback, useMemo } from 'react';
import { DataGrid, GridColDef, GridRowSelectionModel, GridSortModel } from '@mui/x-data-grid';
import Box from '@mui/material/Box';
import { Autocomplete, TextField, ToggleButton, ToggleButtonGroup, Tooltip } from '@mui/material';
import { useTranslation } from 'react-i18next';

import { SysManageHost, doDeleteHost, doGetHosts, doApproveHost, doRefreshAllHostData, doRebootHost, doShutdownHost, doUpdateAgent, doRequestHostDiagnostics } from '../Services/hosts'
import { doDeployOpenTelemetry } from '../Services/opentelemetry'
import { useTablePageSize } from '../hooks/useTablePageSize';
import { useNotificationRefresh } from '../hooks/useNotificationRefresh';
import { useColumnVisibility } from '../hooks/useColumnVisibility';
import SearchBox from '../Components/SearchBox';
import ColumnVisibilityButton from '../Components/ColumnVisibilityButton';
import axiosInstance from '../Services/api';
import { hasPermission, SecurityRoles } from '../Services/permissions';
import { getLicenseInfo } from '../Services/license';
import { broadcastService } from '../Services/broadcast';
import HostsActionBar from '../Components/HostsActionBar';
import { buildHostColumns } from '../Components/hostsColumns';
import { isParentHost, sortHostsGrouped } from '../Components/hostGrouping';

const Hosts = () => {
    const [tableData, setTableData] = useState<SysManageHost[]>([]);
    const [filteredData, setFilteredData] = useState<SysManageHost[]>([]);
    const [selection, setSelection] = useState<GridRowSelectionModel>([]);
    const [loading, setLoading] = useState<boolean>(true);
    const [searchTerm, setSearchTerm] = useState<string>('');
    const [searchColumn, setSearchColumn] = useState<string>('fqdn');
    const [selectedTags, setSelectedTags] = useState<string[]>([]);
    const [allTags, setAllTags] = useState<Array<{id: string, name: string}>>([]);
    const navigate = useNavigate();
    const { t } = useTranslation();

    // Helper to get initial filter from URL hash
    const getFilterFromHash = useCallback((): 'all' | 'parents' | 'children' => {
        const hash = globalThis.location.hash.slice(1); // Remove the '#'
        if (hash === 'parents' || hash === 'children') {
            return hash;
        }
        return 'all';
    }, []);

    // Child host filter: 'all' = show all, 'parents' = hide child hosts, 'children' = child hosts only
    const [childHostFilter, setChildHostFilter] = useState<'all' | 'parents' | 'children'>(getFilterFromHash);

    // Pro+ license module list — used to gate child-host UI (filter,
    // badges).  Without ``container_engine`` loaded, the OSS server
    // refuses child-host operations entirely; the UI follows suit.
    const [licenseModules, setLicenseModules] = useState<string[]>([]);
    useEffect(() => {
        (async () => {
            try {
                const licenseInfo = await getLicenseInfo();
                setLicenseModules(licenseInfo.modules || []);
            } catch {
                setLicenseModules([]);
            }
        })();
    }, []);
    const childHostsLicensed = licenseModules.includes('container_engine');
    const [canApproveHosts, setCanApproveHosts] = useState<boolean>(false);
    const [canDeleteHost, setCanDeleteHost] = useState<boolean>(false);
    const [canViewHostDetails, setCanViewHostDetails] = useState<boolean>(false);
    const [canRebootHost, setCanRebootHost] = useState<boolean>(false);
    const [canShutdownHost, setCanShutdownHost] = useState<boolean>(false);
    const [canUpdateAgent, setCanUpdateAgent] = useState<boolean>(false);
    const [canDeployAntivirus, setCanDeployAntivirus] = useState<boolean>(false);
    const [hasHealthData, setHasHealthData] = useState<boolean>(false);
    const { triggerRefresh } = useNotificationRefresh();

    // Dynamic table page sizing based on window height
    const { pageSize, pageSizeOptions } = useTablePageSize({
        reservedHeight: 250, // Reduced to account for navbar + search box + buttons at bottom
        minRows: 5,
        maxRows: 100,
    });

    // Controlled pagination state for v7
    const [paginationModel, setPaginationModel] = useState({ page: 0, pageSize: 10 });

    // Controlled sort model - empty for "all" mode (custom sort), fqdn asc for other modes
    const [sortModel, setSortModel] = useState<GridSortModel>(
        getFilterFromHash() === 'all' ? [] : [{ field: 'fqdn', sort: 'asc' }]
    );

    // Update pagination when pageSize from hook changes
    useEffect(() => {
        setPaginationModel(prev => ({ ...prev, pageSize }));
    }, [pageSize]);

    // Sync child host filter with URL hash and sort model
    useEffect(() => {
        // Update URL hash when filter changes (without adding to browser history for 'all')
        const newHash = childHostFilter === 'all' ? '' : `#${childHostFilter}`;
        const currentHash = globalThis.location.hash;
        if (newHash !== currentHash) {
            // Use replaceState to avoid polluting browser history
            globalThis.history.replaceState(null, '', `${globalThis.location.pathname}${globalThis.location.search}${newHash}`);
        }
        // In "all" mode, clear DataGrid sort so our custom parent-child grouping is preserved.
        // In other modes, sort by fqdn ascending.
        if (childHostFilter === 'all') {
            setSortModel([]);
        } else {
            setSortModel([{ field: 'fqdn', sort: 'asc' }]);
        }
    }, [childHostFilter]);

    // Listen for hash changes (browser back/forward)
    useEffect(() => {
        const handleHashChange = () => {
            const newFilter = getFilterFromHash();
            if (newFilter !== childHostFilter) {
                setChildHostFilter(newFilter);
            }
        };

        globalThis.addEventListener('hashchange', handleHashChange);
        return () => globalThis.removeEventListener('hashchange', handleHashChange);
    }, [childHostFilter, getFilterFromHash]);

    // Ensure current page size is always in options to avoid MUI warning
    const safePageSizeOptions = useMemo(() => {
        // Defensive check: ensure pageSizeOptions is defined and is an array
        if (!pageSizeOptions || !Array.isArray(pageSizeOptions)) {
            return [5, 10, 25, 50]; // Fallback to default options
        }

        const currentPageSize = paginationModel?.pageSize || 10;
        if (!pageSizeOptions.includes(currentPageSize)) {
            return [...pageSizeOptions, currentPageSize].sort((a, b) => a - b);
        }
        return pageSizeOptions;
    }, [pageSizeOptions, paginationModel?.pageSize]);

    // Column visibility preferences
    const {
        hiddenColumns,
        setHiddenColumns,
        resetPreferences,
        getColumnVisibilityModel,
    } = useColumnVisibility('hosts-grid');

    // Memoize columns to prevent recreation on every render
    const columns: GridColDef[] = useMemo(
        () => buildHostColumns({ t, navigate, canViewHostDetails, tableData, hasHealthData }),
        [t, navigate, canViewHostDetails, tableData, hasHealthData]
    );

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
                return doRebootHost(String(id));
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
                return doShutdownHost(String(id));
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

    const handleUpdateAgentSelected = async () => {
        try {
            // Only update agents on hosts that are active and have privileged agents
            const activePrivilegedSelections = selection.filter(id => {
                const host = filteredData.find(h => h.id.toString() === id.toString());
                return host && host.active && host.is_agent_privileged;
            });

            if (activePrivilegedSelections.length === 0) {
                console.log('No active hosts with privileged agents selected');
                return;
            }

            // Call the API to update agents on the selected active hosts with privileged agents
            const updatePromises = activePrivilegedSelections.map(id => {
                return doUpdateAgent(String(id));
            });

            await Promise.all(updatePromises);
            console.log(`Agent update command sent to ${activePrivilegedSelections.length} hosts`);

            // Clear selection
            setSelection([]);
        } catch (error) {
            console.error('Error updating agents:', error);
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

    const handleBroadcastRefresh = async () => {
        if (!globalThis.confirm(t('broadcast.confirm', 'Send a refresh-inventory broadcast to all connected agents?'))) {
            return;
        }
        try {
            const r = await broadcastService.send({ broadcast_action: 'refresh_inventory' });
            alert(
                t('broadcast.success', 'Broadcast delivered to {{count}} host(s) in {{ms}}ms', {
                    count: r.delivered_count,
                    ms: Math.round(r.elapsed_ms),
                }),
            );
        } catch (error) {
            console.error('Broadcast failed:', error);
            alert(t('broadcast.error', 'Broadcast failed'));
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
            alert(t('hosts.diagnosticsRequested', 'Diagnostics collection requested for host {{hostId}}. Check the host details page to view results when available.', { hostId }));

            // Clear selection
            setSelection([]);
        } catch (error) {
            console.error('Error requesting diagnostics:', error);
            alert(t('hosts.diagnosticsRequestFailed', 'Failed to request diagnostics collection. Please try again.'));
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
            alert(t('hosts.opentelemetryDeploySuccess', `OpenTelemetry deployment queued for ${selection.length} host(s)`, { count: selection.length }));

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
                return host && host.active && host.is_agent_privileged;
            });

            if (eligibleHosts.length === 0) {
                alert(t('hosts.noEligibleHostsForAntivirus', 'No eligible hosts selected. Hosts must be active and in privileged mode for antivirus deployment.'));
                return;
            }

            // Call backend API to deploy antivirus
            const response = await axiosInstance.post('/api/v1/deploy', {
                host_ids: eligibleHosts.map(String)
            });

            // Check for errors
            if (response.data.failed_hosts && response.data.failed_hosts.length > 0) {
                const failedHostsList = response.data.failed_hosts
                    .map((fh: {hostname: string, reason: string}) => `${fh.hostname}: ${fh.reason}`)
                    .join('\n');

                if (response.data.success_count > 0) {
                    alert(t('hosts.antivirusDeployPartialSuccess', `Antivirus deployment initiated for ${response.data.success_count} host(s).\n\nFailed hosts:\n${failedHostsList}`, { count: response.data.success_count, hosts: failedHostsList }));
                } else {
                    alert(t('hosts.antivirusDeployAllFailed', `Antivirus deployment failed for all hosts:\n\n${failedHostsList}`, { hosts: failedHostsList }));
                }
            } else {
                // Show success message
                alert(t('hosts.antivirusDeploySuccess', `Antivirus deployment initiated for ${response.data.success_count} host(s)`, { count: response.data.success_count }));
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
        const intervalId = globalThis.setInterval(() => {
            // Refresh hosts periodically
            refreshHosts();
        }, 60000);

        // Cleanup interval on unmount
        return () => globalThis.clearInterval(intervalId);
    }, [navigate]);

    // Check permissions
    useEffect(() => {
        const checkPermissions = async () => {
            const [approve, deleteHost, viewDetails, reboot, shutdown, updateAgent, deployAntivirus] = await Promise.all([
                hasPermission(SecurityRoles.APPROVE_HOST_REGISTRATION),
                hasPermission(SecurityRoles.DELETE_HOST),
                hasPermission(SecurityRoles.VIEW_HOST_DETAILS),
                hasPermission(SecurityRoles.REBOOT_HOST),
                hasPermission(SecurityRoles.SHUTDOWN_HOST),
                hasPermission(SecurityRoles.UPDATE_AGENT),
                hasPermission(SecurityRoles.DEPLOY_ANTIVIRUS)
            ]);
            setCanApproveHosts(approve);
            setCanDeleteHost(deleteHost);
            setCanViewHostDetails(viewDetails);
            setCanRebootHost(reboot);
            setCanShutdownHost(shutdown);
            setCanUpdateAgent(updateAgent);
            setCanDeployAntivirus(deployAntivirus);
        };
        checkPermissions();
    }, []);

    // Check if any host has health data (from Pro+ health analysis)
    useEffect(() => {
        if (tableData.length > 0) {
            const anyHealthData = tableData.some(
                (h: SysManageHost) => (h as Record<string, unknown>).health_grade
            );
            setHasHealthData(anyHealthData);
        }
    }, [tableData]);


    // Check if any selected hosts need approval - memoized
    const hasPendingSelection = useMemo(() =>
        filteredData.some(host =>
            selection.includes(host.id.toString()) && host.approval_status === 'pending'
        ), [filteredData, selection]);


    // Load all tags for filtering
    const loadAllTags = useCallback(async () => {
        try {
            const response = await axiosInstance.get('/api/v1/tags');
            setAllTags(response.data);
        } catch (error) {
            console.error('Error loading tags:', error);
        }
    }, []);

    // Enhanced search and filter functionality
    const performSearchAndFilter = useCallback(() => {
        let filtered = [...tableData];

        // Apply child host filter
        if (childHostFilter === 'parents') {
            filtered = filtered.filter(isParentHost);
        } else if (childHostFilter === 'children') {
            // Show only child hosts - hosts that have a parent
            filtered = filtered.filter(host => !!host.parent_host_id);
        }
        // 'all' - no filtering needed

        // Apply search filter
        if (searchTerm.trim()) {
            filtered = filtered.filter(host => {
                const fieldValue = host[searchColumn as keyof SysManageHost];
                if (fieldValue == null) {
                    return false;
                }
                // Handle object values by converting to JSON string, otherwise use String()
                const stringValue = typeof fieldValue === 'object'
                    ? JSON.stringify(fieldValue)
                    : String(fieldValue);
                return stringValue.toLowerCase().includes(searchTerm.toLowerCase());
            });
        }

        // Apply tag filter
        if (selectedTags.length > 0) {
            filtered = filtered.filter(host => {
                // Check if host has ALL of the selected tags (AND logic)
                if (!Array.isArray(host.tags)) {
                    return false; // If host has no tags, it doesn't match
                }

                // Check if ALL selected tags are present on this host
                const hostTagIds = new Set(host.tags.map(tag => tag.id));
                return selectedTags.every(selectedTagId =>
                    hostTagIds.has(selectedTagId)
                );
            });
        }

        // Apply custom sorting based on filter mode
        if (childHostFilter === 'all') {
            filtered = sortHostsGrouped(filtered);
        } else {
            filtered.sort((a, b) => (a.fqdn || '').localeCompare(b.fqdn || ''));
        }

        setFilteredData(filtered);
    }, [tableData, searchTerm, searchColumn, selectedTags, childHostFilter]);

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

                {/* Child Host Filter — Pro+ feature, hidden in OSS builds */}
                {childHostsLicensed && (
                    <ToggleButtonGroup
                        value={childHostFilter}
                        exclusive
                        onChange={(_event, newValue) => {
                            if (newValue !== null) {
                                setChildHostFilter(newValue);
                            }
                        }}
                        size="small"
                        aria-label={t('hosts.childHostFilter', 'Child host filter')}
                    >
                        <ToggleButton value="all" aria-label={t('hosts.showAllHosts', 'Show all hosts')}>
                            <Tooltip title={t('hosts.showAllHosts', 'Show all hosts')}>
                                <span>{t('hosts.allHosts', 'All')}</span>
                            </Tooltip>
                        </ToggleButton>
                        <ToggleButton value="parents" aria-label={t('hosts.hideChildHosts', 'Hide child hosts')}>
                            <Tooltip title={t('hosts.hideChildHosts', 'Hide child hosts')}>
                                <span>{t('hosts.parentsOnly', 'Parents')}</span>
                            </Tooltip>
                        </ToggleButton>
                        <ToggleButton value="children" aria-label={t('hosts.childHostsOnly', 'Child hosts only')}>
                            <Tooltip title={t('hosts.childHostsOnly', 'Child hosts only')}>
                                <span>{t('hosts.childrenOnly', 'Children')}</span>
                            </Tooltip>
                        </ToggleButton>
                    </ToggleButtonGroup>
                )}
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
                    rows={filteredData || []}
                    columns={columns || []}
                    loading={loading}
                    paginationModel={paginationModel || { page: 0, pageSize: 10 }}
                    onPaginationModelChange={setPaginationModel}
                    sortModel={sortModel}
                    onSortModelChange={setSortModel}
                    columnVisibilityModel={columnVisibilityModel || { id: false }}
                    pageSizeOptions={safePageSizeOptions}
                    checkboxSelection
                    rowSelectionModel={selection || []}
                    onRowSelectionModelChange={setSelection}
                    localeText={{
                        MuiTablePagination: {
                            labelRowsPerPage: t('common.rowsPerPage'),
                            labelDisplayedRows: ({ from, to, count }: { from: number, to: number, count: number }) => {
                                const countDisplay = count === -1 ? `${t('common.of')} ${to}` : count;
                                return `${from}–${to} ${t('common.of')} ${countDisplay}`;
                            },
                        },
                        noRowsLabel: t('hosts.noRows'),
                        noResultsOverlayLabel: t('hosts.noResults'),
                        footerRowSelected: (count: number) =>
                            count === 1
                                ? `${count.toLocaleString()} ${t('common.rowSelected')}`
                                : `${count.toLocaleString()} ${t('common.rowsSelected')}`,
                    }}
                />
            </Box>

            {/* Action Buttons - scrollable so labels never wrap and
                a narrow viewport gets prev/next arrows.  Container
                still flexShrink: 0 so it stays pinned to the bottom. */}
            <HostsActionBar
                canApproveHosts={canApproveHosts}
                canDeployAntivirus={canDeployAntivirus}
                canRebootHost={canRebootHost}
                canShutdownHost={canShutdownHost}
                canUpdateAgent={canUpdateAgent}
                canDeleteHost={canDeleteHost}
                selectionCount={selection.length}
                hasPendingSelection={hasPendingSelection}
                hasActivePrivilegedSelection={hasActivePrivilegedSelection}
                onApprove={handleApprove}
                onRefreshData={handleRefreshData}
                onBroadcastRefresh={handleBroadcastRefresh}
                onGetDiagnostics={handleGetDiagnostics}
                onDeployOpenTelemetry={handleDeployOpenTelemetry}
                onDeployAntivirus={handleDeployAntivirus}
                onRebootSelected={handleRebootSelected}
                onShutdownSelected={handleShutdownSelected}
                onUpdateAgentSelected={handleUpdateAgentSelected}
                onDelete={handleDelete}
            />
        </Box>
    );
}
 
export default Hosts;