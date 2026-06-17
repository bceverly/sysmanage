import { defineConfig, devices } from '@playwright/test';
import { fileURLToPath } from 'url';
import { dirname, join } from 'path';

// Use absolute path for storage state to avoid macOS path resolution issues
const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);
const authFile = join(__dirname, 'playwright', '.auth', 'user.json');
const globalTeardownPath = join(__dirname, 'e2e', 'global-teardown.ts');

/**
 * SysManage E2E Test Configuration
 * See https://playwright.dev/docs/test-configuration
 */
export default defineConfig({
  testDir: './e2e',
  /* Global teardown to clean up test users created during E2E runs */
  globalTeardown: globalTeardownPath,
  /* Run tests in files in parallel */
  fullyParallel: true,
  /* Fail the build on CI if you accidentally left test.only in the source code. */
  forbidOnly: !!process.env.CI,
  /* One retry everywhere (was CI-only).  These E2E run against a Vite dev
     server with fullyParallel workers, so a heavily-loaded box occasionally
     spikes a single timing-sensitive assertion (page-load budget, element
     attach) 2-3x past its wait.  With 0 local retries that one spike hard-fails
     the whole `make test-e2e`; one retry re-runs just that test (by then other
     workers have usually drained, so contention is lower) and absorbs the
     flake.  Playwright still reports it as "flaky", so a genuinely-broken test
     that fails BOTH attempts is not masked.  One (not two): a real failure
     shouldn't burn three 60s timeouts. */
  retries: 1,
  /* Parallelism.  Capped at 2 locally (was `undefined` → Playwright's default
     of 50% of cores = 4 on an 8-core box).  Four Chromium workers PLUS the Vite
     dev server PLUS the Python backend badly oversubscribe 8 cores, which is
     what spiked timing-sensitive tests 2-8x (a 5s render took 41s) and drove
     the flakes.  Two workers keeps every test near its baseline timing — the
     real fix for the flakiness, not raising individual waits.  CI stays at 3. */
  workers: process.env.CI ? 3 : 2,
  /* Reporter to use. See https://playwright.dev/docs/test-reporters */
  reporter: [
    ['html', { outputFolder: 'playwright-report', open: 'never' }],
    ['list'],
  ],
  /* Shared settings for all the projects below. See https://playwright.dev/docs/api/class-testoptions. */
  use: {
    /* Use the system-installed Chrome instead of Playwright's bundled
     * chromium-headless-shell. Required on distros that Playwright's
     * official support matrix does not yet list (e.g. Ubuntu 26.04).
     * Set at the top level so every project — including `setup` — inherits it. */
    channel: 'chrome',

    /* Base URL to use in actions like `await page.goto('/')`. */
    baseURL: process.env.PLAYWRIGHT_BASE_URL || 'http://localhost:3000',

    /* Collect trace when retrying the failed test. See https://playwright.dev/docs/trace-viewer */
    trace: 'on-first-retry',

    /* Take screenshot on failure */
    screenshot: 'only-on-failure',

    /* Video is intentionally OFF.  Playwright's video recorder requires its
     * bundled ffmpeg binary, which is NOT installed here (this setup uses the
     * system `channel: 'chrome'` and never ran a full `npx playwright install`).
     * With video on, `on-first-retry` made every retry crash instantly in
     * `browserContext.newPage` ("ffmpeg Executable doesn't exist"), so the retry
     * safety net above was DEAD — flakes never got their second chance.  `trace`
     * needs no ffmpeg and gives better debugging than video anyway. */
    video: 'off',
  },

  /* Configure projects for major browsers */
  projects: [
    /* Test setup - authenticate before other tests */
    {
      name: 'setup',
      testMatch: /.*\.setup\.ts/,
    },
    {
      name: 'chromium',
      use: {
        ...devices['Desktop Chrome'],
        /* `channel: 'chrome'` is set at the top-level `use` so it is
         * inherited here (and by the `setup` project that runs before us). */
        /* Use authenticated state from setup */
        storageState: authFile,
      },
      dependencies: ['setup'],
    },
    /* Firefox project temporarily disabled.
     *
     * Re-enable once one of:
     *   (a) Playwright's bundled Firefox supports the host OS, OR
     *   (b) A non-snap Firefox is installed at a path Playwright can launch
     *       (snap-confined Firefox does not work reliably with Playwright
     *       because of the snap sandbox).
     *
     * To re-enable with a non-snap Firefox, restore the block below and add:
     *     launchOptions: { executablePath: '/path/to/firefox' }
     */
    // {
    //   name: 'firefox',
    //   use: {
    //     ...devices['Desktop Firefox'],
    //     storageState: authFile,
    //   },
    //   dependencies: ['setup'],
    // },
    /* Uncomment for WebKit/Safari coverage
    {
      name: 'webkit',
      use: {
        ...devices['Desktop Safari'],
        storageState: authFile,
      },
      dependencies: ['setup'],
    },
    */
  ],

  /*
   * E2E tests expect the full stack to already be running.
   * When run via `make test-e2e`, the Makefile handles starting/stopping servers.
   * For manual runs, start: backend (make start) + frontend (npm run dev)
   */

  /* Global timeout for each test */
  timeout: 60 * 1000,

  /* Expect timeout */
  expect: {
    timeout: 20 * 1000,
  },
});
