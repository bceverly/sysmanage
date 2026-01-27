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
  Settings as SettingsIcon,
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

interface EnabledPackageManager {
  id: string;
  os_name: string;
  package_manager: string;
  created_at: string;
  created_by: string | null;
}

interface OSPackageManagersResponse {
  operating_systems: string[];
  package_managers: Record<string, string[]>;
}

interface PMOSOptionsResponse {
  operating_systems: string[];
  default_package_managers: Record<string, string | null>;
  optional_package_managers: Record<string, string[]>;
}

// Group repositories by OS and package manager for display
interface GroupedRepositories {
  [osName: string]: {
    [packageManager: string]: DefaultRepository[];
  };
}

const HostDefaultsSettings: React.FC = () => { // NOSONAR
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

  // Permission state for repositories
  const [canAdd, setCanAdd] = useState<boolean>(false);
  const [canRemove, setCanRemove] = useState<boolean>(false);
  const [canView, setCanView] = useState<boolean>(false);

  // Enabled Package Managers state
  const [enabledPMs, setEnabledPMs] = useState<EnabledPackageManager[]>([]);
  const [pmOSOptions, setPmOSOptions] = useState<string[]>([]);
  const [pmDefaultManagers, setPmDefaultManagers] = useState<Record<string, string | null>>({});
  const [pmOptionalManagers, setPmOptionalManagers] = useState<Record<string, string[]>>({});
  const [selectedPMOS, setSelectedPMOS] = useState<string>('');
  const [selectedOptionalPM, setSelectedOptionalPM] = useState<string>('');
  const [pmLoading, setPmLoading] = useState<boolean>(true);
  const [pmSaving, setPmSaving] = useState<boolean>(false);
  const [pmError, setPmError] = useState<string | null>(null);

  // Permission state for enabled package managers
  const [canAddPM, setCanAddPM] = useState<boolean>(false);
  const [canRemovePM, setCanRemovePM] = useState<boolean>(false);
  const [canViewPM, setCanViewPM] = useState<boolean>(false);

  // Check permissions
  useEffect(() => {
    const checkPermissions = async () => {
      const [addPerm, removePerm, viewPerm, addPMPerm, removePMPerm, viewPMPerm] = await Promise.all([
        hasPermission(SecurityRoles.ADD_DEFAULT_REPOSITORY),
        hasPermission(SecurityRoles.REMOVE_DEFAULT_REPOSITORY),
        hasPermission(SecurityRoles.VIEW_DEFAULT_REPOSITORIES),
        hasPermission(SecurityRoles.ADD_ENABLED_PACKAGE_MANAGER),
        hasPermission(SecurityRoles.REMOVE_ENABLED_PACKAGE_MANAGER),
        hasPermission(SecurityRoles.VIEW_ENABLED_PACKAGE_MANAGERS),
      ]);
      setCanAdd(addPerm);
      setCanRemove(removePerm);
      setCanView(viewPerm);
      setCanAddPM(addPMPerm);
      setCanRemovePM(removePMPerm);
      setCanViewPM(viewPMPerm);
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

  // Load enabled package managers OS options
  const loadPMOSOptions = useCallback(async () => {
    try {
      const response = await axiosInstance.get<PMOSOptionsResponse>('/api/enabled-package-managers/os-options');
      setPmOSOptions(response.data.operating_systems);
      setPmDefaultManagers(response.data.default_package_managers);
      setPmOptionalManagers(response.data.optional_package_managers);
    } catch (err) {
      console.error('Error loading PM OS options:', err);
      setPmError(t('hostDefaults.errorLoadingOSOptions', 'Failed to load operating system options'));
    }
  }, [t]);

  // Load enabled package managers
  const loadEnabledPMs = useCallback(async () => {
    if (!canViewPM) return;

    setPmLoading(true);
    try {
      const response = await axiosInstance.get<EnabledPackageManager[]>('/api/enabled-package-managers/');
      setEnabledPMs(response.data);
      setPmError(null);
    } catch (err) {
      console.error('Error loading enabled package managers:', err);
      setPmError(t('hostDefaults.errorLoadingPackageManagers', 'Failed to load enabled package managers'));
    } finally {
      setPmLoading(false);
    }
  }, [canViewPM, t]);

  // Initial load
  useEffect(() => {
    loadOSOptions();
    loadPMOSOptions();
  }, [loadOSOptions, loadPMOSOptions]);

  useEffect(() => {
    if (canView) {
      loadRepositories();
    } else {
      setLoading(false);
    }
  }, [canView, loadRepositories]);

  useEffect(() => {
    if (canViewPM) {
      loadEnabledPMs();
    } else {
      setPmLoading(false);
    }
  }, [canViewPM, loadEnabledPMs]);

  // Get available package managers for selected OS
  const availablePackageManagers = packageManagerOptions[selectedOS] ?? [];

  // Get available optional package managers for selected PM OS
  const availableOptionalPMs = pmOptionalManagers[selectedPMOS] ?? [];

  // Reset optional PM selection when PM OS changes
  useEffect(() => {
    setSelectedOptionalPM('');
  }, [selectedPMOS]);

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

  // Helper to check if OS matches any of the given patterns
  const osMatches = (os: string, ...patterns: string[]): boolean => {
    return patterns.some(pattern => os.includes(pattern));
  };

  // Helper to build repository string for Ubuntu/Debian (PPA)
  const buildPpaRepo = useCallback((): string => {
    return (ppaOwner && ppaName) ? `ppa:${ppaOwner}/${ppaName}` : '';
  }, [ppaOwner, ppaName]);

  // Helper to build repository string for Fedora/RHEL/CentOS (COPR)
  const buildCoprRepo = useCallback((): string => {
    return (coprOwner && coprProject) ? `${coprOwner}/${coprProject}` : '';
  }, [coprOwner, coprProject]);

  // Helper to build repository string for SUSE/openSUSE (OBS)
  const buildObsRepo = useCallback((): string => {
    if (obsUrl && obsProjectPath && obsDistroVersion && obsRepoName) {
      const cleanUrl = obsUrl.endsWith('/') ? obsUrl : obsUrl + '/';
      return `${cleanUrl}${obsProjectPath}/${obsDistroVersion}/${obsRepoName}`;
    }
    return '';
  }, [obsUrl, obsProjectPath, obsDistroVersion, obsRepoName]);

  // Helper to build repository string for macOS (Homebrew tap)
  const buildHomebrewTapRepo = useCallback((): string => {
    return (tapUser && tapRepo) ? `${tapUser}/${tapRepo}` : '';
  }, [tapUser, tapRepo]);

  // Helper to build repository string for FreeBSD (pkg)
  const buildFreeBsdRepo = useCallback((): string => {
    return (pkgRepoName && pkgRepoUrl) ? pkgRepoName : '';
  }, [pkgRepoName, pkgRepoUrl]);

  // Helper to build repository string for NetBSD (pkgsrc)
  const buildNetBsdRepo = useCallback((): string => {
    return (pkgsrcName && pkgsrcUrl) ? pkgsrcName : '';
  }, [pkgsrcName, pkgsrcUrl]);

  // Helper to build repository string for Windows
  const buildWindowsRepo = useCallback((): string => {
    return (windowsRepoName && windowsRepoUrl) ? windowsRepoName : '';
  }, [windowsRepoName, windowsRepoUrl]);

  // Build constructed repository string based on OS
  useEffect(() => {
    let repoString = '';

    if (osMatches(selectedOS, 'Ubuntu', 'Debian')) {
      repoString = buildPpaRepo();
    } else if (osMatches(selectedOS, 'Fedora', 'RHEL', 'CentOS')) {
      repoString = buildCoprRepo();
    } else if (osMatches(selectedOS, 'SUSE', 'openSUSE')) {
      repoString = buildObsRepo();
    } else if (osMatches(selectedOS, 'macOS', 'Darwin')) {
      repoString = buildHomebrewTapRepo();
    } else if (osMatches(selectedOS, 'FreeBSD')) {
      repoString = buildFreeBsdRepo();
    } else if (osMatches(selectedOS, 'NetBSD')) {
      repoString = buildNetBsdRepo();
    } else if (osMatches(selectedOS, 'Windows')) {
      repoString = buildWindowsRepo();
    }

    setConstructedRepo(repoString);
  }, [selectedOS, buildPpaRepo, buildCoprRepo, buildObsRepo, buildHomebrewTapRepo, buildFreeBsdRepo, buildNetBsdRepo, buildWindowsRepo]);

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

  // Check if PM form is valid
  const isPMFormValid = selectedPMOS && selectedOptionalPM;

  // Handle add enabled package manager
  const handleAddEnabledPM = async () => {
    if (!isPMFormValid) return;

    setPmSaving(true);
    try {
      await axiosInstance.post('/api/enabled-package-managers/', {
        os_name: selectedPMOS,
        package_manager: selectedOptionalPM,
      });

      // Reset form
      setSelectedPMOS('');
      setSelectedOptionalPM('');

      // Reload enabled package managers
      await loadEnabledPMs();

      setSnackbarMessage(t('hostDefaults.packageManagerAdded', 'Enabled package manager added successfully'));
      setSnackbarSeverity('success');
      setSnackbarOpen(true);
    } catch (err: unknown) {
      console.error('Error adding enabled package manager:', err);
      const errorMessage = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
        t('hostDefaults.errorAddingPackageManager', 'Failed to add enabled package manager');
      setSnackbarMessage(errorMessage);
      setSnackbarSeverity('error');
      setSnackbarOpen(true);
    } finally {
      setPmSaving(false);
    }
  };

  // Handle delete enabled package manager
  const handleDeleteEnabledPM = async (pmId: string) => {
    try {
      await axiosInstance.delete(`/api/enabled-package-managers/${pmId}`);

      // Reload enabled package managers
      await loadEnabledPMs();

      setSnackbarMessage(t('hostDefaults.packageManagerDeleted', 'Enabled package manager removed successfully'));
      setSnackbarSeverity('success');
      setSnackbarOpen(true);
    } catch (err: unknown) {
      console.error('Error removing enabled package manager:', err);
      const errorMessage = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
        t('hostDefaults.errorDeletingPackageManager', 'Failed to remove enabled package manager');
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

  // Sort OS names using localeCompare for proper alphabetical ordering
  const sortedOSNames = Object.keys(groupedRepositories).sort((a, b) => a.localeCompare(b));

  // Render repository items for a given OS and package manager
  const renderRepositoryItems = (osName: string, packageManager: string) => (
    groupedRepositories[osName][packageManager].map((repo) => (
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
    ))
  );

  // Group enabled package managers by OS
  const groupedEnabledPMs: Record<string, EnabledPackageManager[]> = enabledPMs.reduce((acc, pm) => {
    if (!acc[pm.os_name]) {
      acc[pm.os_name] = [];
    }
    acc[pm.os_name].push(pm);
    return acc;
  }, {} as Record<string, EnabledPackageManager[]>);

  // Sort PM OS names using localeCompare for proper alphabetical ordering
  const sortedPMOSNames = Object.keys(groupedEnabledPMs).sort((a, b) => a.localeCompare(b));

  if (!canView && !canViewPM) {
    return (
      <Alert severity="warning">
        {t('hostDefaults.noViewPermissionAll', 'You do not have permission to view host default settings.')}
      </Alert>
    );
  }

  const renderEnabledPMItem = (pm: EnabledPackageManager) => (
    <Box
      key={pm.id}
      sx={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        py: 1,
        px: 2,
        bgcolor: 'action.hover',
        borderRadius: 1,
        mb: 1,
      }}
    >
      <Typography variant="body2" sx={{ fontWeight: 500 }}>
        {pm.package_manager}
      </Typography>
      {canRemovePM && (
        <IconButton
          size="small"
          color="error"
          onClick={() => handleDeleteEnabledPM(pm.id)}
          title={t('common.delete', 'Delete')}
        >
          <DeleteIcon />
        </IconButton>
      )}
    </Box>
  );

  return (
    <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 3 }}>
      <Card sx={{ flex: '1 1 400px', maxWidth: { xs: '100%', lg: '49%' } }}>
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
                {selectedPackageManager && !/Ubuntu|Debian|Fedora|RHEL|CentOS|SUSE|openSUSE|macOS|Darwin|FreeBSD|NetBSD|Windows/.test(selectedOS) && (
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

          {(() => {
            if (loading) {
              return (
                <Box sx={{ display: 'flex', justifyContent: 'center', py: 4 }}>
                  <CircularProgress />
                </Box>
              );
            }
            if (repositories.length === 0) {
              return (
                <Alert severity="info">
                  {t('hostDefaults.noRepositories', 'No default repositories configured. Add repositories above to have them automatically applied to new hosts.')}
                </Alert>
              );
            }
            return (
              <Box>
                {sortedOSNames.map((osName) => (
                  <Box key={osName} sx={{ mb: 3 }}>
                    <Typography variant="h6" sx={{ mb: 1, color: 'primary.main' }}>
                      {osName}
                    </Typography>
                    {Object.keys(groupedRepositories[osName]).sort((a, b) => a.localeCompare(b)).map((packageManager) => (
                      <Box key={`${osName}-${packageManager}`} sx={{ ml: 2, mb: 2 }}>
                        <Typography variant="subtitle2" sx={{ mb: 1, fontWeight: 'bold' }}>
                          {packageManager}
                        </Typography>
                        {renderRepositoryItems(osName, packageManager)}
                      </Box>
                    ))}
                  </Box>
                ))}
              </Box>
            );
          })()}
        </CardContent>
      </Card>

      {/* Enabled Package Managers Card */}
      {canViewPM && (
        <Card sx={{ flex: '1 1 400px', maxWidth: { xs: '100%', lg: '49%' } }}>
          <CardHeader
            avatar={<SettingsIcon color="primary" />}
            title={t('hostDefaults.packageManagersTitle', 'Package Managers')}
            subheader={t('hostDefaults.packageManagersSubheader', 'Enable additional (non-default) package managers for specific operating systems')}
          />
          <CardContent>
            {pmError && (
              <Alert severity="error" sx={{ mb: 2 }}>
                {pmError}
              </Alert>
            )}

            {/* Add Enabled Package Manager Form */}
            {canAddPM && (
              <Box sx={{ mb: 3 }}>
                <Typography variant="subtitle1" sx={{ mb: 2 }}>
                  {t('hostDefaults.addNewPackageManager', 'Add New Package Manager')}
                </Typography>
                <Stack spacing={2}>
                  <Stack direction={{ xs: 'column', md: 'row' }} spacing={2} alignItems="flex-start">
                    <FormControl sx={{ minWidth: 200 }}>
                      <InputLabel>{t('hostDefaults.operatingSystem', 'Operating System')}</InputLabel>
                      <Select
                        value={selectedPMOS}
                        label={t('hostDefaults.operatingSystem', 'Operating System')}
                        onChange={(e) => setSelectedPMOS(e.target.value)}
                      >
                        {pmOSOptions.map((os) => (
                          <MenuItem key={os} value={os}>
                            {os}
                          </MenuItem>
                        ))}
                      </Select>
                    </FormControl>

                    <FormControl sx={{ minWidth: 180 }} disabled={!selectedPMOS || availableOptionalPMs.length === 0}>
                      <InputLabel>{t('hostDefaults.packageManager', 'Package Manager')}</InputLabel>
                      <Select
                        value={availableOptionalPMs.includes(selectedOptionalPM) ? selectedOptionalPM : ''}
                        label={t('hostDefaults.packageManager', 'Package Manager')}
                        onChange={(e) => setSelectedOptionalPM(e.target.value)}
                      >
                        {availableOptionalPMs.map((pm) => (
                          <MenuItem key={pm} value={pm}>
                            {pm}
                          </MenuItem>
                        ))}
                      </Select>
                    </FormControl>

                    <Button
                      variant="contained"
                      startIcon={pmSaving ? <CircularProgress size={20} color="inherit" /> : <AddIcon />}
                      onClick={handleAddEnabledPM}
                      disabled={!isPMFormValid || pmSaving}
                      sx={{ mt: { xs: 0, md: 1 } }}
                    >
                      {t('common.add', 'Add')}
                    </Button>
                  </Stack>

                  {/* Show default package manager info */}
                  {selectedPMOS && pmDefaultManagers[selectedPMOS] && (
                    <Alert severity="info" sx={{ mt: 1 }}>
                      {t('hostDefaults.defaultPackageManagerInfo', 'Default package manager for {{os}}: {{pm}}', {
                        os: selectedPMOS,
                        pm: pmDefaultManagers[selectedPMOS],
                      })}
                    </Alert>
                  )}

                  {/* Show message if no optional package managers available */}
                  {selectedPMOS && availableOptionalPMs.length === 0 && (
                    <Alert severity="warning" sx={{ mt: 1 }}>
                      {t('hostDefaults.noOptionalPackageManagers', 'No additional package managers available for this operating system.')}
                    </Alert>
                  )}
                </Stack>
              </Box>
            )}

            <Divider sx={{ my: 2 }} />

            {/* Enabled Package Manager List */}
            <Typography variant="subtitle1" sx={{ mb: 2 }}>
              {t('hostDefaults.configuredPackageManagers', 'Configured Package Managers')}
            </Typography>

            {(() => {
              if (pmLoading) {
                return (
                  <Box sx={{ display: 'flex', justifyContent: 'center', py: 4 }}>
                    <CircularProgress />
                  </Box>
                );
              }
              if (enabledPMs.length === 0) {
                return (
                  <Alert severity="info">
                    {t('hostDefaults.noPackageManagers', 'No additional package managers enabled. Each operating system uses its default package manager. Add optional package managers above to enable them.')}
                  </Alert>
                );
              }
              return (
                <Box>
                  {sortedPMOSNames.map((osName) => (
                    <Box key={osName} sx={{ mb: 3 }}>
                      <Typography variant="h6" sx={{ mb: 1, color: 'primary.main' }}>
                        {osName}
                      </Typography>
                      <Box sx={{ ml: 2 }}>
                        {pmDefaultManagers[osName] && (
                          <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
                            {t('hostDefaults.defaultLabel', 'Default')}: {pmDefaultManagers[osName]}
                          </Typography>
                        )}
                        {groupedEnabledPMs[osName].map(renderEnabledPMItem)}
                      </Box>
                    </Box>
                  ))}
                </Box>
              );
            })()}
          </CardContent>
        </Card>
      )}

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
