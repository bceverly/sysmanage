// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

// Action buttons must show they were pressed and refuse a second press
// (2026-10-17: "Deploy antivirus" looked idle, inviting repeat presses).

import { act, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import AsyncButton from '../../Components/AsyncButton';
import AntivirusActionButtons from '../../Components/AntivirusActionButtons';
import SelectionActionBar from '../../Components/SelectionActionBar';
import type { AntivirusStatus } from '../../Services/antivirusService';

vi.mock('react-i18next', () => ({
    useTranslation: () => ({ t: (_k: string, fallback?: string) => fallback ?? _k }),
}));

const deferred = () => {
    let resolve!: (_v: boolean) => void;
    const promise = new Promise<boolean>((r) => { resolve = r; });
    return { promise, resolve };
};

const titles = { deploy: '', remove: '', enable: '', disable: '' };
const installed = { software_name: 'clamav', enabled: true } as unknown as AntivirusStatus;

const buttons = (status: AntivirusStatus | null, onDeploy: () => Promise<boolean>) => (
    <AntivirusActionButtons
        status={status}
        onPoll={() => undefined}
        onDeploy={onDeploy}
        canDeploy canRemove={false} canEnable={false} canDisable={false}
        blocked={{ deploy: false, other: false }}
        titles={titles}
    />
);

afterEach(() => vi.useRealTimers());

describe('AsyncButton', () => {
    it('is disabled while its handler runs, so a double click sends once', async () => {
        const gate = deferred();
        const onClick = vi.fn(() => gate.promise);
        render(<AsyncButton onClick={onClick} busyLabel="Rebooting...">Reboot</AsyncButton>);
        const button = screen.getByRole('button');
        fireEvent.click(button);
        fireEvent.click(button);
        expect(onClick).toHaveBeenCalledTimes(1);
        expect(await screen.findByText('Rebooting...')).toBeInTheDocument();
        expect(screen.getByRole('button')).toBeDisabled();
        await act(async () => { gate.resolve(true); await gate.promise; });
        expect(screen.getByRole('button')).not.toBeDisabled();
        expect(screen.getByText('Reboot')).toBeInTheDocument();
    });
});

describe('AntivirusActionButtons', () => {
    it('says Deploying... and stays disabled until the agent reports ClamAV', async () => {
        const gate = deferred();
        const onDeploy = vi.fn(() => gate.promise);
        const { rerender } = render(buttons(null, onDeploy));
        fireEvent.click(screen.getByRole('button'));
        fireEvent.click(screen.getByRole('button'));
        expect(onDeploy).toHaveBeenCalledTimes(1);
        await act(async () => { gate.resolve(true); await gate.promise; });
        // Server accepted; still waiting for the agent.
        expect(screen.getByRole('button')).toBeDisabled();
        expect(screen.getByText('Deploying...')).toBeInTheDocument();
        expect(screen.getByTestId('antivirus-awaiting')).toBeInTheDocument();
        rerender(buttons(installed, onDeploy));
        expect(screen.queryByTestId('antivirus-awaiting')).toBeNull();
    });

    it('a refused request leaves nothing to wait for', async () => {
        const onDeploy = vi.fn(() => Promise.resolve(false));
        render(buttons(null, onDeploy));
        await act(async () => { fireEvent.click(screen.getByRole('button')); });
        expect(screen.queryByTestId('antivirus-awaiting')).toBeNull();
        expect(screen.getByRole('button')).not.toBeDisabled();
    });

    it('gives up after the timeout and says the agent has not confirmed', async () => {
        vi.useFakeTimers();
        render(buttons(null, () => Promise.resolve(true)));
        await act(async () => { fireEvent.click(screen.getByRole('button')); });
        expect(screen.getByTestId('antivirus-awaiting')).toBeInTheDocument();
        await act(async () => { vi.advanceTimersByTime(10 * 60 * 1000 + 1); });
        expect(screen.queryByTestId('antivirus-awaiting')).toBeNull();
        expect(screen.getByTestId('antivirus-timed-out')).toBeInTheDocument();
    });
});

describe('SelectionActionBar', () => {
    it('holds every action while a promise-returning one runs', async () => {
        const gate = deferred();
        const deploy = vi.fn(() => gate.promise);
        const other = vi.fn();
        render(
            <SelectionActionBar
                actions={[
                    { id: 'deploy', label: 'Deploy', primary: true, onClick: deploy },
                    { id: 'other', label: 'Other', primary: true, onClick: other },
                ]}
            />,
        );
        fireEvent.click(screen.getByTestId('action-deploy'));
        fireEvent.click(screen.getByTestId('action-deploy'));
        expect(deploy).toHaveBeenCalledTimes(1);
        expect(await screen.findByTestId('action-other')).toBeDisabled();
        await act(async () => { gate.resolve(true); await gate.promise; });
        expect(screen.getByTestId('action-other')).not.toBeDisabled();
    });
});
