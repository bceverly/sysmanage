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
    __DEV__: JSON.stringify(process.env.NODE_ENV !== 'production')
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
    // Proxy API requests to backend server
    proxy: {
      '/api': {
        target: `http://${config?.api?.host || 'localhost'}:${config?.api?.port || 8080}`,
        changeOrigin: true,
        secure: false
      }
    }
  },
  build: {
    outDir: 'build',
    sourcemap: process.env.NODE_ENV === 'development' ? 'inline' : false,
    // Reduce console noise in production
    minify: process.env.NODE_ENV === 'production'
  },
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: './src/setupTests.ts',
    css: true,
    // Increase timeout for Windows CI environments
    testTimeout: 10000,
    // Reduce file descriptor usage by using threads with limited concurrency
    pool: 'threads',
    poolOptions: {
      threads: {
        maxThreads: 4,
        minThreads: 1
      }
    },
    deps: {
      optimizer: {
        web: {
          include: [
            '@mui/x-data-grid',
            '@mui/x-data-grid-pro',
            '@mui/x-data-grid-premium',
            '@mui/icons-material'
          ]
        }
      }
    },
    coverage: {
      provider: 'v8',
      reporter: ['text', 'json', 'json-summary', 'html'],
      reportsDirectory: './coverage',
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