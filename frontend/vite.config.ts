import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import fs from 'fs'
import path from 'path'
import os from 'os'
import yaml from 'yaml'

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

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    // Use config-driven host and port with environment variable overrides
    host: hasSSLCerts ? (config?.webui?.ssl_host || 'sysmanage.org') : 
          (process.env.VITE_HOST || config?.webui?.host || 'localhost'),
    port: hasSSLCerts ? (config?.webui?.ssl_port || 7443) : 
          parseInt(process.env.VITE_PORT || config?.webui?.port?.toString() || '3000'),
    https: hasSSLCerts ? {
      key: fs.readFileSync(path.join(certPath, 'privkey.pem')),
      cert: fs.readFileSync(path.join(certPath, 'cert.pem'))
    } : undefined,
    // Dynamically allow connections from discovered network hosts
    allowedHosts: getNetworkHosts()
  },
  build: {
    outDir: 'build'
  },
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: './src/setupTests.ts',
    css: true
  }
})