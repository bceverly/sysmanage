import { useNavigate, useParams } from "react-router-dom";
import React, { useEffect, useState } from 'react';
import { 
    Box, 
    Card, 
    CardContent, 
    Typography, 
    Grid, 
    Chip,
    Button,
    CircularProgress,
    Paper,
    LinearProgress
} from '@mui/material';
import ArrowBackIcon from '@mui/icons-material/ArrowBack';
import ComputerIcon from '@mui/icons-material/Computer';
import InfoIcon from '@mui/icons-material/Info';
import MemoryIcon from '@mui/icons-material/Memory';
import StorageIcon from '@mui/icons-material/Storage';
import NetworkCheckIcon from '@mui/icons-material/NetworkCheck';
import HelpOutlineIcon from '@mui/icons-material/HelpOutline';
import CloseIcon from '@mui/icons-material/Close';
import { Dialog, DialogTitle, DialogContent, IconButton, Table, TableBody, TableRow, TableCell, ToggleButton, ToggleButtonGroup } from '@mui/material';
import { useTranslation } from 'react-i18next';

import { SysManageHost, StorageDevice as StorageDeviceType, NetworkInterface as NetworkInterfaceType, doGetHostByID, doGetHostStorage, doGetHostNetwork } from '../Services/hosts';

// Use the service types directly - no need for local interfaces anymore

const HostDetail = () => {
    const { hostId } = useParams<{ hostId: string }>();
    const [host, setHost] = useState<SysManageHost | null>(null);
    const [storageDevices, setStorageDevices] = useState<StorageDeviceType[]>([]);
    const [networkInterfaces, setNetworkInterfaces] = useState<NetworkInterfaceType[]>([]);
    const [loading, setLoading] = useState<boolean>(true);
    const [error, setError] = useState<string | null>(null);
    const [storageFilter, setStorageFilter] = useState<'all' | 'physical' | 'logical'>('physical');
    const [dialogOpen, setDialogOpen] = useState<boolean>(false);
    const [dialogContent, setDialogContent] = useState<string>('');
    const [dialogTitle, setDialogTitle] = useState<string>('');
    const navigate = useNavigate();
    const { t } = useTranslation();

    useEffect(() => {
        if (!localStorage.getItem('bearer_token')) {
            navigate("/login");
            return;
        }

        if (!hostId) {
            setError(t('hostDetail.invalidId', 'Invalid host ID'));
            setLoading(false);
            return;
        }

        const fetchHost = async () => {
            try {
                setLoading(true);
                const hostData = await doGetHostByID(BigInt(hostId));
                setHost(hostData);
                
                // Fetch normalized storage and network data
                try {
                    const [storageData, networkData] = await Promise.all([
                        doGetHostStorage(BigInt(hostId)),
                        doGetHostNetwork(BigInt(hostId))
                    ]);
                    
                    // If normalized data is empty, try to parse JSON fallback data
                    if (storageData.length === 0 && hostData.storage_details) {
                        try {
                            const legacyStorageData = JSON.parse(hostData.storage_details);
                            setStorageDevices(legacyStorageData);
                        } catch (parseErr) {
                            console.warn('Failed to parse legacy storage data:', parseErr);
                        }
                    } else {
                        setStorageDevices(storageData);
                    }
                    
                    if (networkData.length === 0 && hostData.network_details) {
                        try {
                            const legacyNetworkData = JSON.parse(hostData.network_details);
                            setNetworkInterfaces(legacyNetworkData);
                        } catch (parseErr) {
                            console.warn('Failed to parse legacy network data:', parseErr);
                        }
                    } else {
                        setNetworkInterfaces(networkData);
                    }
                } catch (hardwareErr) {
                    // Log but don't fail the whole request - hardware data is optional
                    console.warn('Failed to fetch hardware data:', hardwareErr);
                }
                
                setError(null);
            } catch (err) {
                console.error('Error fetching host:', err);
                setError(t('hostDetail.loadError', 'Failed to load host details'));
            } finally {
                setLoading(false);
            }
        };

        fetchHost();
    }, [hostId, navigate, t]);

    const formatDate = (dateString: string | undefined) => {
        if (!dateString) return t('common.notAvailable', 'N/A');
        try {
            const date = new Date(dateString);
            return date.toLocaleString();
        } catch {
            return t('common.invalidDate', 'Invalid date');
        }
    };

    const getStatusColor = (status: string) => {
        return status === 'up' ? 'success' : 'error';
    };

    const getApprovalStatusColor = (status: string) => {
        switch (status) {
            case 'approved': return 'success';
            case 'pending': return 'warning';
            case 'rejected': return 'error';
            case 'revoked': return 'error';
            default: return 'default';
        }
    };

    const formatMemorySize = (mb: number | undefined) => {
        if (!mb) return t('common.notAvailable');
        if (mb >= 1024) {
            return `${(mb / 1024).toFixed(1)} GB`;
        }
        return `${mb} MB`;
    };

    const formatCpuFrequency = (mhz: number | undefined) => {
        if (!mhz) return t('common.notAvailable');
        if (mhz >= 1000) {
            return `${(mhz / 1000).toFixed(1)} GHz`;
        }
        return `${mhz} MHz`;
    };


    const handleShowDialog = (title: string, content: string) => {
        setDialogTitle(title);
        setDialogContent(content);
        setDialogOpen(true);
    };

    const handleCloseDialog = () => {
        setDialogOpen(false);
        setDialogContent('');
        setDialogTitle('');
    };

    // Utility function to format bytes with appropriate units
    const formatBytesWithCommas = (bytes?: number): string => {
        if (!bytes || bytes === 0) return t('common.notAvailable');
        
        const units = ['B', 'KB', 'MB', 'GB', 'TB'];
        let size = bytes;
        let unitIndex = 0;
        
        while (size >= 1024 && unitIndex < units.length - 1) {
            size /= 1024;
            unitIndex++;
        }
        
        const formattedSize = size.toLocaleString(undefined, { 
            maximumFractionDigits: unitIndex === 0 ? 0 : 1 
        });
        
        return `${formattedSize} ${units[unitIndex]}`;
    };

    // Utility function to calculate and format capacity with percentage free
    const formatCapacityWithFree = (capacity?: number, used?: number, available?: number): string => {
        if (!capacity || capacity === 0) return t('common.notAvailable');
        
        const capacityFormatted = formatBytesWithCommas(capacity);
        
        if (available !== undefined && available !== null) {
            const freePercentage = Math.round((available / capacity) * 100);
            return `${capacityFormatted} (${freePercentage}% free)`;
        } else if (used !== undefined && used !== null) {
            const freeBytes = capacity - used;
            const freePercentage = Math.round((freeBytes / capacity) * 100);
            return `${capacityFormatted} (${freePercentage}% free)`;
        }
        
        return capacityFormatted;
    };

    // Utility function to calculate usage percentage for storage bars
    const getStorageUsagePercentage = (capacity?: number, used?: number, available?: number): number => {
        if (!capacity || capacity === 0) return 0;
        
        // Prefer available bytes calculation for consistency with the text display
        // This accounts for filesystem overhead and ensures text and bar match
        if (available !== undefined && available !== null) {
            const usedPercentage = Math.min(Math.max(((capacity - available) / capacity) * 100, 0), 100);
            return usedPercentage;
        } else if (used !== undefined && used !== null) {
            return Math.min(Math.max((used / capacity) * 100, 0), 100);
        }
        
        return 0;
    };

    // Utility function to get color based on storage usage percentage
    const getStorageUsageColor = (usagePercentage: number): 'success' | 'warning' | 'error' => {
        if (usagePercentage < 70) return 'success';     // Green: lots of free space
        if (usagePercentage < 90) return 'warning';     // Amber: getting full
        return 'error';                                 // Red: scary close to full or full
    };

    // Utility function to deduplicate storage devices by name, preferring root mounts
    const deduplicateStorageDevices = (devices: StorageDeviceType[]): StorageDeviceType[] => {
        const devicesByName = new Map<string, StorageDeviceType[]>();
        
        // Group devices by name
        devices.forEach(device => {
            if (!devicesByName.has(device.name)) {
                devicesByName.set(device.name, []);
            }
            devicesByName.get(device.name)!.push(device);
        });
        
        // For each name, select the best representative device
        const deduplicatedDevices: StorageDeviceType[] = [];
        devicesByName.forEach((deviceGroup) => {
            if (deviceGroup.length === 1) {
                // Only one device with this name, keep it
                deduplicatedDevices.push(deviceGroup[0]);
            } else {
                // Multiple devices with same name, prioritize by mount point
                // Priority: root (/), then system volumes, then others
                const prioritized = deviceGroup.sort((a, b) => {
                    const aMountPriority = getMountPointPriority(a.mount_point);
                    const bMountPriority = getMountPointPriority(b.mount_point);
                    return aMountPriority - bMountPriority;
                });
                
                deduplicatedDevices.push(prioritized[0]);
            }
        });
        
        return deduplicatedDevices;
    };
    
    // Helper function to assign priority to mount points (lower = higher priority)
    const getMountPointPriority = (mountPoint: string): number => {
        if (mountPoint === '/') return 1;                           // Root - highest priority
        if (mountPoint.includes('/System/Volumes')) return 3;      // System volumes - lower priority
        if (mountPoint.includes('/Library')) return 4;             // Library volumes - even lower
        return 2;                                                   // Other mounts - medium priority
    };

    // Filter storage devices based on physical/logical selection
    const getFilteredStorageDevices = (devices: StorageDeviceType[]): StorageDeviceType[] => {
        const deduplicatedDevices = deduplicateStorageDevices(devices);
        
        switch (storageFilter) {
            case 'physical':
                return deduplicatedDevices.filter(device => device.is_physical === true);
            case 'logical':
                return deduplicatedDevices.filter(device => device.is_physical === false);
            case 'all':
            default:
                // Sort physical devices first, then logical
                return deduplicatedDevices.sort((a, b) => {
                    if (a.is_physical === b.is_physical) return 0;
                    return a.is_physical ? -1 : 1;
                });
        }
    };

    if (loading) {
        return (
            <Box display="flex" justifyContent="center" alignItems="center" minHeight="400px">
                <CircularProgress />
            </Box>
        );
    }

    if (error || !host) {
        return (
            <Box>
                <Button 
                    startIcon={<ArrowBackIcon />} 
                    onClick={() => navigate('/hosts')}
                    sx={{ mb: 2 }}
                >
                    {t('common.back')}
                </Button>
                <Paper sx={{ p: 3, textAlign: 'center' }}>
                    <Typography variant="h6" color="error">
                        {error || t('hostDetail.notFound', 'Host not found')}
                    </Typography>
                </Paper>
            </Box>
        );
    }

    return (
        <Box>
            <Button 
                startIcon={<ArrowBackIcon />} 
                onClick={() => navigate('/hosts')}
                sx={{ mb: 2 }}
            >
                {t('common.back')}
            </Button>

            <Typography variant="h4" sx={{ mb: 3, display: 'flex', alignItems: 'center' }}>
                <ComputerIcon sx={{ mr: 2, fontSize: '2rem' }} />
                {host.fqdn}
            </Typography>

            <Grid container spacing={3}>
                {/* Basic Information */}
                <Grid item xs={12} md={6}>
                    <Card>
                        <CardContent>
                            <Typography variant="h6" sx={{ mb: 2, display: 'flex', alignItems: 'center' }}>
                                <InfoIcon sx={{ mr: 1 }} />
                                {t('hostDetail.basicInfo', 'Basic Information')}
                            </Typography>
                            <Grid container spacing={2}>
                                <Grid item xs={12} sm={6}>
                                    <Typography variant="body2" color="textSecondary">
                                        {t('hosts.fqdn', 'FQDN')}
                                    </Typography>
                                    <Typography variant="body1">{host.fqdn}</Typography>
                                </Grid>
                                <Grid item xs={12} sm={6}>
                                    <Typography variant="body2" color="textSecondary">
                                        {t('hosts.ipv4', 'IPv4')}
                                    </Typography>
                                    <Typography variant="body1">{host.ipv4 || t('common.notAvailable')}</Typography>
                                </Grid>
                                <Grid item xs={12} sm={6}>
                                    <Typography variant="body2" color="textSecondary">
                                        {t('hosts.ipv6', 'IPv6')}
                                    </Typography>
                                    <Typography variant="body1">{host.ipv6 || t('common.notAvailable')}</Typography>
                                </Grid>
                                <Grid item xs={12} sm={6}>
                                    <Typography variant="body2" color="textSecondary">
                                        {t('hosts.status', 'Status')}
                                    </Typography>
                                    <Chip 
                                        label={host.status === 'up' ? t('hosts.up') : t('hosts.down')}
                                        color={getStatusColor(host.status)}
                                        size="small"
                                    />
                                </Grid>
                                <Grid item xs={12} sm={6}>
                                    <Typography variant="body2" color="textSecondary">
                                        {t('hostDetail.approvalStatus', 'Approval Status')}
                                    </Typography>
                                    <Chip 
                                        label={host.approval_status.charAt(0).toUpperCase() + host.approval_status.slice(1)}
                                        color={getApprovalStatusColor(host.approval_status)}
                                        size="small"
                                    />
                                </Grid>
                                <Grid item xs={12}>
                                    <Typography variant="body2" color="textSecondary">
                                        {t('hosts.lastCheckin', 'Last Check-in')}
                                    </Typography>
                                    <Typography variant="body1">{formatDate(host.last_access)}</Typography>
                                </Grid>
                                <Grid item xs={12}>
                                    <Typography variant="body2" color="textSecondary">
                                        {t('hostDetail.active', 'Active')}
                                    </Typography>
                                    <Chip 
                                        label={host.active ? t('common.yes') : t('common.no')}
                                        color={host.active ? 'success' : 'default'}
                                        size="small"
                                    />
                                </Grid>
                            </Grid>
                        </CardContent>
                    </Card>
                </Grid>

                {/* Operating System Information */}
                <Grid item xs={12} md={6}>
                    <Card>
                        <CardContent>
                            <Typography variant="h6" sx={{ mb: 2, display: 'flex', alignItems: 'center' }}>
                                <ComputerIcon sx={{ mr: 1 }} />
                                {t('hostDetail.osInfo', 'Operating System')}
                            </Typography>
                            <Grid container spacing={2}>
                                <Grid item xs={12}>
                                    <Typography variant="body2" color="textSecondary">
                                        {t('hostDetail.platform', 'Platform')}
                                    </Typography>
                                    <Typography variant="body1">{host.platform || t('common.notAvailable')}</Typography>
                                </Grid>
                                <Grid item xs={12}>
                                    <Typography variant="body2" color="textSecondary">
                                        {t('hostDetail.platformRelease', 'Platform Release')}
                                    </Typography>
                                    <Typography variant="body1">{host.platform_release || t('common.notAvailable')}</Typography>
                                </Grid>
                                <Grid item xs={12}>
                                    <Typography variant="body2" color="textSecondary">
                                        {t('hostDetail.kernel', 'Kernel')}
                                    </Typography>
                                    <Typography variant="body1" sx={{ wordBreak: 'break-word' }}>
                                        {host.platform_version || t('common.notAvailable')}
                                    </Typography>
                                </Grid>
                                <Grid item xs={12} sm={6}>
                                    <Typography variant="body2" color="textSecondary">
                                        {t('hostDetail.architecture', 'Architecture')}
                                    </Typography>
                                    <Typography variant="body1">{host.machine_architecture || t('common.notAvailable')}</Typography>
                                </Grid>
                                <Grid item xs={12} sm={6}>
                                    <Typography variant="body2" color="textSecondary">
                                        {t('hostDetail.processor', 'Processor')}
                                    </Typography>
                                    <Typography variant="body1">{host.processor || t('common.notAvailable')}</Typography>
                                </Grid>
                                <Grid item xs={12}>
                                    <Typography variant="body2" color="textSecondary">
                                        {t('hostDetail.osVersionUpdated', 'OS Info Updated')}
                                    </Typography>
                                    <Typography variant="body1">{formatDate(host.os_version_updated_at)}</Typography>
                                </Grid>
                                {host.os_details && (
                                    <Grid item xs={12}>
                                        <Typography variant="body2" color="textSecondary" sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                                            {t('hostDetail.osDetails', 'Additional Details')}
                                            <IconButton 
                                                size="small" 
                                                onClick={() => handleShowDialog(t('hostDetail.additionalOSDetails', 'Additional OS Details'), host.os_details)}
                                                sx={{ color: 'textSecondary' }}
                                            >
                                                <HelpOutlineIcon fontSize="small" />
                                            </IconButton>
                                        </Typography>
                                    </Grid>
                                )}
                            </Grid>
                        </CardContent>
                    </Card>
                </Grid>

                {/* Hardware Information */}
                <Grid item xs={12}>
                    <Card>
                        <CardContent>
                            <Typography variant="h6" sx={{ mb: 2, display: 'flex', alignItems: 'center' }}>
                                <MemoryIcon sx={{ mr: 1 }} />
                                {t('hostDetail.hardwareInfo', 'Hardware Information')}
                            </Typography>
                            <Grid container spacing={3}>
                                {/* CPU Information */}
                                <Grid item xs={12} md={6}>
                                    <Typography variant="subtitle1" sx={{ mb: 1, fontWeight: 'bold' }}>
                                        {t('hostDetail.cpuInfo', 'CPU')}
                                    </Typography>
                                    <Grid container spacing={2}>
                                        <Grid item xs={12}>
                                            <Typography variant="body2" color="textSecondary">
                                                {t('hostDetail.cpuVendor', 'CPU Vendor')}
                                            </Typography>
                                            <Typography variant="body1">{host.cpu_vendor || t('common.notAvailable')}</Typography>
                                        </Grid>
                                        <Grid item xs={12}>
                                            <Typography variant="body2" color="textSecondary">
                                                {t('hostDetail.cpuModel', 'CPU Model')}
                                            </Typography>
                                            <Typography variant="body1">{host.cpu_model || t('common.notAvailable')}</Typography>
                                        </Grid>
                                        <Grid item xs={6}>
                                            <Typography variant="body2" color="textSecondary">
                                                {t('hostDetail.cpuCores', 'Cores')}
                                            </Typography>
                                            <Typography variant="body1">{host.cpu_cores || t('common.notAvailable')}</Typography>
                                        </Grid>
                                        <Grid item xs={6}>
                                            <Typography variant="body2" color="textSecondary">
                                                {t('hostDetail.cpuThreads', 'Threads')}
                                            </Typography>
                                            <Typography variant="body1">{host.cpu_threads || t('common.notAvailable')}</Typography>
                                        </Grid>
                                        <Grid item xs={12}>
                                            <Typography variant="body2" color="textSecondary">
                                                {t('hostDetail.cpuFrequency', 'Frequency')}
                                            </Typography>
                                            <Typography variant="body1">{formatCpuFrequency(host.cpu_frequency_mhz)}</Typography>
                                        </Grid>
                                    </Grid>
                                </Grid>

                                {/* Memory Information */}
                                <Grid item xs={12} md={6}>
                                    <Typography variant="subtitle1" sx={{ mb: 1, fontWeight: 'bold' }}>
                                        {t('hostDetail.memoryInfo', 'Memory')}
                                    </Typography>
                                    <Grid container spacing={2}>
                                        <Grid item xs={12}>
                                            <Typography variant="body2" color="textSecondary">
                                                {t('hostDetail.totalMemory', 'Total Memory')}
                                            </Typography>
                                            <Typography variant="body1">{formatMemorySize(host.memory_total_mb)}</Typography>
                                        </Grid>
                                    </Grid>
                                </Grid>

                                {/* Hardware Update Timestamp */}
                                <Grid item xs={12}>
                                    <Typography variant="body2" color="textSecondary">
                                        {t('hostDetail.hardwareUpdated', 'Hardware Info Updated')}
                                    </Typography>
                                    <Typography variant="body1">{formatDate(host.hardware_updated_at)}</Typography>
                                </Grid>

                                {/* Storage Details */}
                                {storageDevices.length > 0 && (
                                    <Grid item xs={12}>
                                        <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 2 }}>
                                            <Typography variant="subtitle1" sx={{ fontWeight: 'bold', display: 'flex', alignItems: 'center' }}>
                                                <StorageIcon sx={{ mr: 1 }} />
                                                {t('hostDetail.storageDetails', 'Storage Devices')}
                                            </Typography>
                                            <ToggleButtonGroup
                                                value={storageFilter}
                                                exclusive
                                                onChange={(_, newFilter) => {
                                                    if (newFilter !== null) {
                                                        setStorageFilter(newFilter);
                                                    }
                                                }}
                                                size="small"
                                                sx={{ ml: 2 }}
                                            >
                                                <ToggleButton value="physical" aria-label="physical volumes">
                                                    {t('hostDetail.physicalVolumes', 'Physical')}
                                                </ToggleButton>
                                                <ToggleButton value="logical" aria-label="logical volumes">
                                                    {t('hostDetail.logicalVolumes', 'Logical')}
                                                </ToggleButton>
                                                <ToggleButton value="all" aria-label="all volumes">
                                                    {t('hostDetail.allVolumes', 'All')}
                                                </ToggleButton>
                                            </ToggleButtonGroup>
                                        </Box>
                                        {getFilteredStorageDevices(storageDevices).map((device: StorageDeviceType, index: number) => (
                                            <Box key={device.id || index} sx={{ mb: 3, p: 2, pb: 3, backgroundColor: 'grey.900', borderRadius: 1, minHeight: '140px', display: 'flex', flexDirection: 'column' }}>
                                                <Grid container spacing={2} alignItems="flex-start">
                                                    <Grid item xs={12} md={3}>
                                                        <Typography variant="body1" sx={{ fontWeight: 'medium', mb: 1 }}>
                                                            {device.name || device.device_path || device.mount_point || `Device ${index + 1}`}
                                                        </Typography>
                                                    </Grid>
                                                    <Grid item xs={12} md={8}>
                                                        <Table size="small">
                                                            <TableBody>
                                                                {device.mount_point && (
                                                                    <TableRow>
                                                                        <TableCell variant="head" sx={{ fontWeight: 'bold', color: 'textSecondary', width: '30%' }}>
                                                                            {t('hostDetail.mountPoint', 'Mount Point')}
                                                                        </TableCell>
                                                                        <TableCell>{device.mount_point}</TableCell>
                                                                    </TableRow>
                                                                )}
                                                                {device.capacity_bytes && (
                                                                    <TableRow>
                                                                        <TableCell variant="head" sx={{ fontWeight: 'bold', color: 'textSecondary' }}>
                                                                            {t('hostDetail.capacity', 'Capacity')}
                                                                        </TableCell>
                                                                        <TableCell>
                                                                            <Box>
                                                                                <Typography variant="body2" sx={{ mb: 1 }}>
                                                                                    {formatCapacityWithFree(device.capacity_bytes, device.used_bytes, device.available_bytes)}
                                                                                </Typography>
                                                                                <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                                                                                    <LinearProgress
                                                                                        variant="determinate"
                                                                                        value={getStorageUsagePercentage(device.capacity_bytes, device.used_bytes, device.available_bytes)}
                                                                                        color={getStorageUsageColor(getStorageUsagePercentage(device.capacity_bytes, device.used_bytes, device.available_bytes))}
                                                                                        sx={{ 
                                                                                            width: '100%', 
                                                                                            height: 8, 
                                                                                            borderRadius: 1,
                                                                                            backgroundColor: 'grey.700'
                                                                                        }}
                                                                                    />
                                                                                    <Typography variant="body2" sx={{ minWidth: 45, textAlign: 'right' }}>
                                                                                        {Math.round(getStorageUsagePercentage(device.capacity_bytes, device.used_bytes, device.available_bytes))}%
                                                                                    </Typography>
                                                                                </Box>
                                                                            </Box>
                                                                        </TableCell>
                                                                    </TableRow>
                                                                )}
                                                                {device.file_system && (
                                                                    <TableRow>
                                                                        <TableCell variant="head" sx={{ fontWeight: 'bold', color: 'textSecondary' }}>
                                                                            {t('hostDetail.filesystem', 'Filesystem')}
                                                                        </TableCell>
                                                                        <TableCell>{device.file_system}</TableCell>
                                                                    </TableRow>
                                                                )}
                                                                {device.device_type && (
                                                                    <TableRow>
                                                                        <TableCell variant="head" sx={{ fontWeight: 'bold', color: 'textSecondary' }}>
                                                                            {t('hostDetail.deviceType', 'Device Type')}
                                                                        </TableCell>
                                                                        <TableCell>{device.device_type}</TableCell>
                                                                    </TableRow>
                                                                )}
                                                            </TableBody>
                                                        </Table>
                                                    </Grid>
                                                    <Grid item xs={12} md={1}>
                                                        <IconButton 
                                                            size="small" 
                                                            onClick={() => handleShowDialog(t('hostDetail.storageDeviceDetails', 'Storage Device Details'), JSON.stringify(device, null, 2))}
                                                            sx={{ color: 'textSecondary' }}
                                                        >
                                                            <HelpOutlineIcon fontSize="small" />
                                                        </IconButton>
                                                    </Grid>
                                                </Grid>
                                            </Box>
                                        ))}
                                    </Grid>
                                )}

                                {/* Network Details */}
                                {networkInterfaces.length > 0 && (
                                    <Grid item xs={12}>
                                        <Typography variant="subtitle1" sx={{ mb: 2, fontWeight: 'bold', display: 'flex', alignItems: 'center' }}>
                                            <NetworkCheckIcon sx={{ mr: 1 }} />
                                            {t('hostDetail.networkDetails', 'Network Interfaces')}
                                        </Typography>
                                        {networkInterfaces
                                            .sort((a, b) => {
                                                // Sort by IP address presence: those with IPs come first
                                                const aHasIP = !!(a.ipv4_address || a.ipv6_address);
                                                const bHasIP = !!(b.ipv4_address || b.ipv6_address);
                                                if (aHasIP === bHasIP) return 0;
                                                return aHasIP ? -1 : 1;
                                            })
                                            .map((iface: NetworkInterfaceType, index: number) => (
                                            <Box key={iface.id || index} sx={{ mb: 3, p: 2, pb: 3, backgroundColor: 'grey.900', borderRadius: 1, minHeight: '140px', display: 'flex', flexDirection: 'column' }}>
                                                <Grid container spacing={2} alignItems="flex-start">
                                                    <Grid item xs={12} md={3}>
                                                        <Typography variant="body1" sx={{ fontWeight: 'medium', mb: 1 }}>
                                                            {iface.name || `Interface ${index + 1}`}
                                                        </Typography>
                                                        {iface.is_active && (
                                                            <Chip label={t('hostDetail.active', 'Active')} size="small" color="success" sx={{ mt: 1 }} />
                                                        )}
                                                    </Grid>
                                                    <Grid item xs={12} md={8}>
                                                        <Table size="small">
                                                            <TableBody>
                                                                {iface.interface_type && (
                                                                    <TableRow>
                                                                        <TableCell variant="head" sx={{ fontWeight: 'bold', color: 'textSecondary', width: '30%' }}>
                                                                            {t('hostDetail.interfaceType', 'Interface Type')}
                                                                        </TableCell>
                                                                        <TableCell>{iface.interface_type}</TableCell>
                                                                    </TableRow>
                                                                )}
                                                                <TableRow>
                                                                    <TableCell variant="head" sx={{ fontWeight: 'bold', color: 'textSecondary' }}>
                                                                        {t('hostDetail.ipv4Address', 'IPv4 Address')}
                                                                    </TableCell>
                                                                    <TableCell>
                                                                        {iface.ipv4_address || (
                                                                            <Typography variant="body2" sx={{ fontStyle: 'italic', color: 'textSecondary' }}>
                                                                                {t('common.unassigned', 'Unassigned')}
                                                                            </Typography>
                                                                        )}
                                                                    </TableCell>
                                                                </TableRow>
                                                                <TableRow>
                                                                    <TableCell variant="head" sx={{ fontWeight: 'bold', color: 'textSecondary' }}>
                                                                        {t('hostDetail.ipv6Address', 'IPv6 Address')}
                                                                    </TableCell>
                                                                    <TableCell>
                                                                        {iface.ipv6_address || (
                                                                            <Typography variant="body2" sx={{ fontStyle: 'italic', color: 'textSecondary' }}>
                                                                                {t('common.unassigned', 'Unassigned')}
                                                                            </Typography>
                                                                        )}
                                                                    </TableCell>
                                                                </TableRow>
                                                                {iface.mac_address && (
                                                                    <TableRow>
                                                                        <TableCell variant="head" sx={{ fontWeight: 'bold', color: 'textSecondary' }}>
                                                                            {t('hostDetail.macAddress', 'MAC Address')}
                                                                        </TableCell>
                                                                        <TableCell>{iface.mac_address}</TableCell>
                                                                    </TableRow>
                                                                )}
                                                                {iface.speed_mbps && (
                                                                    <TableRow>
                                                                        <TableCell variant="head" sx={{ fontWeight: 'bold', color: 'textSecondary' }}>
                                                                            {t('hostDetail.speed', 'Speed')}
                                                                        </TableCell>
                                                                        <TableCell>{iface.speed_mbps} Mbps</TableCell>
                                                                    </TableRow>
                                                                )}
                                                            </TableBody>
                                                        </Table>
                                                    </Grid>
                                                    <Grid item xs={12} md={1}>
                                                        <IconButton 
                                                            size="small" 
                                                            onClick={() => handleShowDialog(t('hostDetail.networkInterfaceDetails', 'Network Interface Details'), JSON.stringify(iface, null, 2))}
                                                            sx={{ color: 'textSecondary' }}
                                                        >
                                                            <HelpOutlineIcon fontSize="small" />
                                                        </IconButton>
                                                    </Grid>
                                                </Grid>
                                            </Box>
                                        ))}
                                    </Grid>
                                )}

                                {/* Additional Hardware Details */}
                                {host.hardware_details && (
                                    <Grid item xs={12}>
                                        <Typography variant="subtitle1" sx={{ mb: 1, fontWeight: 'bold', display: 'flex', alignItems: 'center', gap: 1 }}>
                                            {t('hostDetail.additionalHardware', 'Additional Hardware Details')}
                                            <IconButton 
                                                size="small" 
                                                onClick={() => handleShowDialog('Additional Hardware Details', host.hardware_details)}
                                                sx={{ color: 'textSecondary' }}
                                            >
                                                <HelpOutlineIcon fontSize="small" />
                                            </IconButton>
                                        </Typography>
                                    </Grid>
                                )}
                            </Grid>
                        </CardContent>
                    </Card>
                </Grid>

            </Grid>

            {/* Dialog for Additional Details */}
            <Dialog
                open={dialogOpen}
                onClose={handleCloseDialog}
                maxWidth="md"
                fullWidth
                PaperProps={{
                    sx: { backgroundColor: 'grey.900' }
                }}
            >
                <DialogTitle sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <Typography variant="h6">{dialogTitle}</Typography>
                    <IconButton onClick={handleCloseDialog} size="small">
                        <CloseIcon />
                    </IconButton>
                </DialogTitle>
                <DialogContent>
                    <Typography variant="body2" component="pre" sx={{ 
                        fontSize: '0.75rem', 
                        whiteSpace: 'pre-wrap', 
                        wordBreak: 'break-word',
                        backgroundColor: 'grey.800',
                        p: 2,
                        borderRadius: 1,
                        overflow: 'auto'
                    }}>
                        {dialogContent}
                    </Typography>
                </DialogContent>
            </Dialog>
        </Box>
    );
};

export default HostDetail;