// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

import React from 'react';
import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import HostCapabilitiesCard from '../HostCapabilitiesCard';

vi.mock('react-i18next', () => ({
    useTranslation: () => ({
        // Return the English fallback so assertions read as the user sees it.
        t: (_key: string, fallback?: string) => fallback ?? _key,
    }),
}));

describe('HostCapabilitiesCard', () => {
    it('reads as UNKNOWN when the agent never advertised', () => {
        // The important case: an agent that has not upgraded reports nothing,
        // and calling that "full" would state something the server cannot know.
        render(<HostCapabilitiesCard report={null} limited={null} />);
        expect(screen.getByText(/has not advertised/i)).toBeTruthy();
        expect(screen.queryByText('Full')).toBeNull();
        expect(screen.queryByText('Limited')).toBeNull();
    });

    it('shows Full for an agent with no gaps', () => {
        render(
            <HostCapabilitiesCard
                report={{ capabilities: ['packages'], commands: ['install_package'] }}
                limited={false}
            />
        );
        expect(screen.getByText('Full')).toBeTruthy();
        expect(screen.getByText('packages')).toBeTruthy();
    });

    it('shows Limited and names the unavailable group WITH its reason', () => {
        render(
            <HostCapabilitiesCard
                report={{
                    capabilities: ['packages'],
                    unavailable: { virtualization: 'no_handler' },
                }}
                limited={true}
            />
        );
        expect(screen.getByText('Limited')).toBeTruthy();
        expect(screen.getByText(/virtualization/)).toBeTruthy();
        expect(screen.getByText(/Not built into this agent/)).toBeTruthy();
    });

    it('shows an UNKNOWN reason code rather than swallowing it', () => {
        // A newer agent may send a code this build has no translation for.
        // Hiding it would leave the operator with a gap and no explanation.
        render(
            <HostCapabilitiesCard
                report={{ unavailable: { secrets: 'some_future_reason' } }}
                limited={true}
            />
        );
        expect(screen.getByText(/some_future_reason/)).toBeTruthy();
    });

    it('lists partially-supported groups with a count', () => {
        render(
            <HostCapabilitiesCard
                report={{ partial: { virtualization: ['initialize_kvm', 'delete_vm'] } }}
                limited={true}
            />
        );
        expect(screen.getByText('virtualization (2)')).toBeTruthy();
    });

    it('tolerates a report with no optional fields at all', () => {
        // normalize_report() guarantees `commands`, but the others can be
        // absent/empty; the card must not throw on a minimal report.
        render(<HostCapabilitiesCard report={{ commands: ['x'] }} limited={false} />);
        expect(screen.getByText('Full')).toBeTruthy();
    });
});
