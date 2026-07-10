// jest-dom adds custom jest matchers for asserting on DOM nodes.
// allows you to do things like:
// expect(element).toHaveTextContent(/react/i)
// learn more: https://github.com/testing-library/jest-dom
import '@testing-library/jest-dom';
import './__tests__/setup';

// Declare process.env for TypeScript
declare const process: { env: { CI?: string } } | undefined;

// Setup MSW for all tests
import { beforeAll, afterEach, afterAll } from 'vitest';
import { server } from './mocks/node';

// Start MSW server before all tests
beforeAll(() => {
  // Enable MSW request logging in CI
  const isCI = process !== undefined && process.env?.CI === 'true';

  server.listen({
    onUnhandledRequest: 'warn', // Warn about unhandled requests
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
  } as Storage;
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
