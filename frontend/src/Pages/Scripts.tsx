import React, { useState, useEffect, useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import { 
  IoCode, 
  IoPlay, 
  IoAdd, 
  IoSave,
  IoDocumentText,
  IoEye,
  IoTrash,
  IoTime,
  IoRefresh
} from 'react-icons/io5';
import Editor from '@monaco-editor/react';
import {
  Box,
  Card,
  CardContent,
  Typography,
  Button,
  TextField,
  Select,
  MenuItem,
  FormControl,
  InputLabel,
  Grid,
  Tab,
  Tabs,
  Alert,
  Snackbar,
  Chip,
  IconButton,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Stack
} from '@mui/material';
import { DataGrid, GridColDef, GridRowSelectionModel } from '@mui/x-data-grid';
import { 
  scriptsService, 
  Script, 
  Host, 
  ScriptExecution,
  ExecuteScriptRequest 
} from '../Services/scripts';
import { useTablePageSize } from '../hooks/useTablePageSize';
import SearchBox from '../Components/SearchBox';
import './css/Scripts.css';

interface TabPanelProps {
  children?: React.ReactNode;
  index: number;
  value: number;
}

function TabPanel({ children, value, index, ...other }: TabPanelProps) {
  return (
    <div
      role="tabpanel"
      hidden={value !== index}
      id={`scripts-tabpanel-${index}`}
      aria-labelledby={`scripts-tab-${index}`}
      {...other}
    >
      {value === index && (
        <Box sx={{ p: 3 }}>
          {children}
        </Box>
      )}
    </div>
  );
}

const Scripts: React.FC = () => {
  const { t } = useTranslation();
  const [tabValue, setTabValue] = useState(0);
  const [scripts, setScripts] = useState<Script[]>([]);
  const [filteredScripts, setFilteredScripts] = useState<Script[]>([]);
  const [hosts, setHosts] = useState<Host[]>([]);
  const [executions, setExecutions] = useState<ScriptExecution[]>([]);
  const [loading, setLoading] = useState(false);
  const [executionsLoading, setExecutionsLoading] = useState(false);
  
  // Script editor state
  const [scriptName, setScriptName] = useState('');
  const [scriptDescription, setScriptDescription] = useState('');
  const [scriptContent, setScriptContent] = useState('');
  const [selectedShell, setSelectedShell] = useState('bash');
  const [selectedPlatform, setSelectedPlatform] = useState('linux');
  const [hasUserEditedContent, setHasUserEditedContent] = useState(false);
  const [selectedHost, setSelectedHost] = useState<number | ''>('');
  const [savedScriptId, setSavedScriptId] = useState<number | ''>('');
  const [isEditMode, setIsEditMode] = useState(false);
  const [editingScriptId, setEditingScriptId] = useState<number | null>(null);
  
  // Execution state
  const [isExecuting, setIsExecuting] = useState(false);
  const [currentExecutionId, setCurrentExecutionId] = useState<string | null>(null);
  const [executionResult, setExecutionResult] = useState<ScriptExecution | null>(null);
  
  // Script Library state
  const [selectedScripts, setSelectedScripts] = useState<GridRowSelectionModel>([]);
  const [viewingScript, setViewingScript] = useState<Script | null>(null);
  const [showAddScriptDialog, setShowAddScriptDialog] = useState(false);
  const [searchTerm, setSearchTerm] = useState<string>('');
  const [searchColumn, setSearchColumn] = useState<string>('name');
  
  // Execution History state
  const [selectedExecutions, setSelectedExecutions] = useState<GridRowSelectionModel>([]);
  const [viewingExecution, setViewingExecution] = useState<ScriptExecution | null>(null);
  const [showExecutionDialog, setShowExecutionDialog] = useState(false);
  const [showDeleteDialog, setShowDeleteDialog] = useState(false);
  const [scriptToDelete, setScriptToDelete] = useState<number | null>(null);

  // Table pagination
  const { pageSize, pageSizeOptions } = useTablePageSize();
  
  // UI state
  const [notification, setNotification] = useState<{
    open: boolean;
    message: string;
    severity: 'success' | 'error' | 'info' | 'warning';
  }>({ open: false, message: '', severity: 'info' });

  const allShells = [
    { value: 'bash', label: t('scripts.shells.bash'), platforms: ['linux', 'darwin', 'freebsd', 'openbsd', 'netbsd'] },
    { value: 'sh', label: t('scripts.shells.sh'), platforms: ['linux', 'darwin', 'freebsd', 'openbsd', 'netbsd'] },
    { value: 'zsh', label: t('scripts.shells.zsh'), platforms: ['linux', 'darwin', 'freebsd', 'openbsd', 'netbsd'] },
    { value: 'ksh', label: t('scripts.shells.ksh'), platforms: ['linux', 'darwin', 'freebsd', 'openbsd', 'netbsd'] },
    { value: 'powershell', label: t('scripts.shells.powershell'), platforms: ['windows', 'linux', 'darwin'] },
    { value: 'cmd', label: t('scripts.shells.cmd'), platforms: ['windows'] }
  ];

  // Get shells available for the selected platform
  const getShellsForPlatform = (platform: string) => {
    return allShells.filter(shell => shell.platforms.includes(platform));
  };

  // Helper function to check if host is compatible with selected script
  const isHostCompatibleWithScript = (host: Host, script: Script) => {
    // Check if host has script execution enabled
    if (!host.script_execution_enabled) {
      return false;
    }

    // Check if host platform matches script platform (case-insensitive)
    if (script.platform && host.platform) {
      const scriptPlatform = script.platform.toLowerCase();
      const hostPlatform = host.platform.toLowerCase();
      
      // Map common platform names to normalized values
      const normalizedHostPlatform = hostPlatform.startsWith('win') ? 'windows' : 
                                      hostPlatform === 'darwin' ? 'darwin' :
                                      hostPlatform.includes('bsd') ? hostPlatform :
                                      'linux'; // Default to linux for other Unix-like systems
      
      if (scriptPlatform !== normalizedHostPlatform) {
        return false;
      }
    }

    // Check if host has the required shell enabled
    if (host.enabled_shells) {
      try {
        const hostShells = JSON.parse(host.enabled_shells) as string[];
        // Also make shell comparison case-insensitive
        return hostShells.some(shell => shell.toLowerCase() === script.shell_type.toLowerCase());
      } catch {
        return false;
      }
    }

    return false;
  };

  // Get compatible hosts for the selected script
  const getCompatibleHosts = () => {
    if (!savedScriptId) return [];
    
    const selectedScript = scripts.find(s => s.id === savedScriptId);
    if (!selectedScript) return [];
    
    return hosts.filter(host => isHostCompatibleWithScript(host, selectedScript));
  };

  // Reset function to clear all selections and outputs
  const handleReset = () => {
    setSavedScriptId('');
    setSelectedHost('');
    setExecutionResult(null);
    setCurrentExecutionId(null);
    setIsExecuting(false);
    // Reset script content and other fields if needed
    setScriptContent('');
    setScriptName('');
    setHasUserEditedContent(false);
  };

  const shells = getShellsForPlatform(selectedPlatform);

  const platforms = [
    { value: 'linux', label: t('scripts.platforms.linux') },
    { value: 'darwin', label: t('scripts.platforms.darwin') },
    { value: 'windows', label: t('scripts.platforms.windows') },
    { value: 'freebsd', label: t('scripts.platforms.freebsd') },
    { value: 'openbsd', label: t('scripts.platforms.openbsd') },
    { value: 'netbsd', label: t('scripts.platforms.netbsd') }
  ];

  // Search columns configuration (excluding irrelevant columns)
  const searchColumns = [
    { field: 'name', label: t('scripts.scriptName') },
    { field: 'description', label: t('scripts.description') },
    { field: 'shell_type', label: t('scripts.shellType') },
    { field: 'platform', label: t('scripts.platform') }
  ];

  // Load data
  const loadScripts = useCallback(async () => {
    try {
      const data = await scriptsService.getSavedScripts();
      setScripts(data);
    } catch {
      showNotification(t('scripts.loadError'), 'error');
    }
  }, [t]);

  // Search functionality
  const performSearch = useCallback(() => {
    if (!searchTerm.trim()) {
      setFilteredScripts(scripts);
      return;
    }

    const filtered = scripts.filter(script => {
      const fieldValue = script[searchColumn as keyof Script];
      if (fieldValue === null || fieldValue === undefined) {
        return false;
      }
      return String(fieldValue).toLowerCase().includes(searchTerm.toLowerCase());
    });
    
    setFilteredScripts(filtered);
  }, [searchTerm, searchColumn, scripts]);

  // Update filtered data when scripts change or search is cleared
  React.useEffect(() => {
    if (!searchTerm.trim()) {
      setFilteredScripts(scripts);
    } else {
      performSearch();
    }
  }, [scripts, searchTerm, searchColumn, performSearch]);

  const loadHosts = useCallback(async () => {
    try {
      const data = await scriptsService.getActiveHosts();
      setHosts(data);
    } catch (error) {
      console.error('Failed to load hosts:', error);
    }
  }, []);

  const loadExecutions = useCallback(async () => {
    try {
      setExecutionsLoading(true);
      const data = await scriptsService.getScriptExecutions();
      setExecutions(data.executions || []);
    } catch (error) {
      console.error('Failed to load executions:', error);
      setExecutions([]);
    } finally {
      setExecutionsLoading(false);
    }
  }, []);

  useEffect(() => {
    loadScripts();
    loadExecutions();
  }, [loadScripts, loadExecutions]);

  // Load hosts only when Execute Script tab is accessed
  useEffect(() => {
    if (tabValue === 1 && hosts.length === 0) {
      loadHosts();
    }
  }, [tabValue, hosts.length, loadHosts]);

  // Load executions when Script Executions tab is accessed
  useEffect(() => {
    if (tabValue === 2) {
      loadExecutions();
    }
  }, [tabValue, loadExecutions]);

  // Auto-refresh executions every 30 seconds when on the executions tab
  useEffect(() => {
    if (tabValue !== 2) return;

    const interval = window.setInterval(() => {
      loadExecutions();
    }, 30000);

    return () => window.clearInterval(interval);
  }, [tabValue, loadExecutions]);

  // Poll for execution results with adaptive polling
  useEffect(() => {
    if (!isExecuting || !currentExecutionId) return;

    const startTime = Date.now();

    const fetchExecutionResult = async () => {
      try {
        const result = await scriptsService.getScriptExecution(currentExecutionId);
        setExecutionResult(result);
        
        // Stop polling if execution is complete
        if (result.status === 'completed' || result.status === 'failed' || result.status === 'timeout') {
          setIsExecuting(false);
          showNotification(
            result.status === 'completed' 
              ? t('scripts.executionCompleted') 
              : t('scripts.executionFailed'), 
            result.status === 'completed' ? 'success' : 'error'
          );
          // Refresh executions list to show updated status
          loadExecutions();
        }
      } catch (error) {
        console.error('Failed to fetch execution result:', error);
        // If we get a 404, the execution was deleted - stop polling
        const axiosError = error as { response?: { status?: number } };
        if (axiosError.response?.status === 404) {
          setIsExecuting(false);
          setCurrentExecutionId(null);
          setExecutionResult(null);
        }
      }
    };

    // Fetch immediately
    fetchExecutionResult();

    // Adaptive polling strategy:
    // - First 2 minutes: poll every 3 seconds 
    // - After 2 minutes: poll every 15 seconds
    const scheduleNextPoll = () => {
      const elapsed = Date.now() - startTime;
      const interval = elapsed < 120000 ? 3000 : 15000; // 2 minutes threshold
      
      const timeoutId = window.setTimeout(() => {
        if (isExecuting && currentExecutionId) {
          fetchExecutionResult();
          scheduleNextPoll();
        }
      }, interval);
      
      return timeoutId;
    };

    const timeoutId = scheduleNextPoll();

    return () => window.clearTimeout(timeoutId);
  }, [isExecuting, currentExecutionId, t, loadExecutions]);

  const showNotification = (message: string, severity: 'success' | 'error' | 'info' | 'warning' = 'info') => {
    setNotification({ open: true, message, severity });
  };

  const handleCloseNotification = () => {
    setNotification({ ...notification, open: false });
  };

  const handleTabChange = (_event: React.SyntheticEvent, newValue: number) => {
    // Clear execution state when leaving the Execute Script tab (index 1)
    if (tabValue === 1 && newValue !== 1) {
      setSelectedHost('');
      setSavedScriptId('');
      setExecutionResult(null);
      setCurrentExecutionId(null);
      setIsExecuting(false);
    }
    setTabValue(newValue);
  };

  const resetScriptForm = () => {
    setScriptName('');
    setScriptDescription('');
    setScriptContent(getShellHeader('bash', 'linux'));
    setSelectedShell('bash');
    setSelectedPlatform('linux');
    setHasUserEditedContent(false);
    setIsEditMode(false);
    setEditingScriptId(null);
  };

  const handleSaveScript = async () => {
    if (!scriptName.trim()) {
      showNotification(t('scripts.scriptNameRequired'), 'error');
      return;
    }

    if (!scriptContent.trim()) {
      showNotification(t('scripts.scriptContentRequired'), 'error');
      return;
    }

    setLoading(true);
    try {
      const scriptData = {
        name: scriptName,
        description: scriptDescription,
        content: scriptContent,
        shell_type: selectedShell,
        platform: selectedPlatform
      };

      if (isEditMode && editingScriptId) {
        await scriptsService.updateScript(editingScriptId, scriptData);
        showNotification(t('scripts.updateSuccess'), 'success');
      } else {
        await scriptsService.createScript(scriptData);
        showNotification(t('scripts.saveSuccess'), 'success');
      }

      handleCloseAddScriptDialog();
      loadScripts();
    } catch {
      showNotification(isEditMode ? t('scripts.updateError') : t('scripts.saveError'), 'error');
    } finally {
      setLoading(false);
    }
  };


  const handleDeleteScript = (scriptId: number) => {
    setScriptToDelete(scriptId);
    setShowDeleteDialog(true);
  };

  const handleConfirmDelete = async () => {
    if (!scriptToDelete) return;

    try {
      await scriptsService.deleteScript(scriptToDelete);
      showNotification(t('scripts.deleteSuccess'), 'success');
      loadScripts();
    } catch {
      showNotification(t('scripts.deleteError'), 'error');
    } finally {
      setShowDeleteDialog(false);
      setScriptToDelete(null);
    }
  };

  const handleCancelDelete = () => {
    setShowDeleteDialog(false);
    setScriptToDelete(null);
  };

  const handleExecuteScript = async () => {
    // Prevent double execution
    if (loading || isExecuting) {
      console.warn('Script execution already in progress, ignoring request');
      return;
    }

    if (selectedHost === '') {
      showNotification(t('scripts.hostRequired'), 'error');
      return;
    }

    // Check if selected host appears to be offline
    const selectedHostData = hosts.find(h => h.id === selectedHost);
    if (selectedHostData && !isHostConnected(selectedHostData)) {
      const confirmMessage = t('scripts.hostAppearsOffline') + '\n\n' + t('scripts.continueExecution');
      if (!window.confirm(confirmMessage)) {
        return;
      }
    }

    const executeRequest: ExecuteScriptRequest = {
      host_id: selectedHost as string
    };

    if (savedScriptId) {
      executeRequest.saved_script_id = savedScriptId as string;
    } else {
      if (!scriptContent.trim()) {
        showNotification(t('scripts.scriptContentRequired'), 'error');
        return;
      }
      executeRequest.script_name = scriptName || 'Ad-hoc Script';
      executeRequest.script_content = scriptContent;
      executeRequest.shell_type = selectedShell;
    }

    setLoading(true);
    setIsExecuting(true);
    setExecutionResult(null);
    
    try {
      const response = await scriptsService.executeScript(executeRequest);
      setCurrentExecutionId(response.execution_id);
      showNotification(t('scripts.executeSuccess'), 'success');
      loadExecutions();
    } catch (error) {
      setIsExecuting(false);
      const axiosError = error as { response?: { status?: number } };
      if (axiosError.response?.status === 503) {
        showNotification(t('scripts.errors.hostNotConnected'), 'warning');
      } else {
        showNotification(t('scripts.executeError'), 'error');
      }
    } finally {
      setLoading(false);
    }
  };

  const handleSavedScriptSelect = (scriptId: number) => {
    const script = scripts.find(s => s.id === scriptId);
    if (script) {
      setScriptContent(script.content);
      setSelectedShell(script.shell_type);
      setScriptName(script.name);
      setHasUserEditedContent(true); // Content is loaded from existing script
    }
  };

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'pending':
        return 'default';
      case 'running':
        return 'info';
      case 'completed':
        return 'success';
      case 'failed':
        return 'error';
      case 'timeout':
        return 'warning';
      default:
        return 'default';
    }
  };

  const getLanguageForShell = (shell: string): string => {
    switch (shell) {
      case 'bash':
      case 'sh':
      case 'zsh':
      case 'ksh':
        return 'shell';
      case 'powershell':
        return 'powershell';
      case 'cmd':
        return 'bat';
      default:
        return 'shell';
    }
  };

  // Get the appropriate shebang/header for a shell type and platform
  const getShellHeader = useCallback((shell: string, platform: string = selectedPlatform): string => {
    switch (shell) {
      case 'bash':
        // bash locations vary by OS
        switch (platform) {
          case 'linux':
          case 'darwin':
            return '#!/bin/bash\n\n';
          case 'freebsd':
          case 'openbsd':
          case 'netbsd':
            return '#!/usr/local/bin/bash\n\n';
          default:
            return '#!/bin/bash\n\n';
        }
      case 'sh':
        // sh is usually in /bin on all Unix-like systems
        return '#!/bin/sh\n\n';
      case 'zsh':
        // zsh locations
        switch (platform) {
          case 'linux':
            return '#!/bin/zsh\n\n';
          case 'darwin':
            return '#!/bin/zsh\n\n';
          case 'freebsd':
          case 'openbsd':
          case 'netbsd':
            return '#!/usr/local/bin/zsh\n\n';
          default:
            return '#!/bin/zsh\n\n';
        }
      case 'ksh':
        // ksh locations
        switch (platform) {
          case 'linux':
            return '#!/bin/ksh\n\n';
          case 'darwin':
            return '#!/bin/ksh\n\n';
          case 'freebsd':
          case 'netbsd':
            return '#!/usr/local/bin/ksh\n\n';
          case 'openbsd':
            return '#!/bin/ksh\n\n'; // ksh is default shell on OpenBSD
          default:
            return '#!/bin/ksh\n\n';
        }
      case 'powershell':
        return '# PowerShell Script\n\n';
      case 'cmd':
        return '@echo off\nREM Windows Batch Script\n\n';
      default:
        return '#!/bin/bash\n\n';
    }
  }, [selectedPlatform]);

  // Initialize script content with correct shebang on component mount
  useEffect(() => {
    if (!scriptContent) {
      setScriptContent(getShellHeader('bash', 'linux'));
    }
  }, [scriptContent, getShellHeader]);

  // Cleanup effect to clear execution result when component unmounts
  useEffect(() => {
    return () => {
      // Clear execution state when component unmounts
      setExecutionResult(null);
      setCurrentExecutionId(null);
      setIsExecuting(false);
    };
  }, []);

  // Handle platform change
  const handlePlatformChange = (newPlatform: string) => {
    setSelectedPlatform(newPlatform);
    
    // Check if current shell is available for the new platform
    const availableShells = getShellsForPlatform(newPlatform);
    const currentShellAvailable = availableShells.some(shell => shell.value === selectedShell);
    
    if (!currentShellAvailable && availableShells.length > 0) {
      // Switch to the first available shell for this platform
      const defaultShell = availableShells[0].value;
      setSelectedShell(defaultShell);
      
      // Update script content if user hasn't edited it
      if (!hasUserEditedContent) {
        setScriptContent(getShellHeader(defaultShell, newPlatform));
      }
    } else {
      // Current shell is still available, but platform changed so update shebang path
      if (!hasUserEditedContent) {
        setScriptContent(getShellHeader(selectedShell, newPlatform));
      }
    }
  };

  // Handle shell type change
  const handleShellChange = (newShell: string) => {
    setSelectedShell(newShell);
    
    // Update script content if user hasn't edited it
    if (!hasUserEditedContent) {
      setScriptContent(getShellHeader(newShell, selectedPlatform));
    }
  };

  // Handle script content change
  const handleScriptContentChange = (value: string | undefined) => {
    setScriptContent(value || '');
    setHasUserEditedContent(true);
  };

  const formatTimestamp = (timestamp: string | undefined) => {
    if (!timestamp) return t('common.notAvailable');
    return new Date(timestamp).toLocaleString();
  };

  const isHostConnected = (host: Host): boolean => {
    // Use the actual status field from the database
    return host.status === 'up' && host.active === true;
  };

  // DataGrid columns definition
  const columns: GridColDef[] = [
    {
      field: 'name',
      headerName: t('scripts.scriptName'),
      width: 200,
      flex: 1,
    },
    {
      field: 'description',
      headerName: t('scripts.description'),
      width: 300,
      flex: 1,
      renderCell: (params) => (
        <Typography variant="body2" color="textSecondary">
          {params.value || t('common.noDescription')}
        </Typography>
      ),
    },
    {
      field: 'shell_type',
      headerName: t('scripts.shellType'),
      width: 120,
      renderCell: (params) => (
        <Chip 
          label={allShells.find(s => s.value === params.value)?.label || params.value} 
          size="small" 
          variant="outlined"
        />
      ),
    },
    {
      field: 'platform',
      headerName: t('scripts.platform'),
      width: 120,
      renderCell: (params) => (
        <Chip 
          label={platforms.find(p => p.value === params.value)?.label || params.value} 
          size="small" 
          variant="outlined"
        />
      ),
    },
    {
      field: 'updated_at',
      headerName: t('scripts.updatedAt'),
      width: 150,
      renderCell: (params) => (
        <Typography variant="caption">
          {formatTimestamp(params.value)}
        </Typography>
      ),
    },
    {
      field: 'actions',
      headerName: t('common.actions'),
      width: 100,
      sortable: false,
      filterable: false,
      disableColumnMenu: true,
      renderCell: (params) => (
        <IconButton
          size="small"
          onClick={() => handleViewScript(params.row as Script)}
          title={t('scripts.viewScript')}
          sx={{ color: 'primary.main' }}
        >
          <IoEye />
        </IconButton>
      ),
    },
  ];

  // Execution History DataGrid columns
  const executionColumns: GridColDef[] = [
    {
      field: 'script_name',
      headerName: t('scripts.scriptName'),
      width: 200,
      flex: 1,
    },
    {
      field: 'host_fqdn',
      headerName: t('scripts.hostFqdn'),
      width: 200,
      flex: 1,
    },
    {
      field: 'status',
      headerName: t('common.status'),
      width: 120,
      renderCell: (params) => (
        <Chip 
          label={t(`scripts.status.${params.value}`)} 
          color={getStatusColor(params.value) as 'success' | 'error' | 'warning' | 'info' | 'default'}
          size="small"
        />
      ),
    },
    {
      field: 'started_at',
      headerName: t('scripts.startedAt'),
      width: 180,
      renderCell: (params) => (
        <Typography variant="body2">
          {formatTimestamp(params.value)}
        </Typography>
      ),
    },
    {
      field: 'completed_at',
      headerName: t('scripts.completedAt'),
      width: 180,
      renderCell: (params) => (
        <Typography variant="body2">
          {params.value ? formatTimestamp(params.value) : '-'}
        </Typography>
      ),
    },
    {
      field: 'exit_code',
      headerName: t('scripts.exitCode'),
      width: 100,
      renderCell: (params) => (
        <Typography variant="body2">
          {params.value !== undefined ? params.value : '-'}
        </Typography>
      ),
    },
    {
      field: 'execution_time',
      headerName: t('scripts.executionTime'),
      width: 140,
      renderCell: (params) => (
        <Typography variant="body2">
          {params.value ? `${params.value}s` : '-'}
        </Typography>
      ),
    },
    {
      field: 'actions',
      headerName: t('common.actions'),
      width: 100,
      sortable: false,
      filterable: false,
      renderCell: (params) => (
        <IconButton
          size="small"
          onClick={() => handleViewExecution(params.row)}
          disabled={!params.row.stdout_output && !params.row.stderr_output && !params.row.error_message}
          sx={{ 
            color: 'primary.main',
            '&:disabled': { 
              color: 'grey.400' 
            }
          }}
        >
          <IoEye />
        </IconButton>
      ),
    },
  ];

  const handleViewScript = (script: Script) => {
    setViewingScript(script);
  };

  const handleCloseScriptView = () => {
    setViewingScript(null);
  };

  const handleViewExecution = (execution: ScriptExecution) => {
    setViewingExecution(execution);
    setShowExecutionDialog(true);
  };

  const handleCloseExecutionView = () => {
    setViewingExecution(null);
    setShowExecutionDialog(false);
  };

  const handleEditFromLibrary = (script: Script) => {
    setScriptName(script.name);
    setScriptDescription(script.description);
    setScriptContent(script.content);
    setSelectedShell(script.shell_type);
    setSelectedPlatform(script.platform || 'linux');
    setHasUserEditedContent(true); // Content is from existing script
    setIsEditMode(true);
    setEditingScriptId(script.id || null);
    setShowAddScriptDialog(true);
    setViewingScript(null);
  };

  const handleDeleteSelected = async () => {
    if (selectedScripts.length === 0) return;
    
    const confirmMessage = selectedScripts.length === 1 
      ? t('scripts.delete') + '?' 
      : t('scripts.deleteSelected') + ` (${selectedScripts.length})?`;
    
    if (!window.confirm(confirmMessage)) {
      return;
    }

    setLoading(true);
    try {
      for (const scriptId of selectedScripts) {
        await scriptsService.deleteScript(scriptId as string);
      }
      showNotification(
        selectedScripts.length === 1 
          ? t('scripts.deleteSuccess') 
          : t('scripts.deleteSuccess'), 
        'success'
      );
      setSelectedScripts([]);
      loadScripts();
    } catch {
      showNotification(t('scripts.deleteError'), 'error');
    } finally {
      setLoading(false);
    }
  };

  const handleDeleteSelectedExecutions = async () => {
    if (selectedExecutions.length === 0) return;

    setExecutionsLoading(true);
    try {
      // Map DataGrid selection IDs (database IDs) to execution_ids
      for (const databaseId of selectedExecutions) {
        const execution = executions.find(exec => exec.id === databaseId);
        if (execution) {
          await scriptsService.deleteScriptExecution(execution.execution_id);
        }
      }
      showNotification(
        selectedExecutions.length === 1 
          ? t('scripts.deleteExecutionSuccess') 
          : t('scripts.deleteExecutionsSuccess'), 
        'success'
      );
      setSelectedExecutions([]);
      loadExecutions();
    } catch {
      showNotification(t('scripts.deleteExecutionError'), 'error');
    } finally {
      setExecutionsLoading(false);
    }
  };

  const handleAddNewScript = () => {
    // Clear the form and open the dialog
    setScriptName('');
    setScriptDescription('');
    setScriptContent(getShellHeader('bash', 'linux'));
    setSelectedShell('bash');
    setSelectedPlatform('linux');
    setHasUserEditedContent(false);
    setIsEditMode(false);
    setEditingScriptId(null);
    setShowAddScriptDialog(true);
  };

  const handleCloseAddScriptDialog = () => {
    setShowAddScriptDialog(false);
    resetScriptForm();
  };

  const handleSaveNewScript = async () => {
    if (!scriptName.trim()) {
      showNotification(t('scripts.scriptNameRequired'), 'error');
      return;
    }

    if (!scriptContent.trim()) {
      showNotification(t('scripts.scriptContentRequired'), 'error');
      return;
    }

    setLoading(true);
    try {
      const scriptData = {
        name: scriptName,
        description: scriptDescription,
        content: scriptContent,
        shell_type: selectedShell,
        platform: selectedPlatform
      };

      await scriptsService.createScript(scriptData);
      showNotification(t('scripts.saveSuccess'), 'success');
      handleCloseAddScriptDialog();
      loadScripts();
    } catch {
      showNotification(t('scripts.saveError'), 'error');
    } finally {
      setLoading(false);
    }
  };

  return (
    <Box className="scripts-container">
      <Typography variant="h4" component="h1" gutterBottom>
        <IoCode style={{ marginRight: '0.5rem', verticalAlign: 'middle' }} />
        {t('scripts.title')}
      </Typography>

      <Box sx={{ borderBottom: 1, borderColor: 'divider', mb: 2 }}>
        <Tabs value={tabValue} onChange={handleTabChange}>
          <Tab 
            icon={<IoDocumentText />} 
            iconPosition="start"
            label={t('scripts.scriptLibrary')} 
          />
          <Tab 
            icon={<IoPlay />} 
            iconPosition="start"
            label={t('scripts.executeScript')} 
          />
          <Tab 
            icon={<IoTime />} 
            iconPosition="start"
            label={t('scripts.scriptExecutions')} 
          />
        </Tabs>
      </Box>

      {/* Script Library Tab */}
      <TabPanel value={tabValue} index={0}>
        <Box sx={{ mb: 2, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <Typography variant="h6">
            {t('scripts.scriptLibrary')}
          </Typography>
        </Box>

        {/* Search Box */}
        <SearchBox
          searchTerm={searchTerm}
          setSearchTerm={setSearchTerm}
          searchColumn={searchColumn}
          setSearchColumn={setSearchColumn}
          columns={searchColumns}
          placeholder={t('search.searchScripts', 'Search scripts')}
        />

        <div style={{ height: 400 }}>
          <DataGrid
            rows={filteredScripts}
            columns={columns}
            initialState={{
              pagination: {
                paginationModel: { pageSize: pageSize, page: 0 },
              },
            }}
            pageSizeOptions={pageSizeOptions}
            checkboxSelection
            rowSelectionModel={selectedScripts}
            onRowSelectionModelChange={setSelectedScripts}
            disableRowSelectionOnClick
            localeText={{
              MuiTablePagination: {
                labelRowsPerPage: t('common.rowsPerPage'),
                labelDisplayedRows: ({ from, to, count }: { from: number, to: number, count: number }) =>
                  `${from}–${to} ${t('common.of')} ${count !== -1 ? count : `${t('common.of')} ${to}`}`,
              },
              noRowsLabel: t('scripts.noScripts'),
              noResultsOverlayLabel: t('scripts.noScripts'),
              footerRowSelected: (count: number) => 
                count !== 1 
                  ? `${count.toLocaleString()} ${t('common.rowsSelected')}`
                  : `${count.toLocaleString()} ${t('common.rowSelected')}`,
            }}
          />
        </div>
        <Box component="section">&nbsp;</Box>
        <Stack direction="row" spacing={2}>
          <Button
            variant="outlined"
            startIcon={<IoAdd />}
            onClick={handleAddNewScript}
            disabled={selectedScripts.length > 0}
          >
            {t('scripts.addScript')}
          </Button>
          <Button
            variant="outlined"
            color="error"
            startIcon={<IoTrash />}
            onClick={handleDeleteSelected}
            disabled={selectedScripts.length === 0}
          >
            {t('scripts.deleteSelected')}
          </Button>
        </Stack>
      </TabPanel>

      {/* Execute Script Tab */}
      <TabPanel value={tabValue} index={1}>
        <Grid container spacing={3}>
          {/* Left Card - Execute Script */}
          <Grid item xs={12} md={5}>
            <Card>
              <CardContent>
                <Box sx={{ display: 'flex', alignItems: 'center', mb: 2 }}>
                  <Typography variant="h6" sx={{ flexGrow: 1 }}>
                    {t('scripts.executeScript')}
                  </Typography>
                  <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                    {isExecuting && (
                      <Chip 
                        label={t('scripts.executing')} 
                        color="success" 
                        size="small"
                        sx={{ animation: 'pulse 1.5s ease-in-out infinite' }}
                      />
                    )}
                    <IconButton
                      onClick={handleReset}
                      disabled={!savedScriptId && !selectedHost}
                      size="small"
                      color="primary"
                      title={t('scripts.reset')}
                    >
                      <IoRefresh />
                    </IconButton>
                  </Box>
                </Box>
                
                <FormControl fullWidth margin="normal">
                  <InputLabel>{t('scripts.selectScript')}</InputLabel>
                  <Select
                    value={savedScriptId}
                    label={t('scripts.selectScript')}
                    onChange={(e) => {
                      const scriptId = e.target.value as number;
                      setSavedScriptId(scriptId);
                      // Clear host selection when script changes
                      setSelectedHost('');
                      if (scriptId) {
                        handleSavedScriptSelect(scriptId);
                      }
                    }}
                    disabled={isExecuting || (savedScriptId !== '' && selectedHost !== '')}
                  >
                    {scripts.map((script) => (
                      <MenuItem key={script.id} value={script.id}>
                        {script.name}
                      </MenuItem>
                    ))}
                  </Select>
                </FormControl>

                <FormControl fullWidth margin="normal">
                  <InputLabel>{t('scripts.selectHost')}</InputLabel>
                  <Select
                    value={selectedHost}
                    label={t('scripts.selectHost')}
                    onChange={(e) => setSelectedHost(e.target.value as number)}
                    disabled={isExecuting || !savedScriptId}
                  >
                    {getCompatibleHosts().map((host) => (
                      <MenuItem key={host.id} value={host.id}>
                        <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', width: '100%' }}>
                          <Typography>{host.fqdn}</Typography>
                          <Box sx={{ display: 'flex', gap: 1 }}>
                            <Chip 
                              label={isHostConnected(host) ? 'Connected' : 'Offline'} 
                              size="small" 
                              color={isHostConnected(host) ? 'success' : 'warning'}
                              variant="outlined"
                            />
                          </Box>
                        </Box>
                      </MenuItem>
                    ))}
                  </Select>
                </FormControl>

                {savedScriptId && (
                  <Box sx={{ 
                    mt: 2, 
                    p: 2, 
                    bgcolor: 'primary.50', 
                    borderRadius: 1, 
                    border: 1, 
                    borderColor: 'primary.200' 
                  }}>
                    <Typography variant="subtitle2" gutterBottom color="primary">
                      {t('scripts.selectedScript')}:
                    </Typography>
                    <Typography variant="body2" gutterBottom>
                      <strong>{scriptName}</strong>
                    </Typography>
                    <Typography variant="body2" color="textSecondary">
                      {t('scripts.shellType')}: {allShells.find(s => s.value === selectedShell)?.label}
                    </Typography>
                  </Box>
                )}

                <Button
                  variant="contained"
                  color="primary"
                  fullWidth
                  size="large"
                  startIcon={<IoPlay />}
                  onClick={handleExecuteScript}
                  disabled={loading || !savedScriptId || !selectedHost || isExecuting}
                  sx={{ mt: 3, py: 1.5 }}
                >
                  {isExecuting ? t('scripts.executing') : t('scripts.executeNow')}
                </Button>
              </CardContent>
            </Card>
          </Grid>

          {/* Right Card - Execution Output */}
          <Grid item xs={12} md={7}>
            <Card sx={{ height: '100%', minHeight: 500 }}>
              <CardContent>
                <Typography variant="h6" gutterBottom>
                  {t('scripts.executionOutput')}
                </Typography>
                
                {!executionResult && !isExecuting && (
                  <Box sx={{ 
                    height: 400, 
                    display: 'flex', 
                    flexDirection: 'column',
                    alignItems: 'center', 
                    justifyContent: 'center',
                    bgcolor: 'background.default',
                    borderRadius: 1,
                    border: '2px dashed',
                    borderColor: 'divider'
                  }}>
                    <IoCode style={{ fontSize: '3rem', color: '#9e9e9e', marginBottom: '1rem' }} />
                    <Typography variant="h6" color="textSecondary" gutterBottom>
                      {t('scripts.noExecutionSelected')}
                    </Typography>
                    <Typography variant="body2" color="textSecondary" sx={{ textAlign: 'center', maxWidth: '80%' }}>
                      {t('scripts.selectScriptAndHost', 'Select a script and host, then click Execute Now to see output here')}
                    </Typography>
                  </Box>
                )}

                {isExecuting && !executionResult && (
                  <Box sx={{ 
                    height: 400, 
                    display: 'flex', 
                    flexDirection: 'column',
                    alignItems: 'center', 
                    justifyContent: 'center',
                    bgcolor: 'background.default',
                    borderRadius: 1,
                    border: '2px dashed',
                    borderColor: 'primary.light'
                  }}>
                    <Box sx={{ textAlign: 'center' }}>
                      <IoPlay style={{ 
                        fontSize: '3rem', 
                        color: '#1976d2', 
                        marginBottom: '1rem',
                        animation: 'pulse 1.5s ease-in-out infinite'
                      }} />
                      <Typography variant="h6" color="primary" gutterBottom>
                        {t('scripts.waitingForResults')}
                      </Typography>
                      <Typography variant="body2" color="textSecondary">
                        {t('scripts.refreshingFrequently')}
                      </Typography>
                    </Box>
                  </Box>
                )}

                {executionResult && (
                  <Box>
                    {/* Execution Status */}
                    <Box sx={{ mb: 2 }}>
                      <Box sx={{ display: 'flex', gap: 1, mb: 1 }}>
                        <Chip 
                          label={t(`scripts.status.${executionResult.status}`)} 
                          color={getStatusColor(executionResult.status) as 'success' | 'error' | 'warning' | 'info' | 'default'}
                          size="small"
                        />
                        {executionResult.exit_code !== undefined && (
                          <Chip 
                            label={`Exit Code: ${executionResult.exit_code}`}
                            size="small"
                            variant="outlined"
                          />
                        )}
                      </Box>
                      <Typography variant="caption" color="textSecondary">
                        {t('scripts.startedAt')}: {formatTimestamp(executionResult.started_at)}
                        {executionResult.completed_at && (
                          <> | {t('scripts.completedAt')}: {formatTimestamp(executionResult.completed_at)}</>
                        )}
                      </Typography>
                    </Box>

                    {/* Output Display */}
                    <Box sx={{ 
                      bgcolor: '#1e1e1e', 
                      color: '#d4d4d4',
                      p: 2,
                      borderRadius: 1,
                      fontFamily: 'monospace',
                      fontSize: '0.875rem',
                      maxHeight: 350,
                      overflow: 'auto',
                      whiteSpace: 'pre-wrap',
                      wordBreak: 'break-all'
                    }}>
                      {executionResult.stdout_output && (
                        <Box>
                          <Typography sx={{ color: '#4ec9b0', fontFamily: 'monospace', fontSize: '0.875rem' }}>
                            === STDOUT ===
                          </Typography>
                          <Typography sx={{ color: '#d4d4d4', fontFamily: 'monospace', fontSize: '0.875rem', whiteSpace: 'pre-wrap' }}>
                            {executionResult.stdout_output}
                          </Typography>
                        </Box>
                      )}
                      {executionResult.stderr_output && (
                        <Box sx={{ mt: executionResult.stdout_output ? 2 : 0 }}>
                          <Typography sx={{ color: '#f48771', fontFamily: 'monospace', fontSize: '0.875rem' }}>
                            === STDERR ===
                          </Typography>
                          <Typography sx={{ color: '#f48771', fontFamily: 'monospace', fontSize: '0.875rem', whiteSpace: 'pre-wrap' }}>
                            {executionResult.stderr_output}
                          </Typography>
                        </Box>
                      )}
                      {executionResult.error_message && (
                        <Box sx={{ mt: 2 }}>
                          <Typography sx={{ color: '#ff6b6b', fontFamily: 'monospace', fontSize: '0.875rem' }}>
                            === ERROR ===
                          </Typography>
                          <Typography sx={{ color: '#ff6b6b', fontFamily: 'monospace', fontSize: '0.875rem', whiteSpace: 'pre-wrap' }}>
                            {executionResult.error_message}
                          </Typography>
                        </Box>
                      )}
                      {!executionResult.stdout_output && !executionResult.stderr_output && !executionResult.error_message && (
                        <Typography sx={{ color: '#808080', fontFamily: 'monospace', fontSize: '0.875rem' }}>
                          {t('scripts.noOutput')}
                        </Typography>
                      )}
                    </Box>
                  </Box>
                )}
              </CardContent>
            </Card>
          </Grid>
        </Grid>
      </TabPanel>

      {/* Script Executions Tab */}
      <TabPanel value={tabValue} index={2}>
        <div style={{ height: 400 }}>
          <DataGrid
            rows={executions}
            columns={executionColumns}
            loading={executionsLoading}
            pageSizeOptions={pageSizeOptions}
            initialState={{
              pagination: { paginationModel: { pageSize: pageSize } },
              sorting: { sortModel: [{ field: 'started_at', sort: 'desc' }] },
            }}
            checkboxSelection={true}
            rowSelectionModel={selectedExecutions}
            onRowSelectionModelChange={setSelectedExecutions}
            disableRowSelectionOnClick
            localeText={{
              MuiTablePagination: {
                labelRowsPerPage: t('common.rowsPerPage'),
                labelDisplayedRows: ({ from, to, count }: { from: number, to: number, count: number }) =>
                  `${from}–${to} ${t('common.of')} ${count !== -1 ? count : `${t('common.of')} ${to}`}`,
              },
              noRowsLabel: t('scripts.noExecutions'),
              noResultsOverlayLabel: t('scripts.noExecutions'),
              footerRowSelected: (count: number) => 
                count !== 1 
                  ? `${count.toLocaleString()} ${t('common.rowsSelected')}`
                  : `${count.toLocaleString()} ${t('common.rowSelected')}`,
            }}
          />
        </div>
        <Box component="section">&nbsp;</Box>
        <Button
          variant="outlined"
          color="error"
          startIcon={<IoTrash />}
          onClick={handleDeleteSelectedExecutions}
          disabled={selectedExecutions.length === 0}
        >
          {t('scripts.deleteSelectedExecutions')}
        </Button>
      </TabPanel>

      {/* Script Viewing Dialog */}
      <Dialog
        open={!!viewingScript}
        onClose={handleCloseScriptView}
        maxWidth="md"
        fullWidth
      >
        {viewingScript && (
          <>
            <DialogTitle>
              <Typography variant="h6" component="div" sx={{ flexGrow: 1 }}>
                {viewingScript.name}
              </Typography>
            </DialogTitle>
            <DialogContent>
              <Box sx={{ mb: 2 }}>
                <Typography variant="body2" color="textSecondary" gutterBottom>
                  <strong>{t('scripts.description')}:</strong> {viewingScript.description || t('common.noDescription')}
                </Typography>
                <Box sx={{ display: 'flex', gap: 1, mb: 2 }}>
                  <Chip 
                    label={allShells.find(s => s.value === viewingScript.shell_type)?.label || viewingScript.shell_type} 
                    size="small" 
                    variant="outlined"
                  />
                  <Chip 
                    label={platforms.find(p => p.value === viewingScript.platform)?.label || viewingScript.platform} 
                    size="small" 
                    variant="outlined"
                  />
                </Box>
                <Typography variant="caption" display="block" gutterBottom>
                  {t('scripts.updatedAt')}: {formatTimestamp(viewingScript.updated_at)}
                </Typography>
              </Box>
              
              <Typography variant="subtitle2" gutterBottom>
                {t('scripts.scriptContent')}
              </Typography>
              <Box sx={{ border: 1, borderColor: 'grey.300', borderRadius: 1 }}>
                <Editor
                  height="400px"
                  language={getLanguageForShell(viewingScript.shell_type)}
                  value={viewingScript.content}
                  theme="vs-dark"
                  options={{
                    readOnly: true,
                    minimap: { enabled: false },
                    scrollBeyondLastLine: false,
                    fontSize: 14,
                    lineNumbers: 'on',
                    automaticLayout: true
                  }}
                />
              </Box>
            </DialogContent>
            <DialogActions>
              <Button
                variant="outlined"
                color="error"
                startIcon={<IoTrash />}
                onClick={() => {
                  if (viewingScript.id) {
                    handleDeleteScript(viewingScript.id);
                    handleCloseScriptView();
                  }
                }}
              >
                {t('scripts.delete')}
              </Button>
              <Button
                variant="contained"
                onClick={() => handleEditFromLibrary(viewingScript)}
              >
                {t('scripts.edit')}
              </Button>
              <Button onClick={handleCloseScriptView}>
                {t('common.close')}
              </Button>
            </DialogActions>
          </>
        )}
      </Dialog>

      {/* Execution Viewing Dialog */}
      <Dialog
        open={showExecutionDialog}
        onClose={handleCloseExecutionView}
        maxWidth="md"
        fullWidth
      >
        {viewingExecution && (
          <>
            <DialogTitle>
              <Typography variant="h6" component="div" sx={{ flexGrow: 1 }}>
                {t('scripts.executionDetails')}
              </Typography>
            </DialogTitle>
            <DialogContent>
              <Box sx={{ mb: 3 }}>
                <Grid container spacing={2}>
                  <Grid item xs={12} md={6}>
                    <Typography variant="body2" gutterBottom>
                      <strong>{t('scripts.scriptName')}:</strong> {viewingExecution.script_name}
                    </Typography>
                  </Grid>
                  <Grid item xs={12} md={6}>
                    <Typography variant="body2" gutterBottom>
                      <strong>{t('scripts.hostFqdn')}:</strong> {viewingExecution.host_fqdn}
                    </Typography>
                  </Grid>
                  <Grid item xs={12} md={6}>
                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                      <Typography variant="body2">
                        <strong>{t('common.status')}:</strong>
                      </Typography>
                      <Chip 
                        label={t(`scripts.status.${viewingExecution.status}`)} 
                        color={getStatusColor(viewingExecution.status) as 'success' | 'error' | 'warning' | 'info' | 'default'}
                        size="small"
                      />
                    </Box>
                  </Grid>
                  <Grid item xs={12} md={6}>
                    <Typography variant="body2" gutterBottom>
                      <strong>{t('scripts.executionId')}:</strong> {viewingExecution.id}
                    </Typography>
                  </Grid>
                  <Grid item xs={12} md={6}>
                    <Typography variant="body2" gutterBottom>
                      <strong>{t('scripts.startedAt')}:</strong> {formatTimestamp(viewingExecution.started_at)}
                    </Typography>
                  </Grid>
                  <Grid item xs={12} md={6}>
                    <Typography variant="body2" gutterBottom>
                      <strong>{t('scripts.completedAt')}:</strong> {viewingExecution.completed_at ? formatTimestamp(viewingExecution.completed_at) : '-'}
                    </Typography>
                  </Grid>
                  {viewingExecution.exit_code !== undefined && (
                    <Grid item xs={12} md={6}>
                      <Typography variant="body2" gutterBottom>
                        <strong>{t('scripts.exitCode')}:</strong> {viewingExecution.exit_code}
                      </Typography>
                    </Grid>
                  )}
                  {viewingExecution.execution_time && (
                    <Grid item xs={12} md={6}>
                      <Typography variant="body2" gutterBottom>
                        <strong>{t('scripts.executionTime')}:</strong> {viewingExecution.execution_time}s
                      </Typography>
                    </Grid>
                  )}
                </Grid>
              </Box>
              
              {viewingExecution.stdout_output && (
                <Box sx={{ mb: 2 }}>
                  <Typography variant="subtitle2" gutterBottom>
                    {t('scripts.stdoutOutput')}
                  </Typography>
                  <Box sx={{ 
                    bgcolor: '#1e1e1e', 
                    color: '#d4d4d4',
                    p: 2, 
                    borderRadius: 1,
                    fontFamily: 'monospace',
                    fontSize: '0.875rem',
                    maxHeight: '200px',
                    overflow: 'auto',
                    whiteSpace: 'pre-wrap'
                  }}>
                    {viewingExecution.stdout_output}
                  </Box>
                </Box>
              )}
              
              {viewingExecution.stderr_output && (
                <Box sx={{ mb: 2 }}>
                  <Typography variant="subtitle2" gutterBottom>
                    {t('scripts.stderrOutput')}
                  </Typography>
                  <Box sx={{ 
                    bgcolor: '#1e1e1e', 
                    color: '#f48771',
                    p: 2, 
                    borderRadius: 1,
                    fontFamily: 'monospace',
                    fontSize: '0.875rem',
                    maxHeight: '200px',
                    overflow: 'auto',
                    whiteSpace: 'pre-wrap'
                  }}>
                    {viewingExecution.stderr_output}
                  </Box>
                </Box>
              )}
              
              {viewingExecution.error_message && (
                <Box sx={{ mb: 2 }}>
                  <Typography variant="subtitle2" gutterBottom>
                    {t('scripts.errorMessage')}
                  </Typography>
                  <Alert severity="error">
                    {viewingExecution.error_message}
                  </Alert>
                </Box>
              )}
            </DialogContent>
            <DialogActions>
              <Button onClick={handleCloseExecutionView}>
                {t('common.close')}
              </Button>
            </DialogActions>
          </>
        )}
      </Dialog>

      {/* Add Script Dialog */}
      <Dialog
        open={showAddScriptDialog}
        onClose={handleCloseAddScriptDialog}
        maxWidth="md"
        fullWidth
      >
        <DialogTitle>
          <Typography variant="h6" component="div" sx={{ flexGrow: 1 }}>
            {isEditMode ? t('scripts.edit') : t('scripts.addScript')}
          </Typography>
        </DialogTitle>
        <DialogContent>
          <Box sx={{ mt: 2 }}>
            <TextField
              fullWidth
              label={t('scripts.scriptName')}
              value={scriptName}
              onChange={(e) => setScriptName(e.target.value)}
              margin="normal"
            />
            <TextField
              fullWidth
              label={t('scripts.description')}
              value={scriptDescription}
              onChange={(e) => setScriptDescription(e.target.value)}
              margin="normal"
              multiline
              rows={2}
            />
            
            <Grid container spacing={2} sx={{ mt: 1 }}>
              <Grid item xs={12} sm={6}>
                <FormControl fullWidth variant="outlined">
                  <InputLabel id="shell-type-label">
                    {t('scripts.shellType')}
                  </InputLabel>
                  <Select
                    labelId="shell-type-label"
                    value={selectedShell}
                    label={t('scripts.shellType')}
                    onChange={(e) => handleShellChange(e.target.value)}
                  >
                    {shells.map((shell) => (
                      <MenuItem key={shell.value} value={shell.value}>
                        {shell.label}
                      </MenuItem>
                    ))}
                  </Select>
                </FormControl>
              </Grid>
              <Grid item xs={12} sm={6}>
                <FormControl fullWidth variant="outlined">
                  <InputLabel id="platform-label">
                    {t('scripts.platform')}
                  </InputLabel>
                  <Select
                    labelId="platform-label"
                    value={selectedPlatform}
                    label={t('scripts.platform')}
                    onChange={(e) => handlePlatformChange(e.target.value)}
                  >
                    {platforms.map((platform) => (
                      <MenuItem key={platform.value} value={platform.value}>
                        {platform.label}
                      </MenuItem>
                    ))}
                  </Select>
                </FormControl>
              </Grid>
            </Grid>
          </Box>

          <Typography variant="subtitle1" gutterBottom sx={{ mt: 2 }}>
            {t('scripts.scriptContent')}
          </Typography>
          <Box sx={{ border: 1, borderColor: 'grey.300', borderRadius: 1 }}>
            <Editor
              height="400px"
              language={getLanguageForShell(selectedShell)}
              value={scriptContent}
              onChange={handleScriptContentChange}
              theme="vs-dark"
              options={{
                minimap: { enabled: false },
                scrollBeyondLastLine: false,
                fontSize: 14,
                lineNumbers: 'on',
                roundedSelection: false,
                automaticLayout: true
              }}
            />
          </Box>
        </DialogContent>
        <DialogActions>
          <Button onClick={handleCloseAddScriptDialog}>
            {t('scripts.cancel')}
          </Button>
          <Button
            variant="contained"
            startIcon={<IoSave />}
            onClick={isEditMode ? handleSaveScript : handleSaveNewScript}
            disabled={loading}
          >
            {isEditMode ? t('scripts.update') : t('scripts.save')}
          </Button>
        </DialogActions>
      </Dialog>

      {/* Delete Confirmation Dialog */}
      <Dialog
        open={showDeleteDialog}
        onClose={handleCancelDelete}
        maxWidth="xs"
        fullWidth
      >
        <DialogTitle>
          {t('scripts.confirmDelete', 'Confirm Delete')}
        </DialogTitle>
        <DialogContent>
          <Typography>
            {t('scripts.confirmDeleteMessage', 'Are you sure you want to delete this script? This action cannot be undone.')}
          </Typography>
        </DialogContent>
        <DialogActions>
          <Button onClick={handleCancelDelete}>
            {t('common.cancel', 'Cancel')}
          </Button>
          <Button onClick={handleConfirmDelete} color="error" variant="contained">
            {t('scripts.delete', 'Delete')}
          </Button>
        </DialogActions>
      </Dialog>

      <Snackbar
        open={notification.open}
        autoHideDuration={6000}
        onClose={handleCloseNotification}
      >
        <Alert 
          onClose={handleCloseNotification} 
          severity={notification.severity}
          sx={{ width: '100%' }}
        >
          {notification.message}
        </Alert>
      </Snackbar>
    </Box>
  );
};

export default Scripts;