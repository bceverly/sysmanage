/**
 * Self-contained MFA enrollment card for the user profile page.
 *
 * Drives four UI states:
 *
 *   1. Not enrolled — "Enable MFA" button.
 *   2. Enrolling   — secret + provisioning URI + first-code field.
 *   3. Enrolled    — status summary + buttons to disable / regenerate
 *                    backup codes.
 *   4. Codes-shown — backup codes panel after enroll/regenerate; user
 *                    must acknowledge before the panel hides them.
 *
 * Rendering rule for backup codes: server returns plaintext exactly
 * once.  We surface them in a copy-friendly block, force the user to
 * tick "I've saved these", and never re-display.
 */

import React, { useEffect, useState } from 'react';
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Checkbox,
  Chip,
  CircularProgress,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  FormControlLabel,
  Stack,
  TextField,
  Typography,
} from '@mui/material';
import VerifiedUserIcon from '@mui/icons-material/VerifiedUser';
import KeyIcon from '@mui/icons-material/Key';
import { useTranslation } from 'react-i18next';

import {
  disableMfa,
  enrollComplete,
  enrollStart,
  EnrollStartResponse,
  getMfaStatus,
  MfaStatus,
  regenerateBackupCodes,
} from '../Services/mfa';

const MfaEnrollmentCard: React.FC = () => {
  const { t } = useTranslation();
  const [status, setStatus] = useState<MfaStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Enrolling-state local data.
  const [enrollData, setEnrollData] = useState<EnrollStartResponse | null>(null);
  const [enrollCode, setEnrollCode] = useState('');
  const [enrolling, setEnrolling] = useState(false);

  // Backup-codes "show once" state.
  const [shownBackupCodes, setShownBackupCodes] = useState<string[] | null>(null);
  const [backupAcknowledged, setBackupAcknowledged] = useState(false);

  // Disable confirmation dialog.
  const [disableOpen, setDisableOpen] = useState(false);
  const [disablePassword, setDisablePassword] = useState('');
  const [disabling, setDisabling] = useState(false);

  // Regenerate-codes dialog.
  const [regenOpen, setRegenOpen] = useState(false);
  const [regenCode, setRegenCode] = useState('');
  const [regenerating, setRegenerating] = useState(false);

  const refreshStatus = async () => {
    setLoading(true);
    setError(null);
    try {
      const s = await getMfaStatus();
      setStatus(s);
    } catch {
      setError(t('mfa.statusError', 'Could not load MFA status.'));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    refreshStatus();
    // refreshStatus is stable for the component lifetime; including it
    // would re-fetch on every render.  Mount-only is the intended
    // behavior.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleStartEnroll = async () => {
    setEnrolling(true);
    setError(null);
    try {
      const resp = await enrollStart();
      setEnrollData(resp);
      setEnrollCode('');
    } catch {
      setError(t('mfa.startError', 'Could not start enrollment.'));
    } finally {
      setEnrolling(false);
    }
  };

  const handleCompleteEnroll = async () => {
    if (!enrollCode.trim()) return;
    setEnrolling(true);
    setError(null);
    try {
      const resp = await enrollComplete(enrollCode.trim());
      setShownBackupCodes(resp.backup_codes);
      setBackupAcknowledged(false);
      setEnrollData(null);
      setEnrollCode('');
      await refreshStatus();
    } catch {
      setError(t('mfa.invalidCode', 'Invalid code — please try again.'));
    } finally {
      setEnrolling(false);
    }
  };

  const handleDisable = async () => {
    if (!disablePassword) return;
    setDisabling(true);
    setError(null);
    try {
      await disableMfa(disablePassword);
      setDisableOpen(false);
      setDisablePassword('');
      await refreshStatus();
    } catch {
      setError(t('mfa.disableError', 'Could not disable MFA — check your password.'));
    } finally {
      setDisabling(false);
    }
  };

  const handleRegenerate = async () => {
    if (!regenCode.trim()) return;
    setRegenerating(true);
    setError(null);
    try {
      const resp = await regenerateBackupCodes(regenCode.trim());
      setShownBackupCodes(resp.backup_codes);
      setBackupAcknowledged(false);
      setRegenOpen(false);
      setRegenCode('');
      await refreshStatus();
    } catch {
      setError(t('mfa.regenError', 'Could not regenerate codes — check your TOTP code.'));
    } finally {
      setRegenerating(false);
    }
  };

  // ----- Render: backup-codes "show once" panel ----------------------
  if (shownBackupCodes) {
    return (
      <Card variant="outlined" sx={{ mb: 3 }}>
        <CardContent>
          <Stack direction="row" alignItems="center" spacing={1} sx={{ mb: 2 }}>
            <KeyIcon color="warning" />
            <Typography variant="h6">
              {t('mfa.backupCodesTitle', 'Save your backup codes')}
            </Typography>
          </Stack>
          <Alert severity="warning" sx={{ mb: 2 }}>
            {t(
              'mfa.backupCodesWarning',
              'These one-time backup codes will not be shown again. Save them in a password manager or print them. Each code works once if you lose access to your authenticator.',
            )}
          </Alert>
          <Box
            sx={{
              fontFamily: 'monospace',
              backgroundColor: 'grey.100',
              p: 2,
              borderRadius: 1,
              mb: 2,
              display: 'grid',
              gridTemplateColumns: 'repeat(2, 1fr)',
              gap: 1,
            }}
          >
            {shownBackupCodes.map((code) => (
              <Box key={code}>{code}</Box>
            ))}
          </Box>
          <FormControlLabel
            control={
              <Checkbox
                checked={backupAcknowledged}
                onChange={(e) => setBackupAcknowledged(e.target.checked)}
              />
            }
            label={t('mfa.backupCodesConfirm', "I've saved these codes in a safe place")}
          />
          <Box>
            <Button
              variant="contained"
              disabled={!backupAcknowledged}
              onClick={() => setShownBackupCodes(null)}
            >
              {t('mfa.done', 'Done')}
            </Button>
          </Box>
        </CardContent>
      </Card>
    );
  }

  // ----- Render: loading / error -------------------------------------
  if (loading) {
    return (
      <Card variant="outlined" sx={{ mb: 3 }}>
        <CardContent>
          <CircularProgress size={20} />
        </CardContent>
      </Card>
    );
  }

  // ----- Render: enrolling (showing secret + first-code field) -------
  if (enrollData) {
    return (
      <Card variant="outlined" sx={{ mb: 3 }}>
        <CardContent>
          <Stack direction="row" alignItems="center" spacing={1} sx={{ mb: 2 }}>
            <VerifiedUserIcon color="primary" />
            <Typography variant="h6">{t('mfa.enrollTitle', 'Set up Two-Factor Authentication')}</Typography>
          </Stack>
          {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}
          <Typography variant="body2" sx={{ mb: 1 }}>
            {t('mfa.enrollStep1', '1. Open your authenticator app and add a new account using this URI:')}
          </Typography>
          <Box
            sx={{
              fontFamily: 'monospace',
              fontSize: '0.85rem',
              wordBreak: 'break-all',
              backgroundColor: 'grey.100',
              p: 1.5,
              borderRadius: 1,
              mb: 2,
            }}
          >
            {enrollData.provisioning_uri}
          </Box>
          <Typography variant="body2" sx={{ mb: 1 }}>
            {t('mfa.enrollStep1b', 'Or enter this secret manually:')}{' '}
            <strong style={{ fontFamily: 'monospace' }}>{enrollData.secret}</strong>
          </Typography>
          <Typography variant="body2" sx={{ mb: 2 }}>
            {t('mfa.enrollStep2', '2. Enter the 6-digit code your app shows below to confirm.')}
          </Typography>
          <Stack direction="row" spacing={2} alignItems="flex-start">
            <TextField
              size="small"
              autoFocus
              label={t('mfa.codeLabel', 'Code from authenticator')}
              value={enrollCode}
              onChange={(e) => setEnrollCode(e.target.value)}
              slotProps={{ htmlInput: { inputMode: 'numeric', maxLength: 6 } }}
              sx={{ width: 220 }}
            />
            <Button
              variant="contained"
              disabled={enrolling || enrollCode.trim() === ''}
              onClick={handleCompleteEnroll}
            >
              {enrolling ? <CircularProgress size={20} /> : t('mfa.verifyAndEnroll', 'Verify & Enrol')}
            </Button>
            <Button
              variant="text"
              onClick={() => {
                setEnrollData(null);
                setEnrollCode('');
              }}
            >
              {t('common.cancel', 'Cancel')}
            </Button>
          </Stack>
        </CardContent>
      </Card>
    );
  }

  // ----- Render: enrolled --------------------------------------------
  if (status?.enrolled) {
    return (
      <Card variant="outlined" sx={{ mb: 3 }}>
        <CardContent>
          <Stack direction="row" alignItems="center" spacing={1} sx={{ mb: 1 }}>
            <VerifiedUserIcon color="success" />
            <Typography variant="h6">{t('mfa.enabledTitle', 'Two-Factor Authentication: Enabled')}</Typography>
          </Stack>
          {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}
          <Stack direction="row" spacing={2} sx={{ mb: 2 }}>
            <Chip
              label={t('mfa.backupCodesRemaining', '{{count}} backup codes left', {
                count: status.remaining_backup_codes,
              })}
              color={status.remaining_backup_codes > 2 ? 'default' : 'warning'}
              size="small"
            />
            {status.last_used_at && (
              <Chip
                label={t('mfa.lastUsedAt', 'Last used: {{when}}', {
                  when: new Date(status.last_used_at).toLocaleString(),
                })}
                size="small"
                variant="outlined"
              />
            )}
          </Stack>
          <Stack direction="row" spacing={2}>
            <Button variant="outlined" color="primary" onClick={() => setRegenOpen(true)}>
              {t('mfa.regenerate', 'Regenerate backup codes')}
            </Button>
            <Button variant="outlined" color="error" onClick={() => setDisableOpen(true)}>
              {t('mfa.disable', 'Disable MFA')}
            </Button>
          </Stack>
        </CardContent>

        <Dialog open={disableOpen} onClose={() => setDisableOpen(false)}>
          <DialogTitle>{t('mfa.disableTitle', 'Disable Two-Factor Authentication?')}</DialogTitle>
          <DialogContent>
            <Typography variant="body2" sx={{ mb: 2 }}>
              {t(
                'mfa.disableWarning',
                'Confirm with your account password. Your TOTP secret and backup codes will be deleted.',
              )}
            </Typography>
            <TextField
              autoFocus
              fullWidth
              type="password"
              label={t('mfa.password', 'Password')}
              value={disablePassword}
              onChange={(e) => setDisablePassword(e.target.value)}
            />
          </DialogContent>
          <DialogActions>
            <Button onClick={() => setDisableOpen(false)}>{t('common.cancel', 'Cancel')}</Button>
            <Button
              color="error"
              variant="contained"
              disabled={disabling || !disablePassword}
              onClick={handleDisable}
            >
              {disabling ? <CircularProgress size={20} /> : t('mfa.disableConfirm', 'Disable')}
            </Button>
          </DialogActions>
        </Dialog>

        <Dialog open={regenOpen} onClose={() => setRegenOpen(false)}>
          <DialogTitle>{t('mfa.regenTitle', 'Regenerate backup codes')}</DialogTitle>
          <DialogContent>
            <Typography variant="body2" sx={{ mb: 2 }}>
              {t(
                'mfa.regenPrompt',
                'Enter a current TOTP code. Existing backup codes will be invalidated.',
              )}
            </Typography>
            <TextField
              autoFocus
              fullWidth
              label={t('mfa.codeLabel', 'Code from authenticator')}
              value={regenCode}
              onChange={(e) => setRegenCode(e.target.value)}
              slotProps={{ htmlInput: { inputMode: 'numeric', maxLength: 6 } }}
            />
          </DialogContent>
          <DialogActions>
            <Button onClick={() => setRegenOpen(false)}>{t('common.cancel', 'Cancel')}</Button>
            <Button
              variant="contained"
              disabled={regenerating || !regenCode.trim()}
              onClick={handleRegenerate}
            >
              {regenerating ? <CircularProgress size={20} /> : t('mfa.regenConfirm', 'Regenerate')}
            </Button>
          </DialogActions>
        </Dialog>
      </Card>
    );
  }

  // ----- Render: not enrolled ----------------------------------------
  return (
    <Card variant="outlined" sx={{ mb: 3 }}>
      <CardContent>
        <Stack direction="row" alignItems="center" spacing={1} sx={{ mb: 1 }}>
          <VerifiedUserIcon color="action" />
          <Typography variant="h6">
            {t('mfa.notEnrolledTitle', 'Two-Factor Authentication')}
          </Typography>
        </Stack>
        {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}
        <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
          {t(
            'mfa.notEnrolledDescription',
            'Add a second factor to your account. You\'ll be asked for a one-time code from an authenticator app each time you sign in.',
          )}
        </Typography>
        {status?.admin_required && (
          <Alert severity="warning" sx={{ mb: 2 }}>
            {t(
              'mfa.adminRequiredNotice',
              'Your administrator requires multi-factor authentication. New accounts have a {{days}}-day grace period.',
              { days: status.grace_period_days },
            )}
          </Alert>
        )}
        <Button variant="contained" disabled={enrolling} onClick={handleStartEnroll}>
          {enrolling ? <CircularProgress size={20} /> : t('mfa.enable', 'Enable MFA')}
        </Button>
      </CardContent>
    </Card>
  );
};

export default MfaEnrollmentCard;
