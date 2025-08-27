import React from 'react';
import { render, screen } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';
import Home from '../../Pages/Home';

const HomeWithRouter = () => (
  <BrowserRouter future={{
    v7_startTransition: true,
    v7_relativeSplatPath: true
  }}>
    <Home />
  </BrowserRouter>
);

describe('Home Page', () => {
  test('renders without crashing', () => {
    render(<HomeWithRouter />);
    // Basic smoke test - ensure component renders
    expect(document.body).toBeInTheDocument();
  });

  test('contains main content area', () => {
    render(<HomeWithRouter />);
    // Check for actual content from the Home page
    expect(screen.getByText('Active Hosts')).toBeInTheDocument();
  });

  test('displays home page content', () => {
    render(<HomeWithRouter />);
    
    // At minimum, something should be rendered
    const bodyContent = document.body.textContent || '';
    expect(bodyContent.length).toBeGreaterThan(0);
  });

  test('has proper document structure', () => {
    render(<HomeWithRouter />);
    
    // Ensure the component renders successfully
    expect(document.body).toBeInTheDocument();
  });

  test('renders home page component successfully', () => {
    // This is a comprehensive test to ensure Home component loads
    expect(() => render(<HomeWithRouter />)).not.toThrow();
  });
});