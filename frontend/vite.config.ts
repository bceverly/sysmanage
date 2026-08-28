// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import fs from 'fs'
import path from 'path'
import os from 'os'
import yaml from 'yaml'

// Vitest loads this config to read the `test` block, which fires the dev-server
// startup banners below and clutters test output. Route the banners through a
// helper that stays silent under Vitest but still prints for `vite`/`vite build`.
const rawLog = console.log.bind(console)
const banner = (...args: unknown[]) => {
  if (!process.env.VITEST) rawLog(...args)
}

// Plugin to transform MUI icon barrel imports to individual imports
// This prevents loading thousands of icon files and exhausting file descriptors
function muiIconsPlugin() {
  return {
    name: 'mui-icons-transform',
    transform(code: string, id: string) {
      // Only process .tsx and .ts files
      if (!id.endsWith('.tsx') && !id.endsWith('.ts')) return null

      // Match: import { IconName, AnotherIcon } from '@mui/icons-material'
      // Transform to: import IconName from '@mui/icons-material/IconName'; import AnotherIcon from '@mui/icons-material/AnotherIcon'
      const muiIconsRegex = /import\s+\{([^}]+)\}\s+from\s+['"]@mui\/icons-material['"]/g

      let transformed = code
      let match

      while ((match = muiIconsRegex.exec(code)) !== null) {
        const imports = match[1]
        const iconNames = imports.split(',').map(name => {
          // Handle "Icon as AliasIcon" syntax
          const parts = name.trim().split(/\s+as\s+/)
          return {
            original: parts[0].trim(),
            alias: parts[1]?.trim() || parts[0].trim()
          }
        })

        // Generate individual imports
        const individualImports = iconNames
          .map(({ original, alias }) =>
            alias === original
              ? `import ${original} from '@mui/icons-material/${original}'`
              : `import ${alias} from '@mui/icons-material/${original}'`
          )
          .join('\n')

        transformed = transformed.replace(match[0], individualImports)
      }

      return transformed !== code ? { code: transformed, map: null } : null
    }
  }
}

// Function to load configuration from hierarchy (same as backend)
function loadConfig(): any {
  const configPaths = [
    '/etc/sysmanage.yaml',           // System config (priority 1)
    '../sysmanage-dev.yaml',         // Local dev config (priority 2)
    './sysmanage-dev.yaml'           // Frontend local config (priority 3)
  ];
  
  for (const configPath of configPaths) {
    try {
      if (fs.existsSync(configPath)) {
        const configContent = fs.readFileSync(configPath, 'utf8');
        const config = yaml.parse(configContent);
        banner(`📋 Loaded config from: ${configPath}`);
        return config;
      }
    } catch (error) {
      // nosemgrep: javascript.lang.security.audit.unsafe-formatstring
      console.warn(`⚠️  Failed to load config from ${configPath}:`, error);
    }
  }
  
  banner('📋 No config file found, using defaults');
  return {};
}

// Load configuration
const config = loadConfig();

// A backend may *bind* to a wildcard address (0.0.0.0 / ::) to listen on every
// interface, but those are NOT valid *connect* targets for the dev-proxy client
// — connecting to http://0.0.0.0:PORT is refused on Linux. Normalize wildcard
// hosts to localhost so `/api` proxy requests actually reach the backend.
// (Without this, an ``api.host: 0.0.0.0`` config silently breaks every proxied
// request — e.g. the login POST fails with a network error and the UI just
// sits on /login.)
const proxyConnectHost = (h?: string): string => {
  const v = (h || '').trim();
  // IPv4 wildcard (and empty/default) -> IPv4 loopback; IPv6 wildcard -> IPv6
  // loopback. Using a loopback that matches the bind family avoids the case
  // where ``localhost`` resolves to ::1 while the backend bound 0.0.0.0 (IPv4
  // only) and the proxy connection is refused.
  if (v === '' || v === '0.0.0.0' || v === '0') return '127.0.0.1';
  if (v === '::' || v === '[::]') return '::1';
  return v;
};

// Determine SSL/HTTPS configuration dynamically
const forceHTTP = process.env.FORCE_HTTP === 'true';
const certPath = path.resolve(process.env.HOME || '', 'dev/certs/sysmanage.org');
const configHasSSL = config?.webui?.ssl !== false && config?.webui?.https !== false;
const hasSSLCerts = !forceHTTP && configHasSSL && 
                   fs.existsSync(path.join(certPath, 'privkey.pem')) && 
                   fs.existsSync(path.join(certPath, 'cert.pem'));

banner('🔧 Vite configuration:');
banner('  - Force HTTP:', forceHTTP);
banner('  - Config allows SSL:', configHasSSL);
banner('  - SSL certificates available:', fs.existsSync(path.join(certPath, 'privkey.pem')) && fs.existsSync(path.join(certPath, 'cert.pem')));
banner('  - Using HTTPS:', hasSSLCerts);
banner('  - WebUI host from config:', config?.webui?.host);
banner('  - WebUI port from config:', config?.webui?.port);

// Dynamically discover network interfaces and hostname
function getNetworkHosts(): string[] {
  const hosts = ['localhost', '127.0.0.1', '0.0.0.0'];
  
  // Add system hostname
  const hostname = os.hostname();
  hosts.push(hostname);
  
  // Add hostname with common domain suffixes
  hosts.push(`${hostname}.local`);
  hosts.push(`${hostname}.lan`);
  hosts.push(`${hostname}.theeverlys.lan`);
  hosts.push(`${hostname}.theeverlys.com`);
  
  // Add all network interface IPs
  const interfaces = os.networkInterfaces();
  Object.values(interfaces).forEach(interfaceList => {
    interfaceList?.forEach(iface => {
      if (!iface.internal) {
        hosts.push(iface.address);
      }
    });
  });
  
  const uniqueHosts = [...new Set(hosts)]; // Remove duplicates
  banner('🌐 Vite allowed hosts:', uniqueHosts);
  return uniqueHosts;
}

// Calculate final host and port values
const finalHost = hasSSLCerts ? (config?.webui?.ssl_host || 'sysmanage.org') :
                  (process.env.VITE_HOST || config?.webui?.host || 'localhost');
const finalPort = hasSSLCerts ? (config?.webui?.ssl_port || 7443) :
                  parseInt(process.env.VITE_PORT || config?.webui?.port?.toString() || '3000');

// Calculate client-accessible host for HMR (WebSocket needs a real hostname, not 0.0.0.0)
const clientHost = finalHost === '0.0.0.0' ? 'localhost' : finalHost;

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), muiIconsPlugin()],
  // Development-specific settings
  define: {
    // Suppress some common development warnings
    __DEV__: JSON.stringify(process.env.NODE_ENV !== 'production'),
    // Build-time stamp appended to /locales fetch URLs as a cache-buster.
    // Without it the browser serves a stale /locales/<lng>/translation.json
    // (identical URL) after `make translate` + redeploy, so updated strings
    // never appear until a manual hard-refresh.  A fresh value each build
    // forces i18next-http-backend to re-fetch the current catalog.
    __LOCALE_BUILD_ID__: JSON.stringify(String(Date.now()))
  },
  server: {
    // Use config-driven host and port with environment variable overrides
    host: finalHost,
    port: finalPort,
    https: hasSSLCerts ? {
      key: fs.readFileSync(path.join(certPath, 'privkey.pem')),
      cert: fs.readFileSync(path.join(certPath, 'cert.pem'))
    } : undefined,
    // Dynamically allow connections from discovered network hosts
    allowedHosts: getNetworkHosts(),
    // HMR configuration to fix WebSocket connection issues
    hmr: {
      port: finalPort,
      // Let Vite auto-detect the host from the browser location
      clientPort: finalPort // Ensure client connects to the same port
    },
    // Keep the HMR watcher off Playwright's own output dirs.  They live under
    // the Vite root (frontend/), so while a Playwright run writes its HTML
    // report / traces / screenshots, Vite sees those changes and fires
    // full-page reloads at the very browser under test — the /login page then
    // reloads in a loop and never reaches the "load" event (manifests as a
    // 60s navigation timeout in auth.setup.ts).  Excluding them stops the loop
    // (and avoids the watcher churning over these dirs on NFS).
    watch: {
      ignored: [
        '**/playwright-report/**',
        '**/test-results/**',
        '**/playwright/.cache/**',
      ],
    },
    // Proxy API requests to backend server.
    //
    // Resolution order (first match wins):
    //   1. VITE_BACKEND_HOST / VITE_BACKEND_PORT  — env vars from CI/dev shell
    //   2. config.api.host / config.api.port      — yaml-loaded config
    //   3. localhost:8080                          — package default
    //
    // Falling back from env -> yaml -> default matters on Windows CI:
    // ``loadConfig`` only looks at Unix-style paths (``/etc/sysmanage.yaml``,
    // ``../sysmanage-dev.yaml``) and can't find the Windows config at
    // ``C:\ProgramData\sysmanage\sysmanage.yaml``, so without the env-var
    // override the proxy defaulted to port 8080 while the backend was
    // actually on 8001 — every ``/api/v1/server-info`` request returned
    // 500 from the proxy and the Playwright "no critical failed requests"
    // assertion failed.
    proxy: {
      '/api': {
        target: `http://${
          proxyConnectHost(process.env.VITE_BACKEND_HOST || config?.api?.host)
        }:${
          process.env.VITE_BACKEND_PORT || config?.api?.port || 8080
        }`,
        changeOrigin: true,
        secure: false
      }
    }
  },
  // Preview server — serves the pre-built ``dist/`` bundle (NOT the dev server
  // that streams unbundled ESM modules one-per-request).  CI uses this for the
  // Playwright UI tests: the dev server makes every page load fetch hundreds of
  // module files, which never lets ``networkidle`` settle (so each wait burns
  // its full timeout, worst on Windows).  ``vite preview`` serves the bundled
  // build, so page loads are fast and deterministic.
  //
  // ``server.proxy`` does NOT apply to preview, so the ``/api`` proxy is
  // repeated here with the same env -> yaml -> default resolution.
  preview: {
    host: finalHost,
    port: finalPort,
    strictPort: true,
    proxy: {
      '/api': {
        target: `http://${
          proxyConnectHost(process.env.VITE_BACKEND_HOST || config?.api?.host)
        }:${
          process.env.VITE_BACKEND_PORT || config?.api?.port || 8080
        }`,
        changeOrigin: true,
        secure: false
      }
    }
  },
  build: {
    outDir: 'dist',
    sourcemap: process.env.NODE_ENV === 'development' ? 'inline' : false,
    // Reduce console noise in production
    minify: process.env.NODE_ENV === 'production',
    // Code-split heavy vendor groups so the main app chunk stays cacheable
    // and parses faster on first load.  Without this, everything lands in
    // a single ~2 MB index-*.js bundle.
    // No `manualChunks` — Vite/Rollup's automatic chunk splitting is
    // safe.  Custom splits are tempting (smaller initial parse, better
    // caching) but the React 19 + MUI 7 dependency graph has internal
    // circular imports that produce TDZ errors at runtime when chunks
    // are split manually (symptoms: blank page,
    //   "Cannot access 'X' before initialization" or
    //   "Cannot set properties of undefined (setting 'Activity')"
    // on first load).  Leave this alone unless you have a verified
    // playwright e2e run proving the new split works.
    chunkSizeWarningLimit: 2500,
  },
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: './src/setupTests.ts',
    // Swallow i18next's Locize sponsor banner — a benign line printed on init
    // in v25 (despite showSupportNotice:false) that only clutters test output.
    // (jsdom's "Not implemented: navigation" notice can't be filtered here: its
    // default VirtualConsole writes straight to process.stderr, below vitest's
    // console-intercept layer.) Every other log passes through unchanged.
    onConsoleLog(log: string): boolean | void {
      if (log.includes('i18next is maintained with support from Locize')) {
        return false;
      }
    },
    css: true,  // Enable CSS processing in vitest 4.x
    // Raised for slow environments: Windows CI, and especially an NFS-mounted
    // checkout where a cold dynamic ``import()`` of a module graph (e.g. the
    // AuthHelper import smoke test) transforms over the network and blows past
    // a 10s budget. The suite's import phase alone runs into the hundreds of
    // seconds on NFS, so give individual tests real headroom.
    testTimeout: 30000,
    // Exclude Playwright E2E tests - they run separately via `npx playwright test`
    exclude: ['**/node_modules/**', '**/dist/**', '**/e2e/**'],
    server: {
      deps: {
        inline: [
          '@mui/x-data-grid',
          '@mui/x-data-grid-pro',
          '@mui/x-data-grid-premium'
        ]
      }
    },
    coverage: {
      provider: 'v8',
      reporter: ['text', 'json', 'json-summary', 'html'],
      reportsDirectory: './coverage',
      // Ratchet: floors set a couple points below today's measured coverage so
      // the run only fails on a regression.  vitest fails if any metric drops
      // below these — raise them as coverage improves (never lower).
      //
      // RAMP PLAN: the LINE floor climbs ~10 points per phase until it is in
      // sync with the Python suite's 75% gate (which is a line-coverage number,
      // `--cov-fail-under=75`).  A floor can never exceed *actual* coverage
      // (vitest fails the run otherwise), so each rung is a test-writing push
      // first, then a floor bump — the floor FOLLOWS coverage, never leads it:
      //     line floor →   40  →  50  →  60  →  70  →  75  (== Python)
      // Raise to the next rung only once actual coverage clears it with headroom.
      // statements/functions/branches trail on their own tracks (like the backend,
      // whose gate is also lines) and are ratcheted to just under measured.
      //
      // Phase 16: line floor 40 REACHED.  A HostDetail-hooks test push
      // (useChildHosts, useHostObservability, useHostLifecycle,
      // useHostAccessManagement, useHostSoftware, useHostUbuntuPro) lifted measured
      // lines 34.0% -> 44.2% / statements 33.1% -> 43.2% / functions 31.7% -> 37.2%
      // / branches 21.3% -> 26.3%.  Floors locked ~2-4pts under measured (green).
      //
      // Phase 19 (current): line floor 50 REACHED, which was that plan's stated
      // trigger ("push measured lines past ~52% then raise the `lines` floor to
      // 50").  Measured 2026-08-25 at lines 52.02% / statements 51.05% /
      // functions 43.67% / branches 33.06% over 1121 tests, up from 45.24 /
      // 44.25 / 38.25 / 27.69.  The lift came from pure helpers and hooks first
      // (hostDetailHelpers, useHostRolesAndCerts, scriptsHelpers) and then the
      // five biggest untested pages -- Scripts, Settings, Updates,
      // ThirdPartyRepositories, Secrets -- each with its heavy children stubbed.
      // Floors again locked ~2-3pts under measured, and they FOLLOW coverage,
      // never lead it.
      // Phase 20 rung: line floor 60 REACHED, which was the previous plan's
      // stated trigger ("push measured lines past ~62% then raise the `lines`
      // floor to 60").  Measured 2026-08-26 at lines 62.36% / statements
      // 61.10% / functions 51.07% / branches 41.39% over 1325 tests, up from
      // 52.02 / 51.05 / 43.67 / 33.06.  The lift came from sixteen
      // previously-untested Pages and Components, taken worst-first by
      // uncovered-line count: UserDetail, OSUpgrades, ResetPassword,
      // AcceptInvitation, AuditLogViewer, AirgapCollections, and the
      // MfaEnrollment / AntivirusStatus / ReportTemplates / ReportBranding /
      // HostCompliance / GrafanaIntegration / GraylogAttachment /
      // AddHostAccount / Processes / UbuntuPro components.
      // Floors again locked ~2-3pts under measured, and they FOLLOW coverage,
      // never lead it.
      // Next rung: push measured lines past ~72% then raise `lines` to 70.
      // Phase 20.1 rung. The ladder in ROADMAP.md ("Frontend Test Coverage")
      // moves `lines` +10 per phase on its climb to parity with the Python
      // gate; 60 -> 70 is this phase's step. NEVER lower these.
      //
      // Each floor sits below its measured value on purpose, so an ordinary
      // refactor does not turn red before anyone has written a line of new
      // code. Measured at the time of the bump: lines 71.59, statements
      // 70.28, functions 58.61, branches 50.26.
      thresholds: {
        lines: 70,
        statements: 68,
        functions: 56,
        branches: 48,
      },
      exclude: [
        'node_modules/',
        'src/setupTests.ts',
        '**/*.d.ts',
        '**/*.config.ts',
        '**/*.config.js',
        'coverage/**',
        'dist/**',
        'build/**'
      ]
    }
  }
})