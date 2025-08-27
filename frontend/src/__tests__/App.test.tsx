import React from 'react';
import { render, screen } from '@testing-library/react';
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

describe('App Component', () => {
  test('renders without crashing', () => {
    render(<App />);
    expect(screen.getByTestId('navbar')).toBeInTheDocument();
  });

  test('contains navbar component', () => {
    render(<App />);
    expect(screen.getByTestId('navbar')).toBeInTheDocument();
  });

  test('has proper document structure', () => {
    render(<App />);
    expect(screen.getByTestId('navbar')).toBeInTheDocument();
  });
});