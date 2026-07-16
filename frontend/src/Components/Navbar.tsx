import React, { useState, useEffect } from "react";
import { NavLink, useNavigate, useLocation } from "react-router-dom";
import { IoClose, IoMenu, IoChevronDown, IoSearch } from "react-icons/io5";
import * as Menubar from "@radix-ui/react-menubar";
import { useTranslation } from 'react-i18next';
import { IconButton } from '@mui/material';
import "./css/Navbar.css";
import "./css/MenuBar.css";
import SysManageLogo from "../assets/sysmanage-logo.svg";
import LanguageSelector from "./LanguageSelector";
import ConnectionStatusIndicator from "./ConnectionStatusIndicator";
import UserProfileDropdown from "./UserProfileDropdown";
import { useFederationLicensed } from "../Services/federation";
import NotificationBell from "./NotificationBell";
import { refreshLicenseCache } from "../Services/license";
import { fetchUserPermissions, hasPermissionSync } from "../Services/permissions";
import { usePlugins } from "../plugins";

// --- Grouped "File-menu"-style navigation ---------------------------------
// The flat nav grew to ~20 destinations and got unwieldy, so the left nav is
// now a Radix menubar: non-navigating top-level CATEGORIES whose dropdown items
// are the real destinations.  Categories auto-hide when the user is licensed for
// none of their children.  On mobile the same categories render as grouped
// sections inside the slide-in drawer.
const CATEGORY_ORDER = [
  'fleet',
  'patching',
  'security',
  'automation',
  'insights',
  'admin',
] as const;
type CategoryId = (typeof CATEGORY_ORDER)[number];

const CATEGORY_META: Record<CategoryId, { key: string; def: string }> = {
  fleet: { key: 'nav.cat.fleet', def: 'Fleet' },
  patching: { key: 'nav.cat.patching', def: 'Patching' },
  security: { key: 'nav.cat.security', def: 'Security' },
  automation: { key: 'nav.cat.automation', def: 'Automation' },
  insights: { key: 'nav.cat.insights', def: 'Insights' },
  admin: { key: 'nav.cat.admin', def: 'Administration' },
};

// Map a nav path to its category.  Unmapped (e.g. a new Pro+ plugin) paths fall
// back to "insights" so nothing silently disappears from the bar.
const PATH_CATEGORY: Record<string, CategoryId> = {
  '/hosts': 'fleet',
  '/map': 'fleet',
  '/sites': 'fleet',
  '/tenants': 'fleet',
  '/airgap/repositories': 'fleet',
  '/airgap/collections': 'fleet',
  '/updates': 'patching',
  '/advisories': 'patching',
  '/os-lifecycle': 'patching',
  '/os-upgrades': 'patching',
  '/maintenance-windows': 'patching',
  '/vulnerabilities': 'security',
  '/compliance': 'security',
  '/fips-compliance': 'security',
  '/alerts': 'security',
  '/secrets': 'security',
  '/gpg-keys': 'security',
  '/scripts': 'automation',
  '/custom-metrics': 'automation',
  '/reports': 'insights',
  '/audit-analytics': 'insights',
  '/secrets-analytics': 'insights',
  '/container-analytics': 'insights',
  '/health': 'insights',
  '/users': 'admin',
  '/settings': 'admin',
};

// Nav destinations that require a specific security ROLE to be usable. A user
// who lacks the role has the item hidden outright — a menu entry that would
// only 403 on click should never be shown. Keyed path -> role name (the backend
// SecurityRoles value returned by /api/v1/user/permissions). A Map keeps the
// dynamic lookup clear of the detect-object-injection lint rule.
const PATH_PERMISSION = new Map<string, string>([
  ['/custom-metrics', 'Manage Custom Metrics'],
]);

interface NavLeaf {
  path: string;
  label: string;
}

const Navbar = () => {
  const [showMenu, setShowMenu] = useState(false);
  const { t } = useTranslation();
  // Phase 12.3: hide the Sites link entirely when the federation
  // controller engine isn't loaded.  The Sites page itself remains
  // reachable by direct URL (where it shows the Enterprise upsell),
  // but it's not surfaced via the nav for OSS / unlicensed users.
  const { licensed: federationLicensed } = useFederationLicensed();
  const navigate = useNavigate();
  const location = useLocation();
  const { navItems, navbarWidgets } = usePlugins();
  const [activeLicenseFeatures, setActiveLicenseFeatures] = useState<string[]>([]);
  const [activeLicenseModules, setActiveLicenseModules] = useState<string[]>([]);
  // Bumped once the caller's security-role permissions load, to re-render the
  // nav with any role-gated destinations now resolvable.
  const [, setPermissionsVersion] = useState(0);
  // Phase 11 — server role chip ("Collector" / "Repository").  Hidden on
  // ``standard`` deployments so the OSS UI stays uncluttered.
  const [serverRole, setServerRole] = useState<string>("standard");
  const [roleEngineLoaded, setRoleEngineLoaded] = useState<boolean>(true);
  // Phase 12 — federation role chip ("Coordinator" / "Site").  Independent
  // axis from the air-gap role above; hidden when federation_role is "none".
  const [federationRole, setFederationRole] = useState<string>("none");
  const [federationEngineLoaded, setFederationEngineLoaded] =
    useState<boolean>(true);

  // Refresh the license cache (shared with HostDetail / Hosts / Settings via
  // ``getCachedLicense``) and mirror the result into local state so this
  // component re-renders when it changes.
  useEffect(() => {
    const checkLicenseFeatures = async () => {
      try {
        const licenseInfo = await refreshLicenseCache();
        if (licenseInfo?.active) {
          setActiveLicenseFeatures(licenseInfo.features ?? []);
          setActiveLicenseModules(licenseInfo.modules ?? []);
        } else {
          setActiveLicenseFeatures([]);
          setActiveLicenseModules([]);
        }
      } catch {
        setActiveLicenseFeatures([]);
        setActiveLicenseModules([]);
      }
    };

    if (localStorage.getItem('bearer_token')) {
      checkLicenseFeatures();
    }
  }, []);

  // Load the caller's security-role permissions so the nav can HIDE
  // destinations they can't use (RBAC nav). ``hasPermissionSync`` reads the
  // module-scope cache this populates; bump local state so the nav re-renders
  // once permissions land. Only when authenticated — no perms pre-login.
  useEffect(() => {
    if (!localStorage.getItem('bearer_token')) return;
    let cancelled = false;
    fetchUserPermissions()
      .then(() => { if (!cancelled) setPermissionsVersion(v => v + 1); })
      .catch(() => { /* leave role-gated items hidden if perms can't load */ });
    return () => { cancelled = true; };
  }, []);

  // Phase 11 — fetch the server-info once on mount so we can render the
  // role chip.  Only fetch when authenticated: the air-gap role is
  // operator-facing detail that must not leak to a pre-login visitor.
  useEffect(() => {
    if (!localStorage.getItem('bearer_token')) return;
    let cancelled = false;
    fetch('/api/v1/server-info')
      .then(r => (r.ok ? r.json() : null))
      .then(info => {
        if (cancelled || !info) return;
        setServerRole(info.role || 'standard');
        setRoleEngineLoaded(Boolean(info.role_engine_loaded));
        setFederationRole(info.federation_role || 'none');
        setFederationEngineLoaded(Boolean(info.federation_engine_loaded));
      })
      .catch(() => {
        // Endpoint may not be reachable yet during cold-start; default
        // to standard so we don't render a stale chip.
      });
    return () => { cancelled = true; };
  }, []);

  const toggleMenu = () => setShowMenu(v => !v);
  const closeMenuOnMobile = () => {
    if (window.innerWidth <= 1150) setShowMenu(false);
  };

  const menuVisible = localStorage.getItem('bearer_token') ? 'visible' : 'hidden';

  // Paths hardcoded here — plugins must not duplicate these.
  const hardcodedPaths = new Set(['/', '/hosts', '/users', '/updates', '/os-upgrades', '/maintenance-windows', '/secrets', '/scripts', '/reports', '/airgap/repositories', '/airgap/collections']);
  const hardcodedLabels = new Set([
    t('nav.secrets'),
    t('nav.scripts'),
    t('nav.reports'),
  ]);

  // Plugin nav items, gated by feature flag and de-duplicated vs. hardcoded nav.
  const visiblePluginNavItems = navItems.filter(item => {
    if (hardcodedPaths.has(item.path)) return false;
    if (hardcodedLabels.has(t(item.labelKey))) return false;
    if (!item.featureFlag) return true;
    return activeLicenseFeatures.includes(item.featureFlag);
  });

  // Build the visible leaf destinations (hardcoded + plugin), each already
  // gated, then group them into ordered categories.
  const leaves: NavLeaf[] = [];
  const pushIf = (cond: boolean, path: string, label: string) => {
    if (cond) leaves.push({ path, label });
  };
  pushIf(true, '/hosts', t('nav.hosts'));
  pushIf(true, '/map', t('nav.map'));
  pushIf(federationLicensed, '/sites', t('nav.sites'));
  pushIf(true, '/updates', t('nav.updates'));
  pushIf(true, '/os-upgrades', t('nav.osUpgrades'));
  pushIf(true, '/maintenance-windows', t('nav.maintenanceWindows'));
  pushIf(
    activeLicenseModules.includes('secrets_engine'),
    '/secrets',
    t('nav.secrets'),
  );
  pushIf(true, '/scripts', t('nav.scripts'));
  pushIf(
    activeLicenseModules.includes('reporting_engine') &&
      activeLicenseFeatures.includes('reports'),
    '/reports',
    t('nav.reports'),
  );
  pushIf(
    serverRole === 'repository' &&
      activeLicenseModules.includes('airgap_repository_engine'),
    '/airgap/repositories',
    t('nav.airgapRepositories', 'Air-Gap Repos'),
  );
  pushIf(
    serverRole === 'collector' &&
      activeLicenseModules.includes('airgap_collector_engine'),
    '/airgap/collections',
    t('nav.airgapCollections', 'Air-Gap Collections'),
  );
  pushIf(true, '/users', t('nav.users'));
  pushIf(true, '/settings', t('nav.settings', 'Settings'));
  for (const item of visiblePluginNavItems) {
    leaves.push({ path: item.path, label: t(item.labelKey) });
  }

  const grouped: Record<CategoryId, NavLeaf[]> = {
    fleet: [], patching: [], security: [], automation: [], insights: [], admin: [],
  };
  // RBAC nav: drop destinations the user lacks the required security role for,
  // so an unusable item is hidden entirely rather than shown then 403'd.
  const accessibleLeaves = leaves.filter(leaf => {
    const requiredRole = PATH_PERMISSION.get(leaf.path);
    return !requiredRole || hasPermissionSync(requiredRole);
  });
  for (const leaf of accessibleLeaves) {
    grouped[PATH_CATEGORY[leaf.path] ?? 'insights'].push(leaf);
  }
  const categories = CATEGORY_ORDER
    .map(id => ({
      id,
      label: t(CATEGORY_META[id].key, CATEGORY_META[id].def),
      items: grouped[id],
    }))
    .filter(c => c.items.length > 0);

  const isItemActive = (path: string) =>
    location.pathname === path || location.pathname.startsWith(path + '/');
  const isCategoryActive = (items: NavLeaf[]) =>
    items.some(i => isItemActive(i.path));

  // Phase 11 role chip — only renders when this is half of an air-gap pair.
  const roleLabelFallback =
    serverRole === 'collector' ? 'Air-Gap Collector' : 'Air-Gapped Repository';
  const roleLabelText = t(`nav.role.${serverRole}`, roleLabelFallback);
  const tooltipText = roleEngineLoaded
    ? roleLabelText
    : t('nav.role.engineMissing', 'Required Pro+ engine not loaded; check license.');
  const roleChip = (serverRole === 'standard' || menuVisible !== 'visible') ? null : (
    <span
      className={`nav__role-chip nav__role-chip--${serverRole}` +
        (roleEngineLoaded ? '' : ' nav__role-chip--degraded')}
      title={tooltipText}
    >
      {roleLabelText}
    </span>
  );

  // Phase 12 federation chip — independent of the air-gap chip above.
  const federationLabelFallback =
    federationRole === 'coordinator' ? 'Federation Coordinator' : 'Federation Site';
  const federationLabelText = t(`nav.federationRole.${federationRole}`, federationLabelFallback);
  const federationTooltip = federationEngineLoaded
    ? federationLabelText
    : t('nav.federationRole.engineMissing', 'Required Pro+ federation engine not loaded; check license.');
  const federationChip = (federationRole === 'none' || menuVisible !== 'visible') ? null : (
    <span
      className={`nav__role-chip nav__federation-chip nav__federation-chip--${federationRole}` +
        (federationEngineLoaded ? '' : ' nav__role-chip--degraded')}
      title={federationTooltip}
    >
      {federationLabelText}
    </span>
  );

  // Render nothing at all on the pre-auth screens (login / reset-password /
  // accept-invitation) OR whenever there's no session, so the app-shell bar
  // (logo + menubar) never appears over the login form. The route check is the
  // authoritative one: a stale bearer_token can linger in localStorage on
  // /login, so gating on the token alone would still leak the bar. All hooks
  // above run unconditionally, so this early return is safe.
  const preAuthPaths = ['/login', '/reset-password', '/accept-invitation'];
  if (preAuthPaths.includes(location.pathname) || menuVisible !== 'visible') {
    return null;
  }

  return (
    <header className="header">
      <nav className="nav container">
        <NavLink to="/" className="nav__logo">
          <img src={SysManageLogo} alt={t('nav.logoAlt', 'SysManage')} className="nav__logo-img" />
          {roleChip}
          {federationChip}
        </NavLink>

        {menuVisible === 'visible' && (
          <>
            {/* Desktop: grouped Radix menubar (categories don't navigate). */}
            <Menubar.Root className="nav__menubar">
              {categories.map(cat => (
                <Menubar.Menu key={cat.id}>
                  <Menubar.Trigger
                    className={
                      'menubar__trigger' +
                      (isCategoryActive(cat.items) ? ' menubar__trigger--active' : '')
                    }
                  >
                    {cat.label}
                    <IoChevronDown className="menubar__caret" aria-hidden="true" />
                  </Menubar.Trigger>
                  <Menubar.Portal>
                    <Menubar.Content
                      className="menubar__content"
                      align="start"
                      sideOffset={8}
                    >
                      {cat.items.map(item => (
                        <Menubar.Item
                          key={item.path}
                          className={
                            'menubar__item' +
                            (isItemActive(item.path) ? ' menubar__item--active' : '')
                          }
                          onSelect={() => navigate(item.path)}
                        >
                          {item.label}
                        </Menubar.Item>
                      ))}
                    </Menubar.Content>
                  </Menubar.Portal>
                </Menubar.Menu>
              ))}
            </Menubar.Root>

            {/* Mobile: same categories as grouped sections in a slide-in drawer. */}
            <div
              className={`nav__drawer ${showMenu ? 'show-menu' : ''}`}
              id="nav-menu"
            >
              <ul className="nav__mobile-list">
                {categories.map(cat => (
                  <li key={cat.id} className="nav__mobile-group">
                    <span className="nav__mobile-group-title">{cat.label}</span>
                    {cat.items.map(item => (
                      <NavLink
                        key={item.path}
                        to={item.path}
                        className="nav__link nav__mobile-link"
                        onClick={closeMenuOnMobile}
                      >
                        {item.label}
                      </NavLink>
                    ))}
                  </li>
                ))}
              </ul>
              <button
                className="nav__close"
                id="nav-close"
                onClick={toggleMenu}
                aria-label={t('nav.closeMenu', 'Close menu')}
                type="button"
              >
                <IoClose />
              </button>
            </div>
          </>
        )}

        {/* Utility toolbar — language, connection, notifications, account. */}
        {menuVisible === "visible" && (
          <div className="nav__language-toolbar">
            {navbarWidgets
              .filter((w) => {
                if (w.moduleRequired && !activeLicenseModules.includes(w.moduleRequired)) return false;
                if (w.featureFlag && !activeLicenseFeatures.includes(w.featureFlag)) return false;
                return true;
              })
              .map((w) => {
                const Widget = w.component;
                return <Widget key={w.id} />;
              })}
            <IconButton
              onClick={() => window.dispatchEvent(new window.Event('open-command-palette'))}
              size="small"
              title={t('nav.search', 'Search (Ctrl+K)')}
              aria-label={t('nav.search', 'Search (Ctrl+K)')}
              sx={{ color: 'inherit', mr: 0.5 }}
            >
              <IoSearch />
            </IconButton>
            <ConnectionStatusIndicator />
            <NotificationBell />
            <UserProfileDropdown />
            <LanguageSelector />
          </div>
        )}

        {menuVisible === "visible" && (
          <button
            className="nav__toggle"
            id="nav-toggle"
            onClick={toggleMenu}
            aria-label={t('nav.toggleMenu', 'Toggle menu')}
            type="button"
          >
            <IoMenu />
          </button>
        )}
      </nav>
    </header>
  );
};

export default Navbar;
