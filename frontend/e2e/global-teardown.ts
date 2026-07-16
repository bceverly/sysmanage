// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

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

  // Windows ships `python` (no `python3` on PATH — it maps to a Store stub); Unix uses `python3`.
  const pythonCmd = process.platform === 'win32' ? 'python' : 'python3';

  try {
    const result = execFileSync(pythonCmd, [scriptPath, 'delete'], {
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
