import { useNavigate } from "react-router-dom";
import React, { useEffect, useState } from 'react';
import { DataGrid, GridColDef, GridRowSelectionModel } from '@mui/x-data-grid';
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

import { SysManageUser, doAddUser, doDeleteUser, doGetUsers } from '../Services/users'

const columns: GridColDef[] = [
    { field: 'id', headerName: 'ID', width: 70 },
    { field: 'userid', headerName: 'Email Address', width: 200 }
]

const Users = () => {
    const [tableData, setTableData] = useState<SysManageUser[]>([]);
    const [selection, setSelection] = useState<GridRowSelectionModel>([]);
    const [addDialogOpen, setAddDialogOpen] = useState(false);
    const navigate = useNavigate();

    const handleDelete = () => {
        // Call the API to remove the selected rows
        for (let i=0 ; i<selection.length ; i++) {
            let theID =  BigInt(selection[i].toString());
            doDeleteUser(theID);
        }

        // Remove the selected rows from the tableData
        let newArray: SysManageUser[] = [];
        for (let i=0 ; i<tableData.length ; i++) {
            let found = false;
            for (let j=0 ; j<selection.length ; j++) {
                if (tableData[i].id == BigInt(selection[j])) {
                    found = true;
                }
            }
            if (!found) {
                newArray.push(tableData[i]);
            }
        }
        setTableData(newArray);
    }

    const handleClickOpen = () => {
        setAddDialogOpen(true);
    };
    
      const handleClose = () => {
        setAddDialogOpen(false);
    };

    useEffect(() => {
        if (!localStorage.getItem('bearer_token')) {
            navigate("/login");
        }
        doGetUsers().then((response: SysManageUser[]) => {
            setTableData(response);
            console.log('Num users returned: ' + response.length);
            console.log("typeof(response): " + typeof response);
            for (let i=0 ; i<response.length ; i++) {
                console.log(response[i]);
            }
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
                    pageSizeOptions={[5, 10]}
                    checkboxSelection
                    onRowSelectionModelChange={setSelection}
                />
            </div>
            <Box component="section">&nbsp;</Box>
            <Stack direction="row" spacing={2}>
                <Button variant="outlined" startIcon={<AddIcon />} disabled={selection.length > 0} onClick={handleClickOpen}>
                    Add
                </Button>
                <Button variant="outlined" startIcon={<EditIcon />} disabled={selection.length === 0}>
                    Edit
                </Button>
                <Button variant="outlined" startIcon={<DeleteIcon />} disabled={selection.length === 0} onClick={handleDelete}>
                    Delete Selected
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
                        const formJson = Object.fromEntries((formData as any).entries());
                        const email = formJson.email;
                        const password = formJson.password;
                        console.log(email);
                        console.log(password);
                        doAddUser(true, email, password)
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
                            };
                            newData.push(newRow);
                            console.log('newRow.id = ' + newRow.id);
                            setTableData(newData);
                        });
                        handleClose();
                    },
                }}
            >
                <DialogTitle align="center">Add User</DialogTitle>
                <DialogContent>
                    <DialogContentText>
                        Enter the new user's information below.
                    </DialogContentText>
                    <Box component="section">&nbsp;</Box>
                    <TextField
                        autoFocus
                        required
                        fullWidth
                        margin="normal"
                        id="email"
                        name="email"
                        label="Email Address"
                        type="email"
                        variant="standard"
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
                        autoFocus
                        required
                        fullWidth
                        margin="normal"
                        id="password"
                        name="password"
                        label="Password"
                        type="password"
                        variant="standard"
                    />
                </DialogContent>
                <DialogActions>
                    <Button onClick={handleClose}>Cancel</Button>
                    <Button type="submit">Save</Button>
                </DialogActions>
            </Dialog>
        </div>
    );
}
 
export default Users;