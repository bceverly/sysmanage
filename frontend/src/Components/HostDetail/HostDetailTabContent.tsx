// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

import React from 'react';
import { Box } from '@mui/material';
import ProcessesPanel from '../ProcessesPanel';
import HostCompliancePanel from '../HostCompliancePanel';
import ThirdPartyRepositories from '../../Pages/ThirdPartyRepositories';
import HostInfoTab from './HostInfoTab';
import HostHardwareTab from './HostHardwareTab';
import HostSoftwareTab from './HostSoftwareTab';
import HostUserAccessTab from './HostUserAccessTab';
import HostSecurityTab from './HostSecurityTab';
import HostCertificatesTab from './HostCertificatesTab';
import HostSoftwareChangesTab from './HostSoftwareChangesTab';
import HostServerRolesTab from './HostServerRolesTab';
import HostChildHostsTab from './HostChildHostsTab';
import HostUbuntuProTab from './HostUbuntuProTab';
import HostDiagnosticsTab from './HostDiagnosticsTab';
import { DiagnosticReport, PaginationInfo, SoftwarePackage, SysManageHost, UbuntuProInfo, UserAccount, UserGroup, StorageDevice as StorageDeviceType, NetworkInterface as NetworkInterfaceType } from '../../Services/hosts';
import { Certificate, ChildHost, HostFilterMode, HostRole, InstallationHistoryItem, OpenTelemetryStatus, VirtualizationStatus } from './hostDetailTypes';
import { GridColumnVisibilityModel } from '@mui/x-data-grid';
import { PluginHostDetailTab } from '../../plugins/types';

interface HostTag {
    id: string;
    name: string;
    description: string | null;
}

interface HostDetailTabContentProps {
    addRoleToSelection: (roleId: string) => void;
    antivirusRefreshTrigger: number;
    availableTags: HostTag[];
    canAddHostAccount: boolean;
    canAddHostGroup: boolean;
    canAddPackage: boolean;
    canAttachGraylog: boolean;
    canAttachUbuntuPro: boolean;
    canDeleteHostAccount: boolean;
    canDeleteHostGroup: boolean;
    canDeployAntivirus: boolean;
    canDeployCertificate: boolean;
    canDeployOpenTelemetry: boolean;
    canDeploySshKey: boolean;
    canDetachUbuntuPro: boolean;
    canDisableAntivirus: boolean;
    canEditTags: boolean;
    canEnableAntivirus: boolean;
    canEnableBhyve: boolean;
    canEnableKvm: boolean;
    canEnableLxd: boolean;
    canEnableVmm: boolean;
    canEnableWsl: boolean;
    canRemoveAntivirus: boolean;
    canRestartService: boolean;
    canStartService: boolean;
    canStopService: boolean;
    certificateFilter: 'all' | 'ca' | 'server' | 'client';
    certificatePaginationModel: { page: number; pageSize: number };
    certificateSearchTerm: string;
    certificates: Certificate[];
    certificatesLoading: boolean;
    childHostOperationLoading: Record<string, string | null>;
    childHosts: ChildHost[];
    childHostsLoading: boolean;
    childHostsRefreshRequested: boolean;
    currentTabId: string;
    deselectAllRoles: () => void;
    diagnosticsData: DiagnosticReport[];
    diagnosticsLoading: boolean;
    disableBhyveLoading: boolean;
    editedServices: { [serviceName: string]: boolean };
    enableWslLoading: boolean;
    enabledShells: string[];
    expandedGroupUsers: Set<string>;
    expandedUserGroups: Set<string>;
    filteredGroups: UserGroup[];
    filteredNetworkInterfaces: NetworkInterfaceType[];
    filteredStorageDevices: StorageDeviceType[];
    filteredUsers: UserAccount[];
    getBhyveEmptyMessage: () => string;
    getCertificatesColumnVisibilityModel: () => GridColumnVisibilityModel;
    getEditedServiceLabel: (serviceName: string, serviceStatus: string) => string;
    getLxdEmptyMessage: () => string;
    getVmmEmptyMessage: () => string;
    getWslEmptyMessage: () => string;
    graylogAttached: boolean;
    graylogEligible: boolean;
    graylogLoading: boolean;
    graylogMechanism: string | null;
    graylogPort: number | null;
    graylogTargetHostname: string | null;
    graylogTargetIp: string | null;
    groupFilter: HostFilterMode;
    handleAddSSHKey: (user: UserAccount) => void;
    handleAddTag: () => void;
    handleAttachToGraylog: () => void;
    handleChildHostDeleteConfirm: (child: ChildHost) => void;
    handleChildHostRestart: (child: ChildHost) => void;
    handleChildHostStart: (child: ChildHost) => void;
    handleChildHostStop: (child: ChildHost) => void;
    handleChildHostUpdateAgent: (child: ChildHost) => void;
    handleDeleteDiagnostic: (diagnosticId: string) => void;
    handleDeleteGroupClick: (group: UserGroup) => void;
    handleDeleteInstallation: (installation: InstallationHistoryItem) => void;
    handleDeleteUserClick: (user: UserAccount) => void;
    handleDeployAntivirus: () => void;
    handleDeployOpenTelemetry: () => void;
    handleDisableAntivirus: () => void;
    handleDisableBhyve: () => void;
    handleDisableKvmModules: () => void;
    handleEnableAntivirus: () => void;
    handleEnableKvmModules: () => void;
    handleEnableWsl: () => void;
    handleInitializeBhyve: () => void;
    handleInitializeKvm: () => void;
    handleInitializeLxd: () => void;
    handleInitializeVmm: () => void;
    handleOpenTelemetryConnect: () => void;
    handleOpenTelemetryDisconnect: () => void;
    handleOpenTelemetryRestart: () => void;
    handleOpenTelemetryStart: () => void;
    handleOpenTelemetryStop: () => void;
    handleRemoveAntivirus: () => void;
    handleRemoveOpenTelemetry: () => void;
    handleRemoveTag: (tagId: string) => void;
    handleRequestDiagnostics: () => void;
    handleServiceControl: (action: 'start' | 'stop' | 'restart') => void;
    handleServiceToggle: (serviceName: string, enabled: boolean) => void;
    handleServicesEditToggle: () => void;
    handleServicesSave: () => void;
    handleShowDialog: (title: string, content: string) => void;
    handleUbuntuProAttach: () => void;
    handleUbuntuProDetach: () => void;
    handleUninstallPackage: (pkg: SoftwarePackage) => void;
    handleViewDiagnosticDetail: (diagnosticId: string) => void;
    handleViewInstallationLog: (installation: InstallationHistoryItem) => void;
    hasAntivirusOsDefault: boolean;
    hiddenCertificatesColumns: string[];
    host: SysManageHost;
    hostId: string | undefined;
    hostTags: HostTag[];
    initializeBhyveLoading: boolean;
    initializeKvmLoading: boolean;
    initializeLxdLoading: boolean;
    initializeVmmLoading: boolean;
    installationHistory: InstallationHistoryItem[];
    installationHistoryLoading: boolean;
    isDiagnosticsProcessing: boolean;
    isUbuntu: () => boolean;
    kvmModulesLoading: boolean;
    licenseModules: string[];
    loadAvailableCertificates: () => void;
    loadingSoftware: boolean;
    networkFilter: 'all' | 'active' | 'inactive';
    networkInterfaces: NetworkInterfaceType[];
    openCreateDialogWithType: (childType: string) => void;
    openTelemetryDeploying: boolean;
    openTelemetryEligible: boolean;
    openTelemetryLoading: boolean;
    openTelemetryStatus: OpenTelemetryStatus;
    removeRoleFromSelection: (roleId: string) => void;
    requestCertificatesCollection: () => void;
    requestChildHostsRefresh: (showSnackbar?: boolean) => void;
    requestRolesCollection: () => void;
    resetCertificatesPreferences: () => void;
    roles: HostRole[];
    rolesLoading: boolean;
    safePageSizeOptions: number[];
    selectAllRoles: () => void;
    selectedRoles: string[];
    selectedTagToAdd: string;
    serviceControlLoading: boolean;
    servicesEditMode: boolean;
    servicesMessage: string;
    servicesSaving: boolean;
    setAddCertificateDialogOpen: (value: boolean) => void;
    setAddGroupModalOpen: (value: boolean) => void;
    setAddUserModalOpen: (value: boolean) => void;
    setCertificateFilter: (value: 'all' | 'ca' | 'server' | 'client') => void;
    setCertificatePaginationModel: React.Dispatch<React.SetStateAction<{ page: number; pageSize: number }>>;
    setCertificateSearchTerm: (value: string) => void;
    setExpandedGroupUsers: React.Dispatch<React.SetStateAction<Set<string>>>;
    setExpandedUserGroups: React.Dispatch<React.SetStateAction<Set<string>>>;
    setGroupFilter: (value: HostFilterMode) => void;
    setHiddenCertificatesColumns: (columns: string[]) => void;
    setNetworkFilter: (value: 'all' | 'active' | 'inactive') => void;
    setPackageInstallDialogOpen: (value: boolean) => void;
    setSelectedTagToAdd: (value: string) => void;
    setSoftwarePagination: React.Dispatch<React.SetStateAction<PaginationInfo>>;
    setSoftwareSearchTerm: (value: string) => void;
    setStorageFilter: (value: 'all' | 'physical' | 'logical') => void;
    setUserFilter: (value: HostFilterMode) => void;
    softwarePackages: SoftwarePackage[];
    softwarePagination: PaginationInfo;
    softwareSearchTerm: string;
    storageDevices: StorageDeviceType[];
    storageFilter: 'all' | 'physical' | 'logical';
    supportsChildHosts: () => boolean;
    ubuntuProAttaching: boolean;
    ubuntuProDetaching: boolean;
    ubuntuProInfo: UbuntuProInfo | null;
    userFilter: HostFilterMode;
    virtualizationLoading: boolean;
    virtualizationStatus: VirtualizationStatus | null;
    visiblePluginTabs: PluginHostDetailTab[];
}

const HostDetailTabContent: React.FC<HostDetailTabContentProps> = (props) => {
    const {
        addRoleToSelection,
        antivirusRefreshTrigger,
        availableTags,
        canAddHostAccount,
        canAddHostGroup,
        canAddPackage,
        canAttachGraylog,
        canAttachUbuntuPro,
        canDeleteHostAccount,
        canDeleteHostGroup,
        canDeployAntivirus,
        canDeployCertificate,
        canDeployOpenTelemetry,
        canDeploySshKey,
        canDetachUbuntuPro,
        canDisableAntivirus,
        canEditTags,
        canEnableAntivirus,
        canEnableBhyve,
        canEnableKvm,
        canEnableLxd,
        canEnableVmm,
        canEnableWsl,
        canRemoveAntivirus,
        canRestartService,
        canStartService,
        canStopService,
        certificateFilter,
        certificatePaginationModel,
        certificateSearchTerm,
        certificates,
        certificatesLoading,
        childHostOperationLoading,
        childHosts,
        childHostsLoading,
        childHostsRefreshRequested,
        currentTabId,
        deselectAllRoles,
        diagnosticsData,
        diagnosticsLoading,
        disableBhyveLoading,
        editedServices,
        enableWslLoading,
        enabledShells,
        expandedGroupUsers,
        expandedUserGroups,
        filteredGroups,
        filteredNetworkInterfaces,
        filteredStorageDevices,
        filteredUsers,
        getBhyveEmptyMessage,
        getCertificatesColumnVisibilityModel,
        getEditedServiceLabel,
        getLxdEmptyMessage,
        getVmmEmptyMessage,
        getWslEmptyMessage,
        graylogAttached,
        graylogEligible,
        graylogLoading,
        graylogMechanism,
        graylogPort,
        graylogTargetHostname,
        graylogTargetIp,
        groupFilter,
        handleAddSSHKey,
        handleAddTag,
        handleAttachToGraylog,
        handleChildHostDeleteConfirm,
        handleChildHostRestart,
        handleChildHostStart,
        handleChildHostStop,
        handleChildHostUpdateAgent,
        handleDeleteDiagnostic,
        handleDeleteGroupClick,
        handleDeleteInstallation,
        handleDeleteUserClick,
        handleDeployAntivirus,
        handleDeployOpenTelemetry,
        handleDisableAntivirus,
        handleDisableBhyve,
        handleDisableKvmModules,
        handleEnableAntivirus,
        handleEnableKvmModules,
        handleEnableWsl,
        handleInitializeBhyve,
        handleInitializeKvm,
        handleInitializeLxd,
        handleInitializeVmm,
        handleOpenTelemetryConnect,
        handleOpenTelemetryDisconnect,
        handleOpenTelemetryRestart,
        handleOpenTelemetryStart,
        handleOpenTelemetryStop,
        handleRemoveAntivirus,
        handleRemoveOpenTelemetry,
        handleRemoveTag,
        handleRequestDiagnostics,
        handleServiceControl,
        handleServiceToggle,
        handleServicesEditToggle,
        handleServicesSave,
        handleShowDialog,
        handleUbuntuProAttach,
        handleUbuntuProDetach,
        handleUninstallPackage,
        handleViewDiagnosticDetail,
        handleViewInstallationLog,
        hasAntivirusOsDefault,
        hiddenCertificatesColumns,
        host,
        hostId,
        hostTags,
        initializeBhyveLoading,
        initializeKvmLoading,
        initializeLxdLoading,
        initializeVmmLoading,
        installationHistory,
        installationHistoryLoading,
        isDiagnosticsProcessing,
        isUbuntu,
        kvmModulesLoading,
        licenseModules,
        loadAvailableCertificates,
        loadingSoftware,
        networkFilter,
        networkInterfaces,
        openCreateDialogWithType,
        openTelemetryDeploying,
        openTelemetryEligible,
        openTelemetryLoading,
        openTelemetryStatus,
        removeRoleFromSelection,
        requestCertificatesCollection,
        requestChildHostsRefresh,
        requestRolesCollection,
        resetCertificatesPreferences,
        roles,
        rolesLoading,
        safePageSizeOptions,
        selectAllRoles,
        selectedRoles,
        selectedTagToAdd,
        serviceControlLoading,
        servicesEditMode,
        servicesMessage,
        servicesSaving,
        setAddCertificateDialogOpen,
        setAddGroupModalOpen,
        setAddUserModalOpen,
        setCertificateFilter,
        setCertificatePaginationModel,
        setCertificateSearchTerm,
        setExpandedGroupUsers,
        setExpandedUserGroups,
        setGroupFilter,
        setHiddenCertificatesColumns,
        setNetworkFilter,
        setPackageInstallDialogOpen,
        setSelectedTagToAdd,
        setSoftwarePagination,
        setSoftwareSearchTerm,
        setStorageFilter,
        setUserFilter,
        softwarePackages,
        softwarePagination,
        softwareSearchTerm,
        storageDevices,
        storageFilter,
        supportsChildHosts,
        ubuntuProAttaching,
        ubuntuProDetaching,
        ubuntuProInfo,
        userFilter,
        virtualizationLoading,
        virtualizationStatus,
        visiblePluginTabs,
    } = props;
    return (        <Box sx={{ flexGrow: 1, overflow: 'auto', minHeight: 0 }}>
            {currentTabId === 'info' && (
                <HostInfoTab
                    host={host}
                    hostId={hostId}
                    enabledShells={enabledShells}
                    licenseModules={licenseModules}
                    hostTags={hostTags}
                    availableTags={availableTags}
                    selectedTagToAdd={selectedTagToAdd}
                    setSelectedTagToAdd={setSelectedTagToAdd}
                    canEditTags={canEditTags}
                    handleAddTag={handleAddTag}
                    handleRemoveTag={handleRemoveTag}
                    handleShowDialog={handleShowDialog}
                    openTelemetryStatus={openTelemetryStatus}
                    openTelemetryLoading={openTelemetryLoading}
                    openTelemetryDeploying={openTelemetryDeploying}
                    handleDeployOpenTelemetry={handleDeployOpenTelemetry}
                    handleOpenTelemetryStart={handleOpenTelemetryStart}
                    handleOpenTelemetryStop={handleOpenTelemetryStop}
                    handleOpenTelemetryRestart={handleOpenTelemetryRestart}
                    handleOpenTelemetryConnect={handleOpenTelemetryConnect}
                    handleOpenTelemetryDisconnect={handleOpenTelemetryDisconnect}
                    handleRemoveOpenTelemetry={handleRemoveOpenTelemetry}
                    graylogLoading={graylogLoading}
                    graylogAttached={graylogAttached}
                    graylogMechanism={graylogMechanism}
                    graylogTargetHostname={graylogTargetHostname}
                    graylogTargetIp={graylogTargetIp}
                    graylogPort={graylogPort}
                    canAttachGraylog={canAttachGraylog}
                    graylogEligible={graylogEligible}
                    handleAttachToGraylog={handleAttachToGraylog}
                />
            )}

            {/* Hardware Tab */}
            {currentTabId === 'hardware' && (
                <HostHardwareTab
                    host={host}
                    storageDevices={storageDevices}
                    networkInterfaces={networkInterfaces}
                    filteredStorageDevices={filteredStorageDevices}
                    filteredNetworkInterfaces={filteredNetworkInterfaces}
                    storageFilter={storageFilter}
                    setStorageFilter={setStorageFilter}
                    networkFilter={networkFilter}
                    setNetworkFilter={setNetworkFilter}
                    handleShowDialog={handleShowDialog}
                />
            )}

            {/* Processes Tab */}
            {currentTabId === 'processes' && hostId && (
                <ProcessesPanel
                    hostId={hostId}
                    hostActive={host?.active}
                    isAgentPrivileged={host?.is_agent_privileged}
                />
            )}

            {/* Software Tab */}
            {currentTabId === 'software' && (
                <HostSoftwareTab
                    host={host}
                    licenseModules={licenseModules}
                    softwarePackages={softwarePackages}
                    softwarePagination={softwarePagination}
                    setSoftwarePagination={setSoftwarePagination}
                    softwareSearchTerm={softwareSearchTerm}
                    setSoftwareSearchTerm={setSoftwareSearchTerm}
                    loadingSoftware={loadingSoftware}
                    canAddPackage={canAddPackage}
                    setPackageInstallDialogOpen={setPackageInstallDialogOpen}
                    canDeployOpenTelemetry={canDeployOpenTelemetry}
                    openTelemetryEligible={openTelemetryEligible}
                    openTelemetryDeploying={openTelemetryDeploying}
                    handleDeployOpenTelemetry={handleDeployOpenTelemetry}
                    canAttachGraylog={canAttachGraylog}
                    graylogEligible={graylogEligible}
                    graylogAttached={graylogAttached}
                    handleAttachToGraylog={handleAttachToGraylog}
                    handleUninstallPackage={handleUninstallPackage}
                />
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
                <HostUserAccessTab
                    host={host}
                    licenseModules={licenseModules}
                    filteredUsers={filteredUsers}
                    filteredGroups={filteredGroups}
                    userFilter={userFilter}
                    setUserFilter={setUserFilter}
                    groupFilter={groupFilter}
                    setGroupFilter={setGroupFilter}
                    expandedUserGroups={expandedUserGroups}
                    setExpandedUserGroups={setExpandedUserGroups}
                    expandedGroupUsers={expandedGroupUsers}
                    setExpandedGroupUsers={setExpandedGroupUsers}
                    canAddHostAccount={canAddHostAccount}
                    canAddHostGroup={canAddHostGroup}
                    canDeleteHostAccount={canDeleteHostAccount}
                    canDeleteHostGroup={canDeleteHostGroup}
                    canDeploySshKey={canDeploySshKey}
                    setAddUserModalOpen={setAddUserModalOpen}
                    setAddGroupModalOpen={setAddGroupModalOpen}
                    handleAddSSHKey={handleAddSSHKey}
                    handleDeleteUserClick={handleDeleteUserClick}
                    handleDeleteGroupClick={handleDeleteGroupClick}
                />
            )}

            {/* Security Tab */}
            {currentTabId === 'security' && hostId && (
                <HostSecurityTab
                    host={host}
                    hostId={hostId}
                    hasAntivirusOsDefault={hasAntivirusOsDefault}
                    antivirusRefreshTrigger={antivirusRefreshTrigger}
                    canDeployAntivirus={canDeployAntivirus}
                    canEnableAntivirus={canEnableAntivirus}
                    canDisableAntivirus={canDisableAntivirus}
                    canRemoveAntivirus={canRemoveAntivirus}
                    handleDeployAntivirus={handleDeployAntivirus}
                    handleEnableAntivirus={handleEnableAntivirus}
                    handleDisableAntivirus={handleDisableAntivirus}
                    handleRemoveAntivirus={handleRemoveAntivirus}
                />
            )}

            {/* Plugin tabs content.  Drop any whose id collides with a
                hardcoded OSS tab so the OSS panel stays authoritative — see
                the matching filter in tabDefinitions above. */}
            {visiblePluginTabs
                .filter(pt => !new Set([
                    'info', 'hardware', 'software', 'software-changes',
                    'third-party-repos', 'access', 'security', 'compliance',
                    'certificates', 'server-roles', 'child-hosts', 'ubuntu-pro',
                    'diagnostics',
                ]).has(pt.id))
                .map(pt => (
                    currentTabId === pt.id && hostId && (
                        <Box key={pt.id} sx={{ p: 2 }}>
                            <pt.component hostId={hostId} />
                        </Box>
                    )
                ))}

            {/* Compliance Tab (Phase 8.3) */}
            {currentTabId === 'compliance' && hostId && (
                <Box sx={{ p: 2 }}>
                    <HostCompliancePanel hostId={hostId} />
                </Box>
            )}

            {/* Certificates Tab */}
            {currentTabId === 'certificates' && (
                <HostCertificatesTab
                    host={host}
                    licenseModules={licenseModules}
                    certificates={certificates}
                    certificatesLoading={certificatesLoading}
                    certificateFilter={certificateFilter}
                    setCertificateFilter={setCertificateFilter}
                    certificateSearchTerm={certificateSearchTerm}
                    setCertificateSearchTerm={setCertificateSearchTerm}
                    certificatePaginationModel={certificatePaginationModel}
                    setCertificatePaginationModel={setCertificatePaginationModel}
                    safePageSizeOptions={safePageSizeOptions}
                    canDeployCertificate={canDeployCertificate}
                    setAddCertificateDialogOpen={setAddCertificateDialogOpen}
                    loadAvailableCertificates={loadAvailableCertificates}
                    requestCertificatesCollection={requestCertificatesCollection}
                    hiddenCertificatesColumns={hiddenCertificatesColumns}
                    setHiddenCertificatesColumns={setHiddenCertificatesColumns}
                    resetCertificatesPreferences={resetCertificatesPreferences}
                    getCertificatesColumnVisibilityModel={getCertificatesColumnVisibilityModel}
                />
            )}

            {/* Software Changes Tab */}
            {currentTabId === 'software-changes' && (
                <HostSoftwareChangesTab
                    installationHistory={installationHistory}
                    installationHistoryLoading={installationHistoryLoading}
                    handleViewInstallationLog={handleViewInstallationLog}
                    handleDeleteInstallation={handleDeleteInstallation}
                />
            )}

            {/* Server Roles Tab */}
            {currentTabId === 'server-roles' && (
                <HostServerRolesTab
                    host={host}
                    roles={roles}
                    rolesLoading={rolesLoading}
                    selectedRoles={selectedRoles}
                    serviceControlLoading={serviceControlLoading}
                    canStartService={canStartService}
                    canStopService={canStopService}
                    canRestartService={canRestartService}
                    requestRolesCollection={requestRolesCollection}
                    selectAllRoles={selectAllRoles}
                    deselectAllRoles={deselectAllRoles}
                    addRoleToSelection={addRoleToSelection}
                    removeRoleFromSelection={removeRoleFromSelection}
                    handleServiceControl={handleServiceControl}
                />
            )}

            {/* Child Hosts Tab */}
            {/* NOSONAR: Cognitive complexity is acceptable here as this is a cohesive JSX block rendering virtualization capabilities for multiple hypervisor types (WSL, LXD, VMM, KVM, bhyve) with consistent structure */}
            {currentTabId === 'child-hosts' && supportsChildHosts() && (
                <HostChildHostsTab
                    host={host}
                    licenseModules={licenseModules}
                    virtualizationStatus={virtualizationStatus}
                    virtualizationLoading={virtualizationLoading}
                    childHosts={childHosts}
                    childHostsLoading={childHostsLoading}
                    childHostsRefreshRequested={childHostsRefreshRequested}
                    childHostOperationLoading={childHostOperationLoading}
                    enableWslLoading={enableWslLoading}
                    initializeLxdLoading={initializeLxdLoading}
                    initializeKvmLoading={initializeKvmLoading}
                    initializeVmmLoading={initializeVmmLoading}
                    initializeBhyveLoading={initializeBhyveLoading}
                    disableBhyveLoading={disableBhyveLoading}
                    kvmModulesLoading={kvmModulesLoading}
                    canEnableWsl={canEnableWsl}
                    canEnableLxd={canEnableLxd}
                    canEnableKvm={canEnableKvm}
                    canEnableVmm={canEnableVmm}
                    canEnableBhyve={canEnableBhyve}
                    handleEnableWsl={handleEnableWsl}
                    handleInitializeLxd={handleInitializeLxd}
                    handleInitializeKvm={handleInitializeKvm}
                    handleInitializeVmm={handleInitializeVmm}
                    handleInitializeBhyve={handleInitializeBhyve}
                    handleDisableBhyve={handleDisableBhyve}
                    handleEnableKvmModules={handleEnableKvmModules}
                    handleDisableKvmModules={handleDisableKvmModules}
                    openCreateDialogWithType={openCreateDialogWithType}
                    requestChildHostsRefresh={requestChildHostsRefresh}
                    handleChildHostStart={handleChildHostStart}
                    handleChildHostStop={handleChildHostStop}
                    handleChildHostRestart={handleChildHostRestart}
                    handleChildHostUpdateAgent={handleChildHostUpdateAgent}
                    handleChildHostDeleteConfirm={handleChildHostDeleteConfirm}
                    getWslEmptyMessage={getWslEmptyMessage}
                    getLxdEmptyMessage={getLxdEmptyMessage}
                    getVmmEmptyMessage={getVmmEmptyMessage}
                    getBhyveEmptyMessage={getBhyveEmptyMessage}
                />
            )}

            {/* Ubuntu Pro Tab */}
            {currentTabId === 'ubuntu-pro' && isUbuntu() && ubuntuProInfo?.available && (
                <HostUbuntuProTab
                    host={host}
                    ubuntuProInfo={ubuntuProInfo}
                    ubuntuProAttaching={ubuntuProAttaching}
                    ubuntuProDetaching={ubuntuProDetaching}
                    canAttachUbuntuPro={canAttachUbuntuPro}
                    canDetachUbuntuPro={canDetachUbuntuPro}
                    servicesEditMode={servicesEditMode}
                    servicesSaving={servicesSaving}
                    servicesMessage={servicesMessage}
                    editedServices={editedServices}
                    handleUbuntuProAttach={handleUbuntuProAttach}
                    handleUbuntuProDetach={handleUbuntuProDetach}
                    handleServicesEditToggle={handleServicesEditToggle}
                    handleServicesSave={handleServicesSave}
                    handleServiceToggle={handleServiceToggle}
                    getEditedServiceLabel={getEditedServiceLabel}
                />
            )}

            {/* Diagnostics Tab */}
            {currentTabId === 'diagnostics' && (
                <HostDiagnosticsTab
                    host={host}
                    diagnosticsData={diagnosticsData}
                    diagnosticsLoading={diagnosticsLoading}
                    isDiagnosticsProcessing={isDiagnosticsProcessing}
                    handleRequestDiagnostics={handleRequestDiagnostics}
                    handleViewDiagnosticDetail={handleViewDiagnosticDetail}
                    handleDeleteDiagnostic={handleDeleteDiagnostic}
                />
            )}        </Box>
    );
};

export default HostDetailTabContent;
