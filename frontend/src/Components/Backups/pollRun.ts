// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

// Follow a backup job until it ends: read the run every ``ms`` and hand each
// read to ``onRun``.  Shared by the dialogs that start a short job and show
// its result (changes since the last snapshot, a snapshot's folders).

import { getRun } from '../../Services/backups';
import type { BackupRun } from '../../Services/backups';

export const FINISHED = new Set(['ok', 'different', 'incomplete', 'failed', 'untrusted', 'busy']);

/** Start polling run ``id``; the returned function stops it. */
export const pollRun = (id: string, onRun: (run: BackupRun) => void, ms: number): (() => void) => {
    let alive = true;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const tick = async () => {
        const fresh = await getRun(id);
        if (!alive) return;
        onRun(fresh);
        if (!FINISHED.has(fresh.status)) timer = setTimeout(next, ms);
    };
    // A failed read stops the polling; the dialog keeps the last run it showed.
    const next = () => { tick().catch(() => undefined); };
    next();
    return () => { alive = false; if (timer) clearTimeout(timer); };
};
