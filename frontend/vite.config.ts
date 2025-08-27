import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import fs from 'fs'
import path from 'path'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    host: 'sysmanage.org',
    port: 7443,
    https: {
      key: fs.readFileSync(path.resolve(process.env.HOME!, 'dev/certs/sysmanage.org/privkey.pem')),
      cert: fs.readFileSync(path.resolve(process.env.HOME!, 'dev/certs/sysmanage.org/cert.pem'))
    }
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