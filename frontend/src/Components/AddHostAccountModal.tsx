// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

import React, { useState, useEffect } from 'react';
import {
    Dialog,
    DialogTitle,
    DialogContent,
    DialogActions,
    Button,
    TextField,
    FormControl,
    FormControlLabel,
    Checkbox,
    Typography,
    Box,
    CircularProgress,
    Alert,
    InputLabel,
    Select,
    MenuItem,
} from '@mui/material';
import { useTranslation } from 'react-i18next';
import axiosInstance from '../Services/api';
import {
    AccountFormValues,
    validateAccountForm,
    buildCreateUserPayload,
    extractAccountErrorMessage,
} from './addHostAccountHelpers';

interface AddHostAccountModalProps {
    open: boolean;
    onClose: () => void;
    hostId: string;
    hostPlatform: string;
    onSuccess?: () => void;
}

const AddHostAccountModal: React.FC<AddHostAccountModalProps> = ({
    open,
    onClose,
    hostId,
    hostPlatform,
    onSuccess,
}) => {
    const { t } = useTranslation();
    const [submitting, setSubmitting] = useState(false);
    const [error, setError] = useState<string | null>(null);

    // Common fields
    const [username, setUsername] = useState('');
    const [fullName, setFullName] = useState('');

    // Unix-specific fields
    const [homeDirectory, setHomeDirectory] = useState('');
    const [shell, setShell] = useState('/bin/bash');
    const [createHomeDir, setCreateHomeDir] = useState(true);
    const [uid, setUid] = useState('');
    const [primaryGroup, setPrimaryGroup] = useState('');

    // Windows-specific fields
    const [password, setPassword] = useState('');
    const [confirmPassword, setConfirmPassword] = useState('');
    const [passwordNeverExpires, setPasswordNeverExpires] = useState(false);
    const [userMustChangePassword, setUserMustChangePassword] = useState(true);
    const [accountDisabled, setAccountDisabled] = useState(false);

    // Track if user has manually edited the home directory
    const [homeDirectoryManuallyEdited, setHomeDirectoryManuallyEdited] = useState(false);

    const isWindows = hostPlatform?.toLowerCase().includes('windows');
    const isMacOS = hostPlatform?.toLowerCase() === 'macos' || hostPlatform?.toLowerCase() === 'darwin';
    const isBSD = ['freebsd', 'openbsd', 'netbsd'].includes(hostPlatform?.toLowerCase() || '');
    const isOpenBSD = hostPlatform?.toLowerCase() === 'openbsd';

    // Platform-specific UID minimum: macOS uses 501+, Linux/BSD use 1000+
    const minUid = isMacOS ? 501 : 1000;

    // Get default shell based on platform
    const getDefaultShell = () => {
        if (isWindows) return '';
        if (isMacOS) return '/bin/zsh';
        if (isOpenBSD) return '/bin/ksh';
        if (isBSD) return '/usr/local/bin/bash';
        return '/bin/bash'; // Linux default
    };

    // Reset form when modal opens
    useEffect(() => {
        if (open) {
            setUsername('');
            setFullName('');
            setHomeDirectory('');
            setHomeDirectoryManuallyEdited(false);
            setShell(getDefaultShell());
            setCreateHomeDir(true);
            setUid('');
            setPrimaryGroup('');
            setPassword('');
            setConfirmPassword('');
            setPasswordNeverExpires(false);
            setUserMustChangePassword(true);
            setAccountDisabled(false);
            setError(null);
        }
    // Intentionally omitting ``form`` setters from deps — the effect
    // resets form state when the modal opens or platform changes; it
    // doesn't depend on the form itself.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [open, hostPlatform]);

    // Auto-generate home directory based on username for Unix systems
    useEffect(() => {
        if (!isWindows && username && !homeDirectoryManuallyEdited) {
            if (isMacOS) {
                setHomeDirectory(`/Users/${username}`);
            } else {
                setHomeDirectory(`/home/${username}`);
            }
        }
    }, [username, isWindows, isMacOS, homeDirectoryManuallyEdited]);

    const handleClose = () => {
        if (!submitting) {
            onClose();
        }
    };

    const getFormValues = (): AccountFormValues => ({
        username,
        fullName,
        homeDirectory,
        shell,
        createHomeDir,
        uid,
        primaryGroup,
        password,
        confirmPassword,
        passwordNeverExpires,
        userMustChangePassword,
        accountDisabled,
    });

    const handleSubmit = async () => {
        const values = getFormValues();
        const validationError = validateAccountForm(t, values, isWindows, minUid);
        if (validationError) {
            setError(validationError);
            return;
        }

        setSubmitting(true);
        setError(null);

        try {
            const payload = buildCreateUserPayload(values, isWindows);
            await axiosInstance.post(`/api/v1/host/${hostId}/accounts`, payload);

            // Call success callback and close modal
            if (onSuccess) {
                onSuccess();
            }
            handleClose();
        } catch (err: unknown) {
            setError(extractAccountErrorMessage(t, err));
        } finally {
            setSubmitting(false);
        }
    };

    return (
        <Dialog open={open} onClose={handleClose} maxWidth="sm" fullWidth>
            <DialogTitle>
                {t('hostAccount.addUser', 'Add User Account')}
            </DialogTitle>
            <DialogContent>
                {error && (
                    <Alert severity="error" sx={{ mb: 2 }}>
                        {error}
                    </Alert>
                )}

                <Typography variant="body2" color="textSecondary" sx={{ mb: 2 }}>
                    {isWindows
                        ? t('hostAccount.windowsDescription', 'Create a new local user account on this Windows host.')
                        : t('hostAccount.unixDescription', 'Create a new user account on this host.')}
                </Typography>

                <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2, mt: 2 }}>
                    {/* Common Fields */}
                    <TextField
                        label={t('hostAccount.username', 'Username')}
                        value={username}
                        onChange={(e) => setUsername(e.target.value.toLowerCase())}
                        required
                        fullWidth
                        disabled={submitting}
                        helperText={t('hostAccount.usernameHelp', 'Letters, numbers, underscores, and dashes allowed')}
                    />

                    <TextField
                        label={t('hostAccount.fullName', 'Full Name')}
                        value={fullName}
                        onChange={(e) => setFullName(e.target.value)}
                        fullWidth
                        disabled={submitting}
                        helperText={t('hostAccount.fullNameHelp', 'Optional display name for the user')}
                    />

                    {/* Unix-specific Fields */}
                    {!isWindows && (
                        <>
                            <TextField
                                label={t('hostAccount.homeDirectory', 'Home Directory')}
                                value={homeDirectory}
                                onChange={(e) => {
                                    setHomeDirectory(e.target.value);
                                    setHomeDirectoryManuallyEdited(true);
                                }}
                                fullWidth
                                disabled={submitting}
                            />

                            <FormControl fullWidth disabled={submitting}>
                                <InputLabel>{t('hostAccount.shell', 'Shell')}</InputLabel>
                                <Select
                                    value={shell}
                                    onChange={(e) => setShell(e.target.value)}
                                    label={t('hostAccount.shell', 'Shell')}
                                >
                                    {/* eslint-disable i18next/no-literal-string -- shell file paths are not translatable */}
                                    {/* Common shells */}
                                    <MenuItem value="/bin/sh">{t('hostAccount.shellBourne', 'Bourne Shell')} (/bin/sh)</MenuItem>

                                    {/* Bash - different paths on different platforms */}
                                    {!isBSD && <MenuItem value="/bin/bash">{t('hostAccount.shellBash', 'Bash')} (/bin/bash)</MenuItem>}
                                    {isBSD && <MenuItem value="/usr/local/bin/bash">{t('hostAccount.shellBash', 'Bash')} (/usr/local/bin/bash)</MenuItem>}

                                    {/* Zsh - different paths */}
                                    {!isBSD && <MenuItem value="/bin/zsh">{t('hostAccount.shellZsh', 'Zsh')} (/bin/zsh)</MenuItem>}
                                    {isBSD && <MenuItem value="/usr/local/bin/zsh">{t('hostAccount.shellZsh', 'Zsh')} (/usr/local/bin/zsh)</MenuItem>}

                                    {/* Ksh - common on OpenBSD */}
                                    {isOpenBSD && <MenuItem value="/bin/ksh">{t('hostAccount.shellKsh', 'Ksh')} (/bin/ksh)</MenuItem>}
                                    {!isOpenBSD && <MenuItem value="/bin/ksh">{t('hostAccount.shellKsh', 'Ksh')} (/bin/ksh)</MenuItem>}

                                    {/* Fish - different paths */}
                                    {!isBSD && <MenuItem value="/usr/bin/fish">{t('hostAccount.shellFish', 'Fish')} (/usr/bin/fish)</MenuItem>}
                                    {isBSD && <MenuItem value="/usr/local/bin/fish">{t('hostAccount.shellFish', 'Fish')} (/usr/local/bin/fish)</MenuItem>}

                                    {/* Tcsh/Csh */}
                                    <MenuItem value="/bin/tcsh">{t('hostAccount.shellTcsh', 'Tcsh')} (/bin/tcsh)</MenuItem>
                                    <MenuItem value="/bin/csh">{t('hostAccount.shellCsh', 'Csh')} (/bin/csh)</MenuItem>

                                    {/* No login shells */}
                                    {!isBSD && <MenuItem value="/usr/sbin/nologin">{t('hostAccount.shellNoLogin', 'No Login')} (/usr/sbin/nologin)</MenuItem>}
                                    {!isBSD && <MenuItem value="/sbin/nologin">{t('hostAccount.shellNoLogin', 'No Login')} (/sbin/nologin)</MenuItem>}
                                    {isBSD && <MenuItem value="/sbin/nologin">{t('hostAccount.shellNoLogin', 'No Login')} (/sbin/nologin)</MenuItem>}

                                    <MenuItem value="/bin/false">{t('hostAccount.shellFalse', 'False')} (/bin/false)</MenuItem>
                                    {/* eslint-enable i18next/no-literal-string */}
                                </Select>
                            </FormControl>

                            <TextField
                                label={t('hostAccount.uid', 'User ID (UID)')}
                                value={uid}
                                onChange={(e) => setUid(e.target.value)}
                                fullWidth
                                disabled={submitting}
                                error={uid !== '' && (Number.isNaN(Number(uid)) || Number(uid) < minUid)}
                                helperText={uid !== '' && (Number.isNaN(Number(uid)) || Number(uid) < minUid)
                                    ? t('hostAccount.invalidUidPlatform', `UID must be a number >= ${minUid}`, { minUid })
                                    : t('hostAccount.uidHelpPlatform', `Leave empty to auto-assign. Must be >= ${minUid} if specified.`, { minUid })}
                            />

                            <TextField
                                label={t('hostAccount.primaryGroup', 'Primary Group')}
                                value={primaryGroup}
                                onChange={(e) => setPrimaryGroup(e.target.value)}
                                fullWidth
                                disabled={submitting}
                                helperText={t('hostAccount.primaryGroupHelp', 'Leave empty to create a group with the same name as the user')}
                            />

                            <FormControlLabel
                                control={
                                    <Checkbox
                                        checked={createHomeDir}
                                        onChange={(e) => setCreateHomeDir(e.target.checked)}
                                        disabled={submitting}
                                    />
                                }
                                label={t('hostAccount.createHomeDir', 'Create home directory')}
                            />
                        </>
                    )}

                    {/* Windows-specific Fields */}
                    {isWindows && (
                        <>
                            <TextField
                                label={t('hostAccount.password', 'Password')}
                                type="password"
                                value={password}
                                onChange={(e) => setPassword(e.target.value)}
                                required
                                fullWidth
                                disabled={submitting}
                                error={password !== '' && password.length < 8}
                                helperText={password !== '' && password.length < 8
                                    ? t('hostAccount.passwordTooShort', 'Password must be at least 8 characters')
                                    : t('hostAccount.passwordHelp', 'Minimum 8 characters required')}
                            />

                            <TextField
                                label={t('hostAccount.confirmPassword', 'Confirm Password')}
                                type="password"
                                value={confirmPassword}
                                onChange={(e) => setConfirmPassword(e.target.value)}
                                required
                                fullWidth
                                disabled={submitting}
                                error={confirmPassword !== '' && password !== confirmPassword}
                                helperText={confirmPassword !== '' && password !== confirmPassword ? t('hostAccount.passwordMismatch', 'Passwords do not match') : ''}
                            />

                            <FormControlLabel
                                control={
                                    <Checkbox
                                        checked={userMustChangePassword}
                                        onChange={(e) => setUserMustChangePassword(e.target.checked)}
                                        disabled={submitting}
                                    />
                                }
                                label={t('hostAccount.userMustChangePassword', 'User must change password at next logon')}
                            />

                            <FormControlLabel
                                control={
                                    <Checkbox
                                        checked={passwordNeverExpires}
                                        onChange={(e) => setPasswordNeverExpires(e.target.checked)}
                                        disabled={submitting}
                                    />
                                }
                                label={t('hostAccount.passwordNeverExpires', 'Password never expires')}
                            />

                            <FormControlLabel
                                control={
                                    <Checkbox
                                        checked={accountDisabled}
                                        onChange={(e) => setAccountDisabled(e.target.checked)}
                                        disabled={submitting}
                                    />
                                }
                                label={t('hostAccount.accountDisabled', 'Account is disabled')}
                            />
                        </>
                    )}
                </Box>
            </DialogContent>
            <DialogActions>
                <Button onClick={handleClose} disabled={submitting}>
                    {t('common.cancel', 'Cancel')}
                </Button>
                <Button
                    onClick={handleSubmit}
                    variant="contained"
                    color="primary"
                    disabled={
                        submitting ||
                        !username.trim() ||
                        (!isWindows && uid !== '' && (Number.isNaN(Number(uid)) || Number(uid) < minUid)) ||
                        (isWindows && (!password || password.length < 8 || password !== confirmPassword))
                    }
                >
                    {submitting ? (
                        <CircularProgress size={20} color="inherit" />
                    ) : (
                        t('hostAccount.create', 'Create User')
                    )}
                </Button>
            </DialogActions>
        </Dialog>
    );
};

export default AddHostAccountModal;
