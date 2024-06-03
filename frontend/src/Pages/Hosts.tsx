import { useNavigate } from "react-router-dom";
import React, { useEffect, useState } from 'react';
import { DataGrid, GridColDef, GridRowSelectionModel } from '@mui/x-data-grid';
import Box from '@mui/material/Box';
import Stack from '@mui/material/Stack';
import Button from '@mui/material/Button';
import DeleteIcon from '@mui/icons-material/Delete';

import { SysManageHost, doDeleteHost, doGetHosts } from '../Services/hosts'

const columns: GridColDef[] = [
    { field: 'id', headerName: 'ID', width: 70 },
    { field: 'fqdn', headerName: 'Name', width: 200 },
    { field: 'ipv4', headerName: 'IP', width: 150 },
    { field: 'ipv6', headerName: 'IPv6', width: 200 }
]

const Hosts = () => {
    const [tableData, setTableData] = useState<SysManageHost[]>([]);
    const [selection, setSelection] = useState<GridRowSelectionModel>([]);
    const navigate = useNavigate();

    const handleDelete = () => {
        // Call the API to remove the selected rows
        for (let i=0 ; i<selection.length ; i++) {
            let theID =  BigInt(selection[i].toString());
            doDeleteHost(theID);
        }

        // Remove the selected rows from the tableData
        let newArray: SysManageHost[] = [];
        for (let i=0 ; i<tableData.length ; i++) {
            let found = false;
            for (let j=0 ; j<selection.length ; j++) {
                if (tableData[i].id === BigInt(selection[j])) {
                    found = true;
                }
            }
            if (!found) {
                newArray.push(tableData[i]);
            }
        }
        setTableData(newArray);
    }

    useEffect(() => {
        if (!localStorage.getItem('bearer_token')) {
            navigate("/login");
        }
        doGetHosts().then((response: SysManageHost[]) => {
            setTableData(response);
            console.log('Num hosts returned: ' + response.length);
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
                            sortModel: [{ field: 'fqdn', sort: 'asc'}],
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
                <Button variant="outlined" startIcon={<DeleteIcon />} disabled={selection.length === 0} onClick={handleDelete}>
                    Delete Selected
                </Button>
            </Stack>
        </div>
    );
}
 
export default Hosts;