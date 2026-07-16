// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import {
  Dialog,
  TextField,
  List,
  ListItemButton,
  ListItemText,
  Typography,
  Box,
  InputAdornment,
} from '@mui/material';
import { IoSearch } from 'react-icons/io5';
import { getCachedLicense } from '../Services/license';
import { hasPermissionSync } from '../Services/permissions';

// Global "jump to anything" command palette (Cmd/Ctrl-K).  With the nav now
// three levels deep, this is the fast path for keyboard users.  Kept in sync
// with the grouped menubar categories; Pro+ destinations are gated by the same
// license modules/features so a Community user never sees an unreachable entry.
interface Cmd {
  id: string;
  labelKey: string;
  labelDefault: string;
  group: string;
  path: string;
  module?: string;
  feature?: string;
  permission?: string; // required security role name (RBAC nav)
}

const COMMANDS: Cmd[] = [
  { id: 'dashboard', labelKey: 'nav.dashboard', labelDefault: 'Dashboard', group: 'Fleet', path: '/' },
  { id: 'hosts', labelKey: 'nav.hosts', labelDefault: 'Hosts', group: 'Fleet', path: '/hosts' },
  { id: 'map', labelKey: 'nav.map', labelDefault: 'Map', group: 'Fleet', path: '/map' },
  { id: 'updates', labelKey: 'nav.updates', labelDefault: 'Updates', group: 'Patching', path: '/updates' },
  { id: 'advisories', labelKey: 'nav.advisories', labelDefault: 'Advisories', group: 'Patching', path: '/advisories', feature: 'advisory_management' },
  { id: 'os-lifecycle', labelKey: 'nav.osLifecycle', labelDefault: 'OS Lifecycle', group: 'Patching', path: '/os-lifecycle', feature: 'os_lifecycle' },
  { id: 'os-upgrades', labelKey: 'nav.osUpgrades', labelDefault: 'OS Upgrades', group: 'Patching', path: '/os-upgrades' },
  { id: 'maintenance', labelKey: 'nav.maintenanceWindows', labelDefault: 'Maintenance Windows', group: 'Patching', path: '/maintenance-windows' },
  { id: 'vuln', labelKey: 'nav.vulnerabilities', labelDefault: 'Vulnerabilities', group: 'Security', path: '/vulnerabilities', feature: 'vuln' },
  { id: 'compliance', labelKey: 'nav.compliance', labelDefault: 'Compliance', group: 'Security', path: '/compliance', feature: 'compliance' },
  { id: 'fips', labelKey: 'nav.fips', labelDefault: 'FIPS', group: 'Security', path: '/fips-compliance', feature: 'fips_mode' },
  { id: 'alerts', labelKey: 'nav.alerts', labelDefault: 'Alerts', group: 'Security', path: '/alerts', feature: 'alerts' },
  { id: 'secrets', labelKey: 'nav.secrets', labelDefault: 'Secrets', group: 'Security', path: '/secrets', module: 'secrets_engine' },
  { id: 'scripts', labelKey: 'nav.scripts', labelDefault: 'Scripts', group: 'Automation', path: '/scripts' },
  { id: 'custom-metrics', labelKey: 'nav.customMetrics', labelDefault: 'Custom Metrics', group: 'Automation', path: '/custom-metrics', module: 'observability_engine', permission: 'Manage Custom Metrics' },
  { id: 'reports', labelKey: 'nav.reports', labelDefault: 'Reports', group: 'Insights', path: '/reports', module: 'reporting_engine', feature: 'reports' },
  { id: 'users', labelKey: 'nav.users', labelDefault: 'Users', group: 'Administration', path: '/users' },
  { id: 'settings', labelKey: 'nav.settings', labelDefault: 'Settings', group: 'Administration', path: '/settings' },
];

const CommandPalette: React.FC = () => {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState('');
  const [activeIndex, setActiveIndex] = useState(0);

  // Cmd/Ctrl-K toggles; a custom event lets a toolbar button open it too. Only
  // active when authenticated — no jump targets pre-login.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && (e.key === 'k' || e.key === 'K')) {
        if (!localStorage.getItem('bearer_token')) return;
        e.preventDefault();
        setOpen(o => !o);
      }
    };
    const onOpen = () => {
      if (localStorage.getItem('bearer_token')) setOpen(true);
    };
    window.addEventListener('keydown', onKey);
    window.addEventListener('open-command-palette', onOpen);
    return () => {
      window.removeEventListener('keydown', onKey);
      window.removeEventListener('open-command-palette', onOpen);
    };
  }, []);

  // Computed each render (small list) so it always reflects the current license
  // cache — which may populate after mount — and the current query.
  const license = getCachedLicense();
  const modules: string[] = license?.modules ?? [];
  const features: string[] = license?.features ?? [];
  const q = query.trim().toLowerCase();
  const results = COMMANDS.filter(
    c =>
      (!c.module || modules.includes(c.module)) &&
      (!c.feature || features.includes(c.feature)) &&
      (!c.permission || hasPermissionSync(c.permission)),
  )
    .map(c => ({ ...c, label: t(c.labelKey, c.labelDefault) }))
    .filter(
      c => !q || c.label.toLowerCase().includes(q) || c.group.toLowerCase().includes(q),
    );

  // Keep the active row valid as the result set shrinks.
  useEffect(() => {
    setActiveIndex(0);
  }, [query, open]);

  const close = () => {
    setOpen(false);
    setQuery('');
    setActiveIndex(0);
  };

  const run = (cmd: { path: string }) => {
    navigate(cmd.path);
    close();
  };

  const onInputKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      setActiveIndex(i => Math.min(i + 1, Math.max(results.length - 1, 0)));
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setActiveIndex(i => Math.max(i - 1, 0));
    } else if (e.key === 'Enter') {
      e.preventDefault();
      const chosen = results[activeIndex];
      if (chosen) run(chosen);
    }
  };

  return (
    <Dialog
      open={open}
      onClose={close}
      fullWidth
      maxWidth="sm"
      PaperProps={{ sx: { position: 'fixed', top: '12vh', m: 0, borderRadius: 2 } }}
    >
      <Box sx={{ p: 1.5 }}>
        <TextField
          autoFocus
          fullWidth
          size="small"
          value={query}
          onChange={e => setQuery(e.target.value)}
          onKeyDown={onInputKeyDown}
          placeholder={t('commandPalette.placeholder', 'Search pages…  (Esc to close)')}
          InputProps={{
            startAdornment: (
              <InputAdornment position="start">
                <IoSearch />
              </InputAdornment>
            ),
          }}
        />
      </Box>
      <List dense sx={{ maxHeight: '55vh', overflowY: 'auto', pt: 0 }}>
        {results.length === 0 && (
          <Box sx={{ px: 2, py: 1.5 }}>
            <Typography variant="body2" sx={{ opacity: 0.6 }}>
              {t('commandPalette.noResults', 'No matches.')}
            </Typography>
          </Box>
        )}
        {results.map((cmd, idx) => (
          <ListItemButton
            key={cmd.id}
            selected={idx === activeIndex}
            onMouseEnter={() => setActiveIndex(idx)}
            onClick={() => run(cmd)}
          >
            <ListItemText
              primary={cmd.label}
              secondary={cmd.group}
              primaryTypographyProps={{ variant: 'body2' }}
              secondaryTypographyProps={{ variant: 'caption' }}
            />
          </ListItemButton>
        ))}
      </List>
    </Dialog>
  );
};

export default CommandPalette;
