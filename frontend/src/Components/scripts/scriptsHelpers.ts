// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

import { Host, Script } from '../../Services/scripts';

export type ChipColor = 'success' | 'error' | 'warning' | 'info' | 'default';

// Shell catalog shared by the editor + library.  ``label`` is a
// pre-resolved i18n string, so callers pass their own ``t``.
export interface ShellOption {
  value: string;
  label: string;
  platforms: string[];
}

// Returns the shell catalog with translated labels.  Kept as a
// factory (rather than a module constant) because the labels are
// i18n strings resolved against the caller's ``t``.
export const buildAllShells = (
  t: (key: string) => string,
): ShellOption[] => [
  { value: 'bash', label: t('scripts.shells.bash'), platforms: ['linux', 'darwin', 'freebsd', 'openbsd', 'netbsd'] },
  { value: 'sh', label: t('scripts.shells.sh'), platforms: ['linux', 'darwin', 'freebsd', 'openbsd', 'netbsd'] },
  { value: 'zsh', label: t('scripts.shells.zsh'), platforms: ['linux', 'darwin', 'freebsd', 'openbsd', 'netbsd'] },
  { value: 'ksh', label: t('scripts.shells.ksh'), platforms: ['linux', 'darwin', 'freebsd', 'openbsd', 'netbsd'] },
  { value: 'powershell', label: t('scripts.shells.powershell'), platforms: ['windows', 'linux', 'darwin'] },
  { value: 'cmd', label: t('scripts.shells.cmd'), platforms: ['windows'] },
];

// Returns the platform catalog with translated labels.
export const buildPlatforms = (
  t: (key: string) => string,
): Array<{ value: string; label: string }> => [
  { value: 'linux', label: t('scripts.platforms.linux') },
  { value: 'darwin', label: t('scripts.platforms.darwin') },
  { value: 'windows', label: t('scripts.platforms.windows') },
  { value: 'freebsd', label: t('scripts.platforms.freebsd') },
  { value: 'openbsd', label: t('scripts.platforms.openbsd') },
  { value: 'netbsd', label: t('scripts.platforms.netbsd') },
];

// Get shells available for the selected platform
export const getShellsForPlatform = (
  allShells: ShellOption[],
  platform: string,
): ShellOption[] => allShells.filter((shell) => shell.platforms.includes(platform));

// Helper function to normalize platform names to standard values
export const normalizePlatform = (platform: string): string => {
  const lowerPlatform = platform.toLowerCase();
  if (lowerPlatform.startsWith('win')) {
    return 'windows';
  }
  if (lowerPlatform === 'darwin') {
    return 'darwin';
  }
  if (lowerPlatform.includes('bsd')) {
    return lowerPlatform;
  }
  return 'linux'; // Default to linux for other Unix-like systems
};

// Helper function to check if platforms match
export const doPlatformsMatch = (
  scriptPlatform: string | undefined,
  hostPlatform: string | undefined,
): boolean => {
  if (!scriptPlatform || !hostPlatform) {
    return true; // If either is undefined, consider it a match
  }
  return scriptPlatform.toLowerCase() === normalizePlatform(hostPlatform);
};

// Helper function to check if host has the required shell enabled
export const hostHasShellEnabled = (host: Host, shellType: string): boolean => {
  if (!host.enabled_shells) {
    return false;
  }
  try {
    const hostShells = JSON.parse(host.enabled_shells) as string[];
    return hostShells.some((shell) => shell.toLowerCase() === shellType.toLowerCase());
  } catch {
    return false;
  }
};

// Helper function to check if host is compatible with selected script
export const isHostCompatibleWithScript = (host: Host, script: Script): boolean => {
  if (!host.script_execution_enabled) {
    return false;
  }
  if (!doPlatformsMatch(script.platform, host.platform)) {
    return false;
  }
  return hostHasShellEnabled(host, script.shell_type);
};

export const isHostConnected = (host: Host): boolean => {
  // Use the actual status field from the database
  return host.status === 'up' && host.active === true;
};

export const getStatusColor = (status: string): ChipColor => {
  switch (status) {
    case 'pending':
      return 'default';
    case 'running':
      return 'info';
    case 'completed':
      return 'success';
    case 'failed':
      return 'error';
    case 'timeout':
      return 'warning';
    default:
      return 'default';
  }
};

// Shared MUI DataGrid ``localeText`` for the scripts grids — the
// pagination + row-selection strings are identical across the Library
// and Executions tables; only the empty-state label differs.
export const buildDataGridLocaleText = (
  t: (key: string) => string,
  noRowsLabel: string,
) => ({
  MuiTablePagination: {
    labelRowsPerPage: t('common.rowsPerPage'),
    labelDisplayedRows: ({ from, to, count }: { from: number; to: number; count: number }) => {
      const ofLabel = t('common.of');
      const countDisplay = count === -1 ? ofLabel + ' ' + to : count;
      return from + '-' + to + ' ' + ofLabel + ' ' + countDisplay;
    },
  },
  noRowsLabel,
  noResultsOverlayLabel: noRowsLabel,
  footerRowSelected: (count: number) => {
    const countStr = count.toLocaleString();
    return count === 1
      ? countStr + ' ' + t('common.rowSelected')
      : countStr + ' ' + t('common.rowsSelected');
  },
});

export const getLanguageForShell = (shell: string): string => {
  switch (shell) {
    case 'bash':
    case 'sh':
    case 'zsh':
    case 'ksh':
      return 'shell';
    case 'powershell':
      return 'powershell';
    case 'cmd':
      return 'bat';
    default:
      return 'shell';
  }
};

// Get the appropriate shebang/header for a shell type and platform
export const getShellHeader = (shell: string, platform: string): string => {
  switch (shell) {
    case 'bash':
      // bash locations vary by OS
      switch (platform) {
        case 'linux':
        case 'darwin':
          return '#!/bin/bash\n\n';
        case 'freebsd':
        case 'openbsd':
        case 'netbsd':
          return '#!/usr/local/bin/bash\n\n';
        default:
          return '#!/bin/bash\n\n';
      }
    case 'sh':
      // sh is usually in /bin on all Unix-like systems
      return '#!/bin/sh\n\n';
    case 'zsh':
      // zsh locations
      switch (platform) {
        case 'linux':
          return '#!/bin/zsh\n\n';
        case 'darwin':
          return '#!/bin/zsh\n\n';
        case 'freebsd':
        case 'openbsd':
        case 'netbsd':
          return '#!/usr/local/bin/zsh\n\n';
        default:
          return '#!/bin/zsh\n\n';
      }
    case 'ksh':
      // ksh locations
      switch (platform) {
        case 'linux':
          return '#!/bin/ksh\n\n';
        case 'darwin':
          return '#!/bin/ksh\n\n';
        case 'freebsd':
        case 'netbsd':
          return '#!/usr/local/bin/ksh\n\n';
        case 'openbsd':
          return '#!/bin/ksh\n\n'; // ksh is default shell on OpenBSD
        default:
          return '#!/bin/ksh\n\n';
      }
    case 'powershell':
      return '# PowerShell Script\n\n';
    case 'cmd':
      return '@echo off\nREM Windows Batch Script\n\n';
    default:
      return '#!/bin/bash\n\n';
  }
};
