import { useNavigate, useParams } from "react-router-dom";
import React, { useEffect, useState, useCallback, useMemo, useRef } from 'react';
import AntivirusStatusCard from '../Components/AntivirusStatusCard';
import CommercialAntivirusStatusCard from '../Components/CommercialAntivirusStatusCard';
import FirewallStatusCard from '../Components/FirewallStatusCard';
import GraylogAttachmentModal from '../Components/GraylogAttachmentModal';
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
import SystemUpdateAltIcon from '@mui/icons-material/SystemUpdateAlt';
import VerifiedUserIcon from '@mui/icons-material/VerifiedUser';
import EditIcon from '@mui/icons-material/Edit';
import SaveIcon from '@mui/icons-material/Save';
import CancelIcon from '@mui/icons-material/Cancel';
import AddIcon from '@mui/icons-material/Add';
import HistoryIcon from '@mui/icons-material/History';
import VisibilityIcon from '@mui/icons-material/Visibility';
import CertificateIcon from '@mui/icons-material/AdminPanelSettings';
import AssignmentIcon from '@mui/icons-material/Assignment';
import PlayArrowIcon from '@mui/icons-material/PlayArrow';
import StopIcon from '@mui/icons-material/Stop';
import SourceIcon from '@mui/icons-material/Source';
import ShieldIcon from '@mui/icons-material/Shield';
import { Dialog, DialogTitle, DialogContent, DialogContentText, DialogActions, Table, TableBody, TableRow, TableCell, ToggleButton, ToggleButtonGroup, Snackbar, TextField, List, ListItem, ListItemText, Divider, TableContainer, TableHead, InputAdornment, Pagination } from '@mui/material';
import { DataGrid, GridColDef, GridRowSelectionModel } from '@mui/x-data-grid';
import SearchIcon from '@mui/icons-material/Search';
import { useTranslation } from 'react-i18next';
import { useColumnVisibility } from '../Hooks/useColumnVisibility';
import { useTablePageSize } from '../hooks/useTablePageSize';
import ColumnVisibilityButton from '../Components/ColumnVisibilityButton';
import axiosInstance from '../Services/api';
import { hasPermission, SecurityRoles } from '../Services/permissions';

import { SysManageHost, StorageDevice as StorageDeviceType, NetworkInterface as NetworkInterfaceType, UserAccount, UserGroup, SoftwarePackage, PaginationInfo, DiagnosticReport, DiagnosticDetailResponse, UbuntuProInfo, doGetHostByID, doGetHostStorage, doGetHostNetwork, doGetHostUsers, doGetHostGroups, doGetHostSoftware, doGetHostDiagnostics, doRequestHostDiagnostics, doGetDiagnosticDetail, doDeleteDiagnostic, doRebootHost, doShutdownHost, doRequestPackages, doGetHostUbuntuPro, doAttachUbuntuPro, doDetachUbuntuPro, doEnableUbuntuProService, doDisableUbuntuProService, doRefreshUserAccessData, doRefreshSoftwareData, doRefreshUpdatesCheck, doRequestSystemInfo } from '../Services/hosts';
import { SysManageUser, doGetMe } from '../Services/users';
import { SecretResponse } from '../Services/secrets';
import { doCheckOpenTelemetryEligibility, doDeployOpenTelemetry, doGetOpenTelemetryStatus, doStartOpenTelemetry, doStopOpenTelemetry, doRestartOpenTelemetry, doConnectOpenTelemetryToGrafana, doDisconnectOpenTelemetryFromGrafana, doRemoveOpenTelemetry } from '../Services/opentelemetry';
import { doCheckGraylogHealth, doGetGraylogAttachment } from '../Services/graylog';
import ThirdPartyRepositories from './ThirdPartyRepositories';

// Certificate interface
interface Certificate {
    id: string;
    certificate_name: string;
    subject: string;
    issuer: string;
    not_before: string | null;
    not_after: string | null;
    serial_number: string;
    fingerprint_sha256: string;
    is_ca: boolean;
    key_usage: string | null;
    file_path: string;
    collected_at: string | null;
    is_expired: boolean;
    days_until_expiry: number | null;
    common_name: string | null;
}

interface HostRole {
    id: string;
    role: string;
    package_name: string;
    package_version: string | null;
    service_name: string | null;
    service_status: string | null;
    is_active: boolean;
    detected_at: string;
    updated_at: string;
}

const HostDetail = () => {
    const { hostId } = useParams<{ hostId: string }>();
    const [host, setHost] = useState<SysManageHost | null>(null);
    const [storageDevices, setStorageDevices] = useState<StorageDeviceType[]>([]);
    const [networkInterfaces, setNetworkInterfaces] = useState<NetworkInterfaceType[]>([]);
    const [userAccounts, setUserAccounts] = useState<UserAccount[]>([]);
    const [userGroups, setUserGroups] = useState<UserGroup[]>([]);
    const [softwarePackages, setSoftwarePackages] = useState<SoftwarePackage[]>([]);
    const [loadingSoftware, setLoadingSoftware] = useState<boolean>(false);
    const [softwarePagination, setSoftwarePagination] = useState<PaginationInfo>({
        page: 1,
        page_size: 100,
        total_items: 0,
        total_pages: 0,
        has_next: false,
        has_prev: false
    });
    const [softwareSearchTerm, setSoftwareSearchTerm] = useState<string>('');
    const [certificates, setCertificates] = useState<Certificate[]>([]);
    const [ubuntuProInfo, setUbuntuProInfo] = useState<UbuntuProInfo | null>(null);
    const [diagnosticsData, setDiagnosticsData] = useState<DiagnosticReport[]>([]);
    const [loading, setLoading] = useState<boolean>(true);
    const [error, setError] = useState<string | null>(null);
    const [hasAntivirusOsDefault, setHasAntivirusOsDefault] = useState<boolean>(false);

    // Check if OS supports third-party repositories
    const supportsThirdPartyRepos = useCallback(() => {
        if (!host?.platform_release && !host?.platform) return false;
        const platform = host.platform || '';
        const platformRelease = host.platform_release || '';
        // OpenBSD explicitly does not support third-party repositories by design
        if (platform.includes('OpenBSD') || platformRelease.includes('OpenBSD')) return false;
        return platform.includes('Ubuntu') ||
               platform.includes('Debian') ||
               platform.includes('Fedora') ||
               platform.includes('RHEL') ||
               platform.includes('CentOS') ||
               platform.includes('SUSE') ||
               platform.includes('openSUSE') ||
               platform.includes('macOS') ||
               platform.includes('Darwin') ||
               platform.includes('FreeBSD') ||
               platform.includes('NetBSD') ||
               platform.includes('Windows') ||
               platformRelease.includes('Ubuntu') ||
               platformRelease.includes('Debian') ||
               platformRelease.includes('Fedora') ||
               platformRelease.includes('RHEL') ||
               platformRelease.includes('CentOS') ||
               platformRelease.includes('SUSE') ||
               platformRelease.includes('openSUSE');
    }, [host]);

    // Tab names for URL hash (static tabs only - dynamic tabs handled separately)
    const getTabNames = useCallback(() => {
        const tabs = ['info', 'hardware', 'software', 'software-changes'];
        if (supportsThirdPartyRepos()) tabs.push('third-party-repos');
        tabs.push('access', 'security', 'certificates', 'server-roles');
        if (ubuntuProInfo?.available) tabs.push('ubuntu-pro');
        tabs.push('diagnostics');
        return tabs;
    }, [ubuntuProInfo, supportsThirdPartyRepos]);

    // Initialize tab from URL hash
    const getInitialTab = useCallback(() => {
        const hash = window.location.hash.slice(1);
        if (!hash) return 0;
        const tabs = getTabNames();
        const tabIndex = tabs.indexOf(hash);
        return tabIndex >= 0 ? tabIndex : 0;
    }, [getTabNames]);

    const [currentTab, setCurrentTab] = useState<number>(getInitialTab);
    const [diagnosticsLoading, setDiagnosticsLoading] = useState<boolean>(false);
    const [certificatesLoading, setCertificatesLoading] = useState<boolean>(false);
    const [roles, setRoles] = useState<HostRole[]>([]);
    const [rolesLoading, setRolesLoading] = useState<boolean>(false);
    const [selectedRoles, setSelectedRoles] = useState<string[]>([]);
    const [serviceControlLoading, setServiceControlLoading] = useState<boolean>(false);
    const [openTelemetryStatus, setOpenTelemetryStatus] = useState<{deployed: boolean, service_status: string, grafana_url: string | null, grafana_configured: boolean} | null>(null);
    const [openTelemetryLoading, setOpenTelemetryLoading] = useState<boolean>(false);
    const [graylogAttached, setGraylogAttached] = useState<boolean>(false);
    const [graylogLoading, setGraylogLoading] = useState<boolean>(false);
    const [graylogMechanism, setGraylogMechanism] = useState<string | null>(null);
    const [graylogTargetHostname, setGraylogTargetHostname] = useState<string | null>(null);
    const [graylogTargetIp, setGraylogTargetIp] = useState<string | null>(null);
    const [graylogPort, setGraylogPort] = useState<number | null>(null);
    const rolesRefreshInterval = useRef<ReturnType<typeof setInterval> | null>(null);
    const openTelemetryRefreshInterval = useRef<ReturnType<typeof setInterval> | null>(null);
    const graylogRefreshInterval = useRef<ReturnType<typeof setInterval> | null>(null);
    const [certificateFilter, setCertificateFilter] = useState<'all' | 'ca' | 'server' | 'client'>('server');
    const [certificatePaginationModel, setCertificatePaginationModel] = useState({ page: 0, pageSize: 10 });
    const [certificateSearchTerm, setCertificateSearchTerm] = useState<string>('');
    const [storageFilter, setStorageFilter] = useState<'all' | 'physical' | 'logical'>('physical');
    const [networkFilter, setNetworkFilter] = useState<'all' | 'active' | 'inactive'>('active');
    const [userFilter, setUserFilter] = useState<'all' | 'system' | 'regular'>('all');
    const [groupFilter, setGroupFilter] = useState<'all' | 'system' | 'regular'>('regular');
    const [dialogOpen, setDialogOpen] = useState<boolean>(false);
    const [dialogContent, setDialogContent] = useState<string>('');
    const [dialogTitle, setDialogTitle] = useState<string>('');
    const [expandedUserGroups, setExpandedUserGroups] = useState<Set<string>>(new Set());
    const [expandedGroupUsers, setExpandedGroupUsers] = useState<Set<string>>(new Set());
    const [deleteConfirmOpen, setDeleteConfirmOpen] = useState<boolean>(false);
    const [diagnosticToDelete, setDiagnosticToDelete] = useState<string | null>(null);
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
    const [ubuntuProDetachConfirmOpen, setUbuntuProDetachConfirmOpen] = useState<boolean>(false);

    // Ubuntu Pro service editing state
    const [servicesEditMode, setServicesEditMode] = useState<boolean>(false);
    const [editedServices, setEditedServices] = useState<{[serviceName: string]: boolean}>({});
    const [servicesSaving, setServicesSaving] = useState<boolean>(false);
    const [servicesMessage, setServicesMessage] = useState<string>('');

    // Package installation modal state
    const [packageInstallDialogOpen, setPackageInstallDialogOpen] = useState<boolean>(false);
    const packageSearchInputRef = useRef<HTMLInputElement>(null);

    // SSH Key management state
    const [sshKeyDialogOpen, setSshKeyDialogOpen] = useState<boolean>(false);
    const [selectedUser, setSelectedUser] = useState<UserAccount | null>(null);
    const [availableSSHKeys, setAvailableSSHKeys] = useState<SecretResponse[]>([]);
    const [filteredSSHKeys, setFilteredSSHKeys] = useState<SecretResponse[]>([]);
    const [selectedSSHKeys, setSelectedSSHKeys] = useState<string[]>([]);

    // Certificate management state
    const [addCertificateDialogOpen, setAddCertificateDialogOpen] = useState<boolean>(false);
    const [availableCertificates, setAvailableCertificates] = useState<SecretResponse[]>([]);
    const [filteredCertificates, setFilteredCertificates] = useState<SecretResponse[]>([]);
    const [selectedCertificates, setSelectedCertificates] = useState<string[]>([]);
    const [certificateDialogSearchTerm, setCertificateDialogSearchTerm] = useState<string>('');
    const [isCertificateSearching, setIsCertificateSearching] = useState<boolean>(false);
    const [sshKeySearchTerm, setSshKeySearchTerm] = useState<string>('');
    const [searchResults, setSearchResults] = useState<Array<{name: string, description?: string, version?: string}>>([]);
    const [selectedPackages, setSelectedPackages] = useState<Set<string>>(new Set());
    const [isSearching, setIsSearching] = useState<boolean>(false);

    // Tag-related state
    const [hostTags, setHostTags] = useState<Array<{id: string, name: string, description: string | null}>>([]);
    const [availableTags, setAvailableTags] = useState<Array<{id: string, name: string, description: string | null}>>([]);
    const [selectedTagToAdd, setSelectedTagToAdd] = useState<string>('');
    const [diagnosticDetailLoading, setDiagnosticDetailLoading] = useState<boolean>(false);

    // Permission states
    const [canEditTags, setCanEditTags] = useState<boolean>(false);
    const [canStopService, setCanStopService] = useState<boolean>(false);
    const [canStartService, setCanStartService] = useState<boolean>(false);
    const [canRestartService, setCanRestartService] = useState<boolean>(false);
    const [canAddPackage, setCanAddPackage] = useState<boolean>(false);
    const [canDeploySshKey, setCanDeploySshKey] = useState<boolean>(false);
    const [canDeployCertificate, setCanDeployCertificate] = useState<boolean>(false);
    const [canAttachUbuntuPro, setCanAttachUbuntuPro] = useState<boolean>(false);
    const [canDetachUbuntuPro, setCanDetachUbuntuPro] = useState<boolean>(false);
    const [canDeployAntivirus, setCanDeployAntivirus] = useState<boolean>(false);
    const [canEnableAntivirus, setCanEnableAntivirus] = useState<boolean>(false);
    const [canDisableAntivirus, setCanDisableAntivirus] = useState<boolean>(false);
    const [canRemoveAntivirus, setCanRemoveAntivirus] = useState<boolean>(false);
    const [antivirusRefreshTrigger, setAntivirusRefreshTrigger] = useState<number>(0);

    // OpenTelemetry deployment states
    const [canDeployOpenTelemetry, setCanDeployOpenTelemetry] = useState<boolean>(false);  // User has permission to see button
    const [openTelemetryEligible, setOpenTelemetryEligible] = useState<boolean>(false);  // Deployment is actually allowed
    const [openTelemetryDeploying, setOpenTelemetryDeploying] = useState<boolean>(false);

    // Graylog attachment states
    const [canAttachGraylog, setCanAttachGraylog] = useState<boolean>(false);  // Graylog integration enabled and healthy
    const [graylogEligible, setGraylogEligible] = useState<boolean>(false);  // Agent is privileged
    const [graylogAttachModalOpen, setGraylogAttachModalOpen] = useState<boolean>(false);

    // Installation history state
    interface InstallationHistoryItem {
        request_id: string;  // UUID that groups packages
        requested_by: string;
        status: string;
        operation_type: string;  // install or uninstall
        requested_at: string;
        completed_at?: string;
        result_log?: string;
        package_names: string;  // Comma-separated list of package names
    }
    const [installationHistory, setInstallationHistory] = useState<InstallationHistoryItem[]>([]);
    const [installationHistoryLoading, setInstallationHistoryLoading] = useState<boolean>(false);
    const [selectedInstallationLog, setSelectedInstallationLog] = useState<InstallationHistoryItem | null>(null);
    const [installationLogDialogOpen, setInstallationLogDialogOpen] = useState<boolean>(false);
    const [installationDeleteConfirmOpen, setInstallationDeleteConfirmOpen] = useState<boolean>(false);
    const [installationToDelete, setInstallationToDelete] = useState<InstallationHistoryItem | null>(null);

    // Uninstallation state
    const [uninstallConfirmOpen, setUninstallConfirmOpen] = useState<boolean>(false);
    const [packageToUninstall, setPackageToUninstall] = useState<SoftwarePackage | null>(null);

    // Request packages confirmation state
    const [requestPackagesConfirmOpen, setRequestPackagesConfirmOpen] = useState<boolean>(false);

    // Current user state
    const [currentUser, setCurrentUser] = useState<SysManageUser | null>(null);
    const navigate = useNavigate();
    const { t, i18n } = useTranslation();

    // Column visibility preferences for Certificates grid
    const {
        hiddenColumns: hiddenCertificatesColumns,
        setHiddenColumns: setHiddenCertificatesColumns,
        resetPreferences: resetCertificatesPreferences,
        getColumnVisibilityModel: getCertificatesColumnVisibilityModel,
    } = useColumnVisibility('hostdetail-certificates-grid');

    // Dynamic table page sizing based on window height
    const { pageSize, pageSizeOptions } = useTablePageSize({
        reservedHeight: 300,
        minRows: 5,
        maxRows: 100,
    });

    // Update pagination when pageSize from hook changes
    useEffect(() => {
        setCertificatePaginationModel(prev => ({ ...prev, pageSize }));
    }, [pageSize]);

    // Ensure current page size is always in options to avoid MUI warning
    const safePageSizeOptions = useMemo(() => {
        const currentPageSize = certificatePaginationModel.pageSize;
        if (!pageSizeOptions.includes(currentPageSize)) {
            return [...pageSizeOptions, currentPageSize].sort((a, b) => a - b);
        }
        return pageSizeOptions;
    }, [pageSizeOptions, certificatePaginationModel.pageSize]);

    // Helper functions to calculate dynamic tab indices
    const getSoftwareInstallsTabIndex = () => 3;
    const getThirdPartyReposTabIndex = () => supportsThirdPartyRepos() ? 4 : -1;
    const getAccessTabIndex = () => supportsThirdPartyRepos() ? 5 : 4;
    const getSecurityTabIndex = () => supportsThirdPartyRepos() ? 6 : 5;
    const getCertificatesTabIndex = () => supportsThirdPartyRepos() ? 7 : 6;
    const getServerRolesTabIndex = () => supportsThirdPartyRepos() ? 8 : 7;
    const getUbuntuProTabIndex = () => {
        if (!ubuntuProInfo?.available) return -1;
        return supportsThirdPartyRepos() ? 9 : 8;
    };
    const getDiagnosticsTabIndex = () => {
        const baseIndex = supportsThirdPartyRepos() ? 9 : 8;
        return ubuntuProInfo?.available ? baseIndex + 1 : baseIndex;
    };

    // Certificate-related functions
    const fetchCertificates = useCallback(async () => {
        if (!hostId) return;

        try {
            setCertificatesLoading(true);
            const response = await axiosInstance.get(`/api/host/${hostId}/certificates`);

            if (response.status === 200) {
                setCertificates(response.data.certificates || []);
            }
        } catch (error) {
            console.error('Error fetching certificates:', error);
            // Don't fail the whole page load for certificate errors
            setCertificates([]);
        } finally {
            setCertificatesLoading(false);
        }
    }, [hostId]);

    const requestCertificatesCollection = useCallback(async () => {
        if (!hostId) return;

        try {
            setCertificatesLoading(true);
            const response = await axiosInstance.post(`/api/host/${hostId}/request-certificates-collection`);

            if (response.status === 200) {
                setSnackbarMessage(t('hostDetail.certificateCollectionRequested', 'Certificate collection requested'));
                setSnackbarSeverity('success');
                setSnackbarOpen(true);

                // Refetch certificates after a short delay to allow collection to complete
                setTimeout(() => {
                    fetchCertificates();
                }, 3000);
            }
        } catch (error) {
            console.error('Error requesting certificate collection:', error);
            setSnackbarMessage(t('hostDetail.certificateCollectionError', 'Error requesting certificate collection'));
            setSnackbarSeverity('error');
            setSnackbarOpen(true);
        } finally {
            setCertificatesLoading(false);
        }
    }, [hostId, fetchCertificates, t]);

    // Role-related functions
    const fetchRoles = useCallback(async (showLoading: boolean = true) => {
        if (!hostId) return;
        try {
            if (showLoading) {
                setRolesLoading(true);
            }
            const response = await axiosInstance.get(`/api/host/${hostId}/roles`);
            if (response.status === 200) {
                setRoles(response.data.roles || []);
            }
        } catch (error) {
            console.error('Error fetching roles:', error);
            // Don't fail the whole page load for role errors
            setRoles([]);
        } finally {
            if (showLoading) {
                setRolesLoading(false);
            }
        }
    }, [hostId]);

    const requestRolesCollection = useCallback(async () => {
        if (!hostId) return;
        try {
            setRolesLoading(true);
            const response = await axiosInstance.post(`/api/host/${hostId}/request-roles-collection`);
            if (response.status === 200) {
                setSnackbarMessage(t('hostDetail.roleCollectionRequested', 'Role collection requested'));
                setSnackbarSeverity('success');
                setSnackbarOpen(true);
                // Refetch roles after a short delay to allow collection to complete
                setTimeout(() => {
                    fetchRoles();
                }, 3000);
            }
        } catch (error) {
            console.error('Error requesting role collection:', error);
            setSnackbarMessage(t('hostDetail.roleCollectionError', 'Error requesting role collection'));
            setSnackbarSeverity('error');
            setSnackbarOpen(true);
        } finally {
            setRolesLoading(false);
        }
    }, [hostId, fetchRoles, t]);

    const fetchOpenTelemetryStatus = useCallback(async () => {
        if (!hostId) return;
        try {
            setOpenTelemetryLoading(true);
            const status = await doGetOpenTelemetryStatus(hostId);
            setOpenTelemetryStatus(status);
        } catch (err) {
            console.error('Error fetching OpenTelemetry status:', err);
        } finally {
            setOpenTelemetryLoading(false);
        }
    }, [hostId]);

    const fetchGraylogAttachment = useCallback(async () => {
        if (!hostId) return;
        try {
            setGraylogLoading(true);
            const attachment = await doGetGraylogAttachment(hostId);
            setGraylogAttached(attachment.is_attached);
            setGraylogMechanism(attachment.mechanism);
            setGraylogTargetHostname(attachment.target_hostname);
            setGraylogTargetIp(attachment.target_ip);
            setGraylogPort(attachment.port);
        } catch (err) {
            console.error('Error fetching Graylog attachment:', err);
        } finally {
            setGraylogLoading(false);
        }
    }, [hostId]);

    // Service control handlers
    const handleRoleSelection = (roleId: string, checked: boolean) => {
        if (checked) {
            setSelectedRoles(prev => [...prev, roleId]);
        } else {
            setSelectedRoles(prev => prev.filter(id => id !== roleId));
        }
    };

    const handleSelectAllRoles = (checked: boolean) => {
        if (checked) {
            const selectableRoles = roles.filter(role => role.service_name && role.service_name.trim() !== '').map(role => role.id);
            setSelectedRoles(selectableRoles);
        } else {
            setSelectedRoles([]);
        }
    };

    const handleServiceControl = async (action: 'start' | 'stop' | 'restart') => {
        if (!hostId || selectedRoles.length === 0) return;

        try {
            setServiceControlLoading(true);
            const selectedRoleData = roles.filter(role => selectedRoles.includes(role.id));
            const serviceNames = selectedRoleData.map(role => role.service_name).filter(name => name);

            if (serviceNames.length === 0) {
                setSnackbarMessage(t('hostDetail.noServicesSelected', 'No services selected for control'));
                setSnackbarSeverity('warning');
                setSnackbarOpen(true);
                return;
            }

            const response = await axiosInstance.post(`/api/host/${hostId}/service-control`, {
                action,
                services: serviceNames
            });

            if (response.status === 200) {
                setSnackbarMessage(t(`hostDetail.service${action.charAt(0).toUpperCase() + action.slice(1)}Success`, `Service ${action} requested successfully`));
                setSnackbarSeverity('success');
                setSnackbarOpen(true);
                setSelectedRoles([]);

                // Refresh roles after a delay to get updated status
                setTimeout(() => {
                    fetchRoles();
                }, 3000);
            }
        } catch (error) {
            // nosemgrep: javascript.lang.security.audit.unsafe-formatstring.unsafe-formatstring
            console.error(`Error ${action}ing services:`, error);
            // nosemgrep: javascript.lang.security.audit.unsafe-formatstring.unsafe-formatstring
            setSnackbarMessage(t(`hostDetail.service${action.charAt(0).toUpperCase() + action.slice(1)}Error`, `Error ${action}ing services`));
            setSnackbarSeverity('error');
            setSnackbarOpen(true);
        } finally {
            setServiceControlLoading(false);
        }
    };

    // OpenTelemetry service control handlers
    const handleOpenTelemetryStart = async () => {
        if (!hostId) return;
        try {
            setOpenTelemetryLoading(true);
            await doStartOpenTelemetry(hostId);
            setSnackbarMessage(t('hostDetail.opentelemetryStartSuccess', 'OpenTelemetry service started successfully'));
            setSnackbarSeverity('success');
            setSnackbarOpen(true);
            // Refresh status after a delay
            setTimeout(() => fetchOpenTelemetryStatus(), 2000);
        } catch (error) {
            console.error('Error starting OpenTelemetry:', error);
            setSnackbarMessage(t('hostDetail.opentelemetryOperationFailed', 'OpenTelemetry operation failed'));
            setSnackbarSeverity('error');
            setSnackbarOpen(true);
        } finally {
            setOpenTelemetryLoading(false);
        }
    };

    const handleOpenTelemetryStop = async () => {
        if (!hostId) return;
        try {
            setOpenTelemetryLoading(true);
            await doStopOpenTelemetry(hostId);
            setSnackbarMessage(t('hostDetail.opentelemetryStopSuccess', 'OpenTelemetry service stopped successfully'));
            setSnackbarSeverity('success');
            setSnackbarOpen(true);
            // Refresh status after a delay
            setTimeout(() => fetchOpenTelemetryStatus(), 2000);
        } catch (error) {
            console.error('Error stopping OpenTelemetry:', error);
            setSnackbarMessage(t('hostDetail.opentelemetryOperationFailed', 'OpenTelemetry operation failed'));
            setSnackbarSeverity('error');
            setSnackbarOpen(true);
        } finally {
            setOpenTelemetryLoading(false);
        }
    };

    const handleOpenTelemetryRestart = async () => {
        if (!hostId) return;
        try {
            setOpenTelemetryLoading(true);
            await doRestartOpenTelemetry(hostId);
            setSnackbarMessage(t('hostDetail.opentelemetryRestartSuccess', 'OpenTelemetry service restarted successfully'));
            setSnackbarSeverity('success');
            setSnackbarOpen(true);
            // Refresh status after a delay
            setTimeout(() => fetchOpenTelemetryStatus(), 2000);
        } catch (error) {
            console.error('Error restarting OpenTelemetry:', error);
            setSnackbarMessage(t('hostDetail.opentelemetryOperationFailed', 'OpenTelemetry operation failed'));
            setSnackbarSeverity('error');
            setSnackbarOpen(true);
        } finally {
            setOpenTelemetryLoading(false);
        }
    };

    const handleOpenTelemetryConnect = async () => {
        if (!hostId) return;
        try {
            setOpenTelemetryLoading(true);
            await doConnectOpenTelemetryToGrafana(hostId);
            setSnackbarMessage(t('hostDetail.opentelemetryConnectSuccess', 'OpenTelemetry connected to Grafana successfully'));
            setSnackbarSeverity('success');
            setSnackbarOpen(true);
            // Refresh status after a delay
            setTimeout(() => fetchOpenTelemetryStatus(), 2000);
        } catch (error) {
            console.error('Error connecting OpenTelemetry to Grafana:', error);
            setSnackbarMessage(t('hostDetail.opentelemetryOperationFailed', 'OpenTelemetry operation failed'));
            setSnackbarSeverity('error');
            setSnackbarOpen(true);
        } finally {
            setOpenTelemetryLoading(false);
        }
    };

    const handleOpenTelemetryDisconnect = async () => {
        if (!hostId) return;
        try {
            setOpenTelemetryLoading(true);
            await doDisconnectOpenTelemetryFromGrafana(hostId);
            setSnackbarMessage(t('hostDetail.opentelemetryDisconnectSuccess', 'OpenTelemetry disconnected from Grafana successfully'));
            setSnackbarSeverity('success');
            setSnackbarOpen(true);
            // Refresh status after a delay
            setTimeout(() => fetchOpenTelemetryStatus(), 2000);
        } catch (error) {
            console.error('Error disconnecting OpenTelemetry from Grafana:', error);
            setSnackbarMessage(t('hostDetail.opentelemetryOperationFailed', 'OpenTelemetry operation failed'));
            setSnackbarSeverity('error');
            setSnackbarOpen(true);
        } finally {
            setOpenTelemetryLoading(false);
        }
    };

    const handleRemoveOpenTelemetry = async () => {
        if (!hostId) return;
        try {
            setOpenTelemetryLoading(true);
            await doRemoveOpenTelemetry(hostId);
            setSnackbarMessage(t('hostDetail.opentelemetryRemoveSuccess', 'OpenTelemetry removal queued successfully'));
            setSnackbarSeverity('success');
            setSnackbarOpen(true);
            // Refresh status after a delay
            setTimeout(() => fetchOpenTelemetryStatus(), 2000);
        } catch (error) {
            console.error('Error removing OpenTelemetry:', error);
            setSnackbarMessage(t('hostDetail.opentelemetryOperationFailed', 'OpenTelemetry operation failed'));
            setSnackbarSeverity('error');
            setSnackbarOpen(true);
        } finally {
            setOpenTelemetryLoading(false);
        }
    };

    // Auto-refresh functionality
    useEffect(() => {
        if (currentTab === getServerRolesTabIndex() && host && host.active) {
            // Start auto-refresh every 30 seconds (without loading indicator)
            const interval = setInterval(() => {
                fetchRoles(false);
            }, 30000);
            rolesRefreshInterval.current = interval;

            return () => {
                if (interval) {
                    clearInterval(interval);
                }
            };
        } else {
            // Clear interval when tab is not active or host is not active
            if (rolesRefreshInterval.current) {
                clearInterval(rolesRefreshInterval.current);
                rolesRefreshInterval.current = null;
            }
        }
    }, [currentTab, host?.active, host?.id]); // eslint-disable-line react-hooks/exhaustive-deps

    // Cleanup interval on unmount
    useEffect(() => {
        return () => {
            if (rolesRefreshInterval.current) {
                clearInterval(rolesRefreshInterval.current);
            }
        };
    }, []);

    // Fetch OpenTelemetry status when Info tab is active
    useEffect(() => {
        if (currentTab === 0 && host && host.active) {
            fetchOpenTelemetryStatus();
        }
    }, [currentTab, host?.active, host, fetchOpenTelemetryStatus]);

    // Auto-refresh OpenTelemetry status every 30 seconds when on Info tab
    useEffect(() => {
        if (currentTab === 0 && host && host.active) {
            // Start auto-refresh every 30 seconds
            const interval = setInterval(() => {
                fetchOpenTelemetryStatus();
            }, 30000);
            openTelemetryRefreshInterval.current = interval;

            return () => {
                if (interval) {
                    clearInterval(interval);
                }
            };
        } else {
            // Clear interval when tab is not active or host is not active
            if (openTelemetryRefreshInterval.current) {
                clearInterval(openTelemetryRefreshInterval.current);
                openTelemetryRefreshInterval.current = null;
            }
        }
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [currentTab, host?.active, host?.id, fetchOpenTelemetryStatus]);

    // Fetch Graylog attachment status when Info tab is active
    useEffect(() => {
        if (currentTab === 0 && host && host.active) {
            fetchGraylogAttachment();
        }
    }, [currentTab, host?.active, host, fetchGraylogAttachment]);

    // Auto-refresh Graylog status every 30 seconds when on Info tab
    useEffect(() => {
        if (currentTab === 0 && host && host.active) {
            // Start auto-refresh every 30 seconds
            const interval = setInterval(() => {
                fetchGraylogAttachment();
            }, 30000);
            graylogRefreshInterval.current = interval;

            return () => {
                if (interval) {
                    clearInterval(interval);
                }
            };
        } else {
            // Clear interval when tab is not active or host is not active
            if (graylogRefreshInterval.current) {
                clearInterval(graylogRefreshInterval.current);
                graylogRefreshInterval.current = null;
            }
        }
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [currentTab, host?.active, host?.id, fetchGraylogAttachment]);

    // Cleanup intervals on unmount
    useEffect(() => {
        return () => {
            if (openTelemetryRefreshInterval.current) {
                clearInterval(openTelemetryRefreshInterval.current);
            }
            if (graylogRefreshInterval.current) {
                clearInterval(graylogRefreshInterval.current);
            }
        };
    }, []);

    // Check permissions
    useEffect(() => {
        const checkPermissions = async () => {
            const [editTags, stopService, startService, restartService, addPackage, deploySshKey, deployCertificate, attachUbuntuPro, detachUbuntuPro, deployAntivirus, enableAntivirus, disableAntivirus, removeAntivirus] = await Promise.all([
                hasPermission(SecurityRoles.EDIT_TAGS),
                hasPermission(SecurityRoles.STOP_HOST_SERVICE),
                hasPermission(SecurityRoles.START_HOST_SERVICE),
                hasPermission(SecurityRoles.RESTART_HOST_SERVICE),
                hasPermission(SecurityRoles.ADD_PACKAGE),
                hasPermission(SecurityRoles.DEPLOY_SSH_KEY),
                hasPermission(SecurityRoles.DEPLOY_CERTIFICATE),
                hasPermission(SecurityRoles.ATTACH_UBUNTU_PRO),
                hasPermission(SecurityRoles.DETACH_UBUNTU_PRO),
                hasPermission(SecurityRoles.DEPLOY_ANTIVIRUS),
                hasPermission(SecurityRoles.ENABLE_ANTIVIRUS),
                hasPermission(SecurityRoles.DISABLE_ANTIVIRUS),
                hasPermission(SecurityRoles.REMOVE_ANTIVIRUS)
            ]);
            setCanEditTags(editTags);
            setCanStopService(stopService);
            setCanStartService(startService);
            setCanRestartService(restartService);
            setCanAddPackage(addPackage);
            setCanDeploySshKey(deploySshKey);
            setCanDeployCertificate(deployCertificate);
            setCanAttachUbuntuPro(attachUbuntuPro);
            setCanDetachUbuntuPro(detachUbuntuPro);
            setCanDeployAntivirus(deployAntivirus);
            setCanEnableAntivirus(enableAntivirus);
            setCanDisableAntivirus(disableAntivirus);
            setCanRemoveAntivirus(removeAntivirus);
        };
        checkPermissions();
    }, []);

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
                const hostData = await doGetHostByID(hostId);
                setHost(hostData);

                // Check if there's an antivirus default for this host's OS
                try {
                    // For macOS, use platform directly since platform_release contains version codenames
                    // For other OSes, try platform_release first, but fall back to platform if it's just a version number
                    let osName = '';

                    if (hostData.platform === 'macOS') {
                        osName = 'macOS';
                    } else {
                        osName = hostData.platform_release || '';

                        // If platform_release doesn't start with a letter (e.g., "7.7"), use platform instead
                        if (!osName || !/^[A-Za-z]/.test(osName)) {
                            osName = hostData.platform || '';
                        }

                        // Extract OS name without version (e.g., "Ubuntu 25.04" -> "Ubuntu")
                        // Match common patterns: "Ubuntu X.Y", "FreeBSD X.Y-RELEASE", "NetBSD X.Y", etc.
                        const match = osName.match(/^([A-Za-z]+)/);
                        if (match) {
                            osName = match[1];
                        }
                    }

                    if (osName) {
                        const response = await axiosInstance.get(`/api/antivirus-defaults/${osName}`);
                        setHasAntivirusOsDefault(response.data && response.data.antivirus_package !== null);
                    } else {
                        setHasAntivirusOsDefault(false);
                    }
                } catch {
                    // If 404 or any error, assume no default is configured
                    setHasAntivirusOsDefault(false);
                }

                // Fetch normalized storage, network, user access, and diagnostics data
                // Note: Software packages are loaded lazily when the Software tab is opened (not here)
                try {
                    const [storageData, networkData, usersData, groupsData, diagnosticsData, currentUserData] = await Promise.all([
                        doGetHostStorage(hostId),
                        doGetHostNetwork(hostId),
                        doGetHostUsers(hostId),
                        doGetHostGroups(hostId),
                        doGetHostDiagnostics(hostId),
                        doGetMe()
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

                    // Software data will be loaded lazily when Software tab is opened

                    // Set diagnostics data
                    setDiagnosticsData(diagnosticsData);

                    // Set current user data
                    setCurrentUser(currentUserData);

                    // Fetch Ubuntu Pro data (only for Ubuntu hosts)
                    try {
                        if (hostData.platform?.toLowerCase().includes('ubuntu') ||
                            hostData.platform_release?.toLowerCase().includes('ubuntu')) {
                            const ubuntuProData = await doGetHostUbuntuPro(hostId);
                            setUbuntuProInfo(ubuntuProData);
                        }
                    } catch (error) {
                        // Ubuntu Pro data is optional, don't fail the whole page load
                        console.log('Ubuntu Pro data not available or failed to load:', error);
                    }

                    // Fetch certificates data
                    try {
                        await fetchCertificates();
                    } catch (error) {
                        // Certificates data is optional, don't fail the whole page load
                        console.log('Certificates data not available or failed to load:', error);
                    }
                    // Fetch roles data
                    try {
                        await fetchRoles();
                    } catch (error) {
                        // Roles data is optional, don't fail the whole page load
                        console.log('Roles data not available or failed to load:', error);
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
    }, [hostId, navigate, t, fetchCertificates, fetchRoles]);

    // Check OpenTelemetry eligibility when host is loaded
    useEffect(() => {
        const checkOpenTelemetryEligibility = async () => {
            if (!hostId || !host) return;

            // Don't check eligibility if host is not active (down)
            if (!host.active) {
                setCanDeployOpenTelemetry(false);
                setOpenTelemetryEligible(false);
                return;
            }

            try {
                const eligibility = await doCheckOpenTelemetryEligibility(hostId);
                setCanDeployOpenTelemetry(eligibility.has_permission || false);  // Show button if user has RBAC permission
                setOpenTelemetryEligible(eligibility.eligible || false);  // Enable button only if eligible to deploy
            } catch (error) {
                console.log('Failed to check OpenTelemetry eligibility:', error);
                setCanDeployOpenTelemetry(false);
                setOpenTelemetryEligible(false);
            }
        };

        checkOpenTelemetryEligibility();
    }, [hostId, host]);

    // Check Graylog eligibility when host is loaded
    useEffect(() => {
        const checkGraylogEligibility = async () => {
            if (!hostId || !host) return;

            // Don't check eligibility if host is not active (down)
            if (!host.active) {
                setCanAttachGraylog(false);
                setGraylogEligible(false);
                return;
            }

            try {
                // Check if Graylog integration is enabled and healthy
                const graylogHealth = await doCheckGraylogHealth();
                setCanAttachGraylog(graylogHealth.healthy);

                // Check if agent is running in privileged mode
                setGraylogEligible(host.is_agent_privileged || false);
            } catch (error) {
                console.log('Failed to check Graylog eligibility:', error);
                setCanAttachGraylog(false);
                setGraylogEligible(false);
            }
        };

        checkGraylogEligibility();
    }, [hostId, host]);

    // Tag-related functions
    const loadHostTags = useCallback(async () => {
        if (!hostId) return;

        try {
            const response = await axiosInstance.get(`/api/hosts/${hostId}/tags`);

            if (response.status === 200) {
                const tags = response.data;
                setHostTags(tags);
            }
        } catch (error) {
            console.error('Error loading host tags:', error);
        }
    }, [hostId]);

    const loadAvailableTags = useCallback(async () => {
        try {
            const response = await axiosInstance.get('/api/tags');
            
            if (response.status === 200) {
                const allTags = response.data;
                // Filter out tags that are already assigned to this host
                const available = allTags.filter((tag: {id: string, name: string, description: string | null}) =>
                    !hostTags.some(hostTag => hostTag.id === tag.id)
                );
                setAvailableTags(available);
            }
        } catch (error) {
            console.error('Error loading available tags:', error);
        }
    }, [hostTags]);

    // Installation history function
    const fetchInstallationHistory = useCallback(async () => {
        if (!hostId) return;

        setInstallationHistoryLoading(true);
        try {
            const response = await axiosInstance.get(`/api/packages/installation-history/${hostId}`);
            setInstallationHistory(response.data.installations || []);
        } catch (error) {
            console.error('Error fetching installation history:', error);
            setInstallationHistory([]);
        } finally {
            setInstallationHistoryLoading(false);
        }
    }, [hostId]);

    // Load tags when component mounts and when hostTags change
    useEffect(() => {
        if (hostId) {
            loadHostTags();
        }
    }, [hostId, loadHostTags]);

    useEffect(() => {
        loadAvailableTags();
    }, [hostTags, loadAvailableTags]);

    // Load software packages lazily when Software tab is selected (tab 2) or pagination changes
    useEffect(() => {
        const loadSoftwarePackages = async () => {
            if (currentTab === 2 && hostId) {
                try {
                    setLoadingSoftware(true);
                    const response = await doGetHostSoftware(
                        hostId,
                        softwarePagination.page,
                        softwarePagination.page_size,
                        softwareSearchTerm || undefined
                    );
                    setSoftwarePackages(response.items);
                    setSoftwarePagination(response.pagination);
                } catch (error) {
                    console.error('Failed to load software packages:', error);
                } finally {
                    setLoadingSoftware(false);
                }
            }
        };
        loadSoftwarePackages();
    }, [currentTab, hostId, softwarePagination.page, softwarePagination.page_size, softwareSearchTerm]);

    // Load installation history when Software Changes tab is selected
    useEffect(() => {
        if (currentTab === getSoftwareInstallsTabIndex()) {
            fetchInstallationHistory();
        }
    }, [currentTab, hostId, fetchInstallationHistory]);

    // Auto-refresh installation history every 30 seconds when on Software Changes tab
    useEffect(() => {
        let interval: ReturnType<typeof window.setInterval> | null = null;
        if (hostId && currentTab === getSoftwareInstallsTabIndex()) {
            interval = window.setInterval(async () => {
                try {
                    await fetchInstallationHistory();
                } catch (error) {
                    console.error('Auto-refresh error for installation history:', error);
                }
            }, 30000); // 30 seconds
        }
        return () => {
            if (interval) {
                window.clearInterval(interval);
            }
        };
    }, [hostId, currentTab, fetchInstallationHistory]);

    // Auto-refresh Ubuntu Pro information every 30 seconds
    useEffect(() => {
        let interval: ReturnType<typeof window.setInterval> | null = null;

        if (hostId && ubuntuProInfo?.available) {
            interval = window.setInterval(async () => {
                try {
                    const ubuntuProData = await doGetHostUbuntuPro(hostId);
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

    // Listen for hash changes (browser back/forward)
    useEffect(() => {
        const handleHashChange = () => {
            const hash = window.location.hash.slice(1);
            if (!hash) return;
            const tabs = getTabNames();
            const tabIndex = tabs.indexOf(hash);
            if (tabIndex >= 0) {
                setCurrentTab(tabIndex);
            }
        };

        window.addEventListener('hashchange', handleHashChange);
        return () => window.removeEventListener('hashchange', handleHashChange);
    }, [getTabNames]);

    // Recalculate current tab when host or ubuntuProInfo changes (handles dynamic tabs)
    useEffect(() => {
        const hash = window.location.hash.slice(1);
        if (!hash) return;
        const tabs = getTabNames();
        const tabIndex = tabs.indexOf(hash);
        if (tabIndex >= 0 && tabIndex !== currentTab) {
            setCurrentTab(tabIndex);
        }
    }, [host, ubuntuProInfo, getTabNames, currentTab]);

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

    const handleAddSSHKey = async (user: UserAccount) => {
        setSelectedUser(user);
        try {
            // Load available SSH keys
            const response = await axiosInstance.get('/api/secrets?type=ssh_key');
            const secrets = response.data;
            const sshKeys = secrets.filter((secret: SecretResponse) => secret.secret_type === 'ssh_key');
            setAvailableSSHKeys(sshKeys);
            setFilteredSSHKeys(sshKeys);
            setSelectedSSHKeys([]);
            setSshKeySearchTerm('');
            setSshKeyDialogOpen(true);
        } catch (error) {
            console.error('Failed to load SSH keys:', error);
            setSnackbarMessage(t('hostDetail.failedToLoadSSHKeys', 'Failed to load SSH keys'));
            setSnackbarSeverity('error');
            setSnackbarOpen(true);
        }
    };

    const handleSSHKeyDialogClose = () => {
        setSshKeyDialogOpen(false);
        setSelectedUser(null);
        setAvailableSSHKeys([]);
        setFilteredSSHKeys([]);
        setSelectedSSHKeys([]);
        setSshKeySearchTerm('');
    };

    const handleSSHKeySearch = () => {
        const searchTerm = sshKeySearchTerm.toLowerCase().trim();
        if (searchTerm === '') {
            setFilteredSSHKeys(availableSSHKeys);
        } else {
            const filtered = availableSSHKeys.filter((key) =>
                key.name.toLowerCase().includes(searchTerm) ||
                (key.filename && key.filename.toLowerCase().includes(searchTerm))
            );
            setFilteredSSHKeys(filtered);
        }
    };

    // Certificate management functions
    const handleCertificateDialogClose = () => {
        setAddCertificateDialogOpen(false);
        setAvailableCertificates([]);
        setFilteredCertificates([]);
        setSelectedCertificates([]);
        setCertificateDialogSearchTerm('');
    };

    const handleCertificateSearch = () => {
        const searchTerm = certificateDialogSearchTerm.toLowerCase().trim();
        if (searchTerm === '') {
            setFilteredCertificates(availableCertificates);
        } else {
            const filtered = availableCertificates.filter((cert) =>
                cert.name.toLowerCase().includes(searchTerm) ||
                (cert.filename && cert.filename.toLowerCase().includes(searchTerm))
            );
            setFilteredCertificates(filtered);
        }
    };

    const handleDeployCertificates = async () => {
        if (selectedCertificates.length === 0 || !host) return;

        try {
            const deployData = {
                host_id: host.id,
                secret_ids: selectedCertificates
            };

            await axiosInstance.post('/api/secrets/deploy-certificates', deployData);

            setSnackbarMessage(t('hostDetail.certificatesDeployedSuccess', 'Certificates deployment queued successfully'));
            setSnackbarSeverity('success');
            setSnackbarOpen(true);

            handleCertificateDialogClose();
        } catch (error: unknown) {
            console.error('Failed to deploy certificates:', error);
            let errorMessage = t('hostDetail.certificatesDeployedError', 'Failed to deploy certificates');
            if (error && typeof error === 'object' && 'response' in error) {
                const axiosError = error as { response?: { data?: { detail?: string } } };
                if (axiosError.response?.data?.detail) {
                    errorMessage = axiosError.response.data.detail;
                }
            }

            setSnackbarMessage(errorMessage);
            setSnackbarSeverity('error');
            setSnackbarOpen(true);
        }
    };

    const loadAvailableCertificates = async () => {
        try {
            setIsCertificateSearching(true);
            // Load available SSL certificates - same pattern as SSH keys
            const response = await axiosInstance.get('/api/secrets?type=ssl_certificate');
            const secrets = response.data;
            const certificates = secrets.filter((secret: SecretResponse) => secret.secret_type === 'ssl_certificate');
            setAvailableCertificates(certificates);
            setFilteredCertificates(certificates);
        } catch (error: unknown) {
            console.error('Failed to load certificates:', error);
            setSnackbarMessage(t('hostDetail.certificatesLoadError', 'Failed to load certificates from vault'));
            setSnackbarSeverity('error');
            setSnackbarOpen(true);
        } finally {
            setIsCertificateSearching(false);
        }
    };

    // Certificate DataGrid columns definition for vault certificates
    const vaultCertificateColumns: GridColDef[] = [
        {
            field: 'name',
            headerName: t('secrets.secretName', 'Secret Name'),
            width: 250,
            flex: 1,
        },
        {
            field: 'filename',
            headerName: t('secrets.secretFilename', 'Filename'),
            width: 250,
            flex: 1,
        },
        {
            field: 'secret_subtype',
            headerName: t('secrets.secretSubtype', 'Secret Subtype'),
            width: 150,
            renderCell: (params) => (
                <Typography variant="body2">
                    {t(`secrets.cert_type.${params.value}`, params.value)}
                </Typography>
            ),
        },
        {
            field: 'created_at',
            headerName: t('secrets.createdAt', 'Created'),
            width: 180,
            renderCell: (params) => (
                <Typography variant="body2">
                    {new Date(params.value).toLocaleString()}
                </Typography>
            ),
        },
    ];

    // SSH Key DataGrid columns definition
    const sshKeyColumns: GridColDef[] = [
        {
            field: 'name',
            headerName: t('secrets.secretName', 'Secret Name'),
            width: 250,
            flex: 1,
        },
        {
            field: 'filename',
            headerName: t('secrets.secretFilename', 'Filename'),
            width: 250,
            flex: 1,
        },
        {
            field: 'secret_subtype',
            headerName: t('secrets.secretSubtype', 'Secret Subtype'),
            width: 150,
            renderCell: (params) => (
                <Typography variant="body2">
                    {t(`secrets.key_type.${params.value}`, params.value)}
                </Typography>
            ),
        },
        {
            field: 'created_at',
            headerName: t('secrets.createdAt', 'Created'),
            width: 180,
            renderCell: (params) => (
                <Typography variant="body2">
                    {new Date(params.value).toLocaleString()}
                </Typography>
            ),
        },
    ];

    const handleDeploySSHKeys = async () => {
        if (!selectedUser || selectedSSHKeys.length === 0 || !host) return;

        try {
            const deployData = {
                host_id: host.id,
                username: selectedUser.username,
                secret_ids: selectedSSHKeys
            };

            const response = await axiosInstance.post('/api/secrets/deploy-ssh-keys', deployData);
            const result = response.data;
            console.log('SSH key deployment queued:', result);

            setSnackbarMessage(t('hostDetail.sshKeysDeployedSuccess', 'SSH keys deployment queued successfully'));
            setSnackbarSeverity('success');
            setSnackbarOpen(true);

            handleSSHKeyDialogClose();
        } catch (error: unknown) {
            console.error('Failed to deploy SSH keys:', error);
            let errorMessage = t('hostDetail.sshKeysDeployedError', 'Failed to deploy SSH keys');

            if (error && typeof error === 'object' && 'response' in error) {
                const axiosError = error as { response?: { data?: { detail?: string } } };
                if (axiosError.response?.data?.detail) {
                    errorMessage = axiosError.response.data.detail;
                }
            }

            setSnackbarMessage(errorMessage);
            setSnackbarSeverity('error');
            setSnackbarOpen(true);
        }
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

    // Helper function to assign priority to mount points (lower = higher priority)
    const getMountPointPriority = useCallback((mountPoint: string): number => {
        if (mountPoint === '/') return 1;                           // Root - highest priority
        if (mountPoint.includes('/System/Volumes')) return 3;      // System volumes - lower priority
        if (mountPoint.includes('/Library')) return 4;             // Library volumes - even lower
        return 2;                                                   // Other mounts - medium priority
    }, []);

    // Utility function to deduplicate storage devices by name, preferring root mounts
    const deduplicateStorageDevices = useCallback((devices: StorageDeviceType[]): StorageDeviceType[] => {
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
    }, [getMountPointPriority]);

    // Filter storage devices based on physical/logical selection (memoized)
    const filteredStorageDevices = useMemo(() => {
        const deduplicatedDevices = deduplicateStorageDevices(storageDevices);

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
    }, [storageDevices, storageFilter, deduplicateStorageDevices]);

    // Filter user accounts based on system/regular selection (memoized)
    const filteredUsers = useMemo(() => {
        switch (userFilter) {
            case 'system':
                return userAccounts.filter(user => user.is_system_user === true);
            case 'regular':
                return userAccounts.filter(user => user.is_system_user === false);
            case 'all':
            default:
                // Sort regular users first, then system
                return userAccounts.sort((a, b) => {
                    if (a.is_system_user === b.is_system_user) return 0;
                    return a.is_system_user ? 1 : -1;
                });
        }
    }, [userAccounts, userFilter]);

    // Filter user groups based on system/regular selection (memoized)
    const filteredGroups = useMemo(() => {
        switch (groupFilter) {
            case 'system':
                return userGroups.filter(group => group.is_system_group === true);
            case 'regular':
                return userGroups.filter(group => group.is_system_group === false);
            case 'all':
            default:
                // Sort regular groups first, then system
                return userGroups.sort((a, b) => {
                    if (a.is_system_group === b.is_system_group) return 0;
                    return a.is_system_group ? 1 : -1;
                });
        }
    }, [userGroups, groupFilter]);

    // Filter network interfaces based on active/inactive selection (memoized)
    const filteredNetworkInterfaces = useMemo(() => {
        switch (networkFilter) {
            case 'active':
                return networkInterfaces.filter(iface => !!(iface.ipv4_address || iface.ipv6_address));
            case 'inactive':
                return networkInterfaces.filter(iface => !(iface.ipv4_address || iface.ipv6_address));
            case 'all':
            default:
                // Sort active interfaces first, then inactive
                return networkInterfaces.sort((a, b) => {
                    const aHasIP = !!(a.ipv4_address || a.ipv6_address);
                    const bHasIP = !!(b.ipv4_address || b.ipv6_address);
                    if (aHasIP === bHasIP) return 0;
                    return aHasIP ? -1 : 1;
                });
        }
    }, [networkInterfaces, networkFilter]);

    // Package search function (defined before useEffect to avoid hoisting issues)
    const performPackageSearch = useCallback(async (query: string) => {
        if (!hostId || !query.trim()) return;

        setIsSearching(true);
        try {
            // Get host information to determine OS for package search
            const response = await axiosInstance.get(`/api/packages/search?query=${encodeURIComponent(query)}&limit=20`);

            if (response.data && Array.isArray(response.data)) {
                // Get list of already installed package names
                const installedPackageNames = new Set(
                    softwarePackages
                        .filter(pkg => pkg.package_name) // Filter out packages without names
                        .map(pkg => pkg.package_name.toLowerCase())
                );

                // Filter out already installed packages
                const results = response.data
                    .filter((pkg: { name: string; description: string; version: string }) =>
                        !installedPackageNames.has(pkg.name.toLowerCase())
                    )
                    .map((pkg: { name: string; description: string; version: string }) => ({
                        name: pkg.name,
                        description: pkg.description,
                        version: pkg.version
                    }));
                setSearchResults(results);
            } else {
                setSearchResults([]);
            }
        } catch (error) {
            console.error('Error searching packages:', error);
            // Check if it's an authentication error
            const axiosError = error as { response?: { status?: number; data?: { detail?: string } } };
            if (axiosError.response?.status === 401 || axiosError.response?.status === 403) {
                console.error('Authentication error while searching packages. User may need to log in again.');
                // You could trigger a re-login here or show an auth error message
            }
            // Fall back to empty results on error
            setSearchResults([]);
        } finally {
            setIsSearching(false);
        }
    }, [hostId, softwarePackages]);

    // Parse enabled shells (memoized to avoid JSON.parse on every render)
    const enabledShells = useMemo(() => {
        if (!host?.enabled_shells) return [];
        try {
            const shells = JSON.parse(host.enabled_shells);
            return Array.isArray(shells) ? shells : [];
        } catch {
            return [];
        }
    }, [host?.enabled_shells]);

    // Check if diagnostics are currently being processed based on persistent state
    const isDiagnosticsProcessing = host?.diagnostics_request_status === 'pending';

    const handleAttachToGraylog = () => {
        setGraylogAttachModalOpen(true);
    };

    const handleGraylogAttachModalClose = () => {
        setGraylogAttachModalOpen(false);
        // Refresh Graylog attachment status after modal closes
        fetchGraylogAttachment();
    };

    const handleDeployOpenTelemetry = async () => {
        if (!hostId) return;

        try {
            setOpenTelemetryDeploying(true);

            const result = await doDeployOpenTelemetry(hostId);

            // Show success message
            setSnackbarMessage(result.message || t('hostDetail.opentelemetryDeploySuccess', 'OpenTelemetry deployment queued successfully'));
            setSnackbarSeverity('success');
            setSnackbarOpen(true);

            // Refresh software data after a delay to show the deployment
            setTimeout(async () => {
                try {
                    const softwareData = await doGetHostSoftware(hostId);
                    setSoftwarePackages(softwareData);

                    // Re-check eligibility
                    const eligibility = await doCheckOpenTelemetryEligibility(hostId);
                    setCanDeployOpenTelemetry(eligibility.has_permission || false);
                    setOpenTelemetryEligible(eligibility.eligible || false);
                } catch (error) {
                    console.error('Error refreshing software data:', error);
                }
            }, 5000);
        } catch (error) {
            console.error('Error deploying OpenTelemetry:', error);
            setSnackbarMessage(String(error) || t('hostDetail.opentelemetryDeployFailed', 'Failed to deploy OpenTelemetry'));
            setSnackbarSeverity('error');
            setSnackbarOpen(true);
        } finally {
            setOpenTelemetryDeploying(false);
        }
    };

    const handleRequestDiagnostics = async () => {
        if (!hostId) return;

        try {
            setDiagnosticsLoading(true);

            // Request diagnostics, system info, user access data, software inventory, and package updates
            await Promise.all([
                doRequestHostDiagnostics(hostId),
                doRequestSystemInfo(hostId),
                doRefreshUserAccessData(hostId),
                doRefreshSoftwareData(hostId),
                doRefreshUpdatesCheck(hostId)
            ]);

            // Show success message
            console.log('Diagnostics, system info, user access data, software inventory, and package updates requested successfully');
            
            // Refresh host data to get updated diagnostics request status
            const updatedHost = await doGetHostByID(hostId);
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
                            const currentHost = await doGetHostByID(hostId);
                            setHost(currentHost);
                            
                            // If status changed from pending, also refresh diagnostics data
                            if (currentHost?.diagnostics_request_status !== 'pending') {
                                const updatedDiagnostics = await doGetHostDiagnostics(hostId);
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

    const handleDeleteDiagnostic = (diagnosticId: string) => {
        setDiagnosticToDelete(diagnosticId);
        setDeleteConfirmOpen(true);
    };

    const handleViewDiagnosticDetail = async (diagnosticId: string) => {
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

    const handleRequestPackages = () => {
        setRequestPackagesConfirmOpen(true);
    };

    const handleRequestPackagesConfirm = async () => {
        if (!host || !host.id) return;
        setRequestPackagesConfirmOpen(false);

        try {
            await doRequestPackages(host.id);
            setSnackbarMessage(t('hosts.packagesRequested', 'Package collection requested successfully'));
            setSnackbarOpen(true);
        } catch (error) {
            console.error('Failed to request package collection:', error);
            setSnackbarMessage(t('hosts.packagesRequestFailed', 'Failed to request package collection'));
            setSnackbarOpen(true);
        }
    };

    const handleDeployAntivirus = async () => {
        if (!host || !host.id) return;

        try {
            // Call backend API to deploy antivirus to this specific host
            const response = await axiosInstance.post('/api/deploy', {
                host_ids: [host.id]
            });

            if (response.data.failed_hosts && response.data.failed_hosts.length > 0) {
                const failedHost = response.data.failed_hosts[0];
                setSnackbarMessage(t('hostDetail.antivirusDeployFailed', 'Failed to deploy antivirus: {reason}', { reason: failedHost.reason }));
                setSnackbarSeverity('error');
            } else {
                setSnackbarMessage(t('hostDetail.antivirusDeploySuccess', 'Antivirus deployment initiated successfully'));
                setSnackbarSeverity('success');
                // Trigger refresh after a short delay to allow agent to update
                setTimeout(() => setAntivirusRefreshTrigger(prev => prev + 1), 10000);
            }
            setSnackbarOpen(true);
        } catch (error) {
            console.error('Failed to deploy antivirus:', error);
            setSnackbarMessage(t('hostDetail.antivirusDeployFailed', 'Failed to deploy antivirus'));
            setSnackbarSeverity('error');
            setSnackbarOpen(true);
        }
    };

    const handleEnableAntivirus = async () => {
        if (!host || !host.id) return;

        try {
            await axiosInstance.post(`/api/hosts/${host.id}/antivirus/enable`);
            setSnackbarMessage(t('security.antivirusEnableSuccess', 'Antivirus enable initiated successfully'));
            setSnackbarSeverity('success');
            setSnackbarOpen(true);
            // Trigger refresh after a short delay
            setTimeout(() => setAntivirusRefreshTrigger(prev => prev + 1), 10000);
        } catch (error) {
            console.error('Failed to enable antivirus:', error);
            setSnackbarMessage(t('security.antivirusEnableFailed', 'Failed to enable antivirus'));
            setSnackbarSeverity('error');
            setSnackbarOpen(true);
        }
    };

    const handleDisableAntivirus = async () => {
        if (!host || !host.id) return;

        try {
            await axiosInstance.post(`/api/hosts/${host.id}/antivirus/disable`);
            setSnackbarMessage(t('security.antivirusDisableSuccess', 'Antivirus disable initiated successfully'));
            setSnackbarSeverity('success');
            setSnackbarOpen(true);
            // Trigger refresh after a short delay
            setTimeout(() => setAntivirusRefreshTrigger(prev => prev + 1), 10000);
        } catch (error) {
            console.error('Failed to disable antivirus:', error);
            setSnackbarMessage(t('security.antivirusDisableFailed', 'Failed to disable antivirus'));
            setSnackbarSeverity('error');
            setSnackbarOpen(true);
        }
    };

    const handleRemoveAntivirus = async () => {
        if (!host || !host.id) return;

        try {
            await axiosInstance.post(`/api/hosts/${host.id}/antivirus/remove`);
            setSnackbarMessage(t('security.antivirusRemoveSuccess', 'Antivirus removal initiated successfully'));
            setSnackbarSeverity('success');
            setSnackbarOpen(true);
            // Trigger refresh after a short delay
            setTimeout(() => setAntivirusRefreshTrigger(prev => prev + 1), 10000);
        } catch (error) {
            console.error('Failed to remove antivirus:', error);
            setSnackbarMessage(t('security.antivirusRemoveFailed', 'Failed to remove antivirus'));
            setSnackbarSeverity('error');
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
                    const updatedDiagnostics = await doGetHostDiagnostics(hostId);
                    setDiagnosticsData(updatedDiagnostics);
                    console.log('Diagnostics data refreshed:', updatedDiagnostics.length, 'reports');
                    
                    // Also refresh host data to update the processing pill status
                    // This is especially important if we just deleted the last diagnostic
                    const updatedHost = await doGetHostByID(hostId);
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

    const handleRemoveTag = async (tagId: string) => {
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

    const handleCloseSnackbar = (_event?: React.SyntheticEvent, reason?: string) => {
        if (reason === 'clickaway') {
            return;
        }
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
        const tabs = getTabNames();
        // Safely access array element with bounds check
        // nosemgrep: javascript.lang.security.audit.object-injection.object-injection
        if (newValue >= 0 && newValue < tabs.length) {
            window.location.hash = tabs[newValue];
        }
    };

    // Ubuntu Pro handlers
    const handleUbuntuProAttach = async () => {
        // Try to load master Ubuntu Pro token
        try {
            const response = await axiosInstance.get('/api/ubuntu-pro/');
            const masterKey = response.data.master_key;
            if (masterKey && masterKey.trim()) {
                setUbuntuProToken(masterKey);
            }
        } catch (error) {
            console.log('No master Ubuntu Pro token configured or error loading:', error);
            // Don't show error to user - this is optional functionality
        }

        setUbuntuProTokenDialog(true);
    };

    const handleUbuntuProDetach = () => {
        setUbuntuProDetachConfirmOpen(true);
    };

    const handleConfirmUbuntuProDetach = async () => {
        if (!hostId || !host) return;

        setUbuntuProDetachConfirmOpen(false);
        setUbuntuProDetaching(true);
        try {
            await doDetachUbuntuPro(hostId);
            setSnackbarMessage(t('hostDetail.ubuntuProDetachSuccess', 'Ubuntu Pro detached successfully'));
            setSnackbarSeverity('success');
            setSnackbarOpen(true);

            // Refresh Ubuntu Pro info after a short delay to allow agent to process
            setTimeout(async () => {
                try {
                    const ubuntuProData = await doGetHostUbuntuPro(hostId);
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

    const handleCancelUbuntuProDetach = () => {
        setUbuntuProDetachConfirmOpen(false);
    };

    const handleUbuntuProTokenSubmit = async () => {
        if (!hostId || !host || !ubuntuProToken.trim()) return;

        setUbuntuProAttaching(true);
        setUbuntuProTokenDialog(false);

        try {
            await doAttachUbuntuPro(hostId, ubuntuProToken.trim());
            setSnackbarMessage(t('hostDetail.ubuntuProAttachSuccess', 'Ubuntu Pro attached successfully'));
            setSnackbarSeverity('success');
            setSnackbarOpen(true);

            // Refresh Ubuntu Pro info after a short delay to allow agent to process
            setTimeout(async () => {
                try {
                    const ubuntuProData = await doGetHostUbuntuPro(hostId);
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

    // Package installation handlers

    const handlePackageSelect = (packageName: string) => {
        const newSelected = new Set(selectedPackages);
        if (newSelected.has(packageName)) {
            newSelected.delete(packageName);
        } else {
            newSelected.add(packageName);
        }
        setSelectedPackages(newSelected);
    };

    const handleInstallPackages = async () => {
        if (!hostId || selectedPackages.size === 0) return;

        try {
            const response = await axiosInstance.post(`/api/packages/install/${hostId}`, {
                package_names: Array.from(selectedPackages),
                requested_by: currentUser ? `${currentUser.first_name || ''} ${currentUser.last_name || ''}`.trim() || currentUser.userid : 'Unknown User'
            });

            if (response.data.success) {
                // Close dialog and reset state
                setPackageInstallDialogOpen(false);
                if (packageSearchInputRef.current) {
                    packageSearchInputRef.current.value = '';
                }
                setSearchResults([]);
                setSelectedPackages(new Set());

                // Navigate to Software Changes tab to show progress
                setCurrentTab(getSoftwareInstallsTabIndex());

                // Show success message
                setSnackbarMessage(response.data.message || t('hostDetail.packagesInstallQueued', 'Package installation has been queued'));
                setSnackbarSeverity('success');
                setSnackbarOpen(true);
            } else {
                throw new Error(response.data.message || 'Unknown error');
            }
        } catch (error: unknown) {
            console.error('Error installing packages:', error);
            const axiosError = error as { response?: { data?: { detail?: string } }; message?: string };
            const errorMessage = axiosError.response?.data?.detail || axiosError.message || t('hostDetail.packagesInstallError', 'Error queueing package installation');
            setSnackbarMessage(errorMessage);
            setSnackbarSeverity('error');
            setSnackbarOpen(true);
        }
    };

    const handleClosePackageDialog = () => {
        setPackageInstallDialogOpen(false);
        if (packageSearchInputRef.current) {
            packageSearchInputRef.current.value = '';
        }
        setSearchResults([]);
        setSelectedPackages(new Set());
    };

    // Uninstall handlers
    const handleUninstallPackage = (pkg: SoftwarePackage) => {
        setPackageToUninstall(pkg);
        setUninstallConfirmOpen(true);
    };

    const handleUninstallConfirm = async () => {
        if (!hostId || !packageToUninstall) return;

        try {
            const response = await axiosInstance.post(`/api/packages/uninstall/${hostId}`, {
                package_names: [packageToUninstall.package_name],
                requested_by: currentUser ? `${currentUser.first_name || ''} ${currentUser.last_name || ''}`.trim() || currentUser.userid : 'Unknown User'
            });

            if (response.data.success) {
                // Close dialog and reset state
                setUninstallConfirmOpen(false);
                setPackageToUninstall(null);

                // Navigate to Software Changes tab to show progress
                setCurrentTab(getSoftwareInstallsTabIndex());

                // Show success message
                setSnackbarMessage(response.data.message || t('hostDetail.packageUninstallQueued', 'Package uninstallation has been queued'));
                setSnackbarSeverity('success');
                setSnackbarOpen(true);
            } else {
                throw new Error(response.data.message || 'Unknown error');
            }
        } catch (error: unknown) {
            const axiosError = error as { response?: { data?: { detail?: string } }; message?: string };
            const errorMessage = axiosError.response?.data?.detail || axiosError.message || t('hostDetail.packageUninstallError', 'Error queueing package uninstallation');
            setSnackbarMessage(errorMessage);
            setSnackbarSeverity('error');
            setSnackbarOpen(true);
        }
    };

    const handleUninstallCancel = () => {
        setUninstallConfirmOpen(false);
        setPackageToUninstall(null);
    };

    // Installation history handlers

    const handleViewInstallationLog = (installation: InstallationHistoryItem) => {
        setSelectedInstallationLog(installation);
        setInstallationLogDialogOpen(true);
    };

    const handleCloseInstallationLogDialog = () => {
        setInstallationLogDialogOpen(false);
        setSelectedInstallationLog(null);
    };

    const handleDeleteInstallation = (installation: InstallationHistoryItem) => {
        setInstallationToDelete(installation);
        setInstallationDeleteConfirmOpen(true);
    };

    const handleConfirmDeleteInstallation = async () => {
        if (!installationToDelete) return;

        try {
            await axiosInstance.delete(`/api/packages/installation-history/${installationToDelete.request_id}`);
            setSnackbarMessage(t('hostDetail.installationDeleted', 'Installation record deleted successfully'));
            setSnackbarSeverity('success');
            setSnackbarOpen(true);
            // Refresh the installation history
            fetchInstallationHistory();
        } catch (error) {
            console.error('Error deleting installation record:', error);
            setSnackbarMessage(t('hostDetail.installationDeleteError', 'Failed to delete installation record'));
            setSnackbarSeverity('error');
            setSnackbarOpen(true);
        } finally {
            setInstallationDeleteConfirmOpen(false);
            setInstallationToDelete(null);
        }
    };

    const handleCancelDeleteInstallation = () => {
        setInstallationDeleteConfirmOpen(false);
        setInstallationToDelete(null);
    };

    // Format datetime for display
    const formatDateTime = (dateString: string) => {
        return new Date(dateString).toLocaleString();
    };

    // Get installation status color
    const getInstallationStatusColor = (status: string): 'success' | 'error' | 'warning' | 'default' => {
        switch (status.toLowerCase()) {
            case 'completed':
                return 'success';
            case 'failed':
                return 'error';
            case 'pending':
            case 'queued':
            case 'installing':
            case 'in_progress':
                return 'warning';
            default:
                return 'default';
        }
    };

    // Get translated status text
    const getTranslatedStatus = (status: string) => {
        const translationKey = `scripts.status.${status.toLowerCase()}`;
        const translated = t(translationKey);
        // If translation not found, return capitalized status
        return translated === translationKey ?
            status.charAt(0).toUpperCase() + status.slice(1).replace('_', ' ') :
            translated;
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
                    await doEnableUbuntuProService(hostId, change.service);
                } else {
                    await doDisableUbuntuProService(hostId, change.service);
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

    // Define certificate DataGrid columns
    const certificateColumns: GridColDef[] = [
        {
            field: 'certificate_name',
            headerName: t('hostDetail.certificateName', 'Certificate Name'),
            minWidth: 200,
            flex: 1,
            renderCell: (params) => (
                <Box>
                    <Typography variant="body2" sx={{ fontWeight: 500 }}>
                        {params.value || params.row.common_name || t('common.unknown', 'Unknown')}
                    </Typography>
                    <Box sx={{ display: 'flex', gap: 0.5, mt: 0.25 }}>
                        {params.row.is_expired && (
                            <Chip
                                label={t('hostDetail.expired', 'Expired')}
                                size="small"
                                color="error"
                                sx={{
                                    fontSize: '0.7rem',
                                    height: '18px'
                                }}
                            />
                        )}
                        {!params.row.is_expired && params.row.days_until_expiry !== null && params.row.days_until_expiry <= 30 && (
                            <Chip
                                label={t('hostDetail.expiringSoon', 'Expiring Soon')}
                                size="small"
                                color="warning"
                                sx={{
                                    fontSize: '0.7rem',
                                    height: '18px'
                                }}
                            />
                        )}
                        {params.row.is_ca && (
                            <Chip
                                label="CA"
                                size="small"
                                color="primary"
                                variant="outlined"
                                sx={{
                                    fontSize: '0.7rem',
                                    height: '18px'
                                }}
                            />
                        )}
                    </Box>
                </Box>
            ),
        },
        {
            field: 'issuer',
            headerName: t('hostDetail.issuer', 'Issuer'),
            minWidth: 250,
            flex: 1,
            renderCell: (params) => (
                <Typography
                    variant="body2"
                    sx={{
                        whiteSpace: 'nowrap',
                        overflow: 'hidden',
                        textOverflow: 'ellipsis',
                    }}
                    title={params.value}
                >
                    {params.value}
                </Typography>
            ),
        },
        {
            field: 'not_after',
            headerName: t('hostDetail.expiryDate', 'Expiry Date'),
            minWidth: 130,
            renderCell: (params) => {
                if (!params.value) return t('common.unknown', 'Unknown');

                const expiryDate = new Date(params.value);
                const isExpired = params.row.is_expired;
                const daysUntilExpiry = params.row.days_until_expiry;

                return (
                    <Box>
                        <Typography
                            variant="body2"
                            sx={{
                                color: isExpired ? 'error.main' :
                                       (daysUntilExpiry !== null && daysUntilExpiry <= 30) ? 'warning.main' : 'text.primary'
                            }}
                        >
                            {expiryDate.toLocaleDateString()}
                        </Typography>
                        {daysUntilExpiry !== null && (
                            <Typography variant="caption" sx={{ display: 'block', lineHeight: 1 }}>
                                {isExpired ?
                                    t('hostDetail.expired', 'Expired') :
                                    t('hostDetail.daysUntilExpiry', '{{days}} days', { days: daysUntilExpiry })
                                }
                            </Typography>
                        )}
                    </Box>
                );
            },
        },
        {
            field: 'file_path',
            headerName: t('hostDetail.location', 'Location'),
            minWidth: 300,
            flex: 1,
            renderCell: (params) => (
                <Typography
                    variant="body2"
                    sx={{
                        fontFamily: 'monospace',
                        fontSize: '0.85rem',
                        whiteSpace: 'nowrap',
                        overflow: 'hidden',
                        textOverflow: 'ellipsis',
                    }}
                    title={params.value}
                >
                    {params.value}
                </Typography>
            ),
        },
        {
            field: 'serial_number',
            headerName: t('hostDetail.serialNumber', 'Serial'),
            minWidth: 120,
            renderCell: (params) => (
                <Typography
                    variant="body2"
                    sx={{
                        fontFamily: 'monospace',
                        fontSize: '0.8rem',
                        whiteSpace: 'nowrap',
                        overflow: 'hidden',
                        textOverflow: 'ellipsis',
                    }}
                    title={params.value}
                >
                    {params.value}
                </Typography>
            ),
        },
    ];

    return (
        <Box sx={{
            display: 'flex',
            flexDirection: 'column',
            height: 'calc(100vh - 120px)',
            gap: 2,
            p: 2
        }}>
            <Button
                startIcon={<ArrowBackIcon />}
                onClick={() => navigate('/hosts')}
                sx={{ flexShrink: 0, alignSelf: 'flex-start' }}
            >
                {t('common.back')}
            </Button>

            <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexShrink: 0 }}>
                <Typography variant="h4" sx={{ display: 'flex', alignItems: 'center' }}>
                    <ComputerIcon sx={{ mr: 2, fontSize: '2rem' }} />
                    {host.fqdn}
                </Typography>
                <Box sx={{ display: 'flex', gap: 1 }}>
                    <Button
                        variant="outlined"
                        color="primary"
                        startIcon={<SystemUpdateAltIcon />}
                        onClick={() => navigate(`/updates?host=${hostId}&securityOnly=false`)}
                        disabled={!host.active || (host.security_updates_count || 0) + (host.system_updates_count || 0) === 0}
                    >
                        {t('hosts.updates', 'Updates')}
                    </Button>
                    <Button
                        variant="outlined"
                        color="primary"
                        startIcon={<AppsIcon />}
                        onClick={handleRequestPackages}
                        disabled={!host.active}
                    >
                        {t('hosts.requestPackages', 'Request Avail. Packages')}
                    </Button>
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
            <Box sx={{ borderBottom: 1, borderColor: 'divider', flexShrink: 0 }}>
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
                        icon={<HistoryIcon />}
                        label={t('hostDetail.softwareChangesTab', 'Software Changes')}
                        iconPosition="start"
                        sx={{ textTransform: 'none' }}
                    />
                    {supportsThirdPartyRepos() && (
                        <Tab
                            icon={<SourceIcon />}
                            label={t('hostDetail.thirdPartyReposTab', 'Third-Party Repositories')}
                            iconPosition="start"
                            sx={{ textTransform: 'none' }}
                        />
                    )}
                    <Tab
                        icon={<SecurityIcon />}
                        label={t('hostDetail.accessTab', 'Access')}
                        iconPosition="start"
                        sx={{ textTransform: 'none' }}
                    />
                    <Tab
                        icon={<ShieldIcon />}
                        label={t('hostDetail.securityTab', 'Security')}
                        iconPosition="start"
                        sx={{ textTransform: 'none' }}
                    />
                    <Tab
                        icon={<CertificateIcon />}
                        label={t('hostDetail.certificatesTab', 'Certificates')}
                        iconPosition="start"
                        sx={{ textTransform: 'none' }}
                    />
                    <Tab
                        icon={<AssignmentIcon />}
                        label={t('hostDetail.serverRolesTab', 'Server Roles')}
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

            {/* Tab Content - flexGrow to fill available space */}
            <Box sx={{ flexGrow: 1, overflow: 'auto', minHeight: 0 }}>
            {currentTab === 0 && (
                <Grid container spacing={3}>
                {/* Basic Information */}
                <Grid size={{ xs: 12, md: 6 }}>
                    <Card sx={{ height: '100%' }}>
                        <CardContent>
                            <Typography variant="subtitle1" sx={{ mb: 2, display: 'flex', alignItems: 'center', fontWeight: 'bold', fontSize: '1.1rem' }}>
                                <InfoIcon sx={{ mr: 1 }} />
                                {t('hostDetail.basicInfo', 'Basic Information')}
                            </Typography>
                            <Grid container spacing={2}>
                                <Grid size={{ xs: 12, sm: 6 }}>
                                    <Typography variant="body2" color="textSecondary">
                                        {t('hosts.fqdn', 'FQDN')}
                                    </Typography>
                                    <Typography variant="body1">{host.fqdn}</Typography>
                                </Grid>
                                <Grid size={{ xs: 12, sm: 6 }}>
                                    <Typography variant="body2" color="textSecondary">
                                        {t('hosts.ipv4', 'IPv4')}
                                    </Typography>
                                    <Typography variant="body1">{host.ipv4 || t('common.notAvailable')}</Typography>
                                </Grid>
                                <Grid size={{ xs: 12, sm: 6 }}>
                                    <Typography variant="body2" color="textSecondary">
                                        {t('hosts.ipv6', 'IPv6')}
                                    </Typography>
                                    <Typography variant="body1">{host.ipv6 || t('common.notAvailable')}</Typography>
                                </Grid>
                                <Grid size={{ xs: 12, sm: 6 }}>
                                    <Typography variant="body2" color="textSecondary">
                                        {t('hosts.status', 'Status')}
                                    </Typography>
                                    <Chip
                                        label={getDisplayStatus(host) === 'up' ? t('hosts.up') : t('hosts.down')}
                                        color={getStatusColor(getDisplayStatus(host))}
                                        size="small"
                                    />
                                </Grid>
                                <Grid size={{ xs: 12, sm: 6 }}>
                                    <Typography variant="body2" color="textSecondary">
                                        {t('hostDetail.approvalStatus', 'Approval Status')}
                                    </Typography>
                                    <Chip 
                                        label={host.approval_status.charAt(0).toUpperCase() + host.approval_status.slice(1)}
                                        color={getApprovalStatusColor(host.approval_status)}
                                        size="small"
                                    />
                                </Grid>
                                <Grid size={{ xs: 12, sm: 6 }}>
                                    <Typography variant="body2" color="textSecondary">
                                        {t('hosts.lastCheckin', 'Last Check-in')}
                                    </Typography>
                                    <Typography variant="body1">{formatDate(host.last_access)}</Typography>
                                </Grid>
                                <Grid size={{ xs: 12, sm: 6 }}>
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
                                <Grid size={{ xs: 12, sm: 6 }}>
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
                                <Grid size={{ xs: 12, sm: 6 }}>
                                    <Typography variant="body2" color="textSecondary">
                                        {t('hostDetail.active', 'Active')}
                                    </Typography>
                                    <Chip
                                        label={host.active ? t('common.yes') : t('common.no')}
                                        color={host.active ? 'success' : 'default'}
                                        size="small"
                                    />
                                </Grid>
                                <Grid size={{ xs: 12, sm: 6 }}>
                                    <Typography variant="body2" color="textSecondary">
                                        {t('hosts.shellsAllowed', 'Shells Allowed')}
                                    </Typography>
                                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, flexWrap: 'wrap' }}>
                                        {/* Enabled Shells */}
                                        {enabledShells.length > 0 ? enabledShells.map((shell: string) => (
                                            <Chip
                                                key={shell}
                                                label={shell}
                                                color="success"
                                                size="small"
                                                variant="filled"
                                            />
                                        )) : (
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
                <Grid size={{ xs: 12, md: 6 }}>
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
                                <Grid size={{ xs: 12 }}>
                                    <Typography variant="body2" color="textSecondary">
                                        {t('hostDetail.platform', 'Platform')}
                                    </Typography>
                                    <Typography variant="body1">{host.platform || t('common.notAvailable')}</Typography>
                                </Grid>
                                <Grid size={{ xs: 12 }}>
                                    <Typography variant="body2" color="textSecondary">
                                        {t('hostDetail.platformRelease', 'Platform Release')}
                                    </Typography>
                                    <Typography variant="body1">{host.platform_release || t('common.notAvailable')}</Typography>
                                </Grid>
                                <Grid size={{ xs: 12 }}>
                                    <Typography variant="body2" color="textSecondary">
                                        {t('hostDetail.kernel', 'Kernel')}
                                    </Typography>
                                    <Typography variant="body1" sx={{ wordBreak: 'break-word' }}>
                                        {host.platform_version || t('common.notAvailable')}
                                    </Typography>
                                </Grid>
                                <Grid size={{ xs: 12, sm: 6 }}>
                                    <Typography variant="body2" color="textSecondary">
                                        {t('hostDetail.architecture', 'Architecture')}
                                    </Typography>
                                    <Typography variant="body1">{host.machine_architecture || t('common.notAvailable')}</Typography>
                                </Grid>
                                <Grid size={{ xs: 12, sm: 6 }}>
                                    <Typography variant="body2" color="textSecondary">
                                        {t('hostDetail.processor', 'Processor')}
                                    </Typography>
                                    <Typography variant="body1">{host.processor || t('common.notAvailable')}</Typography>
                                </Grid>
                                {host.os_details && (
                                    <Grid size={{ xs: 12 }}>
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

                {/* OpenTelemetry Status */}
                <Grid size={{ xs: 12, md: 6 }}>
                    <Card sx={{ height: '100%' }}>
                        <CardContent>
                            <Typography variant="subtitle1" sx={{ mb: 2, display: 'flex', alignItems: 'center', fontWeight: 'bold', fontSize: '1.1rem' }}>
                                <MedicalServicesIcon sx={{ mr: 1 }} />
                                {t('hostDetail.opentelemetryStatus', 'OpenTelemetry Status')}
                            </Typography>
                            {openTelemetryLoading ? (
                                <Box sx={{ display: 'flex', justifyContent: 'center', p: 2 }}>
                                    <CircularProgress size={24} />
                                </Box>
                            ) : openTelemetryStatus ? (
                                <Grid container spacing={2}>
                                    <Grid size={{ xs: 12 }}>
                                        <Typography variant="body2" color="textSecondary">
                                            {t('hostDetail.opentelemetryDeployed', 'Deployed')}
                                        </Typography>
                                        <Typography variant="body1">
                                            {openTelemetryStatus.deployed ? t('common.yes', 'Yes') : t('common.no', 'No')}
                                        </Typography>
                                    </Grid>
                                    {!openTelemetryStatus.deployed && hasPermission(SecurityRoles.DEPLOY_OPENTELEMETRY) && host?.is_agent_privileged && (
                                        <Grid size={{ xs: 12 }}>
                                            <Button
                                                variant="contained"
                                                color="primary"
                                                size="small"
                                                onClick={handleDeployOpenTelemetry}
                                                disabled={openTelemetryDeploying || openTelemetryLoading}
                                            >
                                                {openTelemetryDeploying ? t('hostDetail.deploying', 'Deploying...') : t('hostDetail.deployOpenTelemetry', 'Deploy OpenTelemetry')}
                                            </Button>
                                        </Grid>
                                    )}
                                    {openTelemetryStatus.deployed && (
                                        <>
                                            <Grid size={{ xs: 12 }}>
                                                <Typography variant="body2" color="textSecondary">
                                                    {t('hostDetail.opentelemetryServiceStatus', 'Service Status')}
                                                </Typography>
                                                <Chip
                                                    label={
                                                        openTelemetryStatus.service_status === 'running'
                                                            ? t('hostDetail.opentelemetryServiceRunning', 'Running')
                                                            : openTelemetryStatus.service_status === 'stopped'
                                                            ? t('hostDetail.opentelemetryServiceStopped', 'Stopped')
                                                            : t('hostDetail.opentelemetryServiceUnknown', 'Unknown')
                                                    }
                                                    color={
                                                        openTelemetryStatus.service_status === 'running'
                                                            ? 'success'
                                                            : openTelemetryStatus.service_status === 'stopped'
                                                            ? 'error'
                                                            : 'default'
                                                    }
                                                    size="small"
                                                />
                                            </Grid>
                                            <Grid size={{ xs: 12 }}>
                                                <Typography variant="body2" color="textSecondary">
                                                    {t('hostDetail.opentelemetryGrafanaServer', 'Grafana Server')}
                                                </Typography>
                                                <Typography variant="body1">
                                                    {openTelemetryStatus.grafana_url || t('hostDetail.opentelemetryNotConnected', 'Not Connected')}
                                                </Typography>
                                            </Grid>
                                            {host.is_agent_privileged && (
                                                <Grid size={{ xs: 12 }}>
                                                    <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap' }}>
                                                        <Button
                                                            variant="outlined"
                                                            size="small"
                                                            startIcon={<PlayArrowIcon />}
                                                            onClick={handleOpenTelemetryStart}
                                                            disabled={openTelemetryLoading}
                                                        >
                                                            {t('hostDetail.opentelemetryStart', 'Start')}
                                                        </Button>
                                                        <Button
                                                            variant="outlined"
                                                            size="small"
                                                            startIcon={<StopIcon />}
                                                            onClick={handleOpenTelemetryStop}
                                                            disabled={openTelemetryLoading}
                                                        >
                                                            {t('hostDetail.opentelemetryStop', 'Stop')}
                                                        </Button>
                                                        <Button
                                                            variant="outlined"
                                                            size="small"
                                                            startIcon={<RestartAltIcon />}
                                                            onClick={handleOpenTelemetryRestart}
                                                            disabled={openTelemetryLoading}
                                                        >
                                                            {t('hostDetail.opentelemetryRestart', 'Restart')}
                                                        </Button>
                                                        {openTelemetryStatus.grafana_configured && !openTelemetryStatus.grafana_url && (
                                                            <Button
                                                                variant="outlined"
                                                                size="small"
                                                                onClick={handleOpenTelemetryConnect}
                                                                disabled={openTelemetryLoading}
                                                            >
                                                                {t('hostDetail.opentelemetryConnect', 'Connect to Grafana')}
                                                            </Button>
                                                        )}
                                                        <Button
                                                            variant="outlined"
                                                            size="small"
                                                            onClick={handleRemoveOpenTelemetry}
                                                            disabled={openTelemetryLoading}
                                                        >
                                                            {t('hostDetail.opentelemetryRemove', 'Remove OpenTelemetry')}
                                                        </Button>
                                                        {openTelemetryStatus.grafana_url && (
                                                            <Button
                                                                variant="outlined"
                                                                size="small"
                                                                onClick={handleOpenTelemetryDisconnect}
                                                                disabled={openTelemetryLoading}
                                                            >
                                                                {t('hostDetail.opentelemetryDisconnect', 'Disconnect from Grafana')}
                                                            </Button>
                                                        )}
                                                    </Box>
                                                </Grid>
                                            )}
                                        </>
                                    )}
                                </Grid>
                            ) : (
                                <Typography variant="body2" color="textSecondary">
                                    {t('common.notAvailable', 'Not Available')}
                                </Typography>
                            )}
                        </CardContent>
                    </Card>
                </Grid>

                {/* Graylog Status */}
                <Grid size={{ xs: 12, md: 6 }}>
                    <Card sx={{ height: '100%' }}>
                        <CardContent>
                            <Typography variant="subtitle1" sx={{ mb: 2, display: 'flex', alignItems: 'center', fontWeight: 'bold', fontSize: '1.1rem' }}>
                                <StorageIcon sx={{ mr: 1 }} />
                                {t('hostDetail.graylogStatus', 'Graylog Status')}
                            </Typography>
                            {graylogLoading ? (
                                <Box sx={{ display: 'flex', justifyContent: 'center', p: 2 }}>
                                    <CircularProgress size={24} />
                                </Box>
                            ) : (
                                <Grid container spacing={2}>
                                    <Grid size={{ xs: 12 }}>
                                        <Typography variant="body2" color="textSecondary">
                                            {t('hostDetail.graylogAttached', 'Attached to Graylog')}
                                        </Typography>
                                        <Typography variant="body1">
                                            {graylogAttached ? t('common.yes', 'Yes') : t('common.no', 'No')}
                                        </Typography>
                                    </Grid>
                                    {graylogAttached && (
                                        <>
                                            {graylogMechanism && (
                                                <Grid size={{ xs: 12 }}>
                                                    <Typography variant="body2" color="textSecondary">
                                                        {t('hostDetail.graylogMechanism', 'Mechanism')}
                                                    </Typography>
                                                    <Typography variant="body1">
                                                        {graylogMechanism === 'syslog_tcp' && t('graylog.mechanism.syslogTcp', 'Syslog TCP')}
                                                        {graylogMechanism === 'syslog_udp' && t('graylog.mechanism.syslogUdp', 'Syslog UDP')}
                                                        {graylogMechanism === 'gelf_tcp' && t('graylog.mechanism.gelfTcp', 'GELF TCP')}
                                                        {graylogMechanism === 'windows_sidecar' && t('graylog.mechanism.windowsSidecar', 'Windows Sidecar')}
                                                        {graylogPort && ` (port ${graylogPort})`}
                                                    </Typography>
                                                </Grid>
                                            )}
                                            {(graylogTargetHostname || graylogTargetIp) && (
                                                <Grid size={{ xs: 12 }}>
                                                    <Typography variant="body2" color="textSecondary">
                                                        {t('hostDetail.graylogTarget', 'Target')}
                                                    </Typography>
                                                    <Typography variant="body1">
                                                        {graylogTargetHostname || graylogTargetIp}
                                                    </Typography>
                                                </Grid>
                                            )}
                                        </>
                                    )}
                                    {!graylogAttached && canAttachGraylog && graylogEligible && (
                                        <Grid size={{ xs: 12 }}>
                                            <Button
                                                variant="contained"
                                                color="primary"
                                                size="small"
                                                onClick={handleAttachToGraylog}
                                                disabled={graylogLoading}
                                            >
                                                {t('hostDetail.attachToGraylog', 'Attach To Graylog')}
                                            </Button>
                                        </Grid>
                                    )}
                                    {!canAttachGraylog && (
                                        <Grid size={{ xs: 12 }}>
                                            <Typography variant="body2" color="textSecondary">
                                                {t('hostDetail.graylogNotConfigured', 'Graylog integration not configured or not healthy')}
                                            </Typography>
                                        </Grid>
                                    )}
                                    {canAttachGraylog && !graylogEligible && (
                                        <Grid size={{ xs: 12 }}>
                                            <Typography variant="body2" color="textSecondary">
                                                {t('hostDetail.graylogRequiresPrivileged', 'Requires agent in privileged mode')}
                                            </Typography>
                                        </Grid>
                                    )}
                                </Grid>
                            )}
                        </CardContent>
                    </Card>
                </Grid>

                {/* Tags */}
                <Grid size={{ xs: 12, md: 6 }}>
                    <Card sx={{ height: '100%' }}>
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
                                        onDelete={canEditTags ? () => handleRemoveTag(tag.id) : undefined}
                                        deleteIcon={canEditTags ? <DeleteIcon /> : undefined}
                                        variant="outlined"
                                    />
                                ))}
                                {hostTags.length === 0 && (
                                    <Typography variant="body2" color="textSecondary">
                                        {t('hostDetail.noTags', 'No tags assigned')}
                                    </Typography>
                                )}
                            </Box>
                            {canEditTags && (
                                <Box sx={{ display: 'flex', gap: 1, alignItems: 'center' }}>
                                    <FormControl size="small" sx={{ minWidth: 200 }}>
                                        <InputLabel>{t('hostDetail.addTag', 'Add Tag')}</InputLabel>
                                        <Select
                                            value={selectedTagToAdd}
                                            onChange={(e) => setSelectedTagToAdd(e.target.value)}
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
                            )}
                        </CardContent>
                    </Card>
                </Grid>
                </Grid>
            )}

            {/* Hardware Tab */}
            {currentTab === 1 && (
                <Grid container spacing={3}>
                {/* Hardware Information */}
                <Grid size={{ xs: 12 }}>
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
                                            <Typography variant="body1">{formatCpuFrequency(host.cpu_frequency_mhz)}</Typography>
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
                                            <Typography variant="body1">{formatMemorySize(host.memory_total_mb)}</Typography>
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
                                                            {device.name || device.device_path || device.mount_point || `Device ${index + 1}`}
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
                                                            {iface.name || `Interface ${index + 1}`}
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
                    <Grid size={{ xs: 12 }}>
                        <Card>
                            <CardContent>
                                <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 2 }}>
                                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
                                        <Typography variant="subtitle1" sx={{ display: 'flex', alignItems: 'center', fontWeight: 'bold', fontSize: '1.1rem' }}>
                                            <AppsIcon sx={{ mr: 1 }} />
                                            {t('hostDetail.softwarePackages', 'Software Packages')} ({softwarePagination.total_items})
                                        </Typography>
                                        <Typography variant="caption" color="textSecondary">
                                            {t('hosts.updated', 'Updated')}: {formatTimestamp(host.software_updated_at)}
                                        </Typography>
                                    </Box>
                                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
                                        {canAddPackage && (
                                            <Button
                                                variant="contained"
                                                startIcon={<AddIcon />}
                                                sx={{
                                                    backgroundColor: 'primary.main',
                                                    '&:hover': { backgroundColor: 'primary.dark' },
                                                    height: '40px', // Match ToggleButtonGroup height for small size
                                                    minHeight: '40px'
                                                }}
                                                onClick={() => setPackageInstallDialogOpen(true)}
                                            >
                                                {t('hostDetail.addPackage', 'Add Package')}
                                            </Button>
                                        )}
                                        {canDeployOpenTelemetry && (
                                            <Button
                                                variant="contained"
                                                startIcon={openTelemetryDeploying ? <CircularProgress size={20} color="inherit" /> : <SystemUpdateAltIcon />}
                                                disabled={!openTelemetryEligible || openTelemetryDeploying}
                                                sx={{
                                                    backgroundColor: 'success.main',
                                                    '&:hover': { backgroundColor: 'success.dark' },
                                                    height: '40px', // Match ToggleButtonGroup height for small size
                                                    minHeight: '40px'
                                                }}
                                                onClick={handleDeployOpenTelemetry}
                                            >
                                                {t('hostDetail.deployOpenTelemetry', 'Deploy OpenTelemetry')}
                                            </Button>
                                        )}
                                        {canAttachGraylog && (
                                            <Button
                                                variant="contained"
                                                startIcon={<SystemUpdateAltIcon />}
                                                disabled={!graylogEligible || graylogAttached}
                                                sx={{
                                                    backgroundColor: 'info.main',
                                                    '&:hover': { backgroundColor: 'info.dark' },
                                                    height: '40px',
                                                    minHeight: '40px'
                                                }}
                                                onClick={handleAttachToGraylog}
                                            >
                                                {t('hostDetail.attachToGraylog', 'Attach To Graylog')}
                                            </Button>
                                        )}
                                    </Box>
                                </Box>
                                <Box sx={{ mb: 2 }}>
                                    <TextField
                                        fullWidth
                                        variant="outlined"
                                        placeholder={t('hostDetail.searchSoftware', 'Search by package name or description...')}
                                        value={softwareSearchTerm}
                                        onChange={(e) => {
                                            setSoftwareSearchTerm(e.target.value);
                                            setSoftwarePagination(prev => ({ ...prev, page: 1 })); // Reset to page 1 on search
                                        }}
                                        InputProps={{
                                            startAdornment: (
                                                <InputAdornment position="start">
                                                    <SearchIcon />
                                                </InputAdornment>
                                            ),
                                        }}
                                        size="small"
                                    />
                                </Box>
                                {loadingSoftware ? (
                                    <Box sx={{ display: 'flex', justifyContent: 'center', alignItems: 'center', py: 4 }}>
                                        <CircularProgress />
                                        <Typography variant="body2" color="textSecondary" sx={{ ml: 2 }}>
                                            {t('hostDetail.loadingSoftware', 'Loading software packages...')}
                                        </Typography>
                                    </Box>
                                ) : softwarePackages.length === 0 ? (
                                    <Typography variant="body2" color="textSecondary" sx={{ fontStyle: 'italic', textAlign: 'center', py: 2 }}>
                                        {t('hostDetail.noSoftwareFound', 'No software packages found')}
                                    </Typography>
                                ) : (
                                    <>
                                        <Typography variant="body2" color="textSecondary" sx={{ mb: 2 }}>
                                            {t('hostDetail.showingPackages', 'Showing {{start}}-{{end}} of {{total}} packages', {
                                                start: ((softwarePagination.page - 1) * softwarePagination.page_size + 1).toLocaleString(i18n.language),
                                                end: Math.min(softwarePagination.page * softwarePagination.page_size, softwarePagination.total_items).toLocaleString(i18n.language),
                                                total: softwarePagination.total_items.toLocaleString(i18n.language)
                                            })}
                                        </Typography>
                                        <Grid container spacing={2}>
                                            {softwarePackages.map((pkg: SoftwarePackage, index: number) => (
                                            <Grid size={{ xs: 12, sm: 6, md: 4 }} key={pkg.id || index}>
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
                                                        <Box sx={{ mt: 2, display: 'flex', justifyContent: 'flex-end' }}>
                                                            <Button
                                                                variant="contained"
                                                                color="error"
                                                                size="small"
                                                                disabled={!host?.active || !host?.is_agent_privileged}
                                                                onClick={() => handleUninstallPackage(pkg)}
                                                                sx={{ minWidth: 'auto' }}
                                                            >
                                                                {t('hostDetail.uninstall', 'Uninstall')}
                                                            </Button>
                                                        </Box>
                                                    </CardContent>
                                                </Card>
                                            </Grid>
                                        ))}
                                    </Grid>
                                    <Box sx={{ display: 'flex', justifyContent: 'center', mt: 3 }}>
                                        <Pagination
                                            count={softwarePagination.total_pages}
                                            page={softwarePagination.page}
                                            onChange={(_, page) => {
                                                setSoftwarePagination(prev => ({ ...prev, page }));
                                            }}
                                            color="primary"
                                            size="large"
                                            showFirstButton
                                            showLastButton
                                        />
                                    </Box>
                                </>
                                )}
                            </CardContent>
                        </Card>
                    </Grid>
                </Grid>
            )}

            {/* Third-Party Repositories Tab */}
            {currentTab === getThirdPartyReposTabIndex() && host && (
                <ThirdPartyRepositories
                    hostId={hostId || ''}
                    privilegedMode={host.is_agent_privileged || false}
                    osName={host.platform || host.platform_release || ''}
                />
            )}

            {/* Access Tab */}
            {currentTab === getAccessTabIndex() && (
                <Grid container spacing={3}>
                    {/* User Accounts */}
                    <Grid size={{ xs: 12 }}>
                        <Card>
                            <CardContent>
                                <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 2 }}>
                                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
                                        <Typography variant="subtitle1" sx={{ display: 'flex', alignItems: 'center', fontWeight: 'bold', fontSize: '1.1rem' }}>
                                            <PersonIcon sx={{ mr: 1 }} />
                                            {t('hostDetail.userAccounts', 'User Accounts')} ({filteredUsers.length})
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
                                {filteredUsers.length === 0 ? (
                                    <Typography variant="body2" color="textSecondary" sx={{ fontStyle: 'italic', textAlign: 'center', py: 2 }}>
                                        {t('hostDetail.noUsersFound', 'No user accounts found')}
                                    </Typography>
                                ) : (
                                    <Grid container spacing={2}>
                                        {filteredUsers.map((user: UserAccount, index: number) => (
                                            <Grid size={{ xs: 12, sm: 6, md: 4 }} key={user.id || index}>
                                                <Card sx={{ backgroundColor: 'grey.900', height: '100%' }}>
                                                    <CardContent sx={{ p: 2 }}>
                                                        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', mb: 1 }}>
                                                            <Typography variant="subtitle2" sx={{ fontWeight: 'bold' }}>
                                                                {user.username}
                                                            </Typography>
                                                            {canDeploySshKey && (
                                                                <Button
                                                                    size="small"
                                                                    variant="outlined"
                                                                    color="primary"
                                                                    onClick={() => handleAddSSHKey(user)}
                                                                    disabled={!host?.active || !host?.is_agent_privileged}
                                                                    sx={{ minWidth: 'auto', fontSize: '0.7rem', py: 0.25, px: 1 }}
                                                                >
                                                                    {t('hostDetail.addSSHKey', 'Add SSH Key')}
                                                                </Button>
                                                            )}
                                                        </Box>
                                                        <Typography variant="body2" color="textSecondary" sx={{ mb: 0.5 }}>
                                                            {host?.platform?.toLowerCase().includes('windows') ? 'SID' : 'UID'}: {host?.platform?.toLowerCase().includes('windows') ? (user.security_id || t('common.notAvailable')) : (user.uid !== undefined ? user.uid : t('common.notAvailable'))}
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
                    <Grid size={{ xs: 12 }}>
                        <Card>
                            <CardContent>
                                <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 2 }}>
                                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
                                        <Typography variant="subtitle1" sx={{ display: 'flex', alignItems: 'center', fontWeight: 'bold', fontSize: '1.1rem' }}>
                                            <GroupIcon sx={{ mr: 1 }} />
                                            {t('hostDetail.userGroups', 'User Groups')} ({filteredGroups.length})
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
                                {filteredGroups.length === 0 ? (
                                    <Typography variant="body2" color="textSecondary" sx={{ fontStyle: 'italic', textAlign: 'center', py: 2 }}>
                                        {t('hostDetail.noGroupsFound', 'No user groups found')}
                                    </Typography>
                                ) : (
                                    <Grid container spacing={2}>
                                        {filteredGroups.map((group: UserGroup, index: number) => (
                                            <Grid size={{ xs: 12, sm: 6, md: 4 }} key={group.id || index}>
                                                <Card sx={{ backgroundColor: 'grey.900', height: '100%' }}>
                                                    <CardContent sx={{ p: 2 }}>
                                                        <Typography variant="subtitle2" sx={{ fontWeight: 'bold', mb: 1 }}>
                                                            {group.group_name}
                                                        </Typography>
                                                        <Typography variant="body2" color="textSecondary" sx={{ mb: 0.5 }}>
                                                            {host?.platform?.toLowerCase().includes('windows') ? 'SID' : 'GID'}: {host?.platform?.toLowerCase().includes('windows') ? (group.security_id || t('common.notAvailable')) : (group.gid !== undefined && group.gid !== null ? group.gid : t('common.notAvailable'))}
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

            {/* Security Tab */}
            {currentTab === getSecurityTabIndex() && hostId && (
                <Grid container spacing={3}>
                    <Grid size={{ xs: 12, md: 6 }} sx={{ display: 'flex' }}>
                        <AntivirusStatusCard
                            hostId={hostId}
                            onDeployAntivirus={handleDeployAntivirus}
                            onEnableAntivirus={handleEnableAntivirus}
                            onDisableAntivirus={handleDisableAntivirus}
                            onRemoveAntivirus={handleRemoveAntivirus}
                            canDeployAntivirus={canDeployAntivirus}
                            canEnableAntivirus={canEnableAntivirus}
                            canDisableAntivirus={canDisableAntivirus}
                            canRemoveAntivirus={canRemoveAntivirus}
                            isHostActive={host?.active || false}
                            isAgentPrivileged={host?.is_agent_privileged || false}
                            hasOsDefault={hasAntivirusOsDefault}
                            refreshTrigger={antivirusRefreshTrigger}
                            sx={{ height: '100%', width: '100%' }}
                        />
                    </Grid>
                    <Grid size={{ xs: 12, md: 6 }} sx={{ display: 'flex' }}>
                        <CommercialAntivirusStatusCard
                            hostId={hostId}
                            refreshTrigger={antivirusRefreshTrigger}
                            sx={{ height: '100%', width: '100%' }}
                        />
                    </Grid>
                    <Grid size={{ xs: 12, md: 6 }}>
                        <FirewallStatusCard
                            hostId={hostId}
                            refreshTrigger={antivirusRefreshTrigger}
                        />
                    </Grid>
                </Grid>
            )}

            {/* Certificates Tab */}
            {currentTab === getCertificatesTabIndex() && (
                <Grid container spacing={3}>
                    <Grid size={{ xs: 12 }}>
                        <Card>
                            <CardContent>
                                <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 2 }}>
                                    <Typography variant="subtitle1" sx={{ display: 'flex', alignItems: 'center', fontWeight: 'bold', fontSize: '1.1rem' }}>
                                        <CertificateIcon sx={{ mr: 1 }} />
                                        {t('hostDetail.certificates', 'SSL Certificates')} ({certificates.length})
                                    </Typography>
                                    <Box sx={{ display: 'flex', gap: 4, alignItems: 'center' }}>
                                        <TextField
                                            size="small"
                                            placeholder={t('hostDetail.searchCertificates', 'Search certificates...')}
                                            value={certificateSearchTerm}
                                            onChange={(e) => {
                                                setCertificateSearchTerm(e.target.value);
                                                setCertificatePaginationModel({ page: 0, pageSize: certificatePaginationModel.pageSize });
                                            }}
                                            InputProps={{
                                                startAdornment: (
                                                    <InputAdornment position="start">
                                                        <SearchIcon />
                                                    </InputAdornment>
                                                ),
                                            }}
                                            sx={{ width: 350 }}
                                        />
                                        <ToggleButtonGroup
                                            value={certificateFilter}
                                            exclusive
                                            onChange={(_, newFilter) => {
                                                if (newFilter !== null) {
                                                    setCertificateFilter(newFilter);
                                                    setCertificatePaginationModel({ page: 0, pageSize: certificatePaginationModel.pageSize });
                                                }
                                            }}
                                            size="small"
                                            sx={{ height: '36.5px' }}
                                        >
                                            <ToggleButton value="server" sx={{ px: 2 }}>
                                                {t('hostDetail.server', 'Server')}
                                            </ToggleButton>
                                            <ToggleButton value="client" sx={{ px: 2 }}>
                                                {t('hostDetail.client', 'Client')}
                                            </ToggleButton>
                                            <ToggleButton value="ca" sx={{ px: 2 }}>
                                                CA
                                            </ToggleButton>
                                            <ToggleButton value="all" sx={{ px: 2 }}>
                                                {t('common.all', 'All')}
                                            </ToggleButton>
                                        </ToggleButtonGroup>
                                        {canDeployCertificate && (
                                            <Button
                                                variant="outlined"
                                                startIcon={<AddIcon />}
                                                onClick={() => {
                                                    setAddCertificateDialogOpen(true);
                                                    loadAvailableCertificates();
                                                }}
                                                disabled={!host.active || !host.is_agent_privileged}
                                                sx={{ minWidth: 100, height: '36.5px' }}
                                            >
                                                {t('hostDetail.addCertificate', 'Add')}
                                            </Button>
                                        )}
                                        <Button
                                            variant="outlined"
                                            startIcon={<RefreshIcon />}
                                            onClick={requestCertificatesCollection}
                                            disabled={certificatesLoading || !host.active}
                                            sx={{ minWidth: 120, height: '36.5px' }}
                                        >
                                            {certificatesLoading ?
                                                <CircularProgress size={20} /> :
                                                t('hostDetail.collectCertificates', 'Collect')
                                            }
                                        </Button>
                                    </Box>
                                </Box>

                                {/* Certificates will be implemented in the next step */}
                                {certificatesLoading && (
                                    <Box sx={{ display: 'flex', justifyContent: 'center', p: 3 }}>
                                        <CircularProgress />
                                    </Box>
                                )}

                                {/* Certificate DataGrid */}
                                {!certificatesLoading && (
                                    <>
                                        <Box sx={{ mb: 1, display: 'flex', alignItems: 'center', justifyContent: 'flex-end' }}>
                                            <ColumnVisibilityButton
                                                columns={certificateColumns.map(col => ({ field: col.field, headerName: col.headerName || col.field }))}
                                                hiddenColumns={hiddenCertificatesColumns}
                                                onColumnsChange={setHiddenCertificatesColumns}
                                                onReset={resetCertificatesPreferences}
                                            />
                                        </Box>
                                        <DataGrid
                                            rows={certificates.filter(cert => {
                                                // Apply search filter first
                                                if (certificateSearchTerm) {
                                                    const searchLower = certificateSearchTerm.toLowerCase();
                                                    const nameMatch = cert.certificate_name?.toLowerCase().includes(searchLower);
                                                    const subjectMatch = cert.subject?.toLowerCase().includes(searchLower);
                                                    const issuerMatch = cert.issuer?.toLowerCase().includes(searchLower);
                                                    if (!nameMatch && !subjectMatch && !issuerMatch) {
                                                        return false;
                                                    }
                                                }

                                                // Apply type filter
                                                if (certificateFilter === 'all') return true;
                                                if (certificateFilter === 'ca') {
                                                    return cert.is_ca || cert.key_usage === 'CA';
                                                }
                                                if (certificateFilter === 'server') {
                                                    return cert.key_usage === 'Server';
                                                }
                                                if (certificateFilter === 'client') {
                                                    return cert.key_usage === 'Client';
                                                }
                                                return true;
                                            })}
                                            columns={certificateColumns}
                                            loading={certificatesLoading}
                                            initialState={{
                                                sorting: {
                                                    sortModel: [{ field: 'days_until_expiry', sort: 'asc' }],
                                                },
                                            }}
                                            columnVisibilityModel={getCertificatesColumnVisibilityModel()}
                                            paginationModel={certificatePaginationModel}
                                            onPaginationModelChange={setCertificatePaginationModel}
                                            pageSizeOptions={safePageSizeOptions}
                                            disableRowSelectionOnClick
                                            autoHeight
                                            sx={{
                                                '& .MuiDataGrid-row': {
                                                    '&:hover': {
                                                        backgroundColor: 'action.hover',
                                                    },
                                                },
                                            }}
                                        />
                                    </>
                                )}
                            </CardContent>
                        </Card>
                    </Grid>
                </Grid>
            )}

            {/* Software Changes Tab */}
            {currentTab === getSoftwareInstallsTabIndex() && (
                <Grid container spacing={3}>
                    <Grid size={{ xs: 12 }}>
                        <Card>
                            <CardContent>
                                <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 2 }}>
                                    <Typography variant="subtitle1" sx={{ display: 'flex', alignItems: 'center', fontWeight: 'bold', fontSize: '1.1rem' }}>
                                        <HistoryIcon sx={{ mr: 1 }} />
                                        {t('hostDetail.softwareInstallationHistory', 'Software Installation History')}
                                    </Typography>
                                </Box>

                                {installationHistoryLoading ? (
                                    <Box sx={{ display: 'flex', justifyContent: 'center', py: 4 }}>
                                        <CircularProgress />
                                    </Box>
                                ) : installationHistory.length === 0 ? (
                                    <Typography variant="body2" color="textSecondary" sx={{ textAlign: 'center', py: 4 }}>
                                        {t('hostDetail.noInstallationHistory', 'No software installation history found for this host.')}
                                    </Typography>
                                ) : (
                                    <TableContainer>
                                        <Table>
                                            <TableHead>
                                                <TableRow>
                                                    <TableCell>{t('hostDetail.packageNames', 'Package Names')}</TableCell>
                                                    <TableCell>{t('hostDetail.operation', 'Operation')}</TableCell>
                                                    <TableCell>{t('hostDetail.requestedBy', 'Requested By')}</TableCell>
                                                    <TableCell>{t('hostDetail.requestedAt', 'Requested At')}</TableCell>
                                                    <TableCell>{t('hostDetail.status', 'Status')}</TableCell>
                                                    <TableCell>{t('hostDetail.completedAt', 'Completed At')}</TableCell>
                                                    <TableCell>{t('hostDetail.actions', 'Actions')}</TableCell>
                                                </TableRow>
                                            </TableHead>
                                            <TableBody>
                                                {installationHistory.map((installation) => (
                                                    <TableRow key={installation.request_id}>
                                                        <TableCell>{installation.package_names}</TableCell>
                                                        <TableCell>
                                                            <Chip
                                                                label={(installation.operation_type || 'install') === 'install' ? t('hostDetail.install', 'Install') : t('hostDetail.uninstall', 'Uninstall')}
                                                                color={(installation.operation_type || 'install') === 'install' ? 'primary' : 'error'}
                                                                size="small"
                                                                variant="outlined"
                                                            />
                                                        </TableCell>
                                                        <TableCell>{installation.requested_by}</TableCell>
                                                        <TableCell>{formatDateTime(installation.requested_at)}</TableCell>
                                                        <TableCell>
                                                            <Chip
                                                                label={getTranslatedStatus(installation.status)}
                                                                color={getInstallationStatusColor(installation.status)}
                                                                size="small"
                                                            />
                                                        </TableCell>
                                                        <TableCell>
                                                            {installation.completed_at ? formatDateTime(installation.completed_at) : '-'}
                                                        </TableCell>
                                                        <TableCell>
                                                            <IconButton
                                                                size="small"
                                                                onClick={() => handleViewInstallationLog(installation)}
                                                                disabled={installation.status === 'pending' || installation.status === 'queued' || installation.status === 'in_progress' || installation.status === 'installing'}
                                                                title={t('hostDetail.viewInstallationLog', 'View Installation Log')}
                                                                sx={{ mr: 1 }}
                                                            >
                                                                <VisibilityIcon />
                                                            </IconButton>
                                                            <IconButton
                                                                size="small"
                                                                onClick={() => handleDeleteInstallation(installation)}
                                                                title={t('hostDetail.deleteInstallation', 'Delete Installation Record')}
                                                                color="error"
                                                            >
                                                                <DeleteIcon />
                                                            </IconButton>
                                                        </TableCell>
                                                    </TableRow>
                                                ))}
                                            </TableBody>
                                        </Table>
                                    </TableContainer>
                                )}
                            </CardContent>
                        </Card>
                    </Grid>
                </Grid>
            )}

            {/* Server Roles Tab */}
            {currentTab === getServerRolesTabIndex() && (
                <Grid container spacing={3}>
                    <Grid size={{ xs: 12 }}>
                        <Card>
                            <CardContent>
                                <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 2 }}>
                                    <Typography variant="subtitle1" sx={{ display: 'flex', alignItems: 'center', fontWeight: 'bold', fontSize: '1.1rem' }}>
                                        <AssignmentIcon sx={{ mr: 1 }} />
                                        {t('hostDetail.serverRoles', 'Server Roles')} ({roles.length})
                                    </Typography>
                                    <Box sx={{ display: 'flex', gap: 2, alignItems: 'center' }}>
                                        <Button
                                            variant="outlined"
                                            onClick={requestRolesCollection}
                                            disabled={rolesLoading || !host.active}
                                            sx={{ minWidth: 120, height: '36.5px' }}
                                        >
                                            {rolesLoading ?
                                                <CircularProgress size={20} /> :
                                                t('hostDetail.collectRoles', 'Collect')
                                            }
                                        </Button>
                                    </Box>
                                </Box>
                                {rolesLoading && (
                                    <Box sx={{ display: 'flex', justifyContent: 'center', p: 3 }}>
                                        <CircularProgress />
                                    </Box>
                                )}
                                {/* Server Roles Table */}
                                {!rolesLoading && (
                                    <TableContainer>
                                        <Table>
                                            <TableHead>
                                                <TableRow>
                                                    <TableCell padding="checkbox">
                                                        <Checkbox
                                                            indeterminate={selectedRoles.length > 0 && selectedRoles.length < roles.filter(role => role.service_name && role.service_name.trim() !== '').length}
                                                            checked={roles.filter(role => role.service_name && role.service_name.trim() !== '').length > 0 && selectedRoles.length === roles.filter(role => role.service_name && role.service_name.trim() !== '').length}
                                                            onChange={(e) => handleSelectAllRoles(e.target.checked)}
                                                            disabled={!host.is_agent_privileged || roles.filter(role => role.service_name && role.service_name.trim() !== '').length === 0}
                                                        />
                                                    </TableCell>
                                                    <TableCell>{t('hostDetail.role', 'Role')}</TableCell>
                                                    <TableCell>{t('hostDetail.package', 'Package')}</TableCell>
                                                    <TableCell>{t('hostDetail.version', 'Version')}</TableCell>
                                                    <TableCell>{t('hostDetail.service', 'Service')}</TableCell>
                                                    <TableCell>{t('hostDetail.status', 'Status')}</TableCell>
                                                    <TableCell>{t('hostDetail.detected', 'Detected')}</TableCell>
                                                </TableRow>
                                            </TableHead>
                                            <TableBody>
                                                {roles.length === 0 ? (
                                                    <TableRow>
                                                        <TableCell colSpan={7} align="center">
                                                            <Typography variant="body2" sx={{ fontStyle: 'italic', color: 'textSecondary', py: 2 }}>
                                                                {t('hostDetail.noRolesDetected', 'No server roles detected')}
                                                            </Typography>
                                                        </TableCell>
                                                    </TableRow>
                                                ) : (
                                                    roles.map((role) => (
                                                        <TableRow key={role.id}>
                                                            <TableCell padding="checkbox">
                                                                <Checkbox
                                                                    checked={selectedRoles.includes(role.id)}
                                                                    onChange={(e) => handleRoleSelection(role.id, e.target.checked)}
                                                                    disabled={!host.is_agent_privileged || !role.service_name || role.service_name.trim() === ''}
                                                                />
                                                            </TableCell>
                                                            <TableCell>
                                                                <Typography variant="body2" sx={{ fontWeight: 'bold' }}>
                                                                    {role.role}
                                                                </Typography>
                                                            </TableCell>
                                                            <TableCell>
                                                                <Typography variant="body2">
                                                                    {role.package_name}
                                                                </Typography>
                                                            </TableCell>
                                                            <TableCell>
                                                                <Typography variant="body2">
                                                                    {role.package_version || t('common.unknown', 'Unknown')}
                                                                </Typography>
                                                            </TableCell>
                                                            <TableCell>
                                                                <Typography variant="body2">
                                                                    {role.service_name || t('common.none', 'None')}
                                                                </Typography>
                                                            </TableCell>
                                                            <TableCell>
                                                                <Chip
                                                                    label={
                                                                        role.service_status === 'running'
                                                                            ? t('hostDetail.running', 'Running')
                                                                            : role.service_status === 'stopped'
                                                                            ? t('hostDetail.stopped', 'Stopped')
                                                                            : role.service_status === 'installed'
                                                                            ? t('hostDetail.installed', 'Installed')
                                                                            : role.service_status || t('common.unknown', 'Unknown')
                                                                    }
                                                                    color={
                                                                        role.service_status === 'running'
                                                                            ? 'success'
                                                                            : role.service_status === 'stopped'
                                                                            ? 'error'
                                                                            : role.service_status === 'installed'
                                                                            ? 'info'
                                                                            : 'default'
                                                                    }
                                                                    size="small"
                                                                />
                                                            </TableCell>
                                                            <TableCell>
                                                                <Typography variant="body2" sx={{ color: 'textSecondary' }}>
                                                                    {new Date(role.detected_at).toLocaleDateString()}
                                                                </Typography>
                                                            </TableCell>
                                                        </TableRow>
                                                    ))
                                                )}
                                            </TableBody>
                                        </Table>
                                    </TableContainer>
                                )}

                                {/* Service Control Buttons */}
                                {!rolesLoading && roles.length > 0 && roles.some(role => role.service_name && role.service_name.trim() !== '') && (canStartService || canStopService || canRestartService) && (
                                    <Box sx={{ mt: 3, pt: 2, borderTop: '1px solid', borderColor: 'divider', display: 'flex', gap: 2, alignItems: 'center' }}>
                                        <Typography variant="body2" sx={{ color: 'textSecondary', mr: 2 }}>
                                            {t('hostDetail.serviceControlActions', 'Service Control Actions')}:
                                        </Typography>
                                        {canStartService && (
                                            <Button
                                                variant="contained"
                                                color="success"
                                                startIcon={<PlayArrowIcon />}
                                                onClick={() => handleServiceControl('start')}
                                                disabled={!host.is_agent_privileged || selectedRoles.length === 0 || serviceControlLoading}
                                                sx={{ minWidth: 100 }}
                                            >
                                                {serviceControlLoading ? <CircularProgress size={20} /> : t('hostDetail.start', 'Start')}
                                            </Button>
                                        )}
                                        {canStopService && (
                                            <Button
                                                variant="contained"
                                                color="error"
                                                startIcon={<StopIcon />}
                                                onClick={() => handleServiceControl('stop')}
                                                disabled={!host.is_agent_privileged || selectedRoles.length === 0 || serviceControlLoading}
                                                sx={{ minWidth: 100 }}
                                            >
                                                {serviceControlLoading ? <CircularProgress size={20} /> : t('hostDetail.stop', 'Stop')}
                                            </Button>
                                        )}
                                        {canRestartService && (
                                            <Button
                                                variant="contained"
                                                color="warning"
                                                startIcon={<RestartAltIcon />}
                                                onClick={() => handleServiceControl('restart')}
                                                disabled={!host.is_agent_privileged || selectedRoles.length === 0 || serviceControlLoading}
                                                sx={{ minWidth: 100 }}
                                            >
                                                {serviceControlLoading ? <CircularProgress size={20} /> : t('hostDetail.restart', 'Restart')}
                                            </Button>
                                        )}
                                        {!host.is_agent_privileged && (
                                            <Typography variant="caption" sx={{ color: 'warning.main', ml: 2 }}>
                                                {t('hostDetail.privilegedModeRequired', 'Privileged mode required for service control')}
                                            </Typography>
                                        )}
                                        {selectedRoles.length > 0 && (
                                            <Typography variant="caption" sx={{ color: 'primary.main', ml: 2 }}>
                                                {t('hostDetail.selectedServices', `${selectedRoles.length} service(s) selected`)}
                                            </Typography>
                                        )}
                                    </Box>
                                )}
                            </CardContent>
                        </Card>
                    </Grid>
                </Grid>
            )}

            {/* Ubuntu Pro Tab */}
            {currentTab === getUbuntuProTabIndex() && ubuntuProInfo?.available && (
                <Grid container spacing={3}>
                    <Grid size={{ xs: 12 }}>
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
                                                        canDetachUbuntuPro && (
                                                            <Button
                                                                variant="outlined"
                                                                color="warning"
                                                                size="small"
                                                                onClick={handleUbuntuProDetach}
                                                                startIcon={<DeleteIcon />}
                                                            >
                                                                {t('hostDetail.ubuntuProDetach', 'Detach')}
                                                            </Button>
                                                        )
                                                    ) : (
                                                        canAttachUbuntuPro && (
                                                            <Button
                                                                variant="outlined"
                                                                color="primary"
                                                                size="small"
                                                                onClick={handleUbuntuProAttach}
                                                                startIcon={<VerifiedUserIcon />}
                                                            >
                                                                {t('hostDetail.ubuntuProAttach', 'Attach')}
                                                            </Button>
                                                        )
                                                    )}
                                                </>
                                            )}
                                        </Box>
                                    )}
                                </Box>

                                <Grid container spacing={2} sx={{ mt: 1 }}>
                                    <Grid size={{ xs: 12, md: 6 }}>
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

                                    <Grid size={{ xs: 12, md: 6 }}>
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
                                                            <Grid size={{ xs: 12 }} key={index}>
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
                    <Grid size={{ xs: 12 }}>
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
                                            <Grid size={{ xs: 12 }} key={diagnostic.id || index}>
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
            </Box>

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
                                        <Grid size={{ xs: 12, sm: 6 }}>
                                            <Typography variant="body2" color="textSecondary">
                                                {t('hostDetail.collectionId', 'Collection ID')}
                                            </Typography>
                                            <Typography variant="body1" sx={{ fontFamily: 'monospace' }}>
                                                {selectedDiagnostic.collection_id}
                                            </Typography>
                                        </Grid>
                                        <Grid size={{ xs: 12, sm: 6 }}>
                                            <Typography variant="body2" color="textSecondary">
                                                {t('hostDetail.collectionStatus', 'Status')}
                                            </Typography>
                                            <Chip
                                                label={selectedDiagnostic.status}
                                                color={selectedDiagnostic.status === 'completed' ? 'success' : 'warning'}
                                                size="small"
                                            />
                                        </Grid>
                                        <Grid size={{ xs: 12, sm: 6 }}>
                                            <Typography variant="body2" color="textSecondary">
                                                {t('hostDetail.requestedAt', 'Requested At')}
                                            </Typography>
                                            <Typography variant="body1">
                                                {formatDate(selectedDiagnostic.requested_at)}
                                            </Typography>
                                        </Grid>
                                        <Grid size={{ xs: 12, sm: 6 }}>
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

            {/* Ubuntu Pro Detach Confirmation Dialog */}
            <Dialog
                open={ubuntuProDetachConfirmOpen}
                onClose={handleCancelUbuntuProDetach}
                aria-labelledby="ubuntu-pro-detach-dialog-title"
                aria-describedby="ubuntu-pro-detach-dialog-description"
                maxWidth="sm"
                fullWidth
            >
                <DialogTitle id="ubuntu-pro-detach-dialog-title">
                    {t('hostDetail.ubuntuProDetachConfirmTitle', 'Confirm Ubuntu Pro Detach')}
                </DialogTitle>
                <DialogContent>
                    <DialogContentText id="ubuntu-pro-detach-dialog-description">
                        {t('hostDetail.ubuntuProDetachConfirmMessage', 'Are you sure you want to detach Ubuntu Pro from this system? This will remove all Ubuntu Pro benefits and services for this host.')}
                    </DialogContentText>
                </DialogContent>
                <DialogActions>
                    <Button onClick={handleCancelUbuntuProDetach} color="primary">
                        {t('common.cancel', 'Cancel')}
                    </Button>
                    <Button
                        onClick={handleConfirmUbuntuProDetach}
                        color="warning"
                        variant="contained"
                        autoFocus
                    >
                        {t('hostDetail.ubuntuProDetachConfirm', 'Detach')}
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
                    {ubuntuProToken && (
                        <Alert severity="info" sx={{ mb: 2 }}>
                            {t('hostDetail.ubuntuProMasterTokenPreFilled', 'Master Ubuntu Pro token has been pre-filled from settings.')}
                        </Alert>
                    )}
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

            {/* Package Installation Dialog */}
            <Dialog
                open={packageInstallDialogOpen}
                onClose={handleClosePackageDialog}
                maxWidth="md"
                fullWidth
                PaperProps={{
                    sx: { backgroundColor: 'grey.900', minHeight: '500px' }
                }}
            >
                <DialogTitle sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontWeight: 'bold', fontSize: '1.25rem' }}>
                    {t('hostDetail.installPackagesTitle', 'Install Packages')}
                    <IconButton onClick={handleClosePackageDialog} size="small">
                        <CloseIcon />
                    </IconButton>
                </DialogTitle>
                <DialogContent sx={{ p: 3 }}>
                    <Box sx={{ mb: 3 }}>
                        <Box sx={{ display: 'flex', gap: 1, mb: 2 }}>
                            <TextField
                                fullWidth
                                placeholder="Enter package name to search..."
                                variant="outlined"
                                inputRef={packageSearchInputRef}
                            />
                            <Button
                                variant="contained"
                                onClick={() => {
                                    const query = packageSearchInputRef.current?.value || '';
                                    if (query.length >= 2) {
                                        performPackageSearch(query);
                                    }
                                }}
                                sx={{ height: '56px', minWidth: '100px' }}
                            >
                                {isSearching ? <CircularProgress size={20} /> : 'Search'}
                            </Button>
                        </Box>
                    </Box>

                    {searchResults.length > 0 && (
                        <Box sx={{ mb: 3 }}>
                            <Typography variant="subtitle2" sx={{ fontWeight: 'bold', mb: 1 }}>
                                {t('hostDetail.searchResults', 'Search Results')}
                            </Typography>
                            <List sx={{ bgcolor: 'grey.800', borderRadius: 1, maxHeight: 300, overflow: 'auto' }}>
                                {searchResults.map((pkg, index) => (
                                    <React.Fragment key={pkg.name}>
                                        <ListItem
                                            sx={{
                                                display: 'flex',
                                                justifyContent: 'space-between',
                                                alignItems: 'center',
                                                py: 1
                                            }}
                                        >
                                            <ListItemText
                                                primary={pkg.name}
                                                secondary={
                                                    <span>
                                                        {pkg.description && (
                                                            <Typography variant="body2" color="textSecondary" component="span" display="block">
                                                                {pkg.description}
                                                            </Typography>
                                                        )}
                                                        {pkg.version && (
                                                            <Typography variant="caption" color="textSecondary" component="span" display="block">
                                                                {t('hostDetail.version', 'Version')}: {pkg.version}
                                                            </Typography>
                                                        )}
                                                    </span>
                                                }
                                            />
                                            <Button
                                                variant="contained"
                                                size="small"
                                                onClick={() => handlePackageSelect(pkg.name)}
                                                disabled={selectedPackages.has(pkg.name)}
                                                sx={{ ml: 2, minWidth: '80px' }}
                                            >
                                                {selectedPackages.has(pkg.name) ?
                                                    t('hostDetail.added', 'Added') :
                                                    t('hostDetail.install', 'Install')
                                                }
                                            </Button>
                                        </ListItem>
                                        {index < searchResults.length - 1 && <Divider />}
                                    </React.Fragment>
                                ))}
                            </List>
                        </Box>
                    )}

                    {searchResults.length === 0 && !isSearching && (
                        <Typography variant="body2" color="textSecondary" sx={{ textAlign: 'center', py: 2 }}>
                            {t('hostDetail.noPackagesFound', 'No packages found matching your search')}
                        </Typography>
                    )}

                    <Box sx={{ mt: 3, mb: 3 }}>
                        <Typography variant="subtitle2" sx={{ fontWeight: 'bold', mb: 1 }}>
                            {t('hostDetail.packagesToInstall', 'Packages to install')} ({selectedPackages.size})
                        </Typography>
                        {selectedPackages.size > 0 ? (
                            <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 1 }}>
                                {Array.from(selectedPackages).map((pkg) => (
                                    <Chip
                                        key={pkg}
                                        label={pkg}
                                        onDelete={() => handlePackageSelect(pkg)}
                                        color="primary"
                                        variant="outlined"
                                    />
                                ))}
                            </Box>
                        ) : (
                            <Typography variant="body2" color="textSecondary" sx={{ fontStyle: 'italic' }}>
                                {t('hostDetail.noPackagesSelected', 'No packages selected for installation')}
                            </Typography>
                        )}
                    </Box>
                </DialogContent>
                <DialogActions sx={{ p: 3, pt: 0 }}>
                    <Button onClick={handleClosePackageDialog}>
                        {t('common.cancel', 'Cancel')}
                    </Button>
                    <Button
                        onClick={handleInstallPackages}
                        variant="contained"
                        disabled={selectedPackages.size === 0}
                        startIcon={<SystemUpdateAltIcon />}
                    >
                        {t('hostDetail.installSelectedPackages', 'Install Selected Packages')} ({selectedPackages.size})
                    </Button>
                </DialogActions>
            </Dialog>

            {/* Installation Log Dialog */}
            <Dialog
                open={installationLogDialogOpen}
                onClose={handleCloseInstallationLogDialog}
                maxWidth="md"
                fullWidth
            >
                <DialogTitle sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                    {t('hostDetail.installationLogTitle', 'Installation Log')} - {selectedInstallationLog?.package_name}
                    <IconButton
                        edge="end"
                        color="inherit"
                        onClick={handleCloseInstallationLogDialog}
                        aria-label="close"
                    >
                        <CloseIcon />
                    </IconButton>
                </DialogTitle>
                <DialogContent sx={{ p: 3 }}>
                    {selectedInstallationLog && (
                        <Box>
                            <Grid container spacing={2} sx={{ mb: 3 }}>
                                <Grid size={{ xs: 6 }}>
                                    <Typography variant="body2" color="textSecondary">
                                        {t('hostDetail.status', 'Status')}:
                                    </Typography>
                                    <Chip
                                        label={getTranslatedStatus(selectedInstallationLog.status)}
                                        color={getInstallationStatusColor(selectedInstallationLog.status)}
                                        size="small"
                                        sx={{ mt: 0.5 }}
                                    />
                                </Grid>
                                <Grid size={{ xs: 6 }}>
                                    <Typography variant="body2" color="textSecondary">
                                        {t('hostDetail.requestedBy', 'Requested By')}:
                                    </Typography>
                                    <Typography variant="body1">
                                        {selectedInstallationLog.requested_by}
                                    </Typography>
                                </Grid>
                                <Grid size={{ xs: 6 }}>
                                    <Typography variant="body2" color="textSecondary">
                                        {t('hostDetail.requestedAt', 'Requested At')}:
                                    </Typography>
                                    <Typography variant="body1">
                                        {formatDateTime(selectedInstallationLog.requested_at)}
                                    </Typography>
                                </Grid>
                                <Grid size={{ xs: 6 }}>
                                    <Typography variant="body2" color="textSecondary">
                                        {t('hostDetail.completedAt', 'Completed At')}:
                                    </Typography>
                                    <Typography variant="body1">
                                        {selectedInstallationLog.completed_at
                                            ? formatDateTime(selectedInstallationLog.completed_at)
                                            : t('common.notAvailable', 'N/A')
                                        }
                                    </Typography>
                                </Grid>
                                {selectedInstallationLog.installed_version && (
                                    <Grid size={{ xs: 6 }}>
                                        <Typography variant="body2" color="textSecondary">
                                            {t('hostDetail.installedVersion', 'Installed Version')}:
                                        </Typography>
                                        <Typography variant="body1">
                                            {selectedInstallationLog.installed_version}
                                        </Typography>
                                    </Grid>
                                )}
                            </Grid>

                            {selectedInstallationLog.error_message && (
                                <Box sx={{ mb: 3 }}>
                                    <Typography variant="body2" color="textSecondary" sx={{ mb: 1 }}>
                                        {t('hostDetail.errorMessage', 'Error Message')}:
                                    </Typography>
                                    <Alert severity="error">
                                        {selectedInstallationLog.error_message}
                                    </Alert>
                                </Box>
                            )}

                            {selectedInstallationLog.installation_log && (
                                <Box>
                                    <Typography variant="body2" color="textSecondary" sx={{ mb: 1 }}>
                                        {t('hostDetail.installationLog', 'Installation Log')}:
                                    </Typography>
                                    <Paper
                                        sx={{
                                            p: 2,
                                            backgroundColor: 'grey.900',
                                            maxHeight: 400,
                                            overflow: 'auto',
                                            fontFamily: 'monospace',
                                            fontSize: '0.875rem',
                                            whiteSpace: 'pre-wrap',
                                        }}
                                    >
                                        {selectedInstallationLog.installation_log}
                                    </Paper>
                                </Box>
                            )}

                            {!selectedInstallationLog.installation_log && !selectedInstallationLog.error_message && (
                                <Typography variant="body2" color="textSecondary" sx={{ textAlign: 'center', py: 2 }}>
                                    {t('hostDetail.noLogDataAvailable', 'No log data available for this installation.')}
                                </Typography>
                            )}
                        </Box>
                    )}
                </DialogContent>
                <DialogActions>
                    <Button onClick={handleCloseInstallationLogDialog}>
                        {t('common.close', 'Close')}
                    </Button>
                </DialogActions>
            </Dialog>

            {/* Installation Delete Confirmation Dialog */}
            <Dialog
                open={installationDeleteConfirmOpen}
                onClose={handleCancelDeleteInstallation}
                maxWidth="sm"
                fullWidth
            >
                <DialogTitle>
                    {t('hostDetail.confirmDeleteInstallation', 'Delete Installation Record')}
                </DialogTitle>
                <DialogContent>
                    <Typography>
                        {t('hostDetail.confirmDeleteInstallationMessage', 'Are you sure you want to delete this installation record? This action cannot be undone.')}
                    </Typography>
                    {installationToDelete && (
                        <Typography variant="body2" sx={{ mt: 2, fontWeight: 'bold' }}>
                            {t('hostDetail.packages', 'Packages')}: {installationToDelete.package_names}
                        </Typography>
                    )}
                </DialogContent>
                <DialogActions>
                    <Button onClick={handleCancelDeleteInstallation}>
                        {t('common.cancel', 'Cancel')}
                    </Button>
                    <Button
                        onClick={handleConfirmDeleteInstallation}
                        color="error"
                        variant="contained"
                    >
                        {t('common.delete', 'Delete')}
                    </Button>
                </DialogActions>
            </Dialog>

            {/* Request Packages Confirmation Dialog */}
            <Dialog
                open={requestPackagesConfirmOpen}
                onClose={() => setRequestPackagesConfirmOpen(false)}
                maxWidth="sm"
                fullWidth
            >
                <DialogTitle>
                    {t('hostDetail.confirmRequestPackages', 'Request Available Packages')}
                </DialogTitle>
                <DialogContent>
                    <Typography>
                        {t('hostDetail.confirmRequestPackagesMessage', 'This will trigger package collection on the host, which can be resource-intensive and may take several minutes to complete. Do you want to proceed?')}
                    </Typography>
                </DialogContent>
                <DialogActions>
                    <Button onClick={() => setRequestPackagesConfirmOpen(false)}>
                        {t('common.no', 'No')}
                    </Button>
                    <Button
                        onClick={handleRequestPackagesConfirm}
                        color="primary"
                        variant="contained"
                    >
                        {t('common.yes', 'Yes')}
                    </Button>
                </DialogActions>
            </Dialog>

            {/* Package Uninstall Confirmation Dialog */}
            <Dialog
                open={uninstallConfirmOpen}
                onClose={handleUninstallCancel}
                maxWidth="sm"
                fullWidth
            >
                <DialogTitle>
                    {t('hostDetail.confirmUninstallPackage', 'Uninstall Package')}
                </DialogTitle>
                <DialogContent>
                    <Typography>
                        {t('hostDetail.confirmUninstallMessage', 'Are you sure you want to uninstall this package? This action will remove the package from the system.')}
                    </Typography>
                    {packageToUninstall && (
                        <Typography variant="body2" sx={{ mt: 2, fontWeight: 'bold' }}>
                            {t('hostDetail.package', 'Package')}: {packageToUninstall.package_name}
                        </Typography>
                    )}
                </DialogContent>
                <DialogActions>
                    <Button onClick={handleUninstallCancel}>
                        {t('common.cancel', 'Cancel')}
                    </Button>
                    <Button
                        onClick={handleUninstallConfirm}
                        color="error"
                        variant="contained"
                    >
                        {t('hostDetail.uninstall', 'Uninstall')}
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

            {/* SSH Key Selection Dialog */}
            <Dialog
                open={sshKeyDialogOpen}
                onClose={handleSSHKeyDialogClose}
                maxWidth="md"
                fullWidth
            >
                <DialogTitle>
                    {t('hostDetail.addSSHKeyToUser', 'Add SSH Key to {user}').replace('{user}', selectedUser?.username || '')}
                </DialogTitle>
                <DialogContent sx={{ minHeight: '500px' }}>
                    <Typography variant="body2" color="textSecondary" sx={{ mb: 2 }}>
                        {t('hostDetail.selectSSHKeysToAdd', 'Select the SSH keys you want to add to this user:')}
                    </Typography>

                    {/* Search Field */}
                    <Box sx={{ mb: 2, display: 'flex', gap: 1 }}>
                        <TextField
                            fullWidth
                            placeholder={t('hostDetail.searchSSHKeys', 'Search SSH keys by name or filename...')}
                            value={sshKeySearchTerm}
                            onChange={(e) => setSshKeySearchTerm(e.target.value)}
                            size="small"
                            InputProps={{
                                startAdornment: (
                                    <InputAdornment position="start">
                                        <SearchIcon />
                                    </InputAdornment>
                                ),
                            }}
                            onKeyPress={(e) => {
                                if (e.key === 'Enter') {
                                    handleSSHKeySearch();
                                }
                            }}
                        />
                        <Button
                            variant="outlined"
                            onClick={handleSSHKeySearch}
                            sx={{ minWidth: 'auto', px: 3 }}
                        >
                            {t('common.search', 'Search')}
                        </Button>
                    </Box>

                    {availableSSHKeys.length === 0 ? (
                        <Typography variant="body2" color="textSecondary" sx={{ fontStyle: 'italic', textAlign: 'center', py: 3 }}>
                            {t('hostDetail.noSSHKeysAvailable', 'No SSH keys available. Create SSH keys in the Secrets section first.')}
                        </Typography>
                    ) : (
                        <Box sx={{ height: 350, width: '100%' }}>
                            <DataGrid
                                rows={filteredSSHKeys}
                                columns={sshKeyColumns}
                                checkboxSelection
                                disableRowSelectionOnClick
                                rowSelectionModel={selectedSSHKeys}
                                onRowSelectionModelChange={(newSelection: GridRowSelectionModel) => {
                                    setSelectedSSHKeys(newSelection as string[]);
                                }}
                                initialState={{
                                    pagination: {
                                        paginationModel: { pageSize: 10, page: 0 },
                                    },
                                }}
                                pageSizeOptions={[10, 25, 50]}
                                sx={{
                                    '& .MuiDataGrid-root': {
                                        border: 'none',
                                    },
                                }}
                            />
                        </Box>
                    )}
                </DialogContent>
                <DialogActions>
                    <Button onClick={handleSSHKeyDialogClose}>
                        {t('common.cancel', 'Cancel')}
                    </Button>
                    <Button
                        variant="contained"
                        onClick={handleDeploySSHKeys}
                        disabled={selectedSSHKeys.length === 0}
                    >
                        {t('common.add', 'Add')}
                    </Button>
                </DialogActions>
            </Dialog>

            {/* Certificate Selection Dialog */}
            <Dialog
                open={addCertificateDialogOpen}
                onClose={handleCertificateDialogClose}
                maxWidth="md"
                fullWidth
            >
                <DialogTitle>
                    {t('hostDetail.addCertificateToHost', 'Add Certificate to {host}').replace('{host}', host?.fqdn || '')}
                </DialogTitle>
                <DialogContent sx={{ minHeight: '500px' }}>
                    <Typography variant="body2" color="textSecondary" sx={{ mb: 2 }}>
                        {t('hostDetail.selectCertificatesToAdd', 'Select the certificates you want to add to this host:')}
                    </Typography>

                    {/* Search Field */}
                    <Box sx={{ mb: 2, display: 'flex', gap: 1 }}>
                        <TextField
                            fullWidth
                            placeholder={t('hostDetail.searchCertificates', 'Search certificates by name or filename...')}
                            value={certificateDialogSearchTerm}
                            onChange={(e) => setCertificateDialogSearchTerm(e.target.value)}
                            size="small"
                            InputProps={{
                                startAdornment: (
                                    <InputAdornment position="start">
                                        <SearchIcon />
                                    </InputAdornment>
                                ),
                            }}
                            onKeyPress={(e) => {
                                if (e.key === 'Enter') {
                                    handleCertificateSearch();
                                }
                            }}
                        />
                        <Button
                            variant="outlined"
                            onClick={handleCertificateSearch}
                            sx={{ minWidth: 'auto', px: 3 }}
                        >
                            {t('common.search', 'Search')}
                        </Button>
                    </Box>

                    {availableCertificates.length === 0 ? (
                        <Typography variant="body2" color="textSecondary" sx={{ fontStyle: 'italic', textAlign: 'center', py: 3 }}>
                            {isCertificateSearching ?
                                t('hostDetail.loadingCertificates', 'Loading certificates...') :
                                t('hostDetail.noCertificatesFound', 'No certificates found in vault')
                            }
                        </Typography>
                    ) : (
                        <>
                            <Typography variant="body2" sx={{ mb: 1 }}>
                                {t('hostDetail.certificateCount', 'Found {count} certificates').replace('{count}', String(filteredCertificates.length))}
                            </Typography>
                            <DataGrid
                                rows={filteredCertificates}
                                columns={vaultCertificateColumns}
                                initialState={{
                                    pagination: {
                                        paginationModel: { pageSize: 10, page: 0 },
                                    },
                                }}
                                pageSizeOptions={[5, 10, 25]}
                                checkboxSelection
                                disableRowSelectionOnClick
                                autoHeight
                                sx={{
                                    maxHeight: 400,
                                    '& .MuiDataGrid-row': {
                                        '&:hover': {
                                            backgroundColor: 'action.hover',
                                        },
                                    },
                                }}
                                onRowSelectionModelChange={(newSelectionModel) => {
                                    setSelectedCertificates(newSelectionModel as string[]);
                                }}
                                rowSelectionModel={selectedCertificates}
                            />
                        </>
                    )}
                </DialogContent>
                <DialogActions>
                    <Button onClick={handleCertificateDialogClose} color="primary">
                        {t('common.cancel', 'Cancel')}
                    </Button>
                    <Button
                        variant="contained"
                        onClick={handleDeployCertificates}
                        disabled={selectedCertificates.length === 0}
                    >
                        {t('common.add', 'Add')}
                    </Button>
                </DialogActions>
            </Dialog>

            <GraylogAttachmentModal
                open={graylogAttachModalOpen}
                onClose={handleGraylogAttachModalClose}
                hostId={hostId || ''}
                hostPlatform={host?.os || ''}
            />
        </Box>
    );
};

export default HostDetail;