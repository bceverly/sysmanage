// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

import React from 'react';
import { useTranslation } from 'react-i18next';
import { IoAdd, IoTrash } from 'react-icons/io5';
import { Box, Button, Stack, Typography } from '@mui/material';
import {
  DataGrid,
  GridColDef,
  GridColumnVisibilityModel,
  GridRowSelectionModel,
} from '@mui/x-data-grid';
import { Script } from '../../Services/scripts';
import SearchBox from '../SearchBox';
import ColumnVisibilityButton from '../ColumnVisibilityButton';
import { buildDataGridLocaleText } from './scriptsHelpers';

interface ScriptLibraryTabProps {
  filteredScripts: Script[];
  columns: GridColDef[];
  loading: boolean;
  searchTerm: string;
  setSearchTerm: (value: string) => void;
  searchColumn: string;
  setSearchColumn: (value: string) => void;
  searchColumns: Array<{ field: string; label: string }>;
  hiddenColumns: string[];
  setHiddenColumns: (cols: string[]) => void;
  resetPreferences: () => void;
  columnVisibilityModel: GridColumnVisibilityModel;
  paginationModel: { page: number; pageSize: number };
  setPaginationModel: (model: { page: number; pageSize: number }) => void;
  pageSizeOptions: number[];
  selectedScripts: GridRowSelectionModel;
  setSelectedScripts: (model: GridRowSelectionModel) => void;
  canAddScript: boolean;
  canDeleteScript: boolean;
  onAddScript: () => void;
  onDeleteSelected: () => void;
}

const ScriptLibraryTab: React.FC<ScriptLibraryTabProps> = ({
  filteredScripts,
  columns,
  loading,
  searchTerm,
  setSearchTerm,
  searchColumn,
  setSearchColumn,
  searchColumns,
  hiddenColumns,
  setHiddenColumns,
  resetPreferences,
  columnVisibilityModel,
  paginationModel,
  setPaginationModel,
  pageSizeOptions,
  selectedScripts,
  setSelectedScripts,
  canAddScript,
  canDeleteScript,
  onAddScript,
  onDeleteSelected,
}) => {
  const { t } = useTranslation();

  return (
    <Box sx={{
      display: 'flex',
      flexDirection: 'column',
      height: 'calc(100vh - 250px)',
      gap: 2,
      p: 2
    }}>
      <Box sx={{ mb: 2, display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexShrink: 0 }}>
        <Typography variant="h6">
          {t('scripts.scriptLibrary')}
        </Typography>
      </Box>

      {/* Search Box */}
      <Box sx={{ flexShrink: 0 }}>
        <SearchBox
          searchTerm={searchTerm}
          setSearchTerm={setSearchTerm}
          searchColumn={searchColumn}
          setSearchColumn={setSearchColumn}
          columns={searchColumns}
          placeholder={t('search.searchScripts', 'Search scripts')}
        />
      </Box>

      {/* Column Visibility Button */}
      <Box sx={{ mb: 1, mr: 2, display: 'flex', alignItems: 'center', justifyContent: 'flex-end', flexShrink: 0 }}>
        <ColumnVisibilityButton
          columns={columns
            .filter(col => col.field !== 'actions')
            .map(col => ({ field: col.field, headerName: col.headerName || col.field }))}
          hiddenColumns={hiddenColumns}
          onColumnsChange={setHiddenColumns}
          onReset={resetPreferences}
        />
      </Box>

      <Box sx={{ flexGrow: 1, minHeight: 0 }}>
        <DataGrid
          rows={filteredScripts}
          columns={columns}
          loading={loading}
          paginationModel={paginationModel}
          onPaginationModelChange={setPaginationModel}
          columnVisibilityModel={columnVisibilityModel}
          pageSizeOptions={pageSizeOptions}
          checkboxSelection
          rowSelectionModel={selectedScripts}
          onRowSelectionModelChange={setSelectedScripts}
          disableRowSelectionOnClick
          localeText={buildDataGridLocaleText(t, t('scripts.noScripts'))}
        />
      </Box>

      <Stack direction="row" spacing={2} sx={{ flexShrink: 0 }}>
        {canAddScript && (
          <Button
            variant="outlined"
            startIcon={<IoAdd />}
            onClick={onAddScript}
            disabled={selectedScripts.length > 0}
          >
            {t('scripts.addScript')}
          </Button>
        )}
        {canDeleteScript && (
          <Button
            variant="outlined"
            color="error"
            startIcon={<IoTrash />}
            onClick={onDeleteSelected}
            disabled={selectedScripts.length === 0}
          >
            {t('scripts.deleteSelected')}
          </Button>
        )}
      </Stack>
    </Box>
  );
};

export default ScriptLibraryTab;
