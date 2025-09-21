// jest-dom adds custom jest matchers for asserting on DOM nodes.
// allows you to do things like:
// expect(element).toHaveTextContent(/react/i)
// learn more: https://github.com/testing-library/jest-dom
import '@testing-library/jest-dom';
import './__tests__/setup';

// Fix for React 19 compatibility in JSDOM environment
declare global {
  var IS_REACT_ACT_ENVIRONMENT: boolean;
  function beforeAll(fn: () => void | Promise<void>): void;
  function afterEach(fn: () => void | Promise<void>): void;
  function afterAll(fn: () => void | Promise<void>): void;
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

// Polyfill for React 19's scheduler in test environment
Object.defineProperty(window, 'MessageChannel', {
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
        return (typeof globalThis.performance !== 'undefined' && globalThis.performance.now) || Date.now;
      }
    }
  });
}
