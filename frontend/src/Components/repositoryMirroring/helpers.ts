// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

import {
  MirrorPlatform,
  MirrorRepository,
  MirrorRepositoryCreate,
} from '../../Services/repositoryMirroring';

// Phase 10.4.3: each tab is one PM, so the package_manager dropdown
// drops out of the Add Mirror dialog — the platform === the PM.

// Match a host's reported platform/release strings against the
// distro family that natively runs the given PM.  Hosts that don't
// match are filtered out of the picker so an Ubuntu host doesn't
// show up under the RHEL/Fedora tab (where ``dnf`` mirroring would
// be meaningless).  We look at ``platform_release`` because it
// carries either a friendly distro name (``Ubuntu 26.04``) or the
// kernel uname (``5.15.0-...el9uek...``) — the ``.el`` substring
// is the canonical RHEL-family marker in kernel strings, which is
// how Linux distros tag their kernel package builds.
export const hostMatchesPm = (
  host: { platform: string | null; platform_release?: string | null },
  pm: MirrorPlatform,
): boolean => {
  const platform = (host.platform || '').toLowerCase();
  const release = (host.platform_release || '').toLowerCase();
  if (pm === 'pkg') return platform === 'freebsd';
  if (platform !== 'linux') return false;
  if (pm === 'apt') return /\b(ubuntu|debian|mint|kali|raspbian|pop!_os|elementary)\b/.test(release);
  if (pm === 'dnf') {
    return (
      /\.el\d/.test(release) ||  // kernel uname tag, e.g. el9, el8
      /\.fc\d/.test(release) ||  // Fedora kernel tag
      /\b(rhel|red hat|fedora|oracle linux|rocky|alma|centos|amazon linux|amzn)\b/.test(release)
    );
  }
  if (pm === 'zypper') {
    return /\b(opensuse|suse|sled|sles)\b/.test(release);
  }
  return false;
};

export interface HostSummary {
  id: string;
  fqdn: string;
  platform: string | null;
  platform_release: string | null;
}

// Client-side mirror of the engine's ``validate_mirror_config``
// — returns true when every server-required field is populated for
// the draft's package_manager.  Drives the Save button's disabled
// state so the user can never submit a payload that would 400.
//
// Keep this in lock-step with
// ``repository_mirroring_engine.pyx::validate_mirror_config``:
//   * name, host_id, upstream_url required for every PM
//   * apt:    suite + components required
//   * dnf:    repoid required
//   * zypper: repo_alias required
//   * pkg:    no extra required fields
export const isDraftValid = (draft: MirrorRepositoryCreate): boolean => {
  if (!draft.name?.trim()) return false;
  if (!draft.host_id) return false;
  if (!draft.upstream_url?.trim()) return false;
  switch (draft.package_manager) {
    case 'apt':
      return !!draft.suite?.trim() && !!draft.components?.trim();
    case 'dnf':
      return !!draft.repoid?.trim();
    case 'zypper':
      return !!draft.repo_alias?.trim();
    case 'pkg':
      return true;
    default:
      return false;
  }
};

export const EMPTY_DRAFT_FOR = (
  pm: MirrorRepository['package_manager'],
): MirrorRepositoryCreate => ({
  name: '',
  package_manager: pm,
  upstream_url: '',
  host_id: '',
  bandwidth_cap_kbps: 0,
  sync_cron: '0 4 * * *',
  enabled: true,
  // apt sources MUST have at least one component (the engine's
  // ``validate_mirror_config`` rejects empty components with
  // "apt mirror requires non-empty components"), and ``main``
  // is universally the safe default — covers the canonical
  // Ubuntu/Debian-officially-supported subset.  Other PMs don't
  // use components at all, so leave undefined.
  components: pm === 'apt' ? 'main' : undefined,
});

// Friendly platform-family labels shared across the empty-state and
// no-eligible-hosts prompts.
export const PLATFORM_FAMILY_LABEL: Record<MirrorPlatform, string> = {
  apt: 'Ubuntu/Debian',
  dnf: 'RHEL/Fedora',
  zypper: 'openSUSE/SLES',
  pkg: 'FreeBSD',
} as const;

export const formatElapsed = (since: Date): string => {
  const ms = Date.now() - since.getTime();
  if (ms < 60_000) return `${Math.max(1, Math.round(ms / 1000))}s`;
  if (ms < 3_600_000) return `${Math.round(ms / 60_000)}m`;
  return `${Math.round(ms / 3_600_000)}h`;
};

export const formatBytes = (bytes: number | null | undefined): string => {
  if (bytes == null) return '—';
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 ** 2) return `${(bytes / 1024).toFixed(1)} KB`;
  if (bytes < 1024 ** 3) return `${(bytes / 1024 ** 2).toFixed(1)} MB`;
  return `${(bytes / 1024 ** 3).toFixed(2)} GB`;
};
