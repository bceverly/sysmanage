import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  CircularProgress,
  Divider,
  FormControlLabel,
  Snackbar,
  Switch,
  TextField,
  Typography,
} from '@mui/material';
import SaveIcon from '@mui/icons-material/Save';
import { useTranslation } from 'react-i18next';

import { ServerSetting, serverSettingsService } from '../Services/serverSettings';

// Human-friendly labels + group order. Defaults double as the English copy
// so the panel is usable before locale files are translated.
const GROUP_ORDER = ['security', 'monitoring', 'message_queue', 'email'];

const GROUP_LABELS: Record<string, [string, string]> = {
  security: ['configuration.group.security', 'Security & Sessions'],
  monitoring: ['configuration.group.monitoring', 'Monitoring'],
  message_queue: ['configuration.group.messageQueue', 'Message Queue'],
  email: ['configuration.group.email', 'Email'],
};

const FIELD_LABELS: Record<string, [string, string]> = {
  heartbeat_timeout: ['configuration.field.heartbeatTimeout', 'Heartbeat timeout (minutes)'],
  max_failed_logins: ['configuration.field.maxFailedLogins', 'Max failed logins before lockout'],
  account_lockout_duration: ['configuration.field.lockoutDuration', 'Account lockout duration (minutes)'],
  jwt_auth_timeout: ['configuration.field.jwtAuthTimeout', 'Access token lifetime (seconds)'],
  jwt_refresh_timeout: ['configuration.field.jwtRefreshTimeout', 'Refresh token lifetime (seconds)'],
  cookie_domain: ['configuration.field.cookieDomain', 'Cookie domain (blank = host only)'],
  mq_expiration_minutes: ['configuration.field.mqExpiration', 'Message expiration (minutes)'],
  mq_cleanup_minutes: ['configuration.field.mqCleanup', 'Cleanup interval (minutes)'],
  email_enabled: ['configuration.field.emailEnabled', 'Email enabled'],
  email_host: ['configuration.field.emailHost', 'SMTP host'],
  email_port: ['configuration.field.emailPort', 'SMTP port'],
  email_use_tls: ['configuration.field.emailUseTls', 'Use STARTTLS'],
  email_use_ssl: ['configuration.field.emailUseSsl', 'Use SSL/TLS'],
  email_username: ['configuration.field.emailUsername', 'SMTP username'],
  email_from_address: ['configuration.field.emailFromAddress', 'From address'],
  email_from_name: ['configuration.field.emailFromName', 'From name'],
  email_password: ['configuration.field.emailPassword', 'SMTP password'],
};

const ConfigurationSettings: React.FC = () => {
  const { t } = useTranslation();
  const [settings, setSettings] = useState<ServerSetting[]>([]);
  const [values, setValues] = useState<Record<string, number | boolean | string>>({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [savedOpen, setSavedOpen] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await serverSettingsService.get();
      setSettings(data);
      const v: Record<string, number | boolean | string> = {};
      data.forEach((s) => {
        v[s.key] = s.value;
      });
      setValues(v);
    } catch {
      setError(t('configuration.loadError', 'Failed to load configuration settings.'));
    } finally {
      setLoading(false);
    }
  }, [t]);

  useEffect(() => {
    load();
  }, [load]);

  const grouped = useMemo(() => {
    const map: Record<string, ServerSetting[]> = {};
    settings.forEach((s) => {
      (map[s.group] = map[s.group] || []).push(s);
    });
    return map;
  }, [settings]);

  const setValue = (key: string, value: number | boolean | string) => {
    setValues((prev) => ({ ...prev, [key]: value }));
  };

  const handleSave = async () => {
    setSaving(true);
    setError(null);
    try {
      const updated = await serverSettingsService.update(values);
      setSettings(updated);
      setSavedOpen(true);
    } catch {
      setError(t('configuration.saveError', 'Failed to save configuration settings.'));
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <Box sx={{ display: 'flex', justifyContent: 'center', p: 4 }}>
        <CircularProgress />
      </Box>
    );
  }

  return (
    <Box>
      <Typography variant="h6" gutterBottom>
        {t('configuration.title', 'Configuration')}
      </Typography>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
        {t(
          'configuration.description',
          'Server-wide operational settings. Saved values are stored in the database and override sysmanage.yaml.',
        )}
      </Typography>

      {error && (
        <Alert severity="error" sx={{ mb: 2 }} onClose={() => setError(null)}>
          {error}
        </Alert>
      )}

      {GROUP_ORDER.filter((g) => grouped[g]?.length).map((group) => {
        const [labelKey, labelDefault] = GROUP_LABELS[group] || [group, group];
        return (
          <Card key={group} variant="outlined" sx={{ mb: 2 }}>
            <CardContent>
              <Typography variant="subtitle1" sx={{ fontWeight: 600 }}>
                {t(labelKey, labelDefault)}
              </Typography>
              <Divider sx={{ my: 1.5 }} />
              <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2, maxWidth: 480 }}>
                {grouped[group].map((s) => {
                  const [fk, fd] = FIELD_LABELS[s.key] || [s.key, s.key];
                  const label = t(fk, fd);
                  if (s.type === 'secret') {
                    // Write-only: the value is never sent from the server; a
                    // blank submission leaves the stored secret unchanged.
                    return (
                      <TextField
                        key={s.key}
                        label={label}
                        type="password"
                        size="small"
                        autoComplete="new-password"
                        value={String(values[s.key] ?? '')}
                        onChange={(e) => setValue(s.key, e.target.value)}
                        placeholder={
                          s.configured
                            ? t('configuration.secretSet', '•••••••• (stored — leave blank to keep)')
                            : t('configuration.secretUnset', 'Not set')
                        }
                        helperText={
                          s.configured
                            ? t('configuration.secretSetHelp', 'A password is stored in OpenBAO. Type a new one to replace it.')
                            : t('configuration.secretUnsetHelp', 'Stored securely in OpenBAO, not in the database.')
                        }
                        InputLabelProps={{ shrink: true }}
                        fullWidth
                      />
                    );
                  }
                  if (s.type === 'bool') {
                    return (
                      <FormControlLabel
                        key={s.key}
                        control={
                          <Switch
                            checked={Boolean(values[s.key])}
                            onChange={(e) => setValue(s.key, e.target.checked)}
                          />
                        }
                        label={label}
                      />
                    );
                  }
                  return (
                    <TextField
                      key={s.key}
                      label={label}
                      type={s.type === 'int' ? 'number' : 'text'}
                      size="small"
                      value={values[s.key] ?? ''}
                      onChange={(e) =>
                        setValue(
                          s.key,
                          s.type === 'int'
                            ? Number(e.target.value)
                            : e.target.value,
                        )
                      }
                      fullWidth
                    />
                  );
                })}
              </Box>
            </CardContent>
          </Card>
        );
      })}

      <Box sx={{ mt: 2 }}>
        <Button
          variant="contained"
          startIcon={saving ? <CircularProgress size={18} /> : <SaveIcon />}
          onClick={handleSave}
          disabled={saving}
        >
          {t('configuration.save', 'Save')}
        </Button>
      </Box>

      <Snackbar
        open={savedOpen}
        autoHideDuration={3000}
        onClose={() => setSavedOpen(false)}
        message={t('configuration.saved', 'Configuration saved.')}
      />
    </Box>
  );
};

export default ConfigurationSettings;
