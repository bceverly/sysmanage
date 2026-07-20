// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

import React from 'react';
import {
  Box,
  Typography,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
  TextField,
  Stack,
} from '@mui/material';
import { useTranslation } from 'react-i18next';

interface RepositoryOSFieldsProps {
  selectedOS: string;
  selectedPackageManager: string;
  constructedRepo: string;
  repositoryUrl: string;
  setRepositoryUrl: (value: string) => void;

  ppaOwner: string;
  setPpaOwner: (value: string) => void;
  ppaName: string;
  setPpaName: (value: string) => void;

  coprOwner: string;
  setCoprOwner: (value: string) => void;
  coprProject: string;
  setCoprProject: (value: string) => void;

  obsUrl: string;
  setObsUrl: (value: string) => void;
  obsProjectPath: string;
  setObsProjectPath: (value: string) => void;
  obsDistroVersion: string;
  setObsDistroVersion: (value: string) => void;
  obsRepoName: string;
  setObsRepoName: (value: string) => void;

  tapUser: string;
  setTapUser: (value: string) => void;
  tapRepo: string;
  setTapRepo: (value: string) => void;

  pkgRepoName: string;
  setPkgRepoName: (value: string) => void;
  pkgRepoUrl: string;
  setPkgRepoUrl: (value: string) => void;

  pkgsrcName: string;
  setPkgsrcName: (value: string) => void;
  pkgsrcUrl: string;
  setPkgsrcUrl: (value: string) => void;

  windowsRepoType: string;
  setWindowsRepoType: (value: string) => void;
  windowsRepoName: string;
  setWindowsRepoName: (value: string) => void;
  windowsRepoUrl: string;
  setWindowsRepoUrl: (value: string) => void;
}

/**
 * The OS-specific repository-construction fields for the "Add default
 * repository" form.  Purely presentational: all field values and
 * setters are supplied by the parent so state ownership stays put.
 */
const RepositoryOSFields: React.FC<RepositoryOSFieldsProps> = (props) => {
  const { t } = useTranslation();
  const { selectedOS, selectedPackageManager, constructedRepo, repositoryUrl, setRepositoryUrl } = props;

  return (
    <>
      {/* Ubuntu/Debian PPA Fields */}
      {(selectedOS.includes('Ubuntu') || selectedOS.includes('Debian')) && (
        <Stack direction="row" spacing={2}>
          <TextField
            fullWidth
            label={t('thirdPartyRepos.ppaOwner', 'PPA Owner')}
            value={props.ppaOwner}
            onChange={(e) => props.setPpaOwner(e.target.value)}
            placeholder={t('thirdPartyRepos.ppaOwnerPlaceholder', 'e.g., bceverly')}
          />
          <TextField
            fullWidth
            label={t('thirdPartyRepos.ppaName', 'PPA Name')}
            value={props.ppaName}
            onChange={(e) => props.setPpaName(e.target.value)}
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
            value={props.coprOwner}
            onChange={(e) => props.setCoprOwner(e.target.value)}
            placeholder={t('thirdPartyRepos.coprOwnerPlaceholder', 'e.g., @dotnet-sig')}
          />
          <TextField
            fullWidth
            label={t('thirdPartyRepos.coprProject', 'COPR Project')}
            value={props.coprProject}
            onChange={(e) => props.setCoprProject(e.target.value)}
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
            value={props.obsUrl}
            onChange={(e) => props.setObsUrl(e.target.value)}
            placeholder="https://download.opensuse.org/repositories/"
          />
          <TextField
            fullWidth
            label={t('thirdPartyRepos.obsProjectPath', 'Project Path')}
            value={props.obsProjectPath}
            onChange={(e) => props.setObsProjectPath(e.target.value)}
            placeholder="home:/username:/project"
          />
          <Stack direction="row" spacing={2}>
            <TextField
              fullWidth
              label={t('thirdPartyRepos.obsDistroVersion', 'Distribution/Version')}
              value={props.obsDistroVersion}
              onChange={(e) => props.setObsDistroVersion(e.target.value)}
              placeholder="openSUSE_Tumbleweed"
            />
            <TextField
              fullWidth
              label={t('thirdPartyRepos.obsRepoName', 'Repository Name')}
              value={props.obsRepoName}
              onChange={(e) => props.setObsRepoName(e.target.value)}
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
            value={props.tapUser}
            onChange={(e) => props.setTapUser(e.target.value)}
            placeholder="homebrew"
          />
          <TextField
            fullWidth
            label={t('thirdPartyRepos.tapRepo', 'Tap Repository')}
            value={props.tapRepo}
            onChange={(e) => props.setTapRepo(e.target.value)}
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
            value={props.pkgRepoName}
            onChange={(e) => props.setPkgRepoName(e.target.value)}
            placeholder="custom-repo"
          />
          <TextField
            fullWidth
            label={t('thirdPartyRepos.pkgRepoUrl', 'Repository URL')}
            value={props.pkgRepoUrl}
            onChange={(e) => props.setPkgRepoUrl(e.target.value)}
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
            value={props.pkgsrcName}
            onChange={(e) => props.setPkgsrcName(e.target.value)}
            placeholder="custom-pkgsrc"
          />
          <TextField
            fullWidth
            label={t('thirdPartyRepos.pkgsrcUrl', 'Repository URL')}
            value={props.pkgsrcUrl}
            onChange={(e) => props.setPkgsrcUrl(e.target.value)}
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
              value={props.windowsRepoType}
              label={t('thirdPartyRepos.windowsRepoType', 'Repository Type')}
              onChange={(e) => props.setWindowsRepoType(e.target.value)}
            >
              {/* eslint-disable i18next/no-literal-string -- package manager brand names */}
              <MenuItem value="chocolatey">Chocolatey</MenuItem>
              <MenuItem value="scoop">Scoop</MenuItem>
              {/* eslint-enable i18next/no-literal-string */}
            </Select>
          </FormControl>
          <TextField
            fullWidth
            label={t('thirdPartyRepos.windowsRepoName', 'Repository Name')}
            value={props.windowsRepoName}
            onChange={(e) => props.setWindowsRepoName(e.target.value)}
            placeholder="custom-repo"
          />
          <TextField
            fullWidth
            label={t('thirdPartyRepos.windowsRepoUrl', 'Repository URL')}
            value={props.windowsRepoUrl}
            onChange={(e) => props.setWindowsRepoUrl(e.target.value)}
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
    </>
  );
};

export default RepositoryOSFields;
