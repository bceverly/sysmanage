import { useNavigate } from "react-router-dom";
import React, { useEffect, useState } from 'react';
import Stack from '@mui/material/Stack';
import { Gauge, gaugeClasses } from '@mui/x-charts/Gauge';
import Box from '@mui/material/Box';
import { useTranslation } from 'react-i18next';
import { Typography, Grid, Skeleton, CircularProgress } from "@mui/material";

import { doGetHosts } from '../Services/hosts'
import { updatesService } from '../Services/updates';

const Dashboard = () => {
    const [hostsTotal, setHostsTotal] = useState<number>(0);
    const [hostStatusColor, setHostStatusColor] = useState<string>('#52b202'); // Default green
    const [hostsWithUpdates, setHostsWithUpdates] = useState<number>(0);
    const [updatesTotal, setUpdatesTotal] = useState<number>(0);
    const [updatesColor, setUpdatesColor] = useState<string>('#52b202'); // Default green
    const [securityUpdates, setSecurityUpdates] = useState<number>(0);
    const [securityColor, setSecurityColor] = useState<string>('#52b202'); // Default green
    const [rebootRequired, setRebootRequired] = useState<number>(0);
    const [rebootColor, setRebootColor] = useState<string>('#52b202'); // Default green
    const [loading, setLoading] = useState<boolean>(true);
    const navigate = useNavigate();
    const { t } = useTranslation();

    const fetchData = async (isInitialLoad = false) => {
        // Only show loading state on initial load, not on refresh
        if (isInitialLoad) {
            setLoading(true);
        }

        try {
            // Fetch both hosts and updates data in parallel
            const [hostsResponse, updatesResponse] = await Promise.allSettled([
                doGetHosts(),
                updatesService.getUpdatesSummary()
            ]);

            // Process hosts data
            if (hostsResponse.status === 'fulfilled') {
                const hosts = hostsResponse.value;
                setHostsTotal(hosts.length);

                // Determine color based on host status - only consider approved hosts
                const approvedHosts = hosts.filter(host => host.approval_status === 'approved');
                const approvedHostsUp = approvedHosts.filter(host => host.status === 'up').length;
                const approvedHostsDown = approvedHosts.filter(host => host.status === 'down').length;

                if (approvedHosts.length === 0) {
                    setHostStatusColor('#52b202'); // Green if no approved hosts
                } else if (approvedHostsDown === approvedHosts.length) {
                    setHostStatusColor('#ff1744'); // Red - all approved hosts are down
                } else if (approvedHostsUp > 0 && approvedHostsDown > 0) {
                    setHostStatusColor('#ff9800'); // Yellow - mixed up/down
                } else {
                    setHostStatusColor('#52b202'); // Green - all approved hosts are up
                }

                // Calculate reboot required statistics
                const hostsRequiringReboot = hosts.filter(host =>
                    host.approval_status === 'approved' && host.reboot_required
                ).length;
                setRebootRequired(hostsRequiringReboot);
                setRebootColor(hostsRequiringReboot > 0 ? '#ff1744' : '#52b202'); // Red if any, green if none
            }

            // Process updates data
            if (updatesResponse.status === 'fulfilled') {
                const summary = updatesResponse.value;
                setHostsWithUpdates(summary.hosts_with_updates);
                setUpdatesTotal(summary.total_updates);
                setSecurityUpdates(summary.security_updates);

                // Set colors based on counts
                setUpdatesColor(summary.hosts_with_updates > 0 ? '#ff1744' : '#52b202');
                setSecurityColor(summary.security_updates > 0 ? '#ff1744' : '#52b202');
            } else {
                console.error('Failed to fetch updates summary:', updatesResponse.reason);
                // Keep defaults (0) on error
            }
        } catch (error) {
            console.error('Error fetching dashboard data:', error);
        } finally {
            if (isInitialLoad) {
                setLoading(false);
            }
        }
    };

    useEffect(() => {
        if (!localStorage.getItem('bearer_token')) {
            navigate("/login");
            return;
        }

        // Initial data fetch
        fetchData(true);

        // Set up auto-refresh every 30 seconds
        // eslint-disable-next-line no-undef
        const refreshInterval = setInterval(() => {
            fetchData(false);
        }, 30000);

        // Cleanup interval on component unmount
        return () => {
            // eslint-disable-next-line no-undef
            clearInterval(refreshInterval);
        };
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

    const handleRebootClick = () => {
        // Navigate to hosts page to show hosts requiring reboot
        navigate('/hosts');
    };

    const DashboardCard = ({ title, value, maxValue, color, onClick, loading }: {
        title: string;
        value: number;
        maxValue: number;
        color: string;
        onClick: () => void;
        loading?: boolean;
    }) => (
        <Box
            height={250}
            width={250}
            onClick={loading ? undefined : onClick}
            sx={{
                border: '1px solid white',
                borderRadius: 3,
                cursor: loading ? 'default' : 'pointer',
                '&:hover': loading ? {} : {
                    backgroundColor: 'rgba(255, 255, 255, 0.1)',
                    borderColor: '#90caf9',
                },
                transition: 'background-color 0.2s, border-color 0.2s',
                padding: 2
            }}
        >
            <Typography align="center" variant="h5" sx={{ mb: 1 }}>
                {loading ? <Skeleton width="80%" /> : title}
            </Typography>
            <Stack direction={{ xs: 'column', md: 'row' }} spacing={{ xs: 1, md: 3 }} alignItems="center">
                {loading ? (
                    <Box display="flex" justifyContent="center" alignItems="center" width={200} height={180}>
                        <CircularProgress size={60} />
                    </Box>
                ) : (
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
                )}
            </Stack>
        </Box>
    );

    return (
        <Grid container spacing={3} sx={{ mt: 2 }}>
            <Grid item>
                <DashboardCard
                    title={t('dashboard.hosts')}
                    value={hostsTotal}
                    maxValue={hostsTotal || 1} // Prevent division by zero
                    color={hostStatusColor}
                    onClick={handleHostsClick}
                    loading={loading}
                />
            </Grid>
            <Grid item>
                <DashboardCard
                    title={t('dashboard.updates')}
                    value={hostsWithUpdates}
                    maxValue={hostsTotal || 1}
                    color={updatesColor}
                    onClick={handleUpdatesClick}
                    loading={loading}
                />
            </Grid>
            <Grid item>
                <DashboardCard
                    title={t('dashboard.security')}
                    value={securityUpdates}
                    maxValue={updatesTotal || 1}
                    color={securityColor}
                    onClick={handleSecurityClick}
                    loading={loading}
                />
            </Grid>
            <Grid item>
                <DashboardCard
                    title={t('dashboard.rebootRequired')}
                    value={rebootRequired}
                    maxValue={hostsTotal || 1}
                    color={rebootColor}
                    onClick={handleRebootClick}
                    loading={loading}
                />
            </Grid>
        </Grid>
    );
}
 
export default Dashboard;