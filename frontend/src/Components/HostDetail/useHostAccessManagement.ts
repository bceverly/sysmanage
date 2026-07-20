// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

// User/group deletion, SSH-key and certificate deployment dialog state and
// handlers, plus the generic "additional details" dialog, for Host Detail.

import React, { useState } from 'react';
import type { TFunction } from 'i18next';
import axios from 'axios';
import axiosInstance from '../../Services/api';
import { SysManageHost, UserAccount, UserGroup } from '../../Services/hosts';
import { SecretResponse } from '../../Services/secrets';
import type { SnackbarSeverity } from './useHostSnackbar';

interface UseHostAccessManagementArgs {
    hostId: string | undefined;
    host: SysManageHost | null;
    t: TFunction;
    setSnackbarMessage: React.Dispatch<React.SetStateAction<string>>;
    setSnackbarSeverity: React.Dispatch<React.SetStateAction<SnackbarSeverity>>;
    setSnackbarOpen: React.Dispatch<React.SetStateAction<boolean>>;
}

export const useHostAccessManagement = ({
    hostId,
    host,
    t,
    setSnackbarMessage,
    setSnackbarSeverity,
    setSnackbarOpen,
}: UseHostAccessManagementArgs) => {
    const [dialogOpen, setDialogOpen] = useState<boolean>(false);
    const [dialogContent, setDialogContent] = useState<string>('');
    const [dialogTitle, setDialogTitle] = useState<string>('');
    const [sshKeyDialogOpen, setSshKeyDialogOpen] = useState<boolean>(false);
    const [selectedUser, setSelectedUser] = useState<UserAccount | null>(null);
    const [availableSSHKeys, setAvailableSSHKeys] = useState<SecretResponse[]>([]);
    const [filteredSSHKeys, setFilteredSSHKeys] = useState<SecretResponse[]>([]);
    const [selectedSSHKeys, setSelectedSSHKeys] = useState<string[]>([]);

    // Certificate management state
    const [addCertificateDialogOpen, setAddCertificateDialogOpen] = useState<boolean>(false);
    const [availableCertificates, setAvailableCertificates] = useState<SecretResponse[]>([]);
    const [filteredCertificates, setFilteredCertificates] = useState<SecretResponse[]>([]);
    const [selectedCertificates, setSelectedCertificates] = useState<string[]>([]);
    const [certificateDialogSearchTerm, setCertificateDialogSearchTerm] = useState<string>('');
    const [isCertificateSearching, setIsCertificateSearching] = useState<boolean>(false);
    const [sshKeySearchTerm, setSshKeySearchTerm] = useState<string>('');
    const [addUserModalOpen, setAddUserModalOpen] = useState<boolean>(false);
    const [addGroupModalOpen, setAddGroupModalOpen] = useState<boolean>(false);
    const [deleteUserConfirmOpen, setDeleteUserConfirmOpen] = useState<boolean>(false);
    const [deleteGroupConfirmOpen, setDeleteGroupConfirmOpen] = useState<boolean>(false);
    const [userToDelete, setUserToDelete] = useState<UserAccount | null>(null);
    const [groupToDelete, setGroupToDelete] = useState<UserGroup | null>(null);
    const [deletingUser, setDeletingUser] = useState<boolean>(false);
    const [deletingGroup, setDeletingGroup] = useState<boolean>(false);
    const [deleteDefaultGroup, setDeleteDefaultGroup] = useState<boolean>(true);
    const handleShowDialog = (title: string, content: string) => {
        setDialogTitle(title);
        setDialogContent(content);
        setDialogOpen(true);
    };

    const handleCloseDialog = () => {
        setDialogOpen(false);
        setDialogContent('');
        setDialogTitle('');
    };

    const handleAddSSHKey = async (user: UserAccount) => {
        setSelectedUser(user);
        try {
            // Load available SSH keys
            const response = await axiosInstance.get('/api/v1/stored-secrets?type=ssh_key');
            const secrets = response.data;
            const sshKeys = secrets.filter((secret: SecretResponse) => secret.secret_type === 'ssh_key');
            setAvailableSSHKeys(sshKeys);
            setFilteredSSHKeys(sshKeys);
            setSelectedSSHKeys([]);
            setSshKeySearchTerm('');
            setSshKeyDialogOpen(true);
        } catch (error) {
            console.error('Failed to load SSH keys:', error);
            setSnackbarMessage(t('hostDetail.failedToLoadSSHKeys', 'Failed to load SSH keys'));
            setSnackbarSeverity('error');
            setSnackbarOpen(true);
        }
    };

    const handleSSHKeyDialogClose = () => {
        setSshKeyDialogOpen(false);
        setSelectedUser(null);
        setAvailableSSHKeys([]);
        setFilteredSSHKeys([]);
        setSelectedSSHKeys([]);
        setSshKeySearchTerm('');
    };

    // Delete user account handlers
    const handleDeleteUserClick = (user: UserAccount) => {
        setUserToDelete(user);
        setDeleteDefaultGroup(true);  // Reset to default checked
        setDeleteUserConfirmOpen(true);
    };

    const handleDeleteUserConfirm = async () => {
        if (!userToDelete || !hostId) return;

        setDeletingUser(true);
        try {
            await axiosInstance.delete(`/api/v1/host/${hostId}/accounts/${encodeURIComponent(userToDelete.username)}?delete_default_group=${deleteDefaultGroup}`);
            setSnackbarMessage(t('hostAccount.deleteSuccess', 'User account deletion requested. The user list will update automatically.'));
            setSnackbarSeverity('success');
            setSnackbarOpen(true);
            setDeleteUserConfirmOpen(false);
            setUserToDelete(null);
        } catch (error: unknown) {
            console.error('Failed to delete user:', error);
            let errorMessage = t('hostAccount.deleteFailed', 'Failed to delete user account');
            if (axios.isAxiosError(error) && error.response?.data?.detail) {
                errorMessage = error.response.data.detail;
            }
            setSnackbarMessage(errorMessage);
            setSnackbarSeverity('error');
            setSnackbarOpen(true);
        } finally {
            setDeletingUser(false);
        }
    };

    const handleDeleteUserCancel = () => {
        setDeleteUserConfirmOpen(false);
        setUserToDelete(null);
    };

    // Delete group handlers
    const handleDeleteGroupClick = (group: UserGroup) => {
        setGroupToDelete(group);
        setDeleteGroupConfirmOpen(true);
    };

    const handleDeleteGroupConfirm = async () => {
        if (!groupToDelete || !hostId) return;

        setDeletingGroup(true);
        try {
            await axiosInstance.delete(`/api/v1/host/${hostId}/groups/${encodeURIComponent(groupToDelete.group_name)}`);
            setSnackbarMessage(t('hostGroup.deleteSuccess', 'Group deletion requested. The group list will update automatically.'));
            setSnackbarSeverity('success');
            setSnackbarOpen(true);
            setDeleteGroupConfirmOpen(false);
            setGroupToDelete(null);
        } catch (error: unknown) {
            console.error('Failed to delete group:', error);
            let errorMessage = t('hostGroup.deleteFailed', 'Failed to delete group');
            if (axios.isAxiosError(error) && error.response?.data?.detail) {
                errorMessage = error.response.data.detail;
            }
            setSnackbarMessage(errorMessage);
            setSnackbarSeverity('error');
            setSnackbarOpen(true);
        } finally {
            setDeletingGroup(false);
        }
    };

    const handleDeleteGroupCancel = () => {
        setDeleteGroupConfirmOpen(false);
        setGroupToDelete(null);
    };

    const handleSSHKeySearch = () => {
        const searchTerm = sshKeySearchTerm.toLowerCase().trim();
        if (searchTerm === '') {
            setFilteredSSHKeys(availableSSHKeys);
        } else {
            const filtered = availableSSHKeys.filter((key) =>
                key.name.toLowerCase().includes(searchTerm) ||
                (key.filename?.toLowerCase().includes(searchTerm))
            );
            setFilteredSSHKeys(filtered);
        }
    };

    // Certificate management functions
    const handleCertificateDialogClose = () => {
        setAddCertificateDialogOpen(false);
        setAvailableCertificates([]);
        setFilteredCertificates([]);
        setSelectedCertificates([]);
        setCertificateDialogSearchTerm('');
    };

    const handleCertificateSearch = () => {
        const searchTerm = certificateDialogSearchTerm.toLowerCase().trim();
        if (searchTerm === '') {
            setFilteredCertificates(availableCertificates);
        } else {
            const filtered = availableCertificates.filter((cert) =>
                cert.name.toLowerCase().includes(searchTerm) ||
                cert.filename?.toLowerCase().includes(searchTerm)
            );
            setFilteredCertificates(filtered);
        }
    };

    const handleDeployCertificates = async () => {
        if (selectedCertificates.length === 0 || !host) return;

        try {
            const deployData = {
                host_id: host.id,
                secret_ids: selectedCertificates
            };

            await axiosInstance.post('/api/v1/stored-secrets/deploy-certificates', deployData);

            setSnackbarMessage(t('hostDetail.certificatesDeployedSuccess', 'Certificates deployment queued successfully'));
            setSnackbarSeverity('success');
            setSnackbarOpen(true);

            handleCertificateDialogClose();
        } catch (error: unknown) {
            console.error('Failed to deploy certificates:', error);
            let errorMessage = t('hostDetail.certificatesDeployedError', 'Failed to deploy certificates');
            if (axios.isAxiosError(error) && error.response?.data?.detail) {
                errorMessage = error.response.data.detail;
            }

            setSnackbarMessage(errorMessage);
            setSnackbarSeverity('error');
            setSnackbarOpen(true);
        }
    };

    const loadAvailableCertificates = async () => {
        try {
            setIsCertificateSearching(true);
            // Load available SSL certificates - same pattern as SSH keys
            const response = await axiosInstance.get('/api/v1/stored-secrets?type=ssl_certificate');
            const secrets = response.data;
            const certificates = secrets.filter((secret: SecretResponse) => secret.secret_type === 'ssl_certificate');
            setAvailableCertificates(certificates);
            setFilteredCertificates(certificates);
        } catch (error: unknown) {
            console.error('Failed to load certificates:', error);
            setSnackbarMessage(t('hostDetail.certificatesLoadError', 'Failed to load certificates from vault'));
            setSnackbarSeverity('error');
            setSnackbarOpen(true);
        } finally {
            setIsCertificateSearching(false);
        }
    };

    const handleDeploySSHKeys = async () => {
        if (!selectedUser || selectedSSHKeys.length === 0 || !host) return;

        try {
            const deployData = {
                host_id: host.id,
                username: selectedUser.username,
                secret_ids: selectedSSHKeys
            };

            const response = await axiosInstance.post('/api/v1/stored-secrets/deploy-ssh-keys', deployData);
            const result = response.data;
            console.log('SSH key deployment queued:', result);

            setSnackbarMessage(t('hostDetail.sshKeysDeployedSuccess', 'SSH keys deployment queued successfully'));
            setSnackbarSeverity('success');
            setSnackbarOpen(true);

            handleSSHKeyDialogClose();
        } catch (error: unknown) {
            console.error('Failed to deploy SSH keys:', error);
            let errorMessage = t('hostDetail.sshKeysDeployedError', 'Failed to deploy SSH keys');

            if (axios.isAxiosError(error) && error.response?.data?.detail) {
                errorMessage = error.response.data.detail;
            }

            setSnackbarMessage(errorMessage);
            setSnackbarSeverity('error');
            setSnackbarOpen(true);
        }
    };
    return {
        dialogOpen,
        dialogContent,
        dialogTitle,
        sshKeyDialogOpen,
        selectedUser,
        availableSSHKeys,
        filteredSSHKeys,
        selectedSSHKeys,
        setSelectedSSHKeys,
        addCertificateDialogOpen,
        setAddCertificateDialogOpen,
        availableCertificates,
        filteredCertificates,
        selectedCertificates,
        setSelectedCertificates,
        certificateDialogSearchTerm,
        setCertificateDialogSearchTerm,
        isCertificateSearching,
        sshKeySearchTerm,
        setSshKeySearchTerm,
        addUserModalOpen,
        setAddUserModalOpen,
        addGroupModalOpen,
        setAddGroupModalOpen,
        deleteUserConfirmOpen,
        deleteGroupConfirmOpen,
        userToDelete,
        groupToDelete,
        deletingUser,
        deletingGroup,
        deleteDefaultGroup,
        setDeleteDefaultGroup,
        handleShowDialog,
        handleCloseDialog,
        handleAddSSHKey,
        handleSSHKeyDialogClose,
        handleDeleteUserClick,
        handleDeleteUserConfirm,
        handleDeleteUserCancel,
        handleDeleteGroupClick,
        handleDeleteGroupConfirm,
        handleDeleteGroupCancel,
        handleSSHKeySearch,
        handleCertificateDialogClose,
        handleCertificateSearch,
        handleDeployCertificates,
        loadAvailableCertificates,
        handleDeploySSHKeys,
    };
};
