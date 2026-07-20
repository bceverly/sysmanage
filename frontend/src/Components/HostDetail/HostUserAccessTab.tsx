// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

import React from 'react';
import {
    Box,
    Card,
    CardContent,
    Typography,
    Grid,
    Chip,
    Button,
    IconButton,
    ToggleButton,
    ToggleButtonGroup,
} from '@mui/material';
import GroupIcon from '@mui/icons-material/Group';
import PersonIcon from '@mui/icons-material/Person';
import AddIcon from '@mui/icons-material/Add';
import DeleteIcon from '@mui/icons-material/Delete';
import { useTranslation } from 'react-i18next';
import { SysManageHost, UserAccount, UserGroup } from '../../Services/hosts';
import {
    formatTimestamp,
    getUserIdDisplay,
    getGroupIdDisplay,
} from './hostDetailHelpers';
import { HostFilterMode } from './hostDetailTypes';

interface HostUserAccessTabProps {
    host: SysManageHost;
    licenseModules: string[];
    filteredUsers: UserAccount[];
    filteredGroups: UserGroup[];
    userFilter: HostFilterMode;
    setUserFilter: (value: HostFilterMode) => void;
    groupFilter: HostFilterMode;
    setGroupFilter: (value: HostFilterMode) => void;
    expandedUserGroups: Set<string>;
    setExpandedUserGroups: React.Dispatch<React.SetStateAction<Set<string>>>;
    expandedGroupUsers: Set<string>;
    setExpandedGroupUsers: React.Dispatch<React.SetStateAction<Set<string>>>;
    canAddHostAccount: boolean;
    canAddHostGroup: boolean;
    canDeleteHostAccount: boolean;
    canDeleteHostGroup: boolean;
    canDeploySshKey: boolean;
    setAddUserModalOpen: (value: boolean) => void;
    setAddGroupModalOpen: (value: boolean) => void;
    handleAddSSHKey: (user: UserAccount) => void;
    handleDeleteUserClick: (user: UserAccount) => void;
    handleDeleteGroupClick: (group: UserGroup) => void;
}

const HostUserAccessTab: React.FC<HostUserAccessTabProps> = ({
    host,
    licenseModules,
    filteredUsers,
    filteredGroups,
    userFilter,
    setUserFilter,
    groupFilter,
    setGroupFilter,
    expandedUserGroups,
    setExpandedUserGroups,
    expandedGroupUsers,
    setExpandedGroupUsers,
    canAddHostAccount,
    canAddHostGroup,
    canDeleteHostAccount,
    canDeleteHostGroup,
    canDeploySshKey,
    setAddUserModalOpen,
    setAddGroupModalOpen,
    handleAddSSHKey,
    handleDeleteUserClick,
    handleDeleteGroupClick,
}) => {
    const { t } = useTranslation();
    return (
                <Grid container spacing={3}>
                    {/* User Accounts */}
                    <Grid size={{ xs: 12 }}>
                        <Card>
                            <CardContent>
                                <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 2 }}>
                                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
                                        <Typography variant="subtitle1" sx={{ display: 'flex', alignItems: 'center', fontWeight: 'bold', fontSize: '1.1rem' }}>
                                            <PersonIcon sx={{ mr: 1 }} />
                                            {t('hostDetail.userAccounts', 'User Accounts')} ({filteredUsers.length})
                                        </Typography>
                                        <Typography variant="caption" color="textSecondary">
                                            {t('hosts.updated', 'Updated')}: {formatTimestamp(t, host.user_access_updated_at)}
                                        </Typography>
                                    </Box>
                                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                                        {canAddHostAccount && host?.is_agent_privileged && (
                                            <Button
                                                variant="contained"
                                                color="primary"
                                                size="small"
                                                startIcon={<AddIcon />}
                                                onClick={() => setAddUserModalOpen(true)}
                                                disabled={!host?.active}
                                            >
                                                {t('hostAccount.add', 'Add')}
                                            </Button>
                                        )}
                                        <ToggleButtonGroup
                                            value={userFilter}
                                            exclusive
                                            onChange={(_, newFilter) => {
                                                if (newFilter !== null) {
                                                    setUserFilter(newFilter);
                                                }
                                            }}
                                            size="small"
                                        >
                                            <ToggleButton value="regular" aria-label="regular users">
                                                {t('hostDetail.regularUsers', 'Regular')}
                                            </ToggleButton>
                                            <ToggleButton value="system" aria-label="system users">
                                                {t('hostDetail.systemUsers', 'System')}
                                            </ToggleButton>
                                            <ToggleButton value="all" aria-label="all users">
                                                {t('hostDetail.allUsers', 'All')}
                                            </ToggleButton>
                                        </ToggleButtonGroup>
                                    </Box>
                                </Box>
                                {filteredUsers.length === 0 ? (
                                    <Typography variant="body2" color="textSecondary" sx={{ fontStyle: 'italic', textAlign: 'center', py: 2 }}>
                                        {t('hostDetail.noUsersFound', 'No user accounts found')}
                                    </Typography>
                                ) : (
                                    <Grid container spacing={2}>
                                        {filteredUsers.map((user: UserAccount, index: number) => (
                                            <Grid size={{ xs: 12, sm: 6, md: 4 }} key={user.id || index}>
                                                <Card sx={{ backgroundColor: 'grey.900', height: '100%' }}>
                                                    <CardContent sx={{ p: 2 }}>
                                                        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', mb: 1 }}>
                                                            <Typography variant="subtitle2" sx={{ fontWeight: 'bold' }}>
                                                                {user.username}
                                                            </Typography>
                                                            <Box sx={{ display: 'flex', gap: 0.5 }}>
                                                                {canDeploySshKey && licenseModules.includes('secrets_engine') && (
                                                                    <Button
                                                                        size="small"
                                                                        variant="outlined"
                                                                        color="primary"
                                                                        onClick={() => handleAddSSHKey(user)}
                                                                        disabled={!host?.active || !host?.is_agent_privileged}
                                                                        sx={{ minWidth: 'auto', fontSize: '0.7rem', py: 0.25, px: 1 }}
                                                                    >
                                                                        {t('hostDetail.addSSHKey', 'Add SSH Key')}
                                                                    </Button>
                                                                )}
                                                                {canDeleteHostAccount && host?.is_agent_privileged && !user.is_system_user && (
                                                                    <IconButton
                                                                        size="small"
                                                                        color="error"
                                                                        onClick={() => handleDeleteUserClick(user)}
                                                                        disabled={!host?.active}
                                                                        title={t('hostAccount.deleteUser', 'Delete User')}
                                                                        sx={{ p: 0.25 }}
                                                                    >
                                                                        <DeleteIcon fontSize="small" />
                                                                    </IconButton>
                                                                )}
                                                            </Box>
                                                        </Box>
                                                        <Typography variant="body2" color="textSecondary" sx={{ mb: 0.5 }}>
                                                            {getUserIdDisplay(t, host, user)}
                                                        </Typography>
                                                        {user.home_directory && (
                                                            <Typography variant="body2" color="textSecondary" sx={{ mb: 0.5, wordBreak: 'break-all' }}>
                                                                {t('hostDetail.homeDir', 'Home')}: {user.home_directory}
                                                            </Typography>
                                                        )}
                                                        {user.shell && (
                                                            <Typography variant="body2" color="textSecondary" sx={{ mb: 0.5 }}>
                                                                {t('hostDetail.shell', 'Shell')}: {user.shell}
                                                            </Typography>
                                                        )}
                                                        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mt: 1, mb: 1 }}>
                                                            <Chip 
                                                                label={user.is_system_user ? t('hostDetail.systemUser', 'System') : t('hostDetail.regularUser', 'Regular')}
                                                                color={user.is_system_user ? 'default' : 'primary'}
                                                                size="small"
                                                            />
                                                        </Box>
                                                        {user.groups && user.groups.length > 0 && (
                                                            <Box sx={{ mt: 1 }}>
                                                                <Typography variant="body2" color="textSecondary" sx={{ mb: 0.5, fontSize: '0.75rem' }}>
                                                                    {t('hostDetail.memberOfGroups', 'Groups')}:
                                                                </Typography>
                                                                <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.5, maxHeight: expandedUserGroups.has(user.id) ? 'none' : '60px', overflow: 'auto' }}>
                                                                    {(expandedUserGroups.has(user.id) ? user.groups : user.groups.slice(0, 6)).map((groupName: string) => (
                                                                        <Chip
                                                                            key={groupName}
                                                                            label={groupName}
                                                                            size="small"
                                                                            variant="outlined"
                                                                            color="secondary"
                                                                            sx={{ 
                                                                                fontSize: '0.7rem', 
                                                                                height: '20px',
                                                                                '& .MuiChip-label': { px: 1 }
                                                                            }}
                                                                        />
                                                                    ))}
                                                                    {user.groups.length > 6 && !expandedUserGroups.has(user.id) && (
                                                                        <Chip 
                                                                            label={`+${user.groups.length - 6}`}
                                                                            size="small"
                                                                            variant="outlined"
                                                                            color="info"
                                                                            sx={{ 
                                                                                fontSize: '0.7rem', 
                                                                                height: '20px',
                                                                                '& .MuiChip-label': { px: 1 },
                                                                                cursor: 'pointer'
                                                                            }}
                                                                            onClick={() => {
                                                                                setExpandedUserGroups(prev => new Set([...Array.from(prev), user.id]));
                                                                            }}
                                                                        />
                                                                    )}
                                                                    {expandedUserGroups.has(user.id) && (
                                                                        <Chip 
                                                                            label={t('common.less', 'less')}
                                                                            size="small"
                                                                            variant="outlined"
                                                                            color="default"
                                                                            sx={{ 
                                                                                fontSize: '0.7rem', 
                                                                                height: '20px',
                                                                                '& .MuiChip-label': { px: 1 },
                                                                                cursor: 'pointer'
                                                                            }}
                                                                            onClick={() => {
                                                                                setExpandedUserGroups(prev => {
                                                                                    const newSet = new Set(prev);
                                                                                    newSet.delete(user.id);
                                                                                    return newSet;
                                                                                });
                                                                            }}
                                                                        />
                                                                    )}
                                                                </Box>
                                                            </Box>
                                                        )}
                                                    </CardContent>
                                                </Card>
                                            </Grid>
                                        ))}
                                    </Grid>
                                )}
                            </CardContent>
                        </Card>
                    </Grid>

                    {/* User Groups */}
                    <Grid size={{ xs: 12 }}>
                        <Card>
                            <CardContent>
                                <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 2 }}>
                                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
                                        <Typography variant="subtitle1" sx={{ display: 'flex', alignItems: 'center', fontWeight: 'bold', fontSize: '1.1rem' }}>
                                            <GroupIcon sx={{ mr: 1 }} />
                                            {t('hostDetail.userGroups', 'User Groups')} ({filteredGroups.length})
                                        </Typography>
                                        <Typography variant="caption" color="textSecondary">
                                            {t('hosts.updated', 'Updated')}: {formatTimestamp(t, host.user_access_updated_at)}
                                        </Typography>
                                    </Box>
                                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                                        {canAddHostGroup && host?.is_agent_privileged && (
                                            <Button
                                                variant="contained"
                                                color="primary"
                                                size="small"
                                                startIcon={<AddIcon />}
                                                onClick={() => setAddGroupModalOpen(true)}
                                                disabled={!host?.active}
                                            >
                                                {t('hostGroup.add', 'Add')}
                                            </Button>
                                        )}
                                        <ToggleButtonGroup
                                            value={groupFilter}
                                            exclusive
                                            onChange={(_, newFilter) => {
                                                if (newFilter !== null) {
                                                    setGroupFilter(newFilter);
                                                }
                                            }}
                                            size="small"
                                        >
                                            <ToggleButton value="regular" aria-label="regular groups">
                                                {t('hostDetail.regularGroups', 'Regular')}
                                            </ToggleButton>
                                            <ToggleButton value="system" aria-label="system groups">
                                                {t('hostDetail.systemGroups', 'System')}
                                            </ToggleButton>
                                            <ToggleButton value="all" aria-label="all groups">
                                                {t('hostDetail.allGroups', 'All')}
                                            </ToggleButton>
                                        </ToggleButtonGroup>
                                    </Box>
                                </Box>
                                {filteredGroups.length === 0 ? (
                                    <Typography variant="body2" color="textSecondary" sx={{ fontStyle: 'italic', textAlign: 'center', py: 2 }}>
                                        {t('hostDetail.noGroupsFound', 'No user groups found')}
                                    </Typography>
                                ) : (
                                    <Grid container spacing={2}>
                                        {filteredGroups.map((group: UserGroup, index: number) => (
                                            <Grid size={{ xs: 12, sm: 6, md: 4 }} key={group.id || index}>
                                                <Card sx={{ backgroundColor: 'grey.900', height: '100%' }}>
                                                    <CardContent sx={{ p: 2 }}>
                                                        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', mb: 1 }}>
                                                            <Typography variant="subtitle2" sx={{ fontWeight: 'bold' }}>
                                                                {group.group_name}
                                                            </Typography>
                                                            {canDeleteHostGroup && host?.is_agent_privileged && !group.is_system_group && (
                                                                <IconButton
                                                                    size="small"
                                                                    color="error"
                                                                    onClick={() => handleDeleteGroupClick(group)}
                                                                    disabled={!host?.active}
                                                                    title={t('hostGroup.deleteGroup', 'Delete Group')}
                                                                    sx={{ p: 0.25 }}
                                                                >
                                                                    <DeleteIcon fontSize="small" />
                                                                </IconButton>
                                                            )}
                                                        </Box>
                                                        <Typography variant="body2" color="textSecondary" sx={{ mb: 0.5 }}>
                                                            {getGroupIdDisplay(t, host, group)}
                                                        </Typography>
                                                        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mt: 1, mb: 1 }}>
                                                            <Chip
                                                                label={group.is_system_group ? t('hostDetail.systemGroup', 'System') : t('hostDetail.regularGroup', 'Regular')}
                                                                color={group.is_system_group ? 'default' : 'primary'}
                                                                size="small"
                                                            />
                                                        </Box>
                                                        {group.users && group.users.length > 0 && (
                                                            <Box sx={{ mt: 1 }}>
                                                                <Typography variant="body2" color="textSecondary" sx={{ mb: 0.5, fontSize: '0.75rem' }}>
                                                                    {t('hostDetail.groupMembers', 'Members')}:
                                                                </Typography>
                                                                <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.5, maxHeight: expandedGroupUsers.has(group.id) ? 'none' : '60px', overflow: 'auto' }}>
                                                                    {(expandedGroupUsers.has(group.id) ? group.users : group.users.slice(0, 6)).map((userName: string) => (
                                                                        <Chip
                                                                            key={userName}
                                                                            label={userName}
                                                                            size="small"
                                                                            variant="outlined"
                                                                            color="secondary"
                                                                            sx={{ 
                                                                                fontSize: '0.7rem', 
                                                                                height: '20px',
                                                                                '& .MuiChip-label': { px: 1 }
                                                                            }}
                                                                        />
                                                                    ))}
                                                                    {group.users.length > 6 && !expandedGroupUsers.has(group.id) && (
                                                                        <Chip 
                                                                            label={`+${group.users.length - 6}`}
                                                                            size="small"
                                                                            variant="outlined"
                                                                            color="info"
                                                                            sx={{ 
                                                                                fontSize: '0.7rem', 
                                                                                height: '20px',
                                                                                '& .MuiChip-label': { px: 1 },
                                                                                cursor: 'pointer'
                                                                            }}
                                                                            onClick={() => {
                                                                                setExpandedGroupUsers(prev => new Set([...Array.from(prev), group.id]));
                                                                            }}
                                                                        />
                                                                    )}
                                                                    {expandedGroupUsers.has(group.id) && (
                                                                        <Chip 
                                                                            label={t('common.less', 'less')}
                                                                            size="small"
                                                                            variant="outlined"
                                                                            color="default"
                                                                            sx={{ 
                                                                                fontSize: '0.7rem', 
                                                                                height: '20px',
                                                                                '& .MuiChip-label': { px: 1 },
                                                                                cursor: 'pointer'
                                                                            }}
                                                                            onClick={() => {
                                                                                setExpandedGroupUsers(prev => {
                                                                                    const newSet = new Set(prev);
                                                                                    newSet.delete(group.id);
                                                                                    return newSet;
                                                                                });
                                                                            }}
                                                                        />
                                                                    )}
                                                                </Box>
                                                            </Box>
                                                        )}
                                                    </CardContent>
                                                </Card>
                                            </Grid>
                                        ))}
                                    </Grid>
                                )}
                            </CardContent>
                        </Card>
                    </Grid>
                </Grid>    );
};

export default HostUserAccessTab;
