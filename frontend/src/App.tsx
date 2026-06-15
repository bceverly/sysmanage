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
import Home from './Pages/Home';
import Hosts from './Pages/Hosts';
import HostDetail from './Pages/HostDetail';
import Users from './Pages/Users';
import UserDetail from './Pages/UserDetail';
import Updates from './Pages/Updates';
import OSUpgrades from './Pages/OSUpgrades';
import Secrets from './Pages/Secrets';
import Scripts from './Pages/Scripts';
import Reports from './Pages/Reports';
import ReportViewer from './Pages/ReportViewer';
import AuditLogViewer from './Pages/AuditLogViewer';
import Profile from './Pages/Profile';
import Settings from './Pages/Settings';
import TenantManagement from './Pages/TenantManagement';
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
import { PluginProvider, usePlugins } from './plugins';

function AppRoutes() {
  const { routes, pluginsLoaded } = usePlugins();

  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/reset-password" element={<ResetPassword />} />
      <Route path="/" element={<Home />} />
      <Route path="/hosts" element={<Hosts />} />
      <Route path="/hosts/:hostId" element={<HostDetail />} />
      <Route path="/users" element={<Users />} />
      <Route path="/users/:userId" element={<UserDetail />} />
      <Route path="/updates" element={<Updates />} />
      <Route path="/os-upgrades" element={<OSUpgrades />} />
      <Route path="/secrets" element={<Secrets />} />
      <Route path="/scripts" element={<Scripts />} />
      <Route path="/reports" element={<Reports />} />
      <Route path="/reports/audit-log" element={<AuditLogViewer />} />
      <Route path="/reports/:reportId" element={<ReportViewer />} />
      <Route path="/profile" element={<Profile />} />
      <Route path="/settings" element={<Settings />} />
      <Route path="/tenants" element={<TenantManagement />} />
      <Route path="/airgap/repositories" element={<AirgapRepositories />} />
      <Route path="/airgap/collections" element={<AirgapCollections />} />
      <Route path="/map" element={<MapView />} />
      <Route path="/sites" element={<Sites />} />
      {/* ``/sites/map`` is listed BEFORE the dynamic ``:siteId``
          variant so react-router prefers the literal match. */}
      <Route path="/sites/map" element={<SitesMap />} />
      <Route path="/sites/tiles" element={<SitesTiles />} />
      <Route path="/sites/:siteId" element={<SiteDetail />} />
      <Route path="/audit/federation" element={<FederationAuditLog />} />
      <Route path="/federation/hosts" element={<FederationHosts />} />
      <Route path="/federation/policies" element={<FederationPolicies />} />
      <Route path="/logout" element={<Logout />} />
      {routes.map(route => (
        <Route
          key={route.path}
          path={route.path}
          element={<route.component />}
        />
      ))}
      {!pluginsLoaded && <Route path="*" element={null} />}
    </Routes>
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
