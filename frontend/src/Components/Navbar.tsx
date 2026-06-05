import React, { useState, useEffect } from "react";
import { NavLink, useNavigate } from "react-router-dom";
import { IoClose, IoMenu, IoSettingsOutline } from "react-icons/io5";
import { useTranslation } from 'react-i18next';
import { IconButton } from '@mui/material';
import "./css/Navbar.css";
import SysManageLogo from "../assets/sysmanage-logo.svg";
import LanguageSelector from "./LanguageSelector";
import ConnectionStatusIndicator from "./ConnectionStatusIndicator";
import UserProfileDropdown from "./UserProfileDropdown";
import { useFederationLicensed } from "../Services/federation";
import NotificationBell from "./NotificationBell";
import ScrollableNavList from "./ScrollableNavList";
import { refreshLicenseCache } from "../Services/license";
import { usePlugins } from "../plugins";

const Navbar = () => {
  const [showMenu, setShowMenu] = useState(false);
  const { t } = useTranslation();
  // Phase 12.3: hide the Sites link entirely when the federation
  // controller engine isn't loaded.  The Sites page itself remains
  // reachable by direct URL (where it shows the Enterprise upsell),
  // but it's not surfaced via the nav for OSS / unlicensed users.
  const { licensed: federationLicensed } = useFederationLicensed();
  const navigate = useNavigate();
  const { navItems } = usePlugins();
  const [activeLicenseFeatures, setActiveLicenseFeatures] = useState<string[]>([]);
  const [activeLicenseModules, setActiveLicenseModules] = useState<string[]>([]);
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

  // Phase 11 — fetch the server-info once on mount so we can render the
  // role chip.  ``/api/v1/server-info`` is unauthenticated, so this works
  // pre-login too (the chip is hidden anyway when role === "standard").
  useEffect(() => {
    // Only fetch role info once authenticated.  The role chip is
    // operator-facing detail; an unauthenticated visitor on the login
    // screen must not be able to learn this server's air-gap role
    // (collector / repository) — that's pre-auth information disclosure.
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

  const toggleMenu = () => {
    setShowMenu(!showMenu);
  };

  const closeMenuOnMobile = () => {
    if (window.innerWidth <= 1150) {
      setShowMenu(false);
    }
  };

  const checkIfLoggedIn = () => {
    if (localStorage.getItem('bearer_token')) {
      return "visible";
    }

    return "hidden";
  };

  const menuVisible = checkIfLoggedIn();

  const handleSettingsClick = () => {
    navigate('/settings');
  };

  // Paths that are hardcoded in the navbar - plugins must not duplicate these
  const hardcodedPaths = new Set(['/', '/hosts', '/users', '/updates', '/os-upgrades', '/secrets', '/scripts', '/reports', '/airgap/repositories', '/airgap/collections']);

  // Labels that are hardcoded in the navbar - plugins with matching labels are duplicates
  const hardcodedLabels = new Set([
    t('nav.secrets'),
    t('nav.scripts'),
    t('nav.reports'),
  ]);

  // Filter plugin nav items by their feature flag and exclude duplicates of hardcoded nav
  const visiblePluginNavItems = navItems.filter(item => {
    if (hardcodedPaths.has(item.path)) return false;
    if (hardcodedLabels.has(t(item.labelKey))) return false;
    if (!item.featureFlag) return true;
    return activeLicenseFeatures.includes(item.featureFlag);
  });

  // Phase 11 role chip — only renders when this is half of an air-gap
  // pair.  Color reflects health: green when the role-specific Pro+ engine
  // is loaded, red when it should be but isn't (license problem).
  // Compute the role-label fallback up front so the JSX has no nested
  // ternaries (SonarQube readability rule).
  const roleLabelFallback =
    serverRole === 'collector' ? 'Air-Gap Collector' : 'Air-Gapped Repository';
  const roleLabelText = t(`nav.role.${serverRole}`, roleLabelFallback);
  const tooltipText = roleEngineLoaded
    ? roleLabelText
    : t('nav.role.engineMissing', 'Required Pro+ engine not loaded; check license.');
  // Never render the role chip pre-login (defense-in-depth alongside the
  // gated fetch above): no air-gap role disclosure to unauthenticated
  // visitors on the login screen.
  const roleChip = (serverRole === 'standard' || menuVisible !== 'visible') ? null : (
    <span
      className={`nav__role-chip nav__role-chip--${serverRole}` +
        (roleEngineLoaded ? '' : ' nav__role-chip--degraded')}
      title={tooltipText}
    >
      {roleLabelText}
    </span>
  );

  // Phase 12 federation chip — independent of the air-gap chip above, so a
  // server that is both shows two chips.  Same health semantics: degraded
  // (red) when the federation Pro+ engine should be loaded but isn't.
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

  return (
    <header className="header">
      <nav className="nav container">
        <NavLink to="/" className="nav__logo">
          <img src={SysManageLogo} alt={t('nav.logoAlt', 'SysManage')} className="nav__logo-img" />
          {roleChip}
          {federationChip}
        </NavLink>

        <div
          className={`nav__menu ${showMenu ? "show-menu" : ""}`}
          id="nav-menu"
          style={{visibility: menuVisible}}
        >
          <ScrollableNavList listClassName="nav__list">
            <li className="nav__item">
              <NavLink
                to="/"
                className="nav__link"
                onClick={closeMenuOnMobile}
                end
              >
                {t('nav.dashboard')}
              </NavLink>
            </li>
            <li className="nav__item">
              <NavLink
                to="/hosts"
                className="nav__link"
                onClick={closeMenuOnMobile}
              >
                {t('nav.hosts')}
              </NavLink>
            </li>
            <li className="nav__item">
              <NavLink
                to="/map"
                className="nav__link"
                onClick={closeMenuOnMobile}
              >
                {t('nav.map')}
              </NavLink>
            </li>
            {federationLicensed && (
              <li className="nav__item">
                <NavLink
                  to="/sites"
                  className="nav__link"
                  onClick={closeMenuOnMobile}
                >
                  {t('nav.sites')}
                </NavLink>
              </li>
            )}
            <li className="nav__item">
              <NavLink
                to="/users"
                className="nav__link"
                onClick={closeMenuOnMobile}
              >
                {t('nav.users')}
              </NavLink>
            </li>
            <li className="nav__item">
              <NavLink
                to="/updates"
                className="nav__link"
                onClick={closeMenuOnMobile}
              >
                {t('nav.updates')}
              </NavLink>
            </li>
            <li className="nav__item">
              <NavLink
                to="/os-upgrades"
                className="nav__link"
                onClick={closeMenuOnMobile}
              >
                {t('nav.osUpgrades')}
              </NavLink>
            </li>
            {visiblePluginNavItems.map(item => (
              <li key={item.path} className="nav__item">
                <NavLink
                  to={item.path}
                  className="nav__link"
                  onClick={closeMenuOnMobile}
                >
                  {t(item.labelKey)}
                </NavLink>
              </li>
            ))}
            {activeLicenseModules.includes('secrets_engine') && (
              <li className="nav__item">
                <NavLink
                  to="/secrets"
                  className="nav__link"
                  onClick={closeMenuOnMobile}
                >
                  {t('nav.secrets')}
                </NavLink>
              </li>
            )}
            <li className="nav__item">
              <NavLink
                to="/scripts"
                className="nav__link"
                onClick={closeMenuOnMobile}
              >
                {t('nav.scripts')}
              </NavLink>
            </li>
            {activeLicenseModules.includes('reporting_engine') && (
              <li className="nav__item">
                <NavLink
                  to="/reports"
                  className="nav__link"
                  onClick={closeMenuOnMobile}
                >
                  {t('nav.reports')}
                </NavLink>
              </li>
            )}
            {serverRole === 'repository' && (
              <li className="nav__item">
                <NavLink
                  to="/airgap/repositories"
                  className="nav__link"
                  onClick={closeMenuOnMobile}
                >
                  {t('nav.airgapRepositories', 'Air-Gap Repos')}
                </NavLink>
              </li>
            )}
            {serverRole === 'collector' &&
              activeLicenseModules.includes('airgap_collector_engine') && (
                <li className="nav__item">
                  <NavLink
                    to="/airgap/collections"
                    className="nav__link"
                    onClick={closeMenuOnMobile}
                  >
                    {t('nav.airgapCollections', 'Air-Gap Collections')}
                  </NavLink>
                </li>
              )}
          </ScrollableNavList>
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

        {/* Language selector, connection status, and notifications at toolbar level - only render when logged in */}
        {menuVisible === "visible" && (
          <div className="nav__language-toolbar">
            <ConnectionStatusIndicator />
            <NotificationBell />
            <IconButton
              onClick={handleSettingsClick}
              size="small"
              title={t('nav.settings', 'Settings')}
              sx={{ color: 'inherit', mr: 1 }}
            >
              <IoSettingsOutline />
            </IconButton>
            <UserProfileDropdown />
            <LanguageSelector />
          </div>
        )}

        <button
            className="nav__toggle"
            id="nav-toggle"
            onClick={toggleMenu}
            aria-label={t('nav.toggleMenu', 'Toggle menu')}
            type="button"
        >
          <IoMenu />
        </button>
      </nav>
    </header>
  );
};

export default Navbar;
