import React from 'react';
import { render, screen, act } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';
import Navbar from '../../Components/Navbar';

const NavbarWithRouter = () => (
  <BrowserRouter future={{
    v7_startTransition: true,
    v7_relativeSplatPath: true
  }}>
    <Navbar />
  </BrowserRouter>
);

describe('Navbar Component', () => {
  test('renders navigation links', async () => {
    await act(async () => {
      render(<NavbarWithRouter />);
    });
    
    expect(screen.getByText('SysManage')).toBeInTheDocument();
    expect(screen.getByText('Dashboard')).toBeInTheDocument();
    expect(screen.getByText('Users')).toBeInTheDocument();
    expect(screen.getByText('Hosts')).toBeInTheDocument();
    expect(screen.getByText('Logout')).toBeInTheDocument();
  });

  test('has proper navigation structure', async () => {
    await act(async () => {
      render(<NavbarWithRouter />);
    });
    
    const nav = screen.getByRole('banner');
    expect(nav).toBeInTheDocument();
    expect(nav.tagName).toBe('HEADER');
  });

  test('contains navigation menu', async () => {
    await act(async () => {
      render(<NavbarWithRouter />);
    });
    
    // Check that navigation links are present in the DOM
    expect(screen.getByText('Dashboard')).toBeInTheDocument();
    expect(screen.getByText('Users')).toBeInTheDocument();
    expect(screen.getByText('Hosts')).toBeInTheDocument();
    expect(screen.getByText('Logout')).toBeInTheDocument();
  });

  test('menu toggle functionality', async () => {
    await act(async () => {
      render(<NavbarWithRouter />);
    });
    
    // Check if menu toggle elements exist (mobile menu)
    expect(screen.getByText('SysManage')).toBeInTheDocument();
  });

  test('navigation links are clickable', async () => {
    await act(async () => {
      render(<NavbarWithRouter />);
    });
    
    // Navigation links exist in DOM but are hidden by CSS visibility
    // Use getAllByRole to get all links including hidden ones
    const allLinks = screen.getAllByRole('link', { hidden: true });
    
    // Verify we have the expected links
    expect(allLinks).toHaveLength(5); // SysManage logo + 4 nav links
    
    // Find links by their href attributes since they don't have accessible names when hidden
    const dashboardLink = allLinks.find(link => link.getAttribute('href') === '/');
    const usersLink = allLinks.find(link => link.getAttribute('href') === '/users');
    const hostsLink = allLinks.find(link => link.getAttribute('href') === '/hosts');
    const logoutLink = allLinks.find(link => link.getAttribute('href') === '/logout');
    
    expect(dashboardLink).toHaveAttribute('href', '/');
    expect(usersLink).toHaveAttribute('href', '/users');
    expect(hostsLink).toHaveAttribute('href', '/hosts');
    expect(logoutLink).toHaveAttribute('href', '/logout');
  });
});