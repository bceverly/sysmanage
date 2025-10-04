import { useNavigate } from "react-router-dom";
import React, { useEffect, useState, useCallback } from 'react';
import { DataGrid, GridColDef, GridRowSelectionModel } from '@mui/x-data-grid';
import { useTranslation } from 'react-i18next';
import { useTablePageSize } from '../hooks/useTablePageSize';
import Box from '@mui/material/Box';
import Stack from '@mui/material/Stack';
import Button from '@mui/material/Button';
import AddIcon from '@mui/icons-material/Add';
import EditIcon from '@mui/icons-material/Edit';
import VisibilityIcon from '@mui/icons-material/Visibility';
import Dialog from '@mui/material/Dialog';
import DialogActions from '@mui/material/DialogActions';
import DialogContent from '@mui/material/DialogContent';
import DialogContentText from '@mui/material/DialogContentText';
import DialogTitle from '@mui/material/DialogTitle';
import TextField from '@mui/material/TextField';
import InputAdornment from '@mui/material/InputAdornment';
import IconButton from '@mui/material/IconButton';
import AccountCircle from '@mui/icons-material/AccountCircle';
import { SysManageUser, doAddUser, doDeleteUser, doGetUsers, doUnlockUser, doLockUser, doUpdateUser, doUploadUserImage, doGetUserImage, doDeleteUserImage } from '../Services/users'
import LockIcon from '@mui/icons-material/Lock';
import LockOpenIcon from '@mui/icons-material/LockOpen';
import PhotoCameraIcon from '@mui/icons-material/PhotoCamera';
import DeleteIcon from '@mui/icons-material/Delete';
import Avatar from '@mui/material/Avatar';
import SearchBox from '../Components/SearchBox';
import { hasPermission, SecurityRoles } from '../Services/permissions';

const Users = () => {
    const [tableData, setTableData] = useState<SysManageUser[]>([]);
    const [filteredData, setFilteredData] = useState<SysManageUser[]>([]);
    const [selection, setSelection] = useState<GridRowSelectionModel>([]);
    const [addDialogOpen, setAddDialogOpen] = useState(false);
    const [editDialogOpen, setEditDialogOpen] = useState(false);
    const [dupeError, setDupeError] = useState<boolean>(false);
    const [editUser, setEditUser] = useState<SysManageUser | null>(null);
    const [editEmail, setEditEmail] = useState<string>('');
    const [editPassword, setEditPassword] = useState<string>('');
    const [editFirstName, setEditFirstName] = useState<string>('');
    const [editLastName, setEditLastName] = useState<string>('');
    const [editUserImageUrl, setEditUserImageUrl] = useState<string | null>(null);
    const [editImageLoading, setEditImageLoading] = useState<boolean>(false);
    const [searchTerm, setSearchTerm] = useState<string>('');
    const [searchColumn, setSearchColumn] = useState<string>('userid');

    // Permission states
    const [canLockUser, setCanLockUser] = useState<boolean>(false);
    const [canUnlockUser, setCanUnlockUser] = useState<boolean>(false);
    const [canAddUser, setCanAddUser] = useState<boolean>(false);
    const [canEditUser, setCanEditUser] = useState<boolean>(false);
    const [canDeleteUser, setCanDeleteUser] = useState<boolean>(false);

    const { t } = useTranslation();

    // Dynamic table page sizing based on window height
    const { pageSize, pageSizeOptions } = useTablePageSize({
        reservedHeight: 350, // Account for navbar, title, buttons, margins, and action buttons below table
        minRows: 5,
        maxRows: 50,
    });

    const navigate = useNavigate();

    const columns: GridColDef[] = [
        { field: 'id', headerName: t('common.id', 'ID'), width: 70 },
        { field: 'userid', headerName: t('users.email'), width: 400 },
        { 
            field: 'is_locked', 
            headerName: t('users.status'), 
            width: 120,
            renderCell: (params) => (
                <Box display="flex" alignItems="center">
                    {params.value ? (
                        <>
                            <LockIcon color="error" sx={{ mr: 1 }} />
                            {t('users.locked')}
                        </>
                    ) : (
                        <>
                            <LockOpenIcon color="success" sx={{ mr: 1 }} />
                            {t('users.unlocked')}
                        </>
                    )}
                </Box>
            )
        },
        {
            field: 'actions',
            headerName: t('common.actions'),
            width: 100,
            sortable: false,
            filterable: false,
            renderCell: (params) => (
                <IconButton
                    color="primary"
                    size="small"
                    onClick={() => navigate(`/users/${params.row.id}`)}
                    title={t('common.view')}
                >
                    <VisibilityIcon />
                </IconButton>
            )
        }
    ];

    // Search columns configuration (excluding irrelevant columns)
    const searchColumns = [
        { field: 'userid', label: t('users.email') }
    ];

    const handleDelete = async () => {
        try {
            // Call the API to remove the selected rows
            const deletePromises = selection.map(id => {
                return doDeleteUser(id.toString());
            });
            
            await Promise.all(deletePromises);
            
            // Refresh the data from the server
            const updatedUsers = await doGetUsers();
            setTableData(updatedUsers);
            
            // Clear selection
            setSelection([]);
        } catch (error) {
            console.error('Error deleting users:', error);
        }
    }

    const handleUnlock = async () => {
        // Call the API to unlock the selected rows
        const promises = selection.map(async (selectedItem) => {
            if (!selectedItem || typeof selectedItem !== 'string' && typeof selectedItem !== 'number') {
                return;
            }
            let theID = selectedItem.toString();
            try {
                const updatedUser = await doUnlockUser(theID);
                // Update the tableData with the new status
                setTableData(prevData =>
                    prevData.map(user =>
                        user.id === updatedUser.id ? updatedUser : user
                    )
                );
            } catch (error) {
                console.error('Error unlocking user:', error);
            }
        });

        // Wait for all operations to complete, then clear selection
        await Promise.all(promises);
        setSelection([]);
    }

    const handleLock = async () => {
        // Call the API to lock the selected rows
        const promises = selection.map(async (selectedItem) => {
            if (!selectedItem || typeof selectedItem !== 'string' && typeof selectedItem !== 'number') {
                return;
            }
            let theID = selectedItem.toString();
            try {
                const updatedUser = await doLockUser(theID);
                // Update the tableData with the new status
                setTableData(prevData =>
                    prevData.map(user =>
                        user.id === updatedUser.id ? updatedUser : user
                    )
                );
            } catch (error) {
                console.error('Error locking user:', error);
            }
        });

        // Wait for all operations to complete, then clear selection
        await Promise.all(promises);
        setSelection([]);
    }

    const getSelectedUsersLockStatus = () => {
        const selectedUsers = filteredData.filter(user =>
            selection.includes(user.id)
        );
        return selectedUsers.some(user => user.is_locked);
    };

    const getSelectedUsersUnlockStatus = () => {
        const selectedUsers = filteredData.filter(user =>
            selection.includes(user.id)
        );
        return selectedUsers.some(user => !user.is_locked);
    };

    // Search functionality
    const performSearch = useCallback(() => {
        if (!searchTerm.trim()) {
            setFilteredData(tableData);
            return;
        }

        const filtered = tableData.filter(user => {
            const fieldValue = user[searchColumn as keyof SysManageUser];
            if (fieldValue === null || fieldValue === undefined) {
                return false;
            }
            return String(fieldValue).toLowerCase().includes(searchTerm.toLowerCase());
        });
        
        setFilteredData(filtered);
    }, [searchTerm, searchColumn, tableData]);

    // Update filtered data when table data changes or search is cleared
    React.useEffect(() => {
        if (!searchTerm.trim()) {
            setFilteredData(tableData);
        } else {
            performSearch();
        }
    }, [tableData, searchTerm, searchColumn, performSearch]);

    // Check permissions
    useEffect(() => {
        const checkPermissions = async () => {
            const [lockUser, unlockUser, addUser, editUser, deleteUser] = await Promise.all([
                hasPermission(SecurityRoles.LOCK_USER),
                hasPermission(SecurityRoles.UNLOCK_USER),
                hasPermission(SecurityRoles.ADD_USER),
                hasPermission(SecurityRoles.EDIT_USER),
                hasPermission(SecurityRoles.DELETE_USER)
            ]);
            setCanLockUser(lockUser);
            setCanUnlockUser(unlockUser);
            setCanAddUser(addUser);
            setCanEditUser(editUser);
            setCanDeleteUser(deleteUser);
        };
        checkPermissions();
    }, []);

    const handleClickOpen = () => {
        setAddDialogOpen(true);
    };

    const fetchEditUserImage = async (userId: string) => {
        if (editImageLoading) return;
        
        setEditImageLoading(true);
        try {
            const imageBlob = await doGetUserImage(userId);
            const imageUrl = window.URL.createObjectURL(imageBlob);
            setEditUserImageUrl(imageUrl);
        } catch {
            console.debug('No profile image available for user or error fetching image');
            setEditUserImageUrl(null);
        } finally {
            setEditImageLoading(false);
        }
    };

    const handleEditClickOpen = () => {
        if (selection.length === 1) {
            const selectedUser = filteredData.find(user => Number(user.id) === Number(selection[0]));
            if (selectedUser) {
                setEditUser(selectedUser);
                setEditEmail(selectedUser.userid);
                setEditPassword('');
                setEditFirstName(selectedUser.first_name || '');
                setEditLastName(selectedUser.last_name || '');
                setEditUserImageUrl(null);
                setEditDialogOpen(true);
                // Fetch the user's profile image
                fetchEditUserImage(selectedUser.id);
            }
        }
    };
    
    const handleClose = () => {
        setDupeError(false);
        setAddDialogOpen(false);
    };

    const handleEditClose = () => {
        setDupeError(false);
        setEditDialogOpen(false);
        setEditUser(null);
        setEditEmail('');
        setEditPassword('');
        setEditFirstName('');
        setEditLastName('');
        // Clean up image URL
        if (editUserImageUrl) {
            window.URL.revokeObjectURL(editUserImageUrl);
        }
        setEditUserImageUrl(null);
        setEditImageLoading(false);
    };

    const handleEditImageUpload = async (event: React.ChangeEvent<HTMLInputElement>) => {
        const file = event.target.files?.[0];
        if (!file || !editUser) return;

        try {
            await doUploadUserImage(editUser.id, file);
            // Refresh the image
            await fetchEditUserImage(editUser.id);
        } catch (error) {
            console.error('Error uploading profile image:', error);
        }
    };

    const handleEditImageDelete = async () => {
        if (!editUser) return;

        try {
            await doDeleteUserImage(editUser.id);
            // Clear the current image
            if (editUserImageUrl) {
                window.URL.revokeObjectURL(editUserImageUrl);
            }
            setEditUserImageUrl(null);
        } catch (error) {
            console.error('Error deleting profile image:', error);
        }
    };

    const getFirstInitial = (email: string): string => {
        if (!email) return '?';
        const beforeAt = email.split('@')[0];
        return beforeAt.charAt(0).toUpperCase();
    };

    useEffect(() => {
        if (!localStorage.getItem('bearer_token')) {
            navigate("/login");
        }
        doGetUsers().then((response: SysManageUser[]) => {
            setTableData(response);
            return Promise.resolve(response);
        });
    }, [navigate]);

    return (
        <div>
            {/* Search Box */}
            <SearchBox
                searchTerm={searchTerm}
                setSearchTerm={setSearchTerm}
                searchColumn={searchColumn}
                setSearchColumn={setSearchColumn}
                columns={searchColumns}
                placeholder={t('search.searchUsers', 'Search users')}
            />
            
            <div  style={{ height: `${Math.min(600, Math.max(300, (pageSize + 2) * 52 + 120))}px` }}>
                <DataGrid
                    rows={filteredData}
                    columns={columns}
                    initialState={{
                        pagination: {
                            paginationModel: { page: 0, pageSize: pageSize },
                        },
                        sorting: {
                            sortModel: [{ field: 'userid', sort: 'asc'}],
                        },
                        columns: {
                            columnVisibilityModel: {
                                id: false,
                            },
                        },
                    }}
                    autosizeOptions = {{
                        columns: ['userid'],
                        includeOutliers: true,
                        includeHeaders: true,
                    }}
                    pageSizeOptions={pageSizeOptions}
                    checkboxSelection
                    rowSelectionModel={selection}
                    onRowSelectionModelChange={setSelection}
                    localeText={{
                        MuiTablePagination: {
                            labelRowsPerPage: t('common.rowsPerPage'),
                            labelDisplayedRows: ({ from, to, count }: { from: number, to: number, count: number }) =>
                                `${from}–${to} ${t('common.of')} ${count !== -1 ? count : `${t('common.of')} ${to}`}`,
                        },
                    }}
                />
            </div>
            <Box component="section">&nbsp;</Box>
            <Stack direction="row" spacing={2}>
                {canAddUser && (
                    <Button variant="outlined" startIcon={<AddIcon />} disabled={selection.length > 0} onClick={handleClickOpen}>
                        {t('common.add')}
                    </Button>
                )}
                {canEditUser && (
                    <Button variant="outlined" startIcon={<EditIcon />} disabled={selection.length !== 1} onClick={handleEditClickOpen}>
                        {t('common.edit')}
                    </Button>
                )}
                {canLockUser && (
                    <Button
                        variant="outlined"
                        startIcon={<LockIcon />}
                        disabled={selection.length === 0 || !getSelectedUsersUnlockStatus()}
                        onClick={handleLock}
                    >
                        {t('users.lockSelected')}
                    </Button>
                )}
                {canUnlockUser && (
                    <Button
                        variant="outlined"
                        startIcon={<LockOpenIcon />}
                        disabled={selection.length === 0 || !getSelectedUsersLockStatus()}
                        onClick={handleUnlock}
                    >
                        {t('users.unlockSelected')}
                    </Button>
                )}
                {canDeleteUser && (
                    <Button variant="outlined" startIcon={<DeleteIcon />} disabled={selection.length === 0} onClick={handleDelete}>
                        {t('common.delete')} {t('common.selected')}
                    </Button>
                )}
            </Stack>
            <Dialog
                open={addDialogOpen}
                onClose={handleClose}
                PaperProps={{
                    component: 'form',
                    onSubmit: (event: React.FormEvent<HTMLFormElement>) => {
                        event.preventDefault();
                        const formData = new FormData(event.currentTarget);
                        const formJson = Object.fromEntries(formData.entries());
                        doAddUser(
                            true,
                            formJson.email as string,
                            '', // No password - will be set via email
                            formJson.firstName as string,
                            formJson.lastName as string
                        )
                        .then((result) => {
                            const newData: SysManageUser[] = tableData.filter(dataItem =>
                                dataItem && typeof dataItem === 'object' && dataItem.id
                            );
                            const newRow: SysManageUser = {
                                id: result.id,
                                active: result.active,
                                userid: result.userid,
                                password: result.password,
                                is_locked: result.is_locked,
                                failed_login_attempts: result.failed_login_attempts,
                                locked_at: result.locked_at,
                            };
                            newData.push(newRow);
                            setTableData(newData);
                            setDupeError(false);
                            handleClose();
                        })
                        .catch((error) => {
                            console.log('TheError: ' + error);
                            if (error === 'AxiosError: Request failed with status code 409') {
                                setDupeError(true);
                            }
                        });
                    },
                }}
            >
                <DialogTitle align="center">{t('users.addUser')}</DialogTitle>
                <DialogContent>
                    <DialogContentText>
                        {t('users.enterInfo', { defaultValue: 'Enter the new user\'s information below.' })}
                    </DialogContentText>
                    <DialogContentText sx={{ mt: 2, fontSize: '0.875rem', color: 'text.secondary' }}>
                        {t('users.emailNotification', { defaultValue: 'An email will be sent to the user with a secure link to set their initial password.' })}
                    </DialogContentText>
                    <Box component="section">&nbsp;</Box>
                    <TextField
                        autoFocus
                        required
                        fullWidth
                        margin="normal"
                        id="email"
                        name="email"
                        label={t('users.email')}
                        type="email"
                        variant="standard"
                        error={dupeError}
                        helperText={dupeError ? t('users.emailUnique', { defaultValue: 'Email address must be unique' }) : ""}
                        InputProps={{
                            startAdornment: (
                              <InputAdornment position="start">
                                <AccountCircle />
                              </InputAdornment>
                            ),
                          }}
                    />
                    <TextField
                        fullWidth
                        margin="normal"
                        id="firstName"
                        name="firstName"
                        label={t('users.firstName', 'First Name')}
                        type="text"
                        variant="standard"
                    />
                    <TextField
                        fullWidth
                        margin="normal"
                        id="lastName"
                        name="lastName"
                        label={t('users.lastName', 'Last Name')}
                        type="text"
                        variant="standard"
                    />
                </DialogContent>
                <DialogActions>
                    <Button onClick={handleClose}>{t('common.cancel')}</Button>
                    <Button type="submit">{t('common.save')}</Button>
                </DialogActions>
            </Dialog>
            <Dialog
                key={editUser?.id ? String(editUser.id) : 'no-user'}
                open={editDialogOpen}
                onClose={handleEditClose}
                maxWidth="sm"
                fullWidth
                PaperProps={{
                    component: 'form',
                    onSubmit: (event: React.FormEvent<HTMLFormElement>) => {
                        event.preventDefault();
                        if (!editUser) return;
                        
                        doUpdateUser(editUser.id, true, editEmail, editPassword, editFirstName, editLastName)
                        .then(() => {
                            // Update the tableData with the edited user
                            setTableData(prevData => 
                                prevData.map(user => 
                                    user.id === editUser.id ? {
                                        ...user,
                                        userid: editEmail,
                                        password: editPassword
                                    } : user
                                )
                            );
                            setDupeError(false);
                            handleEditClose();
                            setSelection([]);
                        })
                        .catch((error) => {
                            console.log('TheError: ' + error);
                            if (error === 'AxiosError: Request failed with status code 409') {
                                setDupeError(true);
                            }
                        });
                    },
                }}
            >
                <DialogTitle align="center">{t('users.editUser')}</DialogTitle>
                <DialogContent>
                    <DialogContentText>
                        {t('users.editInfo', { defaultValue: 'Edit the user\'s information below.' })}
                    </DialogContentText>
                    
                    {/* Profile Image Section */}
                    <Box sx={{ display: 'flex', flexDirection: 'column', alignItems: 'center', my: 3 }}>
                        <Avatar
                            src={editUserImageUrl || undefined}
                            sx={{
                                width: 120,
                                height: 120,
                                mb: 2,
                                bgcolor: editUserImageUrl ? 'transparent' : 'primary.main',
                                fontSize: '2rem',
                                fontWeight: 'bold',
                            }}
                        >
                            {!editUserImageUrl && getFirstInitial(editEmail)}
                        </Avatar>
                        
                        <Stack direction="row" spacing={2}>
                            <Button
                                variant="outlined"
                                component="label"
                                startIcon={<PhotoCameraIcon />}
                                size="small"
                            >
                                {t('profile.uploadImage', 'Upload Image')}
                                <input
                                    type="file"
                                    hidden
                                    accept="image/*"
                                    onChange={handleEditImageUpload}
                                />
                            </Button>
                            {editUserImageUrl && (
                                <Button
                                    variant="outlined"
                                    color="error"
                                    startIcon={<DeleteIcon />}
                                    size="small"
                                    onClick={handleEditImageDelete}
                                >
                                    {t('profile.deleteImage', 'Delete')}
                                </Button>
                            )}
                        </Stack>
                    </Box>
                    
                    <Box component="section">&nbsp;</Box>
                    <TextField
                        autoFocus
                        required
                        fullWidth
                        margin="normal"
                        id="email"
                        name="email"
                        label={t('users.email')}
                        type="email"
                        variant="standard"
                        value={editEmail}
                        onChange={(e) => setEditEmail(e.target.value)}
                        error={dupeError}
                        helperText={dupeError ? t('users.emailUnique', { defaultValue: 'Email address must be unique' }) : ""}
                        InputProps={{
                            startAdornment: (
                              <InputAdornment position="start">
                                <AccountCircle />
                              </InputAdornment>
                            ),
                          }}
                    />
                    <TextField
                        fullWidth
                        margin="normal"
                        id="editFirstName"
                        name="editFirstName"
                        label={t('users.firstName', 'First Name')}
                        type="text"
                        variant="standard"
                        value={editFirstName}
                        onChange={(e) => setEditFirstName(e.target.value)}
                    />
                    <TextField
                        fullWidth
                        margin="normal"
                        id="editLastName"
                        name="editLastName"
                        label={t('users.lastName', 'Last Name')}
                        type="text"
                        variant="standard"
                        value={editLastName}
                        onChange={(e) => setEditLastName(e.target.value)}
                    />
                    <Box component="section">&nbsp;</Box>
                    <TextField
                        required
                        fullWidth
                        margin="normal"
                        id="password"
                        name="password"
                        label={t('users.newPassword', 'Enter new password')}
                        type="password"
                        variant="standard"
                        value={editPassword}
                        onChange={(e) => setEditPassword(e.target.value)}
                        placeholder={t('users.newPassword', { defaultValue: 'Enter new password' })}
                    />
                </DialogContent>
                <DialogActions>
                    <Button onClick={handleEditClose}>{t('common.cancel')}</Button>
                    <Button type="submit">{t('common.save')}</Button>
                </DialogActions>
            </Dialog>
        </div>
    );
}
 
export default Users;