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
        const response = await api.get('/api/security/default-credentials-status');
        const status = response.data;
        setSecurityStatus(status);
        
        // Set banner height based on security warnings
        if (status && (status.hasDefaultCredentials || status.securityWarnings.length > 0)) {
          // Calculate height based on content - be more dynamic
          const hasCredentials = status.hasDefaultCredentials;
          const warningCount = status.securityWarnings.length;
          
          // Base height for padding and icon
          let calculatedHeight = 80;
          
          // Add height for credentials warning
          if (hasCredentials) {
            // Check if user is logged in as default (needs step-by-step instructions)
            const currentUserId = localStorage.getItem('userid');
            const isLoggedInAsDefault = currentUserId === status.defaultUserId;

            if (isLoggedInAsDefault) {
              calculatedHeight += 280; // For detailed step-by-step instructions
            } else {
              calculatedHeight += 90; // For basic credentials warning
            }
          }
          
          // Add height for each security warning (JWT, salt, etc.)
          for (let i = 0; i < warningCount; i++) {
            calculatedHeight += 85; // Each warning with command text and styling needs more space
          }
          
          setBannerHeight(`${calculatedHeight}px`);
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
            minHeight: 'auto',
            height: 'auto',
            fontSize: '16px',
            fontWeight: 'bold',
            boxShadow: '0 4px 8px rgba(0,0,0,0.2)',
            display: 'flex',
            alignItems: 'flex-start',
            paddingTop: '20px',
            paddingBottom: '20px',
            '& .MuiAlert-message': {
              width: '100%',
              display: 'flex',
              alignItems: 'flex-start',
              padding: '0 16px',
              flexDirection: 'column',
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
              <Box sx={{ mb: securityStatus.securityWarnings.length > 0 ? 3 : 0 }}>
                <AlertTitle sx={{ mb: 1.5, fontWeight: 'bold', fontSize: '18px' }}>
                  {t('security.criticalWarning', 'CRITICAL SECURITY WARNING')}
                </AlertTitle>
                <Box sx={{ fontSize: '16px', lineHeight: 1.5 }}>
                  {t('security.loggedInAsDefault',
                    'You are logged in as the default admin user from the YAML configuration file. This is a critical security risk! Follow these steps in order:'
                  )}
                </Box>
                <Box sx={{ mt: 2, fontSize: '15px', lineHeight: 1.6 }}>
                  <Box sx={{ fontWeight: 'bold', mb: 1 }}>
                    {t('security.securityStepsTitle', 'Required Security Steps (in order):')}
                  </Box>
                  <Box sx={{ ml: 2 }}>
                    <Box sx={{ mb: 1 }}>
                      1. {t('security.step1JwtSecret', 'Change JWT secret: Run')}{' '}
                      <Box component="span" sx={{
                        fontFamily: 'monospace',
                        backgroundColor: 'rgba(255,255,255,0.2)',
                        padding: '2px 6px',
                        borderRadius: '3px'
                      }}>
                        python3 scripts/migrate-security-config.py --jwt-only
                      </Box>
                    </Box>
                    <Box sx={{ mb: 1 }}>
                      2. {t('security.step2PasswordSalt', 'Change password salt: Run')}{' '}
                      <Box component="span" sx={{
                        fontFamily: 'monospace',
                        backgroundColor: 'rgba(255,255,255,0.2)',
                        padding: '2px 6px',
                        borderRadius: '3px'
                      }}>
                        python3 scripts/migrate-security-config.py --salt-only
                      </Box>
                    </Box>
                    <Box sx={{ mb: 1 }}>
                      3. {t('security.step3CreateUser', 'Create a new admin user via the Users page in this interface')}
                    </Box>
                    <Box sx={{ mb: 1 }}>
                      4. {t('security.step4LoginNewUser', 'Log out and log in with your new admin account')}
                    </Box>
                    <Box sx={{ mb: 1 }}>
                      5. {t('security.step5RemoveCredentials', 'Remove admin_userid and admin_password from your YAML configuration file')}
                    </Box>
                    <Box>
                      6. {t('security.step6RestartServer', 'Restart the server with ./run.sh')}
                    </Box>
                  </Box>
                </Box>
              </Box>
            )}
            {hasCredentialsWarning && !isLoggedInAsDefault && (
              <Box sx={{ mb: securityStatus.securityWarnings.length > 0 ? 3 : 0 }}>
                <AlertTitle sx={{ mb: 1.5, fontWeight: 'bold', fontSize: '18px' }}>
                  {t('security.configWarning', 'Configuration Security Warning')}
                </AlertTitle>
                <Box sx={{ fontSize: '16px', lineHeight: 1.5 }}>
                  {t('security.defaultCredentialsExist', 
                    'Default admin credentials are configured in your YAML file'
                  )}
                </Box>
                <Box sx={{ fontSize: '14px', mt: 1, opacity: 0.9 }}>
                  Remove admin_userid and admin_password from your configuration file and restart the server
                </Box>
              </Box>
            )}
            
            {/* Other security warnings */}
            {securityStatus.securityWarnings.map((warning, index) => (
              <Box key={index} sx={{ mb: index < securityStatus.securityWarnings.length - 1 ? 2.5 : 0 }}>
                {securityStatus.securityWarnings.length === 1 && !hasCredentialsWarning && (
                  <AlertTitle sx={{ mb: 1.5, fontWeight: 'bold', fontSize: '18px' }}>
                    {warning.severity === 'critical'
                      ? t('security.criticalWarning', 'CRITICAL SECURITY WARNING')
                      : warning.type === 'email_integration_required'
                        ? t('security.emailConfigurationWarning', 'Email Configuration Required')
                        : t('security.securityWarning', 'Security Warning')
                    }
                  </AlertTitle>
                )}
                <Box sx={{ fontSize: hasCredentialsWarning ? '15px' : '16px', lineHeight: 1.5 }}>
                  {warning.message}
                  {warning.details && (
                    <Box sx={{
                      mt: 1,
                      fontSize: '14px',
                      opacity: 0.95,
                      fontFamily: warning.type === 'email_integration_required' ? 'inherit' : 'monospace',
                      backgroundColor: 'rgba(255,255,255,0.1)',
                      padding: '8px 12px',
                      borderRadius: '4px',
                      border: '1px solid rgba(255,255,255,0.2)'
                    }}>
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