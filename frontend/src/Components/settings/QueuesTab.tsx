// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

/**
 * The Settings > Queues tab: expired/failed messages from the store-and-forward
 * queue.
 *
 * Self-contained by design.  Every piece of queue state -- the rows, the
 * selection, the column preferences, the pagination and the details dialog --
 * lives here rather than in Settings.tsx, because nothing outside this tab
 * reads any of it.  Settings.tsx renders it only while the tab is active, so
 * the fetch happens on mount and no parent has to remember to trigger it.
 */

import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { DataGrid, GridColDef, GridRowSelectionModel } from '@mui/x-data-grid';
import {
  Box,
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  IconButton,
  Stack,
  Typography,
} from '@mui/material';
import {
  Delete as DeleteIcon,
  Visibility as VisibilityIcon,
} from '@mui/icons-material';

import ColumnVisibilityButton from '../ColumnVisibilityButton';
import axiosInstance from '../../Services/api';
import { useColumnVisibility } from '../../hooks/useColumnVisibility';
import { useTablePageSize } from '../../hooks/useTablePageSize';
import { formatUTCTimestamp } from '../../utils/dateUtils';
import { hasPermission, SecurityRoles } from '../../Services/permissions';
import { QueueMessage } from './settingsTypes';

const QueuesTab: React.FC = () => {
  const { t } = useTranslation();

  const [queueMessages, setQueueMessages] = useState<QueueMessage[]>([]);
  const [selectedMessages, setSelectedMessages] = useState<GridRowSelectionModel>([]);
  const [queueLoading, setQueueLoading] = useState<boolean>(true);
  const [messageDetailOpen, setMessageDetailOpen] = useState(false);
  const [selectedMessage, setSelectedMessage] = useState<QueueMessage | null>(null);
  const [canDeleteQueueMessage, setCanDeleteQueueMessage] = useState<boolean>(false);

  const { pageSize, pageSizeOptions } = useTablePageSize({ reservedHeight: 350 });
  const [paginationModel, setPaginationModel] = useState({ page: 0, pageSize: 10 });

  useEffect(() => {
    setPaginationModel(prev => ({ ...prev, pageSize }));
  }, [pageSize]);

  // Ensure the current page size is always in options to avoid a MUI warning.
  const safePageSizeOptions = useMemo(() => {
    if (!pageSizeOptions.includes(paginationModel.pageSize)) {
      return [...pageSizeOptions, paginationModel.pageSize].sort((a, b) => a - b);
    }
    return pageSizeOptions;
  }, [pageSizeOptions, paginationModel.pageSize]);

  const {
    hiddenColumns: hiddenQueueColumns,
    setHiddenColumns: setHiddenQueueColumns,
    resetPreferences: resetQueuePreferences,
    getColumnVisibilityModel: getQueueColumnVisibilityModel,
  } = useColumnVisibility('settings-queue-grid');

  useEffect(() => {
    const checkPermission = async () => {
      setCanDeleteQueueMessage(await hasPermission(SecurityRoles.DELETE_QUEUE_MESSAGE));
    };
    // Fail CLOSED and say so.  Unguarded, an expired session or a network
    // blip rejected here into an UNHANDLED promise: the permission flags
    // stayed false, the buttons stayed disabled, and nothing on screen
    // explained why.  Nine call sites had this shape; see ROADMAP Phase 19.
    checkPermission().catch((error: unknown) => {
      console.error('Failed to resolve permissions:', error);
    });
  }, []);

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

  useEffect(() => {
    loadQueueMessages();
  }, [loadQueueMessages]);

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

  const handleViewMessage = async (messageId: string) => {
    try {
      const response = await axiosInstance.get(`/api/v1/queue/failed/${messageId}`);
      setSelectedMessage(response.data);
      setMessageDetailOpen(true);
    } catch (error) {
      console.error('Error fetching message details:', error);
    }
  };

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

  return (
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
          paginationModel={paginationModel}
          onPaginationModelChange={setPaginationModel}
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

      {/* Message Details Dialog */}
      <Dialog
        open={messageDetailOpen}
        onClose={() => setMessageDetailOpen(false)}
        maxWidth="lg"
        fullWidth
      >
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
                <strong>{t('queues.hostId', 'Host ID')}:</strong> {selectedMessage.host_id || t('common.notAvailable', 'N/A')}
              </Typography>
              <Typography variant="body2" sx={{ mb: 1 }}>
                <strong>{t('queues.created', 'Created At')}:</strong> {formatUTCTimestamp(selectedMessage.created_at, t('common.notAvailable', 'N/A'))}
              </Typography>
              <Typography variant="body2" sx={{ mb: 2 }}>
                <strong>{t('queues.expired', 'Expired At')}:</strong> {formatUTCTimestamp(selectedMessage.timestamp, t('common.notAvailable', 'N/A'))}
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
          <Button onClick={() => setMessageDetailOpen(false)}>
            {t('common.close', 'Close')}
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
};

export default QueuesTab;
