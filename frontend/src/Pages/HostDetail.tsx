// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

import { useNavigate, useParams } from "react-router-dom";
import React, { useState, useCallback, useMemo } from 'react';
import { Box, Typography, Button, CircularProgress, Paper } from '@mui/material';
import ArrowBackIcon from '@mui/icons-material/ArrowBack';
import ComputerIcon from '@mui/icons-material/Computer';
import InfoIcon from '@mui/icons-material/Info';
import MemoryIcon from '@mui/icons-material/Memory';
import DvrIcon from '@mui/icons-material/Dvr';
import SecurityIcon from '@mui/icons-material/Security';
import AppsIcon from '@mui/icons-material/Apps';
import MedicalServicesIcon from '@mui/icons-material/MedicalServices';
import VerifiedUserIcon from '@mui/icons-material/VerifiedUser';
import HistoryIcon from '@mui/icons-material/History';
import CertificateIcon from '@mui/icons-material/AdminPanelSettings';
import AssignmentIcon from '@mui/icons-material/Assignment';
import SourceIcon from '@mui/icons-material/Source';
import ShieldIcon from '@mui/icons-material/Shield';
import RuleIcon from '@mui/icons-material/Rule';

import { useTranslation } from 'react-i18next';

import { SysManageHost, StorageDevice as StorageDeviceType, NetworkInterface as NetworkInterfaceType, UserAccount, UserGroup, UbuntuProInfo, doGetHostUsers, doGetHostGroups } from '../Services/hosts';
import { SysManageUser } from '../Services/users';

import { usePlugins } from '../plugins';

import HostDetailHeader from '../Components/HostDetail/HostDetailHeader';
import HostDetailNavRail from '../Components/HostDetail/HostDetailNavRail';
import HostDetailTabContent from '../Components/HostDetail/HostDetailTabContent';
import HostConfirmDialogs from '../Components/HostDetail/HostConfirmDialogs';
import HostActionDialogs from '../Components/HostDetail/HostActionDialogs';
import CreateChildHostDialog from '../Components/HostDetail/CreateChildHostDialog';
import { useHostPermissions } from '../Components/HostDetail/useHostPermissions';
import { useHostSnackbar } from '../Components/HostDetail/useHostSnackbar';
import { useHostAntivirus } from '../Components/HostDetail/useHostAntivirus';
import { useHostUbuntuPro } from '../Components/HostDetail/useHostUbuntuPro';
import { useHostTags } from '../Components/HostDetail/useHostTags';
import { useHostObservability } from '../Components/HostDetail/useHostObservability';
import { useChildHosts } from '../Components/HostDetail/useChildHosts';
import { useHostSoftware } from '../Components/HostDetail/useHostSoftware';
import { useHostAccessManagement } from '../Components/HostDetail/useHostAccessManagement';
import { useHostRolesAndCerts } from '../Components/HostDetail/useHostRolesAndCerts';
import { useHostLifecycle } from '../Components/HostDetail/useHostLifecycle';
import { useHostInventoryFilters } from '../Components/HostDetail/useHostInventoryFilters';
import { useHostData } from '../Components/HostDetail/useHostData';
import { useHostTabNavigation } from '../Components/HostDetail/useHostTabNavigation';
import { useCertificateGrid } from '../Components/HostDetail/useCertificateGrid';

// Large page component that coordinates host details, hardware info, software, virtualization, and multiple interactive features

const HostDetail = () => { // NOSONAR
    const { hostId } = useParams<{ hostId: string }>();
    const [host, setHost] = useState<SysManageHost | null>(null);
    const [storageDevices, setStorageDevices] = useState<StorageDeviceType[]>([]);
    const [networkInterfaces, setNetworkInterfaces] = useState<NetworkInterfaceType[]>([]);
    const [userAccounts, setUserAccounts] = useState<UserAccount[]>([]);
    const [userGroups, setUserGroups] = useState<UserGroup[]>([]);
    const [ubuntuProInfo, setUbuntuProInfo] = useState<UbuntuProInfo | null>(null);
    const [loading, setLoading] = useState<boolean>(true);
    const [error, setError] = useState<string | null>(null);
    const [hasAntivirusOsDefault, setHasAntivirusOsDefault] = useState<boolean>(false);
    const [licenseModules, setLicenseModules] = useState<string[]>([]);
    const [licenseFeatures, setLicenseFeatures] = useState<string[]>([]);

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

    // Check if host supports child hosts (virtualization).
    // Child host management is a Professional+ feature, gated by the
    // ``container_engine`` license module — without it the tab and its
    // panel must not render in OSS builds.
    const supportsChildHosts = useCallback(() => {
        if (!host?.platform) return false;
        if (!licenseModules.includes('container_engine')) return false;
        // Child hosts (VMs, containers, WSL instances) cannot have their own child hosts
        if (host.parent_host_id) return false;
        const platform = host.platform || '';
        // Windows hosts support WSL, Linux hosts support LXD/KVM, OpenBSD hosts support VMM, FreeBSD hosts support bhyve
        return platform.includes('Windows') || platform.includes('Linux') || platform.includes('OpenBSD') || platform.includes('FreeBSD');
    }, [host, licenseModules]);

    // Check if host is running Ubuntu (for Ubuntu Pro feature)
    const isUbuntu = useCallback(() => {
        if (!host?.platform && !host?.platform_release) return false;
        const platform = (host.platform || '').toLowerCase();
        const platformRelease = (host.platform_release || '').toLowerCase();
        return platform.includes('ubuntu') || platformRelease.includes('ubuntu');
    }, [host]);


    const [currentTab, setCurrentTab] = useState<number>(0);

    const [storageFilter, setStorageFilter] = useState<'all' | 'physical' | 'logical'>('physical');
    const [networkFilter, setNetworkFilter] = useState<'all' | 'active' | 'inactive'>('active');
    const [userFilter, setUserFilter] = useState<'all' | 'system' | 'regular'>('all');
    const [groupFilter, setGroupFilter] = useState<'all' | 'system' | 'regular'>('regular');
    const [expandedUserGroups, setExpandedUserGroups] = useState<Set<string>>(new Set());
    const [expandedGroupUsers, setExpandedGroupUsers] = useState<Set<string>>(new Set());

    // Tag-related state

    // Current user state
    const [currentUser, setCurrentUser] = useState<SysManageUser | null>(null);
    const navigate = useNavigate();
    const { t } = useTranslation();

    // Host RBAC permissions (resolved once on mount).
    const {
        canEditTags,
        canEditHostname,
        canStopService,
        canStartService,
        canRestartService,
        canAddPackage,
        canDeploySshKey,
        canDeployCertificate,
        canAttachUbuntuPro,
        canDetachUbuntuPro,
        canDeployAntivirus,
        canEnableAntivirus,
        canDisableAntivirus,
        canRemoveAntivirus,
        canAddHostAccount,
        canAddHostGroup,
        canDeleteHostAccount,
        canDeleteHostGroup,
        canEnableWsl,
        canEnableLxd,
        canEnableKvm,
        canEnableVmm,
        canEnableBhyve,
    } = useHostPermissions();

    const {
        snackbarOpen,
        snackbarMessage,
        snackbarSeverity,
        setSnackbarOpen,
        setSnackbarMessage,
        setSnackbarSeverity,
        handleCloseSnackbar,
    } = useHostSnackbar();

    const {
        antivirusRefreshTrigger,
        handleDeployAntivirus,
        handleEnableAntivirus,
        handleDisableAntivirus,
        handleRemoveAntivirus,
    } = useHostAntivirus({ host, t, setSnackbarMessage, setSnackbarSeverity, setSnackbarOpen });

    const {
        ubuntuProTokenDialog,
        ubuntuProToken,
        setUbuntuProToken,
        ubuntuProAttaching,
        ubuntuProDetaching,
        ubuntuProDetachConfirmOpen,
        servicesEditMode,
        editedServices,
        servicesSaving,
        servicesMessage,
        handleUbuntuProAttach,
        handleUbuntuProDetach,
        handleConfirmUbuntuProDetach,
        handleCancelUbuntuProDetach,
        handleUbuntuProTokenSubmit,
        handleUbuntuProTokenCancel,
        getEditedServiceLabel,
        handleServicesEditToggle,
        handleServiceToggle,
        handleServicesSave,
    } = useHostUbuntuPro({ hostId, host, ubuntuProInfo, setUbuntuProInfo, isUbuntu, t, setSnackbarMessage, setSnackbarSeverity, setSnackbarOpen });

    const {
        hostTags,
        availableTags,
        selectedTagToAdd,
        setSelectedTagToAdd,
        handleAddTag,
        handleRemoveTag,
    } = useHostTags({ hostId, t, setSnackbarMessage, setSnackbarSeverity, setSnackbarOpen });

    const {
        certificateFilter,
        setCertificateFilter,
        certificatePaginationModel,
        setCertificatePaginationModel,
        certificateSearchTerm,
        setCertificateSearchTerm,
        hiddenCertificatesColumns,
        setHiddenCertificatesColumns,
        resetCertificatesPreferences,
        getCertificatesColumnVisibilityModel,
        safePageSizeOptions,
    } = useCertificateGrid();





    // Plugin system: get registered host detail tabs
    const { hostDetailTabs: pluginTabs } = usePlugins();

    // Filter plugin tabs based on the license.  A tab is shown only when BOTH
    // its module gate (is the engine bundle licensed?) AND its feature gate
    // (is this specific capability licensed?) pass.  The feature gate is what
    // hides an Enterprise capability that ships inside a Professional module
    // (e.g. the ``fips_mode`` tab inside ``compliance_engine``) — without it a
    // Professional user would see the tab and then hit a 402.
    const visiblePluginTabs = useMemo(() => {
        return pluginTabs.filter(pt => {
            if (pt.moduleRequired && !licenseModules.includes(pt.moduleRequired)) {
                return false;
            }
            if (pt.featureFlag && !licenseFeatures.includes(pt.featureFlag)) {
                return false;
            }
            return true;
        });
    }, [pluginTabs, licenseModules, licenseFeatures]);

    // Build ordered tab definitions array.  Plugin-registered tabs whose
    // ``id`` collides with a hardcoded OSS tab are dropped — otherwise
    // React warns about duplicate keys and BOTH tabs render their panel
    // content on click.  Pro+ plugins that want to provide a richer
    // version of an OSS tab should pick a distinct id (e.g. ``compliance-pro``).
    const tabDefinitions = useMemo(() => {
        const HARDCODED_IDS = new Set([
            'info', 'hardware', 'processes', 'software', 'software-changes',
            'third-party-repos', 'access', 'security', 'compliance',
            'certificates', 'server-roles', 'child-hosts', 'ubuntu-pro',
            'diagnostics',
        ]);
        const safePluginTabs = visiblePluginTabs.filter(
            p => !HARDCODED_IDS.has(p.id),
        );
        const tabs: Array<{ id: string; icon: React.ReactElement; label: string }> = [
            { id: 'info', icon: <InfoIcon />, label: t('hostDetail.infoTab', 'Info') },
            ...safePluginTabs.filter(p => p.position === 'after-info').map(pt => ({ id: pt.id, icon: pt.icon, label: t(pt.labelKey) })),
            { id: 'hardware', icon: <MemoryIcon />, label: t('hostDetail.hardwareTab', 'Hardware') },
            { id: 'processes', icon: <DvrIcon />, label: t('hostDetail.processesTab', 'Processes') },
            { id: 'software', icon: <AppsIcon />, label: t('hostDetail.softwareTab', 'Software') },
            { id: 'software-changes', icon: <HistoryIcon />, label: t('hostDetail.softwareChangesTab', 'Software Changes') },
            ...(supportsThirdPartyRepos() ? [{ id: 'third-party-repos', icon: <SourceIcon />, label: t('hostDetail.thirdPartyReposTab', 'Third-Party Repositories') }] : []),
            { id: 'access', icon: <SecurityIcon />, label: t('hostDetail.accessTab', 'Access') },
            { id: 'security', icon: <ShieldIcon />, label: t('hostDetail.securityTab', 'Security') },
            // Compliance is an Enterprise capability: the ``compliance_engine``
            // module ships at Professional, but the compliance surface itself is
            // gated on the Enterprise ``compliance`` feature — so require BOTH,
            // otherwise a Professional user sees a tab that 402s on every call.
            ...((licenseModules.includes('compliance_engine') && licenseFeatures.includes('compliance')) ? [{ id: 'compliance', icon: <RuleIcon />, label: t('hostDetail.complianceTab', 'Compliance') }] : []),
            ...safePluginTabs.filter(p => p.position === 'after-security').map(pt => ({ id: pt.id, icon: pt.icon, label: t(pt.labelKey) })),
            { id: 'certificates', icon: <CertificateIcon />, label: t('hostDetail.certificatesTab', 'Certificates') },
            { id: 'server-roles', icon: <AssignmentIcon />, label: t('hostDetail.serverRolesTab', 'Server Roles') },
            ...safePluginTabs.filter(p => p.position === 'before-diagnostics').map(pt => ({ id: pt.id, icon: pt.icon, label: t(pt.labelKey) })),
            ...(supportsChildHosts() ? [{ id: 'child-hosts', icon: <ComputerIcon />, label: t('hostDetail.childHostsTab', 'Child Hosts') }] : []),
            ...((isUbuntu() && ubuntuProInfo?.available) ? [{ id: 'ubuntu-pro', icon: <VerifiedUserIcon />, label: t('hostDetail.ubuntuProTab', 'Ubuntu Pro') }] : []),
            { id: 'diagnostics', icon: <MedicalServicesIcon />, label: t('hostDetail.diagnosticsTab', 'Diagnostics') },
        ];

        return tabs;
    }, [visiblePluginTabs, supportsThirdPartyRepos, supportsChildHosts, isUbuntu, ubuntuProInfo, licenseModules, licenseFeatures, t]);

    // Get tab ID for current numeric index
    const currentTabId = tabDefinitions[currentTab]?.id || 'info';

    const {
        hostTabGroups,
        handleTabChange,
    } = useHostTabNavigation({ tabDefinitions, currentTab, setCurrentTab, host, ubuntuProInfo, t });

    const {
        softwarePackages,
        setSoftwarePackages,
        loadingSoftware,
        softwarePagination,
        setSoftwarePagination,
        softwareSearchTerm,
        setSoftwareSearchTerm,
        packageInstallDialogOpen,
        setPackageInstallDialogOpen,
        packageSearchInputRef,
        searchResults,
        selectedPackages,
        isSearching,
        installationHistory,
        installationHistoryLoading,
        selectedInstallationLog,
        installationLogDialogOpen,
        installationDeleteConfirmOpen,
        installationToDelete,
        uninstallConfirmOpen,
        packageToUninstall,
        requestPackagesConfirmOpen,
        setRequestPackagesConfirmOpen,
        performPackageSearch,
        handleRequestPackages,
        handleRequestPackagesConfirm,
        handlePackageSelect,
        handleInstallPackages,
        handleClosePackageDialog,
        handleUninstallPackage,
        handleUninstallConfirm,
        handleUninstallCancel,
        handleViewInstallationLog,
        handleCloseInstallationLogDialog,
        handleDeleteInstallation,
        handleConfirmDeleteInstallation,
        handleCancelDeleteInstallation,
    } = useHostSoftware({ hostId, host, currentTabId, currentUser, tabDefinitions, setCurrentTab, t, setSnackbarMessage, setSnackbarSeverity, setSnackbarOpen });

    const {
        dialogOpen,
        dialogContent,
        dialogTitle,
        sshKeyDialogOpen,
        selectedUser,
        availableSSHKeys,
        filteredSSHKeys,
        selectedSSHKeys,
        setSelectedSSHKeys,
        addCertificateDialogOpen,
        setAddCertificateDialogOpen,
        availableCertificates,
        filteredCertificates,
        selectedCertificates,
        setSelectedCertificates,
        certificateDialogSearchTerm,
        setCertificateDialogSearchTerm,
        isCertificateSearching,
        sshKeySearchTerm,
        setSshKeySearchTerm,
        addUserModalOpen,
        setAddUserModalOpen,
        addGroupModalOpen,
        setAddGroupModalOpen,
        deleteUserConfirmOpen,
        deleteGroupConfirmOpen,
        userToDelete,
        groupToDelete,
        deletingUser,
        deletingGroup,
        deleteDefaultGroup,
        setDeleteDefaultGroup,
        handleShowDialog,
        handleCloseDialog,
        handleAddSSHKey,
        handleSSHKeyDialogClose,
        handleDeleteUserClick,
        handleDeleteUserConfirm,
        handleDeleteUserCancel,
        handleDeleteGroupClick,
        handleDeleteGroupConfirm,
        handleDeleteGroupCancel,
        handleSSHKeySearch,
        handleCertificateDialogClose,
        handleCertificateSearch,
        handleDeployCertificates,
        loadAvailableCertificates,
        handleDeploySSHKeys,
    } = useHostAccessManagement({ hostId, host, t, setSnackbarMessage, setSnackbarSeverity, setSnackbarOpen });

    const {
        certificates,
        certificatesLoading,
        roles,
        rolesLoading,
        selectedRoles,
        serviceControlLoading,
        fetchCertificates,
        requestCertificatesCollection,
        fetchRoles,
        requestRolesCollection,
        addRoleToSelection,
        removeRoleFromSelection,
        selectAllRoles,
        deselectAllRoles,
        handleServiceControl,
    } = useHostRolesAndCerts({ hostId, host, currentTabId, t, setSnackbarMessage, setSnackbarSeverity, setSnackbarOpen });

    const {
        openTelemetryStatus,
        openTelemetryLoading,
        openTelemetryDeploying,
        canDeployOpenTelemetry,
        openTelemetryEligible,
        graylogAttached,
        graylogLoading,
        graylogMechanism,
        graylogTargetHostname,
        graylogTargetIp,
        graylogPort,
        canAttachGraylog,
        graylogEligible,
        graylogAttachModalOpen,
        handleOpenTelemetryStart,
        handleOpenTelemetryStop,
        handleOpenTelemetryRestart,
        handleOpenTelemetryConnect,
        handleOpenTelemetryDisconnect,
        handleRemoveOpenTelemetry,
        handleAttachToGraylog,
        handleGraylogAttachModalClose,
        handleDeployOpenTelemetry,
    } = useHostObservability({ hostId, host, currentTabId, t, setSnackbarMessage, setSnackbarSeverity, setSnackbarOpen, setSoftwarePackages });

    const {
        childHosts,
        childHostsLoading,
        childHostsRefreshRequested,
        virtualizationStatus,
        virtualizationLoading,
        enableWslLoading,
        initializeLxdLoading,
        initializeVmmLoading,
        initializeKvmLoading,
        initializeBhyveLoading,
        disableBhyveLoading,
        kvmModulesLoading,
        createChildHostOpen,
        setCreateChildHostOpen,
        createChildHostLoading,
        childHostFormData,
        setChildHostFormData,
        childHostCreationProgress,
        childHostFormValidated,
        setChildHostFormValidated,
        availableDistributions,
        computedFqdn,
        childHostOperationLoading,
        deleteChildHostConfirmOpen,
        childHostToDelete,
        fetchChildHosts,
        fetchVirtualizationStatus,
        requestChildHostsRefresh,
        handleChildHostStart,
        handleChildHostStop,
        handleChildHostRestart,
        handleChildHostUpdateAgent,
        handleChildHostDeleteConfirm,
        handleChildHostDeleteCancel,
        handleChildHostDelete,
        handleEnableWsl,
        handleInitializeLxd,
        handleInitializeVmm,
        handleInitializeKvm,
        handleInitializeBhyve,
        handleDisableBhyve,
        handleEnableKvmModules,
        handleDisableKvmModules,
        openCreateDialogWithType,
        handleCreateChildHost,
        getWslEmptyMessage,
        getLxdEmptyMessage,
        getVmmEmptyMessage,
        getBhyveEmptyMessage,
        getCreateChildHostTitle,
    } = useChildHosts({ hostId, host, licenseModules, currentTabId, supportsChildHosts, t, setSnackbarMessage, setSnackbarSeverity, setSnackbarOpen });

    const {
        diagnosticsData,
        setDiagnosticsData,
        diagnosticsLoading,
        deleteConfirmOpen,
        rebootConfirmOpen,
        setRebootConfirmOpen,
        shutdownConfirmOpen,
        setShutdownConfirmOpen,
        rebootPreCheckData,
        setRebootPreCheckData,
        rebootPreCheckLoading,
        rebootOrchestrationId,
        rebootOrchestrationStatus,
        diagnosticDetailOpen,
        setDiagnosticDetailOpen,
        selectedDiagnostic,
        diagnosticDetailLoading,
        hostnameEditOpen,
        setHostnameEditOpen,
        newHostname,
        setNewHostname,
        hostnameEditLoading,
        handleDeleteDiagnostic,
        handleViewDiagnosticDetail,
        handleRebootClick,
        handleShutdownClick,
        handleUpdateAgent,
        handleRebootConfirm,
        handleHostnameEditClick,
        handleHostnameChange,
        handleShutdownConfirm,
        handleConfirmDelete,
        handleCancelDelete,
        handleRequestDiagnostics,
    } = useHostLifecycle({ hostId, host, setHost, supportsChildHosts, fetchVirtualizationStatus, t, setSnackbarMessage, setSnackbarSeverity, setSnackbarOpen });

    const {
        filteredStorageDevices,
        filteredNetworkInterfaces,
        filteredUsers,
        filteredGroups,
        enabledShells,
        isDiagnosticsProcessing,
    } = useHostInventoryFilters({ host, storageDevices, networkInterfaces, userAccounts, userGroups, storageFilter, networkFilter, userFilter, groupFilter });

    useHostData({
        hostId, navigate, t,
        setHost, setStorageDevices, setNetworkInterfaces, setUserAccounts, setUserGroups,
        setDiagnosticsData, setCurrentUser, setUbuntuProInfo, setHasAntivirusOsDefault,
        setLoading, setError, setLicenseModules, setLicenseFeatures,
        fetchCertificates, fetchRoles, fetchChildHosts, fetchVirtualizationStatus,
    });




    // Tag-related functions



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


    // Ubuntu Pro handlers

    // Package installation handlers

    // Get edited service label (extracted for SonarQube compliance)

    return (
        <Box sx={{
            display: 'flex',
            flexDirection: 'column',
            height: 'calc(100vh - 120px)',
            gap: 2,
            p: 2
        }}>
            <HostDetailHeader
                host={host}
                hostId={hostId}
                canEditHostname={canEditHostname}
                handleHostnameEditClick={handleHostnameEditClick}
                handleRequestPackages={handleRequestPackages}
                handleRebootClick={handleRebootClick}
                handleShutdownClick={handleShutdownClick}
                handleUpdateAgent={handleUpdateAgent}
            />

            {/* Two-pane layout: grouped category rail on the left, content on the
                right — replaces the old overflowing horizontal tab strip. */}
            <Box sx={{ display: 'flex', gap: 2, flexGrow: 1, minHeight: 0 }}>
                <HostDetailNavRail
                    hostTabGroups={hostTabGroups}
                    tabDefinitions={tabDefinitions}
                    currentTab={currentTab}
                    handleTabChange={handleTabChange}
                />

                {/* Content — keyed off the tab ID at the active index so the
                    mapping is stable when a Pro+-gated tab is filtered out. */}
                <HostDetailTabContent
                    addRoleToSelection={addRoleToSelection}
                    antivirusRefreshTrigger={antivirusRefreshTrigger}
                    availableTags={availableTags}
                    canAddHostAccount={canAddHostAccount}
                    canAddHostGroup={canAddHostGroup}
                    canAddPackage={canAddPackage}
                    canAttachGraylog={canAttachGraylog}
                    canAttachUbuntuPro={canAttachUbuntuPro}
                    canDeleteHostAccount={canDeleteHostAccount}
                    canDeleteHostGroup={canDeleteHostGroup}
                    canDeployAntivirus={canDeployAntivirus}
                    canDeployCertificate={canDeployCertificate}
                    canDeployOpenTelemetry={canDeployOpenTelemetry}
                    canDeploySshKey={canDeploySshKey}
                    canDetachUbuntuPro={canDetachUbuntuPro}
                    canDisableAntivirus={canDisableAntivirus}
                    canEditTags={canEditTags}
                    canEnableAntivirus={canEnableAntivirus}
                    canEnableBhyve={canEnableBhyve}
                    canEnableKvm={canEnableKvm}
                    canEnableLxd={canEnableLxd}
                    canEnableVmm={canEnableVmm}
                    canEnableWsl={canEnableWsl}
                    canRemoveAntivirus={canRemoveAntivirus}
                    canRestartService={canRestartService}
                    canStartService={canStartService}
                    canStopService={canStopService}
                    certificateFilter={certificateFilter}
                    certificatePaginationModel={certificatePaginationModel}
                    certificateSearchTerm={certificateSearchTerm}
                    certificates={certificates}
                    certificatesLoading={certificatesLoading}
                    childHostOperationLoading={childHostOperationLoading}
                    childHosts={childHosts}
                    childHostsLoading={childHostsLoading}
                    childHostsRefreshRequested={childHostsRefreshRequested}
                    currentTabId={currentTabId}
                    deselectAllRoles={deselectAllRoles}
                    diagnosticsData={diagnosticsData}
                    diagnosticsLoading={diagnosticsLoading}
                    disableBhyveLoading={disableBhyveLoading}
                    editedServices={editedServices}
                    enableWslLoading={enableWslLoading}
                    enabledShells={enabledShells}
                    expandedGroupUsers={expandedGroupUsers}
                    expandedUserGroups={expandedUserGroups}
                    filteredGroups={filteredGroups}
                    filteredNetworkInterfaces={filteredNetworkInterfaces}
                    filteredStorageDevices={filteredStorageDevices}
                    filteredUsers={filteredUsers}
                    getBhyveEmptyMessage={getBhyveEmptyMessage}
                    getCertificatesColumnVisibilityModel={getCertificatesColumnVisibilityModel}
                    getEditedServiceLabel={getEditedServiceLabel}
                    getLxdEmptyMessage={getLxdEmptyMessage}
                    getVmmEmptyMessage={getVmmEmptyMessage}
                    getWslEmptyMessage={getWslEmptyMessage}
                    graylogAttached={graylogAttached}
                    graylogEligible={graylogEligible}
                    graylogLoading={graylogLoading}
                    graylogMechanism={graylogMechanism}
                    graylogPort={graylogPort}
                    graylogTargetHostname={graylogTargetHostname}
                    graylogTargetIp={graylogTargetIp}
                    groupFilter={groupFilter}
                    handleAddSSHKey={handleAddSSHKey}
                    handleAddTag={handleAddTag}
                    handleAttachToGraylog={handleAttachToGraylog}
                    handleChildHostDeleteConfirm={handleChildHostDeleteConfirm}
                    handleChildHostRestart={handleChildHostRestart}
                    handleChildHostStart={handleChildHostStart}
                    handleChildHostStop={handleChildHostStop}
                    handleChildHostUpdateAgent={handleChildHostUpdateAgent}
                    handleDeleteDiagnostic={handleDeleteDiagnostic}
                    handleDeleteGroupClick={handleDeleteGroupClick}
                    handleDeleteInstallation={handleDeleteInstallation}
                    handleDeleteUserClick={handleDeleteUserClick}
                    handleDeployAntivirus={handleDeployAntivirus}
                    handleDeployOpenTelemetry={handleDeployOpenTelemetry}
                    handleDisableAntivirus={handleDisableAntivirus}
                    handleDisableBhyve={handleDisableBhyve}
                    handleDisableKvmModules={handleDisableKvmModules}
                    handleEnableAntivirus={handleEnableAntivirus}
                    handleEnableKvmModules={handleEnableKvmModules}
                    handleEnableWsl={handleEnableWsl}
                    handleInitializeBhyve={handleInitializeBhyve}
                    handleInitializeKvm={handleInitializeKvm}
                    handleInitializeLxd={handleInitializeLxd}
                    handleInitializeVmm={handleInitializeVmm}
                    handleOpenTelemetryConnect={handleOpenTelemetryConnect}
                    handleOpenTelemetryDisconnect={handleOpenTelemetryDisconnect}
                    handleOpenTelemetryRestart={handleOpenTelemetryRestart}
                    handleOpenTelemetryStart={handleOpenTelemetryStart}
                    handleOpenTelemetryStop={handleOpenTelemetryStop}
                    handleRemoveAntivirus={handleRemoveAntivirus}
                    handleRemoveOpenTelemetry={handleRemoveOpenTelemetry}
                    handleRemoveTag={handleRemoveTag}
                    handleRequestDiagnostics={handleRequestDiagnostics}
                    handleServiceControl={handleServiceControl}
                    handleServiceToggle={handleServiceToggle}
                    handleServicesEditToggle={handleServicesEditToggle}
                    handleServicesSave={handleServicesSave}
                    handleShowDialog={handleShowDialog}
                    handleUbuntuProAttach={handleUbuntuProAttach}
                    handleUbuntuProDetach={handleUbuntuProDetach}
                    handleUninstallPackage={handleUninstallPackage}
                    handleViewDiagnosticDetail={handleViewDiagnosticDetail}
                    handleViewInstallationLog={handleViewInstallationLog}
                    hasAntivirusOsDefault={hasAntivirusOsDefault}
                    hiddenCertificatesColumns={hiddenCertificatesColumns}
                    host={host}
                    hostId={hostId}
                    hostTags={hostTags}
                    initializeBhyveLoading={initializeBhyveLoading}
                    initializeKvmLoading={initializeKvmLoading}
                    initializeLxdLoading={initializeLxdLoading}
                    initializeVmmLoading={initializeVmmLoading}
                    installationHistory={installationHistory}
                    installationHistoryLoading={installationHistoryLoading}
                    isDiagnosticsProcessing={isDiagnosticsProcessing}
                    isUbuntu={isUbuntu}
                    kvmModulesLoading={kvmModulesLoading}
                    licenseModules={licenseModules}
                    loadAvailableCertificates={loadAvailableCertificates}
                    loadingSoftware={loadingSoftware}
                    networkFilter={networkFilter}
                    networkInterfaces={networkInterfaces}
                    openCreateDialogWithType={openCreateDialogWithType}
                    openTelemetryDeploying={openTelemetryDeploying}
                    openTelemetryEligible={openTelemetryEligible}
                    openTelemetryLoading={openTelemetryLoading}
                    openTelemetryStatus={openTelemetryStatus}
                    removeRoleFromSelection={removeRoleFromSelection}
                    requestCertificatesCollection={requestCertificatesCollection}
                    requestChildHostsRefresh={requestChildHostsRefresh}
                    requestRolesCollection={requestRolesCollection}
                    resetCertificatesPreferences={resetCertificatesPreferences}
                    roles={roles}
                    rolesLoading={rolesLoading}
                    safePageSizeOptions={safePageSizeOptions}
                    selectAllRoles={selectAllRoles}
                    selectedRoles={selectedRoles}
                    selectedTagToAdd={selectedTagToAdd}
                    serviceControlLoading={serviceControlLoading}
                    servicesEditMode={servicesEditMode}
                    servicesMessage={servicesMessage}
                    servicesSaving={servicesSaving}
                    setAddCertificateDialogOpen={setAddCertificateDialogOpen}
                    setAddGroupModalOpen={setAddGroupModalOpen}
                    setAddUserModalOpen={setAddUserModalOpen}
                    setCertificateFilter={setCertificateFilter}
                    setCertificatePaginationModel={setCertificatePaginationModel}
                    setCertificateSearchTerm={setCertificateSearchTerm}
                    setExpandedGroupUsers={setExpandedGroupUsers}
                    setExpandedUserGroups={setExpandedUserGroups}
                    setGroupFilter={setGroupFilter}
                    setHiddenCertificatesColumns={setHiddenCertificatesColumns}
                    setNetworkFilter={setNetworkFilter}
                    setPackageInstallDialogOpen={setPackageInstallDialogOpen}
                    setSelectedTagToAdd={setSelectedTagToAdd}
                    setSoftwarePagination={setSoftwarePagination}
                    setSoftwareSearchTerm={setSoftwareSearchTerm}
                    setStorageFilter={setStorageFilter}
                    setUserFilter={setUserFilter}
                    softwarePackages={softwarePackages}
                    softwarePagination={softwarePagination}
                    softwareSearchTerm={softwareSearchTerm}
                    storageDevices={storageDevices}
                    storageFilter={storageFilter}
                    supportsChildHosts={supportsChildHosts}
                    ubuntuProAttaching={ubuntuProAttaching}
                    ubuntuProDetaching={ubuntuProDetaching}
                    ubuntuProInfo={ubuntuProInfo}
                    userFilter={userFilter}
                    virtualizationLoading={virtualizationLoading}
                    virtualizationStatus={virtualizationStatus}
                    visiblePluginTabs={visiblePluginTabs}
                />
            </Box>

            <HostConfirmDialogs
                host={host}
                dialogOpen={dialogOpen}
                dialogTitle={dialogTitle}
                dialogContent={dialogContent}
                handleCloseDialog={handleCloseDialog}
                rebootConfirmOpen={rebootConfirmOpen}
                setRebootConfirmOpen={setRebootConfirmOpen}
                rebootPreCheckData={rebootPreCheckData}
                setRebootPreCheckData={setRebootPreCheckData}
                rebootPreCheckLoading={rebootPreCheckLoading}
                handleRebootConfirm={handleRebootConfirm}
                shutdownConfirmOpen={shutdownConfirmOpen}
                setShutdownConfirmOpen={setShutdownConfirmOpen}
                handleShutdownConfirm={handleShutdownConfirm}
                hostnameEditOpen={hostnameEditOpen}
                setHostnameEditOpen={setHostnameEditOpen}
                newHostname={newHostname}
                setNewHostname={setNewHostname}
                hostnameEditLoading={hostnameEditLoading}
                handleHostnameChange={handleHostnameChange}
                deleteConfirmOpen={deleteConfirmOpen}
                handleCancelDelete={handleCancelDelete}
                handleConfirmDelete={handleConfirmDelete}
                deleteChildHostConfirmOpen={deleteChildHostConfirmOpen}
                childHostToDelete={childHostToDelete}
                handleChildHostDeleteCancel={handleChildHostDeleteCancel}
                handleChildHostDelete={handleChildHostDelete}
                diagnosticDetailOpen={diagnosticDetailOpen}
                setDiagnosticDetailOpen={setDiagnosticDetailOpen}
                diagnosticDetailLoading={diagnosticDetailLoading}
                selectedDiagnostic={selectedDiagnostic}
                ubuntuProDetachConfirmOpen={ubuntuProDetachConfirmOpen}
                handleCancelUbuntuProDetach={handleCancelUbuntuProDetach}
                handleConfirmUbuntuProDetach={handleConfirmUbuntuProDetach}
                ubuntuProTokenDialog={ubuntuProTokenDialog}
                ubuntuProToken={ubuntuProToken}
                setUbuntuProToken={setUbuntuProToken}
                handleUbuntuProTokenCancel={handleUbuntuProTokenCancel}
                handleUbuntuProTokenSubmit={handleUbuntuProTokenSubmit}
            />

            <HostActionDialogs
                host={host}
                hostId={hostId}
                packageInstallDialogOpen={packageInstallDialogOpen}
                handleClosePackageDialog={handleClosePackageDialog}
                packageSearchInputRef={packageSearchInputRef}
                performPackageSearch={performPackageSearch}
                isSearching={isSearching}
                searchResults={searchResults}
                selectedPackages={selectedPackages}
                handlePackageSelect={handlePackageSelect}
                handleInstallPackages={handleInstallPackages}
                installationLogDialogOpen={installationLogDialogOpen}
                handleCloseInstallationLogDialog={handleCloseInstallationLogDialog}
                selectedInstallationLog={selectedInstallationLog}
                installationDeleteConfirmOpen={installationDeleteConfirmOpen}
                handleCancelDeleteInstallation={handleCancelDeleteInstallation}
                installationToDelete={installationToDelete}
                handleConfirmDeleteInstallation={handleConfirmDeleteInstallation}
                requestPackagesConfirmOpen={requestPackagesConfirmOpen}
                setRequestPackagesConfirmOpen={setRequestPackagesConfirmOpen}
                handleRequestPackagesConfirm={handleRequestPackagesConfirm}
                uninstallConfirmOpen={uninstallConfirmOpen}
                handleUninstallCancel={handleUninstallCancel}
                packageToUninstall={packageToUninstall}
                handleUninstallConfirm={handleUninstallConfirm}
                rebootOrchestrationStatus={rebootOrchestrationStatus}
                rebootOrchestrationId={rebootOrchestrationId}
                snackbarOpen={snackbarOpen}
                handleCloseSnackbar={handleCloseSnackbar}
                snackbarSeverity={snackbarSeverity}
                snackbarMessage={snackbarMessage}
                sshKeyDialogOpen={sshKeyDialogOpen}
                handleSSHKeyDialogClose={handleSSHKeyDialogClose}
                selectedUser={selectedUser}
                sshKeySearchTerm={sshKeySearchTerm}
                setSshKeySearchTerm={setSshKeySearchTerm}
                handleSSHKeySearch={handleSSHKeySearch}
                availableSSHKeys={availableSSHKeys}
                filteredSSHKeys={filteredSSHKeys}
                selectedSSHKeys={selectedSSHKeys}
                setSelectedSSHKeys={setSelectedSSHKeys}
                handleDeploySSHKeys={handleDeploySSHKeys}
                addCertificateDialogOpen={addCertificateDialogOpen}
                handleCertificateDialogClose={handleCertificateDialogClose}
                certificateDialogSearchTerm={certificateDialogSearchTerm}
                setCertificateDialogSearchTerm={setCertificateDialogSearchTerm}
                handleCertificateSearch={handleCertificateSearch}
                availableCertificates={availableCertificates}
                filteredCertificates={filteredCertificates}
                isCertificateSearching={isCertificateSearching}
                selectedCertificates={selectedCertificates}
                setSelectedCertificates={setSelectedCertificates}
                handleDeployCertificates={handleDeployCertificates}
                graylogAttachModalOpen={graylogAttachModalOpen}
                handleGraylogAttachModalClose={handleGraylogAttachModalClose}
                addUserModalOpen={addUserModalOpen}
                setAddUserModalOpen={setAddUserModalOpen}
                onAddUserSuccess={() => {
                    if (hostId) {
                        doGetHostUsers(hostId).then(setUserAccounts).catch(console.error);
                    }
                }}
                addGroupModalOpen={addGroupModalOpen}
                setAddGroupModalOpen={setAddGroupModalOpen}
                onAddGroupSuccess={() => {
                    if (hostId) {
                        doGetHostGroups(hostId).then(setUserGroups).catch(console.error);
                    }
                }}
                deleteUserConfirmOpen={deleteUserConfirmOpen}
                handleDeleteUserCancel={handleDeleteUserCancel}
                userToDelete={userToDelete}
                deleteDefaultGroup={deleteDefaultGroup}
                setDeleteDefaultGroup={setDeleteDefaultGroup}
                deletingUser={deletingUser}
                handleDeleteUserConfirm={handleDeleteUserConfirm}
                deleteGroupConfirmOpen={deleteGroupConfirmOpen}
                handleDeleteGroupCancel={handleDeleteGroupCancel}
                groupToDelete={groupToDelete}
                deletingGroup={deletingGroup}
                handleDeleteGroupConfirm={handleDeleteGroupConfirm}
            />

            <CreateChildHostDialog
                createChildHostOpen={createChildHostOpen}
                createChildHostLoading={createChildHostLoading}
                childHostFormData={childHostFormData}
                setChildHostFormData={setChildHostFormData}
                childHostFormValidated={childHostFormValidated}
                setChildHostFormValidated={setChildHostFormValidated}
                setCreateChildHostOpen={setCreateChildHostOpen}
                availableDistributions={availableDistributions}
                computedFqdn={computedFqdn}
                childHostCreationProgress={childHostCreationProgress}
                getCreateChildHostTitle={getCreateChildHostTitle}
                handleCreateChildHost={handleCreateChildHost}
            />
        </Box>
    );
};

export default HostDetail;