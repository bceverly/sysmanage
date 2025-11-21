import React, { useState, useEffect, useCallback } from 'react';
import {
  Box,
  Card,
  CardContent,
  CardHeader,
  Typography,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
  TextField,
  Button,
  Stack,
  IconButton,
  Alert,
  Snackbar,
  CircularProgress,
  Divider,
} from '@mui/material';
import {
  Storage as StorageIcon,
  Add as AddIcon,
  Delete as DeleteIcon,
} from '@mui/icons-material';
import { useTranslation } from 'react-i18next';
import axiosInstance from '../Services/api';
import { hasPermission, SecurityRoles } from '../Services/permissions';

interface DefaultRepository {
  id: string;
  os_name: string;
  package_manager: string;
  repository_url: string;
  created_at: string;
  created_by: string | null;
}

interface OSPackageManagersResponse {
  operating_systems: string[];
  package_managers: Record<string, string[]>;
}

// Group repositories by OS and package manager for display
interface GroupedRepositories {
  [osName: string]: {
    [packageManager: string]: DefaultRepository[];
  };
}

const HostDefaultsSettings: React.FC = () => {
  const { t } = useTranslation();

  // Data state
  const [repositories, setRepositories] = useState<DefaultRepository[]>([]);
  const [osOptions, setOsOptions] = useState<string[]>([]);
  const [packageManagerOptions, setPackageManagerOptions] = useState<Record<string, string[]>>({});

  // Form state
  const [selectedOS, setSelectedOS] = useState<string>('');
  const [selectedPackageManager, setSelectedPackageManager] = useState<string>('');
  const [repositoryUrl, setRepositoryUrl] = useState<string>('');

  // OS-specific fields for repository construction
  const [ppaOwner, setPpaOwner] = useState<string>('');
  const [ppaName, setPpaName] = useState<string>('');
  const [coprOwner, setCoprOwner] = useState<string>('');
  const [coprProject, setCoprProject] = useState<string>('');
  const [obsUrl, setObsUrl] = useState<string>('https://download.opensuse.org/repositories/');
  const [obsProjectPath, setObsProjectPath] = useState<string>('');
  const [obsDistroVersion, setObsDistroVersion] = useState<string>('');
  const [obsRepoName, setObsRepoName] = useState<string>('');
  const [tapUser, setTapUser] = useState<string>('');
  const [tapRepo, setTapRepo] = useState<string>('');
  const [pkgRepoName, setPkgRepoName] = useState<string>('');
  const [pkgRepoUrl, setPkgRepoUrl] = useState<string>('');
  const [pkgsrcName, setPkgsrcName] = useState<string>('');
  const [pkgsrcUrl, setPkgsrcUrl] = useState<string>('');
  const [windowsRepoType, setWindowsRepoType] = useState<string>('chocolatey');
  const [windowsRepoName, setWindowsRepoName] = useState<string>('');
  const [windowsRepoUrl, setWindowsRepoUrl] = useState<string>('');

  // Computed repository string
  const [constructedRepo, setConstructedRepo] = useState<string>('');

  // UI state
  const [loading, setLoading] = useState<boolean>(true);
  const [saving, setSaving] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [snackbarOpen, setSnackbarOpen] = useState<boolean>(false);
  const [snackbarMessage, setSnackbarMessage] = useState<string>('');
  const [snackbarSeverity, setSnackbarSeverity] = useState<'success' | 'error'>('success');

  // Permission state
  const [canAdd, setCanAdd] = useState<boolean>(false);
  const [canRemove, setCanRemove] = useState<boolean>(false);
  const [canView, setCanView] = useState<boolean>(false);

  // Check permissions
  useEffect(() => {
    const checkPermissions = async () => {
      const [addPerm, removePerm, viewPerm] = await Promise.all([
        hasPermission(SecurityRoles.ADD_DEFAULT_REPOSITORY),
        hasPermission(SecurityRoles.REMOVE_DEFAULT_REPOSITORY),
        hasPermission(SecurityRoles.VIEW_DEFAULT_REPOSITORIES),
      ]);
      setCanAdd(addPerm);
      setCanRemove(removePerm);
      setCanView(viewPerm);
    };
    checkPermissions();
  }, []);

  // Load OS options
  const loadOSOptions = useCallback(async () => {
    try {
      const response = await axiosInstance.get<OSPackageManagersResponse>('/api/default-repositories/os-options');
      setOsOptions(response.data.operating_systems);
      setPackageManagerOptions(response.data.package_managers);
    } catch (err) {
      console.error('Error loading OS options:', err);
      setError(t('hostDefaults.errorLoadingOSOptions', 'Failed to load operating system options'));
    }
  }, [t]);

  // Load repositories
  const loadRepositories = useCallback(async () => {
    if (!canView) return;

    setLoading(true);
    try {
      const response = await axiosInstance.get<DefaultRepository[]>('/api/default-repositories/');
      setRepositories(response.data);
      setError(null);
    } catch (err) {
      console.error('Error loading repositories:', err);
      setError(t('hostDefaults.errorLoadingRepositories', 'Failed to load default repositories'));
    } finally {
      setLoading(false);
    }
  }, [canView, t]);

  // Initial load
  useEffect(() => {
    loadOSOptions();
  }, [loadOSOptions]);

  useEffect(() => {
    if (canView) {
      loadRepositories();
    } else {
      setLoading(false);
    }
  }, [canView, loadRepositories]);

  // Get available package managers for selected OS
  const availablePackageManagers = selectedOS ? (packageManagerOptions[selectedOS] || []) : [];

  // Reset package manager when OS changes
  useEffect(() => {
    setSelectedPackageManager('');
    // Also reset all OS-specific fields when OS changes
    setPpaOwner('');
    setPpaName('');
    setCoprOwner('');
    setCoprProject('');
    setObsUrl('https://download.opensuse.org/repositories/');
    setObsProjectPath('');
    setObsDistroVersion('');
    setObsRepoName('');
    setTapUser('');
    setTapRepo('');
    setPkgRepoName('');
    setPkgRepoUrl('');
    setPkgsrcName('');
    setPkgsrcUrl('');
    setWindowsRepoType('chocolatey');
    setWindowsRepoName('');
    setWindowsRepoUrl('');
    setConstructedRepo('');
  }, [selectedOS]);

  // Build constructed repository string based on OS
  useEffect(() => {
    if (selectedOS.includes('Ubuntu') || selectedOS.includes('Debian')) {
      if (ppaOwner && ppaName) {
        setConstructedRepo(`ppa:${ppaOwner}/${ppaName}`);
      } else {
        setConstructedRepo('');
      }
    } else if (selectedOS.includes('Fedora') || selectedOS.includes('RHEL') || selectedOS.includes('CentOS')) {
      if (coprOwner && coprProject) {
        setConstructedRepo(`${coprOwner}/${coprProject}`);
      } else {
        setConstructedRepo('');
      }
    } else if (selectedOS.includes('SUSE') || selectedOS.includes('openSUSE')) {
      if (obsUrl && obsProjectPath && obsDistroVersion && obsRepoName) {
        const cleanUrl = obsUrl.endsWith('/') ? obsUrl : obsUrl + '/';
        setConstructedRepo(`${cleanUrl}${obsProjectPath}/${obsDistroVersion}/${obsRepoName}`);
      } else {
        setConstructedRepo('');
      }
    } else if (selectedOS.includes('macOS') || selectedOS.includes('Darwin')) {
      if (tapUser && tapRepo) {
        setConstructedRepo(`${tapUser}/${tapRepo}`);
      } else {
        setConstructedRepo('');
      }
    } else if (selectedOS.includes('FreeBSD')) {
      if (pkgRepoName && pkgRepoUrl) {
        setConstructedRepo(pkgRepoName);
      } else {
        setConstructedRepo('');
      }
    } else if (selectedOS.includes('NetBSD')) {
      if (pkgsrcName && pkgsrcUrl) {
        setConstructedRepo(pkgsrcName);
      } else {
        setConstructedRepo('');
      }
    } else if (selectedOS.includes('Windows')) {
      if (windowsRepoName && windowsRepoUrl) {
        setConstructedRepo(windowsRepoName);
      } else {
        setConstructedRepo('');
      }
    }
  }, [selectedOS, ppaOwner, ppaName, coprOwner, coprProject, obsUrl, obsProjectPath, obsDistroVersion, obsRepoName, tapUser, tapRepo, pkgRepoName, pkgRepoUrl, pkgsrcName, pkgsrcUrl, windowsRepoName, windowsRepoUrl]);

  // Check if form is valid - use constructedRepo if available, otherwise fall back to repositoryUrl
  const finalRepoUrl = constructedRepo || repositoryUrl.trim();
  const isFormValid = selectedOS && selectedPackageManager && finalRepoUrl;

  // Handle add repository
  const handleAddRepository = async () => {
    if (!isFormValid) return;

    setSaving(true);
    try {
      await axiosInstance.post('/api/default-repositories/', {
        os_name: selectedOS,
        package_manager: selectedPackageManager,
        repository_url: finalRepoUrl,
      });

      // Reset form
      setSelectedOS('');
      setSelectedPackageManager('');
      setRepositoryUrl('');
      setPpaOwner('');
      setPpaName('');
      setCoprOwner('');
      setCoprProject('');
      setObsUrl('https://download.opensuse.org/repositories/');
      setObsProjectPath('');
      setObsDistroVersion('');
      setObsRepoName('');
      setTapUser('');
      setTapRepo('');
      setPkgRepoName('');
      setPkgRepoUrl('');
      setPkgsrcName('');
      setPkgsrcUrl('');
      setWindowsRepoType('chocolatey');
      setWindowsRepoName('');
      setWindowsRepoUrl('');
      setConstructedRepo('');

      // Reload repositories
      await loadRepositories();

      setSnackbarMessage(t('hostDefaults.repositoryAdded', 'Default repository added successfully'));
      setSnackbarSeverity('success');
      setSnackbarOpen(true);
    } catch (err: unknown) {
      console.error('Error adding repository:', err);
      const errorMessage = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
        t('hostDefaults.errorAddingRepository', 'Failed to add default repository');
      setSnackbarMessage(errorMessage);
      setSnackbarSeverity('error');
      setSnackbarOpen(true);
    } finally {
      setSaving(false);
    }
  };

  // Handle delete repository
  const handleDeleteRepository = async (repoId: string) => {
    try {
      await axiosInstance.delete(`/api/default-repositories/${repoId}`);

      // Reload repositories
      await loadRepositories();

      setSnackbarMessage(t('hostDefaults.repositoryDeleted', 'Default repository deleted successfully'));
      setSnackbarSeverity('success');
      setSnackbarOpen(true);
    } catch (err: unknown) {
      console.error('Error deleting repository:', err);
      const errorMessage = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
        t('hostDefaults.errorDeletingRepository', 'Failed to delete default repository');
      setSnackbarMessage(errorMessage);
      setSnackbarSeverity('error');
      setSnackbarOpen(true);
    }
  };

  // Group repositories by OS and package manager
  const groupedRepositories: GroupedRepositories = repositories.reduce((acc, repo) => {
    if (!acc[repo.os_name]) {
      acc[repo.os_name] = {};
    }
    if (!acc[repo.os_name][repo.package_manager]) {
      acc[repo.os_name][repo.package_manager] = [];
    }
    acc[repo.os_name][repo.package_manager].push(repo);
    return acc;
  }, {} as GroupedRepositories);

  // Sort OS names
  const sortedOSNames = Object.keys(groupedRepositories).sort();

  if (!canView) {
    return (
      <Alert severity="warning">
        {t('hostDefaults.noViewPermission', 'You do not have permission to view default repositories.')}
      </Alert>
    );
  }

  return (
    <Box>
      <Card>
        <CardHeader
          avatar={<StorageIcon color="primary" />}
          title={t('hostDefaults.repositoriesTitle', 'Repositories')}
          subheader={t('hostDefaults.repositoriesSubheader', 'Configure default third-party repositories that will be applied to new hosts when approved')}
        />
        <CardContent>
          {error && (
            <Alert severity="error" sx={{ mb: 2 }}>
              {error}
            </Alert>
          )}

          {/* Add Repository Form */}
          {canAdd && (
            <Box sx={{ mb: 3 }}>
              <Typography variant="subtitle1" sx={{ mb: 2 }}>
                {t('hostDefaults.addNewRepository', 'Add New Default Repository')}
              </Typography>
              <Stack spacing={2}>
                <Stack direction={{ xs: 'column', md: 'row' }} spacing={2} alignItems="flex-start">
                  <FormControl sx={{ minWidth: 200 }}>
                    <InputLabel>{t('hostDefaults.operatingSystem', 'Operating System')}</InputLabel>
                    <Select
                      value={selectedOS}
                      label={t('hostDefaults.operatingSystem', 'Operating System')}
                      onChange={(e) => setSelectedOS(e.target.value)}
                    >
                      {osOptions.map((os) => (
                        <MenuItem key={os} value={os}>
                          {os}
                        </MenuItem>
                      ))}
                    </Select>
                  </FormControl>

                  <FormControl sx={{ minWidth: 180 }} disabled={!selectedOS}>
                    <InputLabel>{t('hostDefaults.packageManager', 'Package Manager')}</InputLabel>
                    <Select
                      value={availablePackageManagers.includes(selectedPackageManager) ? selectedPackageManager : ''}
                      label={t('hostDefaults.packageManager', 'Package Manager')}
                      onChange={(e) => setSelectedPackageManager(e.target.value)}
                    >
                      {availablePackageManagers.map((pm) => (
                        <MenuItem key={pm} value={pm}>
                          {pm}
                        </MenuItem>
                      ))}
                    </Select>
                  </FormControl>
                </Stack>

                {/* Ubuntu/Debian PPA Fields */}
                {(selectedOS.includes('Ubuntu') || selectedOS.includes('Debian')) && (
                  <Stack direction="row" spacing={2}>
                    <TextField
                      fullWidth
                      label={t('thirdPartyRepos.ppaOwner', 'PPA Owner')}
                      value={ppaOwner}
                      onChange={(e) => setPpaOwner(e.target.value)}
                      placeholder={t('thirdPartyRepos.ppaOwnerPlaceholder', 'e.g., bceverly')}
                    />
                    <TextField
                      fullWidth
                      label={t('thirdPartyRepos.ppaName', 'PPA Name')}
                      value={ppaName}
                      onChange={(e) => setPpaName(e.target.value)}
                      placeholder={t('thirdPartyRepos.ppaNamePlaceholder', 'e.g., sysmanage-agent')}
                    />
                  </Stack>
                )}

                {/* CentOS/RHEL/Fedora COPR Fields */}
                {(selectedOS.includes('Fedora') || selectedOS.includes('RHEL') || selectedOS.includes('CentOS')) && (
                  <Stack direction="row" spacing={2}>
                    <TextField
                      fullWidth
                      label={t('thirdPartyRepos.coprOwner', 'COPR Owner')}
                      value={coprOwner}
                      onChange={(e) => setCoprOwner(e.target.value)}
                      placeholder={t('thirdPartyRepos.coprOwnerPlaceholder', 'e.g., @dotnet-sig')}
                    />
                    <TextField
                      fullWidth
                      label={t('thirdPartyRepos.coprProject', 'COPR Project')}
                      value={coprProject}
                      onChange={(e) => setCoprProject(e.target.value)}
                      placeholder={t('thirdPartyRepos.coprProjectPlaceholder', 'e.g., dotnet-6.0')}
                    />
                  </Stack>
                )}

                {/* SUSE OBS Fields */}
                {(selectedOS.includes('SUSE') || selectedOS.includes('openSUSE')) && (
                  <Stack spacing={2}>
                    <TextField
                      fullWidth
                      label={t('thirdPartyRepos.obsUrl', 'OBS Base URL')}
                      value={obsUrl}
                      onChange={(e) => setObsUrl(e.target.value)}
                      placeholder="https://download.opensuse.org/repositories/"
                    />
                    <TextField
                      fullWidth
                      label={t('thirdPartyRepos.obsProjectPath', 'Project Path')}
                      value={obsProjectPath}
                      onChange={(e) => setObsProjectPath(e.target.value)}
                      placeholder="home:/username:/project"
                    />
                    <Stack direction="row" spacing={2}>
                      <TextField
                        fullWidth
                        label={t('thirdPartyRepos.obsDistroVersion', 'Distribution/Version')}
                        value={obsDistroVersion}
                        onChange={(e) => setObsDistroVersion(e.target.value)}
                        placeholder="openSUSE_Tumbleweed"
                      />
                      <TextField
                        fullWidth
                        label={t('thirdPartyRepos.obsRepoName', 'Repository Name')}
                        value={obsRepoName}
                        onChange={(e) => setObsRepoName(e.target.value)}
                        placeholder="myrepo"
                      />
                    </Stack>
                  </Stack>
                )}

                {/* macOS Homebrew Tap Fields */}
                {(selectedOS.includes('macOS') || selectedOS.includes('Darwin')) && (
                  <Stack direction="row" spacing={2}>
                    <TextField
                      fullWidth
                      label={t('thirdPartyRepos.tapUser', 'Tap User')}
                      value={tapUser}
                      onChange={(e) => setTapUser(e.target.value)}
                      placeholder="homebrew"
                    />
                    <TextField
                      fullWidth
                      label={t('thirdPartyRepos.tapRepo', 'Tap Repository')}
                      value={tapRepo}
                      onChange={(e) => setTapRepo(e.target.value)}
                      placeholder="core"
                    />
                  </Stack>
                )}

                {/* FreeBSD pkg Fields */}
                {selectedOS.includes('FreeBSD') && (
                  <Stack direction="row" spacing={2}>
                    <TextField
                      fullWidth
                      label={t('thirdPartyRepos.pkgRepoName', 'Repository Name')}
                      value={pkgRepoName}
                      onChange={(e) => setPkgRepoName(e.target.value)}
                      placeholder="custom-repo"
                    />
                    <TextField
                      fullWidth
                      label={t('thirdPartyRepos.pkgRepoUrl', 'Repository URL')}
                      value={pkgRepoUrl}
                      onChange={(e) => setPkgRepoUrl(e.target.value)}
                      placeholder="https://pkg.example.com/${ABI}"
                    />
                  </Stack>
                )}

                {/* NetBSD pkgsrc Fields */}
                {selectedOS.includes('NetBSD') && (
                  <Stack direction="row" spacing={2}>
                    <TextField
                      fullWidth
                      label={t('thirdPartyRepos.pkgsrcName', 'Repository Name')}
                      value={pkgsrcName}
                      onChange={(e) => setPkgsrcName(e.target.value)}
                      placeholder="custom-pkgsrc"
                    />
                    <TextField
                      fullWidth
                      label={t('thirdPartyRepos.pkgsrcUrl', 'Repository URL')}
                      value={pkgsrcUrl}
                      onChange={(e) => setPkgsrcUrl(e.target.value)}
                      placeholder="https://pkgsrc.example.com"
                    />
                  </Stack>
                )}

                {/* Windows Package Manager Fields */}
                {selectedOS.includes('Windows') && (
                  <Stack spacing={2}>
                    <FormControl fullWidth>
                      <InputLabel>{t('thirdPartyRepos.windowsRepoType', 'Repository Type')}</InputLabel>
                      <Select
                        value={windowsRepoType}
                        label={t('thirdPartyRepos.windowsRepoType', 'Repository Type')}
                        onChange={(e) => setWindowsRepoType(e.target.value)}
                      >
                        <MenuItem value="chocolatey">Chocolatey</MenuItem>
                        <MenuItem value="scoop">Scoop</MenuItem>
                      </Select>
                    </FormControl>
                    <TextField
                      fullWidth
                      label={t('thirdPartyRepos.windowsRepoName', 'Repository Name')}
                      value={windowsRepoName}
                      onChange={(e) => setWindowsRepoName(e.target.value)}
                      placeholder="custom-repo"
                    />
                    <TextField
                      fullWidth
                      label={t('thirdPartyRepos.windowsRepoUrl', 'Repository URL')}
                      value={windowsRepoUrl}
                      onChange={(e) => setWindowsRepoUrl(e.target.value)}
                      placeholder="https://chocolatey.example.com/api/v2"
                    />
                  </Stack>
                )}

                {/* Show constructed repository */}
                {constructedRepo && (
                  <Box sx={{ p: 2, bgcolor: 'action.hover', border: 1, borderColor: 'divider', borderRadius: 1 }}>
                    <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 0.5 }}>
                      {t('thirdPartyRepos.constructedIdentifier', 'Repository Identifier')}:
                    </Typography>
                    <Typography variant="body2" color="text.primary" sx={{ fontFamily: 'monospace', fontWeight: 500 }}>
                      {constructedRepo}
                    </Typography>
                  </Box>
                )}

                {/* Fallback: Manual repository URL entry for unsupported OS */}
                {selectedPackageManager && !selectedOS.match(/Ubuntu|Debian|Fedora|RHEL|CentOS|SUSE|openSUSE|macOS|Darwin|FreeBSD|NetBSD|Windows/) && (
                  <TextField
                    fullWidth
                    label={t('hostDefaults.repositoryUrl', 'Repository URL / PPA')}
                    value={repositoryUrl}
                    onChange={(e) => setRepositoryUrl(e.target.value)}
                    placeholder={t('hostDefaults.repositoryUrlPlaceholder', 'e.g., ppa:example/ppa or https://...')}
                  />
                )}

                <Button
                  variant="contained"
                  startIcon={saving ? <CircularProgress size={20} color="inherit" /> : <AddIcon />}
                  onClick={handleAddRepository}
                  disabled={!isFormValid || saving}
                  sx={{ alignSelf: 'flex-start' }}
                >
                  {t('common.add', 'Add')}
                </Button>
              </Stack>
            </Box>
          )}

          <Divider sx={{ my: 2 }} />

          {/* Repository List */}
          <Typography variant="subtitle1" sx={{ mb: 2 }}>
            {t('hostDefaults.configuredRepositories', 'Configured Default Repositories')}
          </Typography>

          {loading ? (
            <Box sx={{ display: 'flex', justifyContent: 'center', py: 4 }}>
              <CircularProgress />
            </Box>
          ) : repositories.length === 0 ? (
            <Alert severity="info">
              {t('hostDefaults.noRepositories', 'No default repositories configured. Add repositories above to have them automatically applied to new hosts.')}
            </Alert>
          ) : (
            <Box>
              {sortedOSNames.map((osName) => (
                <Box key={osName} sx={{ mb: 3 }}>
                  <Typography variant="h6" sx={{ mb: 1, color: 'primary.main' }}>
                    {osName}
                  </Typography>
                  {Object.keys(groupedRepositories[osName]).sort().map((packageManager) => (
                    <Box key={`${osName}-${packageManager}`} sx={{ ml: 2, mb: 2 }}>
                      <Typography variant="subtitle2" sx={{ mb: 1, fontWeight: 'bold' }}>
                        {packageManager}
                      </Typography>
                      {groupedRepositories[osName][packageManager].map((repo) => (
                        <Box
                          key={repo.id}
                          sx={{
                            display: 'flex',
                            alignItems: 'center',
                            justifyContent: 'space-between',
                            py: 1,
                            px: 2,
                            ml: 2,
                            bgcolor: 'action.hover',
                            borderRadius: 1,
                            mb: 1,
                          }}
                        >
                          <Typography variant="body2" sx={{ fontFamily: 'monospace', wordBreak: 'break-all' }}>
                            {repo.repository_url}
                          </Typography>
                          {canRemove && (
                            <IconButton
                              size="small"
                              color="error"
                              onClick={() => handleDeleteRepository(repo.id)}
                              title={t('common.delete', 'Delete')}
                            >
                              <DeleteIcon />
                            </IconButton>
                          )}
                        </Box>
                      ))}
                    </Box>
                  ))}
                </Box>
              ))}
            </Box>
          )}
        </CardContent>
      </Card>

      <Snackbar
        open={snackbarOpen}
        autoHideDuration={6000}
        onClose={() => setSnackbarOpen(false)}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'center' }}
      >
        <Alert
          onClose={() => setSnackbarOpen(false)}
          severity={snackbarSeverity}
          sx={{ width: '100%' }}
        >
          {snackbarMessage}
        </Alert>
      </Snackbar>
    </Box>
  );
};

export default HostDefaultsSettings;
