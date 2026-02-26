/* global Event */
import { useNavigate, useParams } from "react-router-dom";
import React, { useEffect, useState, useCallback, useMemo, useRef } from 'react';
import AntivirusStatusCard from '../Components/AntivirusStatusCard';
import CommercialAntivirusStatusCard from '../Components/CommercialAntivirusStatusCard';
import FirewallStatusCard from '../Components/FirewallStatusCard';
import HypervisorStatusCard from '../Components/HypervisorStatusCard';
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
    Alert,
    Dialog,
    DialogTitle,
    DialogContent,
    DialogContentText,
    DialogActions,
    Table,
    TableBody,
    TableRow,
    TableCell,
    ToggleButton,
    ToggleButtonGroup,
    Snackbar,
    TextField,
    List,
    ListItem,
    ListItemText,
    Divider,
    TableContainer,
    TableHead,
    InputAdornment,
    Pagination,
    FormHelperText
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
import WarningIcon from '@mui/icons-material/Warning';
import AccountTreeIcon from '@mui/icons-material/AccountTree';
import { DataGrid, GridColDef, GridRowSelectionModel } from '@mui/x-data-grid';
import SearchIcon from '@mui/icons-material/Search';
import { useTranslation } from 'react-i18next';
import { useColumnVisibility } from '../hooks/useColumnVisibility';
import { useTablePageSize } from '../hooks/useTablePageSize';
import ColumnVisibilityButton from '../Components/ColumnVisibilityButton';
import axios from 'axios';
import axiosInstance from '../Services/api';
import { distributionService } from '../Services/childHostDistributions';
import { hasPermission, hasPermissionSync, SecurityRoles } from '../Services/permissions';

import { SysManageHost, StorageDevice as StorageDeviceType, NetworkInterface as NetworkInterfaceType, UserAccount, UserGroup, SoftwarePackage, PaginationInfo, DiagnosticReport, DiagnosticDetailResponse, UbuntuProInfo, RebootPreCheckResponse, RebootOrchestrationStatus, doGetHostByID, doGetHostStorage, doGetHostNetwork, doGetHostUsers, doGetHostGroups, doGetHostSoftware, doGetHostDiagnostics, doRequestHostDiagnostics, doGetDiagnosticDetail, doDeleteDiagnostic, doRebootHost, doShutdownHost, doRequestPackages, doGetHostUbuntuPro, doAttachUbuntuPro, doDetachUbuntuPro, doEnableUbuntuProService, doDisableUbuntuProService, doRefreshUserAccessData, doRefreshSoftwareData, doRefreshUpdatesCheck, doRequestSystemInfo, doChangeHostname, doRebootPreCheck, doOrchestratedReboot, getRebootOrchestrationStatus } from '../Services/hosts';
import { SysManageUser, doGetMe } from '../Services/users';
import { SecretResponse } from '../Services/secrets';
import { parseUTCTimestamp, formatUTCTimestamp, formatUTCDate } from '../utils/dateUtils';
import { doCheckOpenTelemetryEligibility, doDeployOpenTelemetry, doGetOpenTelemetryStatus, doStartOpenTelemetry, doStopOpenTelemetry, doRestartOpenTelemetry, doConnectOpenTelemetryToGrafana, doDisconnectOpenTelemetryFromGrafana, doRemoveOpenTelemetry } from '../Services/opentelemetry';
import { doCheckGraylogHealth, doGetGraylogAttachment } from '../Services/graylog';
import ThirdPartyRepositories from './ThirdPartyRepositories';
import AddHostAccountModal from '../Components/AddHostAccountModal';
import AddHostGroupModal from '../Components/AddHostGroupModal';
import { getLicenseInfo } from '../Services/license';
import { usePlugins } from '../plugins';

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

// Child host interface
interface ChildHost {
    id: string;
    parent_host_id: string;
    child_host_id: string | null;
    child_name: string;
    child_type: string;
    distribution: string | null;
    distribution_version: string | null;
    hostname: string | null;
    status: string;
    installation_step: string | null;
    error_message: string | null;
    created_at: string | null;
    installed_at: string | null;
}

// Large page component that coordinates host details, hardware info, software, virtualization, and multiple interactive features
const HostDetail = () => { // NOSONAR
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
    const [licenseModules, setLicenseModules] = useState<string[]>([]);

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

    // Check if host supports child hosts (virtualization)
    const supportsChildHosts = useCallback(() => {
        if (!host?.platform) return false;
        // Child hosts (VMs, containers, WSL instances) cannot have their own child hosts
        if (host.parent_host_id) return false;
        const platform = host.platform || '';
        // Windows hosts support WSL, Linux hosts support LXD/KVM, OpenBSD hosts support VMM, FreeBSD hosts support bhyve
        return platform.includes('Windows') || platform.includes('Linux') || platform.includes('OpenBSD') || platform.includes('FreeBSD');
    }, [host]);

    // Check if host is running Ubuntu (for Ubuntu Pro feature)
    const isUbuntu = useCallback(() => {
        if (!host?.platform && !host?.platform_release) return false;
        const platform = (host.platform || '').toLowerCase();
        const platformRelease = (host.platform_release || '').toLowerCase();
        return platform.includes('ubuntu') || platformRelease.includes('ubuntu');
    }, [host]);

    // Store the initial URL hash for tab resolution after tabDefinitions is ready
    const initialTabHash = useRef(globalThis.location.hash.slice(1));

    const [currentTab, setCurrentTab] = useState<number>(0);
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
    const childHostsRefreshInterval = useRef<ReturnType<typeof setInterval> | null>(null);
    const childHostsLastAgentRefresh = useRef<number>(0);

    // Child hosts state
    const [childHosts, setChildHosts] = useState<ChildHost[]>([]);
    const [childHostsLoading, setChildHostsLoading] = useState<boolean>(false);
    const [childHostsRefreshRequested, setChildHostsRefreshRequested] = useState<boolean>(false);

    // Virtualization status state
    interface VirtualizationStatus {
        supported_types: string[];
        capabilities: {
            wsl?: {
                available: boolean;
                enabled: boolean;
                needs_enable: boolean;
                needs_bios_virtualization?: boolean;
                version?: string;
                default_version?: number;
            };
            lxd?: {
                available: boolean;
                installed: boolean;
                initialized: boolean;
                user_in_group: boolean;
                needs_install: boolean;
                needs_init: boolean;
                snap_available: boolean;
            };
            vmm?: {
                available: boolean;
                enabled: boolean;
                running: boolean;
                initialized: boolean;
                kernel_supported: boolean;
                needs_enable: boolean;
            };
            kvm?: {
                available: boolean;
                installed: boolean;
                enabled: boolean;
                running: boolean;
                initialized: boolean;
                needs_install: boolean;
                needs_enable: boolean;
            };
            bhyve?: {
                available: boolean;
                enabled: boolean;
                running: boolean;
                initialized: boolean;
                kernel_supported: boolean;
                needs_enable: boolean;
            };
            [key: string]: unknown;
        };
        reboot_required: boolean;
    }
    const [virtualizationStatus, setVirtualizationStatus] = useState<VirtualizationStatus | null>(null);
    const [virtualizationLoading, setVirtualizationLoading] = useState<boolean>(false);
    const [enableWslLoading, setEnableWslLoading] = useState<boolean>(false);
    const [initializeLxdLoading, setInitializeLxdLoading] = useState<boolean>(false);
    const [initializeVmmLoading, setInitializeVmmLoading] = useState<boolean>(false);
    const [initializeKvmLoading, setInitializeKvmLoading] = useState<boolean>(false);
    const [initializeBhyveLoading, setInitializeBhyveLoading] = useState<boolean>(false);
    const [disableBhyveLoading, setDisableBhyveLoading] = useState<boolean>(false);
    const [kvmModulesLoading, setKvmModulesLoading] = useState<boolean>(false);

    // Create child host modal state
    const explicitChildTypeRef = useRef<string | null>(null);
    const [createChildHostOpen, setCreateChildHostOpen] = useState<boolean>(false);
    const [createChildHostLoading, setCreateChildHostLoading] = useState<boolean>(false);
    const [childHostFormData, setChildHostFormData] = useState({
        childType: 'wsl',  // 'wsl' for Windows, 'lxd' for Linux, 'vmm' for OpenBSD
        distribution: '',
        containerName: '',  // For LXD containers
        vmName: '',  // For VMM virtual machines
        hostname: '',
        username: '',
        password: '',
        confirmPassword: '',
        rootPassword: '',  // For VMM: separate root password
        confirmRootPassword: '',  // For VMM: confirm root password
        autoApprove: false,  // Automatically approve when the child host connects
    });
    const [childHostCreationProgress, setChildHostCreationProgress] = useState<string>('');
    const [childHostFormValidated, setChildHostFormValidated] = useState<boolean>(false);
    const [availableDistributions, setAvailableDistributions] = useState<Array<{
        id: string;
        display_name: string;
        install_identifier: string;
        child_type: string;
    }>>([]);

    // Compute FQDN from hostname - appends server domain if not already an FQDN
    const getServerDomain = useCallback(() => {
        const hostname = globalThis.location.hostname;
        // Extract domain from hostname (e.g., "t14.theeverlys.com" -> "theeverlys.com")
        const parts = hostname.split('.');
        if (parts.length >= 2) {
            return parts.slice(1).join('.');
        }
        return hostname;
    }, []);

    const computedFqdn = useMemo(() => {
        const hostname = childHostFormData.hostname.trim().toLowerCase();
        if (!hostname) return '';
        // If already contains a dot, it's already an FQDN
        if (hostname.includes('.')) {
            return hostname;
        }
        // Append the server's domain
        return `${hostname}.${getServerDomain()}`;
    }, [childHostFormData.hostname, getServerDomain]);

    // Fetch distributions when create child host dialog opens
    const fetchDistributions = useCallback(async (childType: string) => {
        try {
            const distributions = await distributionService.getAll(childType);
            const activeDistributions = distributions
                .filter(d => d.is_active)
                .map(d => ({
                    id: d.id,
                    display_name: d.display_name,
                    install_identifier: d.install_identifier || '',
                    child_type: d.child_type,
                }));
            setAvailableDistributions(activeDistributions);
        } catch (error) {
            console.error('Error fetching distributions:', error);
            setAvailableDistributions([]);
        }
    }, []);

    // Set child type based on platform and fetch distributions when dialog opens
    useEffect(() => {
        if (createChildHostOpen && host) {
            // If dialog was opened with an explicit type (e.g. from HypervisorStatusCard),
            // respect that choice instead of auto-detecting from platform/virtualization
            if (explicitChildTypeRef.current) {
                explicitChildTypeRef.current = null;
                return;
            }
            const platform = host.platform || '';
            const isLinux = platform.toLowerCase().includes('linux');
            const isOpenBSD = platform.includes('OpenBSD');
            const isFreeBSD = platform.includes('FreeBSD');
            // Determine child type based on platform and available virtualization:
            // - FreeBSD -> bhyve
            // - OpenBSD -> vmm
            // - Linux -> kvm (if initialized) or lxd (fallback)
            // - Windows -> wsl
            let childType = 'wsl';
            if (isFreeBSD) {
                childType = 'bhyve';
            } else if (isOpenBSD) {
                childType = 'vmm';
            } else if (isLinux) {
                // Prefer KVM if initialized, otherwise use LXD
                if (virtualizationStatus?.capabilities?.kvm?.initialized) {
                    childType = 'kvm';
                } else {
                    childType = 'lxd';
                }
            }
            setChildHostFormData(prev => ({
                ...prev,
                childType,
                distribution: '',  // Reset distribution when type changes
            }));
            fetchDistributions(childType);
        }
    }, [createChildHostOpen, host, fetchDistributions, virtualizationStatus]);

    // Child host control state (start/stop/restart/delete)
    const [childHostOperationLoading, setChildHostOperationLoading] = useState<Record<string, string | null>>({});
    const [deleteChildHostConfirmOpen, setDeleteChildHostConfirmOpen] = useState<boolean>(false);
    const [childHostToDelete, setChildHostToDelete] = useState<ChildHost | null>(null);

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
    const [rebootPreCheckData, setRebootPreCheckData] = useState<RebootPreCheckResponse | null>(null);
    const [rebootPreCheckLoading, setRebootPreCheckLoading] = useState<boolean>(false);
    const [rebootOrchestrationId, setRebootOrchestrationId] = useState<string | null>(null);
    const [rebootOrchestrationStatus, setRebootOrchestrationStatus] = useState<RebootOrchestrationStatus | null>(null);
    const [snackbarSeverity, setSnackbarSeverity] = useState<'success' | 'error' | 'warning'>('success');
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
    const [canEditHostname, setCanEditHostname] = useState<boolean>(false);
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

    // Host account management states
    const [canAddHostAccount, setCanAddHostAccount] = useState<boolean>(false);
    const [canAddHostGroup, setCanAddHostGroup] = useState<boolean>(false);
    const [canDeleteHostAccount, setCanDeleteHostAccount] = useState<boolean>(false);
    const [canDeleteHostGroup, setCanDeleteHostGroup] = useState<boolean>(false);
    const [addUserModalOpen, setAddUserModalOpen] = useState<boolean>(false);
    const [addGroupModalOpen, setAddGroupModalOpen] = useState<boolean>(false);
    const [deleteUserConfirmOpen, setDeleteUserConfirmOpen] = useState<boolean>(false);
    const [deleteGroupConfirmOpen, setDeleteGroupConfirmOpen] = useState<boolean>(false);
    const [userToDelete, setUserToDelete] = useState<UserAccount | null>(null);
    const [groupToDelete, setGroupToDelete] = useState<UserGroup | null>(null);
    const [deletingUser, setDeletingUser] = useState<boolean>(false);
    const [deletingGroup, setDeletingGroup] = useState<boolean>(false);
    const [deleteDefaultGroup, setDeleteDefaultGroup] = useState<boolean>(true);

    // OpenTelemetry deployment states
    const [canDeployOpenTelemetry, setCanDeployOpenTelemetry] = useState<boolean>(false);  // User has permission to see button
    const [openTelemetryEligible, setOpenTelemetryEligible] = useState<boolean>(false);  // Deployment is actually allowed
    const [openTelemetryDeploying, setOpenTelemetryDeploying] = useState<boolean>(false);

    // Graylog attachment states
    const [canAttachGraylog, setCanAttachGraylog] = useState<boolean>(false);  // Graylog integration enabled and healthy
    const [graylogEligible, setGraylogEligible] = useState<boolean>(false);  // Agent is privileged
    const [graylogAttachModalOpen, setGraylogAttachModalOpen] = useState<boolean>(false);

    // Virtualization enablement permission states
    const [canEnableWsl, setCanEnableWsl] = useState<boolean>(false);
    const [canEnableLxd, setCanEnableLxd] = useState<boolean>(false);
    const [canEnableKvm, setCanEnableKvm] = useState<boolean>(false);
    const [canEnableVmm, setCanEnableVmm] = useState<boolean>(false);
    const [canEnableBhyve, setCanEnableBhyve] = useState<boolean>(false);

    // Hostname editing state
    const [hostnameEditOpen, setHostnameEditOpen] = useState<boolean>(false);
    const [newHostname, setNewHostname] = useState<string>('');
    const [hostnameEditLoading, setHostnameEditLoading] = useState<boolean>(false);

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
        installed_version?: string;
        error_message?: string;
        installation_log?: string;
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

    // Check Pro+ license modules for plugin tab filtering
    useEffect(() => {
        const checkLicenseModules = async () => {
            try {
                const licenseInfo = await getLicenseInfo();
                setLicenseModules(licenseInfo.modules || []);
            } catch {
                // License check unavailable — proceed without Pro+ features
                setLicenseModules([]);
            }
        };
        checkLicenseModules();
    }, []);

    // Ensure current page size is always in options to avoid MUI warning
    const safePageSizeOptions = useMemo(() => {
        const currentPageSize = certificatePaginationModel.pageSize;
        if (!pageSizeOptions.includes(currentPageSize)) {
            const combinedOptions = [...pageSizeOptions, currentPageSize];
            combinedOptions.sort((a, b) => a - b);
            return combinedOptions;
        }
        return pageSizeOptions;
    }, [pageSizeOptions, certificatePaginationModel.pageSize]);

    // Plugin system: get registered host detail tabs
    const { hostDetailTabs: pluginTabs } = usePlugins();

    // Filter plugin tabs based on required license modules
    const visiblePluginTabs = useMemo(() => {
        return pluginTabs.filter(pt => {
            if (pt.moduleRequired) {
                return licenseModules.includes(pt.moduleRequired);
            }
            return true;
        });
    }, [pluginTabs, licenseModules]);

    // Build ordered tab definitions array
    const tabDefinitions = useMemo(() => {
        const tabs: Array<{ id: string; icon: React.ReactElement; label: string }> = [
            { id: 'info', icon: <InfoIcon />, label: t('hostDetail.infoTab', 'Info') },
            ...visiblePluginTabs.filter(p => p.position === 'after-info').map(pt => ({ id: pt.id, icon: pt.icon, label: t(pt.labelKey) })),
            { id: 'hardware', icon: <MemoryIcon />, label: t('hostDetail.hardwareTab', 'Hardware') },
            { id: 'software', icon: <AppsIcon />, label: t('hostDetail.softwareTab', 'Software') },
            { id: 'software-changes', icon: <HistoryIcon />, label: t('hostDetail.softwareChangesTab', 'Software Changes') },
            ...(supportsThirdPartyRepos() ? [{ id: 'third-party-repos', icon: <SourceIcon />, label: t('hostDetail.thirdPartyReposTab', 'Third-Party Repositories') }] : []),
            { id: 'access', icon: <SecurityIcon />, label: t('hostDetail.accessTab', 'Access') },
            { id: 'security', icon: <ShieldIcon />, label: t('hostDetail.securityTab', 'Security') },
            ...visiblePluginTabs.filter(p => p.position === 'after-security').map(pt => ({ id: pt.id, icon: pt.icon, label: t(pt.labelKey) })),
            { id: 'certificates', icon: <CertificateIcon />, label: t('hostDetail.certificatesTab', 'Certificates') },
            { id: 'server-roles', icon: <AssignmentIcon />, label: t('hostDetail.serverRolesTab', 'Server Roles') },
            ...visiblePluginTabs.filter(p => p.position === 'before-diagnostics').map(pt => ({ id: pt.id, icon: pt.icon, label: t(pt.labelKey) })),
            ...(supportsChildHosts() ? [{ id: 'child-hosts', icon: <ComputerIcon />, label: t('hostDetail.childHostsTab', 'Child Hosts') }] : []),
            ...((isUbuntu() && ubuntuProInfo?.available) ? [{ id: 'ubuntu-pro', icon: <VerifiedUserIcon />, label: t('hostDetail.ubuntuProTab', 'Ubuntu Pro') }] : []),
            { id: 'diagnostics', icon: <MedicalServicesIcon />, label: t('hostDetail.diagnosticsTab', 'Diagnostics') },
        ];

        return tabs;
    }, [visiblePluginTabs, supportsThirdPartyRepos, supportsChildHosts, isUbuntu, ubuntuProInfo, t]);

    // Get tab ID for current numeric index
    const currentTabId = tabDefinitions[currentTab]?.id || 'info';

    // Tab names for URL hash - derived from tabDefinitions
    const getTabNames = useCallback(() => {
        return tabDefinitions.map(td => td.id);
    }, [tabDefinitions]);

    // Resolve initial tab from URL hash once tabDefinitions is ready
    useEffect(() => {
        if (initialTabHash.current) {
            const hash = initialTabHash.current;
            initialTabHash.current = ''; // Only resolve once
            const idx = tabDefinitions.findIndex(td => td.id === hash);
            if (idx > 0) {
                setCurrentTab(idx);
            }
        }
    }, [tabDefinitions]);

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

    // Child hosts functions
    const fetchChildHosts = useCallback(async (showLoading: boolean = true) => {
        if (!hostId) return;
        try {
            if (showLoading) {
                setChildHostsLoading(true);
            }
            const response = await axiosInstance.get(`/api/host/${hostId}/children`);
            if (response.status === 200) {
                setChildHosts(response.data || []);
            }
        } catch (error) {
            console.error('Error fetching child hosts:', error);
            // Don't fail the whole page load for child host errors
            setChildHosts([]);
        } finally {
            if (showLoading) {
                setChildHostsLoading(false);
            }
        }
    }, [hostId]);

    // Fetch virtualization status
    const fetchVirtualizationStatus = useCallback(async () => {
        if (!hostId) return;
        try {
            setVirtualizationLoading(true);
            const response = await axiosInstance.get(`/api/host/${hostId}/virtualization/status`);
            if (response.status === 200) {
                setVirtualizationStatus(response.data);
            }
        } catch (error) {
            console.error('Error fetching virtualization status:', error);
            // Don't fail the whole page load for virtualization errors
            setVirtualizationStatus(null);
        } finally {
            setVirtualizationLoading(false);
        }
    }, [hostId]);

    const requestChildHostsRefresh = useCallback(async (showSnackbar: boolean = true) => {
        if (!hostId) return;
        try {
            setChildHostsRefreshRequested(true);
            // Request the agent to list child hosts with fresh status and refresh virtualization status
            const [childHostsResponse] = await Promise.all([
                axiosInstance.post(`/api/host/${hostId}/children/refresh`),
                // Also request virtualization status refresh
                axiosInstance.get(`/api/host/${hostId}/virtualization`).catch(err => {
                    console.log('Virtualization check request failed (optional):', err);
                    return null;
                })
            ]);
            if (childHostsResponse.status === 200) {
                if (showSnackbar) {
                    setSnackbarMessage(t('hostDetail.childHostsRefreshRequested', 'Child hosts refresh requested'));
                    setSnackbarSeverity('success');
                    setSnackbarOpen(true);
                }
                // Refetch child hosts and virtualization status after a short delay to allow collection to complete
                setTimeout(() => {
                    fetchChildHosts(false);
                    fetchVirtualizationStatus();
                    setChildHostsRefreshRequested(false);
                }, 3000);
            }
        } catch (error) {
            console.error('Error requesting child hosts refresh:', error);
            if (showSnackbar) {
                setSnackbarMessage(t('hostDetail.childHostsRefreshError', 'Error requesting child hosts refresh'));
                setSnackbarSeverity('error');
                setSnackbarOpen(true);
            }
            setChildHostsRefreshRequested(false);
        }
    }, [hostId, fetchChildHosts, fetchVirtualizationStatus, t]);

    // Child host control functions (start/stop/restart/delete)
    const handleChildHostStart = useCallback(async (child: ChildHost) => {
        if (!hostId) return;
        try {
            setChildHostOperationLoading(prev => ({ ...prev, [child.id]: 'start' }));
            await axiosInstance.post(`/api/host/${hostId}/children/${child.id}/start`);
            setSnackbarMessage(t('hostDetail.childHostStartRequested', 'Start requested for {{name}}', { name: child.child_name }));
            setSnackbarSeverity('success');
            setSnackbarOpen(true);
            // Refresh after a short delay
            setTimeout(() => {
                fetchChildHosts(false);
            }, 3000);
        } catch (error) {
            console.error('Error starting child host:', error);
            setSnackbarMessage(t('hostDetail.childHostStartError', 'Error starting child host'));
            setSnackbarSeverity('error');
            setSnackbarOpen(true);
        } finally {
            setChildHostOperationLoading(prev => ({ ...prev, [child.id]: null }));
        }
    }, [hostId, fetchChildHosts, t]);

    const handleChildHostStop = useCallback(async (child: ChildHost) => {
        if (!hostId) return;
        try {
            setChildHostOperationLoading(prev => ({ ...prev, [child.id]: 'stop' }));
            await axiosInstance.post(`/api/host/${hostId}/children/${child.id}/stop`);
            setSnackbarMessage(t('hostDetail.childHostStopRequested', 'Stop requested for {{name}}', { name: child.child_name }));
            setSnackbarSeverity('success');
            setSnackbarOpen(true);
            // Refresh after a short delay
            setTimeout(() => {
                fetchChildHosts(false);
            }, 3000);
        } catch (error) {
            console.error('Error stopping child host:', error);
            setSnackbarMessage(t('hostDetail.childHostStopError', 'Error stopping child host'));
            setSnackbarSeverity('error');
            setSnackbarOpen(true);
        } finally {
            setChildHostOperationLoading(prev => ({ ...prev, [child.id]: null }));
        }
    }, [hostId, fetchChildHosts, t]);

    const handleChildHostRestart = useCallback(async (child: ChildHost) => {
        if (!hostId) return;
        try {
            setChildHostOperationLoading(prev => ({ ...prev, [child.id]: 'restart' }));
            await axiosInstance.post(`/api/host/${hostId}/children/${child.id}/restart`);
            setSnackbarMessage(t('hostDetail.childHostRestartRequested', 'Restart requested for {{name}}', { name: child.child_name }));
            setSnackbarSeverity('success');
            setSnackbarOpen(true);
            // Refresh after a short delay
            setTimeout(() => {
                fetchChildHosts(false);
            }, 5000);
        } catch (error) {
            console.error('Error restarting child host:', error);
            setSnackbarMessage(t('hostDetail.childHostRestartError', 'Error restarting child host'));
            setSnackbarSeverity('error');
            setSnackbarOpen(true);
        } finally {
            setChildHostOperationLoading(prev => ({ ...prev, [child.id]: null }));
        }
    }, [hostId, fetchChildHosts, t]);

    const handleChildHostDeleteConfirm = useCallback((child: ChildHost) => {
        setChildHostToDelete(child);
        setDeleteChildHostConfirmOpen(true);
    }, []);

    const handleChildHostDeleteCancel = useCallback(() => {
        setChildHostToDelete(null);
        setDeleteChildHostConfirmOpen(false);
    }, []);

    const handleChildHostDelete = useCallback(async () => {
        if (!hostId || !childHostToDelete) return;
        try {
            setChildHostOperationLoading(prev => ({ ...prev, [childHostToDelete.id]: 'delete' }));
            setDeleteChildHostConfirmOpen(false);
            await axiosInstance.delete(`/api/host/${hostId}/children/${childHostToDelete.id}`);
            setSnackbarMessage(t('hostDetail.childHostDeleteRequested', 'Delete requested for {{name}}', { name: childHostToDelete.child_name }));
            setSnackbarSeverity('success');
            setSnackbarOpen(true);
            // Refresh after a short delay
            setTimeout(() => {
                fetchChildHosts(false);
            }, 3000);
        } catch (error) {
            // Check if this is a 404 (child host already removed)
            if (axios.isAxiosError(error) && error.response?.status === 404) {
                setSnackbarMessage(t('hostDetail.childHostNotFound', 'Child host not found - it may have already been deleted'));
                setSnackbarSeverity('warning');
                setSnackbarOpen(true);
                // Refresh the list to remove the stale entry
                setTimeout(() => {
                    fetchChildHosts(false);
                }, 1000);
            } else {
                console.error('Error deleting child host:', error);
                let errorMessage = t('hostDetail.childHostDeleteError', 'Error deleting child host');
                if (axios.isAxiosError(error) && error.response?.data?.detail) {
                    errorMessage = error.response.data.detail;
                }
                setSnackbarMessage(errorMessage);
                setSnackbarSeverity('error');
                setSnackbarOpen(true);
            }
        } finally {
            setChildHostOperationLoading(prev => ({ ...prev, [childHostToDelete.id]: null }));
            setChildHostToDelete(null);
        }
    }, [hostId, childHostToDelete, fetchChildHosts, t]);

    // Enable WSL on Windows host
    const handleEnableWsl = useCallback(async () => {
        if (!hostId) return;
        try {
            setEnableWslLoading(true);
            const response = await axiosInstance.post(`/api/host/${hostId}/virtualization/enable-wsl`);
            if (response.status === 200) {
                const result = response.data;
                if (result.reboot_required) {
                    setSnackbarMessage(t('hostDetail.wslEnabledRebootRequired', 'WSL has been enabled. A reboot is required to complete the installation.'));
                } else {
                    setSnackbarMessage(t('hostDetail.wslEnabledSuccess', 'WSL has been enabled successfully.'));
                }
                setSnackbarSeverity('success');
                setSnackbarOpen(true);
                // Refresh virtualization status
                setTimeout(() => {
                    fetchVirtualizationStatus();
                }, 3000);
            }
        } catch (error) {
            console.error('Error enabling WSL:', error);
            setSnackbarMessage(t('hostDetail.wslEnableFailed', 'Failed to enable WSL'));
            setSnackbarSeverity('error');
            setSnackbarOpen(true);
        } finally {
            setEnableWslLoading(false);
        }
    }, [hostId, fetchVirtualizationStatus, t]);

    // Initialize LXD on Linux host
    const handleInitializeLxd = useCallback(async () => {
        if (!hostId) return;
        try {
            setInitializeLxdLoading(true);
            const response = await axiosInstance.post(`/api/host/${hostId}/virtualization/initialize-lxd`);
            if (response.status === 200) {
                setSnackbarMessage(t('hostDetail.lxdInitializedSuccess', 'LXD initialization requested. The agent will install and configure LXD.'));
                setSnackbarSeverity('success');
                setSnackbarOpen(true);
                // Refresh virtualization status after a delay
                setTimeout(() => {
                    fetchVirtualizationStatus();
                }, 5000);
            }
        } catch (error) {
            console.error('Error initializing LXD:', error);
            setSnackbarMessage(t('hostDetail.lxdInitializeFailed', 'Failed to initialize LXD'));
            setSnackbarSeverity('error');
            setSnackbarOpen(true);
        } finally {
            setInitializeLxdLoading(false);
        }
    }, [hostId, fetchVirtualizationStatus, t]);

    // Initialize VMM on OpenBSD host
    const handleInitializeVmm = useCallback(async () => {
        if (!hostId) return;
        try {
            setInitializeVmmLoading(true);
            const response = await axiosInstance.post(`/api/host/${hostId}/virtualization/initialize-vmm`);
            if (response.status === 200) {
                setSnackbarMessage(t('hostDetail.vmmInitializedSuccess', 'VMM initialization requested. The agent will enable and start the vmd daemon.'));
                setSnackbarSeverity('success');
                setSnackbarOpen(true);
                // Refresh virtualization status after a delay
                setTimeout(() => {
                    fetchVirtualizationStatus();
                }, 5000);
            }
        } catch (error) {
            console.error('Error initializing VMM:', error);
            setSnackbarMessage(t('hostDetail.vmmInitializeFailed', 'Failed to initialize VMM'));
            setSnackbarSeverity('error');
            setSnackbarOpen(true);
        } finally {
            setInitializeVmmLoading(false);
        }
    }, [hostId, fetchVirtualizationStatus, t]);

    // Initialize KVM on Linux host
    const handleInitializeKvm = useCallback(async () => {
        if (!hostId) return;
        try {
            setInitializeKvmLoading(true);
            const response = await axiosInstance.post(`/api/host/${hostId}/virtualization/initialize-kvm`);
            if (response.status === 200) {
                setSnackbarMessage(t('hostDetail.kvmInitializedSuccess', 'KVM initialization requested. The agent will install and configure libvirt.'));
                setSnackbarSeverity('success');
                setSnackbarOpen(true);
                // Refresh virtualization status after a delay
                setTimeout(() => {
                    fetchVirtualizationStatus();
                }, 5000);
            }
        } catch (error) {
            console.error('Error initializing KVM:', error);
            setSnackbarMessage(t('hostDetail.kvmInitializeFailed', 'Failed to initialize KVM'));
            setSnackbarSeverity('error');
            setSnackbarOpen(true);
        } finally {
            setInitializeKvmLoading(false);
        }
    }, [hostId, fetchVirtualizationStatus, t]);

    // Initialize bhyve on FreeBSD host
    const handleInitializeBhyve = useCallback(async () => {
        if (!hostId) return;
        try {
            setInitializeBhyveLoading(true);
            const response = await axiosInstance.post(`/api/host/${hostId}/virtualization/initialize-bhyve`);
            if (response.status === 200) {
                setSnackbarMessage(t('hostDetail.bhyveInitializedSuccess', 'bhyve initialization requested. The agent will load vmm.ko and configure the system.'));
                setSnackbarSeverity('success');
                setSnackbarOpen(true);
                // Refresh virtualization status after a delay
                setTimeout(() => {
                    fetchVirtualizationStatus();
                }, 5000);
            }
        } catch (error) {
            console.error('Error initializing bhyve:', error);
            setSnackbarMessage(t('hostDetail.bhyveInitializeFailed', 'Failed to initialize bhyve'));
            setSnackbarSeverity('error');
            setSnackbarOpen(true);
        } finally {
            setInitializeBhyveLoading(false);
        }
    }, [hostId, fetchVirtualizationStatus, t]);

    // Disable bhyve on FreeBSD host
    const handleDisableBhyve = useCallback(async () => {
        if (!hostId) return;
        try {
            setDisableBhyveLoading(true);
            const response = await axiosInstance.post(`/api/host/${hostId}/virtualization/disable-bhyve`);
            if (response.status === 200) {
                setSnackbarMessage(t('hostDetail.bhyveDisabledSuccess', 'bhyve disable requested. The agent will unload vmm.ko and update the configuration.'));
                setSnackbarSeverity('success');
                setSnackbarOpen(true);
                // Refresh virtualization status after a delay
                setTimeout(() => {
                    fetchVirtualizationStatus();
                }, 5000);
            }
        } catch (error) {
            console.error('Error disabling bhyve:', error);
            setSnackbarMessage(t('hostDetail.bhyveDisableFailed', 'Failed to disable bhyve'));
            setSnackbarSeverity('error');
            setSnackbarOpen(true);
        } finally {
            setDisableBhyveLoading(false);
        }
    }, [hostId, fetchVirtualizationStatus, t]);

    // Enable KVM modules via modprobe
    const handleEnableKvmModules = useCallback(async () => {
        if (!hostId) return;
        try {
            setKvmModulesLoading(true);
            const response = await axiosInstance.post(`/api/host/${hostId}/virtualization/enable-kvm-modules`);
            if (response.status === 200) {
                setSnackbarMessage(t('hostDetail.kvmModulesEnableSuccess', 'KVM modules enable requested. The agent will load the kernel modules.'));
                setSnackbarSeverity('success');
                setSnackbarOpen(true);
                // Refresh virtualization status after a delay (needs time for queue round-trip)
                setTimeout(() => {
                    fetchVirtualizationStatus();
                }, 6000);
            }
        } catch (error) {
            console.error('Error enabling KVM modules:', error);
            setSnackbarMessage(t('hostDetail.kvmModulesEnableFailed', 'Failed to enable KVM modules'));
            setSnackbarSeverity('error');
            setSnackbarOpen(true);
        } finally {
            setKvmModulesLoading(false);
        }
    }, [hostId, fetchVirtualizationStatus, t]);

    // Disable KVM modules via modprobe -r
    const handleDisableKvmModules = useCallback(async () => {
        if (!hostId) return;
        try {
            setKvmModulesLoading(true);
            const response = await axiosInstance.post(`/api/host/${hostId}/virtualization/disable-kvm-modules`);
            if (response.status === 200) {
                setSnackbarMessage(t('hostDetail.kvmModulesDisableSuccess', 'KVM modules disable requested. The agent will unload the kernel modules.'));
                setSnackbarSeverity('success');
                setSnackbarOpen(true);
                // Refresh virtualization status after a delay (needs time for queue round-trip)
                setTimeout(() => {
                    fetchVirtualizationStatus();
                }, 6000);
            }
        } catch (error) {
            console.error('Error disabling KVM modules:', error);
            setSnackbarMessage(t('hostDetail.kvmModulesDisableFailed', 'Failed to disable KVM modules. Ensure no VMs are running.'));
            setSnackbarSeverity('error');
            setSnackbarOpen(true);
        } finally {
            setKvmModulesLoading(false);
        }
    }, [hostId, fetchVirtualizationStatus, t]);

    // Open create dialog with a specific child type (called from HypervisorStatusCard)
    const openCreateDialogWithType = useCallback((childType: string) => {
        explicitChildTypeRef.current = childType;
        setChildHostFormData(prev => ({
            ...prev,
            childType,
            distribution: '',  // Reset distribution when type changes
            containerName: '',
            vmName: '',
            hostname: '',
            username: '',
            password: '',
            confirmPassword: '',
            rootPassword: '',
            confirmRootPassword: '',
            autoApprove: false,
        }));
        fetchDistributions(childType);
        setCreateChildHostOpen(true);
    }, [fetchDistributions]);

    // Create child host
    // Complex form validation and conditional request building for multiple child host types (WSL, LXD, VMM, KVM, bhyve)
    const handleCreateChildHost = useCallback(async () => { // NOSONAR
        if (!hostId) return;

        // Mark form as validated to show inline errors
        setChildHostFormValidated(true);

        // Validate form
        if (!childHostFormData.distribution) {
            // Error is shown inline on the field
            return;
        }
        if (!childHostFormData.hostname || !computedFqdn) {
            setSnackbarMessage(t('hostDetail.childHostHostnameRequired', 'Please enter a hostname'));
            setSnackbarSeverity('error');
            setSnackbarOpen(true);
            return;
        }
        if (!childHostFormData.username) {
            setSnackbarMessage(t('hostDetail.childHostUsernameRequired', 'Please enter a username'));
            setSnackbarSeverity('error');
            setSnackbarOpen(true);
            return;
        }
        if (!childHostFormData.password) {
            setSnackbarMessage(t('hostDetail.childHostPasswordRequired', 'Please enter a password'));
            setSnackbarSeverity('error');
            setSnackbarOpen(true);
            return;
        }
        if (childHostFormData.password !== childHostFormData.confirmPassword) {
            setSnackbarMessage(t('hostDetail.childHostPasswordMismatch', 'Passwords do not match'));
            setSnackbarSeverity('error');
            setSnackbarOpen(true);
            return;
        }
        // For VMM, KVM, and bhyve, require VM name
        if (childHostFormData.childType === 'vmm' || childHostFormData.childType === 'kvm' || childHostFormData.childType === 'bhyve') {
            if (!childHostFormData.vmName) {
                setSnackbarMessage(t('hostDetail.childHostVmNameRequired', 'Please enter a VM name'));
                setSnackbarSeverity('error');
                setSnackbarOpen(true);
                return;
            }
        }
        // For VMM specifically, require root password (KVM uses cloud-init with user password)
        if (childHostFormData.childType === 'vmm') {
            if (!childHostFormData.rootPassword) {
                setSnackbarMessage(t('hostDetail.childHostRootPasswordRequired', 'Please enter a root password'));
                setSnackbarSeverity('error');
                setSnackbarOpen(true);
                return;
            }
            if (childHostFormData.rootPassword !== childHostFormData.confirmRootPassword) {
                setSnackbarMessage(t('hostDetail.childHostRootPasswordMismatch', 'Root passwords do not match'));
                setSnackbarSeverity('error');
                setSnackbarOpen(true);
                return;
            }
        }

        try {
            setCreateChildHostLoading(true);
            setChildHostCreationProgress(t('hostDetail.childHostCreationStarting', 'Starting child host creation...'));

            // Build request based on child type
            const requestData: Record<string, string | boolean> = {
                child_type: childHostFormData.childType,
                distribution: childHostFormData.distribution,
                hostname: computedFqdn,  // Always send the computed FQDN
                username: childHostFormData.username,
                password: childHostFormData.password,
                auto_approve: childHostFormData.autoApprove,
            };

            // For LXD, also send container name
            if (childHostFormData.childType === 'lxd' && childHostFormData.containerName) {
                requestData.container_name = childHostFormData.containerName;
            }

            // For VMM, send vm_name, iso_url, and root_password
            if (childHostFormData.childType === 'vmm') {
                requestData.vm_name = childHostFormData.vmName || childHostFormData.hostname;
                // For VMM, the install_identifier contains the ISO URL
                if (childHostFormData.distribution) {
                    requestData.iso_url = childHostFormData.distribution;
                }
                // VMM requires separate root password
                requestData.root_password = childHostFormData.rootPassword;
            }

            // For KVM, send vm_name and cloud_image_url
            if (childHostFormData.childType === 'kvm') {
                requestData.vm_name = childHostFormData.vmName || childHostFormData.hostname;
                // For KVM, the install_identifier contains the cloud image URL
                if (childHostFormData.distribution) {
                    requestData.cloud_image_url = childHostFormData.distribution;
                }
            }

            // For bhyve, send vm_name and cloud_image_url (similar to KVM)
            if (childHostFormData.childType === 'bhyve') {
                requestData.vm_name = childHostFormData.vmName || childHostFormData.hostname;
                // For bhyve, the install_identifier contains the cloud image URL
                if (childHostFormData.distribution) {
                    requestData.cloud_image_url = childHostFormData.distribution;
                }
            }

            const response = await axiosInstance.post(`/api/host/${hostId}/virtualization/create-child`, requestData);

            if (response.status === 200) {
                const result = response.data;
                if (result.success) {
                    setSnackbarMessage(t('hostDetail.childHostCreated', 'Child host created successfully'));
                    setSnackbarSeverity('success');
                    setSnackbarOpen(true);
                    setCreateChildHostOpen(false);
                    // Reset form
                    setChildHostFormValidated(false);
                    setChildHostFormData({
                        childType: childHostFormData.childType,  // Keep the child type
                        distribution: '',
                        containerName: '',
                        vmName: '',
                        hostname: '',
                        username: '',
                        password: '',
                        confirmPassword: '',
                        rootPassword: '',
                        confirmRootPassword: '',
                        autoApprove: false,
                    });
                    // Refresh child hosts list
                    setTimeout(() => {
                        fetchChildHosts();
                    }, 3000);
                } else if (result.reboot_required) {
                    setSnackbarMessage(t('hostDetail.childHostNeedsReboot', 'WSL needs to be enabled. A reboot is required first.'));
                    setSnackbarSeverity('warning');
                    setSnackbarOpen(true);
                } else {
                    setSnackbarMessage(result.error || t('hostDetail.childHostCreationFailed', 'Failed to create child host'));
                    setSnackbarSeverity('error');
                    setSnackbarOpen(true);
                }
            }
        } catch (error: unknown) {
            console.error('Error creating child host:', error);
            // Extract error message from axios error response
            let errorMessage = t('hostDetail.childHostCreationFailed', 'Failed to create child host');
            if (axios.isAxiosError(error) && error.response?.data?.detail) {
                errorMessage = error.response.data.detail;
            }
            setSnackbarMessage(errorMessage);
            setSnackbarSeverity('error');
            setSnackbarOpen(true);
        } finally {
            setCreateChildHostLoading(false);
            setChildHostCreationProgress('');
        }
    }, [hostId, childHostFormData, computedFqdn, fetchChildHosts, t]);

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
    const addRoleToSelection = (roleId: string) => {
        setSelectedRoles(prev => [...prev, roleId]);
    };

    const removeRoleFromSelection = (roleId: string) => {
        setSelectedRoles(prev => prev.filter(id => id !== roleId));
    };

    const selectAllRoles = () => {
        const selectableRoles = roles.filter(role => role.service_name && role.service_name.trim() !== '').map(role => role.id);
        setSelectedRoles(selectableRoles);
    };

    const deselectAllRoles = () => {
        setSelectedRoles([]);
    };

    const handleServiceControl = async (action: 'start' | 'stop' | 'restart') => {
        if (!hostId || selectedRoles.length === 0) return;

        try {
            setServiceControlLoading(true);
            const selectedRoleData = roles.filter(role => selectedRoles.includes(role.id));
            const serviceNames = selectedRoleData.map(role => role.service_name).filter(Boolean);

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
        if (currentTabId === 'server-roles' && host?.active) {
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
        } else if (rolesRefreshInterval.current) {
            // Clear interval when tab is not active or host is not active
            clearInterval(rolesRefreshInterval.current);
            rolesRefreshInterval.current = null;
        }
    }, [currentTabId, host?.active, host?.id, fetchRoles, host]);

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
        if (currentTabId === 'info' && host?.active) {
            fetchOpenTelemetryStatus();
        }
    }, [currentTabId, host?.active, host, fetchOpenTelemetryStatus]);

    // Auto-refresh OpenTelemetry status every 30 seconds when on Info tab
    useEffect(() => {
        if (currentTabId === 'info' && host?.active) {
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
        } else if (openTelemetryRefreshInterval.current) {
            // Clear interval when tab is not active or host is not active
            clearInterval(openTelemetryRefreshInterval.current);
            openTelemetryRefreshInterval.current = null;
        }
    }, [currentTabId, host?.active, host?.id, fetchOpenTelemetryStatus, host]);

    // Fetch Graylog attachment status when Info tab is active
    useEffect(() => {
        if (currentTabId === 'info' && host?.active) {
            fetchGraylogAttachment();
        }
    }, [currentTabId, host?.active, host, fetchGraylogAttachment]);

    // Auto-refresh Graylog status every 30 seconds when on Info tab
    useEffect(() => {
        if (currentTabId === 'info' && host?.active) {
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
        } else if (graylogRefreshInterval.current) {
            // Clear interval when tab is not active or host is not active
            clearInterval(graylogRefreshInterval.current);
            graylogRefreshInterval.current = null;
        }
    }, [currentTabId, host?.active, host?.id, fetchGraylogAttachment, host]);

    // Cleanup intervals on unmount
    useEffect(() => {
        return () => {
            if (openTelemetryRefreshInterval.current) {
                clearInterval(openTelemetryRefreshInterval.current);
            }
            if (graylogRefreshInterval.current) {
                clearInterval(graylogRefreshInterval.current);
            }
            if (childHostsRefreshInterval.current) {
                clearInterval(childHostsRefreshInterval.current);
            }
        };
    }, []);

    // Auto-refresh Child Hosts and Virtualization Status every 15 seconds when on Child Hosts tab
    // Also trigger an agent refresh when first opening the tab (to get live status from WSL)
    // Pause auto-refresh when Create Child Host modal is open to prevent interference
    useEffect(() => {
        if (currentTabId === 'child-hosts' && host?.active && supportsChildHosts() && !createChildHostOpen) {
            // When tab is first opened, request fresh status from agent
            // Only do this once every 30 seconds to avoid spamming
            const now = Date.now();
            if (now - childHostsLastAgentRefresh.current > 30000) {
                childHostsLastAgentRefresh.current = now;
                // Request fresh child host status from agent (silently, no snackbar)
                requestChildHostsRefresh(false);
            }

            // Start auto-refresh every 15 seconds (without loading indicator)
            const interval = setInterval(() => {
                fetchChildHosts(false);
                fetchVirtualizationStatus();
            }, 15000);
            childHostsRefreshInterval.current = interval;

            return () => {
                if (interval) {
                    clearInterval(interval);
                }
            };
        } else if (childHostsRefreshInterval.current) {
            // Clear interval when tab is not active, host is not active, or modal is open
            clearInterval(childHostsRefreshInterval.current);
            childHostsRefreshInterval.current = null;
        }
    }, [currentTabId, host?.active, host?.id, fetchChildHosts, fetchVirtualizationStatus, supportsChildHosts, host, requestChildHostsRefresh, createChildHostOpen]);

    // Poll reboot orchestration status every 5 seconds when active
    useEffect(() => {
        if (!rebootOrchestrationId || !host?.id) return;

        const pollStatus = async () => {
            try {
                const status = await getRebootOrchestrationStatus(host.id, rebootOrchestrationId);
                setRebootOrchestrationStatus(status);

                if (status.status === 'completed' || status.status === 'failed') {
                    setRebootOrchestrationId(null);
                    if (status.status === 'completed') {
                        setSnackbarMessage(
                            status.error_message
                                ? t('hosts.rebootOrchestration.completedWithErrors', 'Orchestrated reboot completed: {{error}}', { error: status.error_message })
                                : t('hosts.rebootOrchestration.completed', 'Orchestrated reboot completed successfully')
                        );
                        setSnackbarSeverity(status.error_message ? 'warning' : 'success');
                    } else {
                        setSnackbarMessage(t('hosts.rebootOrchestration.failed', 'Orchestrated reboot failed: {{error}}', { error: status.error_message || 'Unknown error' }));
                        setSnackbarSeverity('error');
                    }
                    setSnackbarOpen(true);
                }
            } catch (error) {
                console.error('Failed to poll orchestration status:', error);
            }
        };

        pollStatus();
        const interval = setInterval(pollStatus, 5000);
        return () => clearInterval(interval);
    }, [rebootOrchestrationId, host?.id, t]);

    // Check permissions
    useEffect(() => {
        const checkPermissions = async () => {
            const [editTags, editHostname, stopService, startService, restartService, addPackage, deploySshKey, deployCertificate, attachUbuntuPro, detachUbuntuPro, deployAntivirus, enableAntivirus, disableAntivirus, removeAntivirus, addHostAccount, addHostGroup, deleteHostAccount, deleteHostGroup, enableWsl, enableLxd, enableKvm, enableVmm, enableBhyve] = await Promise.all([
                hasPermission(SecurityRoles.EDIT_TAGS),
                hasPermission(SecurityRoles.EDIT_HOST_HOSTNAME),
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
                hasPermission(SecurityRoles.REMOVE_ANTIVIRUS),
                hasPermission(SecurityRoles.ADD_HOST_ACCOUNT),
                hasPermission(SecurityRoles.ADD_HOST_GROUP),
                hasPermission(SecurityRoles.DELETE_HOST_ACCOUNT),
                hasPermission(SecurityRoles.DELETE_HOST_GROUP),
                hasPermission(SecurityRoles.ENABLE_WSL),
                hasPermission(SecurityRoles.ENABLE_LXD),
                hasPermission(SecurityRoles.ENABLE_KVM),
                hasPermission(SecurityRoles.ENABLE_VMM),
                hasPermission(SecurityRoles.ENABLE_BHYVE)
            ]);
            setCanEditTags(editTags);
            setCanEditHostname(editHostname);
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
            setCanAddHostAccount(addHostAccount);
            setCanAddHostGroup(addHostGroup);
            setCanDeleteHostAccount(deleteHostAccount);
            setCanDeleteHostGroup(deleteHostGroup);
            setCanEnableWsl(enableWsl);
            setCanEnableLxd(enableLxd);
            setCanEnableKvm(enableKvm);
            setCanEnableVmm(enableVmm);
            setCanEnableBhyve(enableBhyve);
        };
        checkPermissions();
    }, []);

    // Main initialization effect that loads host data, storage, network, users, certificates, and optional subsystems with proper error handling
    useEffect(() => { // NOSONAR
        if (!localStorage.getItem('bearer_token')) {
            navigate("/login");
            return;
        }

        if (!hostId) {
            setError(t('hostDetail.invalidId', 'Invalid host ID'));
            setLoading(false);
            return;
        }

        const fetchHost = async () => { // NOSONAR
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
                        const match = /^([A-Za-z]+)/.exec(osName);
                        if (match) {
                            osName = match[1];
                        }
                    }

                    if (osName) {
                        const response = await axiosInstance.get(`/api/antivirus-defaults/${osName}`);
                        setHasAntivirusOsDefault(response.data?.antivirus_package !== null);
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
                        } catch (_error) {
                            console.warn('Failed to parse legacy storage data:', _error);
                        }
                    } else {
                        setStorageDevices(storageData);
                    }

                    if (networkData.length === 0 && hostData.network_details) {
                        try {
                            const legacyNetworkData = JSON.parse(hostData.network_details);
                            setNetworkInterfaces(legacyNetworkData);
                        } catch (_error) {
                            console.warn('Failed to parse legacy network data:', _error);
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
                    // Fetch child hosts data and virtualization status if supported
                    // Windows hosts support WSL, Linux hosts support LXD (Ubuntu 22.04+)
                    if (hostData.platform?.includes('Windows') || hostData.platform?.includes('Linux')) {
                        try {
                            await fetchChildHosts();
                            await fetchVirtualizationStatus();
                        } catch (error) {
                            // Child hosts data is optional, don't fail the whole page load
                            console.log('Child hosts data not available or failed to load:', error);
                        }
                    }
                } catch (_error) {
                    // Log but don't fail the whole request - hardware/software/diagnostics data is optional
                    console.warn('Failed to fetch hardware/software/diagnostics data:', _error);
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
    }, [hostId, navigate, t, fetchCertificates, fetchRoles, fetchChildHosts, fetchVirtualizationStatus]);

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
            } catch {
                // Graylog not configured or unavailable — not an error condition
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

    // Load software packages lazily when Software tab is selected or pagination changes
    useEffect(() => {
        const loadSoftwarePackages = async () => {
            if (currentTabId === 'software' && hostId) {
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
    }, [currentTabId, hostId, softwarePagination.page, softwarePagination.page_size, softwareSearchTerm]);

    // Load installation history when Software Changes tab is selected
    useEffect(() => {
        if (currentTabId === 'software-changes') {
            fetchInstallationHistory();
        }
    }, [currentTabId, hostId, fetchInstallationHistory]);

    // Auto-refresh installation history every 30 seconds when on Software Changes tab
    useEffect(() => {
        let interval: ReturnType<typeof globalThis.setInterval> | null = null;
        if (hostId && currentTabId === 'software-changes') {
            interval = globalThis.setInterval(async () => {
                try {
                    await fetchInstallationHistory();
                } catch (error) {
                    console.error('Auto-refresh error for installation history:', error);
                }
            }, 30000); // 30 seconds
        }
        return () => {
            if (interval) {
                globalThis.clearInterval(interval);
            }
        };
    }, [hostId, currentTabId, fetchInstallationHistory]);

    // Auto-refresh Ubuntu Pro information every 30 seconds
    useEffect(() => {
        let interval: ReturnType<typeof globalThis.setInterval> | null = null;

        if (hostId && isUbuntu() && ubuntuProInfo?.available) {
            interval = globalThis.setInterval(async () => {
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
                globalThis.clearInterval(interval);
            }
        };
    }, [hostId, isUbuntu, ubuntuProInfo?.available, servicesMessage]);

    // Auto-refresh user accounts and groups every 60 seconds
    useEffect(() => {
        let interval: ReturnType<typeof globalThis.setInterval> | null = null;

        if (hostId) {
            interval = globalThis.setInterval(async () => {
                try {
                    const [usersData, groupsData] = await Promise.all([
                        doGetHostUsers(hostId),
                        doGetHostGroups(hostId),
                    ]);
                    setUserAccounts(usersData);
                    setUserGroups(groupsData);
                } catch {
                    // Silently ignore errors during auto-refresh
                }
            }, 60000); // 60 seconds
        }

        return () => {
            if (interval) {
                globalThis.clearInterval(interval);
            }
        };
    }, [hostId]);

    // Listen for hash changes (browser back/forward)
    useEffect(() => {
        const handleHashChange = () => {
            const hash = globalThis.location.hash.slice(1);
            if (!hash) return;
            const tabs = getTabNames();
            const tabIndex = tabs.indexOf(hash);
            if (tabIndex >= 0) {
                setCurrentTab(tabIndex);
            }
        };

        globalThis.addEventListener('hashchange', handleHashChange);
        return () => globalThis.removeEventListener('hashchange', handleHashChange);
    }, [getTabNames]);

    // Recalculate current tab when host or ubuntuProInfo changes (handles dynamic tabs)
    useEffect(() => {
        const hash = globalThis.location.hash.slice(1);
        if (!hash) return;
        const tabs = getTabNames();
        const tabIndex = tabs.indexOf(hash);
        if (tabIndex >= 0 && tabIndex !== currentTab) {
            setCurrentTab(tabIndex);
        }
    }, [host, ubuntuProInfo, getTabNames, currentTab]);

    const formatDate = (dateString: string | null | undefined): string => {
        return formatUTCTimestamp(dateString, t('common.notAvailable', 'N/A'));
    };

    const formatTimestamp = (timestamp: string | null | undefined) => {
        if (!timestamp) return t('hosts.never', 'never');
        const date = parseUTCTimestamp(timestamp);
        if (!date) return t('hosts.invalidDate', 'invalid');

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
        const lastAccess = parseUTCTimestamp(host.last_access);
        if (!lastAccess) return 'down';
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

    // Helper function to get user ID label and value (extracts nested ternary for SonarQube compliance)
    const getUserIdDisplay = (user: UserAccount): string => {
        const isWindows = host?.platform?.toLowerCase().includes('windows');
        const label = isWindows ? 'SID' : 'UID';
        let value: string;
        if (isWindows) {
            value = user.security_id || t('common.notAvailable');
        } else {
            value = user.uid === undefined ? t('common.notAvailable') : String(user.uid);
        }
        return `${label}: ${value}`;
    };

    // Helper function to get group ID label and value (extracts nested ternary for SonarQube compliance)
    const getGroupIdDisplay = (group: UserGroup): string => {
        const isWindows = host?.platform?.toLowerCase().includes('windows');
        const label = isWindows ? 'SID' : 'GID';
        let value: string;
        if (isWindows) {
            value = group.security_id || t('common.notAvailable');
        } else {
            value = (group.gid !== undefined && group.gid !== null) ? String(group.gid) : t('common.notAvailable');
        }
        return `${label}: ${value}`;
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

    // Delete user account handlers
    const handleDeleteUserClick = (user: UserAccount) => {
        setUserToDelete(user);
        setDeleteDefaultGroup(true);  // Reset to default checked
        setDeleteUserConfirmOpen(true);
    };

    const handleDeleteUserConfirm = async () => {
        if (!userToDelete || !hostId) return;

        setDeletingUser(true);
        try {
            await axiosInstance.delete(`/api/host/${hostId}/accounts/${encodeURIComponent(userToDelete.username)}?delete_default_group=${deleteDefaultGroup}`);
            setSnackbarMessage(t('hostAccount.deleteSuccess', 'User account deletion requested. The user list will update automatically.'));
            setSnackbarSeverity('success');
            setSnackbarOpen(true);
            setDeleteUserConfirmOpen(false);
            setUserToDelete(null);
        } catch (error: unknown) {
            console.error('Failed to delete user:', error);
            let errorMessage = t('hostAccount.deleteFailed', 'Failed to delete user account');
            if (axios.isAxiosError(error) && error.response?.data?.detail) {
                errorMessage = error.response.data.detail;
            }
            setSnackbarMessage(errorMessage);
            setSnackbarSeverity('error');
            setSnackbarOpen(true);
        } finally {
            setDeletingUser(false);
        }
    };

    const handleDeleteUserCancel = () => {
        setDeleteUserConfirmOpen(false);
        setUserToDelete(null);
    };

    // Delete group handlers
    const handleDeleteGroupClick = (group: UserGroup) => {
        setGroupToDelete(group);
        setDeleteGroupConfirmOpen(true);
    };

    const handleDeleteGroupConfirm = async () => {
        if (!groupToDelete || !hostId) return;

        setDeletingGroup(true);
        try {
            await axiosInstance.delete(`/api/host/${hostId}/groups/${encodeURIComponent(groupToDelete.group_name)}`);
            setSnackbarMessage(t('hostGroup.deleteSuccess', 'Group deletion requested. The group list will update automatically.'));
            setSnackbarSeverity('success');
            setSnackbarOpen(true);
            setDeleteGroupConfirmOpen(false);
            setGroupToDelete(null);
        } catch (error: unknown) {
            console.error('Failed to delete group:', error);
            let errorMessage = t('hostGroup.deleteFailed', 'Failed to delete group');
            if (axios.isAxiosError(error) && error.response?.data?.detail) {
                errorMessage = error.response.data.detail;
            }
            setSnackbarMessage(errorMessage);
            setSnackbarSeverity('error');
            setSnackbarOpen(true);
        } finally {
            setDeletingGroup(false);
        }
    };

    const handleDeleteGroupCancel = () => {
        setDeleteGroupConfirmOpen(false);
        setGroupToDelete(null);
    };

    const handleSSHKeySearch = () => {
        const searchTerm = sshKeySearchTerm.toLowerCase().trim();
        if (searchTerm === '') {
            setFilteredSSHKeys(availableSSHKeys);
        } else {
            const filtered = availableSSHKeys.filter((key) =>
                key.name.toLowerCase().includes(searchTerm) ||
                (key.filename?.toLowerCase().includes(searchTerm))
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
                cert.filename?.toLowerCase().includes(searchTerm)
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
            if (axios.isAxiosError(error) && error.response?.data?.detail) {
                errorMessage = error.response.data.detail;
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
                    {String(t(`secrets.cert_type.${String(params.value)}`, String(params.value)))}
                </Typography>
            ),
        },
        {
            field: 'created_at',
            headerName: t('secrets.createdAt', 'Created'),
            width: 180,
            renderCell: (params) => (
                <Typography variant="body2">
                    {formatUTCTimestamp(params.value)}
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
                    {String(t(`secrets.key_type.${String(params.value)}`, String(params.value)))}
                </Typography>
            ),
        },
        {
            field: 'created_at',
            headerName: t('secrets.createdAt', 'Created'),
            width: 180,
            renderCell: (params) => (
                <Typography variant="body2">
                    {formatUTCTimestamp(params.value)}
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

            if (axios.isAxiosError(error) && error.response?.data?.detail) {
                errorMessage = error.response.data.detail;
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
                const prioritized = deviceGroup.toSorted((a, b) => {
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
                    setSoftwarePackages(softwareData.items);

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

            // Build list of requests to make
            const requests: Promise<unknown>[] = [
                doRequestHostDiagnostics(hostId),
                doRequestSystemInfo(hostId),
                doRefreshUserAccessData(hostId),
                doRefreshSoftwareData(hostId),
                doRefreshUpdatesCheck(hostId)
            ];

            // If host supports child hosts (Windows), also request virtualization check
            if (supportsChildHosts()) {
                requests.push(
                    axiosInstance.get(`/api/host/${hostId}/virtualization`).catch(err => {
                        console.log('Virtualization check request failed (optional):', err);
                        return null;
                    })
                );
            }

            // Request diagnostics, system info, user access data, software inventory, package updates, and virtualization check
            await Promise.all(requests);

            // Show success message
            console.log('Host data requested successfully');
            
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
                            
                            // If status is still pending, continue polling; otherwise refresh diagnostics data and virtualization status
                            if (currentHost?.diagnostics_request_status === 'pending') {
                                // Continue polling
                                pollForCompletion(attempts + 1, maxAttempts);
                            } else {
                                const updatedDiagnostics = await doGetHostDiagnostics(hostId);
                                setDiagnosticsData(updatedDiagnostics);
                                // Also refresh virtualization status if this host supports child hosts
                                if (supportsChildHosts()) {
                                    await fetchVirtualizationStatus();
                                }
                                console.log('Diagnostics request completed');
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

    const handleRebootClick = async () => {
        if (supportsChildHosts() && host?.id) {
            setRebootPreCheckLoading(true);
            try {
                const preCheck = await doRebootPreCheck(host.id);
                setRebootPreCheckData(preCheck);
            } catch (error) {
                console.error('Failed to pre-check reboot:', error);
                setRebootPreCheckData(null);
            } finally {
                setRebootPreCheckLoading(false);
            }
        } else {
            setRebootPreCheckData(null);
        }
        setRebootConfirmOpen(true);
    };

    const handleShutdownClick = () => {
        setShutdownConfirmOpen(true);
    };

    const handleRebootConfirm = async () => {
        if (!host?.id) return;

        try {
            if (rebootPreCheckData?.has_running_children && rebootPreCheckData?.has_container_engine) {
                // Pro+: Use orchestrated reboot
                const result = await doOrchestratedReboot(host.id);
                setRebootOrchestrationId(result.orchestration_id);
                setSnackbarMessage(t('hosts.rebootOrchestration.initiated', 'Orchestrated reboot initiated — stopping {{count}} child host(s)', { count: result.child_count }));
                setSnackbarSeverity('success');
            } else {
                // Standard reboot (no children or no Pro+)
                await doRebootHost(host.id);
                setSnackbarMessage(t('hosts.rebootRequested', 'Reboot requested successfully'));
                setSnackbarSeverity('success');
            }
            setSnackbarOpen(true);
            setRebootConfirmOpen(false);
            setRebootPreCheckData(null);
        } catch (error) {
            console.error('Failed to request reboot:', error);
            setSnackbarMessage(t('hosts.rebootFailed', 'Failed to request reboot'));
            setSnackbarSeverity('error');
            setSnackbarOpen(true);
        }
    };

    const handleHostnameEditClick = () => {
        if (host) {
            setNewHostname(host.fqdn);
            setHostnameEditOpen(true);
        }
    };

    const handleHostnameChange = async () => {
        if (!host?.id || !newHostname.trim()) return;

        setHostnameEditLoading(true);
        try {
            await doChangeHostname(host.id, newHostname.trim());
            setSnackbarMessage(t('hostDetail.hostnameChangeRequested', 'Hostname change requested'));
            setSnackbarSeverity('success');
            setSnackbarOpen(true);
            setHostnameEditOpen(false);
        } catch (error) {
            console.error('Failed to change hostname:', error);
            setSnackbarMessage(t('hostDetail.hostnameChangeFailed', 'Failed to change hostname'));
            setSnackbarSeverity('error');
            setSnackbarOpen(true);
        } finally {
            setHostnameEditLoading(false);
        }
    };

    const handleRequestPackages = () => {
        setRequestPackagesConfirmOpen(true);
    };

    const handleRequestPackagesConfirm = async () => {
        if (!host?.id) return;
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
        if (!host?.id) return;

        try {
            // Call backend API to deploy antivirus to this specific host
            const response = await axiosInstance.post('/api/deploy', {
                host_ids: [host.id]
            });

            if (response.data.failed_hosts?.length > 0) {
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
        if (!host?.id) return;

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
        if (!host?.id) return;

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
        if (!host?.id) return;

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
        if (!host?.id) return;

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
            const response = await globalThis.fetch(`/api/hosts/${hostId}/tags/${selectedTagToAdd}`, {
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
            const response = await globalThis.fetch(`/api/hosts/${hostId}/tags/${tagId}`, {
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

    const handleCloseSnackbar = (_event: React.SyntheticEvent | Event, reason?: string) => {
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
        if (newValue >= 0 && newValue < tabs.length) {
            globalThis.location.hash = tabs[newValue]; // nosemgrep: detect-object-injection
        }
    };

    // Ubuntu Pro handlers
    const handleUbuntuProAttach = async () => {
        // Try to load master Ubuntu Pro token
        try {
            const response = await axiosInstance.get('/api/ubuntu-pro/');
            const masterKey = response.data.master_key;
            if (masterKey?.trim()) {
                // Master key exists - attach directly without showing the token

                setUbuntuProAttaching(true);
                try {
                    await doAttachUbuntuPro(hostId!, masterKey.trim());
                    setSnackbarMessage(t('hostDetail.ubuntuProAttachSuccess', 'Ubuntu Pro attach requested'));
                    setSnackbarSeverity('success');
                    setSnackbarOpen(true);
                    // Start polling - attaching state stays active until attached
                    startUbuntuProPolling();
                } catch {
                    setSnackbarMessage(t('hostDetail.ubuntuProAttachError', 'Failed to attach Ubuntu Pro'));
                    setSnackbarSeverity('error');
                    setSnackbarOpen(true);
                    setUbuntuProAttaching(false);
                }
                return;
            }
        } catch (error) {
            console.log('No master Ubuntu Pro token configured or error loading:', error);
        }

        // No master key - show dialog for manual token entry
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
            setSnackbarMessage(t('hostDetail.ubuntuProDetachSuccess', 'Ubuntu Pro detach requested'));
            setSnackbarSeverity('success');
            setSnackbarOpen(true);
            // Poll until detached
            let pollCount = 0;
            const maxPolls = 30;
            const pollInterval = setInterval(async () => {
                pollCount++;
                try {
                    const ubuntuProData = await doGetHostUbuntuPro(hostId);
                    setUbuntuProInfo(ubuntuProData);
                    if (!ubuntuProData.attached || pollCount >= maxPolls) {
                        clearInterval(pollInterval);
                        setUbuntuProDetaching(false);
                    }
                } catch {
                    if (pollCount >= maxPolls) {
                        clearInterval(pollInterval);
                        setUbuntuProDetaching(false);
                    }
                }
            }, 2000);
        } catch {
            setSnackbarMessage(t('hostDetail.ubuntuProDetachError', 'Failed to detach Ubuntu Pro'));
            setSnackbarSeverity('error');
            setSnackbarOpen(true);
            setUbuntuProDetaching(false);
        }
    };

    const handleCancelUbuntuProDetach = () => {
        setUbuntuProDetachConfirmOpen(false);
    };

    const startUbuntuProPolling = () => {
        if (!hostId) return;
        let pollCount = 0;
        const maxPolls = 30; // Poll for up to ~60 seconds
        const pollInterval = setInterval(async () => {
            pollCount++;
            try {
                const ubuntuProData = await doGetHostUbuntuPro(hostId);
                setUbuntuProInfo(ubuntuProData);
                if (ubuntuProData.attached || pollCount >= maxPolls) {
                    clearInterval(pollInterval);
                    setUbuntuProAttaching(false);
                }
            } catch {
                if (pollCount >= maxPolls) {
                    clearInterval(pollInterval);
                    setUbuntuProAttaching(false);
                }
            }
        }, 2000);
    };

    const handleUbuntuProTokenSubmit = async () => {
        if (!hostId || !host || !ubuntuProToken.trim()) return;

        setUbuntuProAttaching(true);
        setUbuntuProTokenDialog(false);

        try {
            await doAttachUbuntuPro(hostId, ubuntuProToken.trim());
            setSnackbarMessage(t('hostDetail.ubuntuProAttachSuccess', 'Ubuntu Pro attach requested'));
            setSnackbarSeverity('success');
            setSnackbarOpen(true);
            setUbuntuProToken('');
            // Start polling - attaching state stays active until attached
            startUbuntuProPolling();
        } catch {
            setSnackbarMessage(t('hostDetail.ubuntuProAttachError', 'Failed to attach Ubuntu Pro'));
            setSnackbarSeverity('error');
            setSnackbarOpen(true);
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
                const swChangesIdx = tabDefinitions.findIndex(td => td.id === 'software-changes');
                if (swChangesIdx >= 0) setCurrentTab(swChangesIdx);

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
                const swChangesIdx = tabDefinitions.findIndex(td => td.id === 'software-changes');
                if (swChangesIdx >= 0) setCurrentTab(swChangesIdx);

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
        return formatUTCTimestamp(dateString);
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
            status.charAt(0).toUpperCase() + status.slice(1).replaceAll('_', ' ') :
            translated;
    };

    // Get OpenTelemetry service status label (extracted for SonarQube compliance)
    const getOpenTelemetryServiceLabel = (serviceStatus: string): string => {
        if (serviceStatus === 'running') {
            return t('hostDetail.opentelemetryServiceRunning', 'Running');
        } else if (serviceStatus === 'stopped') {
            return t('hostDetail.opentelemetryServiceStopped', 'Stopped');
        } else {
            return t('hostDetail.opentelemetryServiceUnknown', 'Unknown');
        }
    };

    // Get OpenTelemetry service status color (extracted for SonarQube compliance)
    const getOpenTelemetryServiceColor = (serviceStatus: string): 'success' | 'error' | 'default' => {
        if (serviceStatus === 'running') {
            return 'success';
        } else if (serviceStatus === 'stopped') {
            return 'error';
        } else {
            return 'default';
        }
    };

    // Get role service status label (extracted for SonarQube compliance)
    const getRoleServiceStatusLabel = (serviceStatus: string | null | undefined): string => {
        if (serviceStatus === 'running') {
            return t('hostDetail.running', 'Running');
        } else if (serviceStatus === 'stopped') {
            return t('hostDetail.stopped', 'Stopped');
        } else if (serviceStatus === 'installed') {
            return t('hostDetail.installed', 'Installed');
        } else {
            return serviceStatus || t('common.unknown', 'Unknown');
        }
    };

    // Get role service status color (extracted for SonarQube compliance)
    const getRoleServiceStatusColor = (serviceStatus: string | null | undefined): 'success' | 'error' | 'info' | 'default' => {
        if (serviceStatus === 'running') {
            return 'success';
        } else if (serviceStatus === 'stopped') {
            return 'error';
        } else if (serviceStatus === 'installed') {
            return 'info';
        } else {
            return 'default';
        }
    };

    // Get service status label for Ubuntu Pro services (extracted for SonarQube compliance)
    const getServiceStatusLabel = (status: string): string => {
        if (status === 'n/a') {
            return 'N/A';
        } else if (status === 'enabled') {
            return t('hostDetail.enabled', 'Enabled');
        } else {
            return t('hostDetail.disabled', 'Disabled');
        }
    };

    // Get service status color for Ubuntu Pro services (extracted for SonarQube compliance)
    const getServiceStatusColor = (status: string): 'success' | 'default' | 'warning' => {
        if (status === 'enabled') {
            return 'success';
        } else if (status === 'n/a') {
            return 'default';
        } else {
            return 'warning';
        }
    };

    // Get edited service label (extracted for SonarQube compliance)
    const getEditedServiceLabel = (serviceName: string, serviceStatus: string): string => {
        const isEnabled = editedServices[serviceName] ?? (serviceStatus === 'enabled');
        return isEnabled ? t('hostDetail.enabled', 'Enabled') : t('hostDetail.disabled', 'Disabled');
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

                const expiryDate = parseUTCTimestamp(params.value);
                const isExpired = params.row.is_expired;
                const daysUntilExpiry = params.row.days_until_expiry;

                let expiryColor: string;
                if (isExpired) {
                    expiryColor = 'error.main';
                } else if (daysUntilExpiry !== null && daysUntilExpiry <= 30) {
                    expiryColor = 'warning.main';
                } else {
                    expiryColor = 'text.primary';
                }

                return (
                    <Box>
                        <Typography
                            variant="body2"
                            sx={{
                                color: expiryColor
                            }}
                        >
                            {expiryDate ? expiryDate.toLocaleDateString() : t('common.unknown', 'Unknown')}
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

    // Helper function to get empty state message for Windows hosts (WSL)
    const getWslEmptyMessage = (): string => {
        if (virtualizationStatus?.capabilities?.wsl?.enabled) {
            return t('hostDetail.childHostsEmptyWslEnabled', 'Click "Create Child Host" to create a new WSL instance.');
        }
        if (virtualizationStatus?.capabilities?.wsl?.needs_enable) {
            return t('hostDetail.childHostsEmptyWslNotEnabled', 'Enable WSL to create virtual machines on this host.');
        }
        return t('hostDetail.childHostsEmptyDescription', 'WSL instances and other virtual machines on this Windows host will appear here.');
    };

    // Helper function to get empty state message for Linux hosts (LXD)
    const getLxdEmptyMessage = (): string => {
        if (virtualizationStatus?.capabilities?.lxd?.installed && virtualizationStatus?.capabilities?.lxd?.initialized) {
            return t('hostDetail.childHostsEmptyLxdReady', 'Click "Create Child Host" to create a new LXD container.');
        }
        if (virtualizationStatus?.capabilities?.lxd?.available) {
            return t('hostDetail.childHostsEmptyLxdNotReady', 'Enable LXD to create containers on this host.');
        }
        return t('hostDetail.childHostsEmptyLxdNotAvailable', 'LXD is not available on this host. Ubuntu 22.04 or newer is required.');
    };

    // Helper function to get empty state message for OpenBSD hosts (VMM)
    const getVmmEmptyMessage = (): string => {
        if (virtualizationStatus?.capabilities?.vmm?.enabled && virtualizationStatus?.capabilities?.vmm?.running) {
            return t('hostDetail.childHostsEmptyVmmReady', 'Click "Create Child Host" to create a new VMM virtual machine.');
        }
        if (virtualizationStatus?.capabilities?.vmm?.available) {
            return t('hostDetail.childHostsEmptyVmmNotReady', 'Enable VMM to create virtual machines on this host.');
        }
        return t('hostDetail.childHostsEmptyVmmNotAvailable', 'VMM is not available on this host.');
    };

    // Helper function to get empty state message for FreeBSD hosts (bhyve)
    const getBhyveEmptyMessage = (): string => {
        if (virtualizationStatus?.capabilities?.bhyve?.enabled && virtualizationStatus?.capabilities?.bhyve?.running) {
            return t('hostDetail.childHostsEmptyBhyveReady', 'Click "Create Child Host" to create a new bhyve virtual machine.');
        }
        if (virtualizationStatus?.capabilities?.bhyve?.available) {
            return t('hostDetail.childHostsEmptyBhyveNotReady', 'Enable bhyve to create virtual machines on this host.');
        }
        return t('hostDetail.childHostsEmptyBhyveNotAvailable', 'bhyve is not available on this host.');
    };

    // Helper function to get the create child host dialog title
    const getCreateChildHostTitle = (): string => {
        switch (childHostFormData.childType) {
            case 'lxd':
                return t('hostDetail.createLxdContainerTitle', 'Create LXD Container');
            case 'vmm':
                return t('hostDetail.createVmmVmTitle', 'Create VMM Virtual Machine');
            case 'kvm':
                return t('hostDetail.createKvmVmTitle', 'Create KVM Virtual Machine');
            case 'bhyve':
                return t('hostDetail.createBhyveVmTitle', 'Create bhyve Virtual Machine');
            default:
                return t('hostDetail.createChildHostTitle', 'Create WSL Instance');
        }
    };

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
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
                    <Typography variant="h4" sx={{ display: 'flex', alignItems: 'center' }}>
                        <ComputerIcon sx={{ mr: 2, fontSize: '2rem' }} />
                        {host.fqdn}
                        {canEditHostname && host.active && host.is_agent_privileged && (
                            <IconButton
                                size="small"
                                onClick={handleHostnameEditClick}
                                sx={{ ml: 1 }}
                                title={t('hostDetail.editHostname', 'Edit Hostname')}
                            >
                                <EditIcon fontSize="small" />
                            </IconButton>
                        )}
                    </Typography>
                    {host.parent_host_id && (
                        <Button
                            variant="outlined"
                            size="small"
                            startIcon={<AccountTreeIcon />}
                            onClick={() => navigate(`/hosts/${host.parent_host_id}`)}
                            sx={{ textTransform: 'none' }}
                        >
                            {t('hosts.viewParent', 'View Parent Host')}
                        </Button>
                    )}
                </Box>
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
                <Tabs value={currentTab} onChange={handleTabChange} aria-label="host detail tabs" variant="scrollable" scrollButtons="auto">
                    {tabDefinitions.map(tabDef => (
                        <Tab
                            key={tabDef.id}
                            icon={tabDef.icon}
                            label={tabDef.label}
                            iconPosition="start"
                            sx={{ textTransform: 'none' }}
                        />
                    ))}
                </Tabs>
            </Box>

            {/* Tab Content - flexGrow to fill available space */}
            <Box sx={{ flexGrow: 1, overflow: 'auto', minHeight: 0 }}>
            {currentTabId === 'info' && (
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
                                <Grid size={{ xs: 12, sm: 6 }}>
                                    <Typography variant="body2" color="textSecondary">
                                        {t('hostDetail.timezone', 'Timezone')}
                                    </Typography>
                                    <Typography variant="body1">{host.timezone || t('common.notAvailable')}</Typography>
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
                            {(() => {
                                if (openTelemetryLoading) {
                                    return (
                                        <Box sx={{ display: 'flex', justifyContent: 'center', p: 2 }}>
                                            <CircularProgress size={24} />
                                        </Box>
                                    );
                                }
                                if (openTelemetryStatus) {
                                    return (
                                        <Grid container spacing={2}>
                                            <Grid size={{ xs: 12 }}>
                                                <Typography variant="body2" color="textSecondary">
                                                    {t('hostDetail.opentelemetryDeployed', 'Deployed')}
                                                </Typography>
                                                <Typography variant="body1">
                                                    {openTelemetryStatus.deployed ? t('common.yes', 'Yes') : t('common.no', 'No')}
                                                </Typography>
                                            </Grid>
                                            {!openTelemetryStatus.deployed && hasPermissionSync(SecurityRoles.DEPLOY_OPENTELEMETRY) && host?.is_agent_privileged && (
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
                                                            label={getOpenTelemetryServiceLabel(openTelemetryStatus.service_status)}
                                                            color={getOpenTelemetryServiceColor(openTelemetryStatus.service_status)}
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
                                    );
                                }
                                return (
                                    <Typography variant="body2" color="textSecondary">
                                        {t('common.notAvailable', 'Not Available')}
                                    </Typography>
                                );
                            })()}
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
            {currentTabId === 'hardware' && (
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
            {currentTabId === 'software' && (
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
                                        slotProps={{
                                            input: {
                                                startAdornment: (
                                                    <InputAdornment position="start">
                                                        <SearchIcon />
                                                    </InputAdornment>
                                                ),
                                            },
                                        }}
                                        size="small"
                                    />
                                </Box>
                                {(() => {
                                    if (loadingSoftware) {
                                        return (
                                            <Box sx={{ display: 'flex', justifyContent: 'center', alignItems: 'center', py: 4 }}>
                                                <CircularProgress />
                                                <Typography variant="body2" color="textSecondary" sx={{ ml: 2 }}>
                                                    {t('hostDetail.loadingSoftware', 'Loading software packages...')}
                                                </Typography>
                                            </Box>
                                        );
                                    }
                                    if (softwarePackages.length === 0) {
                                        return (
                                            <Typography variant="body2" color="textSecondary" sx={{ fontStyle: 'italic', textAlign: 'center', py: 2 }}>
                                                {t('hostDetail.noSoftwareFound', 'No software packages found')}
                                            </Typography>
                                        );
                                    }
                                    return (
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
                                    );
                                })()}
                            </CardContent>
                        </Card>
                    </Grid>
                </Grid>
            )}

            {/* Third-Party Repositories Tab */}
            {currentTabId === 'third-party-repos' && host && (
                <ThirdPartyRepositories
                    hostId={hostId || ''}
                    privilegedMode={host.is_agent_privileged || false}
                    osName={host.platform_release || host.platform || ''}
                />
            )}

            {/* Access Tab */}
            {currentTabId === 'access' && (
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
                                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                                        {canAddHostAccount && host?.is_agent_privileged && (
                                            <Button
                                                variant="contained"
                                                color="primary"
                                                size="small"
                                                startIcon={<AddIcon />}
                                                onClick={() => setAddUserModalOpen(true)}
                                                disabled={!host?.active}
                                            >
                                                {t('hostAccount.add', 'Add')}
                                            </Button>
                                        )}
                                        <ToggleButtonGroup
                                            value={userFilter}
                                            exclusive
                                            onChange={(_, newFilter) => {
                                                if (newFilter !== null) {
                                                    setUserFilter(newFilter);
                                                }
                                            }}
                                            size="small"
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
                                                            <Box sx={{ display: 'flex', gap: 0.5 }}>
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
                                                                {canDeleteHostAccount && host?.is_agent_privileged && !user.is_system_user && (
                                                                    <IconButton
                                                                        size="small"
                                                                        color="error"
                                                                        onClick={() => handleDeleteUserClick(user)}
                                                                        disabled={!host?.active}
                                                                        title={t('hostAccount.deleteUser', 'Delete User')}
                                                                        sx={{ p: 0.25 }}
                                                                    >
                                                                        <DeleteIcon fontSize="small" />
                                                                    </IconButton>
                                                                )}
                                                            </Box>
                                                        </Box>
                                                        <Typography variant="body2" color="textSecondary" sx={{ mb: 0.5 }}>
                                                            {getUserIdDisplay(user)}
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
                                                                    {(expandedUserGroups.has(user.id) ? user.groups : user.groups.slice(0, 6)).map((groupName: string) => (
                                                                        <Chip
                                                                            key={groupName}
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
                                                                                setExpandedUserGroups(prev => new Set([...Array.from(prev), user.id]));
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
                                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                                        {canAddHostGroup && host?.is_agent_privileged && (
                                            <Button
                                                variant="contained"
                                                color="primary"
                                                size="small"
                                                startIcon={<AddIcon />}
                                                onClick={() => setAddGroupModalOpen(true)}
                                                disabled={!host?.active}
                                            >
                                                {t('hostGroup.add', 'Add')}
                                            </Button>
                                        )}
                                        <ToggleButtonGroup
                                            value={groupFilter}
                                            exclusive
                                            onChange={(_, newFilter) => {
                                                if (newFilter !== null) {
                                                    setGroupFilter(newFilter);
                                                }
                                            }}
                                            size="small"
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
                                                        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', mb: 1 }}>
                                                            <Typography variant="subtitle2" sx={{ fontWeight: 'bold' }}>
                                                                {group.group_name}
                                                            </Typography>
                                                            {canDeleteHostGroup && host?.is_agent_privileged && !group.is_system_group && (
                                                                <IconButton
                                                                    size="small"
                                                                    color="error"
                                                                    onClick={() => handleDeleteGroupClick(group)}
                                                                    disabled={!host?.active}
                                                                    title={t('hostGroup.deleteGroup', 'Delete Group')}
                                                                    sx={{ p: 0.25 }}
                                                                >
                                                                    <DeleteIcon fontSize="small" />
                                                                </IconButton>
                                                            )}
                                                        </Box>
                                                        <Typography variant="body2" color="textSecondary" sx={{ mb: 0.5 }}>
                                                            {getGroupIdDisplay(group)}
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
                                                                    {(expandedGroupUsers.has(group.id) ? group.users : group.users.slice(0, 6)).map((userName: string) => (
                                                                        <Chip
                                                                            key={userName}
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
                                                                                setExpandedGroupUsers(prev => new Set([...Array.from(prev), group.id]));
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
            {currentTabId === 'security' && hostId && (
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

            {/* Plugin tabs content */}
            {visiblePluginTabs.map(pt => (
                currentTabId === pt.id && hostId && (
                    <Box key={pt.id} sx={{ p: 2 }}>
                        <pt.component hostId={hostId} />
                    </Box>
                )
            ))}

            {/* Certificates Tab */}
            {currentTabId === 'certificates' && (
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
                                            slotProps={{
                                                input: {
                                                    startAdornment: (
                                                        <InputAdornment position="start">
                                                            <SearchIcon />
                                                        </InputAdornment>
                                                    ),
                                                },
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
                                        <Box sx={{ height: 500 }}>
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
                                                sx={{
                                                    '& .MuiDataGrid-row': {
                                                        '&:hover': {
                                                            backgroundColor: 'action.hover',
                                                        },
                                                    },
                                                }}
                                            />
                                        </Box>
                                    </>
                                )}
                            </CardContent>
                        </Card>
                    </Grid>
                </Grid>
            )}

            {/* Software Changes Tab */}
            {currentTabId === 'software-changes' && (
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

                                {(() => {
                                    if (installationHistoryLoading) {
                                        return (
                                            <Box sx={{ display: 'flex', justifyContent: 'center', py: 4 }}>
                                                <CircularProgress />
                                            </Box>
                                        );
                                    }
                                    if (installationHistory.length === 0) {
                                        return (
                                            <Typography variant="body2" color="textSecondary" sx={{ textAlign: 'center', py: 4 }}>
                                                {t('hostDetail.noInstallationHistory', 'No software installation history found for this host.')}
                                            </Typography>
                                        );
                                    }
                                    return (
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
                                    );
                                })()}
                            </CardContent>
                        </Card>
                    </Grid>
                </Grid>
            )}

            {/* Server Roles Tab */}
            {currentTabId === 'server-roles' && (
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
                                                        {(() => {
                                                            const rolesWithServiceCount = roles.filter(role => role.service_name && role.service_name.trim() !== '').length;
                                                            return (
                                                                <Checkbox
                                                                    indeterminate={selectedRoles.length > 0 && selectedRoles.length < rolesWithServiceCount}
                                                                    checked={rolesWithServiceCount > 0 && selectedRoles.length === rolesWithServiceCount}
                                                                    onChange={(e) => e.target.checked ? selectAllRoles() : deselectAllRoles()}
                                                                    disabled={!host.is_agent_privileged || rolesWithServiceCount === 0}
                                                                />
                                                            );
                                                        })()}
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
                                                                    onChange={(e) => e.target.checked ? addRoleToSelection(role.id) : removeRoleFromSelection(role.id)}
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
                                                                    label={getRoleServiceStatusLabel(role.service_status)}
                                                                    color={getRoleServiceStatusColor(role.service_status)}
                                                                    size="small"
                                                                />
                                                            </TableCell>
                                                            <TableCell>
                                                                <Typography variant="body2" sx={{ color: 'textSecondary' }}>
                                                                    {formatUTCDate(role.detected_at)}
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
                                {!rolesLoading && roles.some(role => role.service_name && role.service_name.trim() !== '') && (canStartService || canStopService || canRestartService) && (
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

            {/* Child Hosts Tab */}
            {/* NOSONAR: Cognitive complexity is acceptable here as this is a cohesive JSX block rendering virtualization capabilities for multiple hypervisor types (WSL, LXD, VMM, KVM, bhyve) with consistent structure */}
            {currentTabId === 'child-hosts' && supportsChildHosts() && (
                <Grid container spacing={3}>
                    {/* Virtualization Capabilities - Card-based layout */}
                    <Grid size={{ xs: 12 }}>
                        <Box sx={{ mb: 2 }}>
                            <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 2 }}>
                                <Typography variant="h6" sx={{ fontWeight: 'bold' }}>
                                    {t('hostDetail.virtualizationCapabilities', 'Virtualization Capabilities')}
                                </Typography>
                                {virtualizationLoading && <CircularProgress size={20} />}
                            </Box>

                            {!virtualizationStatus && !virtualizationLoading && (
                                <Typography variant="body2" color="textSecondary">
                                    {t('hostDetail.virtualizationStatusUnavailable', 'Virtualization status not available')}
                                </Typography>
                            )}

                            {virtualizationStatus && (
                                <Grid container spacing={2}>
                                    {/* WSL Card - Windows hosts */}
                                    {host?.platform?.includes('Windows') && (
                                        <Grid size={{ xs: 12, sm: 6, md: 4, lg: 3 }}>
                                            <HypervisorStatusCard
                                                type="wsl"
                                                capabilities={virtualizationStatus.capabilities?.wsl}
                                                onEnable={handleEnableWsl}
                                                onCreate={() => openCreateDialogWithType('wsl')}
                                                canEnable={canEnableWsl}
                                                canCreate={hasPermissionSync(SecurityRoles.CREATE_CHILD_HOST)}
                                                isLoading={virtualizationLoading}
                                                isEnableLoading={enableWslLoading}
                                                isAgentPrivileged={host?.is_agent_privileged || false}
                                                rebootRequired={virtualizationStatus.reboot_required}
                                            />
                                        </Grid>
                                    )}

                                    {/* LXD Card - Linux hosts */}
                                    {host?.platform?.includes('Linux') && (
                                        <Grid size={{ xs: 12, sm: 6, md: 4, lg: 3 }}>
                                            <HypervisorStatusCard
                                                type="lxd"
                                                capabilities={virtualizationStatus.capabilities?.lxd}
                                                onEnable={handleInitializeLxd}
                                                onCreate={() => openCreateDialogWithType('lxd')}
                                                canEnable={canEnableLxd}
                                                canCreate={hasPermissionSync(SecurityRoles.CREATE_CHILD_HOST)}
                                                isLoading={virtualizationLoading}
                                                isEnableLoading={initializeLxdLoading}
                                                isAgentPrivileged={host?.is_agent_privileged || false}
                                            />
                                        </Grid>
                                    )}

                                    {/* KVM Card - Linux hosts */}
                                    {host?.platform?.includes('Linux') && (
                                        <Grid size={{ xs: 12, sm: 6, md: 4, lg: 3 }}>
                                            <HypervisorStatusCard
                                                type="kvm"
                                                capabilities={virtualizationStatus.capabilities?.kvm}
                                                onEnable={handleInitializeKvm}
                                                onCreate={() => openCreateDialogWithType('kvm')}
                                                onEnableModules={handleEnableKvmModules}
                                                onDisableModules={handleDisableKvmModules}
                                                canEnable={canEnableKvm}
                                                canCreate={hasPermissionSync(SecurityRoles.CREATE_CHILD_HOST)}
                                                isLoading={virtualizationLoading}
                                                isEnableLoading={initializeKvmLoading}
                                                isModulesLoading={kvmModulesLoading}
                                                isAgentPrivileged={host?.is_agent_privileged || false}
                                            />
                                        </Grid>
                                    )}

                                    {/* VMM Card - OpenBSD hosts */}
                                    {host?.platform?.includes('OpenBSD') && (
                                        <Grid size={{ xs: 12, sm: 6, md: 4, lg: 3 }}>
                                            <HypervisorStatusCard
                                                type="vmm"
                                                capabilities={virtualizationStatus.capabilities?.vmm}
                                                onEnable={handleInitializeVmm}
                                                onCreate={() => openCreateDialogWithType('vmm')}
                                                canEnable={canEnableVmm}
                                                canCreate={hasPermissionSync(SecurityRoles.CREATE_CHILD_HOST)}
                                                isLoading={virtualizationLoading}
                                                isEnableLoading={initializeVmmLoading}
                                                isAgentPrivileged={host?.is_agent_privileged || false}
                                            />
                                        </Grid>
                                    )}

                                    {/* bhyve Card - FreeBSD hosts */}
                                    {host?.platform?.includes('FreeBSD') && (
                                        <Grid size={{ xs: 12, sm: 6, md: 4, lg: 3 }}>
                                            <HypervisorStatusCard
                                                type="bhyve"
                                                capabilities={virtualizationStatus.capabilities?.bhyve}
                                                onEnable={handleInitializeBhyve}
                                                onDisable={handleDisableBhyve}
                                                onCreate={() => openCreateDialogWithType('bhyve')}
                                                canEnable={canEnableBhyve}
                                                canCreate={hasPermissionSync(SecurityRoles.CREATE_CHILD_HOST)}
                                                isLoading={virtualizationLoading}
                                                isEnableLoading={initializeBhyveLoading}
                                                isDisableLoading={disableBhyveLoading}
                                                isAgentPrivileged={host?.is_agent_privileged || false}
                                            />
                                        </Grid>
                                    )}
                                </Grid>
                            )}
                        </Box>
                    </Grid>

                    <Grid size={{ xs: 12 }}>
                        <Card>
                            <CardContent>
                                <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 2 }}>
                                    <Typography variant="h6" sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                                        <ComputerIcon />
                                        {t('hostDetail.childHostsTitle', 'Child Hosts')}
                                    </Typography>
                                    <Box sx={{ display: 'flex', gap: 1 }}>
                                        <Button
                                            variant="outlined"
                                            size="small"
                                            startIcon={childHostsRefreshRequested ? <CircularProgress size={16} /> : <RefreshIcon />}
                                            onClick={() => requestChildHostsRefresh()}
                                            disabled={childHostsRefreshRequested || childHostsLoading}
                                        >
                                            {t('hostDetail.refreshChildHosts', 'Refresh')}
                                        </Button>
                                    </Box>
                                </Box>

                                {/* Loading state */}
                                {childHostsLoading && (
                                    <Box sx={{ display: 'flex', justifyContent: 'center', py: 4 }}>
                                        <CircularProgress />
                                    </Box>
                                )}

                                {/* Empty state */}
                                {!childHostsLoading && childHosts.length === 0 && (
                                    <Box sx={{ textAlign: 'center', py: 4 }}>
                                        <ComputerIcon sx={{ fontSize: 64, color: 'text.secondary', mb: 2 }} />
                                        <Typography variant="h6" color="textSecondary" gutterBottom>
                                            {t('hostDetail.childHostsEmpty', 'No child hosts found')}
                                        </Typography>
                                        <Typography variant="body2" color="textSecondary">
                                            {/* Windows hosts - WSL messages */}
                                            {host?.platform?.includes('Windows') && getWslEmptyMessage()}
                                            {/* Linux hosts - LXD messages */}
                                            {host?.platform?.includes('Linux') && getLxdEmptyMessage()}
                                            {/* OpenBSD hosts - VMM messages */}
                                            {host?.platform?.includes('OpenBSD') && getVmmEmptyMessage()}
                                            {/* FreeBSD hosts - bhyve messages */}
                                            {host?.platform?.includes('FreeBSD') && getBhyveEmptyMessage()}
                                        </Typography>
                                    </Box>
                                )}

                                {/* Child hosts list */}
                                {!childHostsLoading && childHosts.length > 0 && (
                                    <TableContainer component={Paper} variant="outlined">
                                        <Table size="small">
                                            <TableHead>
                                                <TableRow>
                                                    <TableCell>{t('hostDetail.childHostName', 'Name')}</TableCell>
                                                    <TableCell>{t('hostDetail.childHostType', 'Type')}</TableCell>
                                                    <TableCell>{t('hostDetail.childHostDistribution', 'Distribution')}</TableCell>
                                                    <TableCell>{t('hostDetail.childHostHostname', 'Hostname')}</TableCell>
                                                    <TableCell>{t('hostDetail.childHostStatus', 'Status')}</TableCell>
                                                    <TableCell align="right">{t('hostDetail.childHostActions', 'Actions')}</TableCell>
                                                </TableRow>
                                            </TableHead>
                                            <TableBody>
                                                {childHosts.map((child) => {
                                                    const isOperationLoading = childHostOperationLoading[child.id] != null;
                                                    const currentOperation = childHostOperationLoading[child.id];
                                                    return (
                                                    <TableRow key={child.id}>
                                                        <TableCell>
                                                            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                                                                <ComputerIcon fontSize="small" />
                                                                {child.child_name}
                                                            </Box>
                                                        </TableCell>
                                                        <TableCell>
                                                            <Chip
                                                                label={child.child_type.toUpperCase()}
                                                                size="small"
                                                                color={child.child_type === 'wsl' ? 'primary' : 'default'}
                                                            />
                                                        </TableCell>
                                                        <TableCell>
                                                            {child.distribution}
                                                            {child.distribution_version && ` ${child.distribution_version}`}
                                                        </TableCell>
                                                        <TableCell>
                                                            {child.hostname || (child.status === 'running' ? '-' : t('hostDetail.childHostNotRunning', 'Not running'))}
                                                        </TableCell>
                                                        <TableCell>
                                                            <Box sx={{ display: 'flex', flexDirection: 'row', flexWrap: 'wrap', gap: 0.5, alignItems: 'center' }}>
                                                                {(() => {
                                                                    let statusLabel: string;
                                                                    if (child.status === 'creating') {
                                                                        statusLabel = t('hostDetail.childHostCreating', 'Creating...');
                                                                    } else if (child.status === 'running') {
                                                                        statusLabel = t('hostDetail.childHostRunning', 'Running');
                                                                    } else if (child.status === 'stopped') {
                                                                        statusLabel = t('hostDetail.childHostStopped', 'Stopped');
                                                                    } else if (child.status === 'error') {
                                                                        statusLabel = t('hostDetail.childHostError', 'Error');
                                                                    } else {
                                                                        statusLabel = child.status;
                                                                    }

                                                                    let statusColor: 'success' | 'default' | 'error' | 'info' | 'warning';
                                                                    if (child.status === 'running') {
                                                                        statusColor = 'success';
                                                                    } else if (child.status === 'stopped') {
                                                                        statusColor = 'default';
                                                                    } else if (child.status === 'error') {
                                                                        statusColor = 'error';
                                                                    } else if (child.status === 'creating') {
                                                                        statusColor = 'info';
                                                                    } else {
                                                                        statusColor = 'warning';
                                                                    }

                                                                    return (
                                                                        <Chip
                                                                            icon={child.status === 'creating' ? <CircularProgress size={12} color="inherit" /> : undefined}
                                                                            label={statusLabel}
                                                                            size="small"
                                                                            color={statusColor}
                                                                        />
                                                                    );
                                                                })()}
                                                                {/* Show error message if status is error */}
                                                                {child.status === 'error' && child.error_message && (
                                                                    <Typography variant="caption" color="error" sx={{ maxWidth: 200 }}>
                                                                        {child.error_message}
                                                                    </Typography>
                                                                )}
                                                                {/* Show "Pending Approval" if child is running but not linked to approved host */}
                                                                {child.status === 'running' && !child.child_host_id && (
                                                                    <Chip
                                                                        icon={<HelpOutlineIcon />}
                                                                        label={t('hostDetail.pendingApproval', 'Pending Approval')}
                                                                        size="small"
                                                                        color="info"
                                                                        variant="outlined"
                                                                    />
                                                                )}
                                                            </Box>
                                                        </TableCell>
                                                        <TableCell align="right">
                                                            <Box sx={{ display: 'flex', gap: 0.5, justifyContent: 'flex-end' }}>
                                                                {/* Start button - only show if stopped */}
                                                                {child.status === 'stopped' && (
                                                                    <IconButton
                                                                        size="small"
                                                                        color="success"
                                                                        onClick={() => handleChildHostStart(child)}
                                                                        disabled={isOperationLoading}
                                                                        title={t('hostDetail.startChildHost', 'Start')}
                                                                    >
                                                                        {currentOperation === 'start' ? <CircularProgress size={16} /> : <PlayArrowIcon fontSize="small" />}
                                                                    </IconButton>
                                                                )}
                                                                {/* Stop button - only show if running */}
                                                                {child.status === 'running' && (
                                                                    <IconButton
                                                                        size="small"
                                                                        color="warning"
                                                                        onClick={() => handleChildHostStop(child)}
                                                                        disabled={isOperationLoading}
                                                                        title={t('hostDetail.stopChildHost', 'Stop')}
                                                                    >
                                                                        {currentOperation === 'stop' ? <CircularProgress size={16} /> : <StopIcon fontSize="small" />}
                                                                    </IconButton>
                                                                )}
                                                                {/* Restart button - show for running or stopped */}
                                                                {(child.status === 'running' || child.status === 'stopped') && (
                                                                    <IconButton
                                                                        size="small"
                                                                        color="primary"
                                                                        onClick={() => handleChildHostRestart(child)}
                                                                        disabled={isOperationLoading}
                                                                        title={t('hostDetail.restartChildHost', 'Restart')}
                                                                    >
                                                                        {currentOperation === 'restart' ? <CircularProgress size={16} /> : <RestartAltIcon fontSize="small" />}
                                                                    </IconButton>
                                                                )}
                                                                {/* Delete/Cancel button - show for all statuses */}
                                                                <IconButton
                                                                    size="small"
                                                                    color="error"
                                                                    onClick={() => handleChildHostDeleteConfirm(child)}
                                                                    disabled={isOperationLoading}
                                                                    title={child.status === 'creating' || child.status === 'pending'
                                                                        ? t('hostDetail.cancelChildHost', 'Cancel')
                                                                        : t('hostDetail.deleteChildHost', 'Delete')}
                                                                >
                                                                    {currentOperation === 'delete' ? <CircularProgress size={16} /> : <DeleteIcon fontSize="small" />}
                                                                </IconButton>
                                                            </Box>
                                                        </TableCell>
                                                    </TableRow>
                                                    );
                                                })}
                                            </TableBody>
                                        </Table>
                                    </TableContainer>
                                )}
                            </CardContent>
                        </Card>
                    </Grid>
                </Grid>
            )}

            {/* Ubuntu Pro Tab */}
            {currentTabId === 'ubuntu-pro' && isUbuntu() && ubuntuProInfo?.available && (
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
                                                <Button
                                                    variant="outlined"
                                                    color="primary"
                                                    size="small"
                                                    disabled
                                                    startIcon={<CircularProgress size={16} />}
                                                >
                                                    {t('hostDetail.ubuntuProAttaching', 'Attaching...')}
                                                </Button>
                                            )}
                                            {ubuntuProDetaching && (
                                                <Button
                                                    variant="outlined"
                                                    color="warning"
                                                    size="small"
                                                    disabled
                                                    startIcon={<CircularProgress size={16} />}
                                                >
                                                    {t('hostDetail.ubuntuProDetaching', 'Detaching...')}
                                                </Button>
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
                                                                <TableCell>{formatUTCDate(ubuntuProInfo.expires)}</TableCell>
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
                                                        {(() => {
                                                            const sortedServices = [...ubuntuProInfo.services].sort((a, b) => {
                                                                // Sort: enabled first, then disabled, then n/a
                                                                const statusOrder = { 'enabled': 0, 'disabled': 1, 'n/a': 2 };
                                                                return statusOrder[a.status as keyof typeof statusOrder] - statusOrder[b.status as keyof typeof statusOrder];
                                                            });
                                                            return sortedServices.map((service) => (
                                                            <Grid size={{ xs: 12 }} key={service.name}>
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
                                                                                    label={getEditedServiceLabel(service.name, service.status)}
                                                                                />
                                                                            ) : (
                                                                                <Chip
                                                                                    label={getServiceStatusLabel(service.status)}
                                                                                    color={getServiceStatusColor(service.status)}
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
                                                        ));
                                                        })()}
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
            {currentTabId === 'diagnostics' && (
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
                slotProps={{
                    paper: { sx: { backgroundColor: 'grey.900' } }
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
                onClose={() => { setRebootConfirmOpen(false); setRebootPreCheckData(null); }}
                aria-labelledby="reboot-dialog-title"
                aria-describedby="reboot-dialog-description"
                maxWidth="sm"
                fullWidth
            >
                <DialogTitle id="reboot-dialog-title">
                    {t('hosts.confirmReboot', 'Confirm System Reboot')}
                </DialogTitle>
                <DialogContent>
                    {rebootPreCheckLoading && (
                        <Box sx={{ display: 'flex', justifyContent: 'center', py: 2 }}>
                            <CircularProgress size={24} />
                        </Box>
                    )}
                    {!rebootPreCheckLoading && rebootPreCheckData?.has_running_children && (
                        <>
                            {rebootPreCheckData.has_container_engine ? (
                                <Alert severity="info" sx={{ mb: 2 }}>
                                    {t('hosts.rebootOrchestration.orchestratedInfo', 'This host has {{count}} running child host(s). SysManage will safely stop them before rebooting and automatically restart them afterward.', { count: rebootPreCheckData.running_count })}
                                </Alert>
                            ) : (
                                <Alert severity="warning" sx={{ mb: 2 }}>
                                    {t('hosts.rebootOrchestration.ungracefulWarning', 'This host has {{count}} running child host(s) that will be ungracefully terminated during reboot. Upgrade to SysManage Professional+ for orchestrated safe reboot.', { count: rebootPreCheckData.running_count })}
                                </Alert>
                            )}
                            <Typography variant="subtitle2" sx={{ mb: 1 }}>
                                {t('hosts.rebootOrchestration.runningChildren', 'Running child hosts:')}
                            </Typography>
                            <Table size="small" sx={{ mb: 2 }}>
                                <TableHead>
                                    <TableRow>
                                        <TableCell>{t('hosts.rebootOrchestration.childName', 'Name')}</TableCell>
                                        <TableCell>{t('hosts.rebootOrchestration.childType', 'Type')}</TableCell>
                                    </TableRow>
                                </TableHead>
                                <TableBody>
                                    {rebootPreCheckData.running_children.map((child) => (
                                        <TableRow key={child.id}>
                                            <TableCell>{child.child_name}</TableCell>
                                            <TableCell>
                                                <Chip label={child.child_type.toUpperCase()} size="small" />
                                            </TableCell>
                                        </TableRow>
                                    ))}
                                </TableBody>
                            </Table>
                            <Typography id="reboot-dialog-description" variant="body2" color="text.secondary">
                                {rebootPreCheckData.has_container_engine
                                    ? t('hosts.rebootOrchestration.proceedOrchestrated', 'Click "Orchestrated Reboot" to safely reboot {{hostname}}.', { hostname: host?.fqdn })
                                    : t('hosts.rebootOrchestration.proceedAnyway', 'Click "Reboot Anyway" to reboot {{hostname}} without stopping child hosts first.', { hostname: host?.fqdn })
                                }
                            </Typography>
                        </>
                    )}
                    {!rebootPreCheckLoading && !rebootPreCheckData?.has_running_children && (
                        <Typography id="reboot-dialog-description">
                            {t('hosts.confirmRebootMessage', 'Are you sure you want to reboot {{hostname}}? The system will be unavailable for a few minutes.', { hostname: host?.fqdn })}
                        </Typography>
                    )}
                </DialogContent>
                <DialogActions>
                    <Button onClick={() => { setRebootConfirmOpen(false); setRebootPreCheckData(null); }}>
                        {t('common.cancel', 'Cancel')}
                    </Button>
                    {!rebootPreCheckLoading && (
                        <Button onClick={handleRebootConfirm} color="warning" variant="contained">
                            {(() => {
                                if (!rebootPreCheckData?.has_running_children) {
                                    return t('hosts.reboot', 'Reboot');
                                }
                                if (rebootPreCheckData.has_container_engine) {
                                    return t('hosts.rebootOrchestration.orchestratedRebootButton', 'Orchestrated Reboot');
                                }
                                return t('hosts.rebootOrchestration.rebootAnywayButton', 'Reboot Anyway');
                            })()}
                        </Button>
                    )}
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

            {/* Edit Hostname Dialog */}
            <Dialog
                open={hostnameEditOpen}
                onClose={() => setHostnameEditOpen(false)}
                aria-labelledby="hostname-edit-dialog-title"
                maxWidth="sm"
                fullWidth
            >
                <DialogTitle id="hostname-edit-dialog-title">
                    {t('hostDetail.editHostname', 'Edit Hostname')}
                </DialogTitle>
                <DialogContent>
                    <TextField
                        autoFocus
                        margin="dense"
                        id="hostname"
                        label={t('hostDetail.hostname', 'Hostname')}
                        type="text"
                        fullWidth
                        variant="outlined"
                        value={newHostname}
                        onChange={(e) => setNewHostname(e.target.value)}
                        helperText={t('hostDetail.hostnameHelp', 'Enter a short hostname or fully qualified domain name (FQDN)')}
                        disabled={hostnameEditLoading}
                    />
                </DialogContent>
                <DialogActions>
                    <Button onClick={() => setHostnameEditOpen(false)} disabled={hostnameEditLoading}>
                        {t('common.cancel', 'Cancel')}
                    </Button>
                    <Button
                        onClick={handleHostnameChange}
                        color="primary"
                        variant="contained"
                        disabled={hostnameEditLoading || !newHostname.trim()}
                    >
                        {hostnameEditLoading ? <CircularProgress size={24} /> : t('common.save', 'Save')}
                    </Button>
                </DialogActions>
            </Dialog>

            {/* Delete Confirmation Dialog */}
            <Dialog
                open={deleteConfirmOpen}
                onClose={handleCancelDelete}
                maxWidth="sm"
                fullWidth
                slotProps={{
                    paper: { sx: { backgroundColor: 'grey.900' } }
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

            {/* Delete/Cancel Child Host Confirmation Dialog */}
            <Dialog
                open={deleteChildHostConfirmOpen}
                onClose={handleChildHostDeleteCancel}
                maxWidth="sm"
                fullWidth
                slotProps={{
                    paper: { sx: { backgroundColor: 'grey.900' } }
                }}
            >
                <DialogTitle sx={{ fontWeight: 'bold', fontSize: '1.25rem', display: 'flex', alignItems: 'center', gap: 1 }}>
                    <WarningIcon color={childHostToDelete?.status === 'creating' || childHostToDelete?.status === 'pending' ? 'warning' : 'error'} />
                    {childHostToDelete?.status === 'creating' || childHostToDelete?.status === 'pending'
                        ? t('hostDetail.cancelChildHostConfirmTitle', 'Cancel Child Host Creation')
                        : t('hostDetail.deleteChildHostConfirmTitle', 'Delete Child Host')}
                </DialogTitle>
                <DialogContent>
                    {childHostToDelete?.status === 'creating' || childHostToDelete?.status === 'pending' ? (
                        <>
                            <Alert severity="warning" sx={{ mb: 2 }}>
                                {t('hostDetail.cancelChildHostWarning', 'This will cancel the child host creation.')}
                            </Alert>
                            <Typography variant="body1" sx={{ mb: 2 }}>
                                {t('hostDetail.cancelChildHostMessage', 'Are you sure you want to cancel the creation of "{{name}}"?', { name: childHostToDelete?.child_name })}
                            </Typography>
                            <Typography variant="body2" color="textSecondary">
                                {t('hostDetail.cancelChildHostNote', 'The creation record will be removed from the database. If the agent is currently creating this child host, the partial installation may need to be cleaned up manually.')}
                            </Typography>
                        </>
                    ) : (
                        <>
                            <Alert severity="error" sx={{ mb: 2 }}>
                                {t('hostDetail.deleteChildHostWarning', 'This action is irreversible!')}
                            </Alert>
                            <Typography variant="body1" sx={{ mb: 2 }}>
                                {t('hostDetail.deleteChildHostMessage', 'Are you sure you want to delete the child host "{{name}}"?', { name: childHostToDelete?.child_name })}
                            </Typography>
                            <Typography variant="body2" color="textSecondary">
                                {t('hostDetail.deleteChildHostDataWarning', 'This will permanently delete the virtual machine and ALL of its data, including:')}
                            </Typography>
                            <Box component="ul" sx={{ pl: 2, mt: 1, color: 'text.secondary' }}>
                                <li>{t('hostDetail.deleteChildHostDataItem1', 'All files and user data')}</li>
                                <li>{t('hostDetail.deleteChildHostDataItem2', 'Installed applications')}</li>
                                <li>{t('hostDetail.deleteChildHostDataItem3', 'System configuration')}</li>
                            </Box>
                        </>
                    )}
                </DialogContent>
                <DialogActions>
                    <Button onClick={handleChildHostDeleteCancel}>
                        {t('common.cancel', 'Cancel')}
                    </Button>
                    <Button onClick={handleChildHostDelete} color={childHostToDelete?.status === 'creating' || childHostToDelete?.status === 'pending' ? 'warning' : 'error'} variant="contained">
                        {childHostToDelete?.status === 'creating' || childHostToDelete?.status === 'pending'
                            ? t('hostDetail.cancelChildHostConfirmButton', 'Cancel Creation')
                            : t('hostDetail.deleteChildHostConfirmButton', 'Delete Permanently')}
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
                    {(() => {
                        if (diagnosticDetailLoading) {
                            return (
                                <Box sx={{ display: 'flex', justifyContent: 'center', py: 4 }}>
                                    <CircularProgress />
                                </Box>
                            );
                        }
                        if (selectedDiagnostic) {
                            return (
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

                                                const sectionTitle = t(`hostDetail.${key}`, key.replaceAll('_', ' ').replaceAll(/\b\w/g, l => l.toUpperCase()));

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
                            );
                        }
                        return null;
                    })()}
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

            {/* Ubuntu Pro Token Dialog - only shown when no master key is configured */}
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

            {/* Package Installation Dialog */}
            <Dialog
                open={packageInstallDialogOpen}
                onClose={handleClosePackageDialog}
                maxWidth="md"
                fullWidth
                slotProps={{
                    paper: { sx: { backgroundColor: 'grey.900', minHeight: '500px' } }
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
                    {t('hostDetail.installationLogTitle', 'Installation Log')} - {selectedInstallationLog?.package_names}
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

            {/* Reboot Orchestration Progress Banner */}
            {rebootOrchestrationStatus && rebootOrchestrationId && (
                <Snackbar
                    open={true}
                    anchorOrigin={{ vertical: 'top', horizontal: 'center' }}
                >
                    <Alert severity="info" sx={{ minWidth: 350 }}>
                        <Typography variant="subtitle2">
                            {t('hosts.rebootOrchestration.inProgress', 'Orchestrated Reboot in Progress')}
                        </Typography>
                        <Typography variant="body2">
                            {rebootOrchestrationStatus.status === 'shutting_down' && t('hosts.rebootOrchestration.statusShuttingDown', 'Stopping child hosts...')}
                            {rebootOrchestrationStatus.status === 'rebooting' && t('hosts.rebootOrchestration.statusRebooting', 'Rebooting host, waiting for reconnect...')}
                            {rebootOrchestrationStatus.status === 'pending_restart' && t('hosts.rebootOrchestration.statusPendingRestart', 'Host reconnected, preparing to restart children...')}
                            {rebootOrchestrationStatus.status === 'restarting' && t('hosts.rebootOrchestration.statusRestarting', 'Restarting child hosts...')}
                        </Typography>
                        <LinearProgress sx={{ mt: 1 }} />
                    </Alert>
                </Snackbar>
            )}

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
                            slotProps={{
                                input: {
                                    startAdornment: (
                                        <InputAdornment position="start">
                                            <SearchIcon />
                                        </InputAdornment>
                                    ),
                                },
                            }}
                            onKeyDown={(e) => {
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
                            slotProps={{
                                input: {
                                    startAdornment: (
                                        <InputAdornment position="start">
                                            <SearchIcon />
                                        </InputAdornment>
                                    ),
                                },
                            }}
                            onKeyDown={(e) => {
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
                            <Box sx={{ height: 400 }}>
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
                                    sx={{
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
                            </Box>
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
                hostPlatform={host?.platform || ''}
            />

            {/* Add Host Account Modal */}
            <AddHostAccountModal
                open={addUserModalOpen}
                onClose={() => setAddUserModalOpen(false)}
                hostId={hostId || ''}
                hostPlatform={host?.platform || ''}
                onSuccess={() => {
                    // Refresh user accounts after successful creation
                    if (hostId) {
                        doGetHostUsers(hostId).then(setUserAccounts).catch(console.error);
                    }
                }}
            />

            {/* Add Host Group Modal */}
            <AddHostGroupModal
                open={addGroupModalOpen}
                onClose={() => setAddGroupModalOpen(false)}
                hostId={hostId || ''}
                hostPlatform={host?.platform || ''}
                onSuccess={() => {
                    // Refresh groups after successful creation
                    if (hostId) {
                        doGetHostGroups(hostId).then(setUserGroups).catch(console.error);
                    }
                }}
            />

            {/* Delete User Confirmation Dialog */}
            <Dialog
                open={deleteUserConfirmOpen}
                onClose={handleDeleteUserCancel}
                maxWidth="sm"
                fullWidth
            >
                <DialogTitle>
                    <Typography variant="h6" component="div">
                        {t('hostAccount.confirmDeleteTitle', 'Delete User Account')}
                    </Typography>
                </DialogTitle>
                <DialogContent>
                    <Typography variant="body1" sx={{ mb: 2 }}>
                        {t('hostAccount.confirmDelete', 'Are you sure you want to delete the user account "{{username}}"? This action cannot be undone.', { username: userToDelete?.username || '' })}
                    </Typography>
                    <FormControlLabel
                        control={
                            <Checkbox
                                checked={deleteDefaultGroup}
                                onChange={(e) => setDeleteDefaultGroup(e.target.checked)}
                                color="primary"
                            />
                        }
                        label={t('hostAccount.deleteDefaultGroup', 'Also delete the user\'s default group (if it exists and has the same name)')}
                    />
                </DialogContent>
                <DialogActions>
                    <Button onClick={handleDeleteUserCancel} disabled={deletingUser}>
                        {t('common.cancel', 'Cancel')}
                    </Button>
                    <Button
                        variant="contained"
                        color="error"
                        onClick={handleDeleteUserConfirm}
                        disabled={deletingUser}
                        startIcon={deletingUser ? <CircularProgress size={16} /> : <DeleteIcon />}
                    >
                        {t('common.delete', 'Delete')}
                    </Button>
                </DialogActions>
            </Dialog>

            {/* Delete Group Confirmation Dialog */}
            <Dialog
                open={deleteGroupConfirmOpen}
                onClose={handleDeleteGroupCancel}
                maxWidth="sm"
                fullWidth
            >
                <DialogTitle>
                    <Typography variant="h6" component="div">
                        {t('hostGroup.confirmDeleteTitle', 'Delete Group')}
                    </Typography>
                </DialogTitle>
                <DialogContent>
                    <Typography variant="body1">
                        {t('hostGroup.confirmDelete', 'Are you sure you want to delete the group "{{groupName}}"? This action cannot be undone.', { groupName: groupToDelete?.group_name || '' })}
                    </Typography>
                </DialogContent>
                <DialogActions>
                    <Button onClick={handleDeleteGroupCancel} disabled={deletingGroup}>
                        {t('common.cancel', 'Cancel')}
                    </Button>
                    <Button
                        variant="contained"
                        color="error"
                        onClick={handleDeleteGroupConfirm}
                        disabled={deletingGroup}
                        startIcon={deletingGroup ? <CircularProgress size={16} /> : <DeleteIcon />}
                    >
                        {t('common.delete', 'Delete')}
                    </Button>
                </DialogActions>
            </Dialog>

            {/* Create Child Host Dialog */}
            <Dialog
                open={createChildHostOpen}
                onClose={() => {
                    if (!createChildHostLoading) {
                        setChildHostFormValidated(false);
                        setCreateChildHostOpen(false);
                    }
                }}
                maxWidth="sm"
                fullWidth
            >
                <DialogTitle sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    {getCreateChildHostTitle()}
                    <IconButton
                        onClick={() => {
                            setChildHostFormValidated(false);
                            setCreateChildHostOpen(false);
                        }}
                        disabled={createChildHostLoading}
                    >
                        <CloseIcon />
                    </IconButton>
                </DialogTitle>
                <DialogContent>
                    <Box sx={{ mt: 2 }}>
                        <FormControl
                            fullWidth
                            sx={{ mb: 2 }}
                            error={childHostFormValidated && !childHostFormData.distribution}
                        >
                            <InputLabel id="distribution-select-label">
                                {childHostFormData.childType === 'lxd'
                                    ? t('hostDetail.childHostImageLabel', 'Image')
                                    : t('hostDetail.childHostDistributionLabel', 'Distribution')}
                            </InputLabel>
                            <Select
                                labelId="distribution-select-label"
                                value={childHostFormData.distribution}
                                label={childHostFormData.childType === 'lxd'
                                    ? t('hostDetail.childHostImageLabel', 'Image')
                                    : t('hostDetail.childHostDistributionLabel', 'Distribution')}
                                onChange={(e) => setChildHostFormData({
                                    ...childHostFormData,
                                    distribution: e.target.value
                                })}
                                disabled={createChildHostLoading}
                                error={childHostFormValidated && !childHostFormData.distribution}
                            >
                                {availableDistributions.map((dist) => (
                                    <MenuItem key={dist.id} value={dist.install_identifier}>
                                        {dist.display_name}
                                    </MenuItem>
                                ))}
                            </Select>
                            {childHostFormValidated && !childHostFormData.distribution && (
                                <FormHelperText>
                                    {childHostFormData.childType === 'lxd'
                                        ? t('hostDetail.childHostImageRequired', 'Please select an image')
                                        : t('hostDetail.childHostDistributionRequired', 'Please select a distribution')}
                                </FormHelperText>
                            )}
                        </FormControl>

                        {/* Container name field for LXD */}
                        {childHostFormData.childType === 'lxd' && (
                            <TextField
                                fullWidth
                                label={t('hostDetail.childHostContainerNameLabel', 'Container Name')}
                                value={childHostFormData.containerName}
                                onChange={(e) => setChildHostFormData({
                                    ...childHostFormData,
                                    containerName: e.target.value.toLowerCase().replaceAll(/[^a-z0-9-]/g, '')
                                })}
                                disabled={createChildHostLoading}
                                sx={{ mb: 2 }}
                                helperText={t('hostDetail.childHostContainerNameHelp', 'Name for the LXD container (lowercase, alphanumeric, hyphens)')}
                            />
                        )}

                        <TextField
                            fullWidth
                            label={t('hostDetail.childHostHostnameLabel', 'Hostname')}
                            value={childHostFormData.hostname}
                            onChange={(e) => {
                                const newHostname = e.target.value;
                                // For VMM, KVM, and bhyve, auto-compute vmName from short hostname
                                const shortName = newHostname.split('.')[0].toLowerCase().replaceAll(/[^a-z0-9-]/g, '');
                                setChildHostFormData({
                                    ...childHostFormData,
                                    hostname: newHostname,
                                    vmName: (childHostFormData.childType === 'vmm' || childHostFormData.childType === 'kvm' || childHostFormData.childType === 'bhyve') ? shortName : childHostFormData.vmName
                                });
                            }}
                            disabled={createChildHostLoading}
                            sx={{ mb: 1 }}
                            helperText={t('hostDetail.childHostHostnameHelp', 'Enter hostname (e.g., "myhost") or FQDN (e.g., "myhost.example.com")')}
                        />

                        <TextField
                            fullWidth
                            label={t('hostDetail.childHostFqdnLabel', 'Fully Qualified Domain Name')}
                            value={computedFqdn}
                            disabled
                            sx={{ mb: 2 }}
                            slotProps={{
                                input: {
                                    readOnly: true,
                                },
                            }}
                            helperText={(() => {
                                if (childHostFormData.childType === 'lxd') {
                                    return t('hostDetail.childHostFqdnHelpLxd', 'This FQDN will be used for the LXD container');
                                }
                                if (childHostFormData.childType === 'vmm') {
                                    return t('hostDetail.childHostFqdnHelpVmm', 'This FQDN will be used for the VMM virtual machine');
                                }
                                if (childHostFormData.childType === 'kvm') {
                                    return t('hostDetail.childHostFqdnHelpKvm', 'This FQDN will be used for the KVM virtual machine');
                                }
                                if (childHostFormData.childType === 'bhyve') {
                                    return t('hostDetail.childHostFqdnHelpBhyve', 'This FQDN will be used for the bhyve virtual machine');
                                }
                                return t('hostDetail.childHostFqdnHelp', 'This FQDN will be used for the WSL instance');
                            })()}
                        />

                        {/* VM name field for VMM, KVM, and bhyve - read-only, derived from hostname */}
                        {(childHostFormData.childType === 'vmm' || childHostFormData.childType === 'kvm' || childHostFormData.childType === 'bhyve') && (
                            <TextField
                                fullWidth
                                label={t('hostDetail.childHostVmNameLabel', 'VM Name')}
                                value={childHostFormData.vmName}
                                disabled
                                sx={{ mb: 2 }}
                                slotProps={{
                                    input: {
                                        readOnly: true,
                                    },
                                }}
                                helperText={t('hostDetail.childHostVmNameHelpReadonly', 'VM name is derived from the hostname')}
                            />
                        )}

                        {/* Root password fields for VMM - before username (matches OpenBSD installer order) */}
                        {childHostFormData.childType === 'vmm' && (
                            <>
                                <TextField
                                    fullWidth
                                    required
                                    label={t('hostDetail.childHostRootPassword', 'Root Password')}
                                    type="password"
                                    value={childHostFormData.rootPassword}
                                    onChange={(e) => setChildHostFormData({
                                        ...childHostFormData,
                                        rootPassword: e.target.value
                                    })}
                                    disabled={createChildHostLoading}
                                    helperText={t('hostDetail.childHostRootPasswordHelp', 'Password for the root user on the OpenBSD VM')}
                                    sx={{ mb: 2 }}
                                />
                                <TextField
                                    fullWidth
                                    required
                                    label={t('hostDetail.childHostConfirmRootPassword', 'Confirm Root Password')}
                                    type="password"
                                    value={childHostFormData.confirmRootPassword}
                                    onChange={(e) => setChildHostFormData({
                                        ...childHostFormData,
                                        confirmRootPassword: e.target.value
                                    })}
                                    disabled={createChildHostLoading}
                                    error={childHostFormData.rootPassword !== childHostFormData.confirmRootPassword && childHostFormData.confirmRootPassword !== ''}
                                    helperText={
                                        childHostFormData.rootPassword !== childHostFormData.confirmRootPassword && childHostFormData.confirmRootPassword !== ''
                                            ? t('hostDetail.childHostRootPasswordMismatch', 'Root passwords do not match')
                                            : ''
                                    }
                                    sx={{ mb: 2 }}
                                />
                            </>
                        )}

                        <TextField
                            fullWidth
                            label={t('hostDetail.childHostUsernameLabel', 'Username')}
                            value={childHostFormData.username}
                            onChange={(e) => setChildHostFormData({
                                ...childHostFormData,
                                username: e.target.value
                            })}
                            disabled={createChildHostLoading}
                            sx={{ mb: 2 }}
                            helperText={t('hostDetail.childHostUsernameHelp', 'The non-root user to create')}
                        />

                        <TextField
                            fullWidth
                            type="password"
                            label={t('hostDetail.childHostPasswordLabel', 'Password')}
                            value={childHostFormData.password}
                            onChange={(e) => setChildHostFormData({
                                ...childHostFormData,
                                password: e.target.value
                            })}
                            disabled={createChildHostLoading}
                            sx={{ mb: 2 }}
                        />

                        <TextField
                            fullWidth
                            type="password"
                            label={t('hostDetail.childHostConfirmPasswordLabel', 'Confirm Password')}
                            value={childHostFormData.confirmPassword}
                            onChange={(e) => setChildHostFormData({
                                ...childHostFormData,
                                confirmPassword: e.target.value
                            })}
                            disabled={createChildHostLoading}
                            error={childHostFormData.password !== childHostFormData.confirmPassword && childHostFormData.confirmPassword !== ''}
                            helperText={
                                childHostFormData.password !== childHostFormData.confirmPassword && childHostFormData.confirmPassword !== ''
                                    ? t('hostDetail.childHostPasswordMismatch', 'Passwords do not match')
                                    : ''
                            }
                            sx={{ mb: 2 }}
                        />

                        {/* Auto-approve checkbox */}
                        <FormControlLabel
                            control={
                                <Checkbox
                                    checked={childHostFormData.autoApprove}
                                    onChange={(e) => setChildHostFormData({
                                        ...childHostFormData,
                                        autoApprove: e.target.checked
                                    })}
                                    disabled={createChildHostLoading}
                                />
                            }
                            label={t('hostDetail.childHostAutoApprove', 'Auto-approve when connected')}
                            sx={{ mb: 2 }}
                        />
                        <Typography variant="caption" color="textSecondary" sx={{ display: 'block', mt: -1, mb: 2, ml: 4 }}>
                            {t('hostDetail.childHostAutoApproveHelp', 'When enabled, the host will be automatically approved when it connects to the server.')}
                        </Typography>

                        {/* Progress indicator during creation */}
                        {createChildHostLoading && childHostCreationProgress && (
                            <Box sx={{ display: 'flex', alignItems: 'center', gap: 2, mt: 2 }}>
                                <CircularProgress size={20} />
                                <Typography variant="body2" color="textSecondary">
                                    {childHostCreationProgress}
                                </Typography>
                            </Box>
                        )}
                    </Box>
                </DialogContent>
                <DialogActions>
                    <Button
                        onClick={() => {
                            setChildHostFormValidated(false);
                            setCreateChildHostOpen(false);
                        }}
                        disabled={createChildHostLoading}
                    >
                        {t('common.cancel', 'Cancel')}
                    </Button>
                    <Button
                        variant="contained"
                        onClick={handleCreateChildHost}
                        disabled={createChildHostLoading}
                        startIcon={createChildHostLoading ? <CircularProgress size={16} /> : <AddIcon />}
                    >
                        {t('hostDetail.createChildHostButton', 'Create')}
                    </Button>
                </DialogActions>
            </Dialog>
        </Box>
    );
};

export default HostDetail;