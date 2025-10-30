import React, { useState, useMemo, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';
import api from '../Services/api';
import { hasPermission, SecurityRoles } from '../Services/permissions';

import {
  Box,
  Typography,
  Card,
  CardContent,
  CardMedia,
  TextField,
  InputAdornment,
  Select,
  MenuItem,
  FormControl,
  InputLabel,
  Grid,
  Tabs,
  Tab,
  Chip,
  Button,
} from '@mui/material';
import {
  Search as SearchIcon,
  Assessment as ReportIcon,
  GetApp as DownloadIcon,
  Visibility as ViewIcon,
} from '@mui/icons-material';

interface TabPanelProps {
  children?: React.ReactNode;
  index: number;
  value: number;
}

function TabPanel(props: TabPanelProps) {
  const { children, value, index, ...other } = props;

  return (
    <div
      role="tabpanel"
      hidden={value !== index}
      id={`reports-tabpanel-${index}`}
      aria-labelledby={`reports-tab-${index}`}
      {...other}
    >
      {value === index && <Box sx={{ p: 3 }}>{children}</Box>}
    </div>
  );
}

interface ReportCard {
  id: string;
  name: string;
  description: string;
  category: 'hosts' | 'users' | 'security';
  screenshot: string;
  tags: string[];
}

const Reports: React.FC = () => {
  const { t } = useTranslation();
  const navigate = useNavigate();

  // Tab names for URL hash
  const tabNames = useMemo(() => ['hosts', 'users', 'security'], []);

  // Initialize tab from URL hash
  const getInitialTab = () => {
    const hash = window.location.hash.slice(1);
    const tabIndex = tabNames.indexOf(hash);
    return tabIndex >= 0 ? tabIndex : 0;
  };

  const [tabValue, setTabValue] = useState(getInitialTab);

  // Handle tab change and update URL hash
  const handleTabChange = (_event: React.SyntheticEvent, newValue: number) => {
    setTabValue(newValue);
    setSearchTerm(''); // Clear search when switching tabs
    // Safely access array element with bounds check
    if (newValue >= 0 && newValue < tabNames.length) {
      // eslint-disable-next-line security/detect-object-injection
      window.location.hash = tabNames[newValue]; // nosemgrep: detect-object-injection
    }
  };

  // Listen for hash changes (browser back/forward)
  useEffect(() => {
    const handleHashChange = () => {
      const hash = window.location.hash.slice(1);
      const tabIndex = tabNames.indexOf(hash);
      if (tabIndex >= 0) {
        setTabValue(tabIndex);
      }
    };

    window.addEventListener('hashchange', handleHashChange);
    return () => window.removeEventListener('hashchange', handleHashChange);
  }, [tabNames]);
  const [searchTerm, setSearchTerm] = useState('');
  const [searchField, setSearchField] = useState<'name' | 'description'>('name');

  // Permission states
  const [canViewReport, setCanViewReport] = useState<boolean>(false);
  const [canGeneratePdfReport, setCanGeneratePdfReport] = useState<boolean>(false);
  const [canViewAuditLog, setCanViewAuditLog] = useState<boolean>(false);

  // Check permissions
  useEffect(() => {
    const checkPermissions = async () => {
      const [viewReport, generatePdf, viewAuditLog] = await Promise.all([
        hasPermission(SecurityRoles.VIEW_REPORT),
        hasPermission(SecurityRoles.GENERATE_PDF_REPORT),
        hasPermission(SecurityRoles.VIEW_AUDIT_LOG)
      ]);
      setCanViewReport(viewReport);
      setCanGeneratePdfReport(generatePdf);
      setCanViewAuditLog(viewAuditLog);
    };
    checkPermissions();
  }, []);

  const filteredReports = useMemo(() => {
    // Get the backend base URL for screenshots
    const getBackendBaseURL = () => {
      const currentHost = window.location.hostname;
      const backendPort = 8080; // This should match your config file
      return `http://${currentHost}:${backendPort}`;
    };

    const baseURL = getBackendBaseURL();

    // Mock data for reports - in real implementation, this would come from API
    const availableReports: ReportCard[] = [
      {
        id: 'registered-hosts',
        name: 'Registered Hosts',
        description: 'Complete listing of all registered hosts showing basic information and operating system details including hostname, IP addresses, OS version, and status.',
        category: 'hosts',
        screenshot: `${baseURL}/api/reports/screenshots/registered-hosts.png`,
        tags: ['hosts', 'system info', 'basic']
      },
      {
        id: 'hosts-with-tags',
        name: 'Hosts with Tags',
        description: 'Shows all registered hosts along with their assigned tags for easy categorization and filtering. Useful for organizing hosts by environment, purpose, or department.',
        category: 'hosts',
        screenshot: `${baseURL}/api/reports/screenshots/hosts-with-tags.png`,
        tags: ['hosts', 'tags', 'organization']
      },
      {
        id: 'users-list',
        name: 'SysManage Users',
        description: 'Comprehensive list of all SysManage users showing their profiles, roles, permissions, and account status. Includes user creation dates and last login times.',
        category: 'users',
        screenshot: `${baseURL}/api/reports/screenshots/users-list.png`,
        tags: ['users', 'accounts', 'permissions']
      },
      {
        id: 'user-rbac',
        name: 'User Security Roles (RBAC)',
        description: 'Complete view of all users with their assigned security roles organized by role groups. Shows the granular permission structure for role-based access control across the system.',
        category: 'security',
        screenshot: `${baseURL}/api/reports/screenshots/user-rbac.png`,
        tags: ['users', 'security', 'rbac', 'permissions', 'roles']
      },
      {
        id: 'firewall-status',
        name: 'Host Firewall Status',
        description: 'Detailed firewall status for all managed hosts including firewall software, enabled/disabled status, open IPv4 and IPv6 ports, and operating system information.',
        category: 'hosts',
        screenshot: `${baseURL}/api/reports/screenshots/firewall-status.png`,
        tags: ['hosts', 'security', 'firewall', 'network']
      },
      {
        id: 'antivirus-opensource',
        name: 'Open-Source Antivirus Status',
        description: 'Status of open-source antivirus software across all hosts showing software name, version, installation path, and enabled/disabled status.',
        category: 'hosts',
        screenshot: `${baseURL}/api/reports/screenshots/antivirus-opensource.png`,
        tags: ['hosts', 'security', 'antivirus', 'opensource']
      },
      {
        id: 'antivirus-commercial',
        name: 'Commercial Antivirus Status',
        description: 'Commercial antivirus protection status including product name, version, signature version, real-time protection status, and service status across all managed hosts.',
        category: 'hosts',
        screenshot: `${baseURL}/api/reports/screenshots/antivirus-commercial.png`,
        tags: ['hosts', 'security', 'antivirus', 'commercial']
      },
      {
        id: 'audit-log',
        name: 'Audit Log',
        description: 'Complete audit trail of all user actions and system changes for compliance and security monitoring. Tracks database modifications, agent messages, and administrative operations.',
        category: 'security',
        screenshot: `${baseURL}/api/reports/screenshots/audit-log.png`,
        tags: ['users', 'security', 'audit', 'compliance', 'tracking']
      }
    ];

    const categoryFilter = tabValue === 0 ? 'hosts' : tabValue === 1 ? 'users' : 'security';
    return availableReports
      .filter(report => report.category === categoryFilter)
      .filter(report => {
        // Filter out audit-log if user doesn't have VIEW_AUDIT_LOG permission
        if (report.id === 'audit-log' && !canViewAuditLog) {
          return false;
        }
        return true;
      })
      .filter(report => {
        if (!searchTerm.trim()) return true;
        const searchValue = searchField === 'name' ? report.name : report.description;
        return searchValue.toLowerCase().includes(searchTerm.toLowerCase());
      });
  }, [tabValue, searchTerm, searchField, canViewAuditLog]);

  const handleViewReport = (reportId: string) => {
    // Audit log has its own dedicated viewer component
    if (reportId === 'audit-log') {
      navigate('/reports/audit-log');
    } else {
      navigate(`/reports/${reportId}`);
    }
  };

  const handleGenerateReport = async (reportId: string) => {
    try {
      const response = await api.get(`/api/reports/generate/${reportId}`, {
        responseType: 'blob', // Important for binary data
      });

      // Get the filename from the Content-Disposition header
      const contentDisposition = response.headers['content-disposition'];
      const filename = contentDisposition
        ? contentDisposition.split('filename=')[1]?.replace(/"/g, '')
        : `${reportId}_${new Date().toISOString().slice(0, 10)}.pdf`;

      // Create blob and download
      const blob = new Blob([response.data], { type: 'application/pdf' });
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = filename;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      window.URL.revokeObjectURL(url);

    } catch (error) {
      console.error('Error generating report:', error);
      // You might want to show a user-friendly error message here
      alert(`Error generating report: ${error instanceof Error ? error.message : 'Unknown error'}`);
    }
  };

  const ReportCard: React.FC<{ report: ReportCard }> = ({ report }) => (
    <Grid size={{ xs: 12, sm: 6, md: 4, lg: 3 }}>
      <Card
        sx={{
          height: '100%',
          display: 'flex',
          flexDirection: 'column',
          transition: 'transform 0.2s, box-shadow 0.2s',
          '&:hover': {
            transform: 'translateY(-4px)',
            boxShadow: 4,
          }
        }}
      >
        <CardMedia
          component="img"
          height="200"
          image={report.screenshot}
          alt={report.name}
          sx={{
            objectFit: 'cover',
            backgroundColor: 'rgba(0,0,0,0.1)',
            border: '1px solid rgba(255,255,255,0.1)'
          }}
          onError={(e) => {
            // Fallback to placeholder if screenshot doesn't exist
            (e.target as HTMLImageElement).src = 'data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iMzAwIiBoZWlnaHQ9IjIwMCIgdmlld0JveD0iMCAwIDMwMCAyMDAiIGZpbGw9Im5vbmUiIHhtbG5zPSJodHRwOi8vd3d3LnczLm9yZy8yMDAwL3N2ZyI+CjxyZWN0IHdpZHRoPSIzMDAiIGhlaWdodD0iMjAwIiBmaWxsPSIjMzc0MTUxIi8+CjxyZWN0IHg9IjIwIiB5PSIyMCIgd2lkdGg9IjI2MCIgaGVpZ2h0PSIxNjAiIGZpbGw9IiM0QTU1NjgiLz4KPHN2ZyB4PSI5NSIgeT0iNjAiIHdpZHRoPSIxMTAiIGhlaWdodD0iODAiIGZpbGw9IiM2Qjc0ODQiPgo8cGF0aCBkPSJNMTAgMTBINTBWNDBIMTBWMTBaIi8+CjxwYXRoIGQ9Ik02MCAyMEgxMDBWNDBINjBWMjBaIi8+CjxwYXRoIGQ9Ik0xMCA2MEg3MFY3MEgxMFY2MFoiLz4KPHN2ZyB4PSIxMzAiIHk9IjEyMCIgd2lkdGg9IjQwIiBoZWlnaHQ9IjQwIiBmaWxsPSIjOUNBM0FGIIB2aWV3Qm94PSIwIDAgMjQgMjQiPgo8cGF0aCBkPSJNMTQgMlY2SDE2TDE0IDhMMTEgNUwxNCAyWk02IDJWMjBMMTggMjBWOEwxMiAySDZaTTggNEgxMFY2SDhWNFpNOCA4SDEwVjEwSDhWOFpNOCAxMkgxNlYxNEg4VjEyWk04IDE2SDE2VjE4SDhWMTZaIi8+Cjwvc3ZnPgo8L3N2Zz4=';
          }}
        />
        <CardContent sx={{ flexGrow: 1, display: 'flex', flexDirection: 'column' }}>
          <Typography gutterBottom variant="h6" component="div" sx={{ fontWeight: 600 }}>
            {report.name}
          </Typography>
          <Typography
            variant="body2"
            color="text.secondary"
            sx={{
              flexGrow: 1,
              mb: 2,
              overflow: 'hidden',
              display: '-webkit-box',
              WebkitLineClamp: 3,
              WebkitBoxOrient: 'vertical',
            }}
          >
            {report.description}
          </Typography>
          <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.5 }}>
            {report.tags.map((tag) => (
              <Chip
                key={tag}
                label={tag}
                size="small"
                variant="outlined"
                sx={{ fontSize: '0.7rem' }}
              />
            ))}
          </Box>
        </CardContent>
        <Box sx={{ p: 2, pt: 0, display: 'flex', gap: 1 }}>
          {canViewReport && (
            <Button
              variant="outlined"
              startIcon={<ViewIcon />}
              fullWidth
              size="small"
              onClick={() => handleViewReport(report.id)}
            >
              {t('reports.viewReport', 'View Report')}
            </Button>
          )}
          {canGeneratePdfReport && (
            <Button
              variant="contained"
              startIcon={<DownloadIcon />}
              fullWidth
              size="small"
              onClick={() => handleGenerateReport(report.id)}
            >
              {t('reports.generatePdf', 'Generate PDF')}
            </Button>
          )}
        </Box>
      </Card>
    </Grid>
  );

  return (
    <div className="container">
      <Box sx={{ mb: 4 }}>
        <Typography variant="h4" component="h1" gutterBottom sx={{ fontWeight: 600 }}>
          <ReportIcon sx={{ mr: 1, verticalAlign: 'middle' }} />
          {t('reports.title', 'Reports')}
        </Typography>
        <Typography variant="body1" color="text.secondary">
          {t('reports.subtitle', 'Generate comprehensive reports for hosts, users, and system analytics')}
        </Typography>
      </Box>

      <Box sx={{ width: '100%' }}>
        <Box sx={{ borderBottom: 1, borderColor: 'divider' }}>
          <Tabs value={tabValue} onChange={handleTabChange} aria-label="reports tabs">
            <Tab label={t('reports.tabs.hosts', 'Hosts')} />
            <Tab label={t('reports.tabs.users', 'Users')} />
            <Tab label={t('reports.tabs.security', 'Security')} />
          </Tabs>
        </Box>

        <TabPanel value={tabValue} index={0}>
          <Box sx={{ mb: 3, display: 'flex', gap: 2, alignItems: 'center' }}>
            <TextField
              label={t('reports.search.label', 'Search reports')}
              variant="outlined"
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              size="small"
              sx={{ minWidth: 300 }}
              InputProps={{
                startAdornment: (
                  <InputAdornment position="start">
                    <SearchIcon />
                  </InputAdornment>
                ),
              }}
            />
            <FormControl size="small" sx={{ minWidth: 140 }}>
              <InputLabel>{t('reports.search.searchBy', 'Search by')}</InputLabel>
              <Select
                value={searchField}
                label={t('reports.search.searchBy', 'Search by')}
                onChange={(e) => setSearchField(e.target.value as 'name' | 'description')}
              >
                <MenuItem value="name">{t('reports.search.name', 'Name')}</MenuItem>
                <MenuItem value="description">{t('reports.search.description', 'Description')}</MenuItem>
              </Select>
            </FormControl>
          </Box>

          <Grid container spacing={3}>
            {filteredReports.map((report) => (
              <ReportCard key={report.id} report={report} />
            ))}
          </Grid>

          {filteredReports.length === 0 && (
            <Box sx={{ textAlign: 'center', py: 4 }}>
              <Typography variant="h6" color="text.secondary">
                {t('reports.noResults', 'No reports found matching your search')}
              </Typography>
            </Box>
          )}
        </TabPanel>

        <TabPanel value={tabValue} index={1}>
          <Box sx={{ mb: 3, display: 'flex', gap: 2, alignItems: 'center' }}>
            <TextField
              label={t('reports.search.label', 'Search reports')}
              variant="outlined"
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              size="small"
              sx={{ minWidth: 300 }}
              InputProps={{
                startAdornment: (
                  <InputAdornment position="start">
                    <SearchIcon />
                  </InputAdornment>
                ),
              }}
            />
            <FormControl size="small" sx={{ minWidth: 140 }}>
              <InputLabel>{t('reports.search.searchBy', 'Search by')}</InputLabel>
              <Select
                value={searchField}
                label={t('reports.search.searchBy', 'Search by')}
                onChange={(e) => setSearchField(e.target.value as 'name' | 'description')}
              >
                <MenuItem value="name">{t('reports.search.name', 'Name')}</MenuItem>
                <MenuItem value="description">{t('reports.search.description', 'Description')}</MenuItem>
              </Select>
            </FormControl>
          </Box>

          <Grid container spacing={3}>
            {filteredReports.map((report) => (
              <ReportCard key={report.id} report={report} />
            ))}
          </Grid>

          {filteredReports.length === 0 && (
            <Box sx={{ textAlign: 'center', py: 4 }}>
              <Typography variant="h6" color="text.secondary">
                {t('reports.noResults', 'No reports found matching your search')}
              </Typography>
            </Box>
          )}
        </TabPanel>

        <TabPanel value={tabValue} index={2}>
          <Box sx={{ mb: 3, display: 'flex', gap: 2, alignItems: 'center' }}>
            <TextField
              label={t('reports.search.label', 'Search reports')}
              variant="outlined"
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              size="small"
              sx={{ minWidth: 300 }}
              InputProps={{
                startAdornment: (
                  <InputAdornment position="start">
                    <SearchIcon />
                  </InputAdornment>
                ),
              }}
            />
            <FormControl size="small" sx={{ minWidth: 140 }}>
              <InputLabel>{t('reports.search.searchBy', 'Search by')}</InputLabel>
              <Select
                value={searchField}
                label={t('reports.search.searchBy', 'Search by')}
                onChange={(e) => setSearchField(e.target.value as 'name' | 'description')}
              >
                <MenuItem value="name">{t('reports.search.name', 'Name')}</MenuItem>
                <MenuItem value="description">{t('reports.search.description', 'Description')}</MenuItem>
              </Select>
            </FormControl>
          </Box>

          <Grid container spacing={3}>
            {filteredReports.map((report) => (
              <ReportCard key={report.id} report={report} />
            ))}
          </Grid>

          {filteredReports.length === 0 && (
            <Box sx={{ textAlign: 'center', py: 4 }}>
              <Typography variant="h6" color="text.secondary">
                {t('reports.noResults', 'No reports found matching your search')}
              </Typography>
            </Box>
          )}
        </TabPanel>
      </Box>
    </div>
  );
};

export default Reports;