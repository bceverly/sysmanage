import React, { useEffect, useState, useCallback } from 'react';
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
import axiosInstance from '../Services/api';
import { hasPermission, SecurityRoles } from '../Services/permissions';

interface ThirdPartyRepository {
    id: string;
    name: string;
    type: string;
    url: string;
    enabled: boolean;
    file_path?: string;
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
    const [loading, setLoading] = useState<boolean>(false);
    const [error, setError] = useState<string | null>(null);
    const [success, setSuccess] = useState<string | null>(null);
    const [selectedRows, setSelectedRows] = useState<GridRowSelectionModel>([]);
    const [addDialogOpen, setAddDialogOpen] = useState<boolean>(false);
    const [canAdd, setCanAdd] = useState<boolean>(false);
    const [canDelete, setCanDelete] = useState<boolean>(false);
    const [canEnable, setCanEnable] = useState<boolean>(false);
    const [canDisable, setCanDisable] = useState<boolean>(false);

    // OS-specific fields
    const [ppaOwner, setPpaOwner] = useState<string>('');
    const [ppaName, setPpaName] = useState<string>('');
    const [coprOwner, setCoprOwner] = useState<string>('');
    const [coprProject, setCoprProject] = useState<string>('');
    const [obsUrl, setObsUrl] = useState<string>('https://download.opensuse.org/repositories/');
    const [obsProjectPath, setObsProjectPath] = useState<string>('');
    const [obsDistroVersion, setObsDistroVersion] = useState<string>('');
    const [obsRepoName, setObsRepoName] = useState<string>('');

    // Computed repository string
    const [constructedRepo, setConstructedRepo] = useState<string>('');

    // Load permissions
    useEffect(() => {
        const loadPermissions = async () => {
            const addPerm = await hasPermission(SecurityRoles.ADD_THIRD_PARTY_REPOSITORY);
            const deletePerm = await hasPermission(SecurityRoles.DELETE_THIRD_PARTY_REPOSITORY);
            const enablePerm = await hasPermission(SecurityRoles.ENABLE_THIRD_PARTY_REPOSITORY);
            const disablePerm = await hasPermission(SecurityRoles.DISABLE_THIRD_PARTY_REPOSITORY);
            setCanAdd(addPerm);
            setCanDelete(deletePerm);
            setCanEnable(enablePerm);
            setCanDisable(disablePerm);
        };
        loadPermissions();
    }, []);

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
            // Add unique IDs for DataGrid
            const reposWithIds = repos.map((repo: ThirdPartyRepository, index: number) => ({
                ...repo,
                id: `${repo.name}-${index}`,
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
        }
    }, [ppaOwner, ppaName, coprOwner, coprProject, obsUrl, obsProjectPath, obsDistroVersion, obsRepoName, osName]);

    useEffect(() => {
        loadRepositories();
        // Auto-refresh every 30 seconds
        const refreshInterval = setInterval(() => {
            loadRepositories();
        }, 30000);
        return () => clearInterval(refreshInterval);
    }, [hostId, privilegedMode, loadRepositories]);

    const handleAddRepository = async () => {
        if (!constructedRepo.trim()) {
            setError(t('thirdPartyRepos.repoIdentifierRequired'));
            return;
        }

        setLoading(true);
        setError(null);

        try {
            const payload: { repository: string; url?: string } = {
                repository: constructedRepo,
            };

            // For SUSE, we might need the full URL
            if (osName.includes('SUSE') || osName.includes('openSUSE')) {
                payload.url = constructedRepo;
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
        <Box sx={{ p: 3 }}>
            <Box sx={{ mb: 2, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
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

            {error && (
                <Alert severity="error" sx={{ mb: 2 }} onClose={() => setError(null)}>
                    {error}
                </Alert>
            )}

            {success && (
                <Alert severity="success" sx={{ mb: 2 }} onClose={() => setSuccess(null)}>
                    {success}
                </Alert>
            )}

            {loading && repositories.length === 0 ? (
                <Box sx={{ display: 'flex', justifyContent: 'center', p: 3 }}>
                    <CircularProgress />
                </Box>
            ) : (
                <DataGrid
                    rows={repositories}
                    columns={columns}
                    checkboxSelection={canDelete || canEnable || canDisable}
                    disableRowSelectionOnClick
                    onRowSelectionModelChange={(newSelection) => {
                        setSelectedRows(newSelection);
                    }}
                    rowSelectionModel={selectedRows}
                    autoHeight
                    pageSizeOptions={[10, 25, 50, 100]}
                    initialState={{
                        pagination: { paginationModel: { pageSize: 25 } },
                    }}
                    sx={{
                        '& .MuiDataGrid-cell': {
                            borderBottom: '1px solid rgba(224, 224, 224, 1)',
                        },
                    }}
                />
            )}

            {/* Action buttons at bottom */}
            <Box sx={{ mt: 2, display: 'flex', gap: 2 }}>
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
