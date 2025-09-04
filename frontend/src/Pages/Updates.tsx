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
  IoPlay
} from 'react-icons/io5';
import { 
  updatesService, 
  UpdateStatsSummary, 
  PackageUpdate, 
  UpdatesResponse,
  HostUpdatesResponse 
} from '../Services/updates';
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

const Updates: React.FC = () => {
  const [searchParams] = useSearchParams();
  const { t } = useTranslation();
  
  const [updateStats, setUpdateStats] = useState<UpdateStatsSummary | null>(null);
  const [updates, setUpdates] = useState<PackageUpdate[]>([]);
  const [selectedUpdates, setSelectedUpdates] = useState<Set<string>>(new Set());
  const [isLoading, setIsLoading] = useState(true);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [currentPage, setCurrentPage] = useState(0);
  const [totalCount, setTotalCount] = useState(0);
  const [hostsWithUpdates, setHostsWithUpdates] = useState<HostWithUpdates[]>([]);
  const [hostSpecificStats, setHostSpecificStats] = useState<HostUpdatesResponse | null>(null);
  const [filters, setFilters] = useState({
    security_only: searchParams.get('securityOnly') === 'true',
    system_only: false,
    package_manager: '',
    host_id: ''
  });

  const ITEMS_PER_PAGE = 50;

  const fetchUpdatesSummary = async () => {
    try {
      const stats = await updatesService.getUpdatesSummary();
      setUpdateStats(stats);
    } catch (error) {
      console.error('Failed to fetch update statistics:', error);
      setUpdateStats(null);
    }
  };

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

  const refreshAll = async () => {
    setIsRefreshing(true);
    await Promise.all([
      fetchUpdatesSummary(),
      fetchHostsWithUpdates(),
      fetchUpdates(0)
    ]);
    setIsRefreshing(false);
    setSelectedUpdates(new Set());
  };

  useEffect(() => {
    Promise.all([
      fetchUpdatesSummary(),
      fetchHostsWithUpdates(),
      fetchUpdates(0)
    ]);
  }, [filters, fetchUpdates, fetchHostsWithUpdates]);

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

    try {
      for (const [hostId, hostUpdates] of updatesByHost) {
        const packageNames = hostUpdates.map(u => u.packageName);
        const packageManagers = [...new Set(hostUpdates.map(u => u.packageManager))];
        
        await updatesService.executeUpdates([hostId], packageNames, packageManagers);
      }
      
      alert(t('updates.executeSuccess', 'Update execution started for selected packages'));
      setSelectedUpdates(new Set());
      await refreshAll();
    } catch (error) {
      console.error('Failed to execute updates:', error);
      alert(t('updates.executeError', 'Failed to execute updates'));
    }
  };

  const getUpdateIcon = (update: PackageUpdate) => {
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
        <button 
          className={`updates__refresh ${isRefreshing ? 'refreshing' : ''}`}
          onClick={refreshAll}
          disabled={isRefreshing}
        >
          <IoRefresh />
          {t('updates.refresh', 'Refresh')}
        </button>
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
        {isLoading ? (
          <div className="updates__loading">
            {t('updates.loading', 'Loading updates...')}
          </div>
        ) : updates.length === 0 ? (
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