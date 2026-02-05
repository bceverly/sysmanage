import React, { useState, useEffect, useCallback, useMemo } from 'react';

import { DataGrid, GridColDef, GridRowSelectionModel } from '@mui/x-data-grid';
import { 
  Typography, 
  Button, 
  Dialog, 
  DialogActions, 
  DialogContent, 
  DialogTitle,
  TextField,
  Box,
  Stack,
  IconButton,
  Chip,
  Tabs,
  Tab,
  Card,
  CardContent,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
  Grid,
  Alert,
} from '@mui/material';
import {
  Add as AddIcon,
  Delete as DeleteIcon,
  Edit as EditIcon,
  Visibility as VisibilityIcon,
  Search as SearchIcon,
  Storage as StorageIcon,
  Refresh as RefreshIcon
} from '@mui/icons-material';
import { useTranslation } from 'react-i18next';
import { useTablePageSize } from '../hooks/useTablePageSize';
import { useColumnVisibility } from '../Hooks/useColumnVisibility';
import SearchBox from '../Components/SearchBox';
import ColumnVisibilityButton from '../Components/ColumnVisibilityButton';
import EmailConfigCard from '../Components/EmailConfigCard';
import OpenBAOStatusCard from '../Components/OpenBAOStatusCard';
import GrafanaIntegrationCard from '../Components/GrafanaIntegrationCard';
import GraylogIntegrationCard from '../Components/GraylogIntegrationCard';
import OpenTelemetryStatusCard from '../Components/OpenTelemetryStatusCard';
import PrometheusStatusCard from '../Components/PrometheusStatusCard';
import UbuntuProSettings from '../Components/UbuntuProSettings';
import AntivirusDefaultsSettings from '../Components/AntivirusDefaultsSettings';
import HostDefaultsSettings from '../Components/HostDefaultsSettings';
import FirewallRolesSettings from '../Components/FirewallRolesSettings';
import DistributionsSettings from '../Components/DistributionsSettings';
import ProPlusSettings from '../Components/ProPlusSettings';
import CveRefreshSettings from '../Components/CveRefreshSettings';
import axiosInstance from '../Services/api';
import { hasPermission, SecurityRoles } from '../Services/permissions';
import { getLicenseInfo } from '../Services/license';

interface Tag {
  id: string;
  name: string;
  description: string | null;
  created_at: string;
  updated_at: string;
  host_count: number;
}

interface TagWithHosts extends Tag {
  hosts: Array<{
    id: string;
    fqdn: string;
    ipv4: string;
    ipv6: string;
    active: boolean;
    status: string;
  }>;
}

interface PackageInfo {
  name: string;
  version: string;
  description?: string;
  package_manager: string;
}

interface PackageManagerSummary {
  package_manager: string;
  package_count: number;
}

interface OSPackageSummary {
  os_name: string;
  os_version: string;
  package_managers: PackageManagerSummary[];
  total_packages: number;
}

interface Host {
  id: string;
  fqdn: string;
  ipv4: string;
  ipv6: string;
  active: boolean;
  approval_status: string;
  platform?: string;
  platform_version?: string;
}

interface QueueMessage {
  id: string;
  type: string;
  direction: string;
  timestamp: string;
  created_at: string;
  host_id: string | null;
  priority: string;
  data: Record<string, unknown>;
}

const Settings: React.FC = () => {
  const { t } = useTranslation();
  const [tags, setTags] = useState<Tag[]>([]);
  const [filteredTags, setFilteredTags] = useState<Tag[]>([]);
  const [tagsLoading, setTagsLoading] = useState<boolean>(true);
  const [selectedTags, setSelectedTags] = useState<GridRowSelectionModel>([]);
  const [searchTerm, setSearchTerm] = useState<string>('');
  const [searchColumn, setSearchColumn] = useState<string>('name');
  
  // Add/Edit dialog state
  const [addDialogOpen, setAddDialogOpen] = useState(false);
  const [editDialogOpen, setEditDialogOpen] = useState(false);
  const [editingTag, setEditingTag] = useState<Tag | null>(null);
  const [tagName, setTagName] = useState('');
  const [tagDescription, setTagDescription] = useState('');
  
  // View hosts dialog state
  const [viewHostsDialogOpen, setViewHostsDialogOpen] = useState(false);
  const [viewingTag, setViewingTag] = useState<TagWithHosts | null>(null);
  
  // Pro+ license state
  const [isProPlusActive, setIsProPlusActive] = useState<boolean>(false);

  // Tab names for URL hash (dynamic based on Pro+ status)
  const tabNames = useMemo(() => {
    const baseTabs = ['tags', 'queues', 'integrations', 'ubuntu-pro', 'antivirus', 'available-packages', 'host-defaults', 'firewall-roles', 'distributions'];
    return isProPlusActive ? [...baseTabs, 'professional-plus', 'cve-refresh'] : baseTabs;
  }, [isProPlusActive]);

  // Initialize tab from URL hash
  const getInitialTab = () => {
    const hash = globalThis.location.hash.slice(1); // Remove # prefix
    const tabIndex = tabNames.indexOf(hash);
    return Math.max(tabIndex, 0);
  };

  // Tab state
  const [activeTab, setActiveTab] = useState(getInitialTab);

  // Handle tab change and update URL hash
  const handleTabChange = (_event: React.SyntheticEvent, newValue: number) => {
    setActiveTab(newValue);
    // Safely access array element with bounds check
    if (newValue >= 0 && newValue < tabNames.length) {
      globalThis.location.hash = tabNames[newValue]; // nosemgrep: detect-object-injection
    }

    // Load queue messages when switching to queue tab
    if (newValue === 1) {
      loadQueueMessages();
    }
    // Note: Available Packages tab is now at index 5 (was 4)
    // Load package data when switching to Available Packages tab
    if (newValue === 5) {
      loadPackageSummary();
      // Start 30-second auto-refresh timer for package cards
      if (packageRefreshInterval) {
        globalThis.clearInterval(packageRefreshInterval);
      }
      const interval = globalThis.setInterval(() => {
        loadPackageSummary();
      }, 30000);
      setPackageRefreshInterval(interval);
    } else if (packageRefreshInterval) {
      // Clear interval when leaving Available Packages tab
      globalThis.clearInterval(packageRefreshInterval);
      setPackageRefreshInterval(null);
    }
  };

  // Listen for hash changes (browser back/forward)
  useEffect(() => {
    const handleHashChange = () => {
      const hash = globalThis.location.hash.slice(1);
      const tabIndex = tabNames.indexOf(hash);
      if (tabIndex >= 0) {
        setActiveTab(tabIndex);
      }
    };

    globalThis.addEventListener('hashchange', handleHashChange);
    return () => globalThis.removeEventListener('hashchange', handleHashChange);
  }, [tabNames]);

  // Re-check URL hash when tabNames changes (e.g., when Pro+ license loads)
  // This fixes the race condition where the hash is checked before Pro+ tabs are available
  useEffect(() => {
    const hash = globalThis.location.hash.slice(1);
    if (hash) {
      const tabIndex = tabNames.indexOf(hash);
      if (tabIndex >= 0) {
        setActiveTab(tabIndex);
      }
    }
  }, [tabNames]);
  
  // Queue management state
  const [queueMessages, setQueueMessages] = useState<QueueMessage[]>([]);
  const [selectedMessages, setSelectedMessages] = useState<GridRowSelectionModel>([]);
  const [queueLoading, setQueueLoading] = useState<boolean>(true);
  const [messageDetailOpen, setMessageDetailOpen] = useState(false);
  const [selectedMessage, setSelectedMessage] = useState<QueueMessage | null>(null);

  // Package management state
  const [packageSummary, setPackageSummary] = useState<OSPackageSummary[]>([]);
  const [selectedOS, setSelectedOS] = useState<string>('');
  const [selectedManager, setSelectedManager] = useState<string>('');
  const [packages, setPackages] = useState<PackageInfo[]>([]);
  const [packageLoading, setPackageLoading] = useState(false);
  const [packageSearchTerm, setPackageSearchTerm] = useState('');
  const [packageTotalCount, setPackageTotalCount] = useState(0);
  const [packageRefreshInterval, setPackageRefreshInterval] = useState<number | null>(null);
  const [hasSearched, setHasSearched] = useState(false);
  const [packageSummaryLoading, setPackageSummaryLoading] = useState(false);

  // Permission states
  const [canDeleteQueueMessage, setCanDeleteQueueMessage] = useState<boolean>(false);

  // Permission state
  const [canEditTags, setCanEditTags] = useState<boolean>(false);

  const { pageSize, pageSizeOptions } = useTablePageSize({
    reservedHeight: 350,
  });

  // Controlled pagination state for DataGrids
  const [tagsPaginationModel, setTagsPaginationModel] = useState({ page: 0, pageSize: 10 });
  const [queuePaginationModel, setQueuePaginationModel] = useState({ page: 0, pageSize: 10 });

  // Update pagination when pageSize from hook changes
  useEffect(() => {
    setTagsPaginationModel(prev => ({ ...prev, pageSize }));
    setQueuePaginationModel(prev => ({ ...prev, pageSize }));
  }, [pageSize]);

  // Ensure current page size is always in options to avoid MUI warning
  const safePageSizeOptions = useMemo(() => {
    const currentPageSizeTags = tagsPaginationModel.pageSize;
    const currentPageSizeQueue = queuePaginationModel.pageSize;
    const maxPageSize = Math.max(currentPageSizeTags, currentPageSizeQueue);
    if (!pageSizeOptions.includes(maxPageSize)) {
      return [...pageSizeOptions, maxPageSize].sort((a, b) => a - b);
    }
    return pageSizeOptions;
  }, [pageSizeOptions, tagsPaginationModel.pageSize, queuePaginationModel.pageSize]);

  // Column visibility preferences for Tags grid
  const {
    hiddenColumns: hiddenTagsColumns,
    setHiddenColumns: setHiddenTagsColumns,
    resetPreferences: resetTagsPreferences,
    getColumnVisibilityModel: getTagsColumnVisibilityModel,
  } = useColumnVisibility('settings-tags-grid');

  // Column visibility preferences for Queue Management grid
  const {
    hiddenColumns: hiddenQueueColumns,
    setHiddenColumns: setHiddenQueueColumns,
    resetPreferences: resetQueuePreferences,
    getColumnVisibilityModel: getQueueColumnVisibilityModel,
  } = useColumnVisibility('settings-queue-grid');

  // Check permissions
  useEffect(() => {
    const checkPermission = async () => {
      const [editTags, deleteQueueMessage] = await Promise.all([
        hasPermission(SecurityRoles.EDIT_TAGS),
        hasPermission(SecurityRoles.DELETE_QUEUE_MESSAGE)
      ]);
      setCanEditTags(editTags);
      setCanDeleteQueueMessage(deleteQueueMessage);
    };
    checkPermission();
  }, []);

  // Check Pro+ license status
  useEffect(() => {
    const checkProPlusStatus = async () => {
      try {
        const licenseInfo = await getLicenseInfo();
        setIsProPlusActive(licenseInfo.active);
      } catch (error) {
        console.log('Pro+ license check failed:', error);
        setIsProPlusActive(false);
      }
    };
    checkProPlusStatus();
  }, []);

  // Search columns configuration
  const searchColumns = [
    { field: 'name', label: t('tags.name', 'Name') },
    { field: 'description', label: t('tags.description', 'Description') }
  ];

  // Load tags from API
  const loadTags = useCallback(async () => {
    setTagsLoading(true);
    try {
      const response = await axiosInstance.get('/api/tags');
      setTags(response.data);
    } catch (error) {
      console.error('Error fetching tags:', error);
    } finally {
      setTagsLoading(false);
    }
  }, []);

  // Search functionality
  const performSearch = useCallback(() => {
    if (!searchTerm.trim()) {
      setFilteredTags(tags);
      return;
    }

    const filtered = tags.filter(tag => {
      const fieldValue = tag[searchColumn as keyof Tag];
      if (fieldValue === null || fieldValue === undefined) {
        return false;
      }
      return String(fieldValue).toLowerCase().includes(searchTerm.toLowerCase());
    });
    
    setFilteredTags(filtered);
  }, [searchTerm, searchColumn, tags]);

  // Update filtered data when tags change or search is cleared
  useEffect(() => {
    if (searchTerm.trim()) {
      performSearch();
    } else {
      setFilteredTags(tags);
    }
  }, [tags, searchTerm, searchColumn, performSearch]);

  useEffect(() => {
    loadTags();
  }, [loadTags]);

  // Cleanup package refresh interval on unmount
  useEffect(() => {
    return () => {
      if (packageRefreshInterval) {
        globalThis.clearInterval(packageRefreshInterval);
      }
    };
  }, [packageRefreshInterval]);

  // Handle create tag
  const handleCreateTag = async () => {
    if (!tagName.trim()) return;
    
    try {
      await axiosInstance.post('/api/tags', {
        name: tagName.trim(),
        description: tagDescription.trim() || null
      });
      
      await loadTags();
      setAddDialogOpen(false);
      setTagName('');
      setTagDescription('');
    } catch (error) {
      console.error('Error creating tag:', error);
    }
  };

  // Handle update tag
  const handleUpdateTag = async () => {
    if (!editingTag || !tagName.trim()) return;
    
    try {
      await axiosInstance.put(`/api/tags/${editingTag.id}`, {
        name: tagName.trim(),
        description: tagDescription.trim() || null
      });
      
      await loadTags();
      setEditDialogOpen(false);
      setEditingTag(null);
      setTagName('');
      setTagDescription('');
    } catch (error) {
      console.error('Error updating tag:', error);
    }
  };

  // Handle delete tags
  const handleDeleteTags = async () => {
    if (selectedTags.length === 0) return;
    
    try {
      const deletePromises = selectedTags.map(id =>
        axiosInstance.delete(`/api/tags/${id}`)
      );
      
      await Promise.all(deletePromises);
      await loadTags();
      setSelectedTags([]);
    } catch (error) {
      console.error('Error deleting tags:', error);
    }
  };

  // Handle view hosts for tag
  const handleViewHosts = async (tagId: number) => {
    try {
      const response = await axiosInstance.get(`/api/tags/${tagId}/hosts`);
      setViewingTag(response.data);
      setViewHostsDialogOpen(true);
    } catch (error) {
      console.error('Error fetching tag hosts:', error);
    }
  };

  // Handle edit tag
  const handleEditTag = (tag: Tag) => {
    setEditingTag(tag);
    setTagName(tag.name);
    setTagDescription(tag.description || '');
    setEditDialogOpen(true);
  };

  // Load queue messages from API
  const loadQueueMessages = useCallback(async () => {
    setQueueLoading(true);
    try {
      const response = await axiosInstance.get('/api/queue/failed');
      setQueueMessages(response.data);
    } catch (error) {
      console.error('Error fetching queue messages:', error);
    } finally {
      setQueueLoading(false);
    }
  }, []);

  // Handle delete selected messages
  const handleDeleteMessages = async () => {
    if (selectedMessages.length === 0) return;
    
    try {
      await axiosInstance.delete('/api/queue/failed', {
        data: selectedMessages
      });
      
      await loadQueueMessages();
      setSelectedMessages([]);
    } catch (error) {
      console.error('Error deleting messages:', error);
    }
  };

  // Handle view message details
  const handleViewMessage = async (messageId: string) => {
    try {
      const response = await axiosInstance.get(`/api/queue/failed/${messageId}`);
      setSelectedMessage(response.data);
      setMessageDetailOpen(true);
    } catch (error) {
      console.error('Error fetching message details:', error);
    }
  };

  // Package management functions
  const loadPackageSummary = useCallback(async () => {
    setPackageSummaryLoading(true);
    try {
      const response = await axiosInstance.get('/api/packages/summary');
      setPackageSummary(response.data);
    } catch (error) {
      console.error('Error fetching package summary:', error);
    } finally {
      setPackageSummaryLoading(false);
    }
  }, []);


  const searchPackages = useCallback(async (page = 0, pageSize = 25) => {
    if (!packageSearchTerm.trim()) {
      setPackages([]);
      setPackageTotalCount(0);
      setHasSearched(false);
      return;
    }

    setPackageLoading(true);
    setHasSearched(true);
    try {
      const params: {
        query: string;
        limit?: number;
        offset?: number;
        os_name?: string;
        os_version?: string;
        package_manager?: string;
      } = {
        query: packageSearchTerm,
      };

      if (selectedOS) {
        const [osName, osVersion] = selectedOS.split(':');
        params.os_name = osName;
        params.os_version = osVersion;
      }

      if (selectedManager) {
        params.package_manager = selectedManager;
      }

      // Get total count for proper pagination
      const countResponse = await axiosInstance.get('/api/packages/search/count', { params });
      setPackageTotalCount(countResponse.data.total_count);

      // Get the actual page data
      const searchParams = {
        ...params,
        limit: pageSize,
        offset: page * pageSize
      };

      const response = await axiosInstance.get('/api/packages/search', { params: searchParams });
      setPackages(response.data);
    } catch (error) {
      console.error('Error searching packages:', error);
      setPackages([]);
      setPackageTotalCount(0);
    } finally {
      setPackageLoading(false);
    }
  }, [packageSearchTerm, selectedOS, selectedManager]);

  // Refresh packages for a specific OS/version
  const refreshPackagesForOS = useCallback(async (osName: string, osVersion: string) => {
    try {
      const response = await axiosInstance.post(`/api/packages/refresh/${encodeURIComponent(osName)}/${encodeURIComponent(osVersion)}`);
      if (response.data.success) {
        // Show success message and reload package summary
        console.log('Package refresh requested successfully:', response.data.message);
        // Reload package summary after a short delay to allow processing
        setTimeout(() => {
          loadPackageSummary();
            }, 2000);
      }
    } catch (error) {
      console.error('Error refreshing packages:', error);
    }
  }, [loadPackageSummary]);

  const refreshAllPackages = useCallback(async () => {
    try {
      // If we have existing package summaries, use those
      if (packageSummary.length > 0) {
        // Refresh packages for all known OS/version combinations from package summaries
        for (const summary of packageSummary) {
          try {
            await axiosInstance.post(`/api/packages/refresh/${encodeURIComponent(summary.os_name)}/${encodeURIComponent(summary.os_version)}`);
          } catch (error) {
            console.error('Error refreshing packages for', summary.os_name, summary.os_version, ':', error);
          }
        }
      } else {
        // No package summaries exist yet, discover active hosts and trigger collection
        try {
          const hostsResponse = await axiosInstance.get('/api/hosts');
          const activeHosts = hostsResponse.data.filter((host: Host) => host.active && host.approval_status === 'approved');

          // Create unique OS/version combinations
          const osVersionCombinations = new Set();
          activeHosts.forEach((host: Host) => {
            if (host.platform && host.platform_version) {
              osVersionCombinations.add(`${host.platform}|${host.platform_version}`);
            }
          });

          // Trigger package collection for each unique OS/version combination
          for (const combination of osVersionCombinations) {
            const [osName, osVersion] = (combination as string).split('|');
            try {
              await axiosInstance.post(`/api/packages/refresh/${encodeURIComponent(osName)}/${encodeURIComponent(osVersion)}`);
            } catch (error) {
              console.error('Error refreshing packages for', osName, osVersion, ':', error);
            }
          }
        } catch (error) {
          console.error('Error fetching hosts for package refresh:', error);
        }
      }


      // Reload package summary after a short delay
      setTimeout(() => {
        loadPackageSummary();
        }, 3000);
    } catch (error: unknown) {
      console.error('Error refreshing all packages:', error);
    }
  }, [packageSummary, loadPackageSummary]);

  // Load package summary on mount if we're on the Available Packages tab
  useEffect(() => {
    if (activeTab === 5) {
      loadPackageSummary();
    }
  }, [activeTab, loadPackageSummary]);

  // DataGrid columns
  const columns: GridColDef[] = [
    { field: 'name', headerName: t('tags.name', 'Name'), width: 200 },
    { field: 'description', headerName: t('tags.description', 'Description'), width: 300, flex: 1 },
    { field: 'host_count', headerName: t('tags.hostCount', 'Host Count'), width: 120 },
    {
      field: 'updated_at',
      headerName: t('tags.lastUpdated', 'Last Updated'),
      width: 180,
      renderCell: (params) => new Date(params.value).toLocaleDateString()
    },
    {
      field: 'actions',
      headerName: t('common.actions', 'Actions'),
      width: 150,
      sortable: false,
      renderCell: (params) => (
        <Box>
          <IconButton
            size="small"
            onClick={() => handleViewHosts(params.row.id)}
            title={t('tags.viewHosts', 'View Hosts')}
          >
            <VisibilityIcon />
          </IconButton>
          <IconButton
            size="small"
            onClick={() => handleEditTag(params.row)}
            title={t('common.edit', 'Edit')}
          >
            <EditIcon />
          </IconButton>
        </Box>
      ),
    },
  ];

  // Queue Messages DataGrid columns
  const queueColumns: GridColDef[] = [
    { field: 'type', headerName: t('queues.messageType', 'Message Type'), width: 150 },
    { field: 'direction', headerName: t('queues.direction', 'Direction'), width: 120 },
    {
      field: 'timestamp',
      headerName: t('queues.expired', 'Expired At'),
      width: 180,
      renderCell: (params) => params.value ? new Date(params.value).toLocaleString() : '-'
    },
    {
      field: 'created_at',
      headerName: t('queues.created', 'Created At'),
      width: 180,
      renderCell: (params) => params.value ? new Date(params.value).toLocaleString() : '-'
    },
    { field: 'host_id', headerName: t('queues.hostId', 'Host ID'), width: 100 },
    { field: 'priority', headerName: t('queues.priority', 'Priority'), width: 100 },
    {
      field: 'actions',
      headerName: t('common.actions', 'Actions'),
      width: 100,
      sortable: false,
      renderCell: (params) => (
        <IconButton
          size="small"
          onClick={() => handleViewMessage(params.row.id)}
          title={t('queues.viewDetails', 'View Details')}
        >
          <VisibilityIcon sx={{ color: 'primary.main' }} />
        </IconButton>
      ),
    },
  ];

  // Render Tags tab content
  const renderTagsTab = () => (
    <Box sx={{
      display: 'flex',
      flexDirection: 'column',
      height: 'calc(100vh - 280px)',
      gap: 2
    }}>
      <Typography variant="h5">
        {t('tags.title', 'Tags')}
      </Typography>

      {/* Search Box */}
      <SearchBox
        searchTerm={searchTerm}
        setSearchTerm={setSearchTerm}
        searchColumn={searchColumn}
        setSearchColumn={setSearchColumn}
        columns={searchColumns}
        placeholder={t('search.searchTags', 'Search tags')}
      />

      {/* Column Visibility Button */}
      <Box sx={{ mr: 2, display: 'flex', alignItems: 'center', justifyContent: 'flex-end', flexShrink: 0 }}>
        <ColumnVisibilityButton
          columns={columns
            .filter(col => col.field !== 'actions')
            .map(col => ({ field: col.field, headerName: col.headerName || col.field }))}
          hiddenColumns={hiddenTagsColumns}
          onColumnsChange={setHiddenTagsColumns}
          onReset={resetTagsPreferences}
        />
      </Box>

      {/* Data Grid - flexGrow to fill available space */}
      <Box sx={{ flexGrow: 1, minHeight: 0 }}>
        <DataGrid
          rows={filteredTags}
          columns={columns}
          loading={tagsLoading}
          checkboxSelection
          onRowSelectionModelChange={setSelectedTags}
          rowSelectionModel={selectedTags}
          columnVisibilityModel={getTagsColumnVisibilityModel()}
          paginationModel={tagsPaginationModel}
          onPaginationModelChange={setTagsPaginationModel}
          pageSizeOptions={safePageSizeOptions}
        />
      </Box>

      {/* Action Buttons - flexShrink: 0 to stay at bottom */}
      <Stack direction="row" spacing={2} sx={{ flexShrink: 0 }}>
        {canEditTags && (
          <Button
            variant="contained"
            startIcon={<AddIcon />}
            onClick={() => setAddDialogOpen(true)}
          >
            {t('tags.addTag', 'Add Tag')}
          </Button>
        )}
        {canEditTags && (
          <Button
            variant="outlined"
            startIcon={<DeleteIcon />}
            onClick={handleDeleteTags}
            disabled={selectedTags.length === 0}
          >
            {t('common.delete', 'Delete')} ({selectedTags.length})
          </Button>
        )}
      </Stack>
    </Box>
  );

  // Render Queues tab content
  const renderQueuesTab = () => (
    <Box sx={{
      display: 'flex',
      flexDirection: 'column',
      height: 'calc(100vh - 280px)',
      gap: 2
    }}>
      <Box>
        <Typography variant="h5" sx={{ mb: 1 }}>
          {t('queues.title', 'Queue Management')}
        </Typography>

        <Typography variant="body1">
          {t('queues.description', 'View and manage expired/failed messages from the message queue.')}
        </Typography>
      </Box>

      {/* Column Visibility Button */}
      <Box sx={{ mr: 2, display: 'flex', alignItems: 'center', justifyContent: 'flex-end', flexShrink: 0 }}>
        <ColumnVisibilityButton
          columns={queueColumns
            .filter(col => col.field !== 'actions')
            .map(col => ({ field: col.field, headerName: col.headerName || col.field }))}
          hiddenColumns={hiddenQueueColumns}
          onColumnsChange={setHiddenQueueColumns}
          onReset={resetQueuePreferences}
        />
      </Box>

      {/* Data Grid - flexGrow to fill available space */}
      <Box sx={{ flexGrow: 1, minHeight: 0 }}>
        <DataGrid
          rows={queueMessages}
          columns={queueColumns}
          loading={queueLoading}
          checkboxSelection
          onRowSelectionModelChange={setSelectedMessages}
          rowSelectionModel={selectedMessages}
          columnVisibilityModel={getQueueColumnVisibilityModel()}
          paginationModel={queuePaginationModel}
          onPaginationModelChange={setQueuePaginationModel}
          pageSizeOptions={safePageSizeOptions}
        />
      </Box>

      {/* Action Buttons - flexShrink: 0 to stay at bottom */}
      <Stack direction="row" spacing={2} sx={{ flexShrink: 0 }}>
        {canDeleteQueueMessage && (
          <Button
            variant="outlined"
            startIcon={<DeleteIcon />}
            onClick={handleDeleteMessages}
            disabled={selectedMessages.length === 0}
          >
            {t('common.delete', 'Delete')} ({selectedMessages.length})
          </Button>
        )}
      </Stack>
    </Box>
  );

  // Render Integrations tab content
  const renderIntegrationsTab = () => (
    <Box>
      <Typography variant="h5" sx={{ mb: 2 }}>
        {t('integrations.title', 'Integrations')}
      </Typography>

      <Typography variant="body1" sx={{ mb: 3 }}>
        {t('integrations.description', 'Configure external service integrations and settings.')}
      </Typography>

      <Box sx={{ mb: 3 }}>
        <EmailConfigCard />
      </Box>

      <Box sx={{ mb: 3 }}>
        <OpenBAOStatusCard />
      </Box>

      <Box sx={{ mb: 3 }}>
        <GrafanaIntegrationCard />
      </Box>

      <Box sx={{ mb: 3 }}>
        <GraylogIntegrationCard />
      </Box>

      <Box sx={{ mb: 3 }}>
        <OpenTelemetryStatusCard />
      </Box>

      <Box>
        <PrometheusStatusCard />
      </Box>
    </Box>
  );

  const renderUbuntuProTab = () => (
    <Box>
      <Typography variant="h5" sx={{ mb: 2 }}>
        {t('ubuntuPro.title', 'Ubuntu Pro')}
      </Typography>

      <Typography variant="body1" sx={{ mb: 3 }}>
        {t('ubuntuPro.description', 'Configure Ubuntu Pro subscription management and master keys for bulk enrollment.')}
      </Typography>

      <UbuntuProSettings />
    </Box>
  );

  const renderAvailablePackagesTab = () => (
    <Box>
      {/* Header with title and refresh button */}
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2 }}>
        <Typography variant="h5">
          {t('availablePackages.title', 'Available Packages')}
        </Typography>
        <Button
          variant="contained"
          startIcon={<RefreshIcon />}
          onClick={refreshAllPackages}
          sx={{ minWidth: 150 }}
        >
          {t('availablePackages.refreshAll', 'Refresh All')}
        </Button>
      </Box>

      {/* Package Summary Cards */}
      {packageSummary.length > 0 && (
        <Box sx={{ mb: 4 }}>
          <Grid container spacing={2}>
            {packageSummary.map((summary) => (
              <Grid size={{ xs: 12, sm: 6, md: 4 }} key={`${summary.os_name}:${summary.os_version}`}>
                <Card>
                  <CardContent>
                    <Box display="flex" alignItems="center" mb={1}>
                      <StorageIcon sx={{ mr: 1, color: 'primary.main' }} />
                      <Typography variant="h6">
                        {summary.os_name} {summary.os_version}
                      </Typography>
                    </Box>
                    <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
                      {t('availablePackages.totalPackages', 'Total Packages')}: {summary.total_packages.toLocaleString()}
                    </Typography>
                    <Box>
                      {summary.package_managers.map((manager) => (
                        <Chip
                          key={manager.package_manager}
                          label={`${manager.package_manager}: ${manager.package_count.toLocaleString()}`}
                          size="small"
                          variant="outlined"
                          sx={{ mr: 0.5, mb: 0.5 }}
                        />
                      ))}
                    </Box>
                    <Box sx={{ mt: 1, display: 'flex', justifyContent: 'flex-end' }}>
                      <Button
                        size="small"
                        variant="outlined"
                        startIcon={<RefreshIcon />}
                        onClick={() => refreshPackagesForOS(summary.os_name, summary.os_version)}
                        sx={{ fontSize: '0.75rem' }}
                      >
                        {t('availablePackages.refresh', 'Refresh')}
                      </Button>
                    </Box>
                  </CardContent>
                </Card>
              </Grid>
            ))}
          </Grid>
        </Box>
      )}

      {/* Search Controls */}
      <Box sx={{ mb: 3 }}>
        <Typography variant="h6" sx={{ mb: 2 }}>
          {t('availablePackages.search', 'Search Packages')}
        </Typography>
        <Grid container spacing={2} alignItems="end">
          <Grid size={{ xs: 12, md: 4 }}>
            <TextField
              fullWidth
              label={t('availablePackages.searchTerm', 'Package name')}
              value={packageSearchTerm}
              onChange={(e) => setPackageSearchTerm(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && searchPackages(0, 25)}
              slotProps={{
                input: {
                  endAdornment: (
                    <IconButton onClick={() => searchPackages(0, 25)}>
                      <SearchIcon />
                    </IconButton>
                  ),
                },
              }}
            />
          </Grid>
          <Grid size={{ xs: 12, md: 3 }}>
            <FormControl fullWidth>
              <InputLabel>{t('availablePackages.filterByOS', 'Operating System / Version')}</InputLabel>
              <Select
                value={selectedOS}
                label={t('availablePackages.filterByOS', 'Operating System / Version')}
                onChange={(e) => setSelectedOS(e.target.value)}
              >
                <MenuItem value="">
                  <em>{t('common.all', 'All')}</em>
                </MenuItem>
                {packageSummary.map((summary) => (
                  <MenuItem key={`${summary.os_name}:${summary.os_version}`} value={`${summary.os_name}:${summary.os_version}`}>
                    {summary.os_name} {summary.os_version}
                  </MenuItem>
                ))}
              </Select>
            </FormControl>
          </Grid>
          <Grid size={{ xs: 12, md: 3 }}>
            <FormControl fullWidth>
              <InputLabel>{t('availablePackages.filterByManager', 'Package Manager')}</InputLabel>
              <Select
                value={selectedManager}
                label={t('availablePackages.filterByManager', 'Package Manager')}
                onChange={(e) => setSelectedManager(e.target.value)}
              >
                <MenuItem value="">
                  <em>{t('updates.filters.allManagers', 'All Package Managers')}</em>
                </MenuItem>
                <MenuItem value="apt">APT</MenuItem>
                <MenuItem value="snap">Snap</MenuItem>
                <MenuItem value="flatpak">Flatpak</MenuItem>
                <MenuItem value="fwupd">fwupd</MenuItem>
                <MenuItem value="homebrew">Homebrew</MenuItem>
                <MenuItem value="winget">Winget</MenuItem>
                <MenuItem value="chocolatey">Chocolatey</MenuItem>
                <MenuItem value="pkg">PKG</MenuItem>
                <MenuItem value="yum">YUM</MenuItem>
                <MenuItem value="dnf">DNF</MenuItem>
                <MenuItem value="zypper">Zypper</MenuItem>
                <MenuItem value="pacman">Pacman</MenuItem>
              </Select>
            </FormControl>
          </Grid>
          <Grid size={{ xs: 12, md: 2 }}>
            <Button
              fullWidth
              variant="contained"
              onClick={() => searchPackages(0, 25)}
              disabled={!packageSearchTerm.trim()}
              startIcon={<SearchIcon />}
              sx={{ height: '56px' }}
            >
              {t('common.search', 'Search')}
            </Button>
          </Grid>
        </Grid>
      </Box>

      {/* Search Results */}
      {packages.length > 0 && (
        <Box>
          <Typography variant="h6" sx={{ mb: 2 }}>
            {t('availablePackages.results', 'Search Results')} ({packageTotalCount.toLocaleString()} total, showing {packages.length})
          </Typography>
          <div style={{ height: 400 }}>
            <DataGrid
              rows={packages.map((pkg, index) => ({ id: index, ...pkg }))}
              columns={[
                { field: 'name', headerName: t('availablePackages.packageName', 'Package Name'), width: 250 },
                { field: 'version', headerName: t('availablePackages.version', 'Version'), width: 150 },
                { field: 'package_manager', headerName: t('availablePackages.manager', 'Manager'), width: 120 },
                {
                  field: 'description',
                  headerName: t('availablePackages.description', 'Description'),
                  width: 400,
                  renderCell: (params) => (
                    <Typography variant="body2" noWrap title={params.value}>
                      {params.value || t('common.noDescription', 'No description')}
                    </Typography>
                  )
                }
              ]}
              loading={packageLoading}
              rowCount={packageTotalCount}
              paginationMode="server"
              onPaginationModelChange={(model) => {
                searchPackages(model.page, model.pageSize);
              }}
              initialState={{
                pagination: {
                  paginationModel: { page: 0, pageSize: 25 },
                },
              }}
              pageSizeOptions={[25, 50, 100]}
            />
          </div>
        </Box>
      )}

      {/* Empty State */}
      {hasSearched && packages.length === 0 && !packageLoading && (
        <Alert severity="info" sx={{ mt: 2 }}>
          {t('availablePackages.noResults', 'No packages found matching your search criteria.')}
        </Alert>
      )}

      {/* Initial State */}
      {!packageSearchTerm && packageSummary.length === 0 && !packageSummaryLoading && (
        <Alert severity="info" sx={{ mt: 2 }}>
          {t('availablePackages.noData', 'No package data available. Packages will be collected from your managed hosts automatically.')}
        </Alert>
      )}

      {/* Loading State */}
      {packageSummaryLoading && packageSummary.length === 0 && (
        <Alert severity="info" sx={{ mt: 2 }}>
          {t('availablePackages.loading', 'Loading package data...')}
        </Alert>
      )}
    </Box>
  );

  return (
    <Box sx={{
      display: 'flex',
      flexDirection: 'column',
      height: 'calc(100vh - 120px)',
      gap: 2,
      p: 2
    }}>
      <Typography variant="h4">
        {t('nav.settings', 'Settings')}
      </Typography>

      {/* Tabs */}
      <Box sx={{ borderBottom: 1, borderColor: 'divider', flexShrink: 0 }}>
        <Tabs value={activeTab} onChange={handleTabChange} aria-label="settings tabs">
          <Tab label={t('tags.title', 'Tags')} />
          <Tab label={t('queues.title', 'Queues')} />
          <Tab label={t('integrations.title', 'Integrations')} />
          <Tab label={t('ubuntuPro.title', 'Ubuntu Pro')} />
          <Tab label={t('antivirus.title', 'Antivirus')} />
          <Tab label={t('availablePackages.title', 'Available Packages')} />
          <Tab label={t('hostDefaults.title', 'Host Defaults')} />
          <Tab label={t('firewallRoles.title', 'Firewall Roles')} />
          <Tab label={t('distributions.title', 'Distributions')} />
          {isProPlusActive && (
            <Tab label={t('proPlus.title', 'Professional+')} />
          )}
          {isProPlusActive && (
            <Tab label={t('cveRefresh.tabTitle', 'CVE Database')} />
          )}
        </Tabs>
      </Box>

      {/* Tab content - flexGrow to fill available space */}
      <Box sx={{ flexGrow: 1, minHeight: 0, overflow: 'auto' }}>
        {activeTab === 0 && renderTagsTab()}
        {activeTab === 1 && renderQueuesTab()}
        {activeTab === 2 && renderIntegrationsTab()}
        {activeTab === 3 && renderUbuntuProTab()}
        {activeTab === 4 && <AntivirusDefaultsSettings />}
        {activeTab === 5 && renderAvailablePackagesTab()}
        {activeTab === 6 && <HostDefaultsSettings />}
        {activeTab === 7 && <FirewallRolesSettings />}
        {activeTab === 8 && <DistributionsSettings />}
        {isProPlusActive && activeTab === 9 && (
          <Box>
            <Typography variant="h5" sx={{ mb: 2 }}>
              {t('proPlus.title', 'Professional+')}
            </Typography>
            <Typography variant="body1" sx={{ mb: 3 }}>
              {t('proPlus.description', 'View your Sysmanage Professional+ license details and provisioned features.')}
            </Typography>
            <ProPlusSettings />
          </Box>
        )}
        {isProPlusActive && activeTab === 10 && (
          <Box>
            <Typography variant="h5" sx={{ mb: 2 }}>
              {t('cveRefresh.tabTitle', 'CVE Database')}
            </Typography>
            <Typography variant="body1" sx={{ mb: 3 }}>
              {t('cveRefresh.description', 'Configure automatic CVE database updates from multiple security data sources.')}
            </Typography>
            <CveRefreshSettings />
          </Box>
        )}
      </Box>

      {/* Add Tag Dialog */}
      <Dialog open={addDialogOpen} onClose={() => setAddDialogOpen(false)} maxWidth="sm" fullWidth>
        <DialogTitle>{t('tags.addTag', 'Add Tag')}</DialogTitle>
        <DialogContent>
          <TextField
            autoFocus
            margin="dense"
            label={t('tags.name', 'Name')}
            fullWidth
            variant="outlined"
            value={tagName}
            onChange={(e) => setTagName(e.target.value)}
            sx={{ mb: 2 }}
          />
          <TextField
            margin="dense"
            label={t('tags.description', 'Description')}
            fullWidth
            variant="outlined"
            multiline
            rows={3}
            value={tagDescription}
            onChange={(e) => setTagDescription(e.target.value)}
          />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setAddDialogOpen(false)}>{t('common.cancel', 'Cancel')}</Button>
          <Button onClick={handleCreateTag} variant="contained">{t('common.add', 'Add')}</Button>
        </DialogActions>
      </Dialog>

      {/* Edit Tag Dialog */}
      <Dialog open={editDialogOpen} onClose={() => setEditDialogOpen(false)} maxWidth="sm" fullWidth>
        <DialogTitle>{t('tags.editTag', 'Edit Tag')}</DialogTitle>
        <DialogContent>
          <TextField
            autoFocus
            margin="dense"
            label={t('tags.name', 'Name')}
            fullWidth
            variant="outlined"
            value={tagName}
            onChange={(e) => setTagName(e.target.value)}
            sx={{ mb: 2 }}
          />
          <TextField
            margin="dense"
            label={t('tags.description', 'Description')}
            fullWidth
            variant="outlined"
            multiline
            rows={3}
            value={tagDescription}
            onChange={(e) => setTagDescription(e.target.value)}
          />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setEditDialogOpen(false)}>{t('common.cancel', 'Cancel')}</Button>
          <Button onClick={handleUpdateTag} variant="contained">{t('common.save', 'Save')}</Button>
        </DialogActions>
      </Dialog>

      {/* View Hosts Dialog */}
      <Dialog open={viewHostsDialogOpen} onClose={() => setViewHostsDialogOpen(false)} maxWidth="md" fullWidth>
        <DialogTitle>
          {t('tags.hostsAssociatedWith', 'Hosts associated with')} "{viewingTag?.name}"
        </DialogTitle>
        <DialogContent>
          {viewingTag?.hosts && viewingTag.hosts.length > 0 ? (
            <Box sx={{ mt: 1 }}>
              {viewingTag.hosts.map(host => (
                <Chip
                  key={host.id}
                  label={`${host.fqdn} (${host.ipv4})`}
                  variant="outlined"
                  sx={{ m: 0.5 }}
                  color={host.active ? 'primary' : 'default'}
                />
              ))}
            </Box>
          ) : (
            <Typography>{t('tags.noHostsAssociated', 'No hosts are associated with this tag.')}</Typography>
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setViewHostsDialogOpen(false)}>{t('common.close', 'Close')}</Button>
        </DialogActions>
      </Dialog>

      {/* Message Details Dialog */}
      <Dialog open={messageDetailOpen} onClose={() => setMessageDetailOpen(false)} maxWidth="lg" fullWidth>
        <DialogTitle>
          {t('queues.messageDetails', 'Message Details')}
        </DialogTitle>
        <DialogContent>
          {selectedMessage && (
            <Box sx={{ mt: 1 }}>
              <Typography variant="body2" sx={{ mb: 1 }}>
                <strong>{t('queues.messageId', 'Message ID')}:</strong> {selectedMessage.id}
              </Typography>
              <Typography variant="body2" sx={{ mb: 1 }}>
                <strong>{t('queues.messageType', 'Type')}:</strong> {selectedMessage.type}
              </Typography>
              <Typography variant="body2" sx={{ mb: 1 }}>
                <strong>{t('queues.direction', 'Direction')}:</strong> {selectedMessage.direction}
              </Typography>
              <Typography variant="body2" sx={{ mb: 1 }}>
                <strong>{t('queues.priority', 'Priority')}:</strong> {selectedMessage.priority}
              </Typography>
              <Typography variant="body2" sx={{ mb: 1 }}>
                <strong>{t('queues.hostId', 'Host ID')}:</strong> {selectedMessage.host_id || 'N/A'}
              </Typography>
              <Typography variant="body2" sx={{ mb: 1 }}>
                <strong>{t('queues.created', 'Created At')}:</strong> {selectedMessage.created_at ? new Date(selectedMessage.created_at).toLocaleString() : 'N/A'}
              </Typography>
              <Typography variant="body2" sx={{ mb: 2 }}>
                <strong>{t('queues.expired', 'Expired At')}:</strong> {selectedMessage.timestamp ? new Date(selectedMessage.timestamp).toLocaleString() : 'N/A'}
              </Typography>
              
              <Typography variant="h6" sx={{ mb: 1 }}>
                {t('queues.messageContent', 'Message Content')}:
              </Typography>
              <Box 
                component="pre" 
                sx={{ 
                  backgroundColor: '#2d2d2d', 
                  color: '#ffffff',
                  p: 2, 
                  borderRadius: 1, 
                  overflow: 'auto',
                  fontSize: '0.875rem',
                  fontFamily: 'monospace'
                }}
              >
                {JSON.stringify(selectedMessage.data, null, 2)}
              </Box>
            </Box>
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setMessageDetailOpen(false)}>{t('common.close', 'Close')}</Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
};

export default Settings;