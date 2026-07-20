// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

import React from 'react';
import { Chip, IconButton, Typography } from '@mui/material';
import { IoEye, IoPencil } from 'react-icons/io5';
import { GridColDef } from '@mui/x-data-grid';
import { TFunction } from 'i18next';
import { Script, ScriptExecution } from '../../Services/scripts';
import { ChipColor, ShellOption } from './scriptsHelpers';

interface ScriptColumnsDeps {
  t: TFunction;
  allShells: ShellOption[];
  platforms: Array<{ value: string; label: string }>;
  canEditScript: boolean;
  formatTimestamp: (timestamp: string | undefined) => string;
  onEdit: (script: Script) => void;
  onView: (script: Script) => void;
}

// Script Library DataGrid columns.
export const buildScriptColumns = ({
  t,
  allShells,
  platforms,
  canEditScript,
  formatTimestamp,
  onEdit,
  onView,
}: ScriptColumnsDeps): GridColDef[] => [
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
      <>
        {canEditScript && (
          <IconButton
            size="small"
            onClick={() => onEdit(params.row as Script)}
            title={t('scripts.edit')}
            sx={{ color: 'primary.main' }}
          >
            <IoPencil />
          </IconButton>
        )}
        <IconButton
          size="small"
          onClick={() => onView(params.row as Script)}
          title={t('scripts.viewScript')}
          sx={{ color: 'primary.main' }}
        >
          <IoEye />
        </IconButton>
      </>
    ),
  },
];

interface ExecutionColumnsDeps {
  t: TFunction;
  getStatusColor: (status: string) => ChipColor;
  formatTimestamp: (timestamp: string | undefined) => string;
  onView: (execution: ScriptExecution) => void;
}

// Execution History DataGrid columns.
export const buildExecutionColumns = ({
  t,
  getStatusColor,
  formatTimestamp,
  onView,
}: ExecutionColumnsDeps): GridColDef[] => [
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
        color={getStatusColor(params.value)}
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
        {params.value ?? '-'}
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
        onClick={() => onView(params.row)}
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
