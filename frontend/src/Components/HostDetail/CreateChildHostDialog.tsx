// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

import React from 'react';
import {
    Box,
    Typography,
    Button,
    CircularProgress,
    FormControl,
    InputLabel,
    Select,
    MenuItem,
    Checkbox,
    FormControlLabel,
    IconButton,
    Dialog,
    DialogTitle,
    DialogContent,
    DialogActions,
    TextField,
    FormHelperText,
} from '@mui/material';
import CloseIcon from '@mui/icons-material/Close';
import AddIcon from '@mui/icons-material/Add';
import { useTranslation } from 'react-i18next';
import { ChildHostFormData, AvailableDistribution } from './hostDetailTypes';

interface CreateChildHostDialogProps {
    createChildHostOpen: boolean;
    createChildHostLoading: boolean;
    childHostFormData: ChildHostFormData;
    setChildHostFormData: React.Dispatch<React.SetStateAction<ChildHostFormData>>;
    childHostFormValidated: boolean;
    setChildHostFormValidated: (value: boolean) => void;
    setCreateChildHostOpen: (value: boolean) => void;
    availableDistributions: AvailableDistribution[];
    computedFqdn: string;
    childHostCreationProgress: string;
    getCreateChildHostTitle: () => string;
    handleCreateChildHost: () => void;
}

const CreateChildHostDialog: React.FC<CreateChildHostDialogProps> = ({
    createChildHostOpen,
    createChildHostLoading,
    childHostFormData,
    setChildHostFormData,
    childHostFormValidated,
    setChildHostFormValidated,
    setCreateChildHostOpen,
    availableDistributions,
    computedFqdn,
    childHostCreationProgress,
    getCreateChildHostTitle,
    handleCreateChildHost,
}) => {
    const { t } = useTranslation();
    return (
            <Dialog
                open={createChildHostOpen}
                onClose={() => {
                    if (!createChildHostLoading) {
                        setChildHostFormValidated(false);
                        setCreateChildHostOpen(false);
                    }
                }}
                maxWidth="sm"
                fullWidth
            >
                <DialogTitle sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    {getCreateChildHostTitle()}
                    <IconButton
                        onClick={() => {
                            setChildHostFormValidated(false);
                            setCreateChildHostOpen(false);
                        }}
                        disabled={createChildHostLoading}
                    >
                        <CloseIcon />
                    </IconButton>
                </DialogTitle>
                <DialogContent>
                    <Box sx={{ mt: 2 }}>
                        <FormControl
                            fullWidth
                            sx={{ mb: 2 }}
                            error={childHostFormValidated && !childHostFormData.distribution}
                        >
                            <InputLabel id="distribution-select-label">
                                {childHostFormData.childType === 'lxd'
                                    ? t('hostDetail.childHostImageLabel', 'Image')
                                    : t('hostDetail.childHostDistributionLabel', 'Distribution')}
                            </InputLabel>
                            <Select
                                labelId="distribution-select-label"
                                value={childHostFormData.distribution}
                                label={childHostFormData.childType === 'lxd'
                                    ? t('hostDetail.childHostImageLabel', 'Image')
                                    : t('hostDetail.childHostDistributionLabel', 'Distribution')}
                                onChange={(e) => setChildHostFormData({
                                    ...childHostFormData,
                                    distribution: e.target.value
                                })}
                                disabled={createChildHostLoading}
                                error={childHostFormValidated && !childHostFormData.distribution}
                            >
                                {availableDistributions.map((dist) => (
                                    <MenuItem key={dist.id} value={dist.install_identifier}>
                                        {dist.display_name}
                                    </MenuItem>
                                ))}
                            </Select>
                            {childHostFormValidated && !childHostFormData.distribution && (
                                <FormHelperText>
                                    {childHostFormData.childType === 'lxd'
                                        ? t('hostDetail.childHostImageRequired', 'Please select an image')
                                        : t('hostDetail.childHostDistributionRequired', 'Please select a distribution')}
                                </FormHelperText>
                            )}
                        </FormControl>

                        <TextField
                            fullWidth
                            label={t('hostDetail.childHostHostnameLabel', 'Hostname')}
                            value={childHostFormData.hostname}
                            onChange={(e) => {
                                const newHostname = e.target.value;
                                // Auto-compute the short identifier (vmName for KVM/bhyve/VMM,
                                // containerName for LXD) from the hostname's left label.
                                const shortName = newHostname.split('.')[0].toLowerCase().replaceAll(/[^a-z0-9-]/g, '');
                                const isVm = childHostFormData.childType === 'vmm'
                                    || childHostFormData.childType === 'kvm'
                                    || childHostFormData.childType === 'bhyve';
                                const isLxd = childHostFormData.childType === 'lxd';
                                setChildHostFormData({
                                    ...childHostFormData,
                                    hostname: newHostname,
                                    vmName: isVm ? shortName : childHostFormData.vmName,
                                    containerName: isLxd ? shortName : childHostFormData.containerName,
                                });
                            }}
                            disabled={createChildHostLoading}
                            sx={{ mb: 1 }}
                            helperText={t('hostDetail.childHostHostnameHelp', 'Enter hostname (e.g., "myhost") or FQDN (e.g., "myhost.example.com")')}
                        />

                        <TextField
                            fullWidth
                            label={t('hostDetail.childHostFqdnLabel', 'Fully Qualified Domain Name')}
                            value={computedFqdn}
                            disabled
                            sx={{ mb: 2 }}
                            slotProps={{
                                input: {
                                    readOnly: true,
                                },
                            }}
                            helperText={(() => {
                                if (childHostFormData.childType === 'lxd') {
                                    return t('hostDetail.childHostFqdnHelpLxd', 'This FQDN will be used for the LXD container');
                                }
                                if (childHostFormData.childType === 'vmm') {
                                    return t('hostDetail.childHostFqdnHelpVmm', 'This FQDN will be used for the VMM virtual machine');
                                }
                                if (childHostFormData.childType === 'kvm') {
                                    return t('hostDetail.childHostFqdnHelpKvm', 'This FQDN will be used for the KVM virtual machine');
                                }
                                if (childHostFormData.childType === 'bhyve') {
                                    return t('hostDetail.childHostFqdnHelpBhyve', 'This FQDN will be used for the bhyve virtual machine');
                                }
                                return t('hostDetail.childHostFqdnHelp', 'This FQDN will be used for the WSL instance');
                            })()}
                        />

                        {/* VM name field for VMM, KVM, and bhyve - read-only, derived from hostname */}
                        {(childHostFormData.childType === 'vmm' || childHostFormData.childType === 'kvm' || childHostFormData.childType === 'bhyve') && (
                            <TextField
                                fullWidth
                                label={t('hostDetail.childHostVmNameLabel', 'VM Name')}
                                value={childHostFormData.vmName}
                                disabled
                                sx={{ mb: 2 }}
                                slotProps={{
                                    input: {
                                        readOnly: true,
                                    },
                                }}
                                helperText={t('hostDetail.childHostVmNameHelpReadonly', 'VM name is derived from the hostname')}
                            />
                        )}

                        {/* Container name field for LXD - read-only, derived from hostname */}
                        {childHostFormData.childType === 'lxd' && (
                            <TextField
                                fullWidth
                                label={t('hostDetail.childHostContainerNameLabel', 'Container Name')}
                                value={childHostFormData.containerName}
                                disabled
                                sx={{ mb: 2 }}
                                slotProps={{
                                    input: {
                                        readOnly: true,
                                    },
                                }}
                                helperText={t('hostDetail.childHostContainerNameHelpReadonly', 'Container name is derived from the hostname')}
                            />
                        )}

                        {/* Root password fields for VMM - before username (matches OpenBSD installer order) */}
                        {childHostFormData.childType === 'vmm' && (
                            <>
                                <TextField
                                    fullWidth
                                    required
                                    label={t('hostDetail.childHostRootPassword', 'Root Password')}
                                    type="password"
                                    value={childHostFormData.rootPassword}
                                    onChange={(e) => setChildHostFormData({
                                        ...childHostFormData,
                                        rootPassword: e.target.value
                                    })}
                                    disabled={createChildHostLoading}
                                    helperText={t('hostDetail.childHostRootPasswordHelp', 'Password for the root user on the OpenBSD VM')}
                                    sx={{ mb: 2 }}
                                />
                                <TextField
                                    fullWidth
                                    required
                                    label={t('hostDetail.childHostConfirmRootPassword', 'Confirm Root Password')}
                                    type="password"
                                    value={childHostFormData.confirmRootPassword}
                                    onChange={(e) => setChildHostFormData({
                                        ...childHostFormData,
                                        confirmRootPassword: e.target.value
                                    })}
                                    disabled={createChildHostLoading}
                                    error={childHostFormData.rootPassword !== childHostFormData.confirmRootPassword && childHostFormData.confirmRootPassword !== ''}
                                    helperText={
                                        childHostFormData.rootPassword !== childHostFormData.confirmRootPassword && childHostFormData.confirmRootPassword !== ''
                                            ? t('hostDetail.childHostRootPasswordMismatch', 'Root passwords do not match')
                                            : ''
                                    }
                                    sx={{ mb: 2 }}
                                />
                            </>
                        )}

                        <TextField
                            fullWidth
                            label={t('hostDetail.childHostUsernameLabel', 'Username')}
                            value={childHostFormData.username}
                            onChange={(e) => setChildHostFormData({
                                ...childHostFormData,
                                username: e.target.value
                            })}
                            disabled={createChildHostLoading}
                            sx={{ mb: 2 }}
                            helperText={t('hostDetail.childHostUsernameHelp', 'The non-root user to create')}
                        />

                        <TextField
                            fullWidth
                            type="password"
                            label={t('hostDetail.childHostPasswordLabel', 'Password')}
                            value={childHostFormData.password}
                            onChange={(e) => setChildHostFormData({
                                ...childHostFormData,
                                password: e.target.value
                            })}
                            disabled={createChildHostLoading}
                            sx={{ mb: 2 }}
                        />

                        <TextField
                            fullWidth
                            type="password"
                            label={t('hostDetail.childHostConfirmPasswordLabel', 'Confirm Password')}
                            value={childHostFormData.confirmPassword}
                            onChange={(e) => setChildHostFormData({
                                ...childHostFormData,
                                confirmPassword: e.target.value
                            })}
                            disabled={createChildHostLoading}
                            error={childHostFormData.password !== childHostFormData.confirmPassword && childHostFormData.confirmPassword !== ''}
                            helperText={
                                childHostFormData.password !== childHostFormData.confirmPassword && childHostFormData.confirmPassword !== ''
                                    ? t('hostDetail.childHostPasswordMismatch', 'Passwords do not match')
                                    : ''
                            }
                            sx={{ mb: 2 }}
                        />

                        {/* Auto-approve checkbox */}
                        <FormControlLabel
                            control={
                                <Checkbox
                                    checked={childHostFormData.autoApprove}
                                    onChange={(e) => setChildHostFormData({
                                        ...childHostFormData,
                                        autoApprove: e.target.checked
                                    })}
                                    disabled={createChildHostLoading}
                                />
                            }
                            label={t('hostDetail.childHostAutoApprove', 'Auto-approve when connected')}
                            sx={{ mb: 2 }}
                        />
                        <Typography variant="caption" color="textSecondary" sx={{ display: 'block', mt: -1, mb: 2, ml: 4 }}>
                            {t('hostDetail.childHostAutoApproveHelp', 'When enabled, the host will be automatically approved when it connects to the server.')}
                        </Typography>

                        {/* Progress indicator during creation */}
                        {createChildHostLoading && childHostCreationProgress && (
                            <Box sx={{ display: 'flex', alignItems: 'center', gap: 2, mt: 2 }}>
                                <CircularProgress size={20} />
                                <Typography variant="body2" color="textSecondary">
                                    {childHostCreationProgress}
                                </Typography>
                            </Box>
                        )}
                    </Box>
                </DialogContent>
                <DialogActions>
                    <Button
                        onClick={() => {
                            setChildHostFormValidated(false);
                            setCreateChildHostOpen(false);
                        }}
                        disabled={createChildHostLoading}
                    >
                        {t('common.cancel', 'Cancel')}
                    </Button>
                    <Button
                        variant="contained"
                        onClick={handleCreateChildHost}
                        disabled={createChildHostLoading}
                        startIcon={createChildHostLoading ? <CircularProgress size={16} /> : <AddIcon />}
                    >
                        {t('hostDetail.createChildHostButton', 'Create')}
                    </Button>
                </DialogActions>
            </Dialog>    );
};

export default CreateChildHostDialog;
