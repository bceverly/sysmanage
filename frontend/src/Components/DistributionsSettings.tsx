import React, { useEffect, useState, useCallback, useMemo } from 'react';
import { DataGrid, GridColDef, GridRowSelectionModel } from '@mui/x-data-grid';
import { useTranslation } from 'react-i18next';
import { useTablePageSize } from '../hooks/useTablePageSize';
import { useColumnVisibility } from '../hooks/useColumnVisibility';
import Box from '@mui/material/Box';
import Stack from '@mui/material/Stack';
import Button from '@mui/material/Button';
import AddIcon from '@mui/icons-material/Add';
import EditIcon from '@mui/icons-material/Edit';
import DeleteIcon from '@mui/icons-material/Delete';
import Dialog from '@mui/material/Dialog';
import DialogActions from '@mui/material/DialogActions';
import DialogContent from '@mui/material/DialogContent';
import DialogContentText from '@mui/material/DialogContentText';
import DialogTitle from '@mui/material/DialogTitle';
import TextField from '@mui/material/TextField';
import Chip from '@mui/material/Chip';
import Switch from '@mui/material/Switch';
import FormControlLabel from '@mui/material/FormControlLabel';
import MenuItem from '@mui/material/MenuItem';
import Typography from '@mui/material/Typography';
import Snackbar from '@mui/material/Snackbar';
import Alert from '@mui/material/Alert';
import SearchBox from './SearchBox';
import ColumnVisibilityButton from './ColumnVisibilityButton';
import { hasPermission, SecurityRoles } from '../Services/permissions';
import {
    Distribution,
    CreateDistributionRequest,
    distributionService,
} from '../Services/childHostDistributions';

interface AxiosError {
    response?: {
        data?: {
            detail?: string;
        };
    };
}

const DistributionsSettings: React.FC = () => {
    const [tableData, setTableData] = useState<Distribution[]>([]);
    const [filteredData, setFilteredData] = useState<Distribution[]>([]);
    const [selection, setSelection] = useState<GridRowSelectionModel>([]);
    const [loading, setLoading] = useState<boolean>(true);
    const [addDialogOpen, setAddDialogOpen] = useState(false);
    const [editDialogOpen, setEditDialogOpen] = useState(false);
    const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
    const [editDistribution, setEditDistribution] = useState<Distribution | null>(null);
    const [searchTerm, setSearchTerm] = useState<string>('');
    const [searchColumn, setSearchColumn] = useState<string>('display_name');

    // Form state
    const [formData, setFormData] = useState<CreateDistributionRequest>({
        child_type: 'wsl',
        distribution_name: '',
        distribution_version: '',
        display_name: '',
        install_identifier: '',
        executable_name: '',
        agent_install_method: '',
        agent_install_commands: '',
        is_active: true,
        min_agent_version: '',
        notes: '',
    });

    // Permission states
    const [canConfigure, setCanConfigure] = useState<boolean>(false);

    // Snackbar state
    const [snackbar, setSnackbar] = useState<{
        open: boolean;
        message: string;
        severity: 'success' | 'error' | 'info' | 'warning';
    }>({
        open: false,
        message: '',
        severity: 'success',
    });

    const { t } = useTranslation();

    // Dynamic table page sizing based on window height
    const { pageSize, pageSizeOptions } = useTablePageSize({
        reservedHeight: 350,
        minRows: 5,
        maxRows: 100,
    });

    // Controlled pagination state
    const [paginationModel, setPaginationModel] = useState({ page: 0, pageSize: 10 });

    // Update pagination when pageSize from hook changes
    useEffect(() => {
        setPaginationModel(prev => ({ ...prev, pageSize }));
    }, [pageSize]);

    // Ensure current page size is always in options
    const safePageSizeOptions = useMemo(() => {
        const currentPageSize = paginationModel.pageSize;
        if (!pageSizeOptions.includes(currentPageSize)) {
            return [...pageSizeOptions, currentPageSize].sort((a, b) => a - b);
        }
        return pageSizeOptions;
    }, [pageSizeOptions, paginationModel.pageSize]);

    // Column visibility preferences
    const {
        hiddenColumns,
        setHiddenColumns,
        resetPreferences,
        getColumnVisibilityModel,
    } = useColumnVisibility('distributions-grid');

    const columns: GridColDef[] = [
        {
            field: 'child_type',
            headerName: t('distributions.childType', 'Type'),
            width: 100,
            renderCell: (params) => (
                <Chip
                    label={params.value.toUpperCase()}
                    size="small"
                    color="primary"
                    variant="outlined"
                />
            ),
        },
        {
            field: 'display_name',
            headerName: t('distributions.displayName', 'Display Name'),
            width: 250,
        },
        {
            field: 'distribution_name',
            headerName: t('distributions.distributionName', 'Distribution'),
            width: 150,
        },
        {
            field: 'distribution_version',
            headerName: t('distributions.version', 'Version'),
            width: 100,
        },
        {
            field: 'install_identifier',
            headerName: t('distributions.installIdentifier', 'Install ID'),
            width: 180,
        },
        {
            field: 'agent_install_method',
            headerName: t('distributions.installMethod', 'Install Method'),
            width: 150,
        },
        {
            field: 'is_active',
            headerName: t('distributions.active', 'Active'),
            width: 100,
            renderCell: (params) => (
                <Chip
                    label={params.value ? t('common.yes', 'Yes') : t('common.no', 'No')}
                    size="small"
                    color={params.value ? 'success' : 'default'}
                />
            ),
        },
    ];

    const searchColumns = [
        { field: 'display_name', label: t('distributions.displayName', 'Display Name') },
        { field: 'distribution_name', label: t('distributions.distributionName', 'Distribution') },
        { field: 'child_type', label: t('distributions.childType', 'Type') },
        { field: 'install_identifier', label: t('distributions.installIdentifier', 'Install ID') },
    ];

    const childTypeOptions = [
        { value: 'wsl', label: 'WSL' },
        { value: 'lxd', label: 'LXD/LXC' },
        { value: 'virtualbox', label: 'VirtualBox' },
        { value: 'hyperv', label: 'Hyper-V' },
        { value: 'vmm', label: 'VMM/vmd (OpenBSD)' },
        { value: 'bhyve', label: 'bhyve (FreeBSD)' },
        { value: 'kvm', label: 'KVM/QEMU' },
    ];

    const installMethodOptions = [
        { value: 'apt_launchpad', label: 'APT (Launchpad PPA)' },
        { value: 'dnf_copr', label: 'DNF (COPR)' },
        { value: 'zypper_obs', label: 'Zypper (OBS)' },
        { value: 'manual', label: 'Manual' },
    ];

    // Check permissions on mount
    useEffect(() => {
        const checkPermissions = async () => {
            const canConfig = await hasPermission(SecurityRoles.CONFIGURE_CHILD_HOST);
            setCanConfigure(canConfig);
        };
        checkPermissions();
    }, []);

    // Load data on mount
    const loadData = useCallback(async () => {
        setLoading(true);
        try {
            const data = await distributionService.getAll();
            setTableData(data);
            setFilteredData(data);
        } catch (error) {
            console.error('Error loading distributions:', error);
            setSnackbar({
                open: true,
                message: t('distributions.loadError', 'Error loading distributions'),
                severity: 'error',
            });
        } finally {
            setLoading(false);
        }
    }, [t]);

    useEffect(() => {
        loadData();
    }, [loadData]);

    // Filter data based on search
    useEffect(() => {
        if (!searchTerm) {
            setFilteredData(tableData);
            return;
        }
        const filtered = tableData.filter((dist) => {
            const value = String(dist[searchColumn as keyof Distribution] || '').toLowerCase();
            return value.includes(searchTerm.toLowerCase());
        });
        setFilteredData(filtered);
    }, [searchTerm, searchColumn, tableData]);

    // Reset form data
    const resetFormData = () => {
        setFormData({
            child_type: 'wsl',
            distribution_name: '',
            distribution_version: '',
            display_name: '',
            install_identifier: '',
            executable_name: '',
            agent_install_method: '',
            agent_install_commands: '',
            is_active: true,
            min_agent_version: '',
            notes: '',
        });
    };

    // Handle add dialog
    const handleAddClick = () => {
        resetFormData();
        setAddDialogOpen(true);
    };

    const handleAddClose = () => {
        setAddDialogOpen(false);
        resetFormData();
    };

    const handleAddSave = async () => {
        try {
            await distributionService.create(formData);
            setSnackbar({
                open: true,
                message: t('distributions.addSuccess', 'Distribution added successfully'),
                severity: 'success',
            });
            handleAddClose();
            loadData();
        } catch (error) {
            const axiosErr = error as AxiosError;
            setSnackbar({
                open: true,
                message: axiosErr?.response?.data?.detail || t('distributions.addError', 'Error adding distribution'),
                severity: 'error',
            });
        }
    };

    // Handle edit dialog
    const handleEditClick = () => {
        if (selection.length !== 1) return;
        const dist = tableData.find((d) => d.id === selection[0]);
        if (dist) {
            setEditDistribution(dist);
            setFormData({
                child_type: dist.child_type,
                distribution_name: dist.distribution_name,
                distribution_version: dist.distribution_version,
                display_name: dist.display_name,
                install_identifier: dist.install_identifier || '',
                executable_name: dist.executable_name || '',
                agent_install_method: dist.agent_install_method || '',
                agent_install_commands: dist.agent_install_commands || '',
                is_active: dist.is_active,
                min_agent_version: dist.min_agent_version || '',
                notes: dist.notes || '',
            });
            setEditDialogOpen(true);
        }
    };

    const handleEditClose = () => {
        setEditDialogOpen(false);
        setEditDistribution(null);
        resetFormData();
    };

    const handleEditSave = async () => {
        if (!editDistribution) return;
        try {
            await distributionService.update(editDistribution.id, formData);
            setSnackbar({
                open: true,
                message: t('distributions.editSuccess', 'Distribution updated successfully'),
                severity: 'success',
            });
            handleEditClose();
            loadData();
        } catch (error) {
            const axiosErr = error as AxiosError;
            setSnackbar({
                open: true,
                message: axiosErr?.response?.data?.detail || t('distributions.editError', 'Error updating distribution'),
                severity: 'error',
            });
        }
    };

    // Handle delete dialog
    const handleDeleteClick = () => {
        if (selection.length !== 1) return;
        setDeleteDialogOpen(true);
    };

    const handleDeleteClose = () => {
        setDeleteDialogOpen(false);
    };

    const handleDeleteConfirm = async () => {
        if (selection.length !== 1) return;
        try {
            await distributionService.delete(selection[0] as string);
            setSnackbar({
                open: true,
                message: t('distributions.deleteSuccess', 'Distribution deleted successfully'),
                severity: 'success',
            });
            handleDeleteClose();
            setSelection([]);
            loadData();
        } catch (error) {
            const axiosErr = error as AxiosError;
            setSnackbar({
                open: true,
                message: axiosErr?.response?.data?.detail || t('distributions.deleteError', 'Error deleting distribution'),
                severity: 'error',
            });
        }
    };

    // Render form fields
    const renderFormFields = () => (
        <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2, mt: 2 }}>
            <TextField
                select
                label={t('distributions.childType', 'Type')}
                value={formData.child_type}
                onChange={(e) => setFormData({ ...formData, child_type: e.target.value })}
                fullWidth
                required
            >
                {childTypeOptions.map((option) => (
                    <MenuItem key={option.value} value={option.value}>
                        {option.label}
                    </MenuItem>
                ))}
            </TextField>
            <TextField
                label={t('distributions.displayName', 'Display Name')}
                value={formData.display_name}
                onChange={(e) => setFormData({ ...formData, display_name: e.target.value })}
                fullWidth
                required
                helperText={t('distributions.displayNameHelp', 'e.g., Ubuntu 24.04 LTS (Noble)')}
            />
            <Box sx={{ display: 'flex', gap: 2 }}>
                <TextField
                    label={t('distributions.distributionName', 'Distribution Name')}
                    value={formData.distribution_name}
                    onChange={(e) => setFormData({ ...formData, distribution_name: e.target.value })}
                    fullWidth
                    required
                    helperText={t('distributions.distributionNameHelp', 'e.g., Ubuntu')}
                />
                <TextField
                    label={t('distributions.version', 'Version')}
                    value={formData.distribution_version}
                    onChange={(e) => setFormData({ ...formData, distribution_version: e.target.value })}
                    fullWidth
                    required
                    helperText={t('distributions.versionHelp', 'e.g., 24.04')}
                />
            </Box>
            <TextField
                label={t('distributions.installIdentifier', 'Install Identifier')}
                value={formData.install_identifier}
                onChange={(e) => setFormData({ ...formData, install_identifier: e.target.value })}
                fullWidth
                helperText={t('distributions.installIdentifierHelp', 'WSL: Ubuntu-24.04, LXD: ubuntu:24.04')}
            />
            <TextField
                label={t('distributions.executableName', 'Executable Name')}
                value={formData.executable_name}
                onChange={(e) => setFormData({ ...formData, executable_name: e.target.value })}
                fullWidth
                helperText={t('distributions.executableNameHelp', 'WSL only: e.g., ubuntu2404.exe')}
            />
            <TextField
                select
                label={t('distributions.installMethod', 'Agent Install Method')}
                value={formData.agent_install_method}
                onChange={(e) => setFormData({ ...formData, agent_install_method: e.target.value })}
                fullWidth
            >
                <MenuItem value="">
                    <em>{t('common.none', 'None')}</em>
                </MenuItem>
                {installMethodOptions.map((option) => (
                    <MenuItem key={option.value} value={option.value}>
                        {option.label}
                    </MenuItem>
                ))}
            </TextField>
            <TextField
                label={t('distributions.installCommands', 'Agent Install Commands')}
                value={formData.agent_install_commands}
                onChange={(e) => setFormData({ ...formData, agent_install_commands: e.target.value })}
                fullWidth
                multiline
                rows={4}
                helperText={t('distributions.installCommandsHelp', 'JSON array of commands to install sysmanage-agent')}
            />
            <TextField
                label={t('distributions.minAgentVersion', 'Minimum Agent Version')}
                value={formData.min_agent_version}
                onChange={(e) => setFormData({ ...formData, min_agent_version: e.target.value })}
                fullWidth
            />
            <TextField
                label={t('distributions.notes', 'Notes')}
                value={formData.notes}
                onChange={(e) => setFormData({ ...formData, notes: e.target.value })}
                fullWidth
                multiline
                rows={2}
            />
            <FormControlLabel
                control={
                    <Switch
                        checked={formData.is_active}
                        onChange={(e) => setFormData({ ...formData, is_active: e.target.checked })}
                    />
                }
                label={t('distributions.active', 'Active')}
            />
        </Box>
    );

    return (
        <Box sx={{
            display: 'flex',
            flexDirection: 'column',
            height: 'calc(100vh - 280px)',
            gap: 2
        }}>
            <Typography variant="h5">
                {t('distributions.title', 'Child Host Distributions')}
            </Typography>
            <Typography variant="body2" color="text.secondary">
                {t('distributions.description', 'Manage the available distributions for creating child hosts (WSL instances, containers, VMs).')}
            </Typography>

            <Stack direction="row" spacing={2} sx={{ flexWrap: 'wrap' }}>
                <SearchBox
                    searchTerm={searchTerm}
                    setSearchTerm={setSearchTerm}
                    searchColumn={searchColumn}
                    setSearchColumn={setSearchColumn}
                    columns={searchColumns}
                />
                <ColumnVisibilityButton
                    columns={columns
                        .filter(col => col.field !== 'actions')
                        .map(col => ({ field: col.field, headerName: col.headerName || col.field }))}
                    hiddenColumns={hiddenColumns}
                    onColumnsChange={setHiddenColumns}
                    onReset={resetPreferences}
                />
            </Stack>

            <Box sx={{ flexGrow: 1, minHeight: 0 }}>
                <DataGrid
                    rows={filteredData}
                    columns={columns}
                    loading={loading}
                    paginationModel={paginationModel}
                    onPaginationModelChange={setPaginationModel}
                    pageSizeOptions={safePageSizeOptions}
                    checkboxSelection
                    disableRowSelectionOnClick
                    rowSelectionModel={selection}
                    onRowSelectionModelChange={setSelection}
                    columnVisibilityModel={getColumnVisibilityModel()}
                    onColumnVisibilityModelChange={(newModel) => {
                        const hidden = Object.entries(newModel)
                            .filter(([, visible]) => !visible)
                            .map(([field]) => field);
                        setHiddenColumns(hidden);
                    }}
                    sx={{ bgcolor: 'background.paper' }}
                />
            </Box>

            {canConfigure && (
                <Stack direction="row" spacing={2} sx={{ flexShrink: 0 }}>
                    <Button
                        variant="contained"
                        startIcon={<AddIcon />}
                        onClick={handleAddClick}
                    >
                        {t('distributions.add', 'Add Distribution')}
                    </Button>
                    <Button
                        variant="outlined"
                        startIcon={<EditIcon />}
                        onClick={handleEditClick}
                        disabled={selection.length !== 1}
                    >
                        {t('distributions.edit', 'Edit')}
                    </Button>
                    <Button
                        variant="outlined"
                        color="error"
                        startIcon={<DeleteIcon />}
                        onClick={handleDeleteClick}
                        disabled={selection.length !== 1}
                    >
                        {t('distributions.delete', 'Delete')}
                    </Button>
                </Stack>
            )}

            {/* Add Dialog */}
            <Dialog open={addDialogOpen} onClose={handleAddClose} maxWidth="md" fullWidth>
                <DialogTitle>{t('distributions.addTitle', 'Add Distribution')}</DialogTitle>
                <DialogContent>
                    {renderFormFields()}
                </DialogContent>
                <DialogActions>
                    <Button onClick={handleAddClose}>{t('common.cancel', 'Cancel')}</Button>
                    <Button onClick={handleAddSave} variant="contained">
                        {t('common.save', 'Save')}
                    </Button>
                </DialogActions>
            </Dialog>

            {/* Edit Dialog */}
            <Dialog open={editDialogOpen} onClose={handleEditClose} maxWidth="md" fullWidth>
                <DialogTitle>{t('distributions.editTitle', 'Edit Distribution')}</DialogTitle>
                <DialogContent>
                    {renderFormFields()}
                </DialogContent>
                <DialogActions>
                    <Button onClick={handleEditClose}>{t('common.cancel', 'Cancel')}</Button>
                    <Button onClick={handleEditSave} variant="contained">
                        {t('common.save', 'Save')}
                    </Button>
                </DialogActions>
            </Dialog>

            {/* Delete Dialog */}
            <Dialog open={deleteDialogOpen} onClose={handleDeleteClose}>
                <DialogTitle>{t('distributions.deleteTitle', 'Delete Distribution')}</DialogTitle>
                <DialogContent>
                    <DialogContentText>
                        {t('distributions.deleteConfirm', 'Are you sure you want to delete this distribution? This action cannot be undone.')}
                    </DialogContentText>
                </DialogContent>
                <DialogActions>
                    <Button onClick={handleDeleteClose}>{t('common.cancel', 'Cancel')}</Button>
                    <Button onClick={handleDeleteConfirm} color="error" variant="contained">
                        {t('common.delete', 'Delete')}
                    </Button>
                </DialogActions>
            </Dialog>

            {/* Snackbar */}
            <Snackbar
                open={snackbar.open}
                autoHideDuration={6000}
                onClose={() => setSnackbar({ ...snackbar, open: false })}
            >
                <Alert
                    onClose={() => setSnackbar({ ...snackbar, open: false })}
                    severity={snackbar.severity}
                    sx={{ width: '100%' }}
                >
                    {snackbar.message}
                </Alert>
            </Snackbar>
        </Box>
    );
};

export default DistributionsSettings;
