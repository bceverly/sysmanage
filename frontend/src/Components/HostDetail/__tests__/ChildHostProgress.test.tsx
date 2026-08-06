// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

import React from 'react';
import { vi, describe, test, expect } from 'vitest';
import { render, screen } from '@testing-library/react';

vi.mock('react-i18next', () => ({
    useTranslation: () => ({
        // Mirror i18next's t(key, fallback, params) interpolation so the
        // assertions read as the user sees them.
        t: (_key: string, fallback: string, params?: Record<string, unknown>) =>
            params
                ? fallback.replace(/\{\{(\w+)\}\}/g, (_m, k) => String(params[k] ?? ''))
                : fallback,
        i18n: { language: 'en' },
    }),
}));

import ChildHostProgress, { STALL_WARNING_MINUTES } from '../ChildHostProgress';
import type { ChildHost } from '../hostDetailTypes';

const minutesAgo = (n: number) => new Date(Date.now() - n * 60000).toISOString();

const child = (overrides: Partial<ChildHost> = {}): ChildHost => ({
    id: 'c1',
    parent_host_id: 'p1',
    child_host_id: null,
    child_name: 'win01',
    child_type: 'kvm',
    distribution: 'Windows Server',
    distribution_version: '2022',
    hostname: 'win01.example.com',
    status: 'creating',
    installation_step: 'create blank 40G disk for win01',
    installation_step_number: 4,
    installation_total_steps: 9,
    installation_step_at: minutesAgo(1),
    error_message: null,
    created_at: new Date().toISOString(),
    installed_at: null,
    ...overrides,
});

describe('ChildHostProgress', () => {
    test('renders nothing unless the child is mid-provision', () => {
        const { container } = render(<ChildHostProgress child={child({ status: 'running' })} />);
        expect(container).toBeEmptyDOMElement();
    });

    test('shows the step counter and description', () => {
        render(<ChildHostProgress child={child()} />);
        expect(screen.getByText(/4\/9 · create blank 40G disk for win01/)).toBeInTheDocument();
    });

    test('the bar is determinate when both numbers are present', () => {
        render(<ChildHostProgress child={child()} />);
        const bar = screen.getByRole('progressbar');
        expect(bar).toHaveAttribute('aria-valuenow');
        // 4 of 9
        expect(Math.round(Number(bar.getAttribute('aria-valuenow')))).toBe(44);
    });

    test('falls back to indeterminate for an older agent that sends no counts', () => {
        // A bar that reports a number it does not have is worse than an honest
        // indeterminate one.
        render(
            <ChildHostProgress
                child={child({ installation_step_number: null, installation_total_steps: null })}
            />,
        );
        expect(screen.getByRole('progressbar')).not.toHaveAttribute('aria-valuenow');
    });

    test('does not divide by a zero total', () => {
        render(<ChildHostProgress child={child({ installation_total_steps: 0 })} />);
        expect(screen.getByRole('progressbar')).not.toHaveAttribute('aria-valuenow');
    });

    test('a step beyond the total does not produce a >100% bar', () => {
        render(
            <ChildHostProgress
                child={child({ installation_step_number: 12, installation_total_steps: 9 })}
            />,
        );
        expect(screen.getByRole('progressbar')).not.toHaveAttribute('aria-valuenow');
    });

    test('states the age of the last update while healthy', () => {
        render(<ChildHostProgress child={child({ installation_step_at: minutesAgo(1) })} />);
        expect(screen.getByText(/^Updated /)).toBeInTheDocument();
        expect(screen.queryByText(/may have stalled/)).toBeNull();
    });

    test('calls out a provision with no recent update', () => {
        render(
            <ChildHostProgress
                child={child({ installation_step_at: minutesAgo(STALL_WARNING_MINUTES + 5) })}
            />,
        );
        expect(screen.getByText(/may have stalled/)).toBeInTheDocument();
    });

    test('does not cry wolf just under the threshold', () => {
        // Windows Setup runs unattended for 25-45 min between reports; a
        // warning that is usually wrong stops being read.
        render(
            <ChildHostProgress
                child={child({ installation_step_at: minutesAgo(STALL_WARNING_MINUTES - 1) })}
            />,
        );
        expect(screen.queryByText(/may have stalled/)).toBeNull();
    });

    test('survives a missing timestamp', () => {
        render(<ChildHostProgress child={child({ installation_step_at: null })} />);
        expect(screen.getByRole('progressbar')).toBeInTheDocument();
        expect(screen.queryByText(/^Updated /)).toBeNull();
    });
});
