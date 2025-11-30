import React, { useState, useEffect, useCallback } from 'react';
import {
  Box,
  Card,
  CardContent,
  CardHeader,
  Typography,
  Button,
  Stack,
  IconButton,
  Alert,
  Snackbar,
  CircularProgress,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  TextField,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
  Chip,
} from '@mui/material';
import {
  DataGrid,
  GridColDef,
  GridRenderCellParams,
} from '@mui/x-data-grid';
import {
  Add as AddIcon,
  Edit as EditIcon,
  Delete as DeleteIcon,
  Security as SecurityIcon,
} from '@mui/icons-material';
import { useTranslation } from 'react-i18next';
import axiosInstance from '../Services/api';
import { hasPermission, SecurityRoles } from '../Services/permissions';

interface PortEntry {
  id?: string;
  port_number: number;
  tcp: boolean;
  udp: boolean;
  ipv4: boolean;
  ipv6: boolean;
}

interface FirewallRole {
  id: string;
  name: string;
  created_at: string;
  created_by: string | null;
  updated_at: string | null;
  updated_by: string | null;
  open_ports: PortEntry[];
}

interface CommonPort {
  port: number;
  name: string;
  default_protocol: string;
}

interface CommonPortsResponse {
  ports: CommonPort[];
}

const FirewallRolesSettings: React.FC = () => {
  const { t } = useTranslation();

  // Data state
  const [roles, setRoles] = useState<FirewallRole[]>([]);
  const [commonPorts, setCommonPorts] = useState<CommonPort[]>([]);

  // UI state
  const [loading, setLoading] = useState<boolean>(true);
  const [saving, setSaving] = useState<boolean>(false);
  const [snackbarOpen, setSnackbarOpen] = useState<boolean>(false);
  const [snackbarMessage, setSnackbarMessage] = useState<string>('');
  const [snackbarSeverity, setSnackbarSeverity] = useState<'success' | 'error'>('success');

  // Permission state
  const [canAdd, setCanAdd] = useState<boolean>(false);
  const [canEdit, setCanEdit] = useState<boolean>(false);
  const [canDelete, setCanDelete] = useState<boolean>(false);
  const [canView, setCanView] = useState<boolean>(false);

  // Dialog state
  const [dialogOpen, setDialogOpen] = useState<boolean>(false);
  const [editingRole, setEditingRole] = useState<FirewallRole | null>(null);
  const [roleName, setRoleName] = useState<string>('');
  const [openPorts, setOpenPorts] = useState<PortEntry[]>([]);

  // Port form state
  const [selectedPort, setSelectedPort] = useState<string>('');
  const [customPort, setCustomPort] = useState<string>('');
  const [portProtocol, setPortProtocol] = useState<'tcp' | 'udp' | 'both'>('tcp');
  const [ipVersion, setIpVersion] = useState<'ipv4' | 'ipv6' | 'both'>('both');
  const [startPort, setStartPort] = useState<string>('');
  const [endPort, setEndPort] = useState<string>('');

  // Delete confirmation dialog
  const [deleteDialogOpen, setDeleteDialogOpen] = useState<boolean>(false);
  const [roleToDelete, setRoleToDelete] = useState<FirewallRole | null>(null);

  // Selection state for grid
  const [selectedRows, setSelectedRows] = useState<string[]>([]);

  // Check permissions
  useEffect(() => {
    const checkPermissions = async () => {
      const [addPerm, editPerm, deletePerm, viewPerm] = await Promise.all([
        hasPermission(SecurityRoles.ADD_FIREWALL_ROLE),
        hasPermission(SecurityRoles.EDIT_FIREWALL_ROLE),
        hasPermission(SecurityRoles.DELETE_FIREWALL_ROLE),
        hasPermission(SecurityRoles.VIEW_FIREWALL_ROLES),
      ]);
      setCanAdd(addPerm);
      setCanEdit(editPerm);
      setCanDelete(deletePerm);
      setCanView(viewPerm);
    };
    checkPermissions();
  }, []);

  // Load common ports
  const loadCommonPorts = useCallback(async () => {
    try {
      const response = await axiosInstance.get<CommonPortsResponse>('/api/firewall-roles/common-ports');
      setCommonPorts(response.data.ports);
    } catch (err) {
      console.error('Error loading common ports:', err);
      showSnackbar(t('firewallRoles.errorLoadingPorts'), 'error');
    }
  }, [t]);

  // Load firewall roles
  const loadRoles = useCallback(async () => {
    if (!canView) return;

    setLoading(true);
    try {
      const response = await axiosInstance.get<FirewallRole[]>('/api/firewall-roles/');
      setRoles(response.data);
    } catch (err) {
      console.error('Error loading firewall roles:', err);
      showSnackbar(t('firewallRoles.errorLoading'), 'error');
    } finally {
      setLoading(false);
    }
  }, [canView, t]);

  useEffect(() => {
    loadCommonPorts();
  }, [loadCommonPorts]);

  useEffect(() => {
    if (canView) {
      loadRoles();
    } else {
      setLoading(false);
    }
  }, [canView, loadRoles]);

  const showSnackbar = (message: string, severity: 'success' | 'error') => {
    setSnackbarMessage(message);
    setSnackbarSeverity(severity);
    setSnackbarOpen(true);
  };

  const handleCloseSnackbar = () => {
    setSnackbarOpen(false);
  };

  // Format port display with protocol
  const formatPort = (port: PortEntry): string => {
    const protocols: string[] = [];
    if (port.tcp) protocols.push('TCP');
    if (port.udp) protocols.push('UDP');
    return `${port.port_number}-${protocols.join('/')}`;
  };

  // Filter ports by IP version
  const getIPv4Ports = (ports: PortEntry[]): PortEntry[] => {
    return ports.filter(p => p.ipv4);
  };

  const getIPv6Ports = (ports: PortEntry[]): PortEntry[] => {
    return ports.filter(p => p.ipv6);
  };

  // Open dialog for add/edit
  const openAddDialog = () => {
    setEditingRole(null);
    setRoleName('');
    setOpenPorts([]);
    resetPortForm();
    setDialogOpen(true);
  };

  const openEditDialog = (role: FirewallRole) => {
    setEditingRole(role);
    setRoleName(role.name);
    setOpenPorts([...role.open_ports]);
    resetPortForm();
    setDialogOpen(true);
  };

  const closeDialog = () => {
    setDialogOpen(false);
    setEditingRole(null);
    setRoleName('');
    setOpenPorts([]);
    resetPortForm();
  };

  const resetPortForm = () => {
    setSelectedPort('');
    setCustomPort('');
    setPortProtocol('tcp');
    setIpVersion('both');
    setStartPort('');
    setEndPort('');
  };

  // Handle adding a port to the current form
  const handleAddPort = () => {
    let portsToAdd: PortEntry[] = [];

    const isIpv4 = ipVersion === 'ipv4' || ipVersion === 'both';
    const isIpv6 = ipVersion === 'ipv6' || ipVersion === 'both';

    if (selectedPort === 'range') {
      // Port range
      const start = parseInt(startPort, 10);
      const end = parseInt(endPort, 10);
      if (isNaN(start) || isNaN(end) || start < 1 || end > 65535 || start > end) {
        showSnackbar(t('firewallRoles.invalidPortNumber'), 'error');
        return;
      }
      for (let p = start; p <= end; p++) {
        portsToAdd.push({
          port_number: p,
          tcp: portProtocol === 'tcp' || portProtocol === 'both',
          udp: portProtocol === 'udp' || portProtocol === 'both',
          ipv4: isIpv4,
          ipv6: isIpv6,
        });
      }
    } else if (selectedPort === 'custom') {
      // Custom port
      const portNum = parseInt(customPort, 10);
      if (isNaN(portNum) || portNum < 1 || portNum > 65535) {
        showSnackbar(t('firewallRoles.invalidPortNumber'), 'error');
        return;
      }
      portsToAdd.push({
        port_number: portNum,
        tcp: portProtocol === 'tcp' || portProtocol === 'both',
        udp: portProtocol === 'udp' || portProtocol === 'both',
        ipv4: isIpv4,
        ipv6: isIpv6,
      });
    } else if (selectedPort === 'any') {
      // Any port (0 represents any)
      portsToAdd.push({
        port_number: 0,
        tcp: portProtocol === 'tcp' || portProtocol === 'both',
        udp: portProtocol === 'udp' || portProtocol === 'both',
        ipv4: isIpv4,
        ipv6: isIpv6,
      });
    } else if (selectedPort) {
      // Common port
      const portNum = parseInt(selectedPort, 10);
      if (!isNaN(portNum)) {
        portsToAdd.push({
          port_number: portNum,
          tcp: portProtocol === 'tcp' || portProtocol === 'both',
          udp: portProtocol === 'udp' || portProtocol === 'both',
          ipv4: isIpv4,
          ipv6: isIpv6,
        });
      }
    }

    if (portsToAdd.length === 0) {
      showSnackbar(t('firewallRoles.portNumberRequired'), 'error');
      return;
    }

    // Merge with existing ports - update existing entries or add new ones
    const updatedPorts = [...openPorts];
    for (const newPort of portsToAdd) {
      // Find existing port with same port_number and protocol combination
      const existingIndex = updatedPorts.findIndex(
        p => p.port_number === newPort.port_number && p.tcp === newPort.tcp && p.udp === newPort.udp
      );

      if (existingIndex >= 0) {
        // Update existing port's IP version flags (merge them)
        updatedPorts[existingIndex] = {
          ...updatedPorts[existingIndex],
          ipv4: updatedPorts[existingIndex].ipv4 || newPort.ipv4,
          ipv6: updatedPorts[existingIndex].ipv6 || newPort.ipv6,
        };
      } else {
        // Add new port
        updatedPorts.push(newPort);
      }
    }
    setOpenPorts(updatedPorts);

    resetPortForm();
  };

  // Remove port from IPv4 list
  const removePortFromIPv4 = (index: number) => {
    const port = openPorts[index];
    if (port.ipv6) {
      // Port also has IPv6, just disable IPv4
      setOpenPorts(openPorts.map((p, i) => i === index ? { ...p, ipv4: false } : p));
    } else {
      // Port only has IPv4, remove entirely
      setOpenPorts(openPorts.filter((_, i) => i !== index));
    }
  };

  // Remove port from IPv6 list
  const removePortFromIPv6 = (index: number) => {
    const port = openPorts[index];
    if (port.ipv4) {
      // Port also has IPv4, just disable IPv6
      setOpenPorts(openPorts.map((p, i) => i === index ? { ...p, ipv6: false } : p));
    } else {
      // Port only has IPv6, remove entirely
      setOpenPorts(openPorts.filter((_, i) => i !== index));
    }
  };

  // Save role
  const handleSaveRole = async () => {
    if (!roleName.trim()) {
      showSnackbar(t('firewallRoles.roleNameRequired'), 'error');
      return;
    }

    setSaving(true);
    try {
      const roleData = {
        name: roleName.trim(),
        open_ports: openPorts.map(p => ({
          port_number: p.port_number,
          tcp: p.tcp,
          udp: p.udp,
          ipv4: p.ipv4,
          ipv6: p.ipv6,
        })),
      };

      if (editingRole) {
        await axiosInstance.put(`/api/firewall-roles/${editingRole.id}`, roleData);
        showSnackbar(t('firewallRoles.updateSuccess'), 'success');
      } else {
        await axiosInstance.post('/api/firewall-roles/', roleData);
        showSnackbar(t('firewallRoles.createSuccess'), 'success');
      }

      closeDialog();
      loadRoles();
    } catch (err: unknown) {
      console.error('Error saving firewall role:', err);
      let errorMessage = editingRole ? t('firewallRoles.errorUpdating') : t('firewallRoles.errorCreating');

      // Handle Pydantic validation errors (array of objects) or simple string errors
      const detail = (err as { response?: { data?: { detail?: string | Array<{ msg?: string }> } } })?.response?.data?.detail;
      if (detail) {
        if (typeof detail === 'string') {
          errorMessage = detail;
        } else if (Array.isArray(detail) && detail.length > 0) {
          // Pydantic validation error - extract the message from the first error
          errorMessage = detail[0]?.msg || errorMessage;
        }
      }
      showSnackbar(errorMessage, 'error');
    } finally {
      setSaving(false);
    }
  };

  // Delete role
  const handleDeleteClick = (role: FirewallRole) => {
    setRoleToDelete(role);
    setDeleteDialogOpen(true);
  };

  const handleConfirmDelete = async () => {
    if (!roleToDelete) return;

    try {
      await axiosInstance.delete(`/api/firewall-roles/${roleToDelete.id}`);
      showSnackbar(t('firewallRoles.deleteSuccess'), 'success');
      loadRoles();
    } catch (err: unknown) {
      console.error('Error deleting firewall role:', err);
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      const errorMessage = detail || t('firewallRoles.errorDeleting');
      showSnackbar(errorMessage, 'error');
    } finally {
      setDeleteDialogOpen(false);
      setRoleToDelete(null);
    }
  };

  // Grid columns - now with separate IPv4 and IPv6 columns
  const columns: GridColDef[] = [
    {
      field: 'name',
      headerName: t('firewallRoles.roleName'),
      flex: 1,
      minWidth: 150,
    },
    {
      field: 'ipv4_ports',
      headerName: t('firewallRoles.openIPv4Ports'),
      flex: 1.5,
      minWidth: 180,
      renderCell: (params: GridRenderCellParams<FirewallRole>) => {
        const ipv4Ports = getIPv4Ports(params.row.open_ports);
        return (
          <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.5, py: 0.5 }}>
            {ipv4Ports.length === 0 ? (
              <Typography variant="body2" color="text.secondary">
                {t('firewallRoles.noIPv4Ports')}
              </Typography>
            ) : (
              ipv4Ports.slice(0, 4).map((port, idx) => (
                <Chip
                  key={idx}
                  label={formatPort(port)}
                  size="small"
                  color="success"
                  variant="outlined"
                />
              ))
            )}
            {ipv4Ports.length > 4 && (
              <Chip
                label={`+${ipv4Ports.length - 4}`}
                size="small"
                color="success"
                variant="outlined"
              />
            )}
          </Box>
        );
      },
    },
    {
      field: 'ipv6_ports',
      headerName: t('firewallRoles.openIPv6Ports'),
      flex: 1.5,
      minWidth: 180,
      renderCell: (params: GridRenderCellParams<FirewallRole>) => {
        const ipv6Ports = getIPv6Ports(params.row.open_ports);
        return (
          <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.5, py: 0.5 }}>
            {ipv6Ports.length === 0 ? (
              <Typography variant="body2" color="text.secondary">
                {t('firewallRoles.noIPv6Ports')}
              </Typography>
            ) : (
              ipv6Ports.slice(0, 4).map((port, idx) => (
                <Chip
                  key={idx}
                  label={formatPort(port)}
                  size="small"
                  color="info"
                  variant="outlined"
                />
              ))
            )}
            {ipv6Ports.length > 4 && (
              <Chip
                label={`+${ipv6Ports.length - 4}`}
                size="small"
                color="info"
                variant="outlined"
              />
            )}
          </Box>
        );
      },
    },
    {
      field: 'actions',
      headerName: t('common.actions'),
      width: 120,
      sortable: false,
      renderCell: (params: GridRenderCellParams<FirewallRole>) => (
        <Stack direction="row" spacing={1}>
          {canEdit && (
            <IconButton
              size="small"
              onClick={() => openEditDialog(params.row)}
              title={t('firewallRoles.editRole')}
            >
              <EditIcon fontSize="small" />
            </IconButton>
          )}
          {canDelete && (
            <IconButton
              size="small"
              onClick={() => handleDeleteClick(params.row)}
              title={t('firewallRoles.deleteRole')}
              color="error"
            >
              <DeleteIcon fontSize="small" />
            </IconButton>
          )}
        </Stack>
      ),
    },
  ];

  if (!canView) {
    return (
      <Box sx={{ p: 3 }}>
        <Alert severity="warning">{t('firewallRoles.noViewPermission')}</Alert>
      </Box>
    );
  }

  // Handle delete selected
  const handleDeleteSelected = async () => {
    if (selectedRows.length === 0) return;

    try {
      for (const roleId of selectedRows) {
        await axiosInstance.delete(`/api/firewall-roles/${roleId}`);
      }
      showSnackbar(t('firewallRoles.deleteSuccess'), 'success');
      setSelectedRows([]);
      loadRoles();
    } catch (err: unknown) {
      console.error('Error deleting firewall roles:', err);
      let errorMessage = t('firewallRoles.errorDeleting');
      const detail = (err as { response?: { data?: { detail?: string | Array<{ msg?: string }> } } })?.response?.data?.detail;
      if (detail) {
        if (typeof detail === 'string') {
          errorMessage = detail;
        } else if (Array.isArray(detail) && detail.length > 0) {
          errorMessage = detail[0]?.msg || errorMessage;
        }
      }
      showSnackbar(errorMessage, 'error');
    }
  };

  // Get ports for dialog display - separated by IP version
  const ipv4PortsForDialog = getIPv4Ports(openPorts);
  const ipv6PortsForDialog = getIPv6Ports(openPorts);

  return (
    <Box sx={{ p: 3 }}>
      <Card>
        <CardHeader
          avatar={<SecurityIcon />}
          title={t('firewallRoles.title')}
          subheader={t('firewallRoles.subtitle')}
        />
        <CardContent>
          {loading ? (
            <Box sx={{ display: 'flex', justifyContent: 'center', p: 3 }}>
              <CircularProgress />
            </Box>
          ) : roles.length === 0 ? (
            <Alert severity="info">{t('firewallRoles.noRoles')}</Alert>
          ) : (
            <DataGrid
              rows={roles}
              columns={columns}
              initialState={{
                pagination: { paginationModel: { pageSize: 10 } },
              }}
              pageSizeOptions={[5, 10, 25]}
              checkboxSelection
              disableRowSelectionOnClick
              onRowSelectionModelChange={(newSelection) => {
                setSelectedRows(newSelection as string[]);
              }}
              rowSelectionModel={selectedRows}
              getRowHeight={() => 'auto'}
              sx={{
                '& .MuiDataGrid-cell': {
                  display: 'flex',
                  alignItems: 'center',
                  py: 1,
                },
                '& .MuiDataGrid-cell--withRenderer': {
                  display: 'flex',
                  alignItems: 'center',
                },
                '& .MuiDataGrid-cellCheckbox': {
                  display: 'flex',
                  alignItems: 'center',
                },
              }}
              autoHeight
            />
          )}
          <Stack direction="row" spacing={2} sx={{ mt: 2 }} justifyContent="flex-start">
            {canAdd && (
              <Button
                variant="contained"
                startIcon={<AddIcon />}
                onClick={openAddDialog}
              >
                {t('firewallRoles.addRole')}
              </Button>
            )}
            {canDelete && (
              <Button
                variant="outlined"
                color="error"
                startIcon={<DeleteIcon />}
                onClick={handleDeleteSelected}
                disabled={selectedRows.length === 0}
              >
                {t('firewallRoles.deleteSelected')}
              </Button>
            )}
          </Stack>
        </CardContent>
      </Card>

      {/* Add/Edit Dialog */}
      <Dialog open={dialogOpen} onClose={closeDialog} maxWidth="md" fullWidth>
        <DialogTitle>
          {editingRole ? t('firewallRoles.editRole') : t('firewallRoles.addRole')}
        </DialogTitle>
        <DialogContent dividers>
          <Stack spacing={3}>
            <TextField
              label={t('firewallRoles.roleName')}
              placeholder={t('firewallRoles.roleNamePlaceholder')}
              value={roleName}
              onChange={(e) => setRoleName(e.target.value)}
              fullWidth
              required
            />

            {/* Port Selection */}
            <Box>
              <Typography variant="subtitle2" gutterBottom>
                {t('firewallRoles.addPort')}
              </Typography>
              <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2} alignItems="flex-start" flexWrap="wrap">
                <FormControl sx={{ minWidth: 200 }}>
                  <InputLabel>{t('firewallRoles.selectPort')}</InputLabel>
                  <Select
                    value={selectedPort}
                    label={t('firewallRoles.selectPort')}
                    onChange={(e) => setSelectedPort(e.target.value)}
                  >
                    <MenuItem value="any">{t('firewallRoles.anyPort')}</MenuItem>
                    <MenuItem value="range">{t('firewallRoles.portRange')}</MenuItem>
                    <MenuItem value="custom">{t('firewallRoles.customPort')}</MenuItem>
                    {commonPorts.map((port) => (
                      <MenuItem key={port.port} value={port.port.toString()}>
                        {port.port} - {port.name}
                      </MenuItem>
                    ))}
                  </Select>
                </FormControl>

                {selectedPort === 'custom' && (
                  <TextField
                    label={t('firewallRoles.customPort')}
                    value={customPort}
                    onChange={(e) => setCustomPort(e.target.value)}
                    type="number"
                    inputProps={{ min: 1, max: 65535 }}
                    sx={{ width: 120 }}
                  />
                )}

                {selectedPort === 'range' && (
                  <>
                    <TextField
                      label={t('firewallRoles.startPort')}
                      value={startPort}
                      onChange={(e) => setStartPort(e.target.value)}
                      type="number"
                      inputProps={{ min: 1, max: 65535 }}
                      sx={{ width: 120 }}
                    />
                    <TextField
                      label={t('firewallRoles.endPort')}
                      value={endPort}
                      onChange={(e) => setEndPort(e.target.value)}
                      type="number"
                      inputProps={{ min: 1, max: 65535 }}
                      sx={{ width: 120 }}
                    />
                  </>
                )}

                <FormControl sx={{ minWidth: 120 }}>
                  <InputLabel>{t('firewallRoles.protocol')}</InputLabel>
                  <Select
                    value={portProtocol}
                    label={t('firewallRoles.protocol')}
                    onChange={(e) => setPortProtocol(e.target.value as 'tcp' | 'udp' | 'both')}
                  >
                    <MenuItem value="tcp">{t('firewallRoles.tcp')}</MenuItem>
                    <MenuItem value="udp">{t('firewallRoles.udp')}</MenuItem>
                    <MenuItem value="both">{t('firewallRoles.both')}</MenuItem>
                  </Select>
                </FormControl>

                <FormControl sx={{ minWidth: 140 }}>
                  <InputLabel>{t('firewallRoles.ipVersion')}</InputLabel>
                  <Select
                    value={ipVersion}
                    label={t('firewallRoles.ipVersion')}
                    onChange={(e) => setIpVersion(e.target.value as 'ipv4' | 'ipv6' | 'both')}
                  >
                    <MenuItem value="ipv4">{t('firewallRoles.ipv4Only')}</MenuItem>
                    <MenuItem value="ipv6">{t('firewallRoles.ipv6Only')}</MenuItem>
                    <MenuItem value="both">{t('firewallRoles.ipv4AndIpv6')}</MenuItem>
                  </Select>
                </FormControl>

                <Button
                  variant="outlined"
                  startIcon={<AddIcon />}
                  onClick={handleAddPort}
                  disabled={!selectedPort}
                >
                  {t('firewallRoles.addPort')}
                </Button>
              </Stack>
            </Box>

            {/* IPv4 Ports Display */}
            <Box>
              <Typography variant="subtitle2" gutterBottom color="success.main">
                {t('firewallRoles.openIPv4Ports')} ({ipv4PortsForDialog.length})
              </Typography>
              <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 1, minHeight: 40 }}>
                {ipv4PortsForDialog.length === 0 ? (
                  <Typography variant="body2" color="text.secondary">
                    {t('firewallRoles.noIPv4Ports')}
                  </Typography>
                ) : (
                  openPorts.map((port, idx) => {
                    if (!port.ipv4) return null;
                    return (
                      <Chip
                        key={`ipv4-${idx}`}
                        label={formatPort(port)}
                        color="success"
                        variant="outlined"
                        onDelete={() => removePortFromIPv4(idx)}
                      />
                    );
                  })
                )}
              </Box>
            </Box>

            {/* IPv6 Ports Display */}
            <Box>
              <Typography variant="subtitle2" gutterBottom color="info.main">
                {t('firewallRoles.openIPv6Ports')} ({ipv6PortsForDialog.length})
              </Typography>
              <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 1, minHeight: 40 }}>
                {ipv6PortsForDialog.length === 0 ? (
                  <Typography variant="body2" color="text.secondary">
                    {t('firewallRoles.noIPv6Ports')}
                  </Typography>
                ) : (
                  openPorts.map((port, idx) => {
                    if (!port.ipv6) return null;
                    return (
                      <Chip
                        key={`ipv6-${idx}`}
                        label={formatPort(port)}
                        color="info"
                        variant="outlined"
                        onDelete={() => removePortFromIPv6(idx)}
                      />
                    );
                  })
                )}
              </Box>
            </Box>
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={closeDialog}>{t('common.cancel')}</Button>
          <Button
            variant="contained"
            onClick={handleSaveRole}
            disabled={saving || !roleName.trim()}
          >
            {saving ? <CircularProgress size={24} /> : t('common.save')}
          </Button>
        </DialogActions>
      </Dialog>

      {/* Delete Confirmation Dialog */}
      <Dialog open={deleteDialogOpen} onClose={() => setDeleteDialogOpen(false)}>
        <DialogTitle>{t('firewallRoles.deleteRole')}</DialogTitle>
        <DialogContent>
          <Typography>{t('firewallRoles.confirmDelete')}</Typography>
          {roleToDelete && (
            <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>
              {roleToDelete.name}
            </Typography>
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setDeleteDialogOpen(false)}>{t('common.cancel')}</Button>
          <Button
            variant="contained"
            color="error"
            onClick={handleConfirmDelete}
          >
            {t('common.delete')}
          </Button>
        </DialogActions>
      </Dialog>

      {/* Snackbar for notifications */}
      <Snackbar
        open={snackbarOpen}
        autoHideDuration={6000}
        onClose={handleCloseSnackbar}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'center' }}
      >
        <Alert
          onClose={handleCloseSnackbar}
          severity={snackbarSeverity}
          sx={{ width: '100%' }}
        >
          {snackbarMessage}
        </Alert>
      </Snackbar>
    </Box>
  );
};

export default FirewallRolesSettings;
