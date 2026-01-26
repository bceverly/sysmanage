import { useNavigate } from "react-router-dom";
import React, { useEffect, useState, useCallback } from 'react';
import Stack from '@mui/material/Stack';
import { Gauge, gaugeClasses } from '@mui/x-charts/Gauge';
import Box from '@mui/material/Box';
import { useTranslation } from 'react-i18next';
import { Typography, Grid, Skeleton, CircularProgress, IconButton } from "@mui/material";
import { Settings as SettingsIcon } from '@mui/icons-material';
import { AxiosResponse } from 'axios';

import { doGetHosts, SysManageHost } from '../Services/hosts'
import { updatesService, UpdateStatsSummary } from '../Services/updates';
import axiosInstance from '../Services/api';
import DashboardSettingsDialog from '../Components/DashboardSettingsDialog';

interface DashboardCardProps {
    title: string;
    value: number;
    maxValue: number;
    color: string;
    onClick: () => void;
    loading?: boolean;
}

// Color constants
const COLOR_GREEN = '#52b202';
const COLOR_YELLOW = '#ff9800';
const COLOR_RED = '#ff1744';

// Helper function to determine host status color based on approved hosts
const getHostStatusColor = (hosts: SysManageHost[]): string => {
    const approvedHosts = hosts.filter(host => host.approval_status === 'approved');
    if (approvedHosts.length === 0) {
        return COLOR_GREEN;
    }

    const approvedHostsUp = approvedHosts.filter(host => host.status === 'up').length;
    const approvedHostsDown = approvedHosts.filter(host => host.status === 'down').length;

    if (approvedHostsDown === approvedHosts.length) {
        return COLOR_RED; // All approved hosts are down
    }
    if (approvedHostsUp > 0 && approvedHostsDown > 0) {
        return COLOR_YELLOW; // Mixed up/down
    }
    return COLOR_GREEN; // All approved hosts are up
};

// Helper function to determine color based on coverage percentage thresholds
const getCoverageColor = (coveragePercentage: number): string => {
    if (coveragePercentage >= 80) {
        return COLOR_GREEN;
    }
    if (coveragePercentage >= 50) {
        return COLOR_YELLOW;
    }
    return COLOR_RED;
};

const DashboardCard: React.FC<DashboardCardProps> = ({
    title,
    value,
    maxValue,
    color,
    onClick,
    loading = false,
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

const Dashboard = () => {
    const [hostsTotal, setHostsTotal] = useState<number>(0);
    const [hostStatusColor, setHostStatusColor] = useState<string>(COLOR_GREEN);
    const [hostsWithUpdates, setHostsWithUpdates] = useState<number>(0);
    const [updatesTotal, setUpdatesTotal] = useState<number>(0);
    const [updatesColor, setUpdatesColor] = useState<string>(COLOR_GREEN);
    const [securityUpdates, setSecurityUpdates] = useState<number>(0);
    const [securityColor, setSecurityColor] = useState<string>(COLOR_GREEN);
    const [rebootRequired, setRebootRequired] = useState<number>(0);
    const [rebootColor, setRebootColor] = useState<string>(COLOR_GREEN);
    const [antivirusCoverage, setAntivirusCoverage] = useState<number>(0);
    const [antivirusColor, setAntivirusColor] = useState<string>(COLOR_GREEN);
    const [otelCoverage, setOtelCoverage] = useState<number>(0);
    const [otelColor, setOtelColor] = useState<string>(COLOR_GREEN);
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

    const processHostsResponse = (hostsResponse: PromiseSettledResult<SysManageHost[]>) => {
        if (hostsResponse.status !== 'fulfilled') {
            return;
        }

        const hosts = hostsResponse.value;
        setHostsTotal(hosts.length);
        setHostStatusColor(getHostStatusColor(hosts));

        // Calculate reboot required statistics
        const hostsRequiringReboot = hosts.filter(
            (host: SysManageHost) => host.approval_status === 'approved' && host.reboot_required
        ).length;
        setRebootRequired(hostsRequiringReboot);
        setRebootColor(hostsRequiringReboot > 0 ? COLOR_RED : COLOR_GREEN);
    };

    const processUpdatesResponse = (updatesResponse: PromiseSettledResult<UpdateStatsSummary>) => {
        if (updatesResponse.status !== 'fulfilled') {
            console.error('Failed to fetch updates summary:', (updatesResponse as PromiseRejectedResult).reason);
            return;
        }

        const summary = updatesResponse.value;
        setHostsWithUpdates(summary.hosts_with_updates);
        setUpdatesTotal(summary.total_updates);
        setSecurityUpdates(summary.security_updates);
        setUpdatesColor(summary.hosts_with_updates > 0 ? COLOR_RED : COLOR_GREEN);
        setSecurityColor(summary.security_updates > 0 ? COLOR_RED : COLOR_GREEN);
    };

    const processCoverageResponse = (
        response: PromiseSettledResult<AxiosResponse<{ coverage_percentage: number }>>,
        setCoverage: (value: number) => void,
        setColor: (value: string) => void,
        errorMessage: string
    ) => {
        if (response.status !== 'fulfilled') {
            console.error(errorMessage, (response as PromiseRejectedResult).reason);
            return;
        }

        const coveragePercentage = response.value.data.coverage_percentage;
        setCoverage(Math.round(coveragePercentage));
        setColor(getCoverageColor(coveragePercentage));
    };

    const fetchData = useCallback(async (isInitialLoad = false) => {
        if (isInitialLoad) {
            setLoading(true);
        }

        try {
            const [hostsResponse, updatesResponse, antivirusResponse, otelResponse] = await Promise.allSettled([
                doGetHosts(),
                updatesService.getUpdatesSummary(),
                axiosInstance.get('/api/antivirus-coverage'),
                axiosInstance.get('/api/opentelemetry/opentelemetry-coverage')
            ]);

            processHostsResponse(hostsResponse);
            processUpdatesResponse(updatesResponse);
            processCoverageResponse(antivirusResponse, setAntivirusCoverage, setAntivirusColor, 'Failed to fetch antivirus coverage:');
            processCoverageResponse(otelResponse, setOtelCoverage, setOtelColor, 'Failed to fetch OpenTelemetry coverage:');
        } catch (error) {
            console.error('Error fetching dashboard data:', error);
        } finally {
            if (isInitialLoad) {
                setLoading(false);
            }
        }
    }, []);

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
    }, [navigate, fetchData]);

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