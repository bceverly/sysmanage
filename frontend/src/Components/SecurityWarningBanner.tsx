import React, { useState, useEffect } from 'react';
import { Alert, AlertTitle, Box } from '@mui/material';
import { Warning } from '@mui/icons-material';
import { useTranslation } from 'react-i18next';
import api from '../Services/api';

interface SecurityWarning {
  type: string;
  severity: string;
  message: string;
  details?: string;
}

interface SecurityStatus {
  hasDefaultCredentials: boolean;
  isLoggedInAsDefault: boolean;
  defaultUserId: string;
  securityWarnings: SecurityWarning[];
  hasDefaultJwtSecret: boolean;
  hasDefaultPasswordSalt: boolean;
}

const SecurityWarningBanner: React.FC = () => {
  const { t } = useTranslation();
  const [securityStatus, setSecurityStatus] = useState<SecurityStatus | null>(null);

  useEffect(() => {
    // Set CSS custom property for banner height to push navbar down
    const setBannerHeight = (height: string) => {
      document.documentElement.style.setProperty('--security-banner-height', height);
    };

    const checkSecurityStatus = async () => {
      // Only check security status if user is authenticated
      const token = localStorage.getItem('bearer_token');
      if (!token) {
        setSecurityStatus(null);
        setBannerHeight('0px'); // No banner when not authenticated
        return;
      }

      try {
        const response = await api.get('/security/default-credentials-status');
        const status = response.data;
        setSecurityStatus(status);
        
        // Set banner height based on security warnings
        if (status && (status.hasDefaultCredentials || status.securityWarnings.length > 0)) {
          // Calculate height based on content
          const hasCredentials = status.hasDefaultCredentials;
          const warningCount = status.securityWarnings.length;
          
          if (hasCredentials && warningCount > 0) {
            setBannerHeight('140px'); // Larger for combined warnings
          } else if (hasCredentials) {
            setBannerHeight('100px'); // Standard for credential warnings
          } else if (warningCount > 0) {
            setBannerHeight('120px'); // Sufficient height for JWT/salt warnings
          } else {
            setBannerHeight('0px');
          }
        } else {
          setBannerHeight('0px'); // No banner when no warnings
        }
      } catch (error) {
        console.error('Failed to check security status:', error);
        // Don't show banner if we can't determine status
        setSecurityStatus(null);
        setBannerHeight('0px');
      }
    };

    checkSecurityStatus();
    // Check every 30 seconds in case status changes
    const interval = window.setInterval(checkSecurityStatus, 30000);
    
    return () => window.clearInterval(interval);
  }, []);

  if (!securityStatus || (!securityStatus.hasDefaultCredentials && securityStatus.securityWarnings.length === 0)) {
    return null;
  }

  const currentUserId = localStorage.getItem('userid');
  const isLoggedInAsDefault = currentUserId === securityStatus.defaultUserId;
  
  // Find the most severe warning to determine banner style
  const criticalWarnings = securityStatus.securityWarnings.filter(w => w.severity === 'critical');
  const hasCredentialsWarning = securityStatus.hasDefaultCredentials;
  const hasCriticalWarning = criticalWarnings.length > 0 || hasCredentialsWarning;

  return (
    <Box sx={{ 
      width: '100%', 
      position: 'fixed',
      top: 0,
      left: 0,
      zIndex: 1200
    }}>
        <Alert
          severity={hasCriticalWarning ? 'error' : 'warning'}
          icon={<Warning />}
          sx={{
            borderRadius: 0,
            minHeight: hasCredentialsWarning ? '100px' : '120px',
            height: hasCredentialsWarning ? '100px' : '120px',
            fontSize: '16px',
            fontWeight: 'bold',
            boxShadow: '0 4px 8px rgba(0,0,0,0.2)',
            display: 'flex',
            alignItems: 'center',
            paddingTop: '20px',
            paddingBottom: '10px',
            '& .MuiAlert-message': {
              width: '100%',
              display: 'flex',
              alignItems: 'center',
              padding: '0 16px',
            },
            '& .MuiAlert-icon': {
              fontSize: '28px',
              marginRight: '12px',
            },
            ...(hasCriticalWarning && {
              backgroundColor: '#d32f2f !important',
              color: 'white !important',
              borderBottom: '4px solid #b71c1c',
              '& .MuiAlert-icon': {
                color: 'white !important',
              },
            }),
            ...(!hasCriticalWarning && {
              backgroundColor: '#ff9800 !important',
              color: 'white !important',
              borderBottom: '4px solid #f57c00',
              '& .MuiAlert-icon': {
                color: 'white !important',
              },
            }),
          }}
        >
          <Box sx={{ flex: 1 }}>
            {/* Critical credentials warning */}
            {hasCredentialsWarning && isLoggedInAsDefault && (
              <Box sx={{ mb: securityStatus.securityWarnings.length > 0 ? 2 : 0 }}>
                <AlertTitle sx={{ mb: 1, fontWeight: 'bold' }}>
                  {t('security.criticalWarning', 'CRITICAL SECURITY WARNING')}
                </AlertTitle>
                {t('security.loggedInAsDefault', 
                  'You are logged in as the default admin user from the YAML configuration file. This is a security risk! Please create a new admin user, log in with that account, remove the admin credentials from your YAML configuration file, and restart the server.'
                )}
              </Box>
            )}
            {hasCredentialsWarning && !isLoggedInAsDefault && (
              <Box sx={{ mb: securityStatus.securityWarnings.length > 0 ? 2 : 0 }}>
                <AlertTitle sx={{ mb: 1, fontWeight: 'bold' }}>
                  {t('security.configWarning', 'Configuration Security Warning')}
                </AlertTitle>
                {t('security.defaultCredentialsExist', 
                  'Default admin credentials are still configured in your YAML file. Please remove the admin_userid and admin_password from your configuration file and restart the server to improve security.'
                )}
              </Box>
            )}
            
            {/* Other security warnings */}
            {securityStatus.securityWarnings.map((warning, index) => (
              <Box key={index} sx={{ mb: index < securityStatus.securityWarnings.length - 1 ? 1 : 0 }}>
                {securityStatus.securityWarnings.length === 1 && !hasCredentialsWarning && (
                  <AlertTitle sx={{ mb: 1, fontWeight: 'bold' }}>
                    {warning.severity === 'critical' 
                      ? t('security.criticalWarning', 'CRITICAL SECURITY WARNING')
                      : t('security.securityWarning', 'Security Warning')
                    }
                  </AlertTitle>
                )}
                <Box sx={{ fontSize: hasCredentialsWarning ? '14px' : '16px' }}>
                  {warning.message}
                  {warning.details && (
                    <Box sx={{ mt: 0.5, fontSize: '13px', opacity: 0.9 }}>
                      {warning.details}
                    </Box>
                  )}
                </Box>
              </Box>
            ))}
          </Box>
        </Alert>
    </Box>
  );
};

export default SecurityWarningBanner;