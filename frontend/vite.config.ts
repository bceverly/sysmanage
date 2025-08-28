import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import fs from 'fs'
import path from 'path'

// Force HTTP for development (set FORCE_HTTP=true)
const forceHTTP = process.env.FORCE_HTTP === 'true';
const certPath = path.resolve(process.env.HOME || '', 'dev/certs/sysmanage.org');
const hasSSLCerts = !forceHTTP && fs.existsSync(path.join(certPath, 'privkey.pem')) && 
                   fs.existsSync(path.join(certPath, 'cert.pem'));

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    host: hasSSLCerts ? 'sysmanage.org' : 'localhost',
    port: hasSSLCerts ? 7443 : 3000,
    https: hasSSLCerts ? {
      key: fs.readFileSync(path.join(certPath, 'privkey.pem')),
      cert: fs.readFileSync(path.join(certPath, 'cert.pem'))
    } : undefined
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