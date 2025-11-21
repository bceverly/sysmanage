import React, { useEffect, useState, useCallback, useMemo } from 'react';
import {
    Box,
    Button,
    Dialog,
    DialogTitle,
    DialogContent,
    DialogActions,
    TextField,
    Alert,
    CircularProgress,
    Typography,
    Chip,
} from '@mui/material';
import { DataGrid, GridColDef, GridRowSelectionModel } from '@mui/x-data-grid';
import AddIcon from '@mui/icons-material/Add';
import DeleteIcon from '@mui/icons-material/Delete';
import RefreshIcon from '@mui/icons-material/Refresh';
import CheckCircleIcon from '@mui/icons-material/CheckCircle';
import CancelIcon from '@mui/icons-material/Cancel';
import { useTranslation } from 'react-i18next';
import { useColumnVisibility } from '../Hooks/useColumnVisibility';
import ColumnVisibilityButton from '../Components/ColumnVisibilityButton';
import axiosInstance from '../Services/api';
import { hasPermission, SecurityRoles } from '../Services/permissions';
import { useTablePageSize } from '../hooks/useTablePageSize';

interface ThirdPartyRepository {
    id: string;
    name: string;
    type: string;
    url: string;
    enabled: boolean;
    file_path?: string;
    isDefault?: boolean;
}

interface DefaultRepository {
    id: string;
    os_name: string;
    package_manager: string;
    repository_url: string;
}

interface ThirdPartyRepositoriesProps {
    hostId: string;
    privilegedMode: boolean;
    osName: string;
}

const ThirdPartyRepositories: React.FC<ThirdPartyRepositoriesProps> = ({
    hostId,
    privilegedMode,
    osName,
}) => {
    const { t } = useTranslation();
    const [repositories, setRepositories] = useState<ThirdPartyRepository[]>([]);
    const [defaultRepositories, setDefaultRepositories] = useState<DefaultRepository[]>([]);
    const [loading, setLoading] = useState<boolean>(true);
    const [error, setError] = useState<string | null>(null);
    const [success, setSuccess] = useState<string | null>(null);
    const [selectedRows, setSelectedRows] = useState<GridRowSelectionModel>([]);
    const [addDialogOpen, setAddDialogOpen] = useState<boolean>(false);
    const [canAdd, setCanAdd] = useState<boolean>(false);
    const [canDelete, setCanDelete] = useState<boolean>(false);
    const [canEnable, setCanEnable] = useState<boolean>(false);
    const [canDisable, setCanDisable] = useState<boolean>(false);
    const [canViewDefaults, setCanViewDefaults] = useState<boolean>(false);

    // OS-specific fields
    const [ppaOwner, setPpaOwner] = useState<string>('');
    const [ppaName, setPpaName] = useState<string>('');
    const [coprOwner, setCoprOwner] = useState<string>('');
    const [coprProject, setCoprProject] = useState<string>('');
    const [obsUrl, setObsUrl] = useState<string>('https://download.opensuse.org/repositories/');
    const [obsProjectPath, setObsProjectPath] = useState<string>('');
    const [obsDistroVersion, setObsDistroVersion] = useState<string>('');
    const [obsRepoName, setObsRepoName] = useState<string>('');

    // macOS Homebrew
    const [tapUser, setTapUser] = useState<string>('');
    const [tapRepo, setTapRepo] = useState<string>('');

    // FreeBSD pkg
    const [pkgRepoName, setPkgRepoName] = useState<string>('');
    const [pkgRepoUrl, setPkgRepoUrl] = useState<string>('');

    // NetBSD pkgsrc
    const [pkgsrcName, setPkgsrcName] = useState<string>('');
    const [pkgsrcUrl, setPkgsrcUrl] = useState<string>('');

    // Windows
    const [windowsRepoType, setWindowsRepoType] = useState<string>('chocolatey');
    const [windowsRepoName, setWindowsRepoName] = useState<string>('');
    const [windowsRepoUrl, setWindowsRepoUrl] = useState<string>('');

    // Computed repository string
    const [constructedRepo, setConstructedRepo] = useState<string>('');

    // Column visibility preferences for Third-Party Repositories grid
    const {
        hiddenColumns,
        setHiddenColumns,
        resetPreferences,
        getColumnVisibilityModel,
    } = useColumnVisibility('thirdpartyrepos-grid');

    // Dynamic table page sizing based on window height
    const { pageSize, pageSizeOptions } = useTablePageSize({
        reservedHeight: 350, // Account for dialog content padding and buttons
        minRows: 5,
        maxRows: 100,
    });

    // Controlled pagination state for v7
    const [paginationModel, setPaginationModel] = useState({ page: 0, pageSize: 25 });

    // Update pagination when pageSize from hook changes
    useEffect(() => {
        setPaginationModel(prev => ({ ...prev, pageSize }));
    }, [pageSize]);

    // Ensure current page size is always in options to avoid MUI warning
    const safePageSizeOptions = useMemo(() => {
        const currentPageSize = paginationModel.pageSize;
        if (!pageSizeOptions.includes(currentPageSize)) {
            return [...pageSizeOptions, currentPageSize].sort((a, b) => a - b);
        }
        return pageSizeOptions;
    }, [pageSizeOptions, paginationModel.pageSize]);

    // Load permissions
    useEffect(() => {
        const loadPermissions = async () => {
            const addPerm = await hasPermission(SecurityRoles.ADD_THIRD_PARTY_REPOSITORY);
            const deletePerm = await hasPermission(SecurityRoles.DELETE_THIRD_PARTY_REPOSITORY);
            const enablePerm = await hasPermission(SecurityRoles.ENABLE_THIRD_PARTY_REPOSITORY);
            const disablePerm = await hasPermission(SecurityRoles.DISABLE_THIRD_PARTY_REPOSITORY);
            const viewDefaultsPerm = await hasPermission(SecurityRoles.VIEW_DEFAULT_REPOSITORIES);
            setCanAdd(addPerm);
            setCanDelete(deletePerm);
            setCanEnable(enablePerm);
            setCanDisable(disablePerm);
            setCanViewDefaults(viewDefaultsPerm);
        };
        loadPermissions();
    }, []);

    // Extract OS name for API call (e.g., "Ubuntu" from "Ubuntu 25.04" or "Linux Ubuntu 25.04")
    const extractedOsName = useMemo(() => {
        if (!osName) return '';
        // Try to match common OS names
        const osPatterns = [
            'Ubuntu', 'Debian', 'RHEL', 'CentOS', 'CentOS Stream', 'Fedora',
            'Rocky Linux', 'AlmaLinux', 'openSUSE', 'SLES', 'FreeBSD', 'OpenBSD',
            'NetBSD', 'macOS', 'Windows'
        ];
        for (const pattern of osPatterns) {
            if (osName.includes(pattern)) {
                return pattern;
            }
        }
        return '';
    }, [osName]);

    // Load default repositories for this OS
    const loadDefaultRepositories = useCallback(async () => {
        if (!extractedOsName || !canViewDefaults) {
            setDefaultRepositories([]);
            return;
        }

        try {
            const response = await axiosInstance.get(
                `/api/default-repositories/by-os/${encodeURIComponent(extractedOsName)}`
            );
            setDefaultRepositories(response.data || []);
        } catch {
            // Silently fail - defaults are optional
            setDefaultRepositories([]);
        }
    }, [extractedOsName, canViewDefaults]);

    // Load repositories
    const loadRepositories = useCallback(async () => {
        if (!privilegedMode) {
            return;
        }

        setLoading(true);
        setError(null);

        try {
            const response = await axiosInstance.get(
                `/api/hosts/${hostId}/third-party-repos`
            );
            const repos = response.data.repositories || [];
            // Add unique IDs for DataGrid and mark as not default
            const reposWithIds = repos.map((repo: ThirdPartyRepository, index: number) => ({
                ...repo,
                id: `host-${repo.name}-${index}`,
                isDefault: false,
            }));
            setRepositories(reposWithIds);
        } catch (err: unknown) {
            const errorMessage = (err as { response?: { data?: { detail?: string } } }).response?.data?.detail || t('thirdPartyRepos.loadError');
            setError(errorMessage);
        } finally {
            setLoading(false);
        }
    }, [hostId, privilegedMode, t]);

    // Build constructed repository string based on OS
    useEffect(() => {
        if (osName.includes('Ubuntu') || osName.includes('Debian')) {
            if (ppaOwner && ppaName) {
                setConstructedRepo(`ppa:${ppaOwner}/${ppaName}`);
            } else {
                setConstructedRepo('');
            }
        } else if (osName.includes('Fedora') || osName.includes('RHEL') || osName.includes('CentOS')) {
            if (coprOwner && coprProject) {
                setConstructedRepo(`${coprOwner}/${coprProject}`);
            } else {
                setConstructedRepo('');
            }
        } else if (osName.includes('SUSE') || osName.includes('openSUSE')) {
            if (obsUrl && obsProjectPath && obsDistroVersion && obsRepoName) {
                const cleanUrl = obsUrl.endsWith('/') ? obsUrl : obsUrl + '/';
                setConstructedRepo(`${cleanUrl}${obsProjectPath}/${obsDistroVersion}/${obsRepoName}`);
            } else {
                setConstructedRepo('');
            }
        } else if (osName.includes('macOS') || osName.includes('Darwin')) {
            if (tapUser && tapRepo) {
                setConstructedRepo(`${tapUser}/${tapRepo}`);
            } else {
                setConstructedRepo('');
            }
        } else if (osName.includes('FreeBSD')) {
            if (pkgRepoName && pkgRepoUrl) {
                setConstructedRepo(pkgRepoName);
            } else {
                setConstructedRepo('');
            }
        } else if (osName.includes('NetBSD')) {
            if (pkgsrcName && pkgsrcUrl) {
                setConstructedRepo(pkgsrcName);
            } else {
                setConstructedRepo('');
            }
        } else if (osName.includes('Windows')) {
            if (windowsRepoName && windowsRepoUrl) {
                setConstructedRepo(windowsRepoName);
            } else {
                setConstructedRepo('');
            }
        }
    }, [ppaOwner, ppaName, coprOwner, coprProject, obsUrl, obsProjectPath, obsDistroVersion, obsRepoName, tapUser, tapRepo, pkgRepoName, pkgRepoUrl, pkgsrcName, pkgsrcUrl, windowsRepoName, windowsRepoUrl, osName]);

    useEffect(() => {
        loadRepositories();
        loadDefaultRepositories();
        // Auto-refresh every 30 seconds
        const refreshInterval = setInterval(() => {
            loadRepositories();
            loadDefaultRepositories();
        }, 30000);
        return () => clearInterval(refreshInterval);
    }, [hostId, privilegedMode, loadRepositories, loadDefaultRepositories]);

    // Combine host repositories with default repositories, filtering out duplicates
    const combinedRepositories = useMemo(() => {
        // Convert default repositories to the ThirdPartyRepository format
        const defaultRepos: ThirdPartyRepository[] = defaultRepositories.map((repo, index) => ({
            id: `default-${repo.id}-${index}`,
            name: repo.repository_url,
            type: repo.package_manager,
            url: repo.repository_url,
            enabled: true, // Default repositories are always shown as enabled
            isDefault: true,
        }));

        // Create a set of default repo names for deduplication
        // Use the name field (which is repository_url for defaults) for comparison
        const defaultNames = new Set(defaultRepositories.map(r => r.repository_url.toLowerCase()));

        // Filter host repositories to exclude any that match default names
        // This prevents showing the same repository twice (once as Default, once as Host-Specific)
        const filteredHostRepos = repositories.filter(repo => {
            const repoName = (repo.name || '').toLowerCase();
            return !defaultNames.has(repoName);
        });

        // Return defaults first, then host-specific repos
        return [...defaultRepos, ...filteredHostRepos];
    }, [repositories, defaultRepositories]);

    const handleAddRepository = async () => {
        if (!constructedRepo.trim()) {
            setError(t('thirdPartyRepos.repoIdentifierRequired'));
            return;
        }

        setLoading(true);
        setError(null);

        try {
            const payload: { repository: string; url?: string; type?: string } = {
                repository: constructedRepo,
            };

            // For SUSE, FreeBSD, NetBSD, and Windows, we need the full URL
            if (osName.includes('SUSE') || osName.includes('openSUSE')) {
                payload.url = constructedRepo;
            } else if (osName.includes('FreeBSD')) {
                payload.url = pkgRepoUrl;
            } else if (osName.includes('NetBSD')) {
                payload.url = pkgsrcUrl;
            } else if (osName.includes('Windows')) {
                payload.url = windowsRepoUrl;
                payload.type = windowsRepoType;
            }

            await axiosInstance.post(`/api/hosts/${hostId}/third-party-repos`, payload);
            setSuccess(t('thirdPartyRepos.addSuccess'));
            setAddDialogOpen(false);

            // Reset all fields
            setPpaOwner('');
            setPpaName('');
            setCoprOwner('');
            setCoprProject('');
            setObsUrl('https://download.opensuse.org/repositories/');
            setObsProjectPath('');
            setObsDistroVersion('');
            setObsRepoName('');
            setTapUser('');
            setTapRepo('');
            setPkgRepoName('');
            setPkgRepoUrl('');
            setPkgsrcName('');
            setPkgsrcUrl('');
            setWindowsRepoType('chocolatey');
            setWindowsRepoName('');
            setWindowsRepoUrl('');
            setConstructedRepo('');

            // Wait a moment for the agent to process and then refresh
            setTimeout(() => loadRepositories(), 2000);
        } catch (err: unknown) {
            const errorMessage = (err as { response?: { data?: { detail?: string } } }).response?.data?.detail || t('thirdPartyRepos.addError');
            setError(errorMessage);
        } finally {
            setLoading(false);
        }
    };

    const handleDeleteSelected = async () => {
        if (selectedRows.length === 0) {
            return;
        }

        setLoading(true);
        setError(null);

        try {
            const reposToDelete = repositories.filter((repo) =>
                selectedRows.includes(repo.id)
            );

            await axiosInstance.delete(`/api/hosts/${hostId}/third-party-repos`, {
                data: {
                    repositories: reposToDelete.map((repo) => ({
                        name: repo.name,
                        type: repo.type,
                        file_path: repo.file_path,
                    })),
                },
            });

            setSuccess(t('thirdPartyRepos.deleteSuccess'));
            setSelectedRows([]);
            // Wait a moment for the agent to process and then refresh
            setTimeout(() => loadRepositories(), 2000);
        } catch (err: unknown) {
            const errorMessage = (err as { response?: { data?: { detail?: string } } }).response?.data?.detail || t('thirdPartyRepos.deleteError');
            setError(errorMessage);
        } finally {
            setLoading(false);
        }
    };

    const handleEnableSelected = async () => {
        if (selectedRows.length === 0) {
            return;
        }

        setLoading(true);
        setError(null);

        try {
            const reposToEnable = repositories.filter((repo) =>
                selectedRows.includes(repo.id)
            );

            await axiosInstance.post(`/api/hosts/${hostId}/third-party-repos/enable`, {
                repositories: reposToEnable.map((repo) => ({
                    name: repo.name,
                    type: repo.type,
                    file_path: repo.file_path,
                })),
            });

            setSuccess(t('thirdPartyRepos.enableSuccess'));
            setSelectedRows([]);
            // Wait a moment for the agent to process and then refresh
            setTimeout(() => loadRepositories(), 2000);
        } catch (err: unknown) {
            const errorMessage = (err as { response?: { data?: { detail?: string } } }).response?.data?.detail || t('thirdPartyRepos.enableError');
            setError(errorMessage);
        } finally {
            setLoading(false);
        }
    };

    const handleDisableSelected = async () => {
        if (selectedRows.length === 0) {
            return;
        }

        setLoading(true);
        setError(null);

        try {
            const reposToDisable = repositories.filter((repo) =>
                selectedRows.includes(repo.id)
            );

            await axiosInstance.post(`/api/hosts/${hostId}/third-party-repos/disable`, {
                repositories: reposToDisable.map((repo) => ({
                    name: repo.name,
                    type: repo.type,
                    file_path: repo.file_path,
                })),
            });

            setSuccess(t('thirdPartyRepos.disableSuccess'));
            setSelectedRows([]);
            // Wait a moment for the agent to process and then refresh
            setTimeout(() => loadRepositories(), 2000);
        } catch (err: unknown) {
            const errorMessage = (err as { response?: { data?: { detail?: string } } }).response?.data?.detail || t('thirdPartyRepos.disableError');
            setError(errorMessage);
        } finally {
            setLoading(false);
        }
    };

    const getRepoTypeHelperText = () => {
        if (osName === 'Ubuntu' || osName === 'Debian') {
            return t('thirdPartyRepos.ppaHelp');
        } else if (osName.includes('Fedora') || osName.includes('RHEL') || osName.includes('CentOS')) {
            return t('thirdPartyRepos.coprHelp');
        } else if (osName.includes('SUSE') || osName.includes('openSUSE')) {
            return t('thirdPartyRepos.obsHelp');
        }
        return '';
    };

    const columns: GridColDef[] = [
        {
            field: 'name',
            headerName: t('thirdPartyRepos.name'),
            flex: 2,
            minWidth: 200,
        },
        {
            field: 'type',
            headerName: t('thirdPartyRepos.type'),
            flex: 1,
            minWidth: 100,
        },
        {
            field: 'url',
            headerName: t('thirdPartyRepos.url'),
            flex: 3,
            minWidth: 300,
        },
        {
            field: 'isDefault',
            headerName: t('thirdPartyRepos.source'),
            flex: 1,
            minWidth: 100,
            renderCell: (params) => {
                const isDefault = params.value;
                return (
                    <Chip
                        label={isDefault ? t('thirdPartyRepos.default') : t('thirdPartyRepos.hostSpecific')}
                        color={isDefault ? 'info' : 'default'}
                        size="small"
                        variant="outlined"
                    />
                );
            },
        },
        {
            field: 'enabled',
            headerName: t('thirdPartyRepos.enabled'),
            flex: 1,
            minWidth: 100,
            renderCell: (params) => {
                const isEnabled = params.value;
                if (isEnabled === undefined || isEnabled === null) {
                    return <span style={{ color: '#666', fontStyle: 'italic' }}>Unknown</span>;
                }
                return (
                    <Chip
                        label={isEnabled ? t('common.yes') : t('common.no')}
                        color={isEnabled ? 'success' : 'error'}
                        size="small"
                        variant="filled"
                    />
                );
            },
        },
    ];

    if (!privilegedMode) {
        return (
            <Box sx={{ p: 3 }}>
                <Alert severity="warning">
                    {t('thirdPartyRepos.privilegedModeRequired')}
                </Alert>
            </Box>
        );
    }

    return (
        <Box sx={{
            display: 'flex',
            flexDirection: 'column',
            height: 'calc(100vh - 120px)', // Full viewport height minus navbar and padding
            gap: 2,
            p: 2
        }}>
            {/* Header Row */}
            <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexShrink: 0 }}>
                <Typography variant="h6">{t('thirdPartyRepos.title')}</Typography>
                <Button
                    variant="outlined"
                    startIcon={<RefreshIcon />}
                    onClick={loadRepositories}
                    disabled={loading}
                >
                    {t('common.refresh')}
                </Button>
            </Box>

            {/* Error and Success Alerts */}
            {error && (
                <Alert severity="error" sx={{ flexShrink: 0 }} onClose={() => setError(null)}>
                    {error}
                </Alert>
            )}

            {success && (
                <Alert severity="success" sx={{ flexShrink: 0 }} onClose={() => setSuccess(null)}>
                    {success}
                </Alert>
            )}

            {/* Loading Spinner or DataGrid */}
            {loading && combinedRepositories.length === 0 ? (
                <Box sx={{ display: 'flex', justifyContent: 'center', p: 3, flexShrink: 0 }}>
                    <CircularProgress />
                </Box>
            ) : (
                <>
                    {/* Column Visibility Button */}
                    <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'flex-end', flexShrink: 0 }}>
                        <ColumnVisibilityButton
                            columns={columns.map(col => ({ field: col.field, headerName: col.headerName || col.field }))}
                            hiddenColumns={hiddenColumns}
                            onColumnsChange={setHiddenColumns}
                            onReset={resetPreferences}
                        />
                    </Box>

                    {/* DataGrid - flexGrow to fill available space */}
                    <Box sx={{ flexGrow: 1, minHeight: 0 }}>
                        <DataGrid
                            rows={combinedRepositories}
                            columns={columns}
                            loading={loading}
                            checkboxSelection={canDelete || canEnable || canDisable}
                            disableRowSelectionOnClick
                            isRowSelectable={(params) => !params.row.isDefault}
                            onRowSelectionModelChange={(newSelection) => {
                                // Filter out any default repository IDs that might have been selected
                                const filteredSelection = newSelection.filter(id => {
                                    const row = combinedRepositories.find(r => r.id === id);
                                    return row && !row.isDefault;
                                });
                                setSelectedRows(filteredSelection);
                            }}
                            rowSelectionModel={selectedRows}
                            paginationModel={paginationModel}
                            onPaginationModelChange={setPaginationModel}
                            pageSizeOptions={safePageSizeOptions}
                            columnVisibilityModel={getColumnVisibilityModel()}
                            sx={{
                                '& .MuiDataGrid-cell': {
                                    borderBottom: '1px solid rgba(224, 224, 224, 1)',
                                },
                            }}
                        />
                    </Box>
                </>
            )}

            {/* Action buttons at bottom */}
            <Box sx={{ display: 'flex', gap: 2, flexShrink: 0 }}>
                <Button
                    variant="contained"
                    startIcon={<AddIcon />}
                    onClick={() => setAddDialogOpen(true)}
                    disabled={!canAdd || !privilegedMode || loading}
                >
                    {t('thirdPartyRepos.addRepository')}
                </Button>
                <Button
                    variant="contained"
                    color="success"
                    startIcon={<CheckCircleIcon />}
                    onClick={handleEnableSelected}
                    disabled={!canEnable || !privilegedMode || selectedRows.length === 0 || loading}
                >
                    {t('thirdPartyRepos.enableSelected', { count: selectedRows.length })}
                </Button>
                <Button
                    variant="contained"
                    color="warning"
                    startIcon={<CancelIcon />}
                    onClick={handleDisableSelected}
                    disabled={!canDisable || !privilegedMode || selectedRows.length === 0 || loading}
                >
                    {t('thirdPartyRepos.disableSelected', { count: selectedRows.length })}
                </Button>
                <Button
                    variant="contained"
                    color="error"
                    startIcon={<DeleteIcon />}
                    onClick={handleDeleteSelected}
                    disabled={!canDelete || !privilegedMode || selectedRows.length === 0 || loading}
                >
                    {t('thirdPartyRepos.deleteSelected', { count: selectedRows.length })}
                </Button>
            </Box>

            {/* Add Repository Dialog */}
            <Dialog open={addDialogOpen} onClose={() => setAddDialogOpen(false)} maxWidth="sm" fullWidth>
                <DialogTitle>{t('thirdPartyRepos.addRepository')}</DialogTitle>
                <DialogContent>
                    <Box sx={{ pt: 2 }}>
                        <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
                            {getRepoTypeHelperText()}
                        </Typography>

                        {/* Debug: Show OS Name */}
                        {osName && (
                            <Typography variant="caption" color="text.secondary" sx={{ mb: 2, display: 'block' }}>
                                Detected OS: {osName}
                            </Typography>
                        )}

                        {/* Ubuntu/Debian PPA Fields */}
                        {(osName.includes('Ubuntu') || osName.includes('Debian')) && (
                            <>
                                <TextField
                                    autoFocus
                                    fullWidth
                                    label={t('thirdPartyRepos.ppaOwner', 'PPA Owner')}
                                    value={ppaOwner}
                                    onChange={(e) => setPpaOwner(e.target.value)}
                                    sx={{ mb: 2 }}
                                    helperText={t('thirdPartyRepos.ppaOwnerHelp', 'e.g., deadsnakes')}
                                />
                                <TextField
                                    fullWidth
                                    label={t('thirdPartyRepos.ppaName', 'PPA Name')}
                                    value={ppaName}
                                    onChange={(e) => setPpaName(e.target.value)}
                                    sx={{ mb: 2 }}
                                    helperText={t('thirdPartyRepos.ppaNameHelp', 'e.g., ppa')}
                                />
                                {constructedRepo && (
                                    <Box sx={{ mb: 2, p: 2, bgcolor: 'action.hover', border: 1, borderColor: 'divider', borderRadius: 1 }}>
                                        <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 0.5 }}>
                                            {t('thirdPartyRepos.ppaIdentifier', 'PPA Identifier')}:
                                        </Typography>
                                        <Typography variant="body2" color="text.primary" sx={{ fontFamily: 'monospace', fontWeight: 500 }}>
                                            {constructedRepo}
                                        </Typography>
                                    </Box>
                                )}
                            </>
                        )}

                        {/* CentOS/RHEL/Fedora COPR Fields */}
                        {(osName.includes('Fedora') || osName.includes('RHEL') || osName.includes('CentOS')) && (
                            <>
                                <TextField
                                    autoFocus
                                    fullWidth
                                    label={t('thirdPartyRepos.coprOwner', 'COPR Owner')}
                                    value={coprOwner}
                                    onChange={(e) => setCoprOwner(e.target.value)}
                                    sx={{ mb: 2 }}
                                    helperText={t('thirdPartyRepos.coprOwnerHelp', 'e.g., @python')}
                                />
                                <TextField
                                    fullWidth
                                    label={t('thirdPartyRepos.coprProject', 'COPR Project')}
                                    value={coprProject}
                                    onChange={(e) => setCoprProject(e.target.value)}
                                    sx={{ mb: 2 }}
                                    helperText={t('thirdPartyRepos.coprProjectHelp', 'e.g., python3.11')}
                                />
                                {constructedRepo && (
                                    <Box sx={{ mb: 2, p: 2, bgcolor: 'action.hover', border: 1, borderColor: 'divider', borderRadius: 1 }}>
                                        <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 0.5 }}>
                                            {t('thirdPartyRepos.coprIdentifier', 'COPR Identifier')}:
                                        </Typography>
                                        <Typography variant="body2" color="text.primary" sx={{ fontFamily: 'monospace', fontWeight: 500 }}>
                                            {constructedRepo}
                                        </Typography>
                                    </Box>
                                )}
                            </>
                        )}

                        {/* SUSE/openSUSE OBS Fields */}
                        {(osName.includes('SUSE') || osName.includes('openSUSE')) && (
                            <>
                                <TextField
                                    autoFocus
                                    fullWidth
                                    label={t('thirdPartyRepos.obsUrl', 'Base URL')}
                                    value={obsUrl}
                                    onChange={(e) => setObsUrl(e.target.value)}
                                    sx={{ mb: 2 }}
                                    helperText={t('thirdPartyRepos.obsUrlHelp', 'Base URL for OBS repositories')}
                                />
                                <TextField
                                    fullWidth
                                    label={t('thirdPartyRepos.obsProjectPath', 'Project Path')}
                                    value={obsProjectPath}
                                    onChange={(e) => setObsProjectPath(e.target.value)}
                                    sx={{ mb: 2 }}
                                    helperText={t('thirdPartyRepos.obsProjectPathHelp', 'e.g., devel:languages:python')}
                                />
                                <TextField
                                    fullWidth
                                    label={t('thirdPartyRepos.obsDistroVersion', 'Distribution Version')}
                                    value={obsDistroVersion}
                                    onChange={(e) => setObsDistroVersion(e.target.value)}
                                    sx={{ mb: 2 }}
                                    helperText={t('thirdPartyRepos.obsDistroVersionHelp', 'e.g., openSUSE_Tumbleweed')}
                                />
                                <TextField
                                    fullWidth
                                    label={t('thirdPartyRepos.obsRepoName', 'Repository Name')}
                                    value={obsRepoName}
                                    onChange={(e) => setObsRepoName(e.target.value)}
                                    sx={{ mb: 2 }}
                                    helperText={t('thirdPartyRepos.obsRepoNameHelp', 'e.g., python-devel')}
                                />
                                {constructedRepo && (
                                    <Box sx={{ mb: 2, p: 2, bgcolor: 'action.hover', border: 1, borderColor: 'divider', borderRadius: 1 }}>
                                        <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 0.5 }}>
                                            {t('thirdPartyRepos.obsUrl', 'OBS Repository URL')}:
                                        </Typography>
                                        <Typography variant="body2" color="text.primary" sx={{ fontFamily: 'monospace', fontWeight: 500, wordBreak: 'break-all' }}>
                                            {constructedRepo}
                                        </Typography>
                                    </Box>
                                )}
                            </>
                        )}

                        {/* macOS Homebrew Tap Fields */}
                        {(osName.includes('macOS') || osName.includes('Darwin')) && (
                            <>
                                <TextField
                                    autoFocus
                                    fullWidth
                                    label={t('thirdPartyRepos.tapUser', 'Tap User/Org')}
                                    value={tapUser}
                                    onChange={(e) => setTapUser(e.target.value)}
                                    sx={{ mb: 2 }}
                                    helperText={t('thirdPartyRepos.tapUserHelp', 'e.g., homebrew')}
                                />
                                <TextField
                                    fullWidth
                                    label={t('thirdPartyRepos.tapRepo', 'Tap Repository')}
                                    value={tapRepo}
                                    onChange={(e) => setTapRepo(e.target.value)}
                                    sx={{ mb: 2 }}
                                    helperText={t('thirdPartyRepos.tapRepoHelp', 'e.g., cask-versions')}
                                />
                                {constructedRepo && (
                                    <Box sx={{ mb: 2, p: 2, bgcolor: 'action.hover', border: 1, borderColor: 'divider', borderRadius: 1 }}>
                                        <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 0.5 }}>
                                            {t('thirdPartyRepos.tapIdentifier', 'Tap Identifier')}:
                                        </Typography>
                                        <Typography variant="body2" color="text.primary" sx={{ fontFamily: 'monospace', fontWeight: 500 }}>
                                            {constructedRepo}
                                        </Typography>
                                    </Box>
                                )}
                            </>
                        )}

                        {/* FreeBSD pkg Repository Fields */}
                        {osName.includes('FreeBSD') && (
                            <>
                                <TextField
                                    autoFocus
                                    fullWidth
                                    label={t('thirdPartyRepos.pkgRepoName', 'Repository Name')}
                                    value={pkgRepoName}
                                    onChange={(e) => setPkgRepoName(e.target.value)}
                                    sx={{ mb: 2 }}
                                    helperText={t('thirdPartyRepos.pkgRepoNameHelp', 'e.g., my-custom-repo')}
                                />
                                <TextField
                                    fullWidth
                                    label={t('thirdPartyRepos.pkgRepoUrl', 'Repository URL')}
                                    value={pkgRepoUrl}
                                    onChange={(e) => setPkgRepoUrl(e.target.value)}
                                    sx={{ mb: 2 }}
                                    helperText={t('thirdPartyRepos.pkgRepoUrlHelp', 'e.g., http://example.com/packages')}
                                />
                                {constructedRepo && (
                                    <Box sx={{ mb: 2, p: 2, bgcolor: 'action.hover', border: 1, borderColor: 'divider', borderRadius: 1 }}>
                                        <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 0.5 }}>
                                            {t('thirdPartyRepos.pkgRepoIdentifier', 'Repository Name')}:
                                        </Typography>
                                        <Typography variant="body2" color="text.primary" sx={{ fontFamily: 'monospace', fontWeight: 500 }}>
                                            {constructedRepo}
                                        </Typography>
                                        <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 1, mb: 0.5 }}>
                                            URL:
                                        </Typography>
                                        <Typography variant="body2" color="text.primary" sx={{ fontFamily: 'monospace', fontWeight: 500, wordBreak: 'break-all' }}>
                                            {pkgRepoUrl}
                                        </Typography>
                                    </Box>
                                )}
                            </>
                        )}

                        {/* NetBSD pkgsrc Repository Fields */}
                        {osName.includes('NetBSD') && (
                            <>
                                <TextField
                                    autoFocus
                                    fullWidth
                                    label={t('thirdPartyRepos.pkgsrcName', 'Repository Name')}
                                    value={pkgsrcName}
                                    onChange={(e) => setPkgsrcName(e.target.value)}
                                    sx={{ mb: 2 }}
                                    helperText={t('thirdPartyRepos.pkgsrcNameHelp', 'e.g., wip or custom-packages')}
                                />
                                <TextField
                                    fullWidth
                                    label={t('thirdPartyRepos.pkgsrcUrl', 'Git Repository URL')}
                                    value={pkgsrcUrl}
                                    onChange={(e) => setPkgsrcUrl(e.target.value)}
                                    sx={{ mb: 2 }}
                                    helperText={t('thirdPartyRepos.pkgsrcUrlHelp', 'e.g., https://github.com/NetBSD/pkgsrc-wip')}
                                />
                                {constructedRepo && (
                                    <Box sx={{ mb: 2, p: 2, bgcolor: 'action.hover', border: 1, borderColor: 'divider', borderRadius: 1 }}>
                                        <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 0.5 }}>
                                            {t('thirdPartyRepos.pkgsrcIdentifier', 'Repository Name')}:
                                        </Typography>
                                        <Typography variant="body2" color="text.primary" sx={{ fontFamily: 'monospace', fontWeight: 500 }}>
                                            {constructedRepo}
                                        </Typography>
                                        <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 1, mb: 0.5 }}>
                                            URL:
                                        </Typography>
                                        <Typography variant="body2" color="text.primary" sx={{ fontFamily: 'monospace', fontWeight: 500, wordBreak: 'break-all' }}>
                                            {pkgsrcUrl}
                                        </Typography>
                                    </Box>
                                )}
                            </>
                        )}

                        {/* Windows Repository Fields */}
                        {osName.includes('Windows') && (
                            <>
                                <TextField
                                    select
                                    fullWidth
                                    label={t('thirdPartyRepos.windowsType', 'Repository Type')}
                                    value={windowsRepoType}
                                    onChange={(e) => setWindowsRepoType(e.target.value)}
                                    sx={{ mb: 2 }}
                                    helperText={t('thirdPartyRepos.windowsTypeHelp', 'Choose Chocolatey or winget')}
                                    SelectProps={{
                                        native: true,
                                    }}
                                >
                                    <option value="chocolatey">Chocolatey</option>
                                    <option value="winget">winget</option>
                                </TextField>
                                <TextField
                                    fullWidth
                                    label={t('thirdPartyRepos.windowsName', 'Repository Name')}
                                    value={windowsRepoName}
                                    onChange={(e) => setWindowsRepoName(e.target.value)}
                                    sx={{ mb: 2 }}
                                    helperText={t('thirdPartyRepos.windowsNameHelp', 'e.g., mycompany-repo')}
                                />
                                <TextField
                                    fullWidth
                                    label={t('thirdPartyRepos.windowsUrl', 'Repository URL')}
                                    value={windowsRepoUrl}
                                    onChange={(e) => setWindowsRepoUrl(e.target.value)}
                                    sx={{ mb: 2 }}
                                    helperText={t('thirdPartyRepos.windowsUrlHelp', 'e.g., https://mycompany.com/chocolatey')}
                                />
                                {constructedRepo && (
                                    <Box sx={{ mb: 2, p: 2, bgcolor: 'action.hover', border: 1, borderColor: 'divider', borderRadius: 1 }}>
                                        <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 0.5 }}>
                                            {t('thirdPartyRepos.windowsIdentifier', 'Repository Name')}:
                                        </Typography>
                                        <Typography variant="body2" color="text.primary" sx={{ fontFamily: 'monospace', fontWeight: 500 }}>
                                            {constructedRepo}
                                        </Typography>
                                        <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 1, mb: 0.5 }}>
                                            Type:
                                        </Typography>
                                        <Typography variant="body2" color="text.primary" sx={{ fontFamily: 'monospace', fontWeight: 500 }}>
                                            {windowsRepoType}
                                        </Typography>
                                        <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 1, mb: 0.5 }}>
                                            URL:
                                        </Typography>
                                        <Typography variant="body2" color="text.primary" sx={{ fontFamily: 'monospace', fontWeight: 500, wordBreak: 'break-all' }}>
                                            {windowsRepoUrl}
                                        </Typography>
                                    </Box>
                                )}
                            </>
                        )}
                    </Box>
                </DialogContent>
                <DialogActions>
                    <Button onClick={() => setAddDialogOpen(false)} disabled={loading}>
                        {t('common.cancel')}
                    </Button>
                    <Button onClick={handleAddRepository} variant="contained" disabled={loading}>
                        {loading ? <CircularProgress size={24} /> : t('common.add')}
                    </Button>
                </DialogActions>
            </Dialog>
        </Box>
    );
};

export default ThirdPartyRepositories;
