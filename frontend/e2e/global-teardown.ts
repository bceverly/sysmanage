/**
 * Playwright Global Teardown
 *
 * Cleans up any test users created during E2E test runs.
 * This runs after ALL tests complete (pass or fail), ensuring
 * dynamically created e2e-test-* users don't accumulate in the database.
 */

import { execFileSync } from 'child_process';
import { dirname, join } from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

async function globalTeardown() {
  console.log('[teardown] Cleaning up E2E test users...');

  const scriptPath = join(__dirname, '..', '..', 'scripts', 'e2e_test_user.py');

  try {
    const result = execFileSync('python3', [scriptPath, 'delete'], {
      encoding: 'utf-8',
      timeout: 30000,
      cwd: join(__dirname, '..', '..'),
    });
    console.log(result);
  } catch (e: unknown) {
    // Don't fail the test run if cleanup fails
    const message = e instanceof Error ? e.message : String(e);
    console.warn('[teardown] Warning: E2E test user cleanup failed:', message);
  }
}

export default globalTeardown;
