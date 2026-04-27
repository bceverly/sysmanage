import React, { useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import {
  Card,
  CardContent,
  CardHeader,
  Typography,
  Button,
  Grid,
  Chip,
  Box,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  TextField,
  Alert,
  CircularProgress
} from '@mui/material';
import {
  Email as EmailIcon,
  CheckCircle as CheckCircleIcon,
  Warning as WarningIcon,
  Error as ErrorIcon
} from '@mui/icons-material';
import { emailService, EmailConfig } from '../Services/emailService';

const EmailConfigCard: React.FC = () => {
  const { t } = useTranslation();
  const [config, setConfig] = useState<EmailConfig | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  
  // Test email dialog state
  const [testDialogOpen, setTestDialogOpen] = useState(false);
  const [testEmail, setTestEmail] = useState('');
  const [testLoading, setTestLoading] = useState(false);
  const [testResult, setTestResult] = useState<{ success: boolean; message: string } | null>(null);

  // Load email configuration on mount.  Defining loadConfig inside the
  // effect keeps `t` as the only dependency without requiring useCallback.
  useEffect(() => {
    const loadConfig = async () => {
      try {
        setLoading(true);
        setError(null);
        const emailConfig = await emailService.getConfig();
        setConfig(emailConfig);
      } catch (err) {
        console.error('Failed to load email configuration:', err);
        setError(t('emailConfig.loadFailed', 'Failed to load email configuration'));
      } finally {
        setLoading(false);
      }
    };
    loadConfig();
  }, [t]);

  const handleTestEmail = async () => {
    if (!testEmail.trim()) {
      setTestResult({ success: false, message: t('emailConfig.enterEmail', 'Please enter an email address') });
      return;
    }

    try {
      setTestLoading(true);
      setTestResult(null);
      const result = await emailService.sendTestEmail(testEmail);
      setTestResult(result);

      // Auto-close dialog after successful email send
      if (result.success) {
        setTimeout(() => {
          handleCloseTestDialog();
        }, 2000); // Close after 2 seconds to show success message
      }
    } catch (err) {
      console.error('Failed to send test email:', err);
      setTestResult({
        success: false,
        message: t('emailConfig.sendFailed', 'Failed to send test email. Please check your configuration.')
      });
    } finally {
      setTestLoading(false);
    }
  };

  const handleCloseTestDialog = () => {
    setTestDialogOpen(false);
    setTestEmail('');
    setTestResult(null);
  };

  const getStatusIcon = () => {
    if (!config) return <WarningIcon color="disabled" />;
    
    if (!config.enabled) {
      return <WarningIcon color="warning" />;
    }
    
    if (!config.configured) {
      return <ErrorIcon color="error" />;
    }
    
    return <CheckCircleIcon color="success" />;
  };

  const getStatusText = () => {
    if (!config) return t('emailConfig.status.unknown', 'Unknown');

    if (!config.enabled) {
      return t('emailConfig.status.disabled', 'Disabled');
    }

    if (!config.configured) {
      return t('emailConfig.status.notConfigured', 'Not Configured');
    }

    return t('emailConfig.status.configured', 'Configured');
  };

  const getStatusColor = (): 'default' | 'success' | 'warning' | 'error' => {
    if (!config) return 'default';
    
    if (!config.enabled) return 'warning';
    if (!config.configured) return 'error';
    
    return 'success';
  };

  if (loading) {
    return (
      <Card>
        <CardHeader
          avatar={<EmailIcon />}
          title={t('emailConfig.title', 'Email Configuration')}
          subheader={t('emailConfig.subheader', 'SMTP settings for notifications and password reset')}
        />
        <CardContent>
          <Box display="flex" justifyContent="center" p={2}>
            <CircularProgress />
          </Box>
        </CardContent>
      </Card>
    );
  }

  if (error) {
    return (
      <Card>
        <CardHeader
          avatar={<EmailIcon />}
          title={t('emailConfig.title', 'Email Configuration')}
          subheader={t('emailConfig.subheader', 'SMTP settings for notifications and password reset')}
        />
        <CardContent>
          <Alert severity="error">{error}</Alert>
        </CardContent>
      </Card>
    );
  }

  return (
    <>
      <Card>
        <CardHeader
          avatar={<EmailIcon />}
          title={t('emailConfig.title', 'Email Configuration')}
          subheader={t('emailConfig.subheader', 'SMTP settings for notifications and password reset')}
          action={
            <Box display="flex" alignItems="center" gap={1}>
              {getStatusIcon()}
              <Chip 
                label={getStatusText()} 
                color={getStatusColor()}
                size="small"
              />
            </Box>
          }
        />
        <CardContent>
          {config && (
            <Grid container spacing={2}>
              <Grid size={{ xs: 12, sm: 6 }}>
                <Typography variant="body2" color="text.secondary" gutterBottom>
                  {t('emailConfig.smtpServer', 'SMTP Server')}
                </Typography>
                <Typography variant="body1">
                  {config.smtp_host}:{config.smtp_port}
                </Typography>
              </Grid>

              <Grid size={{ xs: 12, sm: 6 }}>
                <Typography variant="body2" color="text.secondary" gutterBottom>
                  {t('emailConfig.fromAddress', 'From Address')}
                </Typography>
                <Typography variant="body1">
                  {config.from_name} &lt;{config.from_address}&gt;
                </Typography>
              </Grid>

              <Grid size={{ xs: 12, sm: 6 }}>
                <Typography variant="body2" color="text.secondary" gutterBottom>
                  {t('emailConfig.subjectPrefix', 'Subject Prefix')}
                </Typography>
                <Typography variant="body1">
                  {config.subject_prefix || t('common.none', 'None')}
                </Typography>
              </Grid>

              <Grid size={{ xs: 12, sm: 6 }}>
                <Typography variant="body2" color="text.secondary" gutterBottom>
                  {t('emailConfig.statusLabel', 'Status')}
                </Typography>
                <Typography variant="body1">
                  {config.enabled
                    ? t('emailConfig.status.enabled', 'Enabled')
                    : t('emailConfig.status.disabled', 'Disabled')}
                  {config.enabled && !config.configured &&
                    ' ' + t('emailConfig.statusSuffix.notConfigured', '(Not Configured)')}
                </Typography>
              </Grid>

              <Grid size={{ xs: 12 }}>
                <Box mt={2}>
                  <Button
                    variant="outlined"
                    onClick={() => setTestDialogOpen(true)}
                    disabled={!config.enabled || !config.configured}
                    startIcon={<EmailIcon />}
                  >
                    {t('emailConfig.testConfiguration', 'Test Configuration')}
                  </Button>
                  {(!config.enabled || !config.configured) && (
                    <Typography variant="caption" color="text.secondary" sx={{ ml: 2 }}>
                      {t('emailConfig.configureHint', 'Configure email settings in sysmanage.yaml to enable testing')}
                    </Typography>
                  )}
                </Box>
              </Grid>
            </Grid>
          )}
        </CardContent>
      </Card>

      {/* Test Email Dialog */}
      <Dialog open={testDialogOpen} onClose={handleCloseTestDialog} maxWidth="sm" fullWidth>
        <DialogTitle>{t('emailConfig.testDialogTitle', 'Test Email Configuration')}</DialogTitle>
        <DialogContent>
          <Typography variant="body2" color="text.secondary" gutterBottom sx={{ mb: 2 }}>
            {t('emailConfig.testDialogBody', 'Send a test email to verify your SMTP configuration is working correctly.')}
          </Typography>

          <TextField
            autoFocus
            margin="dense"
            label={t('emailConfig.emailAddressLabel', 'Email Address')}
            type="email"
            fullWidth
            variant="outlined"
            value={testEmail}
            onChange={(e) => setTestEmail(e.target.value)}
            placeholder={t('emailConfig.emailAddressPlaceholder', 'Enter email address to send test message')}
            disabled={testLoading}
          />
          
          {testResult && (
            <Alert 
              severity={testResult.success ? 'success' : 'error'} 
              sx={{ mt: 2 }}
            >
              {testResult.message}
            </Alert>
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={handleCloseTestDialog} disabled={testLoading}>
            {t('common.cancel', 'Cancel')}
          </Button>
          <Button
            onClick={handleTestEmail}
            variant="contained"
            disabled={testLoading || !testEmail.trim()}
            startIcon={testLoading ? <CircularProgress size={16} /> : <EmailIcon />}
          >
            {testLoading
              ? t('emailConfig.sending', 'Sending...')
              : t('emailConfig.sendTest', 'Send Test Email')}
          </Button>
        </DialogActions>
      </Dialog>
    </>
  );
};

export default EmailConfigCard;