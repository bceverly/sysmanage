import { useNavigate } from "react-router-dom";
import React, { useEffect, useState } from 'react';
import Stack from '@mui/material/Stack';
import { Gauge, gaugeClasses } from '@mui/x-charts/Gauge';
import Box from '@mui/material/Box';

import { SysManageHost, doGetHosts } from '../Services/hosts'
import { Typography } from "@mui/material";

const Dashboard = () => {
    const [numHosts, setNumHosts] = useState<number>();
    const navigate = useNavigate();

    useEffect(() => {
        if (!localStorage.getItem('bearer_token')) {
            navigate("/login");
        }
        doGetHosts().then((response: SysManageHost[]) => {
            setNumHosts(response.length);
            return Promise.resolve(response);
        });
    }, [navigate]);
    return (
        <Box
            height={225}
            width={225}
            sx={{ 
                border: '1px solid white',
                borderRadius: 3
             }}
        >
            <Typography align="center">
                Active Hosts
            </Typography>
            <Stack direction={{ xs: 'column', md: 'row' }} spacing={{ xs: 1, md: 3 }}>
                <Gauge width={200} height={200} value={numHosts} valueMin={0} valueMax={numHosts} 
                sx={(theme) => ({
                    [`& .${gaugeClasses.valueText}`] : {
                        fontSize: 40,
                    },
                    [`& .${gaugeClasses.valueArc}`]: {
                        fill: '#52b202',
                    },
                })}
                />
            </Stack>
        </Box>
    );
}
 
export default Dashboard;