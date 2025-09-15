import { useNavigate, useParams } from "react-router-dom";
import React, { useEffect, useState, useCallback } from 'react';
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
    LinearProgress,
    Tabs,
    Tab,
    FormControl,
    InputLabel,
    Select,
    MenuItem,
    Checkbox,
    FormControlLabel,
    IconButton,
    Alert
} from '@mui/material';
import ArrowBackIcon from '@mui/icons-material/ArrowBack';
import ComputerIcon from '@mui/icons-material/Computer';
import InfoIcon from '@mui/icons-material/Info';
import MemoryIcon from '@mui/icons-material/Memory';
import StorageIcon from '@mui/icons-material/Storage';
import NetworkCheckIcon from '@mui/icons-material/NetworkCheck';
import GroupIcon from '@mui/icons-material/Group';
import PersonIcon from '@mui/icons-material/Person';
import SecurityIcon from '@mui/icons-material/Security';
import HelpOutlineIcon from '@mui/icons-material/HelpOutline';
import CloseIcon from '@mui/icons-material/Close';
import AppsIcon from '@mui/icons-material/Apps';
import MedicalServicesIcon from '@mui/icons-material/MedicalServices';
import RefreshIcon from '@mui/icons-material/Refresh';
import LocalOfferIcon from '@mui/icons-material/LocalOffer';
import DeleteIcon from '@mui/icons-material/Delete';
import RestartAltIcon from '@mui/icons-material/RestartAlt';
import PowerSettingsNewIcon from '@mui/icons-material/PowerSettingsNew';
import VerifiedUserIcon from '@mui/icons-material/VerifiedUser';
import EditIcon from '@mui/icons-material/Edit';
import SaveIcon from '@mui/icons-material/Save';
import CancelIcon from '@mui/icons-material/Cancel';
import { Dialog, DialogTitle, DialogContent, DialogActions, Table, TableBody, TableRow, TableCell, ToggleButton, ToggleButtonGroup, Snackbar, TextField } from '@mui/material';
import { useTranslation } from 'react-i18next';

import { SysManageHost, StorageDevice as StorageDeviceType, NetworkInterface as NetworkInterfaceType, UserAccount, UserGroup, SoftwarePackage, DiagnosticReport, DiagnosticDetailResponse, UbuntuProInfo, doGetHostByID, doGetHostStorage, doGetHostNetwork, doGetHostUsers, doGetHostGroups, doGetHostSoftware, doGetHostDiagnostics, doRequestHostDiagnostics, doGetDiagnosticDetail, doDeleteDiagnostic, doRebootHost, doShutdownHost, doGetHostUbuntuPro, doAttachUbuntuPro, doDetachUbuntuPro, doEnableUbuntuProService, doDisableUbuntuProService } from '../Services/hosts';

// Use the service types directly - no need for local interfaces anymore

const HostDetail = () => {
    const { hostId } = useParams<{ hostId: string }>();
    const [host, setHost] = useState<SysManageHost | null>(null);
    const [storageDevices, setStorageDevices] = useState<StorageDeviceType[]>([]);
    const [networkInterfaces, setNetworkInterfaces] = useState<NetworkInterfaceType[]>([]);
    const [userAccounts, setUserAccounts] = useState<UserAccount[]>([]);
    const [userGroups, setUserGroups] = useState<UserGroup[]>([]);
    const [softwarePackages, setSoftwarePackages] = useState<SoftwarePackage[]>([]);
    const [ubuntuProInfo, setUbuntuProInfo] = useState<UbuntuProInfo | null>(null);
    const [diagnosticsData, setDiagnosticsData] = useState<DiagnosticReport[]>([]);
    const [loading, setLoading] = useState<boolean>(true);
    const [error, setError] = useState<string | null>(null);
    const [currentTab, setCurrentTab] = useState<number>(0);
    const [diagnosticsLoading, setDiagnosticsLoading] = useState<boolean>(false);
    const [storageFilter, setStorageFilter] = useState<'all' | 'physical' | 'logical'>('physical');
    const [networkFilter, setNetworkFilter] = useState<'all' | 'active' | 'inactive'>('active');
    const [userFilter, setUserFilter] = useState<'all' | 'system' | 'regular'>('regular');
    const [groupFilter, setGroupFilter] = useState<'all' | 'system' | 'regular'>('regular');
    const [packageManagerFilter, setPackageManagerFilter] = useState<string>('all');
    const [dialogOpen, setDialogOpen] = useState<boolean>(false);
    const [dialogContent, setDialogContent] = useState<string>('');
    const [dialogTitle, setDialogTitle] = useState<string>('');
    const [expandedUserGroups, setExpandedUserGroups] = useState<Set<number>>(new Set());
    const [expandedGroupUsers, setExpandedGroupUsers] = useState<Set<number>>(new Set());
    const [deleteConfirmOpen, setDeleteConfirmOpen] = useState<boolean>(false);
    const [diagnosticToDelete, setDiagnosticToDelete] = useState<number | null>(null);
    const [snackbarOpen, setSnackbarOpen] = useState<boolean>(false);
    const [snackbarMessage, setSnackbarMessage] = useState<string>('');
    const [rebootConfirmOpen, setRebootConfirmOpen] = useState<boolean>(false);
    const [shutdownConfirmOpen, setShutdownConfirmOpen] = useState<boolean>(false);
    const [snackbarSeverity, setSnackbarSeverity] = useState<'success' | 'error'>('success');
    const [diagnosticDetailOpen, setDiagnosticDetailOpen] = useState<boolean>(false);
    const [selectedDiagnostic, setSelectedDiagnostic] = useState<DiagnosticDetailResponse | null>(null);

    // Ubuntu Pro state
    const [ubuntuProTokenDialog, setUbuntuProTokenDialog] = useState<boolean>(false);
    const [ubuntuProToken, setUbuntuProToken] = useState<string>('');
    const [ubuntuProAttaching, setUbuntuProAttaching] = useState<boolean>(false);
    const [ubuntuProDetaching, setUbuntuProDetaching] = useState<boolean>(false);

    // Ubuntu Pro service editing state
    const [servicesEditMode, setServicesEditMode] = useState<boolean>(false);
    const [editedServices, setEditedServices] = useState<{[serviceName: string]: boolean}>({});
    const [servicesSaving, setServicesSaving] = useState<boolean>(false);
    const [servicesMessage, setServicesMessage] = useState<string>('');

    // Tag-related state
    const [hostTags, setHostTags] = useState<Array<{id: number, name: string, description: string | null}>>([]);
    const [availableTags, setAvailableTags] = useState<Array<{id: number, name: string, description: string | null}>>([]);
    const [selectedTagToAdd, setSelectedTagToAdd] = useState<number | string>('');
    const [diagnosticDetailLoading, setDiagnosticDetailLoading] = useState<boolean>(false);
    const navigate = useNavigate();
    const { t } = useTranslation();

    // Helper functions to calculate dynamic tab indices
    const getUbuntuProTabIndex = () => ubuntuProInfo?.available ? 4 : -1;
    const getDiagnosticsTabIndex = () => ubuntuProInfo?.available ? 5 : 4;

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
                
                // Fetch normalized storage, network, user access, software, and diagnostics data
                try {
                    const [storageData, networkData, usersData, groupsData, softwareData, diagnosticsData] = await Promise.all([
                        doGetHostStorage(BigInt(hostId)),
                        doGetHostNetwork(BigInt(hostId)),
                        doGetHostUsers(BigInt(hostId)),
                        doGetHostGroups(BigInt(hostId)),
                        doGetHostSoftware(BigInt(hostId)),
                        doGetHostDiagnostics(BigInt(hostId))
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
                    
                    // Set user access data
                    setUserAccounts(usersData);
                    setUserGroups(groupsData);
                    
                    // Set software data
                    setSoftwarePackages(softwareData);

                    // Set diagnostics data
                    setDiagnosticsData(diagnosticsData);

                    // Fetch Ubuntu Pro data (only for Ubuntu hosts)
                    try {
                        if (hostData.platform?.toLowerCase().includes('ubuntu') ||
                            hostData.platform_release?.toLowerCase().includes('ubuntu')) {
                            const ubuntuProData = await doGetHostUbuntuPro(BigInt(hostId));
                            setUbuntuProInfo(ubuntuProData);
                        }
                    } catch (error) {
                        // Ubuntu Pro data is optional, don't fail the whole page load
                        console.log('Ubuntu Pro data not available or failed to load:', error);
                    }
                } catch (hardwareErr) {
                    // Log but don't fail the whole request - hardware/software/diagnostics data is optional
                    console.warn('Failed to fetch hardware/software/diagnostics data:', hardwareErr);
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

    // Tag-related functions
    const loadHostTags = useCallback(async () => {
        if (!hostId) return;
        
        try {
            const response = await window.fetch(`/api/hosts/${hostId}/tags`, {
                headers: {
                    'Authorization': `Bearer ${localStorage.getItem('bearer_token')}`,
                },
            });
            
            if (response.ok) {
                const tags = await response.json();
                setHostTags(tags);
            }
        } catch (error) {
            console.error('Error loading host tags:', error);
        }
    }, [hostId]);

    const loadAvailableTags = useCallback(async () => {
        try {
            const response = await window.fetch('/api/tags', {
                headers: {
                    'Authorization': `Bearer ${localStorage.getItem('bearer_token')}`,
                },
            });
            
            if (response.ok) {
                const allTags = await response.json();
                // Filter out tags that are already assigned to this host
                const available = allTags.filter((tag: {id: number, name: string, description: string | null}) => 
                    !hostTags.some(hostTag => hostTag.id === tag.id)
                );
                setAvailableTags(available);
            }
        } catch (error) {
            console.error('Error loading available tags:', error);
        }
    }, [hostTags]);

    // Load tags when component mounts and when hostTags change
    useEffect(() => {
        if (hostId) {
            loadHostTags();
        }
    }, [hostId, loadHostTags]);

    useEffect(() => {
        loadAvailableTags();
    }, [hostTags, loadAvailableTags]);

    // Auto-refresh Ubuntu Pro information every 30 seconds
    useEffect(() => {
        let interval: ReturnType<typeof window.setInterval> | null = null;

        if (hostId && ubuntuProInfo?.available) {
            interval = window.setInterval(async () => {
                try {
                    const ubuntuProData = await doGetHostUbuntuPro(BigInt(hostId));
                    setUbuntuProInfo(ubuntuProData);
                    // Clear service messages on refresh (as requested by user)
                    if (servicesMessage) {
                        setServicesMessage('');
                    }
                } catch {
                    // Silently ignore errors during auto-refresh
                }
            }, 30000); // 30 seconds
        }

        return () => {
            if (interval) {
                window.clearInterval(interval);
            }
        };
    }, [hostId, ubuntuProInfo?.available, servicesMessage]);

    const formatDate = (dateString: string | undefined) => {
        if (!dateString) return t('common.notAvailable', 'N/A');
        try {
            const date = new Date(dateString);
            return date.toLocaleString();
        } catch {
            return t('common.invalidDate', 'Invalid date');
        }
    };

    const formatTimestamp = (timestamp: string | null | undefined) => {
        if (!timestamp) return t('hosts.never', 'never');
        const date = new Date(timestamp);
        if (isNaN(date.getTime())) return t('hosts.invalidDate', 'invalid');
        
        const now = new Date();
        const diffMinutes = Math.floor((now.getTime() - date.getTime()) / 60000);
        if (diffMinutes < 2) return t('hosts.justNow', 'just now');
        if (diffMinutes < 60) return t('hosts.minutesAgo', '{{minutes}}m ago', { minutes: diffMinutes });
        if (diffMinutes < 1440) return t('hosts.hoursAgo', '{{hours}}h ago', { hours: Math.floor(diffMinutes / 60) });
        return t('hosts.daysAgo', '{{days}}d ago', { days: Math.floor(diffMinutes / 1440) });
    };

    const getStatusColor = (status: string) => {
        return status === 'up' ? 'success' : 'error';
    };

    const getDisplayStatus = (host: SysManageHost) => {
        if (!host.last_access) return 'down';
        
        // Same logic as host list: consider host "up" if last access was within 5 minutes
        const lastAccess = new Date(host.last_access);
        const now = new Date();
        const diffMinutes = Math.floor((now.getTime() - lastAccess.getTime()) / 60000);
        
        return diffMinutes <= 5 ? 'up' : 'down';
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
        
        const unit = units.at(unitIndex) ?? 'B';
        return `${formattedSize} ${unit}`;
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
            const deviceName = device.name || 'Unknown Device';
            if (!devicesByName.has(deviceName)) {
                devicesByName.set(deviceName, []);
            }
            devicesByName.get(deviceName)!.push(device);
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
                    const aMountPriority = getMountPointPriority(a.mount_point || '');
                    const bMountPriority = getMountPointPriority(b.mount_point || '');
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

    // Filter user accounts based on system/regular selection
    const getFilteredUsers = (users: UserAccount[]): UserAccount[] => {
        switch (userFilter) {
            case 'system':
                return users.filter(user => user.is_system_user === true);
            case 'regular':
                return users.filter(user => user.is_system_user === false);
            case 'all':
            default:
                // Sort regular users first, then system
                return users.sort((a, b) => {
                    if (a.is_system_user === b.is_system_user) return 0;
                    return a.is_system_user ? 1 : -1;
                });
        }
    };

    // Filter user groups based on system/regular selection
    const getFilteredGroups = (groups: UserGroup[]): UserGroup[] => {
        switch (groupFilter) {
            case 'system':
                return groups.filter(group => group.is_system_group === true);
            case 'regular':
                return groups.filter(group => group.is_system_group === false);
            case 'all':
            default:
                // Sort regular groups first, then system
                return groups.sort((a, b) => {
                    if (a.is_system_group === b.is_system_group) return 0;
                    return a.is_system_group ? 1 : -1;
                });
        }
    };

    // Filter network interfaces based on active/inactive selection
    const getFilteredNetworkInterfaces = (interfaces: NetworkInterfaceType[]): NetworkInterfaceType[] => {
        switch (networkFilter) {
            case 'active':
                return interfaces.filter(iface => !!(iface.ipv4_address || iface.ipv6_address));
            case 'inactive':
                return interfaces.filter(iface => !(iface.ipv4_address || iface.ipv6_address));
            case 'all':
            default:
                // Sort active interfaces first, then inactive
                return interfaces.sort((a, b) => {
                    const aHasIP = !!(a.ipv4_address || a.ipv6_address);
                    const bHasIP = !!(b.ipv4_address || b.ipv6_address);
                    if (aHasIP === bHasIP) return 0;
                    return aHasIP ? -1 : 1;
                });
        }
    };

    // Get unique package managers from software packages
    const getPackageManagers = (packages: SoftwarePackage[]): string[] => {
        const managers = new Set<string>();
        packages.forEach(pkg => {
            if (pkg.package_manager) {
                managers.add(pkg.package_manager);
            }
        });
        return Array.from(managers).sort();
    };

    // Filter software packages based on package manager selection
    const getFilteredSoftwarePackages = (packages: SoftwarePackage[]): SoftwarePackage[] => {
        if (packageManagerFilter === 'all') {
            return packages.sort((a, b) => (a.package_name || '').localeCompare(b.package_name || ''));
        }
        return packages
            .filter(pkg => pkg.package_manager === packageManagerFilter)
            .sort((a, b) => (a.package_name || '').localeCompare(b.package_name || ''));
    };

    // Check if diagnostics are currently being processed based on persistent state
    const isDiagnosticsProcessing = host?.diagnostics_request_status === 'pending';

    const handleRequestDiagnostics = async () => {
        if (!hostId) return;
        
        try {
            setDiagnosticsLoading(true);
            await doRequestHostDiagnostics(BigInt(hostId));
            
            // Show success message
            console.log('Diagnostics collection requested successfully');
            
            // Refresh host data to get updated diagnostics request status
            const updatedHost = await doGetHostByID(BigInt(hostId));
            setHost(updatedHost);
            
            // Start polling for completion if request is pending
            if (updatedHost?.diagnostics_request_status === 'pending') {
                const pollForCompletion = async (attempts = 0, maxAttempts = 20) => {
                    if (attempts >= maxAttempts) {
                        console.log('Diagnostics polling completed after max attempts');
                        return;
                    }
                    
                    setTimeout(async () => {
                        try {
                            const currentHost = await doGetHostByID(BigInt(hostId));
                            setHost(currentHost);
                            
                            // If status changed from pending, also refresh diagnostics data
                            if (currentHost?.diagnostics_request_status !== 'pending') {
                                const updatedDiagnostics = await doGetHostDiagnostics(BigInt(hostId));
                                setDiagnosticsData(updatedDiagnostics);
                                console.log('Diagnostics request completed');
                            } else {
                                // Continue polling
                                pollForCompletion(attempts + 1, maxAttempts);
                            }
                        } catch (err) {
                            console.warn('Failed to refresh host data:', err);
                            pollForCompletion(attempts + 1, maxAttempts);
                        }
                    }, 3000); // Poll every 3 seconds
                };
                
                pollForCompletion();
            }
        } catch (error) {
            console.error('Error requesting diagnostics:', error);
        } finally {
            setDiagnosticsLoading(false);
        }
    };

    const handleDeleteDiagnostic = (diagnosticId: number) => {
        setDiagnosticToDelete(diagnosticId);
        setDeleteConfirmOpen(true);
    };

    const handleViewDiagnosticDetail = async (diagnosticId: number) => {
        try {
            setDiagnosticDetailLoading(true);
            setDiagnosticDetailOpen(true);
            const diagnosticDetail = await doGetDiagnosticDetail(diagnosticId);
            setSelectedDiagnostic(diagnosticDetail);
        } catch (error) {
            console.error('Error fetching diagnostic detail:', error);
            setSnackbarMessage(t('hostDetail.diagnosticLoadFailed', 'Failed to load diagnostic details'));
            setSnackbarSeverity('error');
            setSnackbarOpen(true);
            setDiagnosticDetailOpen(false);
        } finally {
            setDiagnosticDetailLoading(false);
        }
    };

    const handleRebootClick = () => {
        setRebootConfirmOpen(true);
    };

    const handleShutdownClick = () => {
        setShutdownConfirmOpen(true);
    };

    const handleRebootConfirm = async () => {
        if (!host || !host.id) return;
        
        try {
            await doRebootHost(host.id);
            setSnackbarMessage(t('hosts.rebootRequested', 'Reboot requested successfully'));
            setSnackbarOpen(true);
            setRebootConfirmOpen(false);
        } catch (error) {
            console.error('Failed to request reboot:', error);
            setSnackbarMessage(t('hosts.rebootFailed', 'Failed to request reboot'));
            setSnackbarOpen(true);
        }
    };

    const handleShutdownConfirm = async () => {
        if (!host || !host.id) return;
        
        try {
            await doShutdownHost(host.id);
            setSnackbarMessage(t('hosts.shutdownRequested', 'Shutdown requested successfully'));
            setSnackbarOpen(true);
            setShutdownConfirmOpen(false);
        } catch (error) {
            console.error('Failed to request shutdown:', error);
            setSnackbarMessage(t('hosts.shutdownFailed', 'Failed to request shutdown'));
            setSnackbarOpen(true);
        }
    };

    const handleConfirmDelete = async () => {
        if (!diagnosticToDelete) return;
        
        try {
            console.log('Deleting diagnostic:', diagnosticToDelete);
            await doDeleteDiagnostic(diagnosticToDelete);
            console.log('Diagnostic deleted successfully, refreshing data...');
            
            // Refresh diagnostics data after deletion
            if (hostId) {
                try {
                    const updatedDiagnostics = await doGetHostDiagnostics(BigInt(hostId));
                    setDiagnosticsData(updatedDiagnostics);
                    console.log('Diagnostics data refreshed:', updatedDiagnostics.length, 'reports');
                    
                    // Also refresh host data to update the processing pill status
                    // This is especially important if we just deleted the last diagnostic
                    const updatedHost = await doGetHostByID(BigInt(hostId));
                    setHost(updatedHost);
                    console.log('Host data refreshed, diagnostics_request_status:', updatedHost?.diagnostics_request_status);
                } catch (refreshError) {
                    console.error('Error refreshing data after deletion:', refreshError);
                    // Still show success since deletion worked
                }
            }
            
            setSnackbarMessage(t('hostDetail.diagnosticDeleted', 'Diagnostic report deleted successfully'));
            setSnackbarSeverity('success');
            setSnackbarOpen(true);
            
        } catch (error) {
            console.error('Error deleting diagnostic:', error);
            setSnackbarMessage(t('hostDetail.diagnosticDeleteFailed', 'Failed to delete diagnostic report'));
            setSnackbarSeverity('error');
            setSnackbarOpen(true);
        } finally {
            setDeleteConfirmOpen(false);
            setDiagnosticToDelete(null);
        }
    };

    const handleCancelDelete = () => {
        setDeleteConfirmOpen(false);
        setDiagnosticToDelete(null);
    };

    const handleAddTag = async () => {
        if (!hostId || !selectedTagToAdd) return;
        
        try {
            const response = await window.fetch(`/api/hosts/${hostId}/tags/${selectedTagToAdd}`, {
                method: 'POST',
                headers: {
                    'Authorization': `Bearer ${localStorage.getItem('bearer_token')}`,
                },
            });
            
            if (response.ok) {
                await loadHostTags();
                await loadAvailableTags();
                setSelectedTagToAdd('');
                setSnackbarMessage(t('hostDetail.tagAdded', 'Tag added successfully'));
                setSnackbarSeverity('success');
                setSnackbarOpen(true);
            } else {
                setSnackbarMessage(t('hostDetail.tagAddFailed', 'Failed to add tag'));
                setSnackbarSeverity('error');
                setSnackbarOpen(true);
            }
        } catch (error) {
            console.error('Error adding tag:', error);
            setSnackbarMessage(t('hostDetail.tagAddFailed', 'Failed to add tag'));
            setSnackbarSeverity('error');
            setSnackbarOpen(true);
        }
    };

    const handleRemoveTag = async (tagId: number) => {
        if (!hostId) return;
        
        try {
            const response = await window.fetch(`/api/hosts/${hostId}/tags/${tagId}`, {
                method: 'DELETE',
                headers: {
                    'Authorization': `Bearer ${localStorage.getItem('bearer_token')}`,
                },
            });
            
            if (response.ok) {
                await loadHostTags();
                await loadAvailableTags();
                setSnackbarMessage(t('hostDetail.tagRemoved', 'Tag removed successfully'));
                setSnackbarSeverity('success');
                setSnackbarOpen(true);
            } else {
                setSnackbarMessage(t('hostDetail.tagRemoveFailed', 'Failed to remove tag'));
                setSnackbarSeverity('error');
                setSnackbarOpen(true);
            }
        } catch (error) {
            console.error('Error removing tag:', error);
            setSnackbarMessage(t('hostDetail.tagRemoveFailed', 'Failed to remove tag'));
            setSnackbarSeverity('error');
            setSnackbarOpen(true);
        }
    };

    const handleCloseSnackbar = () => {
        setSnackbarOpen(false);
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
                    <Typography variant="subtitle1" sx={{ fontWeight: 'bold', fontSize: '1.25rem' }} color="error">
                        {error || t('hostDetail.notFound', 'Host not found')}
                    </Typography>
                </Paper>
            </Box>
        );
    }

    const handleTabChange = (event: React.SyntheticEvent, newValue: number) => {
        setCurrentTab(newValue);
    };

    // Ubuntu Pro handlers
    const handleUbuntuProAttach = () => {
        setUbuntuProTokenDialog(true);
    };

    const handleUbuntuProDetach = async () => {
        if (!hostId || !host) return;

        setUbuntuProDetaching(true);
        try {
            await doDetachUbuntuPro(BigInt(hostId));
            setSnackbarMessage(t('hostDetail.ubuntuProDetachSuccess', 'Ubuntu Pro detached successfully'));
            setSnackbarSeverity('success');
            setSnackbarOpen(true);

            // Refresh Ubuntu Pro info after a short delay to allow agent to process
            setTimeout(async () => {
                try {
                    const ubuntuProData = await doGetHostUbuntuPro(BigInt(hostId));
                    setUbuntuProInfo(ubuntuProData);
                } catch (refreshError) {
                    console.log('Failed to refresh Ubuntu Pro data:', refreshError);
                }
            }, 2000);
        } catch {
            setSnackbarMessage(t('hostDetail.ubuntuProDetachError', 'Failed to detach Ubuntu Pro'));
            setSnackbarSeverity('error');
            setSnackbarOpen(true);
        } finally {
            setUbuntuProDetaching(false);
        }
    };

    const handleUbuntuProTokenSubmit = async () => {
        if (!hostId || !host || !ubuntuProToken.trim()) return;

        setUbuntuProAttaching(true);
        setUbuntuProTokenDialog(false);

        try {
            await doAttachUbuntuPro(BigInt(hostId), ubuntuProToken.trim());
            setSnackbarMessage(t('hostDetail.ubuntuProAttachSuccess', 'Ubuntu Pro attached successfully'));
            setSnackbarSeverity('success');
            setSnackbarOpen(true);

            // Refresh Ubuntu Pro info after a short delay to allow agent to process
            setTimeout(async () => {
                try {
                    const ubuntuProData = await doGetHostUbuntuPro(BigInt(hostId));
                    setUbuntuProInfo(ubuntuProData);
                } catch (refreshError) {
                    console.log('Failed to refresh Ubuntu Pro data:', refreshError);
                }
            }, 3000); // Longer delay for attach since it may take more time
        } catch {
            setSnackbarMessage(t('hostDetail.ubuntuProAttachError', 'Failed to attach Ubuntu Pro'));
            setSnackbarSeverity('error');
            setSnackbarOpen(true);
        } finally {
            setUbuntuProAttaching(false);
            setUbuntuProToken('');
        }
    };

    const handleUbuntuProTokenCancel = () => {
        setUbuntuProTokenDialog(false);
        setUbuntuProToken('');
    };

    // Ubuntu Pro service management handlers
    const handleServicesEditToggle = () => {
        if (servicesEditMode) {
            // Cancel editing - reset changes
            setEditedServices({});
            setServicesMessage('');
        } else {
            // Start editing - initialize with current service states
            const currentStates: {[serviceName: string]: boolean} = {};
            ubuntuProInfo?.services.forEach(service => {
                if (service.status !== 'n/a') {
                    currentStates[service.name] = service.status === 'enabled';
                }
            });
            setEditedServices(currentStates);
        }
        setServicesEditMode(!servicesEditMode);
    };

    const handleServiceToggle = (serviceName: string, enabled: boolean) => {
        setEditedServices(prev => ({
            ...prev,
            [serviceName]: enabled
        }));
    };

    const handleServicesSave = async () => {
        if (!hostId || !host || !ubuntuProInfo) return;

        setServicesSaving(true);
        setServicesMessage('');

        try {
            const servicesToChange: Array<{service: string, enable: boolean}> = [];

            // Compare current states with edited states
            ubuntuProInfo.services.forEach(service => {
                if (service.status !== 'n/a') {
                    const currentEnabled = service.status === 'enabled';
                    const newEnabled = editedServices[service.name];

                    if (newEnabled !== undefined && currentEnabled !== newEnabled) {
                        servicesToChange.push({
                            service: service.name,
                            enable: newEnabled
                        });
                    }
                }
            });

            // Apply changes
            for (const change of servicesToChange) {
                if (change.enable) {
                    await doEnableUbuntuProService(parseInt(hostId), change.service);
                } else {
                    await doDisableUbuntuProService(parseInt(hostId), change.service);
                }
            }

            if (servicesToChange.length > 0) {
                setServicesMessage(`${servicesToChange.length} service(s) updated`);
                setSnackbarMessage(t('hostDetail.servicesUpdateRequested', 'Ubuntu Pro services update requested'));
                setSnackbarSeverity('success');
                setSnackbarOpen(true);
            } else {
                setServicesMessage('No changes made');
            }

            setServicesEditMode(false);
            setEditedServices({});

        } catch (error) {
            console.error('Error updating Ubuntu Pro services:', error);
            setServicesMessage('Error updating services');
            setSnackbarMessage(t('hostDetail.servicesUpdateError', 'Error updating Ubuntu Pro services'));
            setSnackbarSeverity('error');
            setSnackbarOpen(true);
        } finally {
            setServicesSaving(false);
        }
    };

    return (
        <Box>
            <Button 
                startIcon={<ArrowBackIcon />} 
                onClick={() => navigate('/hosts')}
                sx={{ mb: 2 }}
            >
                {t('common.back')}
            </Button>

            <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 3 }}>
                <Typography variant="h4" sx={{ display: 'flex', alignItems: 'center' }}>
                    <ComputerIcon sx={{ mr: 2, fontSize: '2rem' }} />
                    {host.fqdn}
                </Typography>
                <Box sx={{ display: 'flex', gap: 1 }}>
                    <Button
                        variant="outlined"
                        color="warning"
                        startIcon={<RestartAltIcon />}
                        onClick={handleRebootClick}
                        disabled={!host.active || !host.is_agent_privileged}
                    >
                        {t('hosts.reboot', 'Reboot')}
                    </Button>
                    <Button
                        variant="outlined"
                        color="error"
                        startIcon={<PowerSettingsNewIcon />}
                        onClick={handleShutdownClick}
                        disabled={!host.active || !host.is_agent_privileged}
                    >
                        {t('hosts.shutdown', 'Shutdown')}
                    </Button>
                </Box>
            </Box>

            {/* Tabs */}
            <Box sx={{ borderBottom: 1, borderColor: 'divider', mb: 3 }}>
                <Tabs value={currentTab} onChange={handleTabChange} aria-label="host detail tabs">
                    <Tab 
                        icon={<InfoIcon />} 
                        label={t('hostDetail.infoTab', 'Info')} 
                        iconPosition="start"
                        sx={{ textTransform: 'none' }}
                    />
                    <Tab 
                        icon={<MemoryIcon />} 
                        label={t('hostDetail.hardwareTab', 'Hardware')} 
                        iconPosition="start"
                        sx={{ textTransform: 'none' }}
                    />
                    <Tab 
                        icon={<AppsIcon />} 
                        label={t('hostDetail.softwareTab', 'Software')} 
                        iconPosition="start"
                        sx={{ textTransform: 'none' }}
                    />
                    <Tab
                        icon={<SecurityIcon />}
                        label={t('hostDetail.accessTab', 'Access')}
                        iconPosition="start"
                        sx={{ textTransform: 'none' }}
                    />
                    {ubuntuProInfo?.available && (
                        <Tab
                            icon={<VerifiedUserIcon />}
                            label={t('hostDetail.ubuntuProTab', 'Ubuntu Pro')}
                            iconPosition="start"
                            sx={{ textTransform: 'none' }}
                        />
                    )}
                    <Tab
                        icon={<MedicalServicesIcon />}
                        label={t('hostDetail.diagnosticsTab', 'Diagnostics')}
                        iconPosition="start"
                        sx={{ textTransform: 'none' }}
                    />
                </Tabs>
            </Box>

            {/* Tab Content */}
            {currentTab === 0 && (
                <Grid container spacing={3}>
                {/* Basic Information */}
                <Grid item xs={12} md={6}>
                    <Card sx={{ height: '100%' }}>
                        <CardContent>
                            <Typography variant="subtitle1" sx={{ mb: 2, display: 'flex', alignItems: 'center', fontWeight: 'bold', fontSize: '1.1rem' }}>
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
                                        label={getDisplayStatus(host) === 'up' ? t('hosts.up') : t('hosts.down')}
                                        color={getStatusColor(getDisplayStatus(host))}
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
                                <Grid item xs={12} sm={6}>
                                    <Typography variant="body2" color="textSecondary">
                                        {t('hosts.lastCheckin', 'Last Check-in')}
                                    </Typography>
                                    <Typography variant="body1">{formatDate(host.last_access)}</Typography>
                                </Grid>
                                <Grid item xs={12} sm={6}>
                                    <Typography variant="body2" color="textSecondary">
                                        {t('hosts.scriptsEnabled', 'Scripts Enabled')}
                                    </Typography>
                                    {host.script_execution_enabled === undefined || host.script_execution_enabled === null ? (
                                        <Typography variant="body2" sx={{ color: 'text.secondary', fontStyle: 'italic' }}>
                                            Unknown
                                        </Typography>
                                    ) : (
                                        <Chip 
                                            label={host.script_execution_enabled ? t('common.yes') : t('common.no')}
                                            color={host.script_execution_enabled ? 'success' : 'error'}
                                            size="small"
                                            variant="filled"
                                            title={host.script_execution_enabled ? t('hosts.scriptsEnabledTooltip') : t('hosts.scriptsDisabledTooltip')}
                                        />
                                    )}
                                </Grid>
                                <Grid item xs={12} sm={6}>
                                    <Typography variant="body2" color="textSecondary">
                                        {t('hosts.privileged', 'Privileged')}
                                    </Typography>
                                    {host.is_agent_privileged === undefined || host.is_agent_privileged === null ? (
                                        <Typography variant="body2" sx={{ color: 'text.secondary', fontStyle: 'italic' }}>
                                            Unknown
                                        </Typography>
                                    ) : (
                                        <Chip 
                                            label={host.is_agent_privileged ? t('common.yes') : t('common.no')}
                                            color={host.is_agent_privileged ? 'success' : 'error'}
                                            size="small"
                                            variant="filled"
                                            title={host.is_agent_privileged ? t('hosts.runningPrivileged') : t('hosts.runningUnprivileged')}
                                        />
                                    )}
                                </Grid>
                                <Grid item xs={12} sm={6}>
                                    <Typography variant="body2" color="textSecondary">
                                        {t('hostDetail.active', 'Active')}
                                    </Typography>
                                    <Chip 
                                        label={host.active ? t('common.yes') : t('common.no')}
                                        color={host.active ? 'success' : 'default'}
                                        size="small"
                                    />
                                </Grid>
                                <Grid item xs={12} sm={6}>
                                    <Typography variant="body2" color="textSecondary">
                                        {t('hosts.shellsAllowed', 'Shells Allowed')}
                                    </Typography>
                                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, flexWrap: 'wrap' }}>
                                        {/* Enabled Shells */}
                                        {host.enabled_shells ? (() => {
                                            try {
                                                const shells = JSON.parse(host.enabled_shells);
                                                if (shells && shells.length > 0) {
                                                    return shells.map((shell: string) => (
                                                        <Chip
                                                            key={shell}
                                                            label={shell}
                                                            color="success"
                                                            size="small"
                                                            variant="filled"
                                                        />
                                                    ));
                                                } else {
                                                    return (
                                                        <Typography variant="body2" sx={{ color: 'text.secondary', fontStyle: 'italic' }}>
                                                            None
                                                        </Typography>
                                                    );
                                                }
                                            } catch {
                                                return (
                                                    <Typography variant="body2" sx={{ color: 'text.secondary', fontStyle: 'italic' }}>
                                                        None
                                                    </Typography>
                                                );
                                            }
                                        })() : (
                                            <Typography variant="body2" sx={{ color: 'text.secondary', fontStyle: 'italic' }}>
                                                None
                                            </Typography>
                                        )}
                                    </Box>
                                </Grid>
                            </Grid>
                        </CardContent>
                    </Card>
                </Grid>

                {/* Operating System Information */}
                <Grid item xs={12} md={6}>
                    <Card sx={{ height: '100%' }}>
                        <CardContent>
                            <Typography variant="subtitle1" sx={{ mb: 2, display: 'flex', alignItems: 'center', gap: 2, fontWeight: 'bold', fontSize: '1.1rem' }}>
                                <ComputerIcon sx={{ mr: 1 }} />
                                {t('hostDetail.osInfo', 'Operating System')}
                                <Typography variant="caption" color="textSecondary">
                                    {t('hosts.updated', 'Updated')}: {formatTimestamp(host.os_version_updated_at)}
                                </Typography>
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
                                {host.os_details && (
                                    <Grid item xs={12}>
                                        <Typography variant="body2" color="textSecondary" sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                                            {t('hostDetail.osDetails', 'Additional Details')}
                                            <IconButton 
                                                size="small" 
                                                onClick={() => handleShowDialog(t('hostDetail.additionalOSDetails', 'Additional OS Details'), host.os_details || '')}
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

                {/* Tags */}
                <Grid item xs={12} md={6}>
                    <Card>
                        <CardContent>
                            <Typography variant="subtitle1" sx={{ mb: 2, display: 'flex', alignItems: 'center', fontWeight: 'bold', fontSize: '1.1rem' }}>
                                <LocalOfferIcon sx={{ mr: 1 }} />
                                {t('hostDetail.tags', 'Tags')}
                            </Typography>
                            <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 1, mb: 2 }}>
                                {hostTags.map(tag => (
                                    <Chip
                                        key={tag.id}
                                        label={tag.name}
                                        onDelete={() => handleRemoveTag(tag.id)}
                                        deleteIcon={<DeleteIcon />}
                                        variant="outlined"
                                    />
                                ))}
                                {hostTags.length === 0 && (
                                    <Typography variant="body2" color="textSecondary">
                                        {t('hostDetail.noTags', 'No tags assigned')}
                                    </Typography>
                                )}
                            </Box>
                            <Box sx={{ display: 'flex', gap: 1, alignItems: 'center' }}>
                                <FormControl size="small" sx={{ minWidth: 200 }}>
                                    <InputLabel>{t('hostDetail.addTag', 'Add Tag')}</InputLabel>
                                    <Select
                                        value={selectedTagToAdd}
                                        onChange={(e) => setSelectedTagToAdd(Number(e.target.value))}
                                        label={t('hostDetail.addTag', 'Add Tag')}
                                    >
                                        {availableTags.map(tag => (
                                            <MenuItem key={tag.id} value={tag.id}>
                                                {tag.name}
                                            </MenuItem>
                                        ))}
                                    </Select>
                                </FormControl>
                                <Button
                                    variant="contained"
                                    onClick={handleAddTag}
                                    disabled={!selectedTagToAdd}
                                    size="small"
                                >
                                    {t('common.add', 'Add')}
                                </Button>
                            </Box>
                        </CardContent>
                    </Card>
                </Grid>
                </Grid>
            )}

            {/* Hardware Tab */}
            {currentTab === 1 && (
                <Grid container spacing={3}>
                {/* Hardware Information */}
                <Grid item xs={12}>
                    <Card>
                        <CardContent>
                            <Typography variant="subtitle1" sx={{ mb: 2, display: 'flex', alignItems: 'center', gap: 2, fontWeight: 'bold', fontSize: '1.1rem' }}>
                                <MemoryIcon sx={{ mr: 1 }} />
                                {t('hostDetail.hardwareInfo', 'Hardware Information')}
                                <Typography variant="caption" color="textSecondary">
                                    {t('hosts.updated', 'Updated')}: {formatTimestamp(host.hardware_updated_at)}
                                </Typography>
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
                                        {getFilteredNetworkInterfaces(networkInterfaces).map((iface: NetworkInterfaceType, index: number) => (
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
                                                onClick={() => handleShowDialog('Additional Hardware Details', host.hardware_details || '')}
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
            )}

            {/* Software Tab */}
            {currentTab === 2 && (
                <Grid container spacing={3}>
                    <Grid item xs={12}>
                        <Card>
                            <CardContent>
                                <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 2 }}>
                                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
                                        <Typography variant="subtitle1" sx={{ display: 'flex', alignItems: 'center', fontWeight: 'bold', fontSize: '1.1rem' }}>
                                            <AppsIcon sx={{ mr: 1 }} />
                                            {t('hostDetail.softwarePackages', 'Software Packages')} ({getFilteredSoftwarePackages(softwarePackages).length})
                                        </Typography>
                                        <Typography variant="caption" color="textSecondary">
                                            {t('hosts.updated', 'Updated')}: {formatTimestamp(host.software_updated_at)}
                                        </Typography>
                                    </Box>
                                    <ToggleButtonGroup
                                        value={packageManagerFilter}
                                        exclusive
                                        onChange={(_, newFilter) => {
                                            if (newFilter !== null) {
                                                setPackageManagerFilter(newFilter);
                                            }
                                        }}
                                        size="small"
                                        sx={{ ml: 2 }}
                                    >
                                        <ToggleButton value="all" aria-label="all packages">
                                            {t('common.all', 'All')}
                                        </ToggleButton>
                                        {getPackageManagers(softwarePackages).map((manager) => (
                                            <ToggleButton key={manager} value={manager} aria-label={`${manager} packages`}>
                                                {manager}
                                            </ToggleButton>
                                        ))}
                                    </ToggleButtonGroup>
                                </Box>
                                {getFilteredSoftwarePackages(softwarePackages).length === 0 ? (
                                    <Typography variant="body2" color="textSecondary" sx={{ fontStyle: 'italic', textAlign: 'center', py: 2 }}>
                                        {t('hostDetail.noSoftwareFound', 'No software packages found')}
                                    </Typography>
                                ) : (
                                    <Grid container spacing={2}>
                                        {getFilteredSoftwarePackages(softwarePackages).map((pkg: SoftwarePackage, index: number) => (
                                            <Grid item xs={12} sm={6} md={4} key={pkg.id || index}>
                                                <Card sx={{ backgroundColor: 'grey.900', height: '100%' }}>
                                                    <CardContent sx={{ p: 2 }}>
                                                        <Typography variant="subtitle2" sx={{ fontWeight: 'bold', mb: 1, wordBreak: 'break-word' }}>
                                                            {pkg.package_name || t('common.unknown', 'Unknown')}
                                                        </Typography>
                                                        {pkg.version && (
                                                            <Typography variant="body2" color="textSecondary" sx={{ mb: 0.5 }}>
                                                                {t('hostDetail.version', 'Version')}: {pkg.version}
                                                            </Typography>
                                                        )}
                                                        {pkg.package_manager && (
                                                            <Chip 
                                                                label={pkg.package_manager}
                                                                color="primary"
                                                                size="small"
                                                                sx={{ mb: 1 }}
                                                            />
                                                        )}
                                                        {pkg.description && (
                                                            <Typography variant="body2" color="textSecondary" sx={{ 
                                                                fontSize: '0.75rem', 
                                                                mt: 1,
                                                                overflow: 'hidden',
                                                                textOverflow: 'ellipsis',
                                                                display: '-webkit-box',
                                                                WebkitLineClamp: 3,
                                                                WebkitBoxOrient: 'vertical'
                                                            }}>
                                                                {pkg.description}
                                                            </Typography>
                                                        )}
                                                        {(pkg.size_bytes || pkg.install_date || pkg.vendor) && (
                                                            <Box sx={{ mt: 1, pt: 1, borderTop: '1px solid', borderColor: 'grey.700' }}>
                                                                {pkg.size_bytes && (
                                                                    <Typography variant="body2" color="textSecondary" sx={{ fontSize: '0.7rem' }}>
                                                                        {t('hostDetail.size', 'Size')}: {formatBytesWithCommas(pkg.size_bytes)}
                                                                    </Typography>
                                                                )}
                                                                {pkg.install_date && (
                                                                    <Typography variant="body2" color="textSecondary" sx={{ fontSize: '0.7rem' }}>
                                                                        {t('hostDetail.installed', 'Installed')}: {formatDate(pkg.install_date)}
                                                                    </Typography>
                                                                )}
                                                                {pkg.vendor && (
                                                                    <Typography variant="body2" color="textSecondary" sx={{ fontSize: '0.7rem' }}>
                                                                        {t('hostDetail.vendor', 'Vendor')}: {pkg.vendor}
                                                                    </Typography>
                                                                )}
                                                            </Box>
                                                        )}
                                                    </CardContent>
                                                </Card>
                                            </Grid>
                                        ))}
                                    </Grid>
                                )}
                            </CardContent>
                        </Card>
                    </Grid>
                </Grid>
            )}

            {/* Access Tab */}
            {currentTab === 3 && (
                <Grid container spacing={3}>
                    {/* User Accounts */}
                    <Grid item xs={12}>
                        <Card>
                            <CardContent>
                                <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 2 }}>
                                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
                                        <Typography variant="subtitle1" sx={{ display: 'flex', alignItems: 'center', fontWeight: 'bold', fontSize: '1.1rem' }}>
                                            <PersonIcon sx={{ mr: 1 }} />
                                            {t('hostDetail.userAccounts', 'User Accounts')} ({getFilteredUsers(userAccounts).length})
                                        </Typography>
                                        <Typography variant="caption" color="textSecondary">
                                            {t('hosts.updated', 'Updated')}: {formatTimestamp(host.user_access_updated_at)}
                                        </Typography>
                                    </Box>
                                    <ToggleButtonGroup
                                        value={userFilter}
                                        exclusive
                                        onChange={(_, newFilter) => {
                                            if (newFilter !== null) {
                                                setUserFilter(newFilter);
                                            }
                                        }}
                                        size="small"
                                        sx={{ ml: 2 }}
                                    >
                                        <ToggleButton value="regular" aria-label="regular users">
                                            {t('hostDetail.regularUsers', 'Regular')}
                                        </ToggleButton>
                                        <ToggleButton value="system" aria-label="system users">
                                            {t('hostDetail.systemUsers', 'System')}
                                        </ToggleButton>
                                        <ToggleButton value="all" aria-label="all users">
                                            {t('hostDetail.allUsers', 'All')}
                                        </ToggleButton>
                                    </ToggleButtonGroup>
                                </Box>
                                {getFilteredUsers(userAccounts).length === 0 ? (
                                    <Typography variant="body2" color="textSecondary" sx={{ fontStyle: 'italic', textAlign: 'center', py: 2 }}>
                                        {t('hostDetail.noUsersFound', 'No user accounts found')}
                                    </Typography>
                                ) : (
                                    <Grid container spacing={2}>
                                        {getFilteredUsers(userAccounts).map((user: UserAccount, index: number) => (
                                            <Grid item xs={12} sm={6} md={4} key={user.id || index}>
                                                <Card sx={{ backgroundColor: 'grey.900', height: '100%' }}>
                                                    <CardContent sx={{ p: 2 }}>
                                                        <Typography variant="subtitle2" sx={{ fontWeight: 'bold', mb: 1 }}>
                                                            {user.username}
                                                        </Typography>
                                                        <Typography variant="body2" color="textSecondary" sx={{ mb: 0.5 }}>
                                                            UID: {user.uid !== undefined ? user.uid : t('common.notAvailable')}
                                                        </Typography>
                                                        {user.home_directory && (
                                                            <Typography variant="body2" color="textSecondary" sx={{ mb: 0.5, wordBreak: 'break-all' }}>
                                                                {t('hostDetail.homeDir', 'Home')}: {user.home_directory}
                                                            </Typography>
                                                        )}
                                                        {user.shell && (
                                                            <Typography variant="body2" color="textSecondary" sx={{ mb: 0.5 }}>
                                                                {t('hostDetail.shell', 'Shell')}: {user.shell}
                                                            </Typography>
                                                        )}
                                                        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mt: 1, mb: 1 }}>
                                                            <Chip 
                                                                label={user.is_system_user ? t('hostDetail.systemUser', 'System') : t('hostDetail.regularUser', 'Regular')}
                                                                color={user.is_system_user ? 'default' : 'primary'}
                                                                size="small"
                                                            />
                                                        </Box>
                                                        {user.groups && user.groups.length > 0 && (
                                                            <Box sx={{ mt: 1 }}>
                                                                <Typography variant="body2" color="textSecondary" sx={{ mb: 0.5, fontSize: '0.75rem' }}>
                                                                    {t('hostDetail.memberOfGroups', 'Groups')}:
                                                                </Typography>
                                                                <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.5, maxHeight: expandedUserGroups.has(user.id) ? 'none' : '60px', overflow: 'auto' }}>
                                                                    {(expandedUserGroups.has(user.id) ? user.groups : user.groups.slice(0, 6)).map((groupName: string, groupIndex: number) => (
                                                                        <Chip 
                                                                            key={groupIndex}
                                                                            label={groupName}
                                                                            size="small"
                                                                            variant="outlined"
                                                                            color="secondary"
                                                                            sx={{ 
                                                                                fontSize: '0.7rem', 
                                                                                height: '20px',
                                                                                '& .MuiChip-label': { px: 1 }
                                                                            }}
                                                                        />
                                                                    ))}
                                                                    {user.groups.length > 6 && !expandedUserGroups.has(user.id) && (
                                                                        <Chip 
                                                                            label={`+${user.groups.length - 6}`}
                                                                            size="small"
                                                                            variant="outlined"
                                                                            color="info"
                                                                            sx={{ 
                                                                                fontSize: '0.7rem', 
                                                                                height: '20px',
                                                                                '& .MuiChip-label': { px: 1 },
                                                                                cursor: 'pointer'
                                                                            }}
                                                                            onClick={() => {
                                                                                setExpandedUserGroups(prev => new Set(Array.from(prev).concat([user.id || 0])));
                                                                            }}
                                                                        />
                                                                    )}
                                                                    {expandedUserGroups.has(user.id) && (
                                                                        <Chip 
                                                                            label={t('common.less', 'less')}
                                                                            size="small"
                                                                            variant="outlined"
                                                                            color="default"
                                                                            sx={{ 
                                                                                fontSize: '0.7rem', 
                                                                                height: '20px',
                                                                                '& .MuiChip-label': { px: 1 },
                                                                                cursor: 'pointer'
                                                                            }}
                                                                            onClick={() => {
                                                                                setExpandedUserGroups(prev => {
                                                                                    const newSet = new Set(prev);
                                                                                    newSet.delete(user.id);
                                                                                    return newSet;
                                                                                });
                                                                            }}
                                                                        />
                                                                    )}
                                                                </Box>
                                                            </Box>
                                                        )}
                                                    </CardContent>
                                                </Card>
                                            </Grid>
                                        ))}
                                    </Grid>
                                )}
                            </CardContent>
                        </Card>
                    </Grid>

                    {/* User Groups */}
                    <Grid item xs={12}>
                        <Card>
                            <CardContent>
                                <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 2 }}>
                                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
                                        <Typography variant="subtitle1" sx={{ display: 'flex', alignItems: 'center', fontWeight: 'bold', fontSize: '1.1rem' }}>
                                            <GroupIcon sx={{ mr: 1 }} />
                                            {t('hostDetail.userGroups', 'User Groups')} ({getFilteredGroups(userGroups).length})
                                        </Typography>
                                        <Typography variant="caption" color="textSecondary">
                                            {t('hosts.updated', 'Updated')}: {formatTimestamp(host.user_access_updated_at)}
                                        </Typography>
                                    </Box>
                                    <ToggleButtonGroup
                                        value={groupFilter}
                                        exclusive
                                        onChange={(_, newFilter) => {
                                            if (newFilter !== null) {
                                                setGroupFilter(newFilter);
                                            }
                                        }}
                                        size="small"
                                        sx={{ ml: 2 }}
                                    >
                                        <ToggleButton value="regular" aria-label="regular groups">
                                            {t('hostDetail.regularGroups', 'Regular')}
                                        </ToggleButton>
                                        <ToggleButton value="system" aria-label="system groups">
                                            {t('hostDetail.systemGroups', 'System')}
                                        </ToggleButton>
                                        <ToggleButton value="all" aria-label="all groups">
                                            {t('hostDetail.allGroups', 'All')}
                                        </ToggleButton>
                                    </ToggleButtonGroup>
                                </Box>
                                {getFilteredGroups(userGroups).length === 0 ? (
                                    <Typography variant="body2" color="textSecondary" sx={{ fontStyle: 'italic', textAlign: 'center', py: 2 }}>
                                        {t('hostDetail.noGroupsFound', 'No user groups found')}
                                    </Typography>
                                ) : (
                                    <Grid container spacing={2}>
                                        {getFilteredGroups(userGroups).map((group: UserGroup, index: number) => (
                                            <Grid item xs={12} sm={6} md={4} key={group.id || index}>
                                                <Card sx={{ backgroundColor: 'grey.900', height: '100%' }}>
                                                    <CardContent sx={{ p: 2 }}>
                                                        <Typography variant="subtitle2" sx={{ fontWeight: 'bold', mb: 1 }}>
                                                            {group.group_name}
                                                        </Typography>
                                                        <Typography variant="body2" color="textSecondary" sx={{ mb: 0.5 }}>
                                                            GID: {group.gid !== undefined ? group.gid : t('common.notAvailable')}
                                                        </Typography>
                                                        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mt: 1, mb: 1 }}>
                                                            <Chip 
                                                                label={group.is_system_group ? t('hostDetail.systemGroup', 'System') : t('hostDetail.regularGroup', 'Regular')}
                                                                color={group.is_system_group ? 'default' : 'primary'}
                                                                size="small"
                                                            />
                                                        </Box>
                                                        {group.users && group.users.length > 0 && (
                                                            <Box sx={{ mt: 1 }}>
                                                                <Typography variant="body2" color="textSecondary" sx={{ mb: 0.5, fontSize: '0.75rem' }}>
                                                                    {t('hostDetail.groupMembers', 'Members')}:
                                                                </Typography>
                                                                <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.5, maxHeight: expandedGroupUsers.has(group.id) ? 'none' : '60px', overflow: 'auto' }}>
                                                                    {(expandedGroupUsers.has(group.id) ? group.users : group.users.slice(0, 6)).map((userName: string, userIndex: number) => (
                                                                        <Chip 
                                                                            key={userIndex}
                                                                            label={userName}
                                                                            size="small"
                                                                            variant="outlined"
                                                                            color="secondary"
                                                                            sx={{ 
                                                                                fontSize: '0.7rem', 
                                                                                height: '20px',
                                                                                '& .MuiChip-label': { px: 1 }
                                                                            }}
                                                                        />
                                                                    ))}
                                                                    {group.users.length > 6 && !expandedGroupUsers.has(group.id) && (
                                                                        <Chip 
                                                                            label={`+${group.users.length - 6}`}
                                                                            size="small"
                                                                            variant="outlined"
                                                                            color="info"
                                                                            sx={{ 
                                                                                fontSize: '0.7rem', 
                                                                                height: '20px',
                                                                                '& .MuiChip-label': { px: 1 },
                                                                                cursor: 'pointer'
                                                                            }}
                                                                            onClick={() => {
                                                                                setExpandedGroupUsers(prev => new Set(Array.from(prev).concat([group.id || 0])));
                                                                            }}
                                                                        />
                                                                    )}
                                                                    {expandedGroupUsers.has(group.id) && (
                                                                        <Chip 
                                                                            label={t('common.less', 'less')}
                                                                            size="small"
                                                                            variant="outlined"
                                                                            color="default"
                                                                            sx={{ 
                                                                                fontSize: '0.7rem', 
                                                                                height: '20px',
                                                                                '& .MuiChip-label': { px: 1 },
                                                                                cursor: 'pointer'
                                                                            }}
                                                                            onClick={() => {
                                                                                setExpandedGroupUsers(prev => {
                                                                                    const newSet = new Set(prev);
                                                                                    newSet.delete(group.id);
                                                                                    return newSet;
                                                                                });
                                                                            }}
                                                                        />
                                                                    )}
                                                                </Box>
                                                            </Box>
                                                        )}
                                                    </CardContent>
                                                </Card>
                                            </Grid>
                                        ))}
                                    </Grid>
                                )}
                            </CardContent>
                        </Card>
                    </Grid>
                </Grid>
            )}

            {/* Ubuntu Pro Tab */}
            {currentTab === getUbuntuProTabIndex() && ubuntuProInfo?.available && (
                <Grid container spacing={3}>
                    <Grid item xs={12}>
                        <Card>
                            <CardContent>
                                <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 2 }}>
                                    <Typography variant="h6" sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                                        <VerifiedUserIcon />
                                        {t('hostDetail.ubuntuProInfo', 'Ubuntu Pro Information')}
                                    </Typography>

                                    {/* Attach/Detach Button - only show if agent is privileged */}
                                    {host?.is_agent_privileged && (
                                        <Box>
                                            {ubuntuProAttaching && (
                                                <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                                                    <CircularProgress size={16} />
                                                    <Typography variant="body2" color="textSecondary">
                                                        {t('hostDetail.ubuntuProAttaching', 'Attaching...')}
                                                    </Typography>
                                                </Box>
                                            )}
                                            {ubuntuProDetaching && (
                                                <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                                                    <CircularProgress size={16} />
                                                    <Typography variant="body2" color="textSecondary">
                                                        {t('hostDetail.ubuntuProDetaching', 'Detaching...')}
                                                    </Typography>
                                                </Box>
                                            )}
                                            {!ubuntuProAttaching && !ubuntuProDetaching && (
                                                <>
                                                    {ubuntuProInfo.attached ? (
                                                        <Button
                                                            variant="outlined"
                                                            color="warning"
                                                            size="small"
                                                            onClick={handleUbuntuProDetach}
                                                            startIcon={<DeleteIcon />}
                                                        >
                                                            {t('hostDetail.ubuntuProDetach', 'Detach')}
                                                        </Button>
                                                    ) : (
                                                        <Button
                                                            variant="outlined"
                                                            color="primary"
                                                            size="small"
                                                            onClick={handleUbuntuProAttach}
                                                            startIcon={<VerifiedUserIcon />}
                                                        >
                                                            {t('hostDetail.ubuntuProAttach', 'Attach')}
                                                        </Button>
                                                    )}
                                                </>
                                            )}
                                        </Box>
                                    )}
                                </Box>

                                <Grid container spacing={2} sx={{ mt: 1 }}>
                                    <Grid item xs={12} md={6}>
                                        <Card variant="outlined" sx={{ mb: 2 }}>
                                            <CardContent>
                                                <Typography variant="h6" gutterBottom>
                                                    {t('hostDetail.subscriptionStatus', 'Subscription Status')}
                                                </Typography>
                                                <Table size="small">
                                                    <TableBody>
                                                        <TableRow>
                                                            <TableCell variant="head" sx={{ fontWeight: 'bold', color: 'textSecondary' }}>
                                                                {t('hostDetail.attached', 'Attached')}
                                                            </TableCell>
                                                            <TableCell>
                                                                <Chip
                                                                    label={ubuntuProInfo.attached ? t('common.yes', 'Yes') : t('common.no', 'No')}
                                                                    color={ubuntuProInfo.attached ? 'success' : 'default'}
                                                                    size="small"
                                                                />
                                                            </TableCell>
                                                        </TableRow>
                                                        {ubuntuProInfo.version && (
                                                            <TableRow>
                                                                <TableCell variant="head" sx={{ fontWeight: 'bold', color: 'textSecondary' }}>
                                                                    {t('hostDetail.version', 'Version')}
                                                                </TableCell>
                                                                <TableCell>{ubuntuProInfo.version}</TableCell>
                                                            </TableRow>
                                                        )}
                                                        {ubuntuProInfo.expires && (
                                                            <TableRow>
                                                                <TableCell variant="head" sx={{ fontWeight: 'bold', color: 'textSecondary' }}>
                                                                    {t('hostDetail.expires', 'Expires')}
                                                                </TableCell>
                                                                <TableCell>{new Date(ubuntuProInfo.expires).toLocaleDateString()}</TableCell>
                                                            </TableRow>
                                                        )}
                                                        {ubuntuProInfo.account_name && (
                                                            <TableRow>
                                                                <TableCell variant="head" sx={{ fontWeight: 'bold', color: 'textSecondary' }}>
                                                                    {t('hostDetail.accountName', 'Account Name')}
                                                                </TableCell>
                                                                <TableCell>{ubuntuProInfo.account_name}</TableCell>
                                                            </TableRow>
                                                        )}
                                                        {ubuntuProInfo.contract_name && (
                                                            <TableRow>
                                                                <TableCell variant="head" sx={{ fontWeight: 'bold', color: 'textSecondary' }}>
                                                                    {t('hostDetail.contractName', 'Contract Name')}
                                                                </TableCell>
                                                                <TableCell>{ubuntuProInfo.contract_name}</TableCell>
                                                            </TableRow>
                                                        )}
                                                        {ubuntuProInfo.tech_support_level && (
                                                            <TableRow>
                                                                <TableCell variant="head" sx={{ fontWeight: 'bold', color: 'textSecondary' }}>
                                                                    {t('hostDetail.techSupportLevel', 'Tech Support Level')}
                                                                </TableCell>
                                                                <TableCell>{ubuntuProInfo.tech_support_level}</TableCell>
                                                            </TableRow>
                                                        )}
                                                    </TableBody>
                                                </Table>
                                            </CardContent>
                                        </Card>
                                    </Grid>

                                    <Grid item xs={12} md={6}>
                                        <Card variant="outlined">
                                            <CardContent>
                                                <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 1 }}>
                                                    <Typography variant="h6">
                                                        {t('hostDetail.services', 'Services')}
                                                    </Typography>
                                                    <Box sx={{ display: 'flex', gap: 1 }}>
                                                        {servicesEditMode ? (
                                                            <>
                                                                <Button
                                                                    size="small"
                                                                    variant="contained"
                                                                    color="primary"
                                                                    onClick={handleServicesSave}
                                                                    disabled={servicesSaving || !host?.is_agent_privileged}
                                                                    startIcon={servicesSaving ? <CircularProgress size={16} /> : <SaveIcon />}
                                                                >
                                                                    {t('common.save', 'Save')}
                                                                </Button>
                                                                <Button
                                                                    size="small"
                                                                    variant="outlined"
                                                                    onClick={handleServicesEditToggle}
                                                                    disabled={servicesSaving}
                                                                    startIcon={<CancelIcon />}
                                                                >
                                                                    {t('common.cancel', 'Cancel')}
                                                                </Button>
                                                            </>
                                                        ) : (
                                                            host?.is_agent_privileged && ubuntuProInfo.attached && (
                                                                <IconButton
                                                                    size="small"
                                                                    onClick={handleServicesEditToggle}
                                                                    title={t('hostDetail.editServices', 'Edit services')}
                                                                >
                                                                    <EditIcon />
                                                                </IconButton>
                                                            )
                                                        )}
                                                    </Box>
                                                </Box>
                                                {servicesMessage && (
                                                    <Alert severity="info" sx={{ mb: 2 }}>
                                                        {servicesMessage}
                                                    </Alert>
                                                )}
                                                {ubuntuProInfo.services.length > 0 ? (
                                                    <Grid container spacing={1}>
                                                        {ubuntuProInfo.services
                                                            .sort((a, b) => {
                                                                // Sort: enabled first, then disabled, then n/a
                                                                const statusOrder = { 'enabled': 0, 'disabled': 1, 'n/a': 2 };
                                                                return statusOrder[a.status as keyof typeof statusOrder] - statusOrder[b.status as keyof typeof statusOrder];
                                                            })
                                                            .map((service, index) => (
                                                            <Grid item xs={12} key={index}>
                                                                <Card variant="outlined" sx={{ p: 1 }}>
                                                                    <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                                                                        <Box sx={{ flex: 1 }}>
                                                                            <Typography variant="subtitle2" sx={{ fontWeight: 'bold' }}>
                                                                                {service.name}
                                                                            </Typography>
                                                                            {service.description && (
                                                                                <Typography variant="caption" color="textSecondary">
                                                                                    {service.description}
                                                                                </Typography>
                                                                            )}
                                                                        </Box>
                                                                        <Box sx={{ display: 'flex', gap: 1, alignItems: 'center' }}>
                                                                            {servicesEditMode && service.status !== 'n/a' ? (
                                                                                <FormControlLabel
                                                                                    control={
                                                                                        <Checkbox
                                                                                            checked={editedServices[service.name] ?? (service.status === 'enabled')}
                                                                                            onChange={(e) => handleServiceToggle(service.name, e.target.checked)}
                                                                                            size="small"
                                                                                        />
                                                                                    }
                                                                                    label={editedServices[service.name] ?? (service.status === 'enabled') ? t('hostDetail.enabled', 'Enabled') : t('hostDetail.disabled', 'Disabled')}
                                                                                />
                                                                            ) : (
                                                                                <Chip
                                                                                    label={service.status === 'n/a' ? 'N/A' : (service.status === 'enabled' ? t('hostDetail.enabled', 'Enabled') : t('hostDetail.disabled', 'Disabled'))}
                                                                                    color={service.status === 'enabled' ? 'success' : service.status === 'n/a' ? 'default' : 'warning'}
                                                                                    size="small"
                                                                                />
                                                                            )}
                                                                            {service.entitled && (
                                                                                <Chip
                                                                                    label={t('hostDetail.entitled', 'Entitled')}
                                                                                    color="primary"
                                                                                    size="small"
                                                                                />
                                                                            )}
                                                                        </Box>
                                                                    </Box>
                                                                </Card>
                                                            </Grid>
                                                        ))}
                                                    </Grid>
                                                ) : (
                                                    <Typography variant="body2" color="textSecondary" sx={{ fontStyle: 'italic' }}>
                                                        {t('hostDetail.noServices', 'No services available')}
                                                    </Typography>
                                                )}
                                            </CardContent>
                                        </Card>
                                    </Grid>
                                </Grid>
                            </CardContent>
                        </Card>
                    </Grid>
                </Grid>
            )}

            {/* Diagnostics Tab */}
            {currentTab === getDiagnosticsTabIndex() && (
                <Grid container spacing={3}>
                    <Grid item xs={12}>
                        <Card>
                            <CardContent>
                                <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 2 }}>
                                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
                                        <Typography variant="subtitle1" sx={{ display: 'flex', alignItems: 'center', fontWeight: 'bold', fontSize: '1.1rem' }}>
                                            <MedicalServicesIcon sx={{ mr: 1 }} />
                                            {t('hostDetail.diagnosticsData', 'Diagnostics Data')}
                                        </Typography>
                                        {diagnosticsData.length > 0 && !isDiagnosticsProcessing && (
                                            <Typography variant="caption" color="textSecondary">
                                                {t('hosts.updated', 'Updated')}: {formatTimestamp(diagnosticsData[0]?.completed_at)}
                                            </Typography>
                                        )}
                                        {isDiagnosticsProcessing && (
                                            <Chip 
                                                label={t('hostDetail.processingDiagnostics', 'Processing...')}
                                                color="warning"
                                                size="small"
                                                sx={{ 
                                                    animation: 'pulse 1.5s ease-in-out infinite',
                                                    '@keyframes pulse': {
                                                        '0%': { opacity: 1 },
                                                        '50%': { opacity: 0.5 },
                                                        '100%': { opacity: 1 }
                                                    }
                                                }}
                                            />
                                        )}
                                        {host?.diagnostics_requested_at && host?.diagnostics_request_status !== 'pending' && (
                                            <Typography variant="caption" color="textSecondary" sx={{ ml: 1 }}>
                                                {t('hostDetail.lastRequested', 'Last requested')}: {formatTimestamp(host.diagnostics_requested_at)}
                                            </Typography>
                                        )}
                                    </Box>
                                    <Button
                                        variant="contained"
                                        startIcon={<RefreshIcon />}
                                        onClick={handleRequestDiagnostics}
                                        disabled={diagnosticsLoading}
                                        color="primary"
                                    >
                                        {diagnosticsLoading 
                                            ? t('hostDetail.requestingDiagnostics', 'Requesting...') 
                                            : t('hostDetail.requestHostData', 'Request Host Data')
                                        }
                                    </Button>
                                </Box>
                                
                                {diagnosticsData.length === 0 ? (
                                    <Box sx={{ textAlign: 'center', py: 4 }}>
                                        <Typography variant="body1" color="textSecondary" sx={{ mb: 2 }}>
                                            {t('hostDetail.noDiagnosticsData', 'No diagnostics data available for this host.')}
                                        </Typography>
                                        <Typography variant="body2" color="textSecondary">
                                            {t('hostDetail.clickRequestData', 'Click "Request Host Data" to collect diagnostic information from the agent.')}
                                        </Typography>
                                    </Box>
                                ) : (
                                    <Grid container spacing={2}>
                                        {diagnosticsData.map((diagnostic: DiagnosticReport, index: number) => (
                                            <Grid item xs={12} key={diagnostic.id || index}>
                                                <Card 
                                                    sx={{ 
                                                        backgroundColor: 'grey.900',
                                                        cursor: 'pointer',
                                                        '&:hover': {
                                                            backgroundColor: 'grey.800'
                                                        }
                                                    }}
                                                    onClick={() => handleViewDiagnosticDetail(diagnostic.id)}
                                                >
                                                    <CardContent sx={{ p: 2 }}>
                                                        <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 2 }}>
                                                            <Box>
                                                                <Typography variant="subtitle1" sx={{ fontWeight: 'bold' }}>
                                                                    {t('hostDetail.diagnosticReport', 'Diagnostic Report')} #{diagnostic.collection_id?.substring(0, 8) || 'Unknown'}
                                                                </Typography>
                                                                <Typography variant="body2" color="textSecondary">
                                                                    {t('hostDetail.collectedAt', 'Collected')}: {formatDate(diagnostic.completed_at)}
                                                                </Typography>
                                                            </Box>
                                                            <IconButton
                                                                size="small"
                                                                onClick={(e) => {
                                                                    e.stopPropagation();
                                                                    handleDeleteDiagnostic(diagnostic.id);
                                                                }}
                                                                sx={{ 
                                                                    ml: 2,
                                                                    color: 'white',
                                                                    '&:hover': {
                                                                        backgroundColor: 'rgba(255, 255, 255, 0.1)'
                                                                    }
                                                                }}
                                                            >
                                                                <DeleteIcon />
                                                            </IconButton>
                                                        </Box>
                                                        
                                                        {/* System Logs Section */}
                                                        {diagnostic.system_logs && (
                                                            <Box sx={{ mb: 2 }}>
                                                                <Typography variant="subtitle2" sx={{ fontWeight: 'bold', mb: 1 }}>
                                                                    {t('hostDetail.systemLogs', 'System Logs')}
                                                                </Typography>
                                                                <Paper sx={{ p: 2, backgroundColor: 'grey.800', maxHeight: 200, overflow: 'auto' }}>
                                                                    <Typography variant="body2" sx={{ fontFamily: 'monospace', whiteSpace: 'pre-wrap' }}>
                                                                        {typeof diagnostic.system_logs === 'string' 
                                                                            ? diagnostic.system_logs 
                                                                            : JSON.stringify(diagnostic.system_logs, null, 2)
                                                                        }
                                                                    </Typography>
                                                                </Paper>
                                                            </Box>
                                                        )}
                                                        
                                                        {/* Configuration Files Section */}
                                                        {diagnostic.configuration_files && (
                                                            <Box sx={{ mb: 2 }}>
                                                                <Typography variant="subtitle2" sx={{ fontWeight: 'bold', mb: 1 }}>
                                                                    {t('hostDetail.configurationFiles', 'Configuration Files')}
                                                                </Typography>
                                                                <Paper sx={{ p: 2, backgroundColor: 'grey.800', maxHeight: 200, overflow: 'auto' }}>
                                                                    <Typography variant="body2" sx={{ fontFamily: 'monospace', whiteSpace: 'pre-wrap' }}>
                                                                        {typeof diagnostic.configuration_files === 'string' 
                                                                            ? diagnostic.configuration_files 
                                                                            : JSON.stringify(diagnostic.configuration_files, null, 2)
                                                                        }
                                                                    </Typography>
                                                                </Paper>
                                                            </Box>
                                                        )}
                                                        
                                                        {/* Process List Section */}
                                                        {diagnostic.process_list && (
                                                            <Box sx={{ mb: 2 }}>
                                                                <Typography variant="subtitle2" sx={{ fontWeight: 'bold', mb: 1 }}>
                                                                    {t('hostDetail.processList', 'Process List')}
                                                                </Typography>
                                                                <Paper sx={{ p: 2, backgroundColor: 'grey.800', maxHeight: 200, overflow: 'auto' }}>
                                                                    <Typography variant="body2" sx={{ fontFamily: 'monospace', whiteSpace: 'pre-wrap' }}>
                                                                        {typeof diagnostic.process_list === 'string' 
                                                                            ? diagnostic.process_list 
                                                                            : JSON.stringify(diagnostic.process_list, null, 2)
                                                                        }
                                                                    </Typography>
                                                                </Paper>
                                                            </Box>
                                                        )}
                                                        
                                                        {/* System Information Section */}
                                                        {diagnostic.system_information && (
                                                            <Box>
                                                                <Typography variant="subtitle2" sx={{ fontWeight: 'bold', mb: 1 }}>
                                                                    {t('hostDetail.systemInformation', 'System Information')}
                                                                </Typography>
                                                                <Paper sx={{ p: 2, backgroundColor: 'grey.800', maxHeight: 200, overflow: 'auto' }}>
                                                                    <Typography variant="body2" sx={{ fontFamily: 'monospace', whiteSpace: 'pre-wrap' }}>
                                                                        {typeof diagnostic.system_information === 'string' 
                                                                            ? diagnostic.system_information 
                                                                            : JSON.stringify(diagnostic.system_information, null, 2)
                                                                        }
                                                                    </Typography>
                                                                </Paper>
                                                            </Box>
                                                        )}
                                                    </CardContent>
                                                </Card>
                                            </Grid>
                                        ))}
                                    </Grid>
                                )}
                            </CardContent>
                        </Card>
                    </Grid>
                </Grid>
            )}

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
                    <Typography variant="subtitle1" sx={{ fontWeight: 'bold', fontSize: '1.25rem' }}>{dialogTitle}</Typography>
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

            {/* Reboot Confirmation Dialog */}
            <Dialog
                open={rebootConfirmOpen}
                onClose={() => setRebootConfirmOpen(false)}
                aria-labelledby="reboot-dialog-title"
                aria-describedby="reboot-dialog-description"
            >
                <DialogTitle id="reboot-dialog-title">
                    {t('hosts.confirmReboot', 'Confirm System Reboot')}
                </DialogTitle>
                <DialogContent>
                    <Typography id="reboot-dialog-description">
                        {t('hosts.confirmRebootMessage', 'Are you sure you want to reboot {{hostname}}? The system will be unavailable for a few minutes.', { hostname: host?.fqdn })}
                    </Typography>
                </DialogContent>
                <DialogActions>
                    <Button onClick={() => setRebootConfirmOpen(false)}>
                        {t('common.cancel', 'Cancel')}
                    </Button>
                    <Button onClick={handleRebootConfirm} color="warning" variant="contained">
                        {t('hosts.reboot', 'Reboot')}
                    </Button>
                </DialogActions>
            </Dialog>

            {/* Shutdown Confirmation Dialog */}
            <Dialog
                open={shutdownConfirmOpen}
                onClose={() => setShutdownConfirmOpen(false)}
                aria-labelledby="shutdown-dialog-title"
                aria-describedby="shutdown-dialog-description"
            >
                <DialogTitle id="shutdown-dialog-title">
                    {t('hosts.confirmShutdown', 'Confirm System Shutdown')}
                </DialogTitle>
                <DialogContent>
                    <Typography id="shutdown-dialog-description">
                        {t('hosts.confirmShutdownMessage', 'Are you sure you want to shutdown {{hostname}}? The system will need to be manually restarted.', { hostname: host?.fqdn })}
                    </Typography>
                </DialogContent>
                <DialogActions>
                    <Button onClick={() => setShutdownConfirmOpen(false)}>
                        {t('common.cancel', 'Cancel')}
                    </Button>
                    <Button onClick={handleShutdownConfirm} color="error" variant="contained">
                        {t('hosts.shutdown', 'Shutdown')}
                    </Button>
                </DialogActions>
            </Dialog>

            {/* Delete Confirmation Dialog */}
            <Dialog
                open={deleteConfirmOpen}
                onClose={handleCancelDelete}
                maxWidth="sm"
                fullWidth
                PaperProps={{
                    sx: { backgroundColor: 'grey.900' }
                }}
            >
                <DialogTitle sx={{ fontWeight: 'bold', fontSize: '1.25rem' }}>
                    {t('hostDetail.deleteDiagnosticConfirm', 'Delete Diagnostic Report')}
                </DialogTitle>
                <DialogContent>
                    <Typography>
                        {t('hostDetail.deleteDiagnosticMessage', 'Are you sure you want to delete this diagnostic report? This action cannot be undone.')}
                    </Typography>
                </DialogContent>
                <DialogActions>
                    <Button onClick={handleCancelDelete}>
                        {t('common.cancel', 'Cancel')}
                    </Button>
                    <Button onClick={handleConfirmDelete} color="error" variant="contained">
                        {t('hosts.delete', 'Delete')}
                    </Button>
                </DialogActions>
            </Dialog>

            {/* Diagnostic Detail Modal */}
            <Dialog
                open={diagnosticDetailOpen}
                onClose={() => setDiagnosticDetailOpen(false)}
                maxWidth="lg"
                fullWidth
                scroll="paper"
            >
                <DialogTitle sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <Typography variant="subtitle1" sx={{ fontWeight: 'bold', fontSize: '1.25rem' }}>
                        {t('hostDetail.diagnosticDetailTitle', 'Diagnostic Report Details')}
                        {selectedDiagnostic && ` #${selectedDiagnostic.collection_id?.substring(0, 8) || 'Unknown'}`}
                    </Typography>
                    <IconButton onClick={() => setDiagnosticDetailOpen(false)} size="small">
                        <CloseIcon />
                    </IconButton>
                </DialogTitle>
                <DialogContent sx={{ p: 3 }}>
                    {diagnosticDetailLoading ? (
                        <Box sx={{ display: 'flex', justifyContent: 'center', py: 4 }}>
                            <CircularProgress />
                        </Box>
                    ) : selectedDiagnostic ? (
                        <Box>
                            {/* Diagnostic Report Metadata */}
                            <Card sx={{ mb: 3, backgroundColor: 'grey.800' }}>
                                <CardContent>
                                    <Grid container spacing={2}>
                                        <Grid item xs={12} sm={6}>
                                            <Typography variant="body2" color="textSecondary">
                                                {t('hostDetail.collectionId', 'Collection ID')}
                                            </Typography>
                                            <Typography variant="body1" sx={{ fontFamily: 'monospace' }}>
                                                {selectedDiagnostic.collection_id}
                                            </Typography>
                                        </Grid>
                                        <Grid item xs={12} sm={6}>
                                            <Typography variant="body2" color="textSecondary">
                                                {t('hostDetail.collectionStatus', 'Status')}
                                            </Typography>
                                            <Chip 
                                                label={selectedDiagnostic.status} 
                                                color={selectedDiagnostic.status === 'completed' ? 'success' : 'warning'} 
                                                size="small" 
                                            />
                                        </Grid>
                                        <Grid item xs={12} sm={6}>
                                            <Typography variant="body2" color="textSecondary">
                                                {t('hostDetail.requestedAt', 'Requested At')}
                                            </Typography>
                                            <Typography variant="body1">
                                                {formatDate(selectedDiagnostic.requested_at)}
                                            </Typography>
                                        </Grid>
                                        <Grid item xs={12} sm={6}>
                                            <Typography variant="body2" color="textSecondary">
                                                {t('hostDetail.completedAt', 'Completed At')}
                                            </Typography>
                                            <Typography variant="body1">
                                                {formatDate(selectedDiagnostic.completed_at)}
                                            </Typography>
                                        </Grid>
                                    </Grid>
                                </CardContent>
                            </Card>

                            {/* Diagnostic Data Sections */}
                            {selectedDiagnostic.diagnostic_data && (
                                <Box>
                                    {Object.entries(selectedDiagnostic.diagnostic_data).map(([key, value]) => {
                                        if (!value || (typeof value === 'object' && Object.keys(value).length === 0)) return null;
                                        
                                        const sectionTitle = t(`hostDetail.${key}`, key.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase()));
                                        
                                        return (
                                            <Card key={key} sx={{ mb: 2, backgroundColor: 'grey.700' }}>
                                                <CardContent>
                                                    <Typography variant="subtitle1" sx={{ mb: 2, fontWeight: 'bold', fontSize: '1.1rem' }}>
                                                        {sectionTitle}
                                                    </Typography>
                                                    <Paper sx={{ p: 2, backgroundColor: 'grey.900', color: 'white', maxHeight: 300, overflow: 'auto' }}>
                                                        <Typography variant="body2" sx={{ fontFamily: 'monospace', whiteSpace: 'pre-wrap' }}>
                                                            {typeof value === 'string' 
                                                                ? value 
                                                                : JSON.stringify(value, null, 2)
                                                            }
                                                        </Typography>
                                                    </Paper>
                                                </CardContent>
                                            </Card>
                                        );
                                    })}
                                </Box>
                            )}

                            {(!selectedDiagnostic.diagnostic_data || Object.keys(selectedDiagnostic.diagnostic_data).length === 0) && (
                                <Box sx={{ textAlign: 'center', py: 4 }}>
                                    <Typography variant="body1" color="textSecondary">
                                        {t('hostDetail.noDataAvailable', 'No data available')}
                                    </Typography>
                                </Box>
                            )}
                        </Box>
                    ) : null}
                </DialogContent>
                <DialogActions>
                    <Button onClick={() => setDiagnosticDetailOpen(false)}>
                        {t('common.close', 'Close')}
                    </Button>
                </DialogActions>
            </Dialog>

            {/* Ubuntu Pro Token Dialog */}
            <Dialog
                open={ubuntuProTokenDialog}
                onClose={handleUbuntuProTokenCancel}
                maxWidth="sm"
                fullWidth
            >
                <DialogTitle>
                    {t('hostDetail.ubuntuProAttachTitle', 'Attach Ubuntu Pro')}
                </DialogTitle>
                <DialogContent>
                    <Typography variant="body2" sx={{ mb: 2 }}>
                        {t('hostDetail.ubuntuProAttachDescription', 'Enter your Ubuntu Pro token to attach this system to your subscription.')}
                    </Typography>
                    <TextField
                        fullWidth
                        label={t('hostDetail.ubuntuProToken', 'Ubuntu Pro Token')}
                        value={ubuntuProToken}
                        onChange={(e) => setUbuntuProToken(e.target.value)}
                        placeholder="C1xxxxxxxxxxxxxxxxxxxxxxxxxx"
                        variant="outlined"
                        multiline={false}
                        sx={{ mt: 1 }}
                    />
                </DialogContent>
                <DialogActions>
                    <Button onClick={handleUbuntuProTokenCancel}>
                        {t('common.cancel', 'Cancel')}
                    </Button>
                    <Button
                        onClick={handleUbuntuProTokenSubmit}
                        variant="contained"
                        disabled={!ubuntuProToken.trim()}
                    >
                        {t('hostDetail.ubuntuProAttachConfirm', 'Attach')}
                    </Button>
                </DialogActions>
            </Dialog>

            {/* Success/Error Snackbar */}
            <Snackbar
                open={snackbarOpen}
                autoHideDuration={4000}
                onClose={handleCloseSnackbar}
                anchorOrigin={{ vertical: 'bottom', horizontal: 'center' }}
            >
                <Alert onClose={handleCloseSnackbar} severity={snackbarSeverity}>
                    {snackbarMessage}
                </Alert>
            </Snackbar>
        </Box>
    );
};

export default HostDetail;