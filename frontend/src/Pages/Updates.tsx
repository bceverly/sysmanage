import React, { useState, useEffect, useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import { useSearchParams } from 'react-router-dom';
import {
  IoRefresh,
  IoCheckbox,
  IoSquareOutline,
  IoWarning,
  IoShieldCheckmark,
  IoHardwareChip,
  IoApps,
  IoFilter,
  IoPlay,
  IoSearch
} from 'react-icons/io5';
import {
  updatesService,
  UpdateStatsSummary,
  PackageUpdate,
  UpdatesResponse,
  HostUpdatesResponse
} from '../Services/updates';
import { hasPermission, SecurityRoles } from '../Services/permissions';
import { useNotificationRefresh } from '../hooks/useNotificationRefresh';
import './css/Updates.css';

interface SelectedUpdate {
  hostId: number;
  packageName: string;
  packageManager: string;
}

interface HostWithUpdates {
  hostId: number;
  hostname: string;
  updateCount: number;
}

interface UpdateStatus {
  status: 'pending' | 'success' | 'failed';
  newVersion?: string;
  timestamp: number;
}

interface UpdatePackage {
  package_name: string;
  package_manager: string;
  new_version?: string;
  error?: string;
}

interface HostResult {
  updated_packages?: UpdatePackage[];
  failed_packages?: UpdatePackage[];
}


const Updates: React.FC = () => {
  const [searchParams] = useSearchParams();
  const { t } = useTranslation();
  const { triggerRefresh } = useNotificationRefresh();
  
  const [updateStats, setUpdateStats] = useState<UpdateStatsSummary | null>(null);
  const [updates, setUpdates] = useState<PackageUpdate[]>([]);
  const [selectedUpdates, setSelectedUpdates] = useState<Set<string>>(new Set());
  const [updateStatuses, setUpdateStatuses] = useState<Map<string, UpdateStatus>>(new Map());
  const [isLoading, setIsLoading] = useState(true);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [currentPage, setCurrentPage] = useState(0);
  const [totalCount, setTotalCount] = useState(0);
  const [hostsWithUpdates, setHostsWithUpdates] = useState<HostWithUpdates[]>([]);
  const [hostSpecificStats, setHostSpecificStats] = useState<HostUpdatesResponse | null>(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [filters, setFilters] = useState({
    security_only: searchParams.get('securityOnly') === 'true' || searchParams.get('filter') === 'security',
    system_only: false,
    application_only: false,
    package_manager: '',
    host_id: searchParams.get('host') || ''
  });

  // Permission state
  const [canApplySoftwareUpdate, setCanApplySoftwareUpdate] = useState<boolean>(false);

  const ITEMS_PER_PAGE = 50;

  // Check permissions
  useEffect(() => {
    const checkPermission = async () => {
      const applySoftwareUpdate = await hasPermission(SecurityRoles.APPLY_SOFTWARE_UPDATE);
      setCanApplySoftwareUpdate(applySoftwareUpdate);
    };
    checkPermission();
  }, []);

  const fetchUpdatesSummary = useCallback(async () => {
    try {
      const stats = await updatesService.getUpdatesSummary();
      setUpdateStats(stats);
    } catch (error) {
      console.error('Failed to fetch update statistics:', error);
      setUpdateStats(null);
    }
  }, []);

  const fetchHostsWithUpdates = useCallback(async () => {
    try {
      // Get all updates to extract unique hosts
      const response = await updatesService.getAllUpdates(
        undefined,
        undefined,
        undefined,
        undefined,
        1000,
        0
      );

      // Extract unique hosts from updates
      const hostMap = new Map<number, { hostname: string; count: number }>();
      (response.updates || []).forEach(update => {
        const existing = hostMap.get(update.host_id);
        if (existing) {
          existing.count++;
        } else {
          hostMap.set(update.host_id, {
            hostname: update.hostname,
            count: 1
          });
        }
      });

      // Convert to array and sort by hostname
      const hosts = Array.from(hostMap.entries()).map(([hostId, data]) => ({
        hostId,
        hostname: data.hostname,
        updateCount: data.count
      })).sort((a, b) => a.hostname.localeCompare(b.hostname));

      setHostsWithUpdates(hosts);
    } catch (error) {
      console.error('Failed to fetch hosts with updates:', error);
      setHostsWithUpdates([]);
    }
  }, []);

  const fetchUpdates = useCallback(async (page = 0) => {
    try {
      setIsLoading(true);

      let fetchedUpdates: PackageUpdate[] = [];

      if (filters.host_id) {
        // Fetch host-specific updates
        const hostId = filters.host_id;
        const response: HostUpdatesResponse = await updatesService.getHostUpdates(
          hostId,
          filters.package_manager || undefined,
          filters.security_only || undefined,
          filters.system_only || undefined,
          filters.application_only || undefined
        );

        fetchedUpdates = response.updates;
        setTotalCount(response.total_updates);
        setHostSpecificStats(response);
        setCurrentPage(0);
      } else {
        // Fetch all updates
        const response: UpdatesResponse = await updatesService.getAllUpdates(
          filters.security_only || undefined,
          filters.system_only || undefined,
          filters.application_only || undefined,
          filters.package_manager || undefined,
          ITEMS_PER_PAGE,
          page * ITEMS_PER_PAGE
        );

        fetchedUpdates = response.updates;
        setTotalCount(response.total_count);
        setHostSpecificStats(null);
        setCurrentPage(page);
      }

      // Apply search filter if present
      if (searchQuery) {
        const query = searchQuery.toLowerCase();
        fetchedUpdates = fetchedUpdates.filter(update =>
          update.package_name.toLowerCase().includes(query)
        );
      }

      setUpdates(fetchedUpdates);
    } catch (error) {
      console.error('Failed to fetch updates:', error);
      setUpdates([]);
      setTotalCount(0);
      setHostSpecificStats(null);
    } finally {
      setIsLoading(false);
    }
  }, [filters, searchQuery]);

  const refreshAll = useCallback(async () => {
    setIsRefreshing(true);
    await Promise.all([
      fetchUpdatesSummary(),
      fetchHostsWithUpdates(),
      fetchUpdates(0)
    ]);
    setIsRefreshing(false);
    setSelectedUpdates(new Set());
    
    // Trigger notification bell refresh after data refresh
    triggerRefresh();
  }, [fetchUpdatesSummary, fetchHostsWithUpdates, fetchUpdates, triggerRefresh]);

  const handleManualRefresh = async () => {
    await refreshAll();
  };

  useEffect(() => {
    Promise.all([
      fetchUpdatesSummary(),
      fetchHostsWithUpdates(),
      fetchUpdates(0)
    ]);
  }, [filters, searchQuery, fetchUpdates, fetchHostsWithUpdates, fetchUpdatesSummary]);

  // Watch for changes in search parameters and update filters accordingly
  useEffect(() => {
    const securityFilter = searchParams.get('securityOnly') === 'true' || searchParams.get('filter') === 'security';
    
    setFilters(prevFilters => ({
      ...prevFilters,
      security_only: securityFilter
    }));
  }, [searchParams]);

  // Helper function to process successful package updates
  const processSuccessfulPackage = (
    pkg: UpdatePackage,
    hostId: string,
    newStatuses: Map<string, UpdateStatus>
  ): boolean => {
    const key = `${hostId}-${pkg.package_name}-${pkg.package_manager}`;
    if (newStatuses.has(key)) {
      newStatuses.set(key, {
        status: 'success',
        newVersion: pkg.new_version,
        timestamp: Date.now()
      });
      return true;
    }
    return false;
  };

  // Helper function to process failed package updates
  const processFailedPackage = (
    pkg: UpdatePackage,
    hostId: string,
    newStatuses: Map<string, UpdateStatus>
  ): boolean => {
    const key = `${hostId}-${pkg.package_name}-${pkg.package_manager}`;
    if (newStatuses.has(key)) {
      newStatuses.set(key, {
        status: 'failed',
        timestamp: Date.now()
      });
      return true;
    }
    return false;
  };

  // Helper function to process host results
  const processHostResults = useCallback((
    results: Record<string, unknown>,
    newStatuses: Map<string, UpdateStatus>
  ): boolean => {
    let hasUpdates = false;
    Object.entries(results).forEach(([hostId, hostResult]: [string, unknown]) => {
      const result = hostResult as HostResult;
      result.updated_packages?.forEach((pkg: UpdatePackage) => {
        if (processSuccessfulPackage(pkg, hostId, newStatuses)) {
          hasUpdates = true;
        }
      });
      result.failed_packages?.forEach((pkg: UpdatePackage) => {
        if (processFailedPackage(pkg, hostId, newStatuses)) {
          hasUpdates = true;
        }
      });
    });
    return hasUpdates;
  }, []);

  // Helper function to clear completed selections
  const clearCompletedSelections = (newStatuses: Map<string, UpdateStatus>) => {
    const completedKeys = new Set<string>();
    newStatuses.forEach((status, key) => {
      if (status.status === 'success' || status.status === 'failed') {
        completedKeys.add(key);
      }
    });

    if (completedKeys.size > 0) {
      setSelectedUpdates(prev => {
        const newSelected = new Set(prev);
        completedKeys.forEach(key => newSelected.delete(key));
        return newSelected;
      });
    }
  };

  // Poll for update results when there are pending updates
  useEffect(() => {
    const pollForResults = async () => {
      if (updateStatuses.size === 0) return;

      try {
        const response = await updatesService.getUpdateResults();
        const results = response.results || {};

        // Process results and update status for matching packages
        const newStatuses = new Map(updateStatuses);
        const hasUpdates = processHostResults(results, newStatuses);

        if (hasUpdates) {
          setUpdateStatuses(newStatuses);

          // Trigger notification bell refresh when packages are updated
          triggerRefresh();

          // Clear selections for completed updates after a delay
          setTimeout(() => clearCompletedSelections(newStatuses), 3000);
        }
      } catch (error) {
        console.error('Failed to poll for update results:', error);
      }
    };

    // Only poll if there are pending updates, and use a reasonable interval
    if (updateStatuses.size === 0) return;

    const interval = globalThis.setInterval(pollForResults, 10000); // Poll every 10 seconds only when needed
    return () => globalThis.clearInterval(interval);
  }, [updateStatuses, triggerRefresh, processHostResults]);

  const handleFilterChange = (key: string, value: boolean | string) => {
    setFilters(prev => ({
      ...prev,
      [key]: value
    }));
    setCurrentPage(0);
    setSelectedUpdates(new Set());
  };

  const handleSelectUpdate = (update: PackageUpdate) => {
    const key = `${update.host_id}-${update.package_name}-${update.package_manager}`;
    const newSelected = new Set(selectedUpdates);
    
    if (newSelected.has(key)) {
      newSelected.delete(key);
    } else {
      newSelected.add(key);
    }
    
    setSelectedUpdates(newSelected);
  };

  const handleSelectAll = () => {
    if (selectedUpdates.size === updates.length) {
      setSelectedUpdates(new Set());
    } else {
      const allKeys = updates.map(update => 
        `${update.host_id}-${update.package_name}-${update.package_manager}`
      );
      setSelectedUpdates(new Set(allKeys));
    }
  };

  const executeSelectedUpdates = async () => {
    if (selectedUpdates.size === 0) return;

    const updatesByHost = new Map<number, SelectedUpdate[]>();
    
    updates.forEach(update => {
      const key = `${update.host_id}-${update.package_name}-${update.package_manager}`;
      if (selectedUpdates.has(key)) {
        const hostId = update.host_id;
        if (hostId === null || hostId === undefined) {
          console.error('ERROR: Found null/undefined host_id in update:', update);
          return; // Skip this update
        }
        
        if (!updatesByHost.has(hostId)) {
          updatesByHost.set(hostId, []);
        }
        updatesByHost.get(hostId)!.push({
          hostId: update.host_id,
          packageName: update.package_name,
          packageManager: update.package_manager
        });
      }
    });

    // Set pending status for all selected updates
    const newStatuses = new Map(updateStatuses);
    selectedUpdates.forEach(key => {
      newStatuses.set(key, {
        status: 'pending',
        timestamp: Date.now()
      });
    });
    setUpdateStatuses(newStatuses);

    // Clear checkboxes immediately after setting pending status
    setSelectedUpdates(new Set());

    try {
      const hosts = Array.from(updatesByHost.entries());
      for (const [hostId, hostUpdates] of hosts) {
        const packageNames = hostUpdates.map((u: SelectedUpdate) => u.packageName);
        const packageManagers = Array.from(new Set<string>(hostUpdates.map((u: SelectedUpdate) => u.packageManager)));
        
        await updatesService.executeUpdates([hostId], packageNames, packageManagers);
      }
      
      // Checkboxes are already cleared above
    } catch (error) {
      console.error('Failed to execute updates:', error);
      
      // Set failed status for updates that failed to submit
      const failedStatuses = new Map(newStatuses);
      // Note: selectedUpdates is already cleared, so we need to iterate over the keys that had pending status
      newStatuses.forEach((status, key) => {
        if (status.status === 'pending') {
          failedStatuses.set(key, {
            status: 'failed',
            timestamp: Date.now()
          });
        }
      });
      setUpdateStatuses(failedStatuses);
    }
  };


  const getUpdateTypeText = (update: PackageUpdate) => {
    if (update.is_security_update) {
      return t('updates.types.security', 'Security');
    } else if (update.is_system_update) {
      return t('updates.types.system', 'System');
    } else {
      return t('updates.types.application', 'Application');
    }
  };

  const getStatusPill = (update: PackageUpdate) => {
    const key = `${update.host_id}-${update.package_name}-${update.package_manager}`;
    const localStatus = updateStatuses.get(key);
    
    // First check local state (for immediate feedback after clicking execute)
    if (localStatus) {
      switch (localStatus.status) {
        case 'pending':
          return <span className="updates__status-pill pending">{t('updates.status.pending', 'Update Requested')}</span>;
        case 'success':
          return <span className="updates__status-pill success">{t('updates.status.success', 'Successfully Updated')}</span>;
        case 'failed':
          return <span className="updates__status-pill failed">{t('updates.status.failed', 'Update Failed')}</span>;
      }
    }
    
    // Then check backend status from the update object itself
    if (update.status) {
      switch (update.status) {
        case 'updating':
          return <span className="updates__status-pill pending">{t('updates.status.pending', 'Update Requested')}</span>;
        case 'completed':
        case 'success':
          return <span className="updates__status-pill success">{t('updates.status.success', 'Successfully Updated')}</span>;
        case 'failed':
        case 'error':
          return <span className="updates__status-pill failed">{t('updates.status.failed', 'Update Failed')}</span>;
      }
    }
    
    return null;
  };

  // Helper function to render checkbox based on permission and selection state
  const renderSelectAllCheckbox = () => {
    if (!canApplySoftwareUpdate) {
      return <IoSquareOutline style={{ opacity: 0.3, cursor: 'not-allowed' }} />;
    }
    if (selectedUpdates.size === updates.length) {
      return <IoCheckbox onClick={handleSelectAll} />;
    }
    return <IoSquareOutline onClick={handleSelectAll} />;
  };

  // Helper function to render individual update item checkbox
  const renderUpdateCheckbox = (update: PackageUpdate, isSelected: boolean) => {
    if (!canApplySoftwareUpdate) {
      return <IoSquareOutline style={{ opacity: 0.3, cursor: 'not-allowed' }} />;
    }
    if (isSelected) {
      return <IoCheckbox onClick={() => handleSelectUpdate(update)} />;
    }
    return <IoSquareOutline onClick={() => handleSelectUpdate(update)} />;
  };

  // Helper function to render update type icon
  const renderUpdateIcon = (update: PackageUpdate) => {
    if (update.is_security_update) {
      return <IoShieldCheckmark className="update-icon security" />;
    }
    if (update.is_system_update) {
      return <IoHardwareChip className="update-icon system" />;
    }
    return <IoApps className="update-icon application" />;
  };

  // Helper function to get update type priority for sorting
  const getTypePriority = (update: PackageUpdate): number => {
    if (update.is_security_update) return 0;
    if (update.is_system_update) return 1;
    return 2;
  };

  // Sort updates: security first, then system, then application, then by name
  const sortedUpdates = [...updates].sort((a, b) => {
    const priorityA = getTypePriority(a);
    const priorityB = getTypePriority(b);

    if (priorityA !== priorityB) {
      return priorityA - priorityB;
    }

    // If same type, sort by package name
    return a.package_name.localeCompare(b.package_name);
  });

  // Use host-specific stats if available, otherwise use global stats
  const displayStats = hostSpecificStats ? {
    total_updates: hostSpecificStats.total_updates,
    security_updates: hostSpecificStats.security_updates,
    system_updates: hostSpecificStats.system_updates,
    application_updates: hostSpecificStats.application_updates,
    hosts_with_updates: 1 // Single host when filtered
  } : updateStats;

  const totalPages = filters.host_id ? 1 : Math.ceil(totalCount / ITEMS_PER_PAGE);

  return (
    <div className="updates">
      <div className="updates__header">
        <h1 className="updates__title">{t('updates.title', 'Package Updates')}</h1>
        <div className="updates__refresh-section">
          <button 
            className={`updates__refresh ${isRefreshing ? 'refreshing' : ''}`}
            onClick={handleManualRefresh}
            disabled={isRefreshing}
          >
            <IoRefresh />
            {t('updates.refresh', 'Refresh')}
          </button>
        </div>
      </div>

      {/* Statistics Cards */}
      {displayStats && (
        <div className="updates__stats">
          <div className="updates__stat-card">
            <div className="updates__stat-icon">
              <IoApps />
            </div>
            <div className="updates__stat-content">
              <div className="updates__stat-number">{displayStats.total_updates}</div>
              <div className="updates__stat-label">{t('updates.stats.total', 'Total Updates')}</div>
            </div>
          </div>
          
          <div className="updates__stat-card security">
            <div className="updates__stat-icon">
              <IoShieldCheckmark />
            </div>
            <div className="updates__stat-content">
              <div className="updates__stat-number">{displayStats.security_updates}</div>
              <div className="updates__stat-label">{t('updates.stats.security', 'Security Updates')}</div>
            </div>
          </div>
          
          <div className="updates__stat-card">
            <div className="updates__stat-icon">
              <IoHardwareChip />
            </div>
            <div className="updates__stat-content">
              <div className="updates__stat-number">{displayStats.system_updates}</div>
              <div className="updates__stat-label">{t('updates.stats.system', 'System Updates')}</div>
            </div>
          </div>

          <div className="updates__stat-card">
            <div className="updates__stat-icon">
              <IoApps />
            </div>
            <div className="updates__stat-content">
              <div className="updates__stat-number">{displayStats.application_updates}</div>
              <div className="updates__stat-label">{t('updates.stats.application', 'Application Updates')}</div>
            </div>
          </div>

          <div className="updates__stat-card">
            <div className="updates__stat-icon">
              <IoWarning />
            </div>
            <div className="updates__stat-content">
              <div className="updates__stat-number">{displayStats.hosts_with_updates}</div>
              <div className="updates__stat-label">{t('updates.stats.hosts', 'Affected Hosts')}</div>
            </div>
          </div>
        </div>
      )}

      {/* Search Bar */}
      <div className="updates__search">
        <IoSearch className="updates__search-icon" />
        <input
          type="text"
          placeholder={t('updates.searchPlaceholder', 'Search for package updates...')}
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          className="updates__search-input"
        />
        {searchQuery && (
          <button
            className="updates__search-clear"
            onClick={() => setSearchQuery('')}
            aria-label={t('updates.clearSearch', 'Clear search')}
          >
            ×
          </button>
        )}
      </div>

      {/* Filters */}
      <div className="updates__filters">
        <div className="updates__filter">
          <IoFilter />
          <label>
            <input
              type="checkbox"
              checked={filters.security_only}
              onChange={(e) => handleFilterChange('security_only', e.target.checked)}
            />
            {t('updates.filters.securityOnly', 'Security Updates Only')}
          </label>
        </div>
        
        <div className="updates__filter">
          <label>
            <input
              type="checkbox"
              checked={filters.system_only}
              onChange={(e) => handleFilterChange('system_only', e.target.checked)}
            />
            {t('updates.filters.systemOnly', 'System Updates Only')}
          </label>
        </div>

        <div className="updates__filter">
          <label>
            <input
              type="checkbox"
              checked={filters.application_only}
              onChange={(e) => handleFilterChange('application_only', e.target.checked)}
            />
            {t('updates.filters.applicationOnly', 'Application Updates Only')}
          </label>
        </div>

        <div className="updates__filter">
          <select
            value={filters.package_manager}
            onChange={(e) => handleFilterChange('package_manager', e.target.value)}
          >
            <option value="">{t('updates.filters.allManagers', 'All Package Managers')}</option>
            <option value="apt">APT (Debian/Ubuntu)</option>
            <option value="dnf">DNF (Fedora/RHEL/CentOS 8+)</option>
            <option value="yum">YUM (RHEL/CentOS 7)</option>
            <option value="zypper">Zypper (openSUSE/SUSE)</option>
            <option value="pacman">Pacman (Arch Linux)</option>
            <option value="pkg">PKG (FreeBSD)</option>
            <option value="pkgin">pkgin (NetBSD)</option>
            <option value="snap">Snap</option>
            <option value="flatpak">Flatpak</option>
            <option value="fwupd">fwupd</option>
            <option value="homebrew">Homebrew (macOS)</option>
            <option value="winget">Winget (Windows)</option>
            <option value="chocolatey">Chocolatey (Windows)</option>
          </select>
        </div>

        <div className="updates__filter">
          <select
            value={filters.host_id}
            onChange={(e) => handleFilterChange('host_id', e.target.value)}
          >
            <option value="">{t('updates.filters.allHosts', 'All Affected Hosts')}</option>
            {hostsWithUpdates.map(host => (
              <option key={host.hostId} value={host.hostId.toString()}>
                {host.hostname} ({host.updateCount} {t('updates.filters.updates', 'updates')})
              </option>
            ))}
          </select>
        </div>
      </div>

      {/* Action Bar */}
      {updates.length > 0 && (
        <div className="updates__actions">
          <div className="updates__selection">
            <label className="updates__select-all">
              {renderSelectAllCheckbox()}
              {t('updates.selectAll', 'Select All')} ({selectedUpdates.size}/{updates.length})
            </label>
          </div>

          {selectedUpdates.size > 0 && canApplySoftwareUpdate && (
            <button
              className="updates__execute"
              onClick={executeSelectedUpdates}
            >
              <IoPlay />
              {t('updates.executeSelected', 'Execute Selected Updates')} ({selectedUpdates.size})
            </button>
          )}
        </div>
      )}

      {/* Updates List */}
      <div className="updates__content">
        {updates.length === 0 && !isLoading ? (
          <div className="updates__empty">
            {filters.security_only || filters.system_only || filters.application_only || filters.package_manager || filters.host_id ?
              t('updates.noMatchingUpdates', 'No updates match the current filters') :
              t('updates.noUpdates', 'All systems are up to date')
            }
          </div>
        ) : (
          <div className="updates__list">
            {sortedUpdates.map(update => {
              const key = `${update.host_id}-${update.package_name}-${update.package_manager}`;
              const isSelected = selectedUpdates.has(key);

              return (
                <div
                  key={update.id}
                  className={`updates__item ${isSelected ? 'selected' : ''} ${update.is_security_update ? 'security' : ''}`}
                >
                  <div className="updates__item-select">
                    {renderUpdateCheckbox(update, isSelected)}
                  </div>

                  <div className="updates__item-icon">
                    {renderUpdateIcon(update)}
                  </div>
                  
                  <div className="updates__item-content">
                    <div className="updates__item-header">
                      <span className="updates__item-package">{update.package_name}</span>
                      <span className="updates__item-type">{getUpdateTypeText(update)}</span>
                      {getStatusPill(update)}
                    </div>
                    
                    <div className="updates__item-details">
                      {!filters.host_id && (
                        <span className="updates__item-host">{update.hostname}</span>
                      )}
                      <span className="updates__item-manager">{update.package_manager}</span>
                      <span className="updates__item-version">
                        {update.current_version || t('updates.unknown', 'Unknown')} → {update.available_version}
                      </span>
                    </div>
                    
                    {update.requires_reboot && (
                      <div className="updates__item-reboot">
                        <IoWarning />
                        {t('updates.requiresReboot', 'Requires reboot')}
                      </div>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="updates__pagination">
          <button 
            onClick={() => fetchUpdates(currentPage - 1)}
            disabled={currentPage === 0}
          >
            {t('updates.previous', 'Previous')}
          </button>
          
          <span className="updates__page-info">
            {t('updates.pageInfo', 'Page {{current}} of {{total}}', {
              current: currentPage + 1,
              total: totalPages
            })}
          </span>
          
          <button 
            onClick={() => fetchUpdates(currentPage + 1)}
            disabled={currentPage >= totalPages - 1}
          >
            {t('updates.next', 'Next')}
          </button>
        </div>
      )}
    </div>
  );
};

export default Updates;