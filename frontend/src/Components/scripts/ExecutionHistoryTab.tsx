// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

import React from 'react';
import { useTranslation } from 'react-i18next';
import { IoTrash } from 'react-icons/io5';
import { Box, Button } from '@mui/material';
import {
  DataGrid,
  GridColDef,
  GridRowSelectionModel,
} from '@mui/x-data-grid';
import { ScriptExecution } from '../../Services/scripts';
import { buildDataGridLocaleText } from './scriptsHelpers';

interface ExecutionHistoryTabProps {
  executions: ScriptExecution[];
  executionColumns: GridColDef[];
  executionsLoading: boolean;
  paginationModel: { page: number; pageSize: number };
  setPaginationModel: (model: { page: number; pageSize: number }) => void;
  pageSizeOptions: number[];
  selectedExecutions: GridRowSelectionModel;
  setSelectedExecutions: (model: GridRowSelectionModel) => void;
  canDeleteScriptExecution: boolean;
  onDeleteSelected: () => void;
}

const ExecutionHistoryTab: React.FC<ExecutionHistoryTabProps> = ({
  executions,
  executionColumns,
  executionsLoading,
  paginationModel,
  setPaginationModel,
  pageSizeOptions,
  selectedExecutions,
  setSelectedExecutions,
  canDeleteScriptExecution,
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
      <Box sx={{ flexGrow: 1, minHeight: 0 }}>
        <DataGrid
          rows={executions}
          columns={executionColumns}
          loading={executionsLoading}
          paginationModel={paginationModel}
          onPaginationModelChange={setPaginationModel}
          pageSizeOptions={pageSizeOptions}
          initialState={{
            sorting: { sortModel: [{ field: 'started_at', sort: 'desc' }] },
          }}
          checkboxSelection={true}
          rowSelectionModel={selectedExecutions}
          onRowSelectionModelChange={setSelectedExecutions}
          disableRowSelectionOnClick
          localeText={buildDataGridLocaleText(t, t('scripts.noExecutions'))}
        />
      </Box>

      {canDeleteScriptExecution && (
        <Box sx={{ flexShrink: 0 }}>
          <Button
            variant="outlined"
            color="error"
            startIcon={<IoTrash />}
            onClick={onDeleteSelected}
            disabled={selectedExecutions.length === 0}
          >
            {t('scripts.deleteSelectedExecutions')}
          </Button>
        </Box>
      )}
    </Box>
  );
};

export default ExecutionHistoryTab;
