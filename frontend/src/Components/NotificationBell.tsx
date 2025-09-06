import React, { useState, useEffect, useCallback, useRef } from 'react';
import { IoNotifications, IoNotificationsOutline } from 'react-icons/io5';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';
import { updatesService, UpdateStatsSummary } from '../Services/updates';
import { useNotificationRefresh } from '../hooks/useNotificationRefresh';
import './css/NotificationBell.css';

const NotificationBell: React.FC = () => {
  const [updateStats, setUpdateStats] = useState<UpdateStatsSummary | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [showDropdown, setShowDropdown] = useState(false);
  const { t } = useTranslation();
  const navigate = useNavigate();
  const isMountedRef = useRef(true);
  const { registerRefresh, unregisterRefresh } = useNotificationRefresh();

  const fetchUpdateStats = useCallback(async () => {
    if (!isMountedRef.current) return;
    
    try {
      if (isMountedRef.current) {
        setIsLoading(true);
      }
      const stats = await updatesService.getUpdatesSummary();
      if (isMountedRef.current) {
        setUpdateStats(stats);
      }
    } catch (error) {
      console.error('Failed to fetch update statistics:', error);
      if (isMountedRef.current) {
        setUpdateStats(null);
      }
    } finally {
      if (isMountedRef.current) {
        setIsLoading(false);
      }
    }
  }, []);

  useEffect(() => {
    isMountedRef.current = true;
    fetchUpdateStats();
    
    // Register the refresh function for external triggers
    registerRefresh(fetchUpdateStats);
    
    // Start with frequent polling (every 10 seconds) for the first 2 minutes to catch initial data
    let interval = window.setInterval(fetchUpdateStats, 10 * 1000);
    
    // After 2 minutes, switch to less frequent polling (every 30 seconds)
    const slowDownTimeout = window.setTimeout(() => {
      if (isMountedRef.current) {
        window.clearInterval(interval);
        interval = window.setInterval(fetchUpdateStats, 30 * 1000);
      }
    }, 2 * 60 * 1000);
    
    return () => {
      isMountedRef.current = false;
      unregisterRefresh();
      window.clearInterval(interval);
      window.clearTimeout(slowDownTimeout);
    };
  }, [fetchUpdateStats, registerRefresh, unregisterRefresh]);

  const handleBellClick = () => {
    setShowDropdown(!showDropdown);
  };

  const handleViewAllUpdates = () => {
    setShowDropdown(false);
    navigate('/updates');
  };

  const handleViewSecurityUpdates = () => {
    setShowDropdown(false);
    navigate('/updates?filter=security');
  };

  const hasUpdates = updateStats && updateStats.total_updates > 0;
  const hasSecurityUpdates = updateStats && updateStats.security_updates > 0;

  return (
    <div className="notification-bell">
      <button
        className={`notification-bell__button ${hasUpdates ? 'has-notifications' : ''}`}
        onClick={handleBellClick}
        title={t('notifications.bell.tooltip', 'View available updates')}
        disabled={isLoading}
      >
        {hasUpdates ? (
          <IoNotifications className="notification-bell__icon" />
        ) : (
          <IoNotificationsOutline className="notification-bell__icon" />
        )}
        
        {hasUpdates && (
          <span className={`notification-bell__badge ${hasSecurityUpdates ? 'security' : ''}`}>
            {updateStats.total_updates > 99 ? '99+' : updateStats.total_updates}
          </span>
        )}
      </button>

      {showDropdown && (
        <>
          <div 
            className="notification-bell__overlay" 
            onClick={() => setShowDropdown(false)}
          />
          <div className="notification-bell__dropdown">
            <div className="notification-bell__header">
              <h3>{t('notifications.title', 'Available Updates')}</h3>
            </div>
            
            <div className="notification-bell__content">
              {isLoading ? (
                <div className="notification-bell__loading">
                  {t('notifications.loading', 'Loading updates...')}
                </div>
              ) : updateStats && hasUpdates ? (
                <div className="notification-bell__stats">
                  <div className="notification-bell__stat">
                    <span className="notification-bell__stat-number">
                      {updateStats.total_updates}
                    </span>
                    <span className="notification-bell__stat-label">
                      {t('notifications.totalUpdates', 'Total Updates')}
                    </span>
                  </div>
                  
                  {updateStats.security_updates > 0 && (
                    <div className="notification-bell__stat security">
                      <span className="notification-bell__stat-number">
                        {updateStats.security_updates}
                      </span>
                      <span className="notification-bell__stat-label">
                        {t('notifications.securityUpdates', 'Security Updates')}
                      </span>
                    </div>
                  )}
                  
                  {updateStats.system_updates > 0 && (
                    <div className="notification-bell__stat">
                      <span className="notification-bell__stat-number">
                        {updateStats.system_updates}
                      </span>
                      <span className="notification-bell__stat-label">
                        {t('notifications.systemUpdates', 'System Updates')}
                      </span>
                    </div>
                  )}
                  
                  {updateStats.application_updates > 0 && (
                    <div className="notification-bell__stat">
                      <span className="notification-bell__stat-number">
                        {updateStats.application_updates}
                      </span>
                      <span className="notification-bell__stat-label">
                        {t('notifications.applicationUpdates', 'Application Updates')}
                      </span>
                    </div>
                  )}
                  
                  <div className="notification-bell__hosts">
                    <span className="notification-bell__hosts-text">
                      {t('notifications.hostsAffected', 
                        '{{count}} of {{total}} hosts have updates', 
                        { 
                          count: updateStats.hosts_with_updates, 
                          total: updateStats.total_hosts 
                        }
                      )}
                    </span>
                  </div>
                </div>
              ) : (
                <div className="notification-bell__no-updates">
                  {t('notifications.noUpdates', 'All systems are up to date')}
                </div>
              )}
            </div>
            
            {hasUpdates && (
              <div className="notification-bell__actions">
                {hasSecurityUpdates && (
                  <button
                    className="notification-bell__action security"
                    onClick={handleViewSecurityUpdates}
                  >
                    {t('notifications.viewSecurity', 'View Security Updates')}
                  </button>
                )}
                <button
                  className="notification-bell__action"
                  onClick={handleViewAllUpdates}
                >
                  {t('notifications.viewAll', 'View All Updates')}
                </button>
              </div>
            )}
          </div>
        </>
      )}
    </div>
  );
};

export default NotificationBell;