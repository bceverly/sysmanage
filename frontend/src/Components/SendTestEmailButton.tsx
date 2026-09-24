// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

/**
 * "Test Configuration" for the Email settings group: sends a test message
 * through the SAVED SMTP settings (POST /api/v1/email/test).
 *
 * It lived in EmailConfigCard, which stopped being rendered anywhere when
 * email settings moved from sysmanage.yaml to Settings -> Configuration -- so
 * there was no way to test email from the UI at all. The button now sits in
 * the Email group itself.  The server reports what went wrong (not enabled,
 * not configured, SMTP refused), so the result is shown rather than the
 * button being pre-emptively disabled on a guess.
 */

import React, { useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  Alert,
  Box,
  Button,
  CircularProgress,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  TextField,
  Typography,
} from '@mui/material';
import { Email as EmailIcon } from '@mui/icons-material';
import { emailService } from '../Services/emailService';

type Result = { success: boolean; message: string } | null;

const SendTestEmailButton: React.FC = () => {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const [address, setAddress] = useState('');
  const [sending, setSending] = useState(false);
  const [result, setResult] = useState<Result>(null);

  const close = () => {
    setOpen(false);
    setAddress('');
    setResult(null);
  };

  const send = async () => {
    if (!address.trim()) {
      setResult({ success: false, message: t('emailConfig.enterEmail', 'Please enter an email address') });
      return;
    }
    setSending(true);
    setResult(null);
    try {
      const outcome = await emailService.sendTestEmail(address);
      setResult(outcome);
      if (outcome.success) {
        setTimeout(close, 2000);
      }
    } catch {
      setResult({
        success: false,
        message: t('emailConfig.sendFailed', 'Failed to send test email. Please check your configuration.'),
      });
    } finally {
      setSending(false);
    }
  };

  return (
    <Box>
      <Button variant="outlined" startIcon={<EmailIcon />} onClick={() => setOpen(true)}>
        {t('emailConfig.testConfiguration', 'Test Configuration')}
      </Button>
      <Dialog open={open} onClose={close} maxWidth="sm" fullWidth>
        <DialogTitle>{t('emailConfig.testDialogTitle', 'Test Email Configuration')}</DialogTitle>
        <DialogContent>
          <Typography variant="body2" color="text.secondary" gutterBottom sx={{ mb: 2 }}>
            {t(
              'emailConfig.testDialogBody',
              'Send a test email to verify your SMTP configuration is working correctly.',
            )}
          </Typography>
          <TextField
            autoFocus
            margin="dense"
            label={t('emailConfig.emailAddressLabel', 'Email Address')}
            type="email"
            fullWidth
            variant="outlined"
            value={address}
            onChange={(e) => setAddress(e.target.value)}
            placeholder={t('emailConfig.emailAddressPlaceholder', 'Enter email address to send test message')}
            disabled={sending}
          />
          {result && (
            <Alert severity={result.success ? 'success' : 'error'} sx={{ mt: 2 }}>
              {result.message}
            </Alert>
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={close} disabled={sending}>
            {t('common.cancel', 'Cancel')}
          </Button>
          <Button
            onClick={send}
            variant="contained"
            disabled={sending || !address.trim()}
            startIcon={sending ? <CircularProgress size={16} /> : <EmailIcon />}
          >
            {sending ? t('emailConfig.sending', 'Sending...') : t('emailConfig.sendTest', 'Send Test Email')}
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
};

export default SendTestEmailButton;
