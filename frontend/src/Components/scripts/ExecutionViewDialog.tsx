// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

import React from 'react';
import { useTranslation } from 'react-i18next';
import {
  Alert,
  Box,
  Button,
  Chip,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Grid,
  Typography,
} from '@mui/material';
import { ScriptExecution } from '../../Services/scripts';
import { ChipColor } from './scriptsHelpers';

interface ExecutionViewDialogProps {
  open: boolean;
  viewingExecution: ScriptExecution | null;
  getStatusColor: (status: string) => ChipColor;
  formatTimestamp: (timestamp: string | undefined) => string;
  onClose: () => void;
}

const ExecutionViewDialog: React.FC<ExecutionViewDialogProps> = ({
  open,
  viewingExecution,
  getStatusColor,
  formatTimestamp,
  onClose,
}) => {
  const { t } = useTranslation();

  return (
    <Dialog
      open={open}
      onClose={onClose}
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
                <Grid size={{ xs: 12, md: 6 }}>
                  <Typography variant="body2" gutterBottom>
                    <strong>{t('scripts.scriptName')}:</strong> {viewingExecution.script_name}
                  </Typography>
                </Grid>
                <Grid size={{ xs: 12, md: 6 }}>
                  <Typography variant="body2" gutterBottom>
                    <strong>{t('scripts.hostFqdn')}:</strong> {viewingExecution.host_fqdn}
                  </Typography>
                </Grid>
                <Grid size={{ xs: 12, md: 6 }}>
                  <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                    <Typography variant="body2">
                      <strong>{t('common.status')}:</strong>
                    </Typography>
                    <Chip
                      label={t(`scripts.status.${viewingExecution.status}`)}
                      color={getStatusColor(viewingExecution.status) }
                      size="small"
                    />
                  </Box>
                </Grid>
                <Grid size={{ xs: 12, md: 6 }}>
                  <Typography variant="body2" gutterBottom>
                    <strong>{t('scripts.executionId')}:</strong> {viewingExecution.id}
                  </Typography>
                </Grid>
                <Grid size={{ xs: 12, md: 6 }}>
                  <Typography variant="body2" gutterBottom>
                    <strong>{t('scripts.startedAt')}:</strong> {formatTimestamp(viewingExecution.started_at)}
                  </Typography>
                </Grid>
                <Grid size={{ xs: 12, md: 6 }}>
                  <Typography variant="body2" gutterBottom>
                    <strong>{t('scripts.completedAt')}:</strong> {viewingExecution.completed_at ? formatTimestamp(viewingExecution.completed_at) : '-'}
                  </Typography>
                </Grid>
                {viewingExecution.exit_code !== undefined && (
                  <Grid size={{ xs: 12, md: 6 }}>
                    <Typography variant="body2" gutterBottom>
                      <strong>{t('scripts.exitCode')}:</strong> {viewingExecution.exit_code}
                    </Typography>
                  </Grid>
                )}
                {viewingExecution.execution_time && (
                  <Grid size={{ xs: 12, md: 6 }}>
                    <Typography variant="body2" gutterBottom>
                      {/* eslint-disable-next-line i18next/no-literal-string -- seconds unit suffix */}
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
            <Button onClick={onClose}>
              {t('common.close')}
            </Button>
          </DialogActions>
        </>
      )}
    </Dialog>
  );
};

export default ExecutionViewDialog;
