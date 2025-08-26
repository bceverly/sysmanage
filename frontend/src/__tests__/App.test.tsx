import React from 'react';
import { render, screen } from '@testing-library/react';
import App from '../App';

// Mock the components to avoid routing complexity in unit tests
jest.mock('../Components/Navbar', () => {
  return function MockNavbar() {
    return <div data-testid="navbar">Mock Navbar</div>;
  };
});

jest.mock('../Pages/Home', () => {
  return function MockHome() {
    return <div data-testid="home">Mock Home</div>;
  };
});

jest.mock('../Pages/Login', () => {
  return function MockLogin() {
    return <div data-testid="login">Mock Login</div>;
  };
});

jest.mock('../Pages/Logout', () => {
  return function MockLogout() {
    return <div data-testid="logout">Mock Logout</div>;
  };
});

jest.mock('../Pages/Users', () => {
  return function MockUsers() {
    return <div data-testid="users">Mock Users</div>;
  };
});

jest.mock('../Pages/Hosts', () => {
  return function MockHosts() {
    return <div data-testid="hosts">Mock Hosts</div>;
  };
});

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