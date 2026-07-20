// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

import React from 'react';
import { useTranslation } from 'react-i18next';
import { IoCode, IoPlay, IoRefresh } from 'react-icons/io5';
import {
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  FormControl,
  Grid,
  IconButton,
  InputLabel,
  MenuItem,
  Select,
  Typography,
} from '@mui/material';
import { Host, Script, ScriptExecution } from '../../Services/scripts';
import { ChipColor, ShellOption, isHostConnected } from './scriptsHelpers';

interface ExecuteScriptTabProps {
  scripts: Script[];
  compatibleHosts: Host[];
  allShells: ShellOption[];
  savedScriptId: string;
  selectedHost: string;
  selectedShell: string;
  scriptName: string;
  loading: boolean;
  isExecuting: boolean;
  canRunScript: boolean;
  executionResult: ScriptExecution | null;
  getStatusColor: (status: string) => ChipColor;
  formatTimestamp: (timestamp: string | undefined) => string;
  onReset: () => void;
  onScriptSelect: (scriptId: string) => void;
  onHostSelect: (hostId: string) => void;
  onExecute: () => void;
}

const ExecuteScriptTab: React.FC<ExecuteScriptTabProps> = ({
  scripts,
  compatibleHosts,
  allShells,
  savedScriptId,
  selectedHost,
  selectedShell,
  scriptName,
  loading,
  isExecuting,
  canRunScript,
  executionResult,
  getStatusColor,
  formatTimestamp,
  onReset,
  onScriptSelect,
  onHostSelect,
  onExecute,
}) => {
  const { t } = useTranslation();

  return (
    <Grid container spacing={3}>
      {/* Left Card - Execute Script */}
      <Grid size={{ xs: 12, md: 5 }}>
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
                  onClick={onReset}
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
              <Select<string>
                value={savedScriptId}
                label={t('scripts.selectScript')}
                onChange={(e) => onScriptSelect(e.target.value)}
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
              <Select<string>
                value={selectedHost}
                label={t('scripts.selectHost')}
                onChange={(e) => onHostSelect(e.target.value)}
                disabled={isExecuting || !savedScriptId}
              >
                {compatibleHosts.map((host) => (
                  <MenuItem key={host.id} value={host.id}>
                    <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', width: '100%' }}>
                      <Typography>{host.fqdn}</Typography>
                      <Box sx={{ display: 'flex', gap: 1 }}>
                        <Chip
                          label={isHostConnected(host) ? t('scripts.connected', 'Connected') : t('scripts.offline', 'Offline')}
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

            {canRunScript && (
              <Button
                variant="contained"
                color="primary"
                fullWidth
                size="large"
                startIcon={<IoPlay />}
                onClick={onExecute}
                disabled={loading || !savedScriptId || !selectedHost || isExecuting}
                sx={{ mt: 3, py: 1.5 }}
              >
                {isExecuting ? t('scripts.executing') : t('scripts.executeNow')}
              </Button>
            )}
          </CardContent>
        </Card>
      </Grid>

      {/* Right Card - Execution Output */}
      <Grid size={{ xs: 12, md: 7 }}>
        <Card sx={{ height: '100%', minHeight: 500 }}>
          <CardContent>
            <Typography variant="h6" gutterBottom>
              {t('scripts.executionOutput')}
            </Typography>

            {(!executionResult || !savedScriptId || !selectedHost) && !isExecuting && (
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

            {executionResult && savedScriptId && selectedHost && (
              <Box>
                {/* Execution Status */}
                <Box sx={{ mb: 2 }}>
                  <Box sx={{ display: 'flex', gap: 1, mb: 1 }}>
                    <Chip
                      label={t(`scripts.status.${executionResult.status}`)}
                      color={getStatusColor(executionResult.status) }
                      size="small"
                    />
                    {executionResult.exit_code !== undefined && (
                      <Chip
                        label={t('scripts.exitCodeLabel', 'Exit Code: {{code}}', { code: executionResult.exit_code })}
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
                      {/* eslint-disable-next-line i18next/no-literal-string -- stream delimiter */}
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
                      {/* eslint-disable-next-line i18next/no-literal-string -- stream delimiter */}
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
                      {/* eslint-disable-next-line i18next/no-literal-string -- stream delimiter */}
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
  );
};

export default ExecuteScriptTab;
