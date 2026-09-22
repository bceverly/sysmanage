// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import FileWatchPanel from '../FileWatchPanel';
import {
    createFileWatch,
    deleteFileWatch,
    listFileWatches,
} from '../../Services/fileWatchService';

// `t` MUST be a stable reference across renders. The panel useCallback's
// `load` over [t] and useEffect's over [load], so a fresh `t` per render makes
// `load` a new function every render, re-fires the effect, and `load`'s own
// `setError(null)` wipes any error before a test can observe it -- an
// infinite re-render that never settles. The real react-i18next `t` is
// memoized, so this is a mock artefact, not a component bug.
vi.mock('react-i18next', () => {
    const t = (key: string, opts?: unknown) =>
        typeof opts === 'string' ? opts : key;
    return { useTranslation: () => ({ t }) };
});

vi.mock('../../Services/fileWatchService', () => ({
    listFileWatches: vi.fn(),
    createFileWatch: vi.fn(),
    deleteFileWatch: vi.fn(),
}));

const watch = (over = {}) => ({
    id: 'w-1',
    name: 'CIS baseline',
    description: null,
    version: 1,
    enabled: true,
    created_by: 'admin',
    created_at: null,
    path_count: 4,
    ...over,
});

describe('FileWatchPanel', () => {
    beforeEach(() => {
        vi.mocked(listFileWatches).mockResolvedValue([]);
        vi.mocked(createFileWatch).mockResolvedValue(watch());
        vi.mocked(deleteFileWatch).mockResolvedValue(undefined);
    });

    it('says plainly that file contents are never collected', async () => {
        // The security property the whole design rests on. An operator
        // deciding whether to watch /etc/shadow needs to read this without
        // going to the documentation.
        render(<FileWatchPanel canEdit />);
        expect(
            await screen.findByText(/never the contents/i),
        ).toBeInTheDocument();
    });

    it('is honest that drift will not say what changed', async () => {
        render(<FileWatchPanel canEdit />);
        expect(
            await screen.findByText(/rather than what changed inside it/i),
        ).toBeInTheDocument();
    });

    it('lists existing watch lists with their path counts', async () => {
        vi.mocked(listFileWatches).mockResolvedValue([watch()]);
        render(<FileWatchPanel canEdit />);
        expect(await screen.findByText('CIS baseline')).toBeInTheDocument();
        expect(screen.getByText('4')).toBeInTheDocument();
    });

    it('shows an empty state rather than a bare table', async () => {
        render(<FileWatchPanel canEdit />);
        expect(
            await screen.findByText('No file watch lists yet.'),
        ).toBeInTheDocument();
    });

    it('hides authoring controls from a user who cannot edit', async () => {
        vi.mocked(listFileWatches).mockResolvedValue([watch()]);
        render(<FileWatchPanel canEdit={false} />);
        await screen.findByText('CIS baseline');
        expect(screen.queryByRole('button', { name: 'New list' })).toBeNull();
        expect(screen.queryByRole('button', { name: 'Delete list' })).toBeNull();
    });

    it('submits one path per line', async () => {
        const user = userEvent.setup();
        render(<FileWatchPanel canEdit />);
        await user.click(await screen.findByRole('button', { name: 'New list' }));
        await user.type(screen.getByLabelText('Name'), 'base');
        await user.type(
            screen.getByLabelText('Paths, one per line'),
            '/etc/hosts\n/etc/motd',
        );
        await user.click(screen.getByRole('button', { name: 'Save' }));

        await waitFor(() =>
            expect(createFileWatch).toHaveBeenCalledWith({
                name: 'base',
                paths: [{ path: '/etc/hosts' }, { path: '/etc/motd' }],
            }),
        );
    });

    it('surfaces the server refusal verbatim rather than a generic message', async () => {
        // The server refuses a list it cannot collect honestly -- a relative
        // path, a duplicate. Replacing that with "could not save" would leave
        // the operator unable to fix it.
        vi.mocked(createFileWatch).mockRejectedValue({
            response: { data: { detail: 'Watched path must be absolute: etc/hosts' } },
        });
        const user = userEvent.setup();
        render(<FileWatchPanel canEdit />);
        await user.click(await screen.findByRole('button', { name: 'New list' }));
        await user.type(screen.getByLabelText('Name'), 'base');
        await user.type(screen.getByLabelText('Paths, one per line'), 'etc/hosts');
        await user.click(screen.getByRole('button', { name: 'Save' }));

        expect(
            await screen.findByText(/must be absolute: etc\/hosts/),
        ).toBeInTheDocument();
    });

    it('warns that a relative path watches different files on each host', async () => {
        const user = userEvent.setup();
        render(<FileWatchPanel canEdit />);
        await user.click(await screen.findByRole('button', { name: 'New list' }));
        expect(
            screen.getByText(/resolves differently on each host/i),
        ).toBeInTheDocument();
    });

    it('reports a load failure instead of showing an empty list', async () => {
        // An empty list and a failed fetch look identical on screen, and one
        // of them means "you have no coverage".
        vi.mocked(listFileWatches).mockRejectedValue(new Error('boom'));
        render(<FileWatchPanel canEdit />);
        expect(
            await screen.findByText('Could not load file watch lists'),
        ).toBeInTheDocument();
    });

    it('refuses to submit an incomplete form', async () => {
        const user = userEvent.setup();
        render(<FileWatchPanel canEdit />);
        await user.click(await screen.findByRole('button', { name: 'New list' }));
        expect(screen.getByRole('button', { name: 'Save' })).toBeDisabled();
    });
});
