import React from 'react';
import { render, RenderOptions } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';

// Custom render function that includes providers
interface AllTheProvidersProps {
  children: React.ReactNode;
}

const AllTheProviders: React.FC<AllTheProvidersProps> = ({ children }) => {
  return <BrowserRouter>{children}</BrowserRouter>;
};

const customRender = (
  ui: React.ReactElement,
  options?: Omit<RenderOptions, 'wrapper'>
) => render(ui, { wrapper: AllTheProviders, ...options });

// Export everything from testing-library
export * from '@testing-library/react';

// Override render method
export { customRender as render };

// Helper functions for common test scenarios
export const mockLocalStorage = {
  getItem: jest.fn(),
  setItem: jest.fn(),
  removeItem: jest.fn(),
  clear: jest.fn(),
};

export const setupLocalStorageMock = () => {
  Object.defineProperty(window, 'localStorage', {
    value: mockLocalStorage,
    writable: true
  });
};

export const mockAuthToken = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4gRG9lIiwiaWF0IjoxNTE2MjM5MDIyfQ.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c';

export const createMockApiResponse = (data: any, status = 200) => ({
  data,
  status,
  statusText: 'OK',
  headers: {},
  config: {}
});

export const waitForLoadingToFinish = () => 
  new Promise(resolve => setTimeout(resolve, 0));

// Simple test to satisfy Jest requirement
describe('Test Utils', () => {
  test('utility functions exist', () => {
    expect(mockLocalStorage).toBeDefined();
    expect(setupLocalStorageMock).toBeDefined();
    expect(mockAuthToken).toBeDefined();
    expect(createMockApiResponse).toBeDefined();
    expect(waitForLoadingToFinish).toBeDefined();
  });
});