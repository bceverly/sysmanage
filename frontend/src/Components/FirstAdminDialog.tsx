// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

import React, { useState } from 'react';
import {
  Alert,
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Stack,
  TextField,
} from '@mui/material';
import { useTranslation } from 'react-i18next';
import axios from 'axios';
import api from '../Services/api';

interface FirstAdminDialogProps {
  open: boolean;
  onClose: () => void;
}

/**
 * FirstAdminDialog -- the recovery account creates the first administrator.
 *
 * A fresh installation's only account is the recovery admin in
 * sysmanage.yaml, which has no database row and so cannot approve hosts, and
 * the Users page needs SMTP to give a new user a password.  This creates one
 * administrator with a password and every role (POST
 * /api/v1/security/first-admin), then offers to sign out so the operator can
 * sign in as it.
 */
const FirstAdminDialog: React.FC<FirstAdminDialogProps> = ({ open, onClose }) => {
  const { t } = useTranslation();
  const [userid, setUserid] = useState('');
  const [firstName, setFirstName] = useState('');
  const [lastName, setLastName] = useState('');
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [created, setCreated] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async () => {
    setBusy(true);
    setError(null);
    try {
      await api.post('/api/v1/security/first-admin', {
        userid,
        first_name: firstName || null,
        last_name: lastName || null,
        password,
        confirm_password: confirm,
      });
      setCreated(userid);
    } catch (err: unknown) {
      const detail = axios.isAxiosError(err) ? err.response?.data?.detail : null;
      setError(
        typeof detail === 'string'
          ? detail
          : t('security.firstAdmin.failed', 'Could not create the administrator.'),
      );
    } finally {
      setBusy(false);
    }
  };

  const signOut = () => {
    globalThis.location.assign('/logout');
  };

  return (
    <Dialog open={open} onClose={busy ? undefined : onClose} maxWidth="sm" fullWidth>
      <DialogTitle>{t('security.firstAdmin.title', 'Create your administrator')}</DialogTitle>
      <DialogContent>
        {created ? (
          <Alert severity="success" sx={{ mt: 1 }}>
            {t('security.firstAdmin.created', {
              defaultValue: 'Administrator {{userid}} created. Sign out, then sign in as {{userid}}.',
              userid: created,
            })}
          </Alert>
        ) : (
          <Stack spacing={2} sx={{ mt: 1 }}>
            <Alert severity="info">
              {t(
                'security.firstAdmin.explain',
                'This account gets every role and needs no email setup. Sign in with it afterward, then remove the recovery account from sysmanage.yaml.',
              )}
            </Alert>
            {error && <Alert severity="error">{error}</Alert>}
            <TextField
              label={t('security.firstAdmin.email', 'Email address')}
              type="email"
              value={userid}
              onChange={(e) => setUserid(e.target.value)}
              required
              autoFocus
            />
            <TextField
              label={t('security.firstAdmin.firstName', 'First name')}
              value={firstName}
              onChange={(e) => setFirstName(e.target.value)}
            />
            <TextField
              label={t('security.firstAdmin.lastName', 'Last name')}
              value={lastName}
              onChange={(e) => setLastName(e.target.value)}
            />
            <TextField
              label={t('security.firstAdmin.password', 'Password')}
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
            />
            <TextField
              label={t('security.firstAdmin.confirm', 'Confirm password')}
              type="password"
              value={confirm}
              onChange={(e) => setConfirm(e.target.value)}
              required
            />
          </Stack>
        )}
      </DialogContent>
      <DialogActions>
        {created ? (
          <Button variant="contained" onClick={signOut}>
            {t('security.firstAdmin.signOut', 'Sign out')}
          </Button>
        ) : (
          <>
            <Button onClick={onClose} disabled={busy}>
              {t('security.firstAdmin.cancel', 'Cancel')}
            </Button>
            <Button
              variant="contained"
              onClick={() => void submit()}
              disabled={busy || !userid || !password || !confirm}
            >
              {t('security.firstAdmin.create', 'Create administrator')}
            </Button>
          </>
        )}
      </DialogActions>
    </Dialog>
  );
};

export default FirstAdminDialog;
