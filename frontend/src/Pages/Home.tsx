import { useNavigate } from "react-router-dom";
import React, { useEffect, useState } from 'react';
import Stack from '@mui/material/Stack';
import { Gauge, gaugeClasses } from '@mui/x-charts/Gauge';
import Box from '@mui/material/Box';
import { useTranslation } from 'react-i18next';
import { Typography, Grid } from "@mui/material";

import { SysManageHost, doGetHosts } from '../Services/hosts'
import { updatesService, UpdateStatsSummary } from '../Services/updates';

const Dashboard = () => {
    const [hostsUp, setHostsUp] = useState<number>(0);
    const [hostsTotal, setHostsTotal] = useState<number>(0);
    const [hostStatusColor, setHostStatusColor] = useState<string>('#52b202'); // Default green
    const [hostsWithUpdates, setHostsWithUpdates] = useState<number>(0);
    const [updatesTotal, setUpdatesTotal] = useState<number>(0);
    const [updatesColor, setUpdatesColor] = useState<string>('#52b202'); // Default green
    const [securityUpdates, setSecurityUpdates] = useState<number>(0);
    const [securityColor, setSecurityColor] = useState<string>('#52b202'); // Default green
    const navigate = useNavigate();
    const { t } = useTranslation();

    useEffect(() => {
        if (!localStorage.getItem('bearer_token')) {
            navigate("/login");
        }
        
        // Fetch host data
        doGetHosts().then((response: SysManageHost[]) => {
            setHostsTotal(response.length);
            
            // Count hosts that are up
            const upHosts = response.filter(host => host.status === 'up').length;
            setHostsUp(upHosts);
            
            // Determine color based on host status
            const anyHostDown = response.some(host => host.status === 'down');
            if (anyHostDown) {
                setHostStatusColor('#ff1744'); // Red
            } else {
                setHostStatusColor('#52b202'); // Green
            }
            
            return Promise.resolve(response);
        });

        // Fetch updates data
        updatesService.getUpdatesSummary().then((summary: UpdateStatsSummary) => {
            setHostsWithUpdates(summary.hosts_with_updates);
            setUpdatesTotal(summary.total_updates);
            setSecurityUpdates(summary.security_updates);
            
            // Set colors based on counts
            setUpdatesColor(summary.hosts_with_updates > 0 ? '#ff1744' : '#52b202');
            setSecurityColor(summary.security_updates > 0 ? '#ff1744' : '#52b202');
        }).catch((error) => {
            console.error('Failed to fetch updates summary:', error);
            // Set defaults on error
            setHostsWithUpdates(0);
            setUpdatesTotal(0);
            setSecurityUpdates(0);
        });
    }, [navigate]);

    const handleHostsClick = () => {
        navigate('/hosts');
    };

    const handleUpdatesClick = () => {
        navigate('/updates');
    };

    const handleSecurityClick = () => {
        // Navigate to updates page with security filter pre-selected
        navigate('/updates?securityOnly=true');
    };

    const DashboardCard = ({ title, value, maxValue, color, onClick }: {
        title: string;
        value: number;
        maxValue: number;
        color: string;
        onClick: () => void;
    }) => (
        <Box
            height={250}
            width={250}
            onClick={onClick}
            sx={{ 
                border: '1px solid white',
                borderRadius: 3,
                cursor: 'pointer',
                '&:hover': {
                    backgroundColor: 'rgba(255, 255, 255, 0.1)',
                    borderColor: '#90caf9',
                },
                transition: 'background-color 0.2s, border-color 0.2s',
                padding: 2
            }}
        >
            <Typography align="center" variant="h5" sx={{ mb: 1 }}>
                {title}
            </Typography>
            <Stack direction={{ xs: 'column', md: 'row' }} spacing={{ xs: 1, md: 3 }} alignItems="center">
                <Gauge 
                    width={200} 
                    height={180} 
                    value={value} 
                    valueMin={0} 
                    valueMax={maxValue} 
                    sx={(_theme) => ({
                        [`& .${gaugeClasses.valueText}`]: {
                            fontSize: 40,
                        },
                        [`& .${gaugeClasses.valueArc}`]: {
                            fill: color,
                        },
                    })}
                />
            </Stack>
        </Box>
    );

    return (
        <Grid container spacing={3} sx={{ mt: 2 }}>
            <Grid item>
                <DashboardCard
                    title={t('dashboard.hosts')}
                    value={hostsUp}
                    maxValue={hostsTotal || 1} // Prevent division by zero
                    color={hostStatusColor}
                    onClick={handleHostsClick}
                />
            </Grid>
            <Grid item>
                <DashboardCard
                    title={t('dashboard.updates')}
                    value={hostsWithUpdates}
                    maxValue={hostsTotal || 1}
                    color={updatesColor}
                    onClick={handleUpdatesClick}
                />
            </Grid>
            <Grid item>
                <DashboardCard
                    title={t('dashboard.security')}
                    value={securityUpdates}
                    maxValue={updatesTotal || 1}
                    color={securityColor}
                    onClick={handleSecurityClick}
                />
            </Grid>
        </Grid>
    );
}
 
export default Dashboard;