import { useNavigate } from "react-router-dom";
import React, { useEffect, useState } from 'react';
import Stack from '@mui/material/Stack';
import { Gauge, gaugeClasses } from '@mui/x-charts/Gauge';
import Box from '@mui/material/Box';
import { useTranslation } from 'react-i18next';
import { Typography, Grid, Skeleton, CircularProgress, IconButton } from "@mui/material";
import { Settings as SettingsIcon } from '@mui/icons-material';

import { doGetHosts } from '../Services/hosts'
import { updatesService } from '../Services/updates';
import axiosInstance from '../Services/api';
import DashboardSettingsDialog from '../Components/DashboardSettingsDialog';

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
    const [antivirusCoverage, setAntivirusCoverage] = useState<number>(0);
    const [antivirusColor, setAntivirusColor] = useState<string>('#52b202'); // Default green
    const [otelCoverage, setOtelCoverage] = useState<number>(0);
    const [otelColor, setOtelColor] = useState<string>('#52b202'); // Default green
    const [loading, setLoading] = useState<boolean>(true);
    const [settingsOpen, setSettingsOpen] = useState(false);
    const [cardVisibility, setCardVisibility] = useState<Record<string, boolean>>({
        hosts: true,
        updates: true,
        security: true,
        reboot: true,
        antivirus: true,
        opentelemetry: true,
    });
    const navigate = useNavigate();
    const { t } = useTranslation();

    const fetchData = async (isInitialLoad = false) => {
        // Only show loading state on initial load, not on refresh
        if (isInitialLoad) {
            setLoading(true);
        }

        try {
            // Fetch hosts, updates, antivirus coverage, and OpenTelemetry coverage data in parallel
            const [hostsResponse, updatesResponse, antivirusResponse, otelResponse] = await Promise.allSettled([
                doGetHosts(),
                updatesService.getUpdatesSummary(),
                axiosInstance.get('/api/antivirus-coverage'),
                axiosInstance.get('/api/opentelemetry/opentelemetry-coverage')
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

            // Process antivirus coverage data
            if (antivirusResponse.status === 'fulfilled') {
                const coverage = antivirusResponse.value.data;
                const coveragePercentage = coverage.coverage_percentage;
                setAntivirusCoverage(Math.round(coveragePercentage));

                // Set color based on coverage: green >= 80%, yellow >= 50%, red < 50%
                if (coveragePercentage >= 80) {
                    setAntivirusColor('#52b202');
                } else if (coveragePercentage >= 50) {
                    setAntivirusColor('#ff9800');
                } else {
                    setAntivirusColor('#ff1744');
                }
            } else {
                console.error('Failed to fetch antivirus coverage:', antivirusResponse.reason);
                // Keep defaults (0) on error
            }

            // Process OpenTelemetry coverage data
            if (otelResponse.status === 'fulfilled') {
                const coverage = otelResponse.value.data;
                const coveragePercentage = coverage.coverage_percentage;
                setOtelCoverage(Math.round(coveragePercentage));

                // Set color based on coverage: green >= 80%, yellow >= 50%, red < 50%
                if (coveragePercentage >= 80) {
                    setOtelColor('#52b202');
                } else if (coveragePercentage >= 50) {
                    setOtelColor('#ff9800');
                } else {
                    setOtelColor('#ff1744');
                }
            } else {
                console.error('Failed to fetch OpenTelemetry coverage:', otelResponse.reason);
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

    const loadCardPreferences = async () => {
        try {
            const response = await axiosInstance.get('/api/user-preferences/dashboard-cards');
            const prefs = response.data.preferences || [];
            const visibilityMap: Record<string, boolean> = {
                hosts: true,
                updates: true,
                security: true,
                reboot: true,
                antivirus: true,
                opentelemetry: true,
            };

            // Apply saved preferences
            if (Array.isArray(prefs)) {
                prefs.forEach((pref: { card_identifier: string; visible: boolean }) => {
                    visibilityMap[pref.card_identifier] = pref.visible;
                });
            }

            setCardVisibility(visibilityMap);
        } catch (error) {
            console.error('Error loading card preferences:', error);
            // Keep defaults on error
        }
    };

    useEffect(() => {
        if (!localStorage.getItem('bearer_token')) {
            navigate("/login");
            return;
        }

        // Load card preferences
        loadCardPreferences();

        // Initial data fetch
        fetchData(true);

        // Set up auto-refresh every 30 seconds
        const refreshInterval = setInterval(() => {
            fetchData(false);
        }, 30000);

        // Cleanup interval on component unmount
        return () => {
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

    const handleAntivirusClick = () => {
        // Navigate to hosts page
        navigate('/hosts');
    };

    const handleOtelClick = () => {
        // Navigate to hosts page
        navigate('/hosts');
    };

    const handleSaveSettings = (cards: { identifier: string; visible: boolean }[]) => {
        const visibilityMap: Record<string, boolean> = {};
        cards.forEach((card) => {
            visibilityMap[card.identifier] = card.visible;
        });
        setCardVisibility(visibilityMap);
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
        <Box>
            <Box sx={{ display: 'flex', justifyContent: 'flex-end', mb: 2 }}>
                <IconButton
                    onClick={() => setSettingsOpen(true)}
                    color="primary"
                    aria-label={t('dashboard.settings.title', 'Dashboard Settings')}
                >
                    <SettingsIcon />
                </IconButton>
            </Box>

            <Grid container spacing={3}>
                {cardVisibility.hosts && (
                    <Grid>
                        <DashboardCard
                            title={t('dashboard.hosts')}
                            value={hostsTotal}
                            maxValue={hostsTotal || 1}
                            color={hostStatusColor}
                            onClick={handleHostsClick}
                            loading={loading}
                        />
                    </Grid>
                )}
                {cardVisibility.updates && (
                    <Grid>
                        <DashboardCard
                            title={t('dashboard.updates')}
                            value={hostsWithUpdates}
                            maxValue={hostsTotal || 1}
                            color={updatesColor}
                            onClick={handleUpdatesClick}
                            loading={loading}
                        />
                    </Grid>
                )}
                {cardVisibility.security && (
                    <Grid>
                        <DashboardCard
                            title={t('dashboard.security')}
                            value={securityUpdates}
                            maxValue={updatesTotal || 1}
                            color={securityColor}
                            onClick={handleSecurityClick}
                            loading={loading}
                        />
                    </Grid>
                )}
                {cardVisibility.reboot && (
                    <Grid>
                        <DashboardCard
                            title={t('dashboard.rebootRequired')}
                            value={rebootRequired}
                            maxValue={hostsTotal || 1}
                            color={rebootColor}
                            onClick={handleRebootClick}
                            loading={loading}
                        />
                    </Grid>
                )}
                {cardVisibility.antivirus && (
                    <Grid>
                        <DashboardCard
                            title={t('dashboard.antivirusCoverage')}
                            value={antivirusCoverage}
                            maxValue={100}
                            color={antivirusColor}
                            onClick={handleAntivirusClick}
                            loading={loading}
                        />
                    </Grid>
                )}
                {cardVisibility.opentelemetry && (
                    <Grid>
                        <DashboardCard
                            title={t('dashboard.openTelemetryCoverage')}
                            value={otelCoverage}
                            maxValue={100}
                            color={otelColor}
                            onClick={handleOtelClick}
                            loading={loading}
                        />
                    </Grid>
                )}
            </Grid>

            <DashboardSettingsDialog
                open={settingsOpen}
                onClose={() => setSettingsOpen(false)}
                onSave={handleSaveSettings}
            />
        </Box>
    );
}
 
export default Dashboard;