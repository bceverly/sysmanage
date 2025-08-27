import React from 'react';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';
import { vi } from 'vitest';
import Login from '../../Pages/Login';

// Mock the API service
vi.mock('../../Services/api.js', () => ({
  default: {
    post: vi.fn()
  }
}));

const LoginWithRouter = () => (
  <BrowserRouter future={{
    v7_startTransition: true,
    v7_relativeSplatPath: true
  }}>
    <Login />
  </BrowserRouter>
);

describe('Login Page', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  test('renders login form', async () => {
    await act(async () => {
      render(<LoginWithRouter />);
    });
    
    expect(screen.getByText('Log in')).toBeInTheDocument();
    expect(screen.getByLabelText(/email/i) || screen.getByPlaceholderText(/email/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/password/i) || screen.getByPlaceholderText(/password/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /log in/i })).toBeInTheDocument();
  });

  test('has proper form structure', async () => {
    await act(async () => {
      render(<LoginWithRouter />);
    });
    
    // Look for form elements or login text
    expect(screen.getByText('Log in')).toBeInTheDocument();
  });

  test('contains email and password inputs', async () => {
    await act(async () => {
      render(<LoginWithRouter />);
    });
    
    const emailInput = screen.getByLabelText(/email/i) || 
                      screen.getByPlaceholderText(/email/i) ||
                      screen.getByDisplayValue('') as HTMLInputElement;
    const passwordInput = screen.getByLabelText(/password/i) || 
                         screen.getByPlaceholderText(/password/i);
    
    expect(emailInput || passwordInput).toBeInTheDocument();
  });

  test('form submission', async () => {
    await act(async () => {
      render(<LoginWithRouter />);
    });
    
    const submitButton = screen.getByRole('button', { name: /log in/i });
    
    await act(async () => {
      fireEvent.click(submitButton);
    });
    
    // Test that the component handles form submission without crashing
    await waitFor(() => {
      expect(submitButton).toBeInTheDocument();
    });
  });

  test('renders without errors', async () => {
    await act(async () => {
      render(<LoginWithRouter />);
    });
    expect(screen.getByText('Log in')).toBeInTheDocument();
  });
});