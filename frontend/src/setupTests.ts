// jest-dom adds custom jest matchers for asserting on DOM nodes.
// allows you to do things like:
// expect(element).toHaveTextContent(/react/i)
// learn more: https://github.com/testing-library/jest-dom
import '@testing-library/jest-dom';
import './__tests__/setup';

// Fix for React 18 Scheduler compatibility in JSDOM environment
// This addresses the "Cannot read properties of undefined (reading 'S')" error
global.IS_REACT_ACT_ENVIRONMENT = true;

// Polyfill for React 18's scheduler in test environment
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
