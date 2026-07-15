import './App.css';
import './plugins/SharedDependencies';
import { BrowserRouter as Router, Routes, Route } from "react-router-dom";
import { useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';

import { ThemeProvider, createTheme } from '@mui/material/styles';
import { prefixer } from 'stylis';
import rtlPlugin from 'stylis-plugin-rtl';
import { CacheProvider } from '@emotion/react';
import createCache from '@emotion/cache';
import darkScrollbar from '@mui/material/darkScrollbar';
import CssBaseline from '@mui/material/CssBaseline';
import '@fontsource/roboto/300.css';
import '@fontsource/roboto/400.css';
import '@fontsource/roboto/500.css';
import '@fontsource/roboto/700.css';

import Navbar from "./Components/Navbar"
import ConnectionProvider from './Components/ConnectionProvider';
import SecurityWarningBanner from './Components/SecurityWarningBanner';
import MigrationCompatBanner from './Components/MigrationCompatBanner';
import Login from './Pages/Login';
import ResetPassword from './Pages/ResetPassword';
import AcceptInvitation from './Pages/AcceptInvitation';
import Home from './Pages/Home';
import Hosts from './Pages/Hosts';
import HostDetail from './Pages/HostDetail';
import Users from './Pages/Users';
import UserDetail from './Pages/UserDetail';
import Updates from './Pages/Updates';
import OSUpgrades from './Pages/OSUpgrades';
import MaintenanceWindows from './Pages/MaintenanceWindows';
import Secrets from './Pages/Secrets';
import Scripts from './Pages/Scripts';
import Reports from './Pages/Reports';
import ReportViewer from './Pages/ReportViewer';
import AuditLogViewer from './Pages/AuditLogViewer';
import Profile from './Pages/Profile';
import ApiKeys from './Pages/ApiKeys';
import Settings from './Pages/Settings';
import AirgapRepositories from './Pages/AirgapRepositories';
import AirgapCollections from './Pages/AirgapCollections';
import FederationAuditLog from './Pages/FederationAuditLog';
import FederationHosts from './Pages/FederationHosts';
import FederationPolicies from './Pages/FederationPolicies';
import MapView from './Pages/MapView';
import Sites from './Pages/Sites';
import SiteDetail from './Pages/SiteDetail';
import SitesMap from './Pages/SitesMap';
import SitesTiles from './Pages/SitesTiles';
import Logout from './Pages/Logout';
import LicensedRoute from './Components/LicensedRoute';
import { getLicenseInfo } from './Services/license';
import { PluginProvider, usePlugins } from './plugins';

function AppRoutes() {
  const { routes, pluginsLoaded } = usePlugins();

  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/reset-password" element={<ResetPassword />} />
      <Route path="/accept-invitation" element={<AcceptInvitation />} />
      <Route path="/" element={<Home />} />
      <Route path="/hosts" element={<Hosts />} />
      <Route path="/hosts/:hostId" element={<HostDetail />} />
      <Route path="/users" element={<Users />} />
      <Route path="/users/:userId" element={<UserDetail />} />
      <Route path="/updates" element={<Updates />} />
      <Route path="/os-upgrades" element={<OSUpgrades />} />
      <Route path="/maintenance-windows" element={<MaintenanceWindows />} />
      <Route path="/secrets" element={<Secrets />} />
      <Route path="/scripts" element={<Scripts />} />
      <Route path="/reports" element={<Reports />} />
      <Route path="/reports/audit-log" element={<AuditLogViewer />} />
      <Route path="/reports/:reportId" element={<ReportViewer />} />
      <Route path="/profile" element={<Profile />} />
      <Route path="/api-keys" element={<ApiKeys />} />
      <Route path="/settings" element={<Settings />} />
      {/* Air-gap and federation pages are ENTERPRISE-only — guard the routes so
          they're unreachable by direct URL on a license that lacks the engine
          (defence-in-depth on top of the nav-level gating). */}
      <Route path="/airgap/repositories" element={<LicensedRoute module="airgap_repository_engine"><AirgapRepositories /></LicensedRoute>} />
      <Route path="/airgap/collections" element={<LicensedRoute module="airgap_collector_engine"><AirgapCollections /></LicensedRoute>} />
      <Route path="/map" element={<MapView />} />
      <Route path="/sites" element={<LicensedRoute module="federation_controller_engine"><Sites /></LicensedRoute>} />
      {/* ``/sites/map`` is listed BEFORE the dynamic ``:siteId``
          variant so react-router prefers the literal match. */}
      <Route path="/sites/map" element={<LicensedRoute module="federation_controller_engine"><SitesMap /></LicensedRoute>} />
      <Route path="/sites/tiles" element={<LicensedRoute module="federation_controller_engine"><SitesTiles /></LicensedRoute>} />
      <Route path="/sites/:siteId" element={<LicensedRoute module="federation_controller_engine"><SiteDetail /></LicensedRoute>} />
      <Route path="/audit/federation" element={<LicensedRoute module="federation_controller_engine"><FederationAuditLog /></LicensedRoute>} />
      <Route path="/federation/hosts" element={<LicensedRoute module="federation_controller_engine"><FederationHosts /></LicensedRoute>} />
      <Route path="/federation/policies" element={<LicensedRoute module="federation_controller_engine"><FederationPolicies /></LicensedRoute>} />
      <Route path="/logout" element={<Logout />} />
      {routes.map(route => {
        // A plugin route that declares a feature/module gate is wrapped in the
        // license guard so it can't be reached by direct URL without the
        // license — even when its nav link is hidden. Ungated routes (neither
        // field set) render as-is, preserving the pre-gate behaviour.
        const RouteComponent = route.component;
        const element = (route.featureFlag || route.moduleRequired) ? (
          <LicensedRoute feature={route.featureFlag} module={route.moduleRequired}>
            <RouteComponent />
          </LicensedRoute>
        ) : (
          <RouteComponent />
        );
        return <Route key={route.path} path={route.path} element={element} />;
      })}
      {!pluginsLoaded && <Route path="*" element={null} />}
    </Routes>
  );
}

/**
 * Renders any app-shell banners contributed by plugins (e.g. the multi-tenancy
 * tenant-migration banner).  Each banner component owns its own visibility.
 */
function PluginAppBanners() {
  const { appBanners } = usePlugins();
  const [license, setLicense] = useState<{ features: string[]; modules: string[] }>({
    features: [],
    modules: [],
  });
  useEffect(() => {
    let cancelled = false;
    // Don't fetch the license until the user is authenticated.  On /login there's
    // no bearer token, so GET /api/v1/license 401s; the axios interceptor then
    // runs its refresh→fail path and redirects to /login, remounting this banner
    // and refetching — an infinite reload loop that makes the login page unusable
    // (and broke the Playwright auth setup).  No banners render pre-login anyway.
    if (!localStorage.getItem('bearer_token')) {
      return;
    }
    getLicenseInfo()
      .then((info) => {
        if (!cancelled) {
          setLicense({ features: info.features || [], modules: info.modules || [] });
        }
      })
      .catch(() => {
        if (!cancelled) setLicense({ features: [], modules: [] });
      });
    return () => {
      cancelled = true;
    };
  }, []);
  return (
    <>
      {appBanners
        .filter((b) => {
          // Honour the banner's license gates (previously ignored). The banner
          // component may still self-hide on top of this.
          if (b.moduleRequired && !license.modules.includes(b.moduleRequired)) return false;
          if (b.featureFlag && !license.features.includes(b.featureFlag)) return false;
          return true;
        })
        .map((b) => {
          const Banner = b.component;
          return <Banner key={b.id} />;
        })}
    </>
  );
}

function App() {
  const { i18n } = useTranslation();
  const [direction, setDirection] = useState<'ltr' | 'rtl'>('ltr');

  // Create emotion cache for RTL support
  const cacheRtl = createCache({
    key: 'muirtl',
    stylisPlugins: [prefixer, rtlPlugin],
  });

  const cacheLtr = createCache({
    key: 'muiltr',
    stylisPlugins: [prefixer],
  });

  // Update direction when language changes
  useEffect(() => {
    const updateDirection = () => {
      const isRtl = i18n.language === 'ar';
      const newDirection = isRtl ? 'rtl' : 'ltr';
      setDirection(newDirection);
      document.dir = newDirection;
    };

    updateDirection();
    i18n.on('languageChanged', updateDirection);

    return () => {
      i18n.off('languageChanged', updateDirection);
    };
  }, [i18n]);

  const darkTheme = createTheme({
    direction,
    palette: {
      mode: 'dark',
    },
    components: {
      MuiCssBaseline: {
        styleOverrides: (themeParam) => ({
          body: themeParam.palette.mode === 'dark' ? darkScrollbar() : null,
        }),
      },
      MuiButton: {
        styleOverrides: {
          // i18n: translated labels run 30-50% longer than English
          // (German/French/Spanish), so a fixed/nowrap button clips the text
          // or pushes past its container.  Let the button grow to its content
          // and wrap onto a second line instead, capped at the container width
          // so it can never overflow horizontally.
          root: {
            whiteSpace: 'normal',
            overflowWrap: 'anywhere',
            maxWidth: '100%',
            lineHeight: 1.3,
          },
        },
      },
    },
  });

  return (
    <div className="App">
      <CacheProvider value={direction === 'rtl' ? cacheRtl : cacheLtr}>
        <ThemeProvider theme={darkTheme}>
          <CssBaseline enableColorScheme/>
          <ConnectionProvider>
            <PluginProvider>
              <Router>
                <Navbar />
                <MigrationCompatBanner />
                <PluginAppBanners />
                <SecurityWarningBanner />
                  <main className="main-content">
                    <AppRoutes />
                  </main>
              </Router>
            </PluginProvider>
          </ConnectionProvider>
        </ThemeProvider>
      </CacheProvider>
    </div>
  );
}

export default App;
