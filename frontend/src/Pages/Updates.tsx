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
  IoTime,
  IoCheckmarkCircle,
  IoCloseCircle
} from 'react-icons/io5';
import { 
  updatesService, 
  UpdateStatsSummary, 
  PackageUpdate, 
  UpdatesResponse,
  HostUpdatesResponse 
} from '../Services/updates';
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
  const [filters, setFilters] = useState({
    security_only: searchParams.get('securityOnly') === 'true' || searchParams.get('filter') === 'security',
    system_only: false,
    package_manager: '',
    host_id: ''
  });

  // Auto-refresh state (disabled)
  // const [refreshCountdown, setRefreshCountdown] = useState(30);
  // const [hasActiveUpdates, setHasActiveUpdates] = useState(false);
  // const refreshTimerRef = useRef<number | null>(null);
  // const countdownTimerRef = useRef<number | null>(null);

  const ITEMS_PER_PAGE = 50;
  // const STANDARD_REFRESH_INTERVAL = 30000; // 30 seconds 
  // const ACTIVE_UPDATES_REFRESH_INTERVAL = 15000; // 15 seconds when updates are running

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
        1000,
        0
      );
      
      // Extract unique hosts from updates
      const hostMap = new Map<number, { hostname: string; count: number }>();
      response.updates.forEach(update => {
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
      
      if (filters.host_id) {
        // Fetch host-specific updates
        const hostId = parseInt(filters.host_id);
        const response: HostUpdatesResponse = await updatesService.getHostUpdates(
          hostId,
          filters.package_manager || undefined,
          filters.security_only || undefined,
          filters.system_only || undefined
        );
        
        
        setUpdates(response.updates);
        setTotalCount(response.total_updates);
        setHostSpecificStats(response);
        setCurrentPage(0);
      } else {
        // Fetch all updates
        const response: UpdatesResponse = await updatesService.getAllUpdates(
          filters.security_only || undefined,
          filters.system_only || undefined,
          filters.package_manager || undefined,
          ITEMS_PER_PAGE,
          page * ITEMS_PER_PAGE
        );
        
        setUpdates(response.updates);
        setTotalCount(response.total_count);
        setHostSpecificStats(null);
        setCurrentPage(page);
      }
    } catch (error) {
      console.error('Failed to fetch updates:', error);
      setUpdates([]);
      setTotalCount(0);
      setHostSpecificStats(null);
    } finally {
      setIsLoading(false);
    }
  }, [filters]);

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
    // resetAutoRefreshTimer(); // Auto-refresh disabled
  };

  // Store timer function in ref to avoid useCallback dependencies (disabled)
  // const resetAutoRefreshTimerRef = useRef<() => void>();
  
  // Auto-refresh timer function disabled
  // resetAutoRefreshTimerRef.current = () => {
  //   // Clear existing timers
  //   if (refreshTimerRef.current) {
  //     window.clearTimeout(refreshTimerRef.current);
  //   }
  //   if (countdownTimerRef.current) {
  //     window.clearInterval(countdownTimerRef.current);
  //   }

  //   // Choose interval based on whether updates are active
  //   const interval = hasActiveUpdates ? ACTIVE_UPDATES_REFRESH_INTERVAL : STANDARD_REFRESH_INTERVAL;
  //   const countdownSeconds = Math.floor(interval / 1000);
  //   
  //   setRefreshCountdown(countdownSeconds);

  //   // Start countdown timer (updates every second)
  //   countdownTimerRef.current = window.setInterval(() => {
  //     setRefreshCountdown((prev) => {
  //       if (prev <= 1) {
  //         return countdownSeconds; // Reset countdown
  //       }
  //       return prev - 1;
  //     });
  //   }, 1000);

  //   // Set main refresh timer
  //   refreshTimerRef.current = window.setTimeout(() => {
  //     refreshAll();
  //     if (resetAutoRefreshTimerRef.current) {
  //       resetAutoRefreshTimerRef.current(); // Schedule next refresh
  //     }
  //   }, interval);
  // };

  // const resetAutoRefreshTimer = useCallback(() => {
  //   if (resetAutoRefreshTimerRef.current) {
  //     resetAutoRefreshTimerRef.current();
  //   }
  // }, []);

  // Remove user interaction timer resets to prevent excessive refreshing

  useEffect(() => {
    Promise.all([
      fetchUpdatesSummary(),
      fetchHostsWithUpdates(),
      fetchUpdates(0)
    ]);
  }, [filters, fetchUpdates, fetchHostsWithUpdates, fetchUpdatesSummary]);

  // Check for active updates on component mount and when updateStatuses changes (disabled)
  // useEffect(() => {
  //   let hasPending = false;
  //   updateStatuses.forEach((status) => {
  //     if (status.status === 'pending') {
  //       hasPending = true;
  //     }
  //   });
  //   // setHasActiveUpdates(hasPending);
  // }, [updateStatuses]);

  // Watch for changes in search parameters and update filters accordingly
  useEffect(() => {
    const securityFilter = searchParams.get('securityOnly') === 'true' || searchParams.get('filter') === 'security';
    
    setFilters(prevFilters => ({
      ...prevFilters,
      security_only: securityFilter
    }));
  }, [searchParams]);

  // Auto-refresh disabled
  // useEffect(() => {
  //   if (resetAutoRefreshTimerRef.current) {
  //     resetAutoRefreshTimerRef.current();
  //   }
  //   
  //   // Cleanup timers on component unmount
  //   return () => {
  //     if (refreshTimerRef.current) {
  //       window.clearTimeout(refreshTimerRef.current);
  //     }
  //     if (countdownTimerRef.current) {
  //       window.clearInterval(countdownTimerRef.current);
  //     }
  //   };
  // }, []);

  // useEffect(() => {
  //   if (resetAutoRefreshTimerRef.current) {
  //     resetAutoRefreshTimerRef.current();
  //   }
  // }, [hasActiveUpdates]);

  // Removed excessive user interaction listeners that were causing timer resets

  // Poll for update results when there are pending updates
  useEffect(() => {
    const pollForResults = async () => {
      if (updateStatuses.size === 0) return;
      
      try {
        const response = await updatesService.getUpdateResults();
        const results = response.results || {};
        
        // Process results and update status for matching packages
        const newStatuses = new Map(updateStatuses);
        let hasUpdates = false;
        
        Object.entries(results).forEach(([hostId, hostResult]: [string, unknown]) => {
          const result = hostResult as HostResult;
          // Handle successful updates
          result.updated_packages?.forEach((pkg: UpdatePackage) => {
            const key = `${hostId}-${pkg.package_name}-${pkg.package_manager}`;
            if (newStatuses.has(key)) {
              newStatuses.set(key, {
                status: 'success',
                newVersion: pkg.new_version,
                timestamp: Date.now()
              });
              hasUpdates = true;
            }
          });
          
          // Handle failed updates
          result.failed_packages?.forEach((pkg: UpdatePackage) => {
            const key = `${hostId}-${pkg.package_name}-${pkg.package_manager}`;
            if (newStatuses.has(key)) {
              newStatuses.set(key, {
                status: 'failed',
                timestamp: Date.now()
              });
              hasUpdates = true;
            }
          });
        });
        
        if (hasUpdates) {
          setUpdateStatuses(newStatuses);
          
          // Trigger notification bell refresh when packages are updated
          triggerRefresh();
          
          // Check if all updates are complete (no pending updates remaining)
          let hasPendingUpdates = false;
          newStatuses.forEach((status) => {
            if (status.status === 'pending') {
              hasPendingUpdates = true;
            }
          });
          
          // Disable fast polling if no pending updates remain
          if (!hasPendingUpdates) {
            // setHasActiveUpdates(false);
          }
          
          // Clear selections for completed updates after a delay
          setTimeout(() => {
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
          }, 3000); // Clear selections after 3 seconds
        }
      } catch (error) {
        console.error('Failed to poll for update results:', error);
      }
    };

    // Only poll if there are pending updates, and use a reasonable interval
    if (updateStatuses.size === 0) return;
    
    const interval = window.setInterval(pollForResults, 10000); // Poll every 10 seconds only when needed
    return () => window.clearInterval(interval);
  }, [updateStatuses, triggerRefresh]);

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
    // setHasActiveUpdates(true); // Enable fast polling

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

  const getUpdateIcon = (update: PackageUpdate) => {
    const key = `${update.host_id}-${update.package_name}-${update.package_manager}`;
    const localStatus = updateStatuses.get(key);
    
    // First check local state (for immediate feedback after clicking execute)
    if (localStatus) {
      switch (localStatus.status) {
        case 'pending':
          return <IoTime className="update-icon pending" />;
        case 'success':
          return <IoCheckmarkCircle className="update-icon success" />;
        case 'failed':
          return <IoCloseCircle className="update-icon failed" />;
      }
    }
    
    // Then check backend status from the update object itself
    if (update.status) {
      switch (update.status) {
        case 'updating':
          return <IoTime className="update-icon pending" />;
        case 'completed':
        case 'success':
          return <IoCheckmarkCircle className="update-icon success" />;
        case 'failed':
        case 'error':
          return <IoCloseCircle className="update-icon failed" />;
      }
    }
    
    // Default icons based on update type
    if (update.is_security_update) {
      return <IoShieldCheckmark className="update-icon security" />;
    } else if (update.is_system_update) {
      return <IoHardwareChip className="update-icon system" />;
    } else {
      return <IoApps className="update-icon application" />;
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
              <IoWarning />
            </div>
            <div className="updates__stat-content">
              <div className="updates__stat-number">{displayStats.hosts_with_updates}</div>
              <div className="updates__stat-label">{t('updates.stats.hosts', 'Affected Hosts')}</div>
            </div>
          </div>
        </div>
      )}

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
          <select
            value={filters.package_manager}
            onChange={(e) => handleFilterChange('package_manager', e.target.value)}
          >
            <option value="">{t('updates.filters.allManagers', 'All Package Managers')}</option>
            <option value="apt">APT</option>
            <option value="snap">Snap</option>
            <option value="flatpak">Flatpak</option>
            <option value="homebrew">Homebrew</option>
            <option value="winget">Winget</option>
            <option value="chocolatey">Chocolatey</option>
            <option value="pkg">PKG</option>
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
              {selectedUpdates.size === updates.length ? (
                <IoCheckbox onClick={handleSelectAll} />
              ) : (
                <IoSquareOutline onClick={handleSelectAll} />
              )}
              {t('updates.selectAll', 'Select All')} ({selectedUpdates.size}/{updates.length})
            </label>
          </div>
          
          {selectedUpdates.size > 0 && (
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
            {filters.security_only || filters.system_only || filters.package_manager || filters.host_id ? 
              t('updates.noMatchingUpdates', 'No updates match the current filters') :
              t('updates.noUpdates', 'All systems are up to date')
            }
          </div>
        ) : (
          <div className="updates__list">
            {updates.map(update => {
              const key = `${update.host_id}-${update.package_name}-${update.package_manager}`;
              const isSelected = selectedUpdates.has(key);
              
              return (
                <div 
                  key={key} 
                  className={`updates__item ${isSelected ? 'selected' : ''} ${update.is_security_update ? 'security' : ''}`}
                >
                  <div className="updates__item-select">
                    {isSelected ? (
                      <IoCheckbox onClick={() => handleSelectUpdate(update)} />
                    ) : (
                      <IoSquareOutline onClick={() => handleSelectUpdate(update)} />
                    )}
                  </div>
                  
                  <div className="updates__item-icon">
                    {getUpdateIcon(update)}
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