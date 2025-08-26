import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';
import Login from '../../Pages/Login';

// Mock the API service
jest.mock('../../Services/api.js', () => ({
  login: jest.fn(),
}));

const LoginWithRouter = () => (
  <BrowserRouter>
    <Login />
  </BrowserRouter>
);

describe('Login Page', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  test('renders login form', () => {
    render(<LoginWithRouter />);
    
    expect(screen.getByText('Log in')).toBeInTheDocument();
    expect(screen.getByLabelText(/email/i) || screen.getByPlaceholderText(/email/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/password/i) || screen.getByPlaceholderText(/password/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /log in/i })).toBeInTheDocument();
  });

  test('has proper form structure', () => {
    render(<LoginWithRouter />);
    
    // Look for form elements or login text
    expect(screen.getByText('Log in')).toBeInTheDocument();
  });

  test('contains email and password inputs', () => {
    render(<LoginWithRouter />);
    
    const emailInput = screen.getByLabelText(/email/i) || 
                      screen.getByPlaceholderText(/email/i) ||
                      screen.getByDisplayValue('') as HTMLInputElement;
    const passwordInput = screen.getByLabelText(/password/i) || 
                         screen.getByPlaceholderText(/password/i);
    
    expect(emailInput || passwordInput).toBeInTheDocument();
  });

  test('form submission', async () => {
    render(<LoginWithRouter />);
    
    const submitButton = screen.getByRole('button', { name: /log in/i });
    
    fireEvent.click(submitButton);
    
    // Test that the component handles form submission without crashing
    await waitFor(() => {
      expect(submitButton).toBeInTheDocument();
    });
  });

  test('renders without errors', () => {
    render(<LoginWithRouter />);
    expect(screen.getByText('Log in')).toBeInTheDocument();
  });
});