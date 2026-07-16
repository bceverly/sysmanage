// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

import React, { useEffect, useState, useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import Button from '@mui/material/Button';
import Box from '@mui/material/Box';
import Stack from '@mui/material/Stack';
import Dialog from '@mui/material/Dialog';
import DialogTitle from '@mui/material/DialogTitle';
import DialogContent from '@mui/material/DialogContent';
import DialogActions from '@mui/material/DialogActions';
import TextField from '@mui/material/TextField';
import FormControlLabel from '@mui/material/FormControlLabel';
import Checkbox from '@mui/material/Checkbox';
import Chip from '@mui/material/Chip';
import Typography from '@mui/material/Typography';
import Alert from '@mui/material/Alert';
import IconButton from '@mui/material/IconButton';
import Table from '@mui/material/Table';
import TableBody from '@mui/material/TableBody';
import TableCell from '@mui/material/TableCell';
import TableHead from '@mui/material/TableHead';
import TableRow from '@mui/material/TableRow';
import Autocomplete from '@mui/material/Autocomplete';
import MailOutlineIcon from '@mui/icons-material/MailOutline';
import SendIcon from '@mui/icons-material/Send';
import DeleteIcon from '@mui/icons-material/Delete';
import {
    Invitation,
    doListInvitations,
    doCreateInvitation,
    doRevokeInvitation,
    doResendInvitation
} from '../Services/invitations';
import { SecurityRole, doGetAllRoleGroups } from '../Services/securityRoles';

const InvitationsManager: React.FC = () => {
    const { t } = useTranslation();

    const [open, setOpen] = useState(false);
    const [invitations, setInvitations] = useState<Invitation[]>([]);
    const [roles, setRoles] = useState<SecurityRole[]>([]);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [info, setInfo] = useState<string | null>(null);

    // New-invitation form
    const [email, setEmail] = useState('');
    const [firstName, setFirstName] = useState('');
    const [lastName, setLastName] = useState('');
    const [isAdmin, setIsAdmin] = useState(false);
    const [selectedRoles, setSelectedRoles] = useState<SecurityRole[]>([]);

    const loadInvitations = useCallback(async () => {
        setLoading(true);
        try {
            const rows = await doListInvitations(false);
            setInvitations(rows);
        } catch (err) {
            console.error('Error loading invitations:', err);
            setError(t('invitations.loadError', 'Failed to load invitations'));
        } finally {
            setLoading(false);
        }
    }, [t]);

    const loadRoles = useCallback(async () => {
        try {
            const groups = await doGetAllRoleGroups();
            setRoles(groups.flatMap((g) => g.roles));
        } catch (err) {
            console.error('Error loading security roles:', err);
        }
    }, []);

    useEffect(() => {
        if (open) {
            loadInvitations();
            loadRoles();
        }
    }, [open, loadInvitations, loadRoles]);

    const resetForm = () => {
        setEmail('');
        setFirstName('');
        setLastName('');
        setIsAdmin(false);
        setSelectedRoles([]);
    };

    const handleClose = () => {
        setOpen(false);
        setError(null);
        setInfo(null);
        resetForm();
    };

    interface AxiosErrorLike {
        response?: { data?: { detail?: string } };
    }

    const handleCreate = async (e: React.BaseSyntheticEvent) => {
        e.preventDefault();
        setError(null);
        setInfo(null);
        try {
            await doCreateInvitation({
                email,
                first_name: firstName || null,
                last_name: lastName || null,
                is_admin: isAdmin,
                role_ids: selectedRoles.map((r) => r.id)
            });
            setInfo(t('invitations.created', 'Invitation sent to {{email}}').replace('{{email}}', email));
            resetForm();
            await loadInvitations();
        } catch (err: unknown) {
            console.error('Error creating invitation:', err);
            const axiosErr = err as AxiosErrorLike;
            setError(
                axiosErr?.response?.data?.detail ||
                t('invitations.createError', 'Failed to create invitation')
            );
        }
    };

    const handleRevoke = async (id: string) => {
        setError(null);
        setInfo(null);
        try {
            await doRevokeInvitation(id);
            await loadInvitations();
        } catch (err) {
            console.error('Error revoking invitation:', err);
            setError(t('invitations.revokeError', 'Failed to revoke invitation'));
        }
    };

    const handleResend = async (id: string) => {
        setError(null);
        setInfo(null);
        try {
            const resp = await doResendInvitation(id);
            setInfo(resp.message || t('invitations.resent', 'Invitation re-sent'));
        } catch (err) {
            console.error('Error resending invitation:', err);
            setError(t('invitations.resendError', 'Failed to resend invitation'));
        }
    };

    const statusLabel = (status: Invitation['status']): string => {
        switch (status) {
            case 'pending':
                return t('invitations.statusPending', 'Pending');
            case 'accepted':
                return t('invitations.statusAccepted', 'Accepted');
            case 'revoked':
                return t('invitations.statusRevoked', 'Revoked');
            case 'expired':
                return t('invitations.statusExpired', 'Expired');
            default:
                return status;
        }
    };

    const statusColor = (
        status: Invitation['status']
    ): 'success' | 'default' | 'warning' | 'error' => {
        switch (status) {
            case 'pending':
                return 'success';
            case 'accepted':
                return 'default';
            case 'expired':
                return 'warning';
            case 'revoked':
                return 'error';
            default:
                return 'default';
        }
    };

    const formatDate = (value: string | null): string => {
        if (!value) return '';
        const d = new Date(value.endsWith('Z') ? value : `${value}Z`);
        return Number.isNaN(d.getTime()) ? '' : d.toLocaleString();
    };

    return (
        <>
            <Button
                variant="outlined"
                startIcon={<MailOutlineIcon />}
                onClick={() => setOpen(true)}
            >
                {t('invitations.manageButton', 'Invitations')}
            </Button>

            <Dialog open={open} onClose={handleClose} maxWidth="md" fullWidth>
                <DialogTitle>{t('invitations.title', 'User Invitations')}</DialogTitle>
                <DialogContent>
                    {error && (
                        <Alert severity="error" sx={{ mb: 2 }} onClose={() => setError(null)}>
                            {error}
                        </Alert>
                    )}
                    {info && (
                        <Alert severity="success" sx={{ mb: 2 }} onClose={() => setInfo(null)}>
                            {info}
                        </Alert>
                    )}

                    {/* New invitation form */}
                    <Box component="form" onSubmit={handleCreate} sx={{ mb: 3 }}>
                        <Typography variant="subtitle1" sx={{ mb: 1 }}>
                            {t('invitations.inviteHeading', 'Invite a new user')}
                        </Typography>
                        <Stack spacing={2}>
                            <TextField
                                required
                                fullWidth
                                size="small"
                                type="email"
                                label={t('invitations.email', 'Email')}
                                value={email}
                                onChange={(e) => setEmail(e.target.value)}
                            />
                            <Stack direction="row" spacing={2}>
                                <TextField
                                    fullWidth
                                    size="small"
                                    label={t('invitations.firstName', 'First Name')}
                                    value={firstName}
                                    onChange={(e) => setFirstName(e.target.value)}
                                />
                                <TextField
                                    fullWidth
                                    size="small"
                                    label={t('invitations.lastName', 'Last Name')}
                                    value={lastName}
                                    onChange={(e) => setLastName(e.target.value)}
                                />
                            </Stack>
                            <Autocomplete
                                multiple
                                size="small"
                                options={roles}
                                value={selectedRoles}
                                onChange={(_e, value) => setSelectedRoles(value)}
                                getOptionLabel={(option) => option.name}
                                isOptionEqualToValue={(option, value) => option.id === value.id}
                                renderInput={(params) => (
                                    <TextField
                                        {...params}
                                        label={t('invitations.roles', 'Security Roles')}
                                        placeholder={t('invitations.rolesPlaceholder', 'Select roles')}
                                    />
                                )}
                            />
                            <FormControlLabel
                                control={
                                    <Checkbox
                                        checked={isAdmin}
                                        onChange={(e) => setIsAdmin(e.target.checked)}
                                    />
                                }
                                label={t('invitations.isAdmin', 'Grant administrator access')}
                            />
                            <Box>
                                <Button
                                    type="submit"
                                    variant="contained"
                                    startIcon={<SendIcon />}
                                    disabled={!email}
                                >
                                    {t('invitations.sendInvite', 'Send Invitation')}
                                </Button>
                            </Box>
                        </Stack>
                    </Box>

                    {/* Existing invitations */}
                    <Typography variant="subtitle1" sx={{ mb: 1 }}>
                        {t('invitations.existingHeading', 'Invitations')}
                    </Typography>
                    {invitations.length === 0 ? (
                        <Typography variant="body2" color="text.secondary">
                            {loading
                                ? t('common.loading', 'Loading...')
                                : t('invitations.none', 'No invitations yet')}
                        </Typography>
                    ) : (
                        <Table size="small">
                            <TableHead>
                                <TableRow>
                                    <TableCell>{t('invitations.email', 'Email')}</TableCell>
                                    <TableCell>{t('invitations.status', 'Status')}</TableCell>
                                    <TableCell>{t('invitations.expires', 'Expires')}</TableCell>
                                    <TableCell align="right">{t('common.actions', 'Actions')}</TableCell>
                                </TableRow>
                            </TableHead>
                            <TableBody>
                                {invitations.map((inv) => (
                                    <TableRow key={inv.id}>
                                        <TableCell>{inv.email}</TableCell>
                                        <TableCell>
                                            <Chip
                                                size="small"
                                                label={statusLabel(inv.status)}
                                                color={statusColor(inv.status)}
                                            />
                                        </TableCell>
                                        <TableCell>{formatDate(inv.expires_at)}</TableCell>
                                        <TableCell align="right">
                                            {inv.status === 'pending' && (
                                                <>
                                                    <IconButton
                                                        size="small"
                                                        title={t('invitations.resend', 'Resend')}
                                                        onClick={() => handleResend(inv.id)}
                                                    >
                                                        <SendIcon fontSize="small" />
                                                    </IconButton>
                                                    <IconButton
                                                        size="small"
                                                        color="error"
                                                        title={t('invitations.revoke', 'Revoke')}
                                                        onClick={() => handleRevoke(inv.id)}
                                                    >
                                                        <DeleteIcon fontSize="small" />
                                                    </IconButton>
                                                </>
                                            )}
                                        </TableCell>
                                    </TableRow>
                                ))}
                            </TableBody>
                        </Table>
                    )}
                </DialogContent>
                <DialogActions>
                    <Button onClick={handleClose}>{t('common.close', 'Close')}</Button>
                </DialogActions>
            </Dialog>
        </>
    );
};

export default InvitationsManager;
