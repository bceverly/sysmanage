import React, { useState, useEffect, useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import {
  IoRefresh,
  IoCheckbox,
  IoSquareOutline,
  IoWarning,
  IoShieldCheckmark,
  IoPlay,
  IoTime,
  IoCheckmarkCircle,
  IoCloseCircle,
  IoDesktop,
  IoFilter
} from 'react-icons/io5';
import {
  updatesService,
  OSUpgradeResponse,
  OSUpgradeSummary
} from '../Services/updates';
import { useNotificationRefresh } from '../hooks/useNotificationRefresh';
import './css/Updates.css'; // Reuse the Updates.css styling


interface UpdateStatus {
  status: 'pending' | 'success' | 'failed';
  timestamp: number;
}

const OSUpgrades: React.FC = () => {
  const { t } = useTranslation();
  const { triggerRefresh } = useNotificationRefresh();

  const [osUpgrades, setOSUpgrades] = useState<OSUpgradeResponse[]>([]);
  const [osUpgradeSummary, setOSUpgradeSummary] = useState<OSUpgradeSummary | null>(null);
  const [selectedUpgrades, setSelectedUpgrades] = useState<Set<string>>(new Set());
  const [updateStatuses, setUpdateStatuses] = useState<Map<string, UpdateStatus>>(new Map());
  const [isLoading, setIsLoading] = useState(true);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [filters, setFilters] = useState({
    package_manager: ''
  });

  const fetchOSUpgrades = useCallback(async () => {
    try {
      setIsLoading(true);
      const response = await updatesService.getOSUpgrades();

      // Extract the upgrades array from the response object
      const upgrades = response.os_upgrades || [];

      // Apply package manager filter if present
      let filteredUpgrades = upgrades;
      if (filters.package_manager) {
        filteredUpgrades = upgrades.filter(upgrade =>
          upgrade.package_manager === filters.package_manager
        );
      }

      setOSUpgrades(filteredUpgrades);
    } catch (error) {
      console.error('Failed to fetch OS upgrades:', error);
      setOSUpgrades([]);
    } finally {
      setIsLoading(false);
    }
  }, [filters]);

  const fetchOSUpgradesSummary = useCallback(async () => {
    try {
      const summary = await updatesService.getOSUpgradesSummary();
      setOSUpgradeSummary(summary);
    } catch (error) {
      console.error('Failed to fetch OS upgrades summary:', error);
      setOSUpgradeSummary(null);
    }
  }, []);

  const refreshAll = useCallback(async () => {
    setIsRefreshing(true);
    await Promise.all([
      fetchOSUpgrades(),
      fetchOSUpgradesSummary()
    ]);
    setIsRefreshing(false);
    setSelectedUpgrades(new Set());

    triggerRefresh();
  }, [fetchOSUpgrades, fetchOSUpgradesSummary, triggerRefresh]);

  useEffect(() => {
    Promise.all([
      fetchOSUpgrades(),
      fetchOSUpgradesSummary()
    ]);
  }, [fetchOSUpgrades, fetchOSUpgradesSummary]);

  const handleFilterChange = (key: string, value: string) => {
    setFilters(prev => ({
      ...prev,
      [key]: value
    }));
    setSelectedUpgrades(new Set());
  };

  const handleSelectUpgrade = (upgrade: OSUpgradeResponse) => {
    const key = `${upgrade.host_id}-${upgrade.package_manager}`;
    const newSelected = new Set(selectedUpgrades);

    if (newSelected.has(key)) {
      newSelected.delete(key);
    } else {
      newSelected.add(key);
    }

    setSelectedUpgrades(newSelected);
  };

  const handleSelectAll = () => {
    if (selectedUpgrades.size === osUpgrades.length) {
      setSelectedUpgrades(new Set());
    } else {
      const allKeys = osUpgrades.map(upgrade =>
        `${upgrade.host_id}-${upgrade.package_manager}`
      );
      setSelectedUpgrades(new Set(allKeys));
    }
  };

  const executeSelectedUpgrades = async () => {
    if (selectedUpgrades.size === 0) return;

    const upgradesByHost = new Map<number, string[]>();

    osUpgrades.forEach(upgrade => {
      const key = `${upgrade.host_id}-${upgrade.package_manager}`;
      if (selectedUpgrades.has(key)) {
        const hostId = upgrade.host_id;
        if (!upgradesByHost.has(hostId)) {
          upgradesByHost.set(hostId, []);
        }
        upgradesByHost.get(hostId)!.push(upgrade.package_manager);
      }
    });

    // Set pending status for all selected upgrades
    const newStatuses = new Map(updateStatuses);
    selectedUpgrades.forEach(key => {
      newStatuses.set(key, {
        status: 'pending',
        timestamp: Date.now()
      });
    });
    setUpdateStatuses(newStatuses);

    // Clear checkboxes immediately
    setSelectedUpgrades(new Set());

    try {
      const hosts = Array.from(upgradesByHost.entries());
      for (const [hostId, packageManagers] of hosts) {
        await updatesService.executeOSUpgrades([hostId], packageManagers);
      }
    } catch (error) {
      console.error('Failed to execute OS upgrades:', error);

      // Set failed status for upgrades that failed to submit
      const failedStatuses = new Map(newStatuses);
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

  const getUpgradeIcon = (upgrade: OSUpgradeResponse) => {
    const key = `${upgrade.host_id}-${upgrade.package_manager}`;
    const status = updateStatuses.get(key);

    if (status) {
      switch (status.status) {
        case 'pending':
          return <IoTime className="update-icon pending" />;
        case 'success':
          return <IoCheckmarkCircle className="update-icon success" />;
        case 'failed':
          return <IoCloseCircle className="update-icon failed" />;
      }
    }

    // All OS upgrades are security updates
    return <IoShieldCheckmark className="update-icon security" />;
  };

  const getStatusPill = (upgrade: OSUpgradeResponse) => {
    const key = `${upgrade.host_id}-${upgrade.package_manager}`;
    const status = updateStatuses.get(key);

    if (status) {
      switch (status.status) {
        case 'pending':
          return <span className="updates__status-pill pending">{t('osUpgrades.status.pending', 'Upgrade Requested')}</span>;
        case 'success':
          return <span className="updates__status-pill success">{t('osUpgrades.status.success', 'Successfully Upgraded')}</span>;
        case 'failed':
          return <span className="updates__status-pill failed">{t('osUpgrades.status.failed', 'Upgrade Failed')}</span>;
      }
    }

    return null;
  };

  const getOSUpgradeTypeText = (packageManager: string) => {
    switch (packageManager) {
      case 'ubuntu-release':
        return t('osUpgrades.types.ubuntu', 'Ubuntu Release Upgrade');
      case 'fedora-release':
        return t('osUpgrades.types.fedora', 'Fedora Version Upgrade');
      case 'opensuse-release':
        return t('osUpgrades.types.opensuse', 'openSUSE Distribution Upgrade');
      case 'macos-upgrade':
        return t('osUpgrades.types.macos', 'macOS Version Upgrade');
      case 'windows-upgrade':
        return t('osUpgrades.types.windows', 'Windows Feature Update');
      case 'openbsd-upgrade':
        return t('osUpgrades.types.openbsd', 'OpenBSD System Upgrade');
      case 'freebsd-upgrade':
        return t('osUpgrades.types.freebsd', 'FreeBSD Version Upgrade');
      default:
        return t('osUpgrades.types.generic', 'OS Upgrade');
    }
  };

  return (
    <div className="updates">
      <div className="updates__header">
        <h1 className="updates__title">{t('osUpgrades.title', 'Operating System Upgrades')}</h1>
        <div className="updates__refresh-section">
          <button
            className={`updates__refresh ${isRefreshing ? 'refreshing' : ''}`}
            onClick={refreshAll}
            disabled={isRefreshing}
          >
            <IoRefresh />
            {t('osUpgrades.refresh', 'Refresh')}
          </button>
        </div>
      </div>

      {/* Statistics Cards */}
      {osUpgradeSummary && (
        <div className="updates__stats">
          <div className="updates__stat-card">
            <div className="updates__stat-icon">
              <IoDesktop />
            </div>
            <div className="updates__stat-content">
              <div className="updates__stat-number">{osUpgradeSummary.total_os_upgrades}</div>
              <div className="updates__stat-label">{t('osUpgrades.stats.total', 'Total OS Upgrades')}</div>
            </div>
          </div>

          <div className="updates__stat-card security">
            <div className="updates__stat-icon">
              <IoShieldCheckmark />
            </div>
            <div className="updates__stat-content">
              <div className="updates__stat-number">{osUpgradeSummary.total_os_upgrades}</div>
              <div className="updates__stat-label">{t('osUpgrades.stats.security', 'Security Updates')}</div>
            </div>
          </div>

          <div className="updates__stat-card">
            <div className="updates__stat-icon">
              <IoWarning />
            </div>
            <div className="updates__stat-content">
              <div className="updates__stat-number">{osUpgradeSummary.hosts_with_os_upgrades}</div>
              <div className="updates__stat-label">{t('osUpgrades.stats.hosts', 'Affected Hosts')}</div>
            </div>
          </div>
        </div>
      )}

      {/* Filters */}
      <div className="updates__filters">
        <div className="updates__filter">
          <IoFilter />
          <select
            value={filters.package_manager}
            onChange={(e) => handleFilterChange('package_manager', e.target.value)}
          >
            <option value="">{t('osUpgrades.filters.allTypes', 'All OS Types')}</option>
            <option value="ubuntu-release">{t('osUpgrades.filters.ubuntu', 'Ubuntu/Debian')}</option>
            <option value="fedora-release">{t('osUpgrades.filters.fedora', 'Fedora')}</option>
            <option value="opensuse-release">{t('osUpgrades.filters.opensuse', 'openSUSE')}</option>
            <option value="macos-upgrade">{t('osUpgrades.filters.macos', 'macOS')}</option>
            <option value="windows-upgrade">{t('osUpgrades.filters.windows', 'Windows')}</option>
            <option value="openbsd-upgrade">{t('osUpgrades.filters.openbsd', 'OpenBSD')}</option>
            <option value="freebsd-upgrade">{t('osUpgrades.filters.freebsd', 'FreeBSD')}</option>
            <option value="netbsd-upgrade">{t('osUpgrades.filters.netbsd', 'NetBSD')}</option>
          </select>
        </div>
      </div>

      {/* Action Bar */}
      {osUpgrades.length > 0 && (
        <div className="updates__actions">
          <div className="updates__selection">
            <label className="updates__select-all">
              {selectedUpgrades.size === osUpgrades.length ? (
                <IoCheckbox onClick={handleSelectAll} />
              ) : (
                <IoSquareOutline onClick={handleSelectAll} />
              )}
              {t('osUpgrades.selectAll', 'Select All')} ({selectedUpgrades.size}/{osUpgrades.length})
            </label>
          </div>

          {selectedUpgrades.size > 0 && (
            <button
              className="updates__execute"
              onClick={executeSelectedUpgrades}
            >
              <IoPlay />
              {t('osUpgrades.executeSelected', 'Execute Selected OS Upgrades')} ({selectedUpgrades.size})
            </button>
          )}
        </div>
      )}

      {/* Upgrades List */}
      <div className="updates__content">
        {osUpgrades.length === 0 && !isLoading ? (
          <div className="updates__empty">
            {filters.package_manager ?
              t('osUpgrades.noMatchingUpgrades', 'No OS upgrades match the current filter') :
              t('osUpgrades.noUpgrades', 'No OS upgrades are currently available')
            }
          </div>
        ) : (
          <div className="updates__list">
            {osUpgrades.map(upgrade => {
              const key = upgrade.id; // Use the unique id from backend
              const selectionKey = `${upgrade.host_id}-${upgrade.package_manager}`;
              const isSelected = selectedUpgrades.has(selectionKey);

              return (
                <div
                  key={key}
                  className={`updates__item ${isSelected ? 'selected' : ''} security`}
                >
                  <div className="updates__item-select">
                    {isSelected ? (
                      <IoCheckbox onClick={() => handleSelectUpgrade(upgrade)} />
                    ) : (
                      <IoSquareOutline onClick={() => handleSelectUpgrade(upgrade)} />
                    )}
                  </div>

                  <div className="updates__item-icon">
                    {getUpgradeIcon(upgrade)}
                  </div>

                  <div className="updates__item-content">
                    <div className="updates__item-header">
                      <span className="updates__item-package">{upgrade.package_name}</span>
                      <span className="updates__item-type">{getOSUpgradeTypeText(upgrade.package_manager)}</span>
                      {getStatusPill(upgrade)}
                    </div>

                    <div className="updates__item-details">
                      <span className="updates__item-host">{upgrade.host_fqdn}</span>
                      <span className="updates__item-version">
                        {upgrade.current_version} → {upgrade.available_version}
                      </span>
                    </div>

                    <div className="updates__item-reboot">
                      <IoWarning />
                      {t('osUpgrades.requiresReboot', 'OS upgrade requires system reboot')}
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
};

export default OSUpgrades;