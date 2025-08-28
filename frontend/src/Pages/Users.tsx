import { useNavigate } from "react-router-dom";
import React, { useEffect, useState } from 'react';
import { DataGrid, GridColDef, GridRowSelectionModel } from '@mui/x-data-grid';
import { useTranslation } from 'react-i18next';
import Box from '@mui/material/Box';
import Stack from '@mui/material/Stack';
import Button from '@mui/material/Button';
import AddIcon from '@mui/icons-material/Add';
import DeleteIcon from '@mui/icons-material/Delete';
import EditIcon from '@mui/icons-material/Edit';
import Dialog from '@mui/material/Dialog';
import DialogActions from '@mui/material/DialogActions';
import DialogContent from '@mui/material/DialogContent';
import DialogContentText from '@mui/material/DialogContentText';
import DialogTitle from '@mui/material/DialogTitle';
import TextField from '@mui/material/TextField';
import InputAdornment from '@mui/material/InputAdornment';
import AccountCircle from '@mui/icons-material/AccountCircle';
import { SysManageUser, doAddUser, doDeleteUser, doGetUsers, doUnlockUser, doUpdateUser } from '../Services/users'
import LockIcon from '@mui/icons-material/Lock';
import LockOpenIcon from '@mui/icons-material/LockOpen';

const Users = () => {
    const [tableData, setTableData] = useState<SysManageUser[]>([]);
    const [selection, setSelection] = useState<GridRowSelectionModel>([]);
    const [addDialogOpen, setAddDialogOpen] = useState(false);
    const [editDialogOpen, setEditDialogOpen] = useState(false);
    const [dupeError, setDupeError] = useState<boolean>(false);
    const [editUser, setEditUser] = useState<SysManageUser | null>(null);
    const [editEmail, setEditEmail] = useState<string>('');
    const [editPassword, setEditPassword] = useState<string>('');
    const { t } = useTranslation();

    const navigate = useNavigate();

    const columns: GridColDef[] = [
        { field: 'id', headerName: 'ID', width: 70 },
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
        }
    ]

    const handleDelete = async () => {
        try {
            // Call the API to remove the selected rows
            const deletePromises = selection.map(id => {
                const theID = BigInt(id.toString());
                return doDeleteUser(theID);
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

    const handleUnlock = () => {
        // Call the API to unlock the selected rows
        for (let i=0 ; i<selection.length ; i++) {
            let theID =  BigInt(selection[i].toString());
            doUnlockUser(theID).then((updatedUser) => {
                // Update the tableData with the new status
                setTableData(prevData => 
                    prevData.map(user => 
                        user.id === updatedUser.id ? updatedUser : user
                    )
                );
            }).catch(error => {
                console.error('Error unlocking user:', error);
            });
        }
        // Clear selection after unlock
        setSelection([]);
    }

    const getSelectedUsersLockStatus = () => {
        const selectedUsers = tableData.filter(user => 
            selection.includes(Number(user.id))
        );
        return selectedUsers.some(user => user.is_locked);
    }

    const handleClickOpen = () => {
        setAddDialogOpen(true);
    };

    const handleEditClickOpen = () => {
        if (selection.length === 1) {
            const selectedUser = tableData.find(user => Number(user.id) === Number(selection[0]));
            if (selectedUser) {
                setEditUser(selectedUser);
                setEditEmail(selectedUser.userid);
                setEditPassword('');
                setEditDialogOpen(true);
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
            <div  style={{ height: 400, width: '99%' }}>
                <DataGrid
                    rows={tableData}
                    columns={columns}
                    initialState={{
                        pagination: {
                        paginationModel: { page: 0, pageSize: 5 },
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
                    pageSizeOptions={[5, 10]}
                    checkboxSelection
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
                <Button variant="outlined" startIcon={<AddIcon />} disabled={selection.length > 0} onClick={handleClickOpen}>
                    {t('common.add')}
                </Button>
                <Button variant="outlined" startIcon={<EditIcon />} disabled={selection.length !== 1} onClick={handleEditClickOpen}>
                    {t('common.edit')}
                </Button>
                <Button 
                    variant="outlined" 
                    startIcon={<LockOpenIcon />} 
                    disabled={selection.length === 0 || !getSelectedUsersLockStatus()} 
                    onClick={handleUnlock}
                >
                    {t('users.unlock')} {t('common.selected')}
                </Button>
                <Button variant="outlined" startIcon={<DeleteIcon />} disabled={selection.length === 0} onClick={handleDelete}>
                    {t('common.delete')} {t('common.selected')}
                </Button>
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
                        doAddUser(true, formJson.email, formJson.password)
                        .then((result) => {
                            let newData: SysManageUser[] = [];
                            for (let i=0 ; i<tableData.length ; i++) {
                                newData.push(tableData[i]);
                            }
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
                    <Box component="section">&nbsp;</Box>
                    <TextField
                        required
                        fullWidth
                        margin="normal"
                        id="password"
                        name="password"
                        label={t('login.password')}
                        type="password"
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
                        
                        doUpdateUser(editUser.id, true, editEmail, editPassword)
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
                    <Box component="section">&nbsp;</Box>
                    <TextField
                        required
                        fullWidth
                        margin="normal"
                        id="password"
                        name="password"
                        label={t('login.password')}
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