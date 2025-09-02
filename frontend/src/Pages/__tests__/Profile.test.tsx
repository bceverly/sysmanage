/**
 * Unit tests for Profile page component
 */

import React from 'react';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, it, expect, beforeEach, vi } from 'vitest';
import Profile from '../Profile';
import * as profileService from '../../Services/profile';

// Mock the profile service
vi.mock('../../Services/profile');

// Mock react-i18next
vi.mock('react-i18next', () => ({
    useTranslation: () => ({
        t: (key: string, defaultValue?: string) => defaultValue || key,
    }),
}));

// Helper function to render component with Router
const renderWithRouter = (component: React.ReactElement) => {
    return render(
        <MemoryRouter future={{
            v7_startTransition: true,
            v7_relativeSplatPath: true
        }}>
            {component}
        </MemoryRouter>
    );
};

describe('Profile Component', () => {
    beforeEach(() => {
        vi.clearAllMocks();
    });

    describe('Loading State', () => {
        it('should show loading spinner while fetching profile', () => {
            vi.mocked(profileService.getProfile).mockImplementation(() => new Promise(() => {}));

            renderWithRouter(<Profile />);

            expect(screen.getByRole('progressbar')).toBeInTheDocument();
        });
    });

    describe('Service Integration', () => {
        it('should call getProfile service on mount', () => {
            vi.mocked(profileService.getProfile).mockImplementation(() => new Promise(() => {}));

            renderWithRouter(<Profile />);

            expect(profileService.getProfile).toHaveBeenCalledTimes(1);
        });

        it('should have proper component structure when loading', () => {
            vi.mocked(profileService.getProfile).mockImplementation(() => new Promise(() => {}));

            renderWithRouter(<Profile />);

            expect(screen.getByRole('progressbar')).toBeInTheDocument();
            expect(screen.queryByText('Profile')).not.toBeInTheDocument();
        });
    });
});