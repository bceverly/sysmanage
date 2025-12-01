import React, { useState, useEffect } from 'react';
import {
    Dialog,
    DialogTitle,
    DialogContent,
    DialogActions,
    Button,
    TextField,
    Typography,
    Box,
    CircularProgress,
    Alert,
} from '@mui/material';
import { useTranslation } from 'react-i18next';
import axiosInstance from '../Services/api';

interface AddHostGroupModalProps {
    open: boolean;
    onClose: () => void;
    hostId: string;
    hostPlatform: string;
    onSuccess?: () => void;
}

const AddHostGroupModal: React.FC<AddHostGroupModalProps> = ({
    open,
    onClose,
    hostId,
    hostPlatform,
    onSuccess,
}) => {
    const { t } = useTranslation();
    const [submitting, setSubmitting] = useState(false);
    const [error, setError] = useState<string | null>(null);

    // Group fields
    const [groupName, setGroupName] = useState('');
    const [gid, setGid] = useState('');
    const [description, setDescription] = useState('');

    const isWindows = hostPlatform?.toLowerCase().includes('windows');

    // Reset form when modal opens
    useEffect(() => {
        if (open) {
            setGroupName('');
            setGid('');
            setDescription('');
            setError(null);
        }
    }, [open]);

    const handleClose = () => {
        if (!submitting) {
            onClose();
        }
    };

    const validateForm = (): boolean => {
        if (!groupName.trim()) {
            setError(t('hostGroup.groupNameRequired', 'Group name is required'));
            return false;
        }

        // Group name validation - allow alphanumeric and underscore/dash
        if (!/^[a-zA-Z][a-zA-Z0-9_-]*$/.test(groupName)) {
            setError(t('hostGroup.invalidGroupName', 'Group name must start with a letter and contain only letters, numbers, underscores, and dashes'));
            return false;
        }

        // GID validation if provided (Unix only)
        if (!isWindows && gid && (isNaN(Number(gid)) || Number(gid) < 1000)) {
            setError(t('hostGroup.invalidGid', 'GID must be a number >= 1000'));
            return false;
        }

        return true;
    };

    const handleSubmit = async () => {
        if (!validateForm()) {
            return;
        }

        setSubmitting(true);
        setError(null);

        try {
            // Build the request payload
            interface CreateGroupPayload {
                group_name: string;
                gid?: number;
                description?: string;
            }

            const payload: CreateGroupPayload = {
                group_name: groupName.trim(),
            };

            if (!isWindows && gid) {
                payload.gid = Number(gid);
            }

            if (isWindows && description.trim()) {
                payload.description = description.trim();
            }

            await axiosInstance.post(`/api/host/${hostId}/groups`, payload);

            // Call success callback and close modal
            if (onSuccess) {
                onSuccess();
            }
            handleClose();
        } catch (err: unknown) {
            // Extract error message from axios error response
            let errorMessage = t('hostGroup.createFailed', 'Failed to create group');
            if (err && typeof err === 'object' && 'response' in err) {
                const axiosError = err as { response?: { data?: { detail?: string } } };
                if (axiosError.response?.data?.detail) {
                    errorMessage = axiosError.response.data.detail;
                }
            } else if (err instanceof Error) {
                errorMessage = err.message;
            }
            setError(errorMessage);
        } finally {
            setSubmitting(false);
        }
    };

    return (
        <Dialog open={open} onClose={handleClose} maxWidth="sm" fullWidth>
            <DialogTitle>
                {t('hostGroup.addGroup', 'Add Group')}
            </DialogTitle>
            <DialogContent>
                {error && (
                    <Alert severity="error" sx={{ mb: 2 }}>
                        {error}
                    </Alert>
                )}

                <Typography variant="body2" color="textSecondary" sx={{ mb: 2 }}>
                    {isWindows
                        ? t('hostGroup.windowsDescription', 'Create a new local group on this Windows host.')
                        : t('hostGroup.unixDescription', 'Create a new group on this host.')}
                </Typography>

                <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2, mt: 2 }}>
                    <TextField
                        label={t('hostGroup.groupName', 'Group Name')}
                        value={groupName}
                        onChange={(e) => setGroupName(e.target.value.toLowerCase())}
                        required
                        fullWidth
                        disabled={submitting}
                        helperText={t('hostGroup.groupNameHelp', 'Letters, numbers, underscores, and dashes allowed')}
                    />

                    {isWindows && (
                        <TextField
                            label={t('hostGroup.description', 'Description')}
                            value={description}
                            onChange={(e) => setDescription(e.target.value)}
                            fullWidth
                            disabled={submitting}
                            helperText={t('hostGroup.descriptionHelp', 'Optional description for the group')}
                        />
                    )}

                    {!isWindows && (
                        <TextField
                            label={t('hostGroup.gid', 'Group ID (GID)')}
                            value={gid}
                            onChange={(e) => setGid(e.target.value)}
                            fullWidth
                            disabled={submitting}
                            error={gid !== '' && (isNaN(Number(gid)) || Number(gid) < 1000)}
                            helperText={gid !== '' && (isNaN(Number(gid)) || Number(gid) < 1000)
                                ? t('hostGroup.invalidGid', 'GID must be a number >= 1000')
                                : t('hostGroup.gidHelp', 'Leave empty to auto-assign. Must be >= 1000 if specified.')}
                        />
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
                    disabled={submitting || !groupName.trim() || (!isWindows && gid !== '' && (isNaN(Number(gid)) || Number(gid) < 1000))}
                >
                    {submitting ? (
                        <CircularProgress size={20} color="inherit" />
                    ) : (
                        t('hostGroup.create', 'Create Group')
                    )}
                </Button>
            </DialogActions>
        </Dialog>
    );
};

export default AddHostGroupModal;
