// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

import React from 'react';
import { useTranslation } from 'react-i18next';
import {
  Alert,
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
  TextField,
  Typography,
} from '@mui/material';
import {
  Refresh as RefreshIcon,
  Search as SearchIcon,
  Storage as StorageIcon,
} from '@mui/icons-material';
import { DataGrid } from '@mui/x-data-grid';
import { OSPackageSummary, PackageInfo } from './settingsTypes';

interface AvailablePackagesTabProps {
  packageSummary: OSPackageSummary[];
  packages: PackageInfo[];
  selectedOS: string;
  setSelectedOS: (value: string) => void;
  selectedManager: string;
  setSelectedManager: (value: string) => void;
  packageSearchTerm: string;
  setPackageSearchTerm: (value: string) => void;
  packageLoading: boolean;
  packageSummaryLoading: boolean;
  packageTotalCount: number;
  hasSearched: boolean;
  onRefreshAll: () => void;
  onRefreshOS: (osName: string, osVersion: string) => void;
  onSearch: (page?: number, pageSize?: number) => void;
}

const AvailablePackagesTab: React.FC<AvailablePackagesTabProps> = ({
  packageSummary,
  packages,
  selectedOS,
  setSelectedOS,
  selectedManager,
  setSelectedManager,
  packageSearchTerm,
  setPackageSearchTerm,
  packageLoading,
  packageSummaryLoading,
  packageTotalCount,
  hasSearched,
  onRefreshAll,
  onRefreshOS,
  onSearch,
}) => {
  const { t } = useTranslation();

  return (
    <Box>
      {/* Header with title and refresh button */}
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2 }}>
        <Typography variant="h5">
          {t('availablePackages.title', 'Available Packages')}
        </Typography>
        <Button
          variant="contained"
          startIcon={<RefreshIcon />}
          onClick={onRefreshAll}
          sx={{ minWidth: 150 }}
        >
          {t('availablePackages.refreshAll', 'Refresh All')}
        </Button>
      </Box>

      {/* Package Summary Cards */}
      {packageSummary.length > 0 && (
        <Box sx={{ mb: 4 }}>
          <Grid container spacing={2}>
            {packageSummary.map((summary) => (
              <Grid size={{ xs: 12, sm: 6, md: 4 }} key={`${summary.os_name}:${summary.os_version}`}>
                <Card>
                  <CardContent>
                    <Box display="flex" alignItems="center" mb={1}>
                      <StorageIcon sx={{ mr: 1, color: 'primary.main' }} />
                      <Typography variant="h6">
                        {summary.os_name} {summary.os_version}
                      </Typography>
                    </Box>
                    <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
                      {t('availablePackages.totalPackages', 'Total Packages')}: {summary.total_packages.toLocaleString()}
                    </Typography>
                    <Box>
                      {summary.package_managers.map((manager) => (
                        <Chip
                          key={manager.package_manager}
                          label={`${manager.package_manager}: ${manager.package_count.toLocaleString()}`}
                          size="small"
                          variant="outlined"
                          sx={{ mr: 0.5, mb: 0.5 }}
                        />
                      ))}
                    </Box>
                    <Box sx={{ mt: 1, display: 'flex', justifyContent: 'flex-end' }}>
                      <Button
                        size="small"
                        variant="outlined"
                        startIcon={<RefreshIcon />}
                        onClick={() => onRefreshOS(summary.os_name, summary.os_version)}
                        sx={{ fontSize: '0.75rem' }}
                      >
                        {t('availablePackages.refresh', 'Refresh')}
                      </Button>
                    </Box>
                  </CardContent>
                </Card>
              </Grid>
            ))}
          </Grid>
        </Box>
      )}

      {/* Search Controls */}
      <Box sx={{ mb: 3 }}>
        <Typography variant="h6" sx={{ mb: 2 }}>
          {t('availablePackages.search', 'Search Packages')}
        </Typography>
        <Grid container spacing={2} alignItems="end">
          <Grid size={{ xs: 12, md: 4 }}>
            <TextField
              fullWidth
              label={t('availablePackages.searchTerm', 'Package name')}
              value={packageSearchTerm}
              onChange={(e) => setPackageSearchTerm(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && onSearch(0, 25)}
              slotProps={{
                input: {
                  endAdornment: (
                    <IconButton onClick={() => onSearch(0, 25)}>
                      <SearchIcon />
                    </IconButton>
                  ),
                },
              }}
            />
          </Grid>
          <Grid size={{ xs: 12, md: 3 }}>
            <FormControl fullWidth>
              <InputLabel>{t('availablePackages.filterByOS', 'Operating System / Version')}</InputLabel>
              <Select
                value={selectedOS}
                label={t('availablePackages.filterByOS', 'Operating System / Version')}
                onChange={(e) => setSelectedOS(e.target.value)}
              >
                <MenuItem value="">
                  <em>{t('common.all', 'All')}</em>
                </MenuItem>
                {packageSummary.map((summary) => (
                  <MenuItem key={`${summary.os_name}:${summary.os_version}`} value={`${summary.os_name}:${summary.os_version}`}>
                    {summary.os_name} {summary.os_version}
                  </MenuItem>
                ))}
              </Select>
            </FormControl>
          </Grid>
          <Grid size={{ xs: 12, md: 3 }}>
            <FormControl fullWidth>
              <InputLabel>{t('availablePackages.filterByManager', 'Package Manager')}</InputLabel>
              <Select
                value={selectedManager}
                label={t('availablePackages.filterByManager', 'Package Manager')}
                onChange={(e) => setSelectedManager(e.target.value)}
              >
                <MenuItem value="">
                  <em>{t('updates.filters.allManagers', 'All Package Managers')}</em>
                </MenuItem>
                {/* eslint-disable i18next/no-literal-string -- package manager brand names */}
                <MenuItem value="apt">APT</MenuItem>
                <MenuItem value="snap">Snap</MenuItem>
                <MenuItem value="flatpak">Flatpak</MenuItem>
                <MenuItem value="fwupd">fwupd</MenuItem>
                <MenuItem value="homebrew">Homebrew</MenuItem>
                <MenuItem value="winget">Winget</MenuItem>
                <MenuItem value="chocolatey">Chocolatey</MenuItem>
                <MenuItem value="pkg">PKG</MenuItem>
                <MenuItem value="yum">YUM</MenuItem>
                <MenuItem value="dnf">DNF</MenuItem>
                <MenuItem value="zypper">Zypper</MenuItem>
                <MenuItem value="pacman">Pacman</MenuItem>
                {/* eslint-enable i18next/no-literal-string */}
              </Select>
            </FormControl>
          </Grid>
          <Grid size={{ xs: 12, md: 2 }}>
            <Button
              fullWidth
              variant="contained"
              onClick={() => onSearch(0, 25)}
              disabled={!packageSearchTerm.trim()}
              startIcon={<SearchIcon />}
              sx={{ height: '56px' }}
            >
              {t('common.search', 'Search')}
            </Button>
          </Grid>
        </Grid>
      </Box>

      {/* Search Results */}
      {packages.length > 0 && (
        <Box>
          <Typography variant="h6" sx={{ mb: 2 }}>
            {t('availablePackages.results', 'Search Results')}{' '}
            {/* eslint-disable-next-line i18next/no-literal-string -- result count summary uses interpolated values */}
            ({packageTotalCount.toLocaleString()} total, showing {packages.length})
          </Typography>
          <div style={{ height: 400 }}>
            <DataGrid
              rows={packages.map((pkg, index) => ({ id: index, ...pkg }))}
              columns={[
                { field: 'name', headerName: t('availablePackages.packageName', 'Package Name'), width: 250 },
                { field: 'version', headerName: t('availablePackages.version', 'Version'), width: 150 },
                { field: 'package_manager', headerName: t('availablePackages.manager', 'Manager'), width: 120 },
                {
                  field: 'description',
                  headerName: t('availablePackages.description', 'Description'),
                  width: 400,
                  renderCell: (params) => (
                    <Typography variant="body2" noWrap title={params.value}>
                      {params.value || t('common.noDescription', 'No description')}
                    </Typography>
                  )
                }
              ]}
              loading={packageLoading}
              rowCount={packageTotalCount}
              paginationMode="server"
              onPaginationModelChange={(model) => {
                onSearch(model.page, model.pageSize);
              }}
              initialState={{
                pagination: {
                  paginationModel: { page: 0, pageSize: 25 },
                },
              }}
              pageSizeOptions={[25, 50, 100]}
            />
          </div>
        </Box>
      )}

      {/* Empty State */}
      {hasSearched && packages.length === 0 && !packageLoading && (
        <Alert severity="info" sx={{ mt: 2 }}>
          {t('availablePackages.noResults', 'No packages found matching your search criteria.')}
        </Alert>
      )}

      {/* Initial State */}
      {!packageSearchTerm && packageSummary.length === 0 && !packageSummaryLoading && (
        <Alert severity="info" sx={{ mt: 2 }}>
          {t('availablePackages.noData', 'No package data available. Packages will be collected from your managed hosts automatically.')}
        </Alert>
      )}

      {/* Loading State */}
      {packageSummaryLoading && packageSummary.length === 0 && (
        <Alert severity="info" sx={{ mt: 2 }}>
          {t('availablePackages.loading', 'Loading package data...')}
        </Alert>
      )}
    </Box>
  );
};

export default AvailablePackagesTab;
