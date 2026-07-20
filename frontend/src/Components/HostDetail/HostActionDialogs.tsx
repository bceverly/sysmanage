// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

/* global Event */
import React from 'react';
import {
    Box,
    Typography,
    Chip,
    Button,
    CircularProgress,
    Paper,
    LinearProgress,
    Checkbox,
    FormControlLabel,
    IconButton,
    Alert,
    Dialog,
    DialogTitle,
    DialogContent,
    DialogActions,
    Grid,
    Snackbar,
    TextField,
    List,
    ListItem,
    ListItemText,
    Divider,
    InputAdornment,
} from '@mui/material';
import CloseIcon from '@mui/icons-material/Close';
import DeleteIcon from '@mui/icons-material/Delete';
import SystemUpdateAltIcon from '@mui/icons-material/SystemUpdateAlt';
import SearchIcon from '@mui/icons-material/Search';
import { DataGrid, GridColDef, GridRowSelectionModel } from '@mui/x-data-grid';
import { useTranslation } from 'react-i18next';
import GraylogAttachmentModal from '../GraylogAttachmentModal';
import AddHostAccountModal from '../AddHostAccountModal';
import AddHostGroupModal from '../AddHostGroupModal';
import { SysManageHost, SoftwarePackage, UserAccount, UserGroup, RebootOrchestrationStatus } from '../../Services/hosts';
import { SecretResponse } from '../../Services/secrets';
import { InstallationHistoryItem } from './hostDetailTypes';
import { formatUTCTimestamp } from '../../utils/dateUtils';
import {
    formatDateTime,
    getInstallationStatusColor,
    getTranslatedStatus,
} from './hostDetailHelpers';

interface HostActionDialogsProps {
    host: SysManageHost | null;
    hostId: string | undefined;
    packageInstallDialogOpen: boolean;
    handleClosePackageDialog: () => void;
    packageSearchInputRef: React.RefObject<HTMLInputElement | null>;
    performPackageSearch: (query: string) => void;
    isSearching: boolean;
    searchResults: Array<{ name: string; description?: string; version?: string }>;
    selectedPackages: Set<string>;
    handlePackageSelect: (packageName: string) => void;
    handleInstallPackages: () => void;
    installationLogDialogOpen: boolean;
    handleCloseInstallationLogDialog: () => void;
    selectedInstallationLog: InstallationHistoryItem | null;
    installationDeleteConfirmOpen: boolean;
    handleCancelDeleteInstallation: () => void;
    installationToDelete: InstallationHistoryItem | null;
    handleConfirmDeleteInstallation: () => void;
    requestPackagesConfirmOpen: boolean;
    setRequestPackagesConfirmOpen: (value: boolean) => void;
    handleRequestPackagesConfirm: () => void;
    uninstallConfirmOpen: boolean;
    handleUninstallCancel: () => void;
    packageToUninstall: SoftwarePackage | null;
    handleUninstallConfirm: () => void;
    rebootOrchestrationStatus: RebootOrchestrationStatus | null;
    rebootOrchestrationId: string | null;
    snackbarOpen: boolean;
    handleCloseSnackbar: (event: React.SyntheticEvent | Event, reason?: string) => void;
    snackbarSeverity: 'success' | 'error' | 'warning';
    snackbarMessage: string;
    sshKeyDialogOpen: boolean;
    handleSSHKeyDialogClose: () => void;
    selectedUser: UserAccount | null;
    sshKeySearchTerm: string;
    setSshKeySearchTerm: (value: string) => void;
    handleSSHKeySearch: () => void;
    availableSSHKeys: SecretResponse[];
    filteredSSHKeys: SecretResponse[];
    selectedSSHKeys: string[];
    setSelectedSSHKeys: (value: string[]) => void;
    handleDeploySSHKeys: () => void;
    addCertificateDialogOpen: boolean;
    handleCertificateDialogClose: () => void;
    certificateDialogSearchTerm: string;
    setCertificateDialogSearchTerm: (value: string) => void;
    handleCertificateSearch: () => void;
    availableCertificates: SecretResponse[];
    filteredCertificates: SecretResponse[];
    isCertificateSearching: boolean;
    selectedCertificates: string[];
    setSelectedCertificates: (value: string[]) => void;
    handleDeployCertificates: () => void;
    graylogAttachModalOpen: boolean;
    handleGraylogAttachModalClose: () => void;
    addUserModalOpen: boolean;
    setAddUserModalOpen: (value: boolean) => void;
    onAddUserSuccess: () => void;
    addGroupModalOpen: boolean;
    setAddGroupModalOpen: (value: boolean) => void;
    onAddGroupSuccess: () => void;
    deleteUserConfirmOpen: boolean;
    handleDeleteUserCancel: () => void;
    userToDelete: UserAccount | null;
    deleteDefaultGroup: boolean;
    setDeleteDefaultGroup: (value: boolean) => void;
    deletingUser: boolean;
    handleDeleteUserConfirm: () => void;
    deleteGroupConfirmOpen: boolean;
    handleDeleteGroupCancel: () => void;
    groupToDelete: UserGroup | null;
    deletingGroup: boolean;
    handleDeleteGroupConfirm: () => void;
}

const HostActionDialogs: React.FC<HostActionDialogsProps> = ({
    host,
    hostId,
    packageInstallDialogOpen,
    handleClosePackageDialog,
    packageSearchInputRef,
    performPackageSearch,
    isSearching,
    searchResults,
    selectedPackages,
    handlePackageSelect,
    handleInstallPackages,
    installationLogDialogOpen,
    handleCloseInstallationLogDialog,
    selectedInstallationLog,
    installationDeleteConfirmOpen,
    handleCancelDeleteInstallation,
    installationToDelete,
    handleConfirmDeleteInstallation,
    requestPackagesConfirmOpen,
    setRequestPackagesConfirmOpen,
    handleRequestPackagesConfirm,
    uninstallConfirmOpen,
    handleUninstallCancel,
    packageToUninstall,
    handleUninstallConfirm,
    rebootOrchestrationStatus,
    rebootOrchestrationId,
    snackbarOpen,
    handleCloseSnackbar,
    snackbarSeverity,
    snackbarMessage,
    sshKeyDialogOpen,
    handleSSHKeyDialogClose,
    selectedUser,
    sshKeySearchTerm,
    setSshKeySearchTerm,
    handleSSHKeySearch,
    availableSSHKeys,
    filteredSSHKeys,
    selectedSSHKeys,
    setSelectedSSHKeys,
    handleDeploySSHKeys,
    addCertificateDialogOpen,
    handleCertificateDialogClose,
    certificateDialogSearchTerm,
    setCertificateDialogSearchTerm,
    handleCertificateSearch,
    availableCertificates,
    filteredCertificates,
    isCertificateSearching,
    selectedCertificates,
    setSelectedCertificates,
    handleDeployCertificates,
    graylogAttachModalOpen,
    handleGraylogAttachModalClose,
    addUserModalOpen,
    setAddUserModalOpen,
    onAddUserSuccess,
    addGroupModalOpen,
    setAddGroupModalOpen,
    onAddGroupSuccess,
    deleteUserConfirmOpen,
    handleDeleteUserCancel,
    userToDelete,
    deleteDefaultGroup,
    setDeleteDefaultGroup,
    deletingUser,
    handleDeleteUserConfirm,
    deleteGroupConfirmOpen,
    handleDeleteGroupCancel,
    groupToDelete,
    deletingGroup,
    handleDeleteGroupConfirm,
}) => {
    const { t } = useTranslation();

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
    return (
        <>
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
                                placeholder={t('hostDetail.packageSearchPlaceholder', 'Enter package name to search...')}
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
                                {isSearching ? <CircularProgress size={20} /> : t('common.search', 'Search')}
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
                                        label={getTranslatedStatus(t, selectedInstallationLog.status)}
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
                onSuccess={onAddUserSuccess}
            />

            {/* Add Host Group Modal */}
            <AddHostGroupModal
                open={addGroupModalOpen}
                onClose={() => setAddGroupModalOpen(false)}
                hostId={hostId || ''}
                hostPlatform={host?.platform || ''}
                onSuccess={onAddGroupSuccess}
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
            </Dialog>        </>
    );
};

export default HostActionDialogs;
