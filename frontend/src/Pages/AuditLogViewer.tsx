import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import {
  Box,
  Button,
  TextField,
  Select,
  MenuItem,
  FormControl,
  InputLabel,
  Paper,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  TablePagination,
  CircularProgress,
  Typography,
  Chip,
  InputAdornment,
  Grid,
} from '@mui/material';
import {
  ArrowBack as BackIcon,
  Search as SearchIcon,
  GetApp as DownloadIcon,
  Refresh as RefreshIcon,
} from '@mui/icons-material';
import api from '../Services/api';

interface AuditLogEntry {
  id: string;
  timestamp: string;
  username: string;
  action_type: string;
  entity_type: string;
  entity_id: string | null;
  entity_name: string | null;
  description: string | null;
  category: string | null;
  entry_type: string | null;
  ip_address: string | null;
  user_agent: string | null;
  result: string;
  error_message: string | null;
}

const AuditLogViewer: React.FC = () => {
  const { t } = useTranslation();
  const navigate = useNavigate();

  // Filter states
  const [search, setSearch] = useState('');
  const [userId, setUserId] = useState('');
  const [actionType, setActionType] = useState('');
  const [entityType, setEntityType] = useState('');
  const [category, setCategory] = useState('');
  const [entryType, setEntryType] = useState('');
  const [startDate, setStartDate] = useState('');
  const [endDate, setEndDate] = useState('');

  // Table states
  const [page, setPage] = useState(0);
  const [rowsPerPage, setRowsPerPage] = useState(25);
  const [entries, setEntries] = useState<AuditLogEntry[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);

  const fetchAuditLogs = useCallback(async () => {
    try {
      setLoading(true);
      const params: Record<string, string | number> = {
        limit: rowsPerPage,
        offset: page * rowsPerPage,
      };

      if (search) params.search = search;
      if (userId) params.user_id = userId;
      if (actionType) params.action_type = actionType;
      if (entityType) params.entity_type = entityType;
      if (category) params.category = category;
      if (entryType) params.entry_type = entryType;
      if (startDate) params.start_date = new Date(startDate).toISOString();
      if (endDate) params.end_date = new Date(endDate).toISOString();

      const response = await api.get('/api/audit-log/list', { params });
      setEntries(response.data.entries);
      setTotal(response.data.total);
    } catch (error) {
      console.error('Error fetching audit logs:', error);
    } finally {
      setLoading(false);
    }
  }, [search, userId, actionType, entityType, category, entryType, startDate, endDate, page, rowsPerPage]);

  useEffect(() => {
    fetchAuditLogs();
  }, [fetchAuditLogs]);

  const handleChangePage = (_event: unknown, newPage: number) => {
    setPage(newPage);
  };

  const handleChangeRowsPerPage = (event: React.ChangeEvent<HTMLInputElement>) => {
    setRowsPerPage(Number.parseInt(event.target.value, 10));
    setPage(0);
  };

  const handleReset = () => {
    setSearch('');
    setUserId('');
    setActionType('');
    setEntityType('');
    setCategory('');
    setEntryType('');
    setStartDate('');
    setEndDate('');
    setPage(0);
  };

  const handleExportCSV = async () => {
    try {
      const params: Record<string, string> = {};
      if (search) params.search = search;
      if (userId) params.user_id = userId;
      if (actionType) params.action_type = actionType;
      if (entityType) params.entity_type = entityType;
      if (category) params.category = category;
      if (entryType) params.entry_type = entryType;
      if (startDate) params.start_date = new Date(startDate).toISOString();
      if (endDate) params.end_date = new Date(endDate).toISOString();

      const response = await api.get('/api/audit-log/export', {
        params,
        responseType: 'blob',
      });

      const blob = new Blob([response.data], { type: 'text/csv' });
      const url = globalThis.URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = `audit_log_${new Date().toISOString().slice(0, 10)}.csv`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      globalThis.URL.revokeObjectURL(url);
    } catch (error) {
      console.error('Error exporting audit log:', error);
    }
  };

  const handleGoBack = () => {
    navigate('/reports#security');
  };

  const getResultColor = (result: string) => {
    switch (result.toUpperCase()) {
      case 'SUCCESS':
        return 'success';
      case 'FAILURE':
        return 'error';
      case 'PARTIAL':
        return 'warning';
      default:
        return 'default';
    }
  };

  return (
      <Box sx={{ p: 3 }}>
        {/* Header */}
        <Box sx={{ mb: 3, display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
            <Button
              variant="outlined"
              startIcon={<BackIcon />}
              onClick={handleGoBack}
            >
              {t('common.back', 'Back')}
            </Button>
            <Typography variant="h5" component="h1">
              {t('reports.auditLog', 'Audit Log')}
            </Typography>
          </Box>
          <Box sx={{ display: 'flex', gap: 1 }}>
            <Button
              variant="outlined"
              startIcon={<RefreshIcon />}
              onClick={fetchAuditLogs}
            >
              {t('common.refresh', 'Refresh')}
            </Button>
            <Button
              variant="contained"
              startIcon={<DownloadIcon />}
              onClick={handleExportCSV}
            >
              {t('common.exportCSV', 'Export CSV')}
            </Button>
          </Box>
        </Box>

        {/* Filters */}
        <Paper sx={{ p: 2, mb: 3 }}>
          <Typography variant="h6" gutterBottom>
            {t('auditLog.filters', 'Filters')}
          </Typography>
          <Grid container spacing={2}>
            <Grid size={{ xs: 12, md: 6 }}>
              <TextField
                fullWidth
                label={t('auditLog.search', 'Search (description or entity name)')}
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                size="small"
                slotProps={{
                  input: {
                    startAdornment: (
                      <InputAdornment position="start">
                        <SearchIcon />
                      </InputAdornment>
                    ),
                  },
                }}
              />
            </Grid>
            <Grid size={{ xs: 12, md: 3 }}>
              <FormControl fullWidth size="small">
                <InputLabel>{t('auditLog.actionType', 'Action Type')}</InputLabel>
                <Select
                  value={actionType}
                  label={t('auditLog.actionType', 'Action Type')}
                  onChange={(e) => setActionType(e.target.value)}
                >
                  <MenuItem value="">{t('common.all', 'All')}</MenuItem>
                  <MenuItem value="CREATE">Create</MenuItem>
                  <MenuItem value="READ">Read</MenuItem>
                  <MenuItem value="UPDATE">Update</MenuItem>
                  <MenuItem value="DELETE">Delete</MenuItem>
                  <MenuItem value="EXECUTE">Execute</MenuItem>
                </Select>
              </FormControl>
            </Grid>
            <Grid size={{ xs: 12, md: 3 }}>
              <FormControl fullWidth size="small">
                <InputLabel>{t('auditLog.entityType', 'Entity Type')}</InputLabel>
                <Select
                  value={entityType}
                  label={t('auditLog.entityType', 'Entity Type')}
                  onChange={(e) => setEntityType(e.target.value)}
                >
                  <MenuItem value="">{t('common.all', 'All')}</MenuItem>
                  <MenuItem value="HOST">Host</MenuItem>
                  <MenuItem value="USER">User</MenuItem>
                  <MenuItem value="PACKAGE">Package</MenuItem>
                  <MenuItem value="SCRIPT">Script</MenuItem>
                  <MenuItem value="SECRET">Secret</MenuItem>
                  <MenuItem value="CERTIFICATE">Certificate</MenuItem>
                  <MenuItem value="TAG">Tag</MenuItem>
                  <MenuItem value="USER_ROLE">User Role</MenuItem>
                </Select>
              </FormControl>
            </Grid>
            <Grid size={{ xs: 12, md: 3 }}>
              <FormControl fullWidth size="small">
                <InputLabel>{t('auditLog.category', 'Category')}</InputLabel>
                <Select
                  value={category}
                  label={t('auditLog.category', 'Category')}
                  onChange={(e) => setCategory(e.target.value)}
                >
                  <MenuItem value="">{t('common.all', 'All')}</MenuItem>
                  <MenuItem value="database">Database</MenuItem>
                  <MenuItem value="agent">Agent</MenuItem>
                  <MenuItem value="authentication">Authentication</MenuItem>
                  <MenuItem value="system">System</MenuItem>
                </Select>
              </FormControl>
            </Grid>
            <Grid size={{ xs: 12, md: 3 }}>
              <FormControl fullWidth size="small">
                <InputLabel>{t('auditLog.entryType', 'Entry Type')}</InputLabel>
                <Select
                  value={entryType}
                  label={t('auditLog.entryType', 'Entry Type')}
                  onChange={(e) => setEntryType(e.target.value)}
                >
                  <MenuItem value="">{t('common.all', 'All')}</MenuItem>
                  <MenuItem value="user_action">User Action</MenuItem>
                  <MenuItem value="system_event">System Event</MenuItem>
                  <MenuItem value="security_event">Security Event</MenuItem>
                  <MenuItem value="data_change">Data Change</MenuItem>
                </Select>
              </FormControl>
            </Grid>
            <Grid size={{ xs: 12, md: 3 }}>
              <TextField
                fullWidth
                label={t('auditLog.startDate', 'Start Date')}
                type="datetime-local"
                value={startDate}
                onChange={(e) => setStartDate(e.target.value)}
                size="small"
                slotProps={{
                  inputLabel: { shrink: true },
                }}
              />
            </Grid>
            <Grid size={{ xs: 12, md: 3 }}>
              <TextField
                fullWidth
                label={t('auditLog.endDate', 'End Date')}
                type="datetime-local"
                value={endDate}
                onChange={(e) => setEndDate(e.target.value)}
                size="small"
                slotProps={{
                  inputLabel: { shrink: true },
                }}
              />
            </Grid>
            <Grid size={{ xs: 12 }}>
              <Box sx={{ display: 'flex', gap: 1, justifyContent: 'flex-end' }}>
                <Button variant="outlined" onClick={handleReset}>
                  {t('common.reset', 'Reset Filters')}
                </Button>
                <Button variant="contained" onClick={fetchAuditLogs}>
                  {t('common.apply', 'Apply Filters')}
                </Button>
              </Box>
            </Grid>
          </Grid>
        </Paper>

        {/* Results */}
        <Paper>
          {loading ? (
            <Box sx={{ display: 'flex', justifyContent: 'center', p: 4 }}>
              <CircularProgress />
            </Box>
          ) : (
            <>
              <TableContainer>
                <Table>
                  <TableHead>
                    <TableRow>
                      <TableCell>{t('auditLog.timestamp', 'Timestamp')}</TableCell>
                      <TableCell>{t('auditLog.username', 'Username')}</TableCell>
                      <TableCell>{t('auditLog.action', 'Action')}</TableCell>
                      <TableCell>{t('auditLog.entity', 'Entity')}</TableCell>
                      <TableCell>{t('auditLog.description', 'Description')}</TableCell>
                      <TableCell>{t('auditLog.result', 'Result')}</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {entries.map((entry) => (
                      <TableRow key={entry.id} hover>
                        <TableCell>
                          {new Date(entry.timestamp).toLocaleString()}
                        </TableCell>
                        <TableCell>{entry.username}</TableCell>
                        <TableCell>
                          <Chip label={entry.action_type} size="small" variant="outlined" />
                        </TableCell>
                        <TableCell>
                          <Box>
                            <Typography variant="body2">
                              {entry.entity_type}
                            </Typography>
                            {entry.entity_name && (
                              <Typography variant="caption" color="text.secondary">
                                {entry.entity_name}
                              </Typography>
                            )}
                          </Box>
                        </TableCell>
                        <TableCell>
                          <Typography variant="body2" sx={{ maxWidth: 400 }}>
                            {entry.description}
                          </Typography>
                        </TableCell>
                        <TableCell>
                          <Chip
                            label={entry.result}
                            size="small"
                            color={getResultColor(entry.result)}
                          />
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </TableContainer>
              <TablePagination
                rowsPerPageOptions={[10, 25, 50, 100]}
                component="div"
                count={total}
                rowsPerPage={rowsPerPage}
                page={page}
                onPageChange={handleChangePage}
                onRowsPerPageChange={handleChangeRowsPerPage}
              />
            </>
          )}
        </Paper>
      </Box>
  );
};

export default AuditLogViewer;
