// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

import React, { useState } from 'react';
import { useTranslation } from 'react-i18next';
import Alert from '@mui/material/Alert';
import Box from '@mui/material/Box';
import FormControlLabel from '@mui/material/FormControlLabel';
import FormHelperText from '@mui/material/FormHelperText';
import Switch from '@mui/material/Switch';

import { doSetUserAdmin } from '../../Services/users';

/**
 * The "Administrator" switch in the user edit dialog.
 *
 * Administrator rights (``is_admin``) unlock the pages no security role
 * covers -- maintenance windows, the threat model, license management and a
 * few settings pages.  Only invitations could set it before, so a user created
 * any other way could never reach them.  It applies immediately (its own
 * audited call), separately from the dialog's Save.  Only an administrator may
 * flip it: everyone else sees it read-only.
 */
interface UserAdminToggleProps {
    userId: string;
    isAdmin: boolean;
    // Whether the person viewing the dialog is an administrator.
    canManage: boolean;
    onChanged: (isAdmin: boolean) => void;
}

const UserAdminToggle: React.FC<UserAdminToggleProps> = ({ userId, isAdmin, canManage, onChanged }) => {
    const { t } = useTranslation();
    const [saving, setSaving] = useState(false);
    const [error, setError] = useState<string | null>(null);

    const change = async (wanted: boolean) => {
        setSaving(true);
        setError(null);
        try {
            const result = await doSetUserAdmin(userId, wanted);
            onChanged(result.is_admin);
        } catch (err) {
            // The server's own reason (e.g. "the last active administrator")
            // is already in the user's language.
            const detail = (err as { response?: { data?: { detail?: unknown } } })
                ?.response?.data?.detail;
            setError(typeof detail === 'string' && detail
                ? detail
                : t('users.adminChangeFailed', 'Administrator rights could not be changed.'));
        } finally {
            setSaving(false);
        }
    };

    return (
        <Box sx={{ mt: 2 }}>
            <FormControlLabel
                control={
                    <Switch
                        checked={isAdmin}
                        disabled={!canManage || saving}
                        onChange={(e) => { void change(e.target.checked); }}
                        slotProps={{ input: { 'aria-describedby': 'user-admin-help' } }}
                    />
                }
                label={t('users.administrator', 'Administrator')}
            />
            <FormHelperText id="user-admin-help">
                {canManage
                    ? t('users.administratorHelp', 'Administrators can also reach pages no security role covers: maintenance windows, the threat model, license management and server settings. Applies immediately.')
                    : t('users.administratorReadOnly', 'Only an administrator can change this.')}
            </FormHelperText>
            {error && <Alert severity="error" sx={{ mt: 1 }}>{error}</Alert>}
        </Box>
    );
};

export default UserAdminToggle;
