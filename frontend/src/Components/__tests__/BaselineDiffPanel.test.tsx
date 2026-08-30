// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import BaselineDiffPanel from '../BaselineDiffPanel';
import {
    getBaselineCategories,
    getBaselineDiff,
} from '../../Services/configManagementService';
import { doGetHosts } from '../../Services/hosts';

vi.mock('react-i18next', () => ({
    useTranslation: () => ({
        // Mirrors both call shapes the component uses: t(key, 'fallback') and
        // t(key, { count, defaultValue, ...interpolations }).
        t: (key: string, opts?: unknown) => {
            if (typeof opts === 'string') return opts;
            if (opts && typeof opts === 'object') {
                const o = opts as Record<string, unknown>;
                if (typeof o.defaultValue === 'string') {
                    return Object.entries(o).reduce(
                        (text, [name, value]) =>
                            name === 'defaultValue'
                                ? text
                                : text.replace(`{{${name}}}`, String(value)),
                        o.defaultValue,
                    );
                }
            }
            return key;
        },
    }),
}));

vi.mock('../../Services/configManagementService', () => ({
    getBaselineCategories: vi.fn(),
    getBaselineDiff: vi.fn(),
}));

// The panel falls back to fetching hosts itself when no `hosts` prop is
// given -- which is how ConfigDrift renders it, so this is the REAL path.
vi.mock('../../Services/hosts', () => ({
    doGetHosts: vi.fn(),
}));

const HOSTS = [
    { id: 'target-1', fqdn: 'broken.invalid' },
    { id: 'golden-1', fqdn: 'golden.invalid' },
];

const emptyCategory = (over = {}) => ({
    missing: [],
    extra: [],
    different: [],
    counts: {
        missing: 0,
        extra: 0,
        different: 0,
        reference_total: 0,
        target_total: 0,
    },
    truncated: false,
    ...over,
});

const diff = (over = {}) => ({
    reference_host_id: 'golden-1',
    reference_fqdn: 'golden.invalid',
    host_id: 'target-1',
    host_fqdn: 'broken.invalid',
    categories: { packages: emptyCategory() },
    total_differences: 0,
    identical: true,
    ...over,
});

const renderPanel = (hosts = HOSTS) =>
    render(<BaselineDiffPanel hostId="target-1" hosts={hosts} />);

/** Pick the reference host and press Compare. */
const compare = async () => {
    const user = userEvent.setup();
    await user.click(screen.getByLabelText('Reference host'));
    await user.click(await screen.findByRole('option', { name: 'golden.invalid' }));
    await user.click(screen.getByRole('button', { name: /Compare/ }));
};

describe('BaselineDiffPanel', () => {
    beforeEach(() => {
        vi.mocked(getBaselineCategories).mockResolvedValue(['packages']);
        vi.mocked(getBaselineDiff).mockResolvedValue(diff());
        vi.mocked(doGetHosts).mockResolvedValue([]);
    });

    it('offers every host except the one being examined', async () => {
        renderPanel();
        await userEvent.setup().click(screen.getByLabelText('Reference host'));
        expect(
            await screen.findByRole('option', { name: 'golden.invalid' }),
        ).toBeInTheDocument();
        // Comparing a host with itself is refused by the server; not offering
        // it is how the UI avoids asking a question with no useful answer.
        expect(
            screen.queryByRole('option', { name: 'broken.invalid' }),
        ).not.toBeInTheDocument();
    });

    it('cannot compare until a reference is chosen', async () => {
        renderPanel();
        // Await the category fetch settling: letting it resolve after the test
        // body ends is a state update outside act(), which this suite treats
        // as a hard failure.
        await waitFor(() => expect(getBaselineCategories).toHaveBeenCalled());
        expect(screen.getByRole('button', { name: /Compare/ })).toBeDisabled();
    });

    it('says so when there is no other host to compare against', async () => {
        renderPanel([{ id: 'target-1', fqdn: 'broken.invalid' }]);
        await waitFor(() => expect(getBaselineCategories).toHaveBeenCalled());
        expect(
            screen.getByText(/no other host to compare against/i),
        ).toBeInTheDocument();
    });

    it('reports a matching host as identical', async () => {
        renderPanel();
        await compare();
        expect(
            await screen.findByText(/matches golden.invalid across every category/i),
        ).toBeInTheDocument();
    });

    it('summarises how many differences were found', async () => {
        vi.mocked(getBaselineDiff).mockResolvedValue(
            diff({
                identical: false,
                total_differences: 3,
                categories: {
                    packages: emptyCategory({
                        missing: [{ name: 'nginx' }],
                        counts: {
                            missing: 1,
                            extra: 0,
                            different: 0,
                            reference_total: 1,
                            target_total: 0,
                        },
                    }),
                },
            }),
        );
        renderPanel();
        await compare();
        expect(
            await screen.findByText(/3 difference\(s\) from golden.invalid/i),
        ).toBeInTheDocument();
    });

    it('shows a field-level comparison for entries present on both hosts', async () => {
        // The distinction an operator acts on: "you don't have it" and "you
        // have the wrong one" are different fixes.
        vi.mocked(getBaselineDiff).mockResolvedValue(
            diff({
                identical: false,
                total_differences: 1,
                categories: {
                    packages: emptyCategory({
                        different: [
                            {
                                name: 'openssl',
                                fields: {
                                    package_version: {
                                        reference: '3.0.2',
                                        target: '1.1.1',
                                    },
                                },
                            },
                        ],
                        counts: {
                            missing: 0,
                            extra: 0,
                            different: 1,
                            reference_total: 1,
                            target_total: 1,
                        },
                    }),
                },
            }),
        );
        renderPanel();
        await compare();
        expect(await screen.findByText('openssl')).toBeInTheDocument();
        expect(screen.getByText('3.0.2')).toBeInTheDocument();
        expect(screen.getByText('1.1.1')).toBeInTheDocument();
    });

    it('warns when a bucket was capped so the lists are not read as complete', async () => {
        vi.mocked(getBaselineDiff).mockResolvedValue(
            diff({
                identical: false,
                total_differences: 500,
                categories: {
                    packages: emptyCategory({
                        missing: [{ name: 'pkg-0001' }],
                        counts: {
                            missing: 500,
                            extra: 0,
                            different: 0,
                            reference_total: 500,
                            target_total: 0,
                        },
                        truncated: true,
                    }),
                },
            }),
        );
        renderPanel();
        await compare();
        expect(
            await screen.findByText(/the counts above are exact/i),
        ).toBeInTheDocument();
    });

    it('surfaces the server explanation when a comparison is refused', async () => {
        vi.mocked(getBaselineDiff).mockRejectedValue({
            response: { data: { detail: 'Reference host not found' } },
        });
        renderPanel();
        await compare();
        expect(await screen.findByText('Reference host not found')).toBeInTheDocument();
    });

    it('still works when the category list cannot be loaded', async () => {
        // Losing the category list only costs the labels; the comparison
        // itself must not be blocked by it.
        vi.mocked(getBaselineCategories).mockRejectedValue(new Error('offline'));
        renderPanel();
        await compare();
        await waitFor(() => expect(getBaselineDiff).toHaveBeenCalled());
        expect(screen.queryByText(/Comparison failed/)).not.toBeInTheDocument();
    });

    it('asks the server only for the chosen reference host', async () => {
        renderPanel();
        await compare();
        await waitFor(() =>
            expect(getBaselineDiff).toHaveBeenCalledWith('target-1', 'golden-1'),
        );
    });
    // --- the self-fetch path: no `hosts` prop, which is how ConfigDrift uses it ---
    //
    // These exist because the suite originally always passed `hosts`, so the
    // fetching branch was never run -- and it shipped listing only hosts whose
    // agent was connected, which left the picker empty on a real box. Every
    // test above would still have passed.
    describe('when no host list is supplied', () => {
        const fetched = (over = {}) => ({
            id: 'golden-1',
            fqdn: 'golden.invalid',
            approval_status: 'approved',
            active: false,
            status: 'down',
            ...over,
        });

        it('offers an approved host whose agent is offline', async () => {
            // The whole point of the feature: the broken host, and often the
            // reference too, may be down. Liveness is irrelevant because the
            // comparison reads stored inventory and never contacts an agent.
            vi.mocked(doGetHosts).mockResolvedValue([
                fetched(),
                fetched({ id: 'target-1', fqdn: 'broken.invalid' }),
            ] as never);
            render(<BaselineDiffPanel hostId="target-1" />);
            await userEvent.setup().click(screen.getByLabelText('Reference host'));
            expect(
                await screen.findByRole('option', { name: 'golden.invalid' }),
            ).toBeInTheDocument();
        });

        it('does not offer hosts that were never approved', async () => {
            vi.mocked(doGetHosts).mockResolvedValue([
                fetched(),
                fetched({ id: 'pending-1', fqdn: 'pending.invalid',
                          approval_status: 'pending', active: true, status: 'up' }),
            ] as never);
            render(<BaselineDiffPanel hostId="target-1" />);
            await userEvent.setup().click(screen.getByLabelText('Reference host'));
            expect(
                await screen.findByRole('option', { name: 'golden.invalid' }),
            ).toBeInTheDocument();
            expect(
                screen.queryByRole('option', { name: 'pending.invalid' }),
            ).not.toBeInTheDocument();
        });

        it('says there is nothing to compare against when the fetch fails', async () => {
            vi.mocked(doGetHosts).mockRejectedValue(new Error('offline'));
            render(<BaselineDiffPanel hostId="target-1" />);
            expect(
                await screen.findByText(/no other host to compare against/i),
            ).toBeInTheDocument();
        });
    });

});
