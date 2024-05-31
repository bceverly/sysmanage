import { useNavigate } from "react-router-dom";
import React, { useEffect, useState } from 'react';
import { DataGrid, GridColDef, GridRowSelectionModel } from '@mui/x-data-grid';
import Box from '@mui/material/Box';
import Stack from '@mui/material/Stack';
import Button from '@mui/material/Button';
import AddIcon from '@mui/icons-material/Add';
import DeleteIcon from '@mui/icons-material/Delete';
import EditIcon from '@mui/icons-material/Edit';

import { SysManageUser, doGetUsers } from '../Services/users'

const columns: GridColDef[] = [
    { field: 'id', headerName: 'ID', width: 70 },
    { field: 'userid', headerName: 'Email Address', width: 200 }
]

const Users = () => {
    const [tableData, setTableData] = useState<SysManageUser[]>([]);
    const [selection, setSelection] = useState<GridRowSelectionModel>([]);
    const navigate = useNavigate();

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
                    }}
                    pageSizeOptions={[5, 10]}
                    checkboxSelection
                    onRowSelectionModelChange={setSelection}
                />
            </div>
            <Box component="section">&nbsp;</Box>
            <Stack direction="row" spacing={2}>
                <Button variant="outlined" startIcon={<AddIcon />} disabled={selection.length > 0}>
                    Add
                </Button>
                <Button variant="outlined" startIcon={<EditIcon />} disabled={selection.length === 0}>
                    Edit
                </Button>
                <Button variant="outlined" startIcon={<DeleteIcon />} disabled={selection.length === 0}>
                    Delete Selected
                </Button>
            </Stack>
        </div>
    );
}
 
export default Users;