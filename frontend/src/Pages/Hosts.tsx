import { useNavigate } from "react-router-dom";
import React, { useEffect, useState } from 'react';
import { DataGrid, GridColDef } from '@mui/x-data-grid';

import { SysManageHost, doGetHosts } from '../Services/hosts'

const columns: GridColDef[] = [
    { field: 'id', headerName: 'ID', width: 70 },
    { field: 'fqdn', headerName: 'Name', width: 200 },
    { field: 'ipv4', headerName: 'IP', width: 150 },
    { field: 'ipv6', headerName: 'IPv6', width: 200 }
]

const Hosts = () => {
    const [tableData, setTableData] = useState<SysManageHost[]>([]);
    const navigate = useNavigate();

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
    }, []);
    return (
        <div  style={{ height: 400, width: '100%' }}>
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
            />
        </div>
    );
}
 
export default Hosts;