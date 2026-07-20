// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

import React, { useState, useEffect, useCallback, useMemo } from 'react';

import { DataGrid, GridColDef, GridRowSelectionModel } from '@mui/x-data-grid';
import {
  Typography,
  Button,
  Box,
  Stack,
  IconButton,
  List,
  ListItemButton,
  ListItemText,
} from '@mui/material';
import {
  Add as AddIcon,
  Delete as DeleteIcon,
  Edit as EditIcon,
  Visibility as VisibilityIcon,
} from '@mui/icons-material';
import { useTranslation } from 'react-i18next';
import { useTablePageSize } from '../hooks/useTablePageSize';
import { useColumnVisibility } from '../hooks/useColumnVisibility';
import SearchBox from '../Components/SearchBox';
import ColumnVisibilityButton from '../Components/ColumnVisibilityButton';
import ConfigurationSettings from '../Components/ConfigurationSettings';
import AntivirusDefaultsSettings from '../Components/AntivirusDefaultsSettings';
import HostDefaultsSettings from '../Components/HostDefaultsSettings';
import FirewallRolesSettings from '../Components/FirewallRolesSettings';
import DistributionsSettings from '../Components/DistributionsSettings';
import UpgradeProfilesSettings from '../Components/UpgradeProfilesSettings';
import PackageProfilesSettings from '../Components/PackageProfilesSettings';
import ReportBrandingSettings from '../Components/ReportBrandingSettings';
import ReportTemplatesSettings from '../Components/ReportTemplatesSettings';
import AirGapBundlesSettings from '../Components/AirGapBundlesSettings';
import RepositoryMirroringSettings from '../Components/RepositoryMirroringSettings';
import AuthenticationProvidersSettings from '../Components/AuthenticationProvidersSettings';
import ServerRoleSettings from '../Components/ServerRoleSettings';
import LoggingSettings from '../Components/LoggingSettings';
import axiosInstance from '../Services/api';
import { formatUTCTimestamp, formatUTCDate } from '../utils/dateUtils';
import { hasPermission, SecurityRoles } from '../Services/permissions';
import { refreshLicenseCache } from '../Services/license';
import { usePlugins } from '../plugins';
import {
  navRailContainerSx,
  navRailGroupSx,
  navRailGroupTitleSx,
  navRailItemSx,
} from '../Components/navRailStyles';
import {
  Tag,
  TagWithHosts,
  PackageInfo,
  OSPackageSummary,
  Host,
  QueueMessage,
} from '../Components/settings/settingsTypes';
import {
  SETTINGS_CATEGORY_ORDER,
  SETTINGS_CAT_LABEL,
  SETTINGS_TAB_CATEGORY,
  SETTINGS_TAB_DEFS,
} from '../Components/settings/settingsCategories';
import AvailablePackagesTab from '../Components/settings/AvailablePackagesTab';
import IntegrationsTab from '../Components/settings/IntegrationsTab';
import UbuntuProTab from '../Components/settings/UbuntuProTab';
import SettingsDialogs from '../Components/settings/SettingsDialogs';

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
  
  // Plugin system for dynamic settings tabs
  const { settingsTabs: pluginSettingsTabs } = usePlugins();

  // Active license modules (for Pro+ tab gating).  ``licenseActive``
  // means "any Pro+ tier is licensed at all" — used by tabs like
  // ``airgap-bundles`` that aren't tied to a specific engine but
  // still want to disappear on the Community edition.
  const [licenseModules, setLicenseModules] = useState<string[]>([]);
  const [licenseFeatures, setLicenseFeatures] = useState<string[]>([]);
  const [licenseActive, setLicenseActive] = useState<boolean>(false);
  useEffect(() => {
    (async () => {
      try {
        const info = await refreshLicenseCache();
        setLicenseModules(info?.modules ?? []);
        setLicenseFeatures(info?.features ?? []);
        setLicenseActive(!!info?.active);
      } catch {
        setLicenseModules([]);
        setLicenseFeatures([]);
        setLicenseActive(false);
      }
    })();
  }, []);

  // Tab definitions live in ``settingsCategories`` (SETTINGS_TAB_DEFS);
  // here we just apply the per-user license filter.  ``moduleRequired``
  // is undefined for OSS-appropriate tabs.  The order there is the
  // visible order in the UI.
  const tabDefs = useMemo(() => {
    return SETTINGS_TAB_DEFS.filter(d => {
      if (d.moduleRequired && !licenseModules.includes(d.moduleRequired)) return false;
      if (d.requiresLicense && !licenseActive) return false;
      return true;
    });
  }, [licenseModules, licenseActive]);

  // Plugin-contributed Settings tabs honour BOTH the ``moduleRequired`` gate
  // (is the engine bundle licensed?) and the ``featureFlag`` gate (is this
  // specific capability licensed?).  The feature gate hides an Enterprise
  // capability that ships inside a Professional module.  Plugins that omit both
  // fields stay always-visible (pre-Phase-10.7 behaviour).
  const visiblePluginSettingsTabs = useMemo(() => {
    return pluginSettingsTabs.filter(pt => {
      if (pt.moduleRequired && !licenseModules.includes(pt.moduleRequired)) return false;
      if (pt.featureFlag && !licenseFeatures.includes(pt.featureFlag)) return false;
      return true;
    });
  }, [pluginSettingsTabs, licenseModules, licenseFeatures]);

  // Tabs in display order: the hardcoded tabDefs, then plugin tabs — EXCEPT the
  // SysManage License ('proplus') tab, which is surfaced right after
  // Configuration so the license is easy to find.  This single ordered list
  // drives both the tab bar and ``tabNames`` so they never desync.
  const orderedSettingsTabs = useMemo(() => {
    const hard = tabDefs.map(d => ({ id: d.id, label: t(d.labelKey, d.labelDefault) }));
    const plugins = visiblePluginSettingsTabs.map(pt => ({
      id: pt.id,
      label: t(pt.labelKey),
    }));
    const proplusIdx = plugins.findIndex(p => p.id === 'proplus');
    if (proplusIdx === -1) {
      return [...hard, ...plugins];
    }
    const proplus = plugins[proplusIdx];
    const restPlugins = plugins.filter((_, i) => i !== proplusIdx);
    const cfgIdx = hard.findIndex(h => h.id === 'configuration');
    const ordered = [...hard];
    ordered.splice(cfgIdx === -1 ? 0 : cfgIdx + 1, 0, proplus);
    return [...ordered, ...restPlugins];
  }, [tabDefs, visiblePluginSettingsTabs, t]);

  // Tab IDs in display order — used for hash navigation (URL hash → activeTab
  // index) and ID-based dispatch in handleTabChange / tab content rendering.
  const tabNames = useMemo(
    () => orderedSettingsTabs.map(x => x.id),
    [orderedSettingsTabs],
  );

  // Group the visible tabs into the left-rail sections (empty categories drop
  // out, so a Community user sees only the categories they have tabs in).
  const settingsGroups = useMemo(() => {
    const groups = new Map<string, { id: string; label: string }[]>();
    for (const tab of orderedSettingsTabs) {
      const cat = SETTINGS_TAB_CATEGORY.get(tab.id) ?? 'system';
      const arr = groups.get(cat) ?? [];
      arr.push(tab);
      groups.set(cat, arr);
    }
    return SETTINGS_CATEGORY_ORDER
      .filter(c => (groups.get(c)?.length ?? 0) > 0)
      .map(c => {
        const meta = SETTINGS_CAT_LABEL.get(c);
        return {
          id: c,
          label: t(meta?.key ?? c, meta?.def ?? c),
          tabs: groups.get(c) ?? [],
        };
      });
  }, [orderedSettingsTabs, t]);

  // Initialize tab from URL hash
  const getInitialTab = () => {
    const hash = globalThis.location.hash.slice(1); // Remove # prefix
    const tabIndex = tabNames.indexOf(hash);
    return Math.max(tabIndex, 0);
  };

  // Tab state
  const [activeTab, setActiveTab] = useState(getInitialTab);

  // Handle tab change and update URL hash.  Dispatch is keyed off the tab
  // ID rather than the index — the visible tab list is filtered by license
  // so indices are not stable across users.
  const handleTabChange = (_event: React.SyntheticEvent, newValue: number) => {
    setActiveTab(newValue);
    // Safely access array element with bounds check
    const newTabId = (newValue >= 0 && newValue < tabNames.length)
      ? tabNames[newValue]  // nosemgrep: detect-object-injection
      : '';
    if (newTabId) {
      globalThis.location.hash = newTabId;
    }

    // Load queue messages when switching to queue tab
    if (newTabId === 'queues') {
      loadQueueMessages();
    }
    // Load package data when switching to Available Packages tab
    if (newTabId === 'available-packages') {
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

  // Note: Pro+ settings tabs are now provided by plugins via usePlugins()

  // Search columns configuration
  const searchColumns = [
    { field: 'name', label: t('tags.name', 'Name') },
    { field: 'description', label: t('tags.description', 'Description') }
  ];

  // Load tags from API
  const loadTags = useCallback(async () => {
    setTagsLoading(true);
    try {
      const response = await axiosInstance.get('/api/v1/tags');
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
      await axiosInstance.post('/api/v1/tags', {
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
      await axiosInstance.put(`/api/v1/tags/${editingTag.id}`, {
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
        axiosInstance.delete(`/api/v1/tags/${id}`)
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
      const response = await axiosInstance.get(`/api/v1/tags/${tagId}/hosts`);
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
      const response = await axiosInstance.get('/api/v1/queue/failed');
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
      await axiosInstance.delete('/api/v1/queue/failed', {
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
      const response = await axiosInstance.get(`/api/v1/queue/failed/${messageId}`);
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
      const response = await axiosInstance.get('/api/v1/packages/summary');
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
      const countResponse = await axiosInstance.get('/api/v1/packages/search/count', { params });
      setPackageTotalCount(countResponse.data.total_count);

      // Get the actual page data
      const searchParams = {
        ...params,
        limit: pageSize,
        offset: page * pageSize
      };

      const response = await axiosInstance.get('/api/v1/packages/search', { params: searchParams });
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
      const response = await axiosInstance.post(`/api/v1/packages/refresh/${encodeURIComponent(osName)}/${encodeURIComponent(osVersion)}`);
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
            await axiosInstance.post(`/api/v1/packages/refresh/${encodeURIComponent(summary.os_name)}/${encodeURIComponent(summary.os_version)}`);
          } catch (error) {
            console.error('Error refreshing packages for', summary.os_name, summary.os_version, ':', error);
          }
        }
      } else {
        // No package summaries exist yet, discover active hosts and trigger collection
        try {
          const hostsResponse = await axiosInstance.get('/api/v1/hosts');
          const activeHosts = hostsResponse.data.filter((host: Host) => host.active && host.approval_status === 'approved');

          // Create unique OS/version combinations
          const osVersionCombinations = new Set<string>();
          activeHosts.forEach((host: Host) => {
            if (host.platform && host.platform_version) {
              osVersionCombinations.add(`${host.platform}|${host.platform_version}`);
            }
          });

          // Trigger package collection for each unique OS/version combination
          for (const combination of Array.from(osVersionCombinations)) {
            const [osName, osVersion] = combination.split('|');
            try {
              await axiosInstance.post(`/api/v1/packages/refresh/${encodeURIComponent(osName)}/${encodeURIComponent(osVersion)}`);
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

  // Load package summary on mount if we're on the Available Packages tab.
  // Keyed off the tab ID (not a hard-coded index) since the visible tab list
  // shifts with license filtering and added tabs.
  useEffect(() => {
    if (tabNames[activeTab] === 'available-packages') {
      loadPackageSummary();
    }
  }, [activeTab, tabNames, loadPackageSummary]);

  // DataGrid columns
  const columns: GridColDef[] = [
    { field: 'name', headerName: t('tags.name', 'Name'), width: 200 },
    { field: 'description', headerName: t('tags.description', 'Description'), width: 300, flex: 1 },
    { field: 'host_count', headerName: t('tags.hostCount', 'Host Count'), width: 120 },
    {
      field: 'updated_at',
      headerName: t('tags.lastUpdated', 'Last Updated'),
      width: 180,
      renderCell: (params) => formatUTCDate(params.value)
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
      renderCell: (params) => formatUTCTimestamp(params.value)
    },
    {
      field: 'created_at',
      headerName: t('queues.created', 'Created At'),
      width: 180,
      renderCell: (params) => formatUTCTimestamp(params.value)
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

      {/* Two-pane layout: grouped category rail on the left, content on the
          right — replaces the old overflowing horizontal tab strip. */}
      <Box sx={{ display: 'flex', gap: 2, flexGrow: 1, minHeight: 0 }}>
        <Box component="nav" aria-label={t('settings.tabsAriaLabel', 'settings tabs')} sx={navRailContainerSx}>
          {settingsGroups.map(group => (
            <Box key={group.id} sx={navRailGroupSx}>
              <Typography variant="overline" sx={navRailGroupTitleSx}>
                {group.label}
              </Typography>
              <List dense disablePadding>
                {group.tabs.map(tab => {
                  const idx = tabNames.indexOf(tab.id);
                  return (
                    <ListItemButton
                      key={tab.id}
                      selected={activeTab === idx}
                      onClick={(e) => handleTabChange(e, idx)}
                      sx={navRailItemSx}
                    >
                      <ListItemText
                        primary={tab.label}
                        slotProps={{ primary: { variant: 'body2' } }}
                      />
                    </ListItemButton>
                  );
                })}
              </List>
            </Box>
          ))}
        </Box>

        {/* Content — keyed off the tab ID at the active index so the mapping is
            stable when a Pro+-gated tab is filtered out for unlicensed users. */}
        <Box sx={{ flexGrow: 1, minHeight: 0, overflow: 'auto' }}>
        {tabNames[activeTab] === 'configuration' && <ConfigurationSettings />}
        {tabNames[activeTab] === 'tags' && renderTagsTab()}
        {tabNames[activeTab] === 'queues' && renderQueuesTab()}
        {tabNames[activeTab] === 'server-role' && <ServerRoleSettings />}
        {tabNames[activeTab] === 'logging' && <LoggingSettings />}
        {tabNames[activeTab] === 'integrations' && <IntegrationsTab />}
        {tabNames[activeTab] === 'ubuntu-pro' && <UbuntuProTab />}
        {tabNames[activeTab] === 'antivirus' && <AntivirusDefaultsSettings />}
        {tabNames[activeTab] === 'available-packages' && (
          <AvailablePackagesTab
            packageSummary={packageSummary}
            packages={packages}
            selectedOS={selectedOS}
            setSelectedOS={setSelectedOS}
            selectedManager={selectedManager}
            setSelectedManager={setSelectedManager}
            packageSearchTerm={packageSearchTerm}
            setPackageSearchTerm={setPackageSearchTerm}
            packageLoading={packageLoading}
            packageSummaryLoading={packageSummaryLoading}
            packageTotalCount={packageTotalCount}
            hasSearched={hasSearched}
            onRefreshAll={refreshAllPackages}
            onRefreshOS={refreshPackagesForOS}
            onSearch={searchPackages}
          />
        )}
        {tabNames[activeTab] === 'host-defaults' && <HostDefaultsSettings />}
        {tabNames[activeTab] === 'firewall-roles' && <FirewallRolesSettings />}
        {tabNames[activeTab] === 'distributions' && <DistributionsSettings />}
        {tabNames[activeTab] === 'update-profiles' && <UpgradeProfilesSettings />}
        {tabNames[activeTab] === 'compliance-profiles' && <PackageProfilesSettings />}
        {tabNames[activeTab] === 'report-branding' && <ReportBrandingSettings />}
        {tabNames[activeTab] === 'report-templates' && <ReportTemplatesSettings />}
        {tabNames[activeTab] === 'airgap-bundles' && <AirGapBundlesSettings />}
        {tabNames[activeTab] === 'repository-mirroring' && <RepositoryMirroringSettings />}
        {tabNames[activeTab] === 'authentication' && <AuthenticationProvidersSettings />}
        {visiblePluginSettingsTabs.map(pt => (
          tabNames[activeTab] === pt.id && (
            <Box key={pt.id}>
              <pt.component />
            </Box>
          )
        ))}
        </Box>
      </Box>

      <SettingsDialogs
        addDialogOpen={addDialogOpen}
        onAddDialogClose={() => setAddDialogOpen(false)}
        onCreateTag={handleCreateTag}
        editDialogOpen={editDialogOpen}
        onEditDialogClose={() => setEditDialogOpen(false)}
        onUpdateTag={handleUpdateTag}
        tagName={tagName}
        setTagName={setTagName}
        tagDescription={tagDescription}
        setTagDescription={setTagDescription}
        viewHostsDialogOpen={viewHostsDialogOpen}
        onViewHostsClose={() => setViewHostsDialogOpen(false)}
        viewingTag={viewingTag}
        messageDetailOpen={messageDetailOpen}
        onMessageDetailClose={() => setMessageDetailOpen(false)}
        selectedMessage={selectedMessage}
      />
    </Box>
  );
};

export default Settings;