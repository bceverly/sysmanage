// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

// jest-dom adds custom jest matchers for asserting on DOM nodes.
// allows you to do things like:
// expect(element).toHaveTextContent(/react/i)
// learn more: https://github.com/testing-library/jest-dom
import '@testing-library/jest-dom';
import './__tests__/setup';

// Testing Library's findBy*/waitFor default to a 1000ms timeout, which is a
// race against how loaded the machine is rather than against anything the code
// does.  It lost that race on 2026-08-13: FirewallRolesSettings' first test
// failed in a full 161s run (139s of it setup) while passing in 2.5s on its
// own, and the four heavier tests in the same file passed alongside it.  The
// failure rendered the empty state, i.e. the mocked GET simply had not resolved
// yet.
//
// 5s costs nothing on a passing test -- a longer ceiling is only ever reached
// when something is genuinely slow -- and it removes a whole class of
// load-dependent flake across the suite as it grows.  vitest's own testTimeout
// (30s, in vite.config.ts) still bounds a truly hung test.
import { configure } from '@testing-library/dom';

configure({ asyncUtilTimeout: 5000 });

// Declare process.env for TypeScript
declare const process: { env: { CI?: string; VITEST_VERBOSE_CONSOLE?: string } } | undefined;

// Setup MSW for all tests
import { beforeAll, beforeEach, afterEach, afterAll } from 'vitest';
import { server } from './mocks/node';

// Start MSW server before all tests
beforeAll(() => {
  // Enable MSW request logging in CI
  const isCI = process !== undefined && process.env?.CI === 'true';

  // 'error', not 'warn'.  An unhandled request is ALWAYS a mocking gap, never
  // something a test legitimately wants -- and while this was 'warn' the
  // handlers sat pinned to http://localhost:8080 while jsdom serves the app
  // from :3000, so every relative-URL request missed all four handlers and
  // fell through to the real network.  That went unnoticed for as long as the
  // warning was only scrollback.
  server.listen({
    onUnhandledRequest: 'error',
  });

  if (isCI) {
    console.log('MSW server started for CI environment');
  }
});

// Reset handlers after each test `important for test isolation`
afterEach(() => {
  server.resetHandlers();
});

// Clean up after all tests are done
afterAll(() => {
  const isCI = process !== undefined && process.env?.CI === 'true';

  if (isCI) {
    console.log('MSW server stopped - CI test run completed');
  }

  server.close();
});


// ---------------------------------------------------------------------------
// Console policy: buffer, then discard on pass / replay on fail
// ---------------------------------------------------------------------------
// Most console output in this suite is EXPECTED: a test that exercises an
// error path asserts the snackbar, and the component logs on its way there.
// Printing it unconditionally buried the runs in scrollback -- 82 blocks across
// 16 files -- which is how genuine problems (an MSW origin mismatch, React
// act() warnings) sat unnoticed in plain sight for months.
//
// So: capture output per test instead of printing it. A passing test discards
// it; a FAILING test replays everything it logged, so the breadcrumbs are
// there exactly when they are useful. Set VITEST_VERBOSE_CONSOLE=1 to pass
// everything straight through while debugging.
//
// This deliberately does NOT use per-file `vi.spyOn(console, 'error')`: a spy
// replaces the wrapper below, which would also opt that file out of the fatal
// checks -- and the hook tests that log the most are precisely where the act()
// warnings turned up.
const FATAL_CONSOLE_PATTERNS = ['not wrapped in act('];

const VERBOSE_CONSOLE =
  process !== undefined && process.env?.VITEST_VERBOSE_CONSOLE === '1';

type ConsoleMethod = 'log' | 'info' | 'warn' | 'error' | 'debug';
const CAPTURED_METHODS: ConsoleMethod[] = ['log', 'info', 'warn', 'error', 'debug'];

let buffered: string[] = [];
let fatalConsoleHits: string[] = [];

const realConsole: Partial<Record<ConsoleMethod, (...args: unknown[]) => void>> = {};
for (const method of CAPTURED_METHODS) {
  realConsole[method] = globalThis.console[method].bind(globalThis.console);
  globalThis.console[method] = (...args: unknown[]) => {
    const text = args.map((a) => String(a)).join(' ');
    if (FATAL_CONSOLE_PATTERNS.some((pattern) => text.includes(pattern))) {
      fatalConsoleHits.push(text.split('\n')[0]);
    }
    if (VERBOSE_CONSOLE) {
      realConsole[method]!(...args);
      return;
    }
    buffered.push(`[console.${method}] ${text}`);
  };
}

beforeEach(() => {
  buffered = [];
  fatalConsoleHits = [];
});

afterEach((ctx: { task?: { result?: { state?: string } } }) => {
  const failed = ctx?.task?.result?.state === 'fail';
  const hits = fatalConsoleHits;
  const captured = buffered;
  buffered = [];
  fatalConsoleHits = [];

  // Replay for a failing test -- that is when the log actually helps.
  if (failed && captured.length > 0) {
    realConsole.error!(
      `--- console output from the failing test above ---\n${captured.join('\n')}`,
    );
  }

  if (hits.length > 0) {
    throw new Error(
      `Console output that must never occur was emitted during this test:\n  - ${hits.join('\n  - ')}`,
    );
  }
});

// Fix for React 19 compatibility in JSDOM environment
declare global {
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

// Node 22+ (this repo runs Node 25) ships a built-in *experimental* `localStorage`
// global that shadows JSDom's; without a valid `--localstorage-file` it warns and is
// not a spec-complete Storage, so component code calling `localStorage.getItem(...)`
// throws "getItem is not a function". Install a deterministic in-memory Storage.
function createTestStorage(): Storage {
  let store: Record<string, string> = {};
  return {
    get length() {
      return Object.keys(store).length;
    },
    clear() {
      store = {};
    },
    getItem(key: string) {
      return Object.hasOwn(store, key) ? store[key] : null;
    },
    setItem(key: string, value: string) {
      store[key] = String(value);
    },
    removeItem(key: string) {
      delete store[key];
    },
    key(index: number) {
      return Object.keys(store)[index] ?? null;
    }
  };
}
Object.defineProperty(globalThis, 'localStorage', {
  configurable: true,
  writable: true,
  value: createTestStorage()
});
Object.defineProperty(globalThis, 'sessionStorage', {
  configurable: true,
  writable: true,
  value: createTestStorage()
});

// JSDom lacks ResizeObserver, which our scrollable nav/button components
// instantiate inside useEffect.  Provide a no-op stub so tests don't crash.
// The methods deliberately do nothing — JSDom never fires resize events
// in unit tests, so observation/teardown are inert by design.
Object.defineProperty(globalThis, 'ResizeObserver', {
  writable: true,
  value: class ResizeObserver {
    observe() {
      /* no-op: JSDom does not fire resize events in unit tests */
    }
    unobserve() {
      /* no-op: nothing to detach since observe() is inert */
    }
    disconnect() {
      /* no-op: no observers to release */
    }
  }
});

// Polyfill for React 19's scheduler in test environment
Object.defineProperty(globalThis, 'MessageChannel', {
  writable: true,
  value: class MessageChannel {
    port1 = {
      onmessage: null,
      postMessage: () => {}
    }
    port2 = {
      onmessage: null,
      postMessage: () => {}
    }
  }
});

// React 19 specific polyfills for test environment
if (typeof globalThis !== 'undefined') {
  // Ensure Scheduler is available
  Object.defineProperty(globalThis, 'Scheduler', {
    writable: true,
    value: {
      unstable_scheduleCallback: (callback: () => void) => setTimeout(callback, 0),
      unstable_cancelCallback: () => {},
      unstable_shouldYield: () => false,
      unstable_requestPaint: () => {},
      unstable_runWithPriority: (_priority: unknown, callback: () => void) => callback(),
      get unstable_now() {
        return globalThis.performance?.now ?? Date.now;
      }
    }
  });
}
