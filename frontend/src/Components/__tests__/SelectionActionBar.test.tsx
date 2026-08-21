// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

import React from 'react';
import { fireEvent, render, screen, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import SelectionActionBar, { SelectionAction } from '../SelectionActionBar';

vi.mock('react-i18next', () => ({
    useTranslation: () => ({
        // Mirrors both call shapes the component uses: t(key, 'fallback') and
        // t(key, { count, defaultValue }).
        t: (key: string, opts?: unknown) => {
            if (typeof opts === 'string') return opts;
            if (opts && typeof opts === 'object') {
                const o = opts as { count?: number; defaultValue?: string };
                if (o.defaultValue) {
                    return o.defaultValue.replace('{{count}}', String(o.count ?? ''));
                }
            }
            return key;
        },
    }),
}));

const action = (over: Partial<SelectionAction> & { id: string }): SelectionAction => ({
    label: over.id,
    onClick: vi.fn(),
    ...over,
});

const openMenu = () => fireEvent.click(screen.getByTestId('selection-more'));

describe('SelectionActionBar', () => {
    it('shows primaries as buttons and puts the rest behind one menu', () => {
        render(
            <SelectionActionBar
                actions={[
                    action({ id: 'approve', primary: true }),
                    action({ id: 'refresh', primary: true }),
                    action({ id: 'antivirus' }),
                    action({ id: 'otel' }),
                ]}
            />,
        );
        expect(screen.getByTestId('action-approve')).toBeTruthy();
        expect(screen.getByTestId('action-refresh')).toBeTruthy();
        // Not rendered at all until the menu is opened.
        expect(screen.queryByTestId('action-antivirus')).toBeNull();
        openMenu();
        expect(screen.getByTestId('action-antivirus')).toBeTruthy();
    });

    it('puts the hidden count on the More button', () => {
        // The whole failure of the old scrolling bar was that nothing told you
        // actions existed off-screen.
        render(
            <SelectionActionBar
                actions={[
                    action({ id: 'a', primary: true }),
                    action({ id: 'b' }),
                    action({ id: 'c' }),
                    action({ id: 'd' }),
                ]}
            />,
        );
        expect(screen.getByTestId('selection-more').textContent).toContain('3');
    });

    it('never renders a More button when everything fits', () => {
        render(
            <SelectionActionBar
                actions={[action({ id: 'a', primary: true }), action({ id: 'b', primary: true })]}
            />,
        );
        expect(screen.queryByTestId('selection-more')).toBeNull();
    });

    it('caps the primary row at maxPrimary and overflows the remainder', () => {
        render(
            <SelectionActionBar
                maxPrimary={2}
                actions={[
                    action({ id: 'a', primary: true }),
                    action({ id: 'b', primary: true }),
                    action({ id: 'c', primary: true }),
                ]}
            />,
        );
        expect(screen.queryByTestId('selection-more')).toBeTruthy();
        expect(screen.getByTestId('selection-more').textContent).toContain('1');
    });

    it('keeps disabled actions visible and explains them in the menu', () => {
        // Disabled-with-a-reason, never hidden: hiding makes an action
        // undiscoverable and makes the bar jump width as selection changes.
        render(
            <SelectionActionBar
                actions={[
                    action({ id: 'a', primary: true }),
                    action({
                        id: 'diagnostics',
                        disabled: true,
                        disabledReason: 'Requires exactly one host',
                    }),
                ]}
            />,
        );
        openMenu();
        const item = screen.getByTestId('action-diagnostics');
        expect(within(item).getByText('Requires exactly one host')).toBeTruthy();
        expect(item.getAttribute('aria-disabled')).toBe('true');
    });

    it('does not fire a disabled action', () => {
        const onClick = vi.fn();
        render(
            <SelectionActionBar
                actions={[
                    action({ id: 'a', primary: true }),
                    action({ id: 'nope', disabled: true, onClick }),
                ]}
            />,
        );
        openMenu();
        fireEvent.click(screen.getByTestId('action-nope'));
        expect(onClick).not.toHaveBeenCalled();
    });

    it('runs a menu action and closes the menu', () => {
        const onClick = vi.fn();
        render(
            <SelectionActionBar
                actions={[action({ id: 'a', primary: true }), action({ id: 'go', onClick })]}
            />,
        );
        openMenu();
        fireEvent.click(screen.getByTestId('action-go'));
        expect(onClick).toHaveBeenCalledTimes(1);
    });

    it('sorts destructive actions last in the menu', () => {
        render(
            <SelectionActionBar
                actions={[
                    action({ id: 'a', primary: true }),
                    action({ id: 'shutdown', destructive: true }),
                    action({ id: 'antivirus' }),
                ]}
            />,
        );
        openMenu();
        const items = screen.getAllByRole('menuitem').map((el) => el.getAttribute('data-testid'));
        expect(items.indexOf('action-antivirus')).toBeLessThan(items.indexOf('action-shutdown'));
    });

    it('omits hidden actions entirely, and renders nothing when all are hidden', () => {
        const { container, rerender } = render(
            <SelectionActionBar
                actions={[action({ id: 'a', primary: true }), action({ id: 'secret', hidden: true })]}
            />,
        );
        // 'secret' is hidden, so the only visible action is the primary one
        // and there is no overflow menu to open at all.
        expect(screen.queryByTestId('selection-more')).toBeNull();
        expect(screen.queryByTestId('action-secret')).toBeNull();

        rerender(<SelectionActionBar actions={[action({ id: 'secret', hidden: true })]} />);
        expect(container.textContent).toBe('');
    });

    it('shows the selection summary and a clear affordance only when something is selected', () => {
        const onClear = vi.fn();
        const { rerender } = render(
            <SelectionActionBar
                actions={[action({ id: 'a', primary: true })]}
                selectionCount={0}
                onClearSelection={onClear}
            />,
        );
        expect(screen.queryByTestId('selection-summary')).toBeNull();

        rerender(
            <SelectionActionBar
                actions={[action({ id: 'a', primary: true })]}
                selectionCount={3}
                onClearSelection={onClear}
            />,
        );
        expect(screen.getByTestId('selection-summary').textContent).toContain('3');
        fireEvent.click(screen.getByTestId('selection-clear'));
        expect(onClear).toHaveBeenCalledTimes(1);
    });

    it('lets a screen name the selection in its own words', () => {
        render(
            <SelectionActionBar
                actions={[action({ id: 'a', primary: true })]}
                selectionCount={2}
                selectionLabel={(n) => `${n} hosts selected`}
            />,
        );
        expect(screen.getByTestId('selection-summary').textContent).toBe('2 hosts selected');
    });
});
