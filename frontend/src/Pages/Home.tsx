import { useNavigate } from "react-router-dom";
import React, { useEffect, useState } from 'react';
import Stack from '@mui/material/Stack';
import { Gauge, gaugeClasses } from '@mui/x-charts/Gauge';
import Box from '@mui/material/Box';
import { useTranslation } from 'react-i18next';

import { SysManageHost, doGetHosts } from '../Services/hosts'
import { Typography } from "@mui/material";

const Dashboard = () => {
    const [numHosts, setNumHosts] = useState<number>();
    const [hostStatusColor, setHostStatusColor] = useState<string>('#52b202'); // Default green
    const navigate = useNavigate();
    const { t } = useTranslation();

    useEffect(() => {
        if (!localStorage.getItem('bearer_token')) {
            navigate("/login");
        }
        doGetHosts().then((response: SysManageHost[]) => {
            setNumHosts(response.length);
            
            // Determine color based on host status
            const anyHostDown = response.some(host => host.status === 'down');
            if (anyHostDown) {
                setHostStatusColor('#ff1744'); // Red
            } else {
                setHostStatusColor('#52b202'); // Green
            }
            
            return Promise.resolve(response);
        });
    }, [navigate]);
    const handleHostsClick = () => {
        navigate('/hosts');
    };

    return (
        <Box
            height={250}
            width={250}
            onClick={handleHostsClick}
            sx={{ 
                border: '1px solid white',
                borderRadius: 3,
                cursor: 'pointer',
                '&:hover': {
                    backgroundColor: 'rgba(255, 255, 255, 0.1)',
                    borderColor: '#90caf9',
                },
                transition: 'background-color 0.2s, border-color 0.2s'
             }}
        >
            <Typography align="center" variant="h5">
                {t('dashboard.hosts')}
            </Typography>
            <Stack direction={{ xs: 'column', md: 'row' }} spacing={{ xs: 1, md: 3 }}>
                <Gauge width={200} height={200} value={numHosts} valueMin={0} valueMax={numHosts} 
                sx={(_theme) => ({
                    [`& .${gaugeClasses.valueText}`] : {
                        fontSize: 40,
                    },
                    [`& .${gaugeClasses.valueArc}`]: {
                        fill: hostStatusColor,
                    },
                })}
                />
            </Stack>
        </Box>
    );
}
 
export default Dashboard;