import React from 'react';
import { render, screen, act } from '@testing-library/react';
import { vi } from 'vitest';
import App from '../App';

// Mock the components to avoid routing complexity in unit tests
vi.mock('../Components/Navbar', () => ({
  default: () => <div data-testid="navbar">Mock Navbar</div>
}));

vi.mock('../Pages/Home', () => ({
  default: () => <div data-testid="home">Mock Home</div>
}));

vi.mock('../Pages/Login', () => ({
  default: () => <div data-testid="login">Mock Login</div>
}));

vi.mock('../Pages/Logout', () => ({
  default: () => <div data-testid="logout">Mock Logout</div>
}));

vi.mock('../Pages/Users', () => ({
  default: () => <div data-testid="users">Mock Users</div>
}));

vi.mock('../Pages/Hosts', () => ({
  default: () => <div data-testid="hosts">Mock Hosts</div>
}));

// Mock ConnectionProvider to avoid async issues
vi.mock('../Components/ConnectionProvider', () => ({
  default: ({ children }: { children: React.ReactNode }) => <div>{children}</div>
}));

// Mock SecurityWarningBanner
vi.mock('../Components/SecurityWarningBanner', () => ({
  default: () => null
}));

describe('App Component', () => {
  test('renders without crashing', async () => {
    await act(async () => {
      render(<App />);
    });
    expect(screen.getByTestId('navbar')).toBeInTheDocument();
  }, 10000); // Increased timeout for Windows CI

  test('contains navbar component', async () => {
    await act(async () => {
      render(<App />);
    });
    expect(screen.getByTestId('navbar')).toBeInTheDocument();
  }, 10000); // Increased timeout for Windows CI

  test('has proper document structure', async () => {
    await act(async () => {
      render(<App />);
    });
    expect(screen.getByTestId('navbar')).toBeInTheDocument();
  }, 10000); // Increased timeout for Windows CI
});