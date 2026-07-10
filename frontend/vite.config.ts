import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import fs from 'fs'
import path from 'path'
import os from 'os'
import yaml from 'yaml'

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
        console.log(`📋 Loaded config from: ${configPath}`);
        return config;
      }
    } catch (error) {
      // nosemgrep: javascript.lang.security.audit.unsafe-formatstring
      console.warn(`⚠️  Failed to load config from ${configPath}:`, error);
    }
  }
  
  console.log('📋 No config file found, using defaults');
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

console.log('🔧 Vite configuration:');
console.log('  - Force HTTP:', forceHTTP);
console.log('  - Config allows SSL:', configHasSSL);
console.log('  - SSL certificates available:', fs.existsSync(path.join(certPath, 'privkey.pem')) && fs.existsSync(path.join(certPath, 'cert.pem')));
console.log('  - Using HTTPS:', hasSSLCerts);
console.log('  - WebUI host from config:', config?.webui?.host);
console.log('  - WebUI port from config:', config?.webui?.port);

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
  console.log('🌐 Vite allowed hosts:', uniqueHosts);
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
      // Phase 13 GA ratchet: floors at today's measured coverage so it can only
      // go up.  vitest fails the run if any metric drops below these — raise
      // them as coverage improves (never lower).
      thresholds: {
        lines: 12,
        statements: 12,
        functions: 9,
        branches: 7,
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