// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

import React from 'react';
import {
    Box,
    Card,
    CardContent,
    Typography,
    Grid,
    Chip,
    LinearProgress,
    IconButton,
    Table,
    TableBody,
    TableRow,
    TableCell,
    ToggleButton,
    ToggleButtonGroup,
} from '@mui/material';
import MemoryIcon from '@mui/icons-material/Memory';
import StorageIcon from '@mui/icons-material/Storage';
import NetworkCheckIcon from '@mui/icons-material/NetworkCheck';
import HelpOutlineIcon from '@mui/icons-material/HelpOutline';
import { useTranslation } from 'react-i18next';
import { SysManageHost, StorageDevice as StorageDeviceType, NetworkInterface as NetworkInterfaceType } from '../../Services/hosts';
import {
    formatTimestamp,
    formatCpuFrequency,
    formatMemorySize,
    formatCapacityWithFree,
    getStorageUsagePercentage,
    getStorageUsageColor,
} from './hostDetailHelpers';

interface HostHardwareTabProps {
    host: SysManageHost;
    storageDevices: StorageDeviceType[];
    networkInterfaces: NetworkInterfaceType[];
    filteredStorageDevices: StorageDeviceType[];
    filteredNetworkInterfaces: NetworkInterfaceType[];
    storageFilter: 'all' | 'physical' | 'logical';
    setStorageFilter: (value: 'all' | 'physical' | 'logical') => void;
    networkFilter: 'all' | 'active' | 'inactive';
    setNetworkFilter: (value: 'all' | 'active' | 'inactive') => void;
    handleShowDialog: (title: string, content: string) => void;
}

const HostHardwareTab: React.FC<HostHardwareTabProps> = ({
    host,
    storageDevices,
    networkInterfaces,
    filteredStorageDevices,
    filteredNetworkInterfaces,
    storageFilter,
    setStorageFilter,
    networkFilter,
    setNetworkFilter,
    handleShowDialog,
}) => {
    const { t } = useTranslation();
    return (
                <Grid container spacing={3}>
                {/* Hardware Information */}
                <Grid size={{ xs: 12 }}>
                    <Card>
                        <CardContent>
                            <Typography variant="subtitle1" sx={{ mb: 2, display: 'flex', alignItems: 'center', gap: 2, fontWeight: 'bold', fontSize: '1.1rem' }}>
                                <MemoryIcon sx={{ mr: 1 }} />
                                {t('hostDetail.hardwareInfo', 'Hardware Information')}
                                <Typography variant="caption" color="textSecondary">
                                    {t('hosts.updated', 'Updated')}: {formatTimestamp(t, host.hardware_updated_at)}
                                </Typography>
                            </Typography>
                            <Grid container spacing={3}>
                                {/* CPU Information */}
                                <Grid size={{ xs: 12, md: 6 }}>
                                    <Typography variant="subtitle1" sx={{ mb: 1, fontWeight: 'bold' }}>
                                        {t('hostDetail.cpuInfo', 'CPU')}
                                    </Typography>
                                    <Grid container spacing={2}>
                                        <Grid size={{ xs: 12 }}>
                                            <Typography variant="body2" color="textSecondary">
                                                {t('hostDetail.cpuVendor', 'CPU Vendor')}
                                            </Typography>
                                            <Typography variant="body1">{host.cpu_vendor || t('common.notAvailable')}</Typography>
                                        </Grid>
                                        <Grid size={{ xs: 12 }}>
                                            <Typography variant="body2" color="textSecondary">
                                                {t('hostDetail.cpuModel', 'CPU Model')}
                                            </Typography>
                                            <Typography variant="body1">{host.cpu_model || t('common.notAvailable')}</Typography>
                                        </Grid>
                                        <Grid size={{ xs: 6 }}>
                                            <Typography variant="body2" color="textSecondary">
                                                {t('hostDetail.cpuCores', 'Cores')}
                                            </Typography>
                                            <Typography variant="body1">{host.cpu_cores || t('common.notAvailable')}</Typography>
                                        </Grid>
                                        <Grid size={{ xs: 6 }}>
                                            <Typography variant="body2" color="textSecondary">
                                                {t('hostDetail.cpuThreads', 'Threads')}
                                            </Typography>
                                            <Typography variant="body1">{host.cpu_threads || t('common.notAvailable')}</Typography>
                                        </Grid>
                                        <Grid size={{ xs: 12 }}>
                                            <Typography variant="body2" color="textSecondary">
                                                {t('hostDetail.cpuFrequency', 'Frequency')}
                                            </Typography>
                                            <Typography variant="body1">{formatCpuFrequency(t, host.cpu_frequency_mhz)}</Typography>
                                        </Grid>
                                    </Grid>
                                </Grid>

                                {/* Memory Information */}
                                <Grid size={{ xs: 12, md: 6 }}>
                                    <Typography variant="subtitle1" sx={{ mb: 1, fontWeight: 'bold' }}>
                                        {t('hostDetail.memoryInfo', 'Memory')}
                                    </Typography>
                                    <Grid container spacing={2}>
                                        <Grid size={{ xs: 12 }}>
                                            <Typography variant="body2" color="textSecondary">
                                                {t('hostDetail.totalMemory', 'Total Memory')}
                                            </Typography>
                                            <Typography variant="body1">{formatMemorySize(t, host.memory_total_mb)}</Typography>
                                        </Grid>
                                    </Grid>
                                </Grid>


                                {/* Storage Details */}
                                {storageDevices.length > 0 && (
                                    <Grid size={{ xs: 12 }}>
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
                                        {filteredStorageDevices.map((device: StorageDeviceType, index: number) => (
                                            <Box key={device.id || index} sx={{ mb: 3, p: 2, pb: 3, backgroundColor: 'grey.900', borderRadius: 1, minHeight: '140px', display: 'flex', flexDirection: 'column' }}>
                                                <Grid container spacing={2} alignItems="flex-start">
                                                    <Grid size={{ xs: 12, md: 3 }}>
                                                        <Typography variant="body1" sx={{ fontWeight: 'medium', mb: 1 }}>
                                                            {device.name || device.device_path || device.mount_point || t('hostDetail.deviceNumber', 'Device {{number}}', { number: index + 1 })}
                                                        </Typography>
                                                    </Grid>
                                                    <Grid size={{ xs: 12, md: 8 }}>
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
                                                                {device.capacity_bytes != null && device.capacity_bytes > 0 && (
                                                                    <TableRow>
                                                                        <TableCell variant="head" sx={{ fontWeight: 'bold', color: 'textSecondary' }}>
                                                                            {t('hostDetail.capacity', 'Capacity')}
                                                                        </TableCell>
                                                                        <TableCell>
                                                                            <Box>
                                                                                <Typography variant="body2" sx={{ mb: 1 }}>
                                                                                    {formatCapacityWithFree(t, device.capacity_bytes, device.used_bytes, device.available_bytes)}
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
                                                    <Grid size={{ xs: 12, md: 1 }}>
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
                                    <Grid size={{ xs: 12 }}>
                                        <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 2 }}>
                                            <Typography variant="subtitle1" sx={{ fontWeight: 'bold', display: 'flex', alignItems: 'center' }}>
                                                <NetworkCheckIcon sx={{ mr: 1 }} />
                                                {t('hostDetail.networkDetails', 'Network Interfaces')}
                                            </Typography>
                                            <ToggleButtonGroup
                                                value={networkFilter}
                                                exclusive
                                                onChange={(_, newFilter) => {
                                                    if (newFilter !== null) {
                                                        setNetworkFilter(newFilter);
                                                    }
                                                }}
                                                size="small"
                                                sx={{ ml: 2 }}
                                            >
                                                <ToggleButton value="active" aria-label="active interfaces">
                                                    {t('hostDetail.activeInterfaces', 'Active')}
                                                </ToggleButton>
                                                <ToggleButton value="inactive" aria-label="inactive interfaces">
                                                    {t('hostDetail.inactiveInterfaces', 'Inactive')}
                                                </ToggleButton>
                                                <ToggleButton value="all" aria-label="all interfaces">
                                                    {t('hostDetail.allInterfaces', 'All')}
                                                </ToggleButton>
                                            </ToggleButtonGroup>
                                        </Box>
                                        {filteredNetworkInterfaces.map((iface: NetworkInterfaceType, index: number) => (
                                            <Box key={iface.id || index} sx={{ mb: 3, p: 2, pb: 3, backgroundColor: 'grey.900', borderRadius: 1, minHeight: '140px', display: 'flex', flexDirection: 'column' }}>
                                                <Grid container spacing={2} alignItems="flex-start">
                                                    <Grid size={{ xs: 12, md: 3 }}>
                                                        <Typography variant="body1" sx={{ fontWeight: 'medium', mb: 1 }}>
                                                            {iface.name || t('hostDetail.interfaceNumber', 'Interface {{number}}', { number: index + 1 })}
                                                        </Typography>
                                                        {iface.is_active && (
                                                            <Chip label={t('hostDetail.active', 'Active')} size="small" color="success" sx={{ mt: 1 }} />
                                                        )}
                                                    </Grid>
                                                    <Grid size={{ xs: 12, md: 8 }}>
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
                                                                {iface.speed_mbps != null && iface.speed_mbps > 0 && (
                                                                    <TableRow>
                                                                        <TableCell variant="head" sx={{ fontWeight: 'bold', color: 'textSecondary' }}>
                                                                            {t('hostDetail.speed', 'Speed')}
                                                                        </TableCell>
                                                                        {/* eslint-disable-next-line i18next/no-literal-string -- network speed unit */}
                                                                        <TableCell>{iface.speed_mbps} Mbps</TableCell>
                                                                    </TableRow>
                                                                )}
                                                            </TableBody>
                                                        </Table>
                                                    </Grid>
                                                    <Grid size={{ xs: 12, md: 1 }}>
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
                                    <Grid size={{ xs: 12 }}>
                                        <Typography variant="subtitle1" sx={{ mb: 1, fontWeight: 'bold', display: 'flex', alignItems: 'center', gap: 1 }}>
                                            {t('hostDetail.additionalHardware', 'Additional Hardware Details')}
                                            <IconButton
                                                size="small"
                                                onClick={() => handleShowDialog(t('hostDetail.additionalHardware', 'Additional Hardware Details'), host.hardware_details || '')}
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

                </Grid>    );
};

export default HostHardwareTab;
