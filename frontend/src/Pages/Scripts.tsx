// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

import React, { useState, useEffect, useCallback, useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { formatUTCTimestamp } from '../utils/dateUtils';
import {
  IoCode,
  IoPlay,
  IoDocumentText,
  IoTime
} from 'react-icons/io5';
import {
  Box,
  Typography,
  Button,
  Tab,
  Tabs,
  Alert,
  Snackbar,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions
} from '@mui/material';
import { GridColDef, GridRowSelectionModel } from '@mui/x-data-grid';
import {
  scriptsService,
  Script,
  Host,
  ScriptExecution,
  ExecuteScriptRequest
} from '../Services/scripts';
import { useTablePageSize } from '../hooks/useTablePageSize';
import { useColumnVisibility } from '../hooks/useColumnVisibility';
import { hasPermission, SecurityRoles } from '../Services/permissions';
import TabPanel from '../Components/scripts/TabPanel';
import ScriptLibraryTab from '../Components/scripts/ScriptLibraryTab';
import ExecuteScriptTab from '../Components/scripts/ExecuteScriptTab';
import ExecutionHistoryTab from '../Components/scripts/ExecutionHistoryTab';
import ScriptViewDialog from '../Components/scripts/ScriptViewDialog';
import ExecutionViewDialog from '../Components/scripts/ExecutionViewDialog';
import AddEditScriptDialog from '../Components/scripts/AddEditScriptDialog';
import {
  buildAllShells,
  buildPlatforms,
  getShellsForPlatform,
  getShellHeader,
  getStatusColor,
  isHostConnected,
  isHostCompatibleWithScript,
} from '../Components/scripts/scriptsHelpers';
import { buildScriptColumns, buildExecutionColumns } from '../Components/scripts/scriptsColumns';
import './css/Scripts.css';

const Scripts: React.FC = () => {
  const { t } = useTranslation();
  const [tabValue, setTabValue] = useState(0);
  const [scripts, setScripts] = useState<Script[]>([]);
  const [filteredScripts, setFilteredScripts] = useState<Script[]>([]);
  const [hosts, setHosts] = useState<Host[]>([]);
  const [executions, setExecutions] = useState<ScriptExecution[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [executionsLoading, setExecutionsLoading] = useState(false);

  // Script editor state
  const [scriptName, setScriptName] = useState('');
  const [scriptDescription, setScriptDescription] = useState('');
  const [scriptContent, setScriptContent] = useState('');
  const [selectedShell, setSelectedShell] = useState('bash');
  const [selectedPlatform, setSelectedPlatform] = useState('linux');
  const [hasUserEditedContent, setHasUserEditedContent] = useState(false);
  const [selectedHost, setSelectedHost] = useState<string>('');
  const [savedScriptId, setSavedScriptId] = useState<string>('');
  const [isEditMode, setIsEditMode] = useState(false);
  const [editingScriptId, setEditingScriptId] = useState<string | null>(null);

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
  const [scriptToDelete, setScriptToDelete] = useState<string | null>(null);

  // Table pagination
  const { pageSize, pageSizeOptions } = useTablePageSize();

  // Controlled pagination state for v7
  const [paginationModel, setPaginationModel] = useState({ page: 0, pageSize: 10 });

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

  // Column visibility preferences
  const {
    hiddenColumns,
    setHiddenColumns,
    resetPreferences,
    getColumnVisibilityModel,
  } = useColumnVisibility('scripts-grid');

  // UI state
  const [notification, setNotification] = useState<{
    open: boolean;
    message: string;
    severity: 'success' | 'error' | 'info' | 'warning';
  }>({ open: false, message: '', severity: 'info' });

  // Permission states
  const [canAddScript, setCanAddScript] = useState<boolean>(false);
  const [canEditScript, setCanEditScript] = useState<boolean>(false);
  const [canDeleteScript, setCanDeleteScript] = useState<boolean>(false);
  const [canRunScript, setCanRunScript] = useState<boolean>(false);
  const [canDeleteScriptExecution, setCanDeleteScriptExecution] = useState<boolean>(false);

  const allShells = useMemo(() => buildAllShells(t), [t]);

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

  const shells = getShellsForPlatform(allShells, selectedPlatform);

  const platforms = useMemo(() => buildPlatforms(t), [t]);

  // Get compatible hosts for the selected script
  const getCompatibleHosts = () => {
    if (!savedScriptId) return [];

    const selectedScript = scripts.find(s => s.id === savedScriptId);
    if (!selectedScript) return [];

    return hosts.filter(host => isHostCompatibleWithScript(host, selectedScript));
  };

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
      setLoading(true);
      const data = await scriptsService.getSavedScripts();
      setScripts(data);
    } catch {
      showNotification(t('scripts.loadError'), 'error');
    } finally {
      setLoading(false);
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
    if (searchTerm.trim()) {
      performSearch();
    } else {
      setFilteredScripts(scripts);
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

  // Check permissions
  useEffect(() => {
    const checkPermissions = async () => {
      const [addScript, editScript, deleteScript, runScript, deleteExecution] = await Promise.all([
        hasPermission(SecurityRoles.ADD_SCRIPT),
        hasPermission(SecurityRoles.EDIT_SCRIPT),
        hasPermission(SecurityRoles.DELETE_SCRIPT),
        hasPermission(SecurityRoles.RUN_SCRIPT),
        hasPermission(SecurityRoles.DELETE_SCRIPT_EXECUTION)
      ]);
      setCanAddScript(addScript);
      setCanEditScript(editScript);
      setCanDeleteScript(deleteScript);
      setCanRunScript(runScript);
      setCanDeleteScriptExecution(deleteExecution);
    };
    checkPermissions();
  }, []);

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

    const interval = globalThis.setInterval(() => {
      loadExecutions();
    }, 30000);

    return () => globalThis.clearInterval(interval);
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

      const timeoutId = globalThis.setTimeout(() => {
        if (isExecuting && currentExecutionId) {
          fetchExecutionResult();
          scheduleNextPoll();
        }
      }, interval);

      return timeoutId;
    };

    const timeoutId = scheduleNextPoll();

    return () => globalThis.clearTimeout(timeoutId);
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

    // When entering the Execute Script tab, ensure clean state if nothing is selected
    if (newValue === 1 && (!savedScriptId || !selectedHost)) {
      setExecutionResult(null);
      setCurrentExecutionId(null);
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
        platform: selectedPlatform,
        is_active: true
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


  const handleDeleteScript = (scriptId: string) => {
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
      if (!globalThis.confirm(confirmMessage)) {
        return;
      }
    }

    const executeRequest: ExecuteScriptRequest = {
      host_id: selectedHost
    };

    if (savedScriptId) {
      executeRequest.saved_script_id = savedScriptId;
    } else {
      if (!scriptContent.trim()) {
        showNotification(t('scripts.scriptContentRequired'), 'error');
        return;
      }
      executeRequest.script_name = scriptName || t('scripts.adHocScript', 'Ad-hoc Script');
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

  const handleSavedScriptSelect = (scriptId: string) => {
    const script = scripts.find(s => s.id === scriptId);
    if (script) {
      setScriptContent(script.content);
      setSelectedShell(script.shell_type);
      setScriptName(script.name);
      setHasUserEditedContent(true); // Content is loaded from existing script
    }
  };

  // Execute-tab script dropdown change: mirror the original inline
  // onChange — set the id, clear host + execution result, then load
  // the script's details.
  const handleExecuteScriptSelect = (scriptId: string) => {
    setSavedScriptId(scriptId);
    setSelectedHost('');
    setExecutionResult(null);
    setCurrentExecutionId(null);
    if (scriptId) {
      handleSavedScriptSelect(scriptId);
    }
  };

  const handleExecuteHostSelect = (hostId: string) => {
    setSelectedHost(hostId);
    setExecutionResult(null);
    setCurrentExecutionId(null);
  };

  // Initialize script content with correct shebang on component mount
  useEffect(() => {
    if (!scriptContent) {
      setScriptContent(getShellHeader('bash', 'linux'));
    }
  }, [scriptContent]);

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
    const availableShells = getShellsForPlatform(allShells, newPlatform);
    const currentShellAvailable = availableShells.some(shell => shell.value === selectedShell);

    if (!currentShellAvailable && availableShells.length > 0) {
      // Switch to the first available shell for this platform
      const defaultShell = availableShells[0].value;
      setSelectedShell(defaultShell);

      // Update script content if user hasn't edited it
      if (!hasUserEditedContent) {
        setScriptContent(getShellHeader(defaultShell, newPlatform));
      }
    } else if (!hasUserEditedContent) {
      // Current shell is still available, but platform changed so update shebang path
      setScriptContent(getShellHeader(selectedShell, newPlatform));
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
    return formatUTCTimestamp(timestamp, t('common.notAvailable'));
  };

  // DataGrid columns definition
  const columns: GridColDef[] = buildScriptColumns({
    t,
    allShells,
    platforms,
    canEditScript,
    formatTimestamp,
    onEdit: (script) => handleEditFromLibrary(script),
    onView: (script) => handleViewScript(script),
  });

  // Execution History DataGrid columns
  const executionColumns: GridColDef[] = buildExecutionColumns({
    t,
    getStatusColor,
    formatTimestamp,
    onView: (execution) => handleViewExecution(execution),
  });

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

    if (!globalThis.confirm(confirmMessage)) {
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
          : t('scripts.deleteMultipleSuccess'),
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
      // Map DataGrid selection IDs (database IDs) to execution IDs
      for (const databaseId of selectedExecutions) {
        const execution = executions.find(exec => exec.id === databaseId);
        if (execution) {
          await scriptsService.deleteScriptExecution(execution.id);
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
        platform: selectedPlatform,
        is_active: true
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
        <ScriptLibraryTab
          filteredScripts={filteredScripts}
          columns={columns}
          loading={loading}
          searchTerm={searchTerm}
          setSearchTerm={setSearchTerm}
          searchColumn={searchColumn}
          setSearchColumn={setSearchColumn}
          searchColumns={searchColumns}
          hiddenColumns={hiddenColumns}
          setHiddenColumns={setHiddenColumns}
          resetPreferences={resetPreferences}
          columnVisibilityModel={{ ...getColumnVisibilityModel() }}
          paginationModel={paginationModel}
          setPaginationModel={setPaginationModel}
          pageSizeOptions={safePageSizeOptions}
          selectedScripts={selectedScripts}
          setSelectedScripts={setSelectedScripts}
          canAddScript={canAddScript}
          canDeleteScript={canDeleteScript}
          onAddScript={handleAddNewScript}
          onDeleteSelected={handleDeleteSelected}
        />
      </TabPanel>

      {/* Execute Script Tab */}
      <TabPanel value={tabValue} index={1}>
        <ExecuteScriptTab
          scripts={scripts}
          compatibleHosts={getCompatibleHosts()}
          allShells={allShells}
          savedScriptId={savedScriptId}
          selectedHost={selectedHost}
          selectedShell={selectedShell}
          scriptName={scriptName}
          loading={loading}
          isExecuting={isExecuting}
          canRunScript={canRunScript}
          executionResult={executionResult}
          getStatusColor={getStatusColor}
          formatTimestamp={formatTimestamp}
          onReset={handleReset}
          onScriptSelect={handleExecuteScriptSelect}
          onHostSelect={handleExecuteHostSelect}
          onExecute={handleExecuteScript}
        />
      </TabPanel>

      {/* Script Executions Tab */}
      <TabPanel value={tabValue} index={2}>
        <ExecutionHistoryTab
          executions={executions}
          executionColumns={executionColumns}
          executionsLoading={executionsLoading}
          paginationModel={paginationModel}
          setPaginationModel={setPaginationModel}
          pageSizeOptions={safePageSizeOptions}
          selectedExecutions={selectedExecutions}
          setSelectedExecutions={setSelectedExecutions}
          canDeleteScriptExecution={canDeleteScriptExecution}
          onDeleteSelected={handleDeleteSelectedExecutions}
        />
      </TabPanel>

      {/* Script Viewing Dialog */}
      <ScriptViewDialog
        viewingScript={viewingScript}
        allShells={allShells}
        platforms={platforms}
        canDeleteScript={canDeleteScript}
        canEditScript={canEditScript}
        formatTimestamp={formatTimestamp}
        onClose={handleCloseScriptView}
        onDelete={handleDeleteScript}
        onEdit={handleEditFromLibrary}
      />

      {/* Execution Viewing Dialog */}
      <ExecutionViewDialog
        open={showExecutionDialog}
        viewingExecution={viewingExecution}
        getStatusColor={getStatusColor}
        formatTimestamp={formatTimestamp}
        onClose={handleCloseExecutionView}
      />

      {/* Add Script Dialog */}
      <AddEditScriptDialog
        open={showAddScriptDialog}
        isEditMode={isEditMode}
        loading={loading}
        scriptName={scriptName}
        scriptDescription={scriptDescription}
        scriptContent={scriptContent}
        selectedShell={selectedShell}
        selectedPlatform={selectedPlatform}
        shells={shells}
        platforms={platforms}
        onScriptNameChange={setScriptName}
        onScriptDescriptionChange={setScriptDescription}
        onScriptContentChange={handleScriptContentChange}
        onShellChange={handleShellChange}
        onPlatformChange={handlePlatformChange}
        onClose={handleCloseAddScriptDialog}
        onSave={isEditMode ? handleSaveScript : handleSaveNewScript}
      />

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
